#!/usr/bin/env python3
"""Summarise a panel and compare its NSE dates with the Nifty calendar.

    python3 jobs/check_panel_coverage.py \
        --panel data/curated/panel_nse_isin.csv \
        --nifty data/index/nifty50.csv \
        --out data/curated/panel_nse_isin_coverage.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", required=True)
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    nifty_dates = set()
    with open(args.nifty, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("close") or "").strip():
                nifty_dates.add(row["date"])

    dates = set()
    nse_dates = set()
    sids = set()
    years = Counter()
    markets = Counter()
    series = Counter()
    ca = Counter()
    flags = Counter()
    isin_source = Counter()
    rows = 0
    nse_rows = 0
    with open(args.panel, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows += 1
            dates.add(row["date"])
            markets[row["market"]] += 1
            series[row["series"]] += 1
            years[row["date"][:4]] += 1
            if row["market"] == "NSE" and row["series"] in {"EQ", "BE", "BZ"}:
                nse_rows += 1
                nse_dates.add(row["date"])
                sids.add(row["stock_id"])
            if row.get("ca_action"):
                ca[row["ca_action"]] += 1
            isin_source[row.get("isin_source") or "none"] += 1
            for flag in (row.get("flags") or "").split(";"):
                if flag:
                    flags[flag] += 1

    missing = sorted(nifty_dates - nse_dates)
    extra = sorted(nse_dates - nifty_dates)
    start = min(dates) if dates else None
    end = max(dates) if dates else None
    within = sorted(d for d in nifty_dates if start and end and start <= d <= end)
    missing_within = sorted(set(within) - nse_dates)

    out = {
        "panel": args.panel,
        "rows": rows,
        "nse_eq_rows": nse_rows,
        "dates": len(dates),
        "nse_dates": len(nse_dates),
        "unique_nse_eq_stocks": len(sids),
        "range": [start, end],
        "markets": dict(markets),
        "series_top": dict(series.most_common(20)),
        "by_year": dict(sorted(years.items())),
        "isin_source": dict(isin_source.most_common(20)),
        "corporate_actions": dict(ca.most_common(20)),
        "flags": dict(flags.most_common(40)),
        "nifty_dates_in_range": len(within),
        "nifty_dates_missing_from_panel": len(missing_within),
        "missing_examples": missing_within[:50],
        "nse_dates_not_in_nifty": len(extra),
        "extra_examples": extra[:20],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k not in ("missing_examples", "extra_examples")}, indent=2))
    if missing_within:
        print("first missing:", missing_within[:10])


if __name__ == "__main__":
    main()
