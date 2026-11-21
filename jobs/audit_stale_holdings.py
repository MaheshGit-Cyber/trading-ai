#!/usr/bin/env python3
"""Audit stale/suspended holdings in a monthly-momentum backtest.

Reads holdings.csv and scans the panel once to find each stock's last trading
date. A holding that is not in the current target and has no future panel row
is treated as delisted; one that still has future rows is a temporary
suspension.

    python3 jobs/audit_stale_holdings.py \
        --holdings data/backtest_monthly_2010_2026/holdings.csv \
        --panel data/curated/panel_nse_isin.csv \
        --out data/backtest_monthly_2010_2026/stale_audit.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--holdings", required=True)
    p.add_argument("--panel", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    holdings = []
    wanted = set()
    with open(args.holdings, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("in_target", "").lower() in ("true", "1"):
                continue
            try:
                value = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if value <= 0:
                continue
            item = {
                "signal_date": row["signal_date"],
                "execution_date": row["execution_date"],
                "stock_id": row["stock_id"],
                "qty": int(float(row["qty"])),
                "price": float(row["price"]),
                "value": value,
            }
            holdings.append(item)
            wanted.add(item["stock_id"])

    first_date = {}
    last_date = {}
    row_count = Counter()
    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            sid = row[ix["stock_id"]]
            if sid not in wanted:
                continue
            d = row[ix["date"]]
            first_date.setdefault(sid, d)
            last_date[sid] = d
            row_count[sid] += 1

    delisted = []
    temporary = []
    for h in holdings:
        last = last_date.get(h["stock_id"], "")
        if last <= h["execution_date"]:
            h["last_panel_date"] = last
            h["kind"] = "delisted_or_no_future_price"
            delisted.append(h)
        else:
            h["last_panel_date"] = last
            h["kind"] = "temporary_gap"
            temporary.append(h)

    by_kind = {
        "stale_snapshots": len(holdings),
        "stale_value_total": sum(h["value"] for h in holdings),
        "delisted_snapshots": len(delisted),
        "delisted_value_total": sum(h["value"] for h in delisted),
        "temporary_snapshots": len(temporary),
        "temporary_value_total": sum(h["value"] for h in temporary),
        "unique_stale_stocks": len(wanted),
        "unique_delisted_stocks": len({h["stock_id"] for h in delisted}),
        "unique_temporary_stocks": len({h["stock_id"] for h in temporary}),
    }
    # Per-rebalance stale share by kind.
    per_exec: dict[str, dict] = defaultdict(
        lambda: {"stale": 0.0, "delisted": 0.0, "temporary": 0.0}
    )
    for h in holdings:
        bucket = (
            "delisted"
            if h["kind"] == "delisted_or_no_future_price"
            else "temporary"
        )
        per_exec[h["execution_date"]]["stale"] += h["value"]
        per_exec[h["execution_date"]][bucket] += h["value"]
    by_kind["per_rebalance"] = dict(sorted(per_exec.items()))

    examples = []
    for h in sorted(delisted, key=lambda x: -x["value"])[:30]:
        examples.append(
            {
                "execution_date": h["execution_date"],
                "stock_id": h["stock_id"],
                "value": h["value"],
                "last_panel_date": h["last_panel_date"],
                "rows": row_count[h["stock_id"]],
                "first_panel_date": first_date[h["stock_id"]],
            }
        )
    by_kind["delisted_examples"] = examples

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(by_kind, f, indent=2)
    print(json.dumps({k: v for k, v in by_kind.items() if k != "per_rebalance"}, indent=2))


if __name__ == "__main__":
    main()
