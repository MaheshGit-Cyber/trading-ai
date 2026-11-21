#!/usr/bin/env python3
"""Phase 3: liquid large-cap mean reversion, frozen pre-registration.

Universe: NSE EQ, raw close >= Rs 50, 20D turnover >= Rs 5 crore, top 200 by
20D turnover. Signal: price > SMA200, SMA50 > SMA200, ret126 > 0, then the
bottom 10 by ret21 (most oversold). Month-end signal, next-session open.

    python3 jobs/backtest_largecap_meanrev.py \
        --panel data/curated/panel_nse_isin_v2.csv \
        --nifty data/index/nifty50.csv \
        --start 2010-10-01 --end 2026-11-19 \
        --outdir data/backtest_meanrev_2010_2026
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict, deque
from datetime import date as ddate

from backtest_monthly_momentum import (
    EXCLUDE_TOKENS,
    build_month_pairs,
    load_nifty,
    load_selected_prices,
    max_drawdown,
    run_portfolio,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel_nse_isin_v2.csv")
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--start", default="2010-10-01")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--universe-size", type=int, default=200)
    p.add_argument("--min-price", type=float, default=50.0)
    p.add_argument(
        "--min-turnover",
        type=float,
        default=500.0,
        help="20D average turnover in lacs; 500 = Rs 5 crore",
    )
    p.add_argument("--max-adv-pct", type=float, default=0.05)
    p.add_argument("--target-weight", type=float, default=0.10)
    p.add_argument("--slippage-mult", type=float, default=1.0)
    p.add_argument(
        "--selection-mode",
        choices=("primary", "random"),
        default="primary",
        help="primary = most oversold; random = random eligible top-N",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--writeoff-days", type=int, default=90)
    p.add_argument("--master", default="data/nse_equity_master.csv")
    p.add_argument("--writeoff-unlisted-only", action="store_true")
    p.add_argument(
        "--benchmark-cost",
        type=float,
        default=0.003,
        help="one-way cost applied per unit of equal-weight universe turnover",
    )
    p.add_argument("--outdir", required=True)
    return p.parse_args()


def build_selections(args: argparse.Namespace, pairs: list[tuple[str, str]]):
    signal_set = {s for s, _ in pairs}
    exec_by_signal = {s: e for s, e in pairs}
    closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
    turns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))
    raw: dict[str, float] = {}
    last_seen: dict[str, str] = {}
    meta: dict[str, tuple[str, str]] = {}
    selections: dict[str, list[dict]] = {}
    universe: dict[str, list[tuple[str, float]]] = {}
    eligible_counts: dict[str, int] = {}
    rng = random.Random(args.seed)
    current_date: str | None = None

    def flush(d: str) -> None:
        if d not in signal_set:
            return
        rows = []
        for sid, cs in closes.items():
            if len(cs) < 200:
                continue
            if last_seen.get(sid) != d:
                continue
            if raw.get(sid, 0.0) < args.min_price:
                continue
            ts = turns[sid]
            if len(ts) < 20:
                continue
            t20 = sum(ts) / 20.0
            if t20 < args.min_turnover:
                continue
            sym, name = meta.get(sid, ("", ""))
            if any(tok in sym.upper() or tok in name.upper() for tok in EXCLUDE_TOKENS):
                continue
            values = list(cs)
            sma200 = sum(values) / 200.0
            sma50 = sum(values[-50:]) / 50.0
            price = values[-1]
            ret21 = price / values[-22] - 1.0
            ret126 = price / values[-127] - 1.0
            rows.append(
                {
                    "stock_id": sid,
                    "turnover20": t20,
                    "signal_close": price,
                    "sma50": sma50,
                    "sma200": sma200,
                    "ret21": ret21,
                    "ret126": ret126,
                }
            )

        # Approved universe: top 200 by 20D turnover, then the trend filter.
        rows.sort(key=lambda r: (-r["turnover20"], r["stock_id"]))
        top = rows[: args.universe_size]
        universe[d] = [(r["stock_id"], r["signal_close"]) for r in top]
        candidates = [
            r
            for r in top
            if r["signal_close"] > r["sma200"]
            and r["sma50"] > r["sma200"]
            and r["ret126"] > 0.0
        ]
        eligible_counts[d] = len(candidates)
        if len(candidates) < args.top_n:
            selections[d] = []
            return
        candidates.sort(key=lambda r: (r["ret21"], r["stock_id"]))
        if args.selection_mode == "random":
            chosen = rng.sample(candidates, args.top_n)
            chosen.sort(key=lambda r: r["stock_id"])
        else:
            chosen = candidates[: args.top_n]
        for i, row in enumerate(chosen, 1):
            row["rank"] = i
            row["signal_date"] = d
            row["execution_date"] = exec_by_signal[d]
        selections[d] = chosen

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d > args.end:
                break
            if d != current_date:
                if current_date is not None:
                    flush(current_date)
                current_date = d
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sid = row[ix["stock_id"]]
            try:
                c = float(row[ix["adj_close"]])
                raw_c = float(row[ix["close"]])
                turn = float(row[ix["turnover_lacs"]] or 0.0)
            except (TypeError, ValueError):
                continue
            closes[sid].append(c)
            turns[sid].append(turn)
            raw[sid] = raw_c
            last_seen[sid] = d
            meta[sid] = (row[ix["symbol"]], row[ix["name"]])
    if current_date is not None:
        flush(current_date)
    return selections, universe, eligible_counts


def equal_weight_benchmark_net(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
    universe: dict[str, list[tuple[str, float]]],
) -> dict:
    """Top-200 equal-weight universe, net of a simple turnover cost."""
    monthly = []
    prev_map: dict[str, float] | None = None
    equity = args.capital
    for signal, _exec in pairs:
        cur = dict(universe.get(signal, []))
        if prev_map:
            rets = [
                cur[sid] / px - 1.0
                for sid, px in prev_map.items()
                if sid in cur and px > 0
            ]
            if rets:
                gross = statistics.fmean(rets)
                prev_ids = set(prev_map)
                cur_ids = set(cur)
                turnover = (
                    1.0 - len(prev_ids & cur_ids) / max(len(prev_ids), 1)
                )
                cost = args.benchmark_cost * turnover
                net = gross - cost
                equity *= 1.0 + net
                monthly.append(
                    {
                        "month": signal[:7],
                        "return": net,
                        "gross_return": gross,
                        "equity": equity,
                        "turnover": turnover,
                    }
                )
        prev_map = cur
    if not monthly:
        return {
            "cagr": None,
            "total_return": None,
            "max_drawdown": None,
            "monthly": [],
        }
    first = monthly[0]["equity"] / (1.0 + monthly[0]["return"])
    last = monthly[-1]["equity"]
    years = len(monthly) / 12.0
    cagr = (last / first) ** (1.0 / years) - 1.0
    curve = [
        {"date": r["month"] + "-01", "equity": r["equity"]} for r in monthly
    ]
    dd, _, _ = max_drawdown(curve)
    rets = [r["return"] for r in monthly]
    sd = statistics.pstdev(rets)
    return {
        "cagr": cagr,
        "total_return": last / first - 1.0,
        "max_drawdown": dd,
        "months": len(monthly),
        "sharpe": (
            statistics.fmean(rets) / sd * math.sqrt(12.0) if sd else None
        ),
        "monthly": monthly,
        "benchmark_cost_per_turnover": args.benchmark_cost,
    }


def excess_stats(
    strategy_monthly: list[dict], benchmark_monthly: list[dict]
) -> dict:
    sm = {r["month"]: r["return"] for r in strategy_monthly}
    bm = {r["month"]: r["return"] for r in benchmark_monthly}
    months = sorted(set(sm) & set(bm))
    excess = [sm[m] - bm[m] for m in months]
    if len(excess) < 2:
        return {"months": len(excess)}
    mu = statistics.fmean(excess)
    sd = statistics.pstdev(excess)
    t = mu / (sd / math.sqrt(len(excess))) if sd else None
    hit = sum(1 for x in excess if x > 0) / len(excess)
    return {
        "months": len(excess),
        "mean_monthly": mu,
        "t_stat": t,
        "hit_rate": hit,
        "monthly": [{"month": m, "excess": sm[m] - bm[m]} for m in months],
    }


def write_outputs(
    args: argparse.Namespace,
    result: dict,
    selections: dict[str, list[dict]],
    eligible_counts: dict[str, int],
) -> None:
    os.makedirs(args.outdir, exist_ok=True)
    summary = {
        "setup": "liquid_largecap_mean_reversion",
        "phase": "3_frozen",
        "panel": args.panel,
        "nifty": args.nifty,
        "selection_mode": args.selection_mode,
        "seed": args.seed,
        "capital": args.capital,
        "top_n": args.top_n,
        "universe_size": args.universe_size,
        "min_price": args.min_price,
        "min_turnover_lacs": args.min_turnover,
        "target_weight": args.target_weight,
        "slippage_mult": args.slippage_mult,
        "benchmark_cost": args.benchmark_cost,
        "universe": "NSE EQ; raw close >= 50; 20D turnover >= 500 lacs; "
        "top 200 by 20D turnover; ETF/REIT/InvIT excluded",
        "signal_rule": "price>SMA200, SMA50>SMA200, ret126>0; bottom 10 ret21",
        "execution_rule": "month-end close signal; next-session open",
        "monthly_signals": len(selections),
        "eligible_counts": {
            "min": min(eligible_counts.values()) if eligible_counts else 0,
            "median": (
                statistics.median(eligible_counts.values())
                if eligible_counts
                else 0
            ),
            "max": max(eligible_counts.values()) if eligible_counts else 0,
        },
        "portfolio": result["summary"],
    }
    with open(
        os.path.join(args.outdir, "summary_largecap_meanrev.json"), "w"
    ) as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(args.outdir, "equity_curve.csv"), "w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "cash", "mtm", "equity", "holdings", "exposure"]
        )
        w.writeheader()
        w.writerows(result["curve"])
    with open(os.path.join(args.outdir, "monthly_returns.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "equity", "return"])
        w.writeheader()
        w.writerows(result["monthly"])
    ew_monthly = result["summary"].get("equal_weight_universe", {}).get(
        "monthly", []
    )
    if ew_monthly:
        with open(
            os.path.join(args.outdir, "equal_weight_monthly.csv"), "w", newline=""
        ) as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "month",
                    "return",
                    "gross_return",
                    "equity",
                    "turnover",
                ],
            )
            w.writeheader()
            w.writerows(ew_monthly)
    excess = result["summary"].get("excess_vs_equal_weight", {}).get("monthly", [])
    if excess:
        with open(
            os.path.join(args.outdir, "monthly_excess.csv"), "w", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=["month", "excess"])
            w.writeheader()
            w.writerows(excess)
    with open(
        os.path.join(args.outdir, "rebalance_trades.csv"), "w", newline=""
    ) as f:
        fields = ["date", "stock_id", "side", "qty", "price", "value", "cost", "reason"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in result["trades"]:
            w.writerow({k: t.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "selections.csv"), "w", newline="") as f:
        fields = [
            "signal_date",
            "execution_date",
            "rank",
            "stock_id",
            "ret21",
            "ret126",
            "turnover20",
            "signal_close",
            "sma50",
            "sma200",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in sorted(selections):
            for row in selections[d]:
                w.writerow({k: row.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "rebalances.csv"), "w", newline="") as f:
        fields = [
            "signal_date",
            "execution_date",
            "equity_open",
            "cash_after",
            "holdings",
            "stale_count",
            "stale_value",
            "stale_pct",
            "target",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in result["rebalances"]:
            w.writerow({k: r.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "holdings.csv"), "w", newline="") as f:
        fields = [
            "signal_date",
            "execution_date",
            "stock_id",
            "qty",
            "price",
            "value",
            "in_target",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in result["holdings"]:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> None:
    args = parse_args()
    nifty_dates, nifty_closes, _ = load_nifty(args.nifty)
    pairs = build_month_pairs(nifty_dates, args.start, args.end)
    if not pairs:
        raise SystemExit("no monthly pairs in range")

    selections, universe, eligible_counts = build_selections(args, pairs)
    # Drop months before the 200-session history is available, so the equity
    # curve starts at the first investable signal rather than after idle cash.
    pairs = [(s, e) for s, e in pairs if s in selections]
    if not pairs:
        raise SystemExit("no investable signals")

    selected_ids = {
        row["stock_id"] for rows in selections.values() for row in rows
    }
    opens, closes, factors = load_selected_prices(
        args, selected_ids, pairs[0][1]
    )
    result = run_portfolio(
        args,
        pairs,
        selections,
        opens,
        closes,
        factors,
        nifty_dates,
        nifty_closes,
    )
    ew = equal_weight_benchmark_net(args, pairs, universe)
    result["summary"]["equal_weight_universe"] = ew
    result["summary"]["excess_vs_equal_weight"] = excess_stats(
        result["monthly"], ew.get("monthly", [])
    )
    write_outputs(args, result, selections, eligible_counts)

    p = result["summary"]
    print(
        json.dumps(
            {
                "cagr": p.get("cagr"),
                "max_drawdown": p.get("max_drawdown"),
                "max_drawdown_peak": p.get("max_drawdown_peak"),
                "max_drawdown_trough": p.get("max_drawdown_trough"),
                "sharpe": p.get("sharpe"),
                "sortino": p.get("sortino"),
                "calmar": p.get("calmar"),
                "return_2025": p.get("return_2025"),
                "return_2026": p.get("return_2026"),
                "test_2025_2026_return": p.get("test_2025_2026_return"),
                "turnover_annual": p.get("turnover_annual"),
                "cost_drag_annual": p.get("cost_drag_annual"),
                "max_holdings": p.get("max_holdings"),
                "avg_stale_pct": p.get("avg_stale_pct"),
                "max_stale_pct": p.get("max_stale_pct"),
                "writeoff_count": p.get("writeoff_count"),
                "writeoff_value": p.get("writeoff_value"),
                "equal_weight_cagr": ew.get("cagr"),
                "equal_weight_max_drawdown": ew.get("max_drawdown"),
                "equal_weight_sharpe": ew.get("sharpe"),
                "excess_vs_equal_weight": {
                    k: p["excess_vs_equal_weight"].get(k)
                    for k in ("months", "mean_monthly", "t_stat", "hit_rate")
                },
                "nifty": p.get("nifty_buy_hold"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
