#!/usr/bin/env python3
"""Record one internal paper-trading signal snapshot.

    python3 jobs/paper_snapshot.py --capital 1000000 --risk-score 7

No order is placed. The snapshot is written only for a date that exists in the
Nifty data. Run it after the daily data refresh; do not backfill fake dates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import DEFAULT_NIFTY, load_nifty_rows  # noqa: E402
from brain.paper import (  # noqa: E402
    DEFAULT_GOLD,
    DEFAULT_PAPER_DIR,
    build_snapshot,
    record_snapshot,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="signal date; defaults to latest Nifty bar")
    p.add_argument("--capital", type=float, default=1_000_000)
    p.add_argument("--risk-score", type=int, default=7)
    p.add_argument("--engine", default="all_weather_defender")
    p.add_argument("--nifty", default=DEFAULT_NIFTY)
    p.add_argument("--gold", default=DEFAULT_GOLD)
    p.add_argument("--root", default=DEFAULT_PAPER_DIR)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    all_rows = load_nifty_rows(args.nifty, max_bars=10_000)
    latest = all_rows[-1].date
    if args.as_of and args.as_of > latest:
        p.error(f"--as-of {args.as_of} is after latest data {latest}")
    cutoff = args.as_of or latest
    rows = load_nifty_rows(args.nifty, as_of=cutoff, max_bars=320)
    snapshot = build_snapshot(
        rows,
        capital=args.capital,
        risk_score=args.risk_score,
        engine=args.engine,
        gold_path=args.gold,
        as_of=cutoff,
    )
    out = {"snapshot": snapshot.to_dict()}
    if not args.dry_run:
        path, ledger = record_snapshot(snapshot, root=args.root)
        out["written"] = {"snapshot": path, "ledger": ledger}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
