#!/usr/bin/env python3
"""Audit monthly-momentum entry execution realism.

Reads a backtest's selections.csv and checks, for every selected stock on its
execution date, the raw open versus the previous close. This catches gaps and
locked-circuit entries that a close-to-open backtest can otherwise fill for
free.

    python3 jobs/audit_monthly_entries.py \
        --selections data/backtest_monthly/selections.csv \
        --panel data/curated/panel.csv \
        --out data/backtest_monthly/entry_audit.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import Counter, defaultdict


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selections", required=True)
    p.add_argument("--panel", default="data/curated/panel.csv")
    p.add_argument("--out", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    wanted: set[tuple[str, str]] = set()
    with open(args.selections, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("execution_date") or "").strip()
            sid = (row.get("stock_id") or "").strip()
            if d and sid:
                wanted.add((d, sid))

    wanted_dates = {d for d, _ in wanted}
    wanted_by_date: dict[str, set[str]] = defaultdict(set)
    for d, sid in wanted:
        wanted_by_date[d].add(sid)

    found: dict[tuple[str, str], dict] = {}
    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d not in wanted_dates:
                continue
            sid = row[ix["stock_id"]]
            if sid not in wanted_by_date[d]:
                continue
            if row[ix["market"]] != "NSE" or row[ix["series"]] not in (
                "EQ",
                "BE",
                "BZ",
            ):
                continue
            key = (d, sid)
            try:
                found[key] = {
                    "open": float(row[ix["open"]]),
                    "high": float(row[ix["high"]]),
                    "low": float(row[ix["low"]]),
                    "close": float(row[ix["close"]]),
                    "prev_close": float(row[ix["prev_close"]]),
                    "turnover_lacs": float(row[ix["turnover_lacs"]] or 0.0),
                    "volume": float(row[ix["volume"]] or 0.0),
                }
            except (TypeError, ValueError):
                continue

    gaps = []
    missing = []
    locked = 0
    zero_volume = 0
    gap_buckets = Counter()
    for key in sorted(wanted):
        r = found.get(key)
        if r is None:
            missing.append({"date": key[0], "stock_id": key[1]})
            continue
        if r["prev_close"] <= 0 or r["open"] <= 0:
            missing.append({"date": key[0], "stock_id": key[1]})
            continue
        gap = r["open"] / r["prev_close"] - 1.0
        gaps.append(gap)
        if r["open"] == r["high"] == r["low"]:
            locked += 1
        if r["volume"] <= 0:
            zero_volume += 1
        if gap > 0.10:
            gap_buckets[">10%"] += 1
        elif gap > 0.05:
            gap_buckets[">5%"] += 1
        elif gap > 0.02:
            gap_buckets[">2%"] += 1
        elif gap < -0.05:
            gap_buckets["<-5%"] += 1
        else:
            gap_buckets["normal"] += 1

    def pct(xs, q):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))]

    out = {
        "selections": len(wanted),
        "matched": len(gaps),
        "missing_execution_row": len(missing),
        "missing_examples": missing[:20],
        "locked_open_high_low": locked,
        "zero_volume": zero_volume,
        "gap_mean": statistics.fmean(gaps) if gaps else None,
        "gap_median": statistics.median(gaps) if gaps else None,
        "gap_p10": pct(gaps, 0.10),
        "gap_p90": pct(gaps, 0.90),
        "gap_p99": pct(gaps, 0.99),
        "gap_max": max(gaps) if gaps else None,
        "gap_min": min(gaps) if gaps else None,
        "gap_buckets": dict(gap_buckets),
        "share_gap_gt_5pct": (
            (gap_buckets[">5%"] + gap_buckets[">10%"]) / len(gaps)
            if gaps
            else None
        ),
        "share_gap_gt_10pct": gap_buckets[">10%"] / len(gaps) if gaps else None,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
