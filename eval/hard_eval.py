"""Hard eval: course-unique facts the model cannot know from pretraining.

course_eval.py has a ceiling problem -- its glossary terms (Basis, Derivative,
LTP, PCR) are common trading vocabulary, so the baseline already scores 0.88
and the test cannot distinguish "taught" from "already knew".

This one builds cloze (fill-in-the-blank) items from sentences that carry a
specific number or date. The missing span is the ground truth. If a fact comes
only from this corpus, baseline should score near zero and taught should not.

NOTE: collect_items() currently yields only 2 items, so --n 16 silently
tests 2. fact_eval.py is the gate; this file is a working prototype kept
for the record, not a gate.

    python3 eval/hard_eval.py [--n 16] [--provider opencode_cli]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.base import get_adapter  # noqa: E402
from engine import paths, rag, schema  # noqa: E402

# A sentence carrying a concrete value worth memorising.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_VALUE = re.compile(
    r"(T\+\d"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d+(?:\.\d+)?\s*%"
    r"₹\s?[\d][\d,]*(?:\.\d+)?"
    r"|\d+\s*:\s*\d+"
    r"|\b\d{1,3}(?:,\d{3})+\b)"
)
_MIN_CTX = 45
_MAX_CTX = 260


def collect_items() -> list[tuple[str, str, str]]:
    """-> [(sentence, answer, source)] with the answer span blanked out."""
    items: list[tuple[str, str, str]] = []
    for root, _d, files in sorted(os.walk(paths.COURSE_DIR)):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), paths.COURSE_DIR)
            with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as f:
                text = f.read()
            # Strip tables and code so we don't quiz on formatting.
            text = re.sub(r"^\|.*$", " ", text, flags=re.M)
            text = re.sub(r"```.*?```", " ", text, flags=re.S)
            text = re.sub(r"^\s*[-*]\s+", " ", text, flags=re.M)
            for sent in _SENT_SPLIT.split(text):
                sent = re.sub(r"\s+", " ", sent).strip(" -#*")
                if not (_MIN_CTX <= len(sent) <= _MAX_CTX):
                    continue
                if sent.count("`") or sent.count("|"):
                    continue
                m = _VALUE.search(sent)
                if not m:
                    continue
                ans = m.group(0)
                # Require the value to be the payload of the sentence, not a aside.
                before = sent[:m.start()].strip()
                if not before.endswith(("of", "is", "at", "to", "than", "by", "=",
                                        "per", "for", "in", "and", "or")) and \
                   not re.search(r"(?:is|of|at|to|than|by|per|for)\s*$", before, re.I):
                    continue
                items.append((sent, ans, rel))
    # De-duplicate by answer+source.
    seen, out = set(), []
    for s, a, src in items:
        k = (a.lower(), src)
        if k in seen:
            continue
        seen.add(k)
        out.append((s, a, src))
    return out


def blank(sentence: str, answer: str) -> str:
    return sentence.replace(answer, "____", 1)


def norm(s: str) -> str:
    s = str(s).strip().lower().strip(".,;:!?'\"")
    s = re.sub(r"[\u20b9,]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def score(given: str, answer: str) -> float:
    """1.0 exact-ish match, 0.5 if the digits agree but formatting differs."""
    g, a = norm(given), norm(answer)
    if not g:
        return 0.0
    if g == a:
        return 1.0
    gd = re.sub(r"[^0-9]", "", g)
    ad = re.sub(r"[^0-9]", "", a)
    if gd and gd == ad:
        return 0.5
    # containment either way (model may echo the unit)
    if a in g or g in a:
        return 0.5
    return 0.0


SYSTEM = """You are completing sentences from a trading course.
Fill the single blank marked ____ with the missing value only.
Return exactly one JSON object mapping the sentence index (as a string,
e.g. "1") to the missing value. No markdown, no explanations."""


def ask(adapter, sentences: list[str], pack: str | None = None,
        retry_wait: int = 40) -> dict:
    lines = [f"{i+1}. {s}" for i, s in enumerate(sentences)]
    user = ("Fill each blank with the missing value:\n\n" + "\n".join(lines) +
            '\n\nReturn exactly one JSON object keyed by index, e.g. {"1": "..."}')
    if pack:
        user = ("## Course reference material\n" + pack + "\n\n## Questions\n" + user)
    last = ""
    for attempt in range(1, 4):
        try:
            raw = adapter.complete(SYSTEM, user)
            obj = schema.extract_json(raw)
            if isinstance(obj, dict) and obj:
                return obj
            last = "empty object"
        except Exception as e:
            last = str(e)
            # The free gateway reports an empty bucket as 429 / limit. Back
            # off instead of hammering it; hammering extends the block.
            wait = retry_wait if "429" in last or "limit" in last.lower() else 3
            if attempt < 3:
                print(f"    retry {attempt} in {wait}s: {last[:90]}")
                time.sleep(wait)
    raise SystemExit(f"model call failed after 3 attempts: {last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--seed", type=int, default=20261120)
    a = ap.parse_args()

    items = collect_items()
    if not items:
        raise SystemExit("no cloze items found -- check course content")
    random.Random(a.seed).shuffle(items)
    sample = items[:a.n]

    with open(paths.CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    adapter = get_adapter(cfg, a.provider)
    prov = a.provider or cfg.get("active")

    # The taught condition must retrieve the source chunks. These are cloze
    # items built from course sentences; pack.json holds glossary/outline/
    # thresholds, not the sentences. Without retrieval "taught" is the same
    # call as "baseline", and the delta is only sampling noise.
    if not os.path.exists(paths.RAG_INDEX):
        raise SystemExit("RAG index missing -- run jobs/teach.py --build-rag")
    index = rag.load(paths.RAG_INDEX)
    ref_blocks: list[str] = []
    seen_src: set[tuple[str, str]] = set()
    for sent, ans, src in sample:
        for c in rag.query(index, f"{src} {blank(sent, ans)}", k=2):
            key = (c["src"], c["title"])
            if key in seen_src:
                continue
            seen_src.add(key)
            ref_blocks.append(f"### {c['src']} :: {c['title']}\n{c['text'][:700]}")
    taught_ctx = "\n\n".join(ref_blocks)
    print(f"[rag] {len(ref_blocks)} reference chunks, {len(taught_ctx):,} chars")

    print(f"provider={prov}  pool={len(items)}  testing={len(sample)}\n")

    blanks = [blank(s, ans) for s, ans, _ in sample]

    t0 = time.time()
    base = ask(adapter, blanks, None)
    t1 = time.time()
    print(f"[gap] baseline done ({t1-t0:.1f}s); cooling down before the "
          f"second call -- rapid consecutive calls trip the rate window")
    time.sleep(45)
    taught = ask(adapter, blanks, taught_ctx)
    t2 = time.time()
    print(f"[timing] baseline {t1-t0:.1f}s   taught {t2-t1:.1f}s\n")

    rows = []
    for i, (sent, ans, src) in enumerate(sample, 1):
        b = score(base.get(str(i), base.get(i, "")), ans)
        d = score(taught.get(str(i), taught.get(i, "")), ans)
        rows.append((i, ans, b, d, src))

    print(f"{'#':>2}  {'answer':<22} base  taught  source")
    print("-" * 74)
    for i, ans, b, d, src in rows:
        print(f"{i:>2}  {ans[:22]:<22} {b:.1f}   {d:.1f}     {src[:34]}")

    mb = sum(r[2] for r in rows) / len(rows)
    md = sum(r[3] for r in rows) / len(rows)
    hb = sum(1 for r in rows if r[2] >= 0.5) / len(rows)
    hd = sum(1 for r in rows if r[3] >= 0.5) / len(rows)
    print("-" * 74)
    print(f"mean score   base={mb:.3f}  taught={md:.3f}  delta={md-mb:+.3f}")
    print(f"hit (>=0.5)  base={hb:.2%}  taught={hd:.2%}")

    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": prov, "n": len(rows), "seed": a.seed,
        "mean_base": round(mb, 4), "mean_taught": round(md, 4),
        "delta": round(md - mb, 4),
        "hit_base": round(hb, 4), "hit_taught": round(hd, 4),
        "items": [{"i": i, "answer": ans, "base": b, "taught": d, "src": src}
                  for i, ans, b, d, src in rows],
    }
    outp = os.path.join(paths.ROOT, "eval", "hard_result.json")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[eval] -> {outp}")

    if mb >= 0.5:
        print("[eval] BASELINE >= 0.5 -- facts are still too common. "
              "This set cannot prove teaching; tighten it.")
    elif md - mb >= 0.20:
        print("[eval] meaningful delta with a weak baseline -- course material "
              "is measurably supplying facts the model did not have.")
    else:
        print("[eval] delta < 0.20 -- weak. Do not claim the course was taught.")


if __name__ == "__main__":
    main()
