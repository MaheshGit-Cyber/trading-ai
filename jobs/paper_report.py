#!/usr/bin/env python3
"""Evaluate the append-only paper ledger under the frozen paper-book rule."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.paper import DEFAULT_PAPER_DIR, load_snapshots  # noqa: E402
from brain.paper_book import evaluate_snapshots  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=DEFAULT_PAPER_DIR)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    snaps = load_snapshots(args.root)
    report = evaluate_snapshots(snaps)
    out = report.to_dict()
    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"paper sessions: {len(out['days'])}")
    print(f"initial: ₹{out['initial_capital']:,.2f}")
    print(f"final:   ₹{out['final_value']:,.2f}")
    print(f"return:  {out['total_return'] * 100:+.3f}%")
    print(f"max DD:  {out['max_drawdown'] * 100:+.3f}%")
    print(f"Nifty:   {out['nifty_return'] * 100:+.3f}%")
    print(f"costs:   ₹{out['total_costs']:,.2f}; rebalances: {out['rebalances']}")
    for day in out["days"]:
        print(
            f"  {day['as_of']}  value ₹{day['value']:,.2f}  "
            f"day {day['daily_return'] * 100:+.3f}%  "
            f"DD {day['drawdown'] * 100:+.3f}%  "
            f"{'rebalance' if day['rebalanced'] else ''}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
