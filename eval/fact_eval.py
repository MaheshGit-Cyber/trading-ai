"""Course-unique fact eval -- the test that can actually prove teaching.

Why this exists:
  course_eval.py  (glossary)   -> baseline 0.876, ceiling problem, proves nothing
  hard_eval.py    (cloze)      -> pool too small, regex too strict
  THIS            (table facts)-> baseline should be LOW, because these are
                                  facts that live only in analysis/course

Each item is a real table row from the corpus:

    section : "2.3 August 2024 yen carry unwind"
    label   : "Date"
    value   : "5 August 2024"        <- ground truth

Question:  According to the course section "X", what is "Y"?
Scoring:   exact / numeric / containment (deterministic, no LLM judge)

    python3 eval/fact_eval.py [--n 16] [--provider opencode_cli]
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

ROW = re.compile(r"^\|\s*\*{0,2}([^|*]+?)\*{0,2}\s*\|\s*([^|]+?)\s*\|\s*$")
HEAD = re.compile(r"^(#{2,3})\s+(.*)$")
VALUE_HAS = re.compile(
    r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\b\d{4}\b|\d+(?:\.\d+)?\s*%|"
    r"₹\s?[\d,]+|\bT\+\d\b|\d+\s*:\s*\d+"
)
_LABEL_OK = re.compile(r"^[A-Za-z][A-Za-z\s/&()'’.-]{1,58}$")
_SKIP_LABELS = {"item", "detail", "year", "event", "era", "theme", "lesson",
                "response", "action", "takeaway", "note", "notes", "source"}
_SKIP_SECTIONS = {"quick index", "how to read this file"}


def clean(s: str) -> str:
    s = re.sub(r"\*{1,2}", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)   # markdown links
    s = re.sub(r"\s+", " ", s).strip(" |")
    return s


def collect() -> list[dict]:
    items: list[dict] = []
    for root, _d, files in sorted(os.walk(paths.COURSE_DIR)):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), paths.COURSE_DIR)
            section = ""
            for line in open(os.path.join(root, fn), encoding="utf-8",
                             errors="replace"):
                line = line.rstrip("\n")
                m = HEAD.match(line)
                if m:
                    section = clean(m.group(2))
                    continue
                m = ROW.match(line)
                if not m:
                    continue
                label, value = clean(m.group(1)), clean(m.group(2))
                if not _LABEL_OK.match(label):
                    continue
                if label.lower() in _SKIP_LABELS:
                    continue
                if not section or section.lower() in _SKIP_SECTIONS:
                    continue
                if not VALUE_HAS.search(value):
                    continue
                if not (3 <= len(value) <= 100):
                    continue
                if len(section) > 70:
                    continue
                items.append({"section": section, "label": label,
                              "answer": value, "src": rel})
    # De-duplicate on (section, label)
    seen, out = set(), []
    for it in items:
        k = (it["section"].lower(), it["label"].lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def norm(s: str) -> str:
    s = str(s).strip().lower().strip(".,;:!?'\"")
    s = re.sub(r"[\u20b9,]", "", s)
    s = re.sub(r"\*{1,2}", "", s)
    return re.sub(r"\s+", " ", s)


def score(given: str, answer: str) -> float:
    g, a = norm(given), norm(answer)
    if not g:
        return 0.0
    if g == a:
        return 1.0
    gd, ad = re.sub(r"[^0-9]", "", g), re.sub(r"[^0-9]", "", a)
    if gd and gd == ad:
        return 0.5
    if len(a) >= 4 and (a in g or g in a):
        return 0.5
    return 0.0


SYSTEM = """You are answering questions drawn from a trading course.
Answer ONLY from the reference material provided. If it is not there,
return an empty string for that key.
Return exactly one JSON object keyed by the question number as a string
(e.g. {"1": "..."}) with the value only -- no explanation, no markdown."""


def ask(adapter, questions: list[str], pack: str | None, retry_wait: int = 40) -> dict:
    lines = [f"{i+1}. {q}" for i, q in enumerate(questions)]
    user = "\n".join(lines)
    if pack:
        user = ("## Course reference material\n" + pack + "\n\n## Questions\n" + user)
    user += '\n\nReturn exactly one JSON object keyed by index, e.g. {"1": "..."}'
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
            # The free gateway enforces a short rolling window and reports it
            # as FreeUsageLimitError. Back off instead of hammering it --
            # hammering only extends the block.
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

    pool = collect()
    if len(pool) < a.n:
        raise SystemExit(f"pool too small: {len(pool)}")
    random.Random(a.seed).shuffle(pool)
    sample = pool[:a.n]

    with open(paths.CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    adapter = get_adapter(cfg, a.provider)
    prov = a.provider or cfg.get("active")

    # The taught condition must use RAG, not the knowledge pack: the pack holds
    # glossary/outline/thresholds, while these questions are about table facts
    # (dates, peaks, triggers) that only exist in the corpus chunks.
    index = rag.load(paths.RAG_INDEX)
    ref_blocks: list[str] = []
    seen_src: set[tuple[str, str]] = set()
    for it in sample:
        q = f"{it['section']} {it['label']}"
        for c in rag.query(index, q, k=2):
            key = (c["src"], c["title"])
            if key in seen_src:
                continue
            seen_src.add(key)
            ref_blocks.append(f"### {c['src']} :: {c['title']}\n{c['text'][:700]}")
    taught_ctx = "\n\n".join(ref_blocks)
    print(f"[rag] {len(ref_blocks)} reference chunks, {len(taught_ctx):,} chars")

    print(f"provider={prov}  pool={len(pool)}  testing={len(sample)}\n")

    qs = [f'In the course section "{it["section"]}", what is "{it["label"]}"?'
          for it in sample]

    t0 = time.time(); base = ask(adapter, qs, None);            t1 = time.time()
    print(f"[gap] baseline done ({t1-t0:.1f}s); cooling down before "
          f"second call -- rapid consecutive calls trip the rate window")
    time.sleep(45)
    taught = ask(adapter, qs, taught_ctx);                      t2 = time.time()
    print(f"[timing] baseline {t1-t0:.1f}s   taught {t2-t1:.1f}s\n")

    rows = []
    for i, (q, it) in enumerate(zip(qs, sample), 1):
        b = score(base.get(str(i), base.get(i, "")), it["answer"])
        d = score(taught.get(str(i), taught.get(i, "")), it["answer"])
        rows.append((i, it, b, d))

    print(f"{'#':>2}  {'section':<30} {'label':<14} {'answer':<26} base  taught")
    print("-" * 96)
    for i, it, b, d in rows:
        print(f"{i:>2}  {it['section'][:30]:<30} {it['label'][:14]:<14} "
              f"{it['answer'][:26]:<26} {b:.1f}   {d:.1f}")

    mb = sum(r[2] for r in rows) / len(rows)
    md = sum(r[3] for r in rows) / len(rows)
    hb = sum(1 for r in rows if r[2] >= 0.5) / len(rows)
    hd = sum(1 for r in rows if r[3] >= 0.5) / len(rows)
    print("-" * 96)
    print(f"mean score   base={mb:.3f}  taught={md:.3f}  delta={md-mb:+.3f}")
    print(f"hit (>=0.5)  base={hb:.2%}  taught={hd:.2%}")

    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "provider": prov,
           "n": len(rows), "seed": a.seed,
           "mean_base": round(mb, 4), "mean_taught": round(md, 4),
           "delta": round(md - mb, 4), "hit_base": round(hb, 4),
           "hit_taught": round(hd, 4),
           "items": [{"i": r[0], **{k: r[1][k] for k in
                                    ("section", "label", "answer", "src")},
                      "base": r[2], "taught": r[3]} for r in rows]}
    outp = os.path.join(paths.ROOT, "eval", "fact_result.json")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[eval] -> {outp}")

    if mb >= 0.5:
        print("[eval] BASELINE >= 0.5 -- facts too common, cannot prove teaching.")
    elif md - mb >= 0.20:
        print("[eval] LOW baseline + meaningful delta -> the course is supplying "
              "facts the model did not have. Retrieval-assisted, not weights.")
    else:
        print("[eval] delta < 0.20 -- weak. Do not claim the course was taught.")


if __name__ == "__main__":
    main()
