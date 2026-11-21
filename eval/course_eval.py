"""Measure whether the course actually reaches the model.

Two conditions, same questions, same scoring:

  A  baseline  -- no course material at all (prior knowledge)
  B  taught    -- knowledge pack injected (retrieved/loaded knowledge)

Score = key-term recall: how much of the reference definition's content
vocabulary appears in the model's answer. Deterministic, no embeddings,
no LLM judge.

    python3 eval/course_eval.py [--n 18] [--provider opencode_cli]

HONESTY NOTE
------------
This measures *retrieval-assisted* knowledge, not knowledge baked into
weights. The free gateway model cannot be fine-tuned, so condition A can
never be made to equal condition B permanently -- that would require
weight access. If someone claims the model was "trained on the course"
without a fine-tune, this eval is the test that catches it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.base import get_adapter  # noqa: E402
from engine import paths, schema  # noqa: E402

STOP = set(
    """a an the and or but of in on at to for with from by as is are was were be
    this that it its we you they not no so than too very can will just about
    also used used for called name term means""".split()
)


def load_glossary() -> dict[str, str]:
    with open(os.path.join(paths.ROOT, "memory", "knowledge", "pack.json"),
              encoding="utf-8") as f:
        return json.load(f)["glossary"]


def content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower())
            if len(w) > 2 and w not in STOP}


def recall(model_answer: str, reference: str) -> float:
    r = content(reference)
    if not r:
        return 0.0
    a = content(model_answer)
    return len(a & r) / len(r)


SYSTEM = """You are answering a knowledge check from a trading course.
Answer from the material you are given. If you were given none, answer
from what you know.
Return exactly one JSON object mapping each requested term to a short
definition (one or two sentences). No markdown, no other keys."""


def ask(adapter, terms: list[str], pack: str | None) -> dict:
    user = "Define each of these terms:\n" + ", ".join(terms)
    if pack:
        user = ("## Course reference material\n" + pack +
                "\n\n## Task\n" + user)
    user += "\n\nReturn exactly one JSON object keyed by the terms above."

    last = ""
    for attempt in range(3):
        try:
            raw = adapter.complete(SYSTEM, user)
            obj = schema.extract_json(raw)
            if isinstance(obj, dict) and obj:
                return obj
            last = "empty object"
        except Exception as e:
            last = str(e)
            time.sleep(1)
    raise SystemExit(f"model call failed after 3 attempts: {last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=18, help="terms to test")
    ap.add_argument("--provider", default=None)
    a = ap.parse_args()

    glossary = load_glossary()
    # Deterministic stratified sample: stride through the sorted term list.
    terms = sorted(glossary)
    stride = max(1, len(terms) // a.n)
    sample = terms[::stride][:a.n]

    if not os.path.exists(paths.CONFIG):
        raise SystemExit(f"missing {paths.CONFIG}")
    with open(paths.CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    adapter = get_adapter(cfg, a.provider)
    prov = a.provider or cfg.get("active")

    with open(os.path.join(paths.ROOT, "memory", "knowledge", "pack.json"),
              encoding="utf-8") as f:
        pack_body = f.read()

    print(f"provider={prov}  terms={len(sample)}  glossary={len(glossary)}")
    print(f"terms: {', '.join(sample)}\n")

    t0 = time.time()
    base = ask(adapter, sample, pack=None)
    t1 = time.time()
    taught = ask(adapter, sample, pack=pack_body)
    t2 = time.time()
    print(f"[timing] baseline {t1-t0:.1f}s   taught {t2-t1:.1f}s\n")

    rows = []
    for t in sample:
        ref = glossary[t]
        b = recall(str(base.get(t, "")), ref)
        d = recall(str(taught.get(t, "")), ref)
        rows.append((t, b, d))

    w = max(len(r[0]) for r in rows)
    print(f"{'term'.ljust(w)}  base  taught   delta")
    print("-" * (w + 24))
    for t, b, d in rows:
        print(f"{t.ljust(w)}  {b:.2f}   {d:.2f}    {d-b:+.2f}")

    mb = sum(r[1] for r in rows) / len(rows)
    md = sum(r[2] for r in rows) / len(rows)
    hb = sum(1 for r in rows if r[1] >= 0.5) / len(rows)
    hd = sum(1 for r in rows if r[2] >= 0.5) / len(rows)
    wins = sum(1 for r in rows if r[2] > r[1])
    losses = sum(1 for r in rows if r[2] < r[1])

    print("-" * (w + 24))
    print(f"mean recall     base={mb:.3f}  taught={md:.3f}  delta={md-mb:+.3f}")
    print(f"hit rate (>=.5) base={hb:.2%}  taught={hd:.2%}")
    print(f"per-term        improved={wins}  worse={losses}  "
          f"same={len(rows)-wins-losses}")

    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": prov,
        "n_terms": len(rows),
        "mean_recall_base": round(mb, 4),
        "mean_recall_taught": round(md, 4),
        "delta": round(md - mb, 4),
        "hit_base": round(hb, 4),
        "hit_taught": round(hd, 4),
        "per_term": [
            {"term": t, "base": round(b, 4), "taught": round(d, 4)}
            for t, b, d in rows
        ],
    }
    outp = os.path.join(paths.ROOT, "eval", "last_result.json")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[eval] -> {outp}")

    if md - mb < 0.05:
        print("[eval] delta < 0.05 -- the pack is NOT reaching the model. "
              "Do not claim the course was taught.")
    else:
        print("[eval] delta >= 0.05 -- course material measurably reaches "
              "the model. This is retrieval-assisted, not baked into weights.")


if __name__ == "__main__":
    main()
