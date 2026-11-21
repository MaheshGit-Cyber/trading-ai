"""Retrieval eval -- no model calls, no quota, fully deterministic.

Question this answers: when the evidence layer asks about a course fact,
does BM25 actually surface the chunk that contains it?

If retrieval misses, no prompt engineering can fix it -- the model would
be asked to answer from material it never received. So this is the FIRST
gate, before any LLM eval.

    python3 eval/retrieval_eval.py [--n 80]

Metrics:
  hit@k     -- source file appears in the top-k retrieved chunks
  answer@k  -- the literal answer string appears in the retrieved text
  rank      -- mean reciprocal rank of the first correct chunk
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import paths, rag  # noqa: E402
from eval.fact_eval import collect, norm  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80, help="0 = all")
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()

    if not os.path.exists(paths.RAG_INDEX):
        raise SystemExit(f"missing {paths.RAG_INDEX} -- run jobs/teach.py --build-rag")
    index = rag.load(paths.RAG_INDEX)

    pool = collect()
    items = pool[:a.n] if a.n else pool
    print(f"index={index['n_chunks']} chunks  facts={len(items)}  k={a.k}\n")

    hit = {k: 0 for k in range(1, a.k + 1)}
    ans = {k: 0 for k in range(1, a.k + 1)}
    rr = 0.0
    misses: list[dict] = []

    for it in items:
        # Query as a human would: section context + the field being asked for.
        q = f"{it['section']} {it['label']} {it['src'].replace('/', ' ').replace('.md', '')}"
        chunks = rag.query(index, q, k=a.k)

        first = None
        for rank, c in enumerate(chunks, 1):
            if c["src"] == it["src"]:
                if first is None:
                    first = rank
                # Literal answer inside the retrieved text?
                if norm(it["answer"]) and norm(it["answer"]) in norm(c["text"]):
                    for k in range(rank, a.k + 1):
                        ans[k] += 1
                    break
        if first is not None:
            rr += 1.0 / first
            for k in range(first, a.k + 1):
                hit[k] += 1
        else:
            misses.append(it)

    n = len(items)
    print("source file retrieved in top-k:")
    for k in range(1, a.k + 1):
        print(f"  hit@{k}    {hit[k]:4d}/{n}  {hit[k]/n:6.1%}")
    print("literal answer present in top-k:")
    for k in range(1, a.k + 1):
        print(f"  answer@{k} {ans[k]:4d}/{n}  {ans[k]/n:6.1%}")
    print(f"\nMRR (source file) = {rr/n:.3f}")

    if misses:
        print(f"\nmissed at k={a.k}: {len(misses)}")
        for it in misses[:10]:
            print(f"  - {it['section'][:40]} :: {it['label']} "
                  f"({it['src']})")

    # Gate
    print()
    if hit[a.k] / n >= 0.80 and ans[a.k] / n >= 0.60:
        print("[retrieval] PASS -- the corpus is reachable at k=%d." % a.k)
    else:
        print("[retrieval] FAIL -- tighten chunking or query construction "
              "before running any LLM eval.")


if __name__ == "__main__":
    main()
