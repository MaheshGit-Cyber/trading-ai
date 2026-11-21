"""The "training" entrypoint -- which is really a teaching session.

    python3 jobs/teach.py --build-rag      # index the course corpus
    python3 jobs/teach.py --status         # what exists so far
    python3 jobs/teach.py --demo           # run one session, append to memory
    python3 jobs/teach.py --add '<json>'   # append your own event
    python3 jobs/teach.py --outcome '<json>'  # close an event with a result

Nothing here touches model weights. It grows memory/rules/RAG, which is
the part that persists across a model swap.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# trading-ai/ cannot be a package name (hyphen), so put it on sys.path and
# import the sub-packages (engine, adapters) as top-level modules.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import evidence, paths, rag  # noqa: E402


def cmd_build_rag() -> None:
    if not os.path.isdir(paths.COURSE_DIR):
        raise SystemExit(f"course dir not found: {paths.COURSE_DIR}")
    print(f"[rag] indexing {paths.COURSE_DIR} + {paths.KNOWLEDGE} ...")
    idx = rag.build(paths.COURSE_DIR, paths.RAG_INDEX, knowledge_dir=paths.KNOWLEDGE)
    size = os.path.getsize(paths.RAG_INDEX)
    print(f"[rag] {idx['n_chunks']} chunks, {len(idx['df'])} unique terms, "
          f"{size/1024/1024:.2f} MB -> {paths.RAG_INDEX}")


def cmd_status() -> None:
    print(f"config   : {'OK' if os.path.exists(paths.CONFIG) else 'MISSING'}  {paths.CONFIG}")
    print(f"rules    : {'OK' if os.path.exists(paths.RULES) else 'MISSING'}  {paths.RULES}")
    if os.path.exists(paths.RULES):
        with open(paths.RULES, encoding="utf-8") as f:
            r = json.load(f)
        print(f"           version={r.get('version')} min_rr={r.get('min_rr')} "
              f"auto_learn={r.get('learning',{}).get('auto_learn')}")
    print(f"memory   : {'OK' if os.path.exists(paths.MEMORY) else 'MISSING'}  {paths.MEMORY}")
    if os.path.exists(paths.MEMORY):
        n = sum(1 for line in open(paths.MEMORY, encoding="utf-8") if line.strip())
        print(f"           {n} line(s)")
    print(f"rag      : {'OK' if os.path.exists(paths.RAG_INDEX) else 'MISSING'}  {paths.RAG_INDEX}")


def cmd_demo(provider: str | None) -> None:
    """One teaching session with an explicitly-labelled DEMO input.

    The Layer-3 input below is synthetic. Real Layer-3 output does not
    exist yet -- Phase 0 (data ingest) and Phase 1 (walk-forward gate)
    have not run. This exercises the pipeline, it does not predict.
    """
    layer3 = {
        "demo": True,
        "symbol": "RELIANCE",
        "isin": "INE002A01018",
        "horizon": "5d",
        "direction": "up",
        "features": [
            "close_above_200dma", "rsi_14=58", "volume_1.8x_20d_avg",
            "range_breakout", "sector_relative_strength_positive",
        ],
        "regime": "trend",
        "entry": 1420.0, "stop": 1385.0, "target": 1495.0,
        "rr": 2.14,
        "note": "SYNTHETIC -- pipeline test only, not a signal",
    }

    print("[teach] running one evidence session ...")
    ev = evidence.run(layer3, provider=provider, verbose=True)

    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    record = {
        "ts": ts,
        "kind": "demo",
        "symbol": layer3["symbol"],
        "horizon": layer3["horizon"],
        "layer3": {k: layer3[k] for k in ("direction", "regime", "features", "rr")},
        "evidence": {k: v for k, v in ev.items() if not k.startswith("_")},
        "meta": {k: ev.get(k) for k in ("_attempts", "_latency_s", "_provider",
                                        "_fallback")},
        "outcome": None,
    }
    evidence.append_memory(record)

    print("\n--- validated evidence ---")
    print(json.dumps(record["evidence"], indent=2, ensure_ascii=False))
    print(f"\n[teach] appended to {paths.MEMORY}")
    print("[teach] NOTE: no outcome yet. Learning stays in quarantine until "
          "N >= 30 samples, per rules.json.")


def cmd_add(raw: str) -> None:
    obj = json.loads(raw)
    obj.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    evidence.append_memory(obj)
    print(f"[teach] appended (kind={obj.get('kind')}) to {paths.MEMORY}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Teaching session runner")
    ap.add_argument("--build-rag", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--add", metavar="JSON")
    ap.add_argument("--provider", default=None,
                    help="override active provider (opencode_cli | opencode_http | local_offline | paid_api)")
    a = ap.parse_args()

    if a.build_rag:
        cmd_build_rag()
    elif a.status:
        cmd_status()
    elif a.demo:
        cmd_demo(a.provider)
    elif a.add:
        cmd_add(a.add)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
