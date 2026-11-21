#!/usr/bin/env python3
"""Build daily cross-sectional relative-strength ranks for H4.

For each NSE EQ stock and each trading date:

    ret63  = close / close 63 sessions ago - 1
    ret126 = close / close 126 sessions ago - 1
    excess = stock return - Nifty 50 return over the same window

Then rank the excess returns across the eligible universe and write the average
percentile. Only rows with ``rs_pct >= --min-rs`` are written, which keeps the
file small enough for the backtest to load into memory.

No future data is used: every value on date D uses closes through D only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict, deque

EXCLUDE_TOKENS = (
    "ETF",
    "BEES",
    "EXCHANGE TRADED",
    "MUTUAL FUND",
    "REIT",
    "INVIT",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel.csv")
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--out", default="data/curated/rs_rank.csv")
    p.add_argument(
        "--min-rs",
        type=float,
        default=0.80,
        help="keep rows at or above this percentile (0.80 = top 20%%)",
    )
    p.add_argument("--price-min", type=float, default=20.0)
    p.add_argument("--turnover-min", type=float, default=100.0)
    return p.parse_args()


def load_nifty_returns(path: str) -> dict[str, tuple[float | None, float | None]]:
    rows: list[tuple[str, float]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["date"], float(r["close"])))
            except (KeyError, ValueError):
                continue
    rows.sort()
    out: dict[str, tuple[float | None, float | None]] = {}
    for i, (d, c) in enumerate(rows):
        r63 = c / rows[i - 63][1] - 1.0 if i >= 63 else None
        r126 = c / rows[i - 126][1] - 1.0 if i >= 126 else None
        out[d] = (r63, r126)
    return out


def percentile_ranks(values: list[float]) -> list[float]:
    """Average-rank percentile in [0, 1]; ties share the average rank."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / (n - 1)
        i = j + 1
    return ranks


def main() -> None:
    args = parse_args()
    nifty = load_nifty_returns(args.nifty)

    closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=127))
    turns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    writer = None
    out_f = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.writer(out_f)
    writer.writerow(["date", "stock_id", "ret63_excess", "ret126_excess", "rs_pct"])

    stats = {"dates": 0, "rows": 0, "kept": 0, "eligible": 0, "top10": 0}
    day_rows: list[tuple[str, str, float, float]] = []
    current_date: str | None = None

    def flush_day(date: str) -> None:
        if not day_rows:
            return
        r63 = [x[2] for x in day_rows]
        r126 = [x[3] for x in day_rows]
        p63 = percentile_ranks(r63)
        p126 = percentile_ranks(r126)
        kept = 0
        for i, (sid, sym, e63, e126) in enumerate(day_rows):
            rs = (p63[i] + p126[i]) / 2.0
            if rs >= 0.90:
                stats["top10"] += 1
            if rs >= args.min_rs:
                writer.writerow([date, sid, f"{e63:.8f}", f"{e126:.8f}", f"{rs:.6f}"])
                kept += 1
        stats["rows"] += len(day_rows)
        stats["eligible"] += len(day_rows)
        stats["kept"] += kept
        stats["dates"] += 1

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        need = ("date", "stock_id", "market", "symbol", "name", "series",
                "turnover_lacs", "close", "adj_close")
        for k in need:
            if k not in ix:
                raise SystemExit(f"missing column: {k}")
        for row in reader:
            d = row[ix["date"]]
            if d != current_date:
                if current_date is not None:
                    flush_day(current_date)
                current_date = d
                day_rows = []
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sym = row[ix["symbol"]].upper()
            name = row[ix["name"]].upper()
            if any(tok in sym or tok in name for tok in EXCLUDE_TOKENS):
                continue
            try:
                close = float(row[ix["adj_close"]])
                raw_close = float(row[ix["close"]])
                turn = float(row[ix["turnover_lacs"]] or 0.0)
            except (TypeError, ValueError):
                continue
            sid = row[ix["stock_id"]]
            closes[sid].append(close)
            turns[sid].append(turn)
            if len(closes[sid]) < 127 or len(turns[sid]) < 20:
                continue
            if raw_close < args.price_min:
                continue
            if sum(turns[sid]) / 20.0 < args.turnover_min:
                continue
            nr = nifty.get(d)
            if nr is None or nr[0] is None or nr[1] is None:
                continue
            r63 = closes[sid][-1] / closes[sid][-64] - 1.0
            r126 = closes[sid][-1] / closes[sid][-127] - 1.0
            day_rows.append((sid, sym, r63 - nr[0], r126 - nr[1]))

    if current_date is not None:
        flush_day(current_date)
    out_f.close()

    manifest = {
        "panel": args.panel,
        "nifty": args.nifty,
        "out": args.out,
        "min_rs_kept": args.min_rs,
        "dates": stats["dates"],
        "eligible_rows": stats["eligible"],
        "kept_rows": stats["kept"],
        "top10_rows": stats["top10"],
        "columns": ["date", "stock_id", "ret63_excess", "ret126_excess", "rs_pct"],
        "note": "ret63/ret126 use the stock's own sessions; excess is versus Nifty 50. Ranks are cross-sectional on each date.",
    }
    manifest_path = os.path.join(os.path.dirname(args.out) or ".", "rs_rank_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
