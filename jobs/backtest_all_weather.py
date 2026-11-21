#!/usr/bin/env python3
"""Phase 4: All-Weather Multi-Asset Engine (approved 2026-11-21).

Target allocation:
  50% Nifty 50 index
  20% Gold BeES (split-adjusted)
  20% sovereign debt / liquid yield at 7.0% p.a.
  10% cash, or BTC/USDT once crypto history starts (2017-08-17)

Rules:
  - Semi-annual rebalance on the last NSE session of June and December.
  - Crash harvesting: when portfolio drawdown from the all-time high reaches
    -15%, rebalance to target once per drawdown episode. Reset on a new high.
  - Daily mark-to-market; no leverage; transaction costs and a 0.20% p.a.
    equity-index expense are charged.

    python3 jobs/backtest_all_weather.py \
        --nifty data/index/nifty50.csv \
        --gold data/gold/goldbees_daily_2010_2026.csv \
        --crypto data/crypto/btcusdt_daily_2017_2026.csv \
        --outdir data/backtest_all_weather_2010_2026
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from datetime import date as ddate

from backtest_monthly_momentum import daily_stats, max_drawdown, period_return


ASSETS = ("eq", "gold", "debt", "crypto", "cash")
COST = {
    "eq": 0.0010,
    "gold": 0.0010,
    "debt": 0.0002,
    "crypto": 0.0020,
    "cash": 0.0,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument(
        "--gold", default="data/gold/goldbees_daily_2010_2026.csv"
    )
    p.add_argument(
        "--crypto", default="data/crypto/btcusdt_daily_2017_2026.csv"
    )
    p.add_argument("--start", default="2010-01-04")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--debt-rate", type=float, default=0.07)
    p.add_argument("--equity-expense", type=float, default=0.0020)
    p.add_argument("--crash-dd", type=float, default=0.15)
    p.add_argument(
        "--no-crash-harvest",
        action="store_true",
        help="semi-annual rebalance only; used for the static benchmark",
    )
    p.add_argument(
        "--no-crypto",
        action="store_true",
        help="hold the 10% sleeve in cash instead of BTC",
    )
    p.add_argument(
        "--crash-on-index",
        action="store_true",
        help="trigger crash harvesting on Nifty drawdown, not portfolio equity drawdown",
    )
    p.add_argument("--outdir", required=True)
    return p.parse_args()


def load_close(path: str) -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = (row.get("date") or "").strip()
            c = (row.get("close") or "").strip()
            if not d or not c:
                continue
            try:
                out[d] = float(c)
            except ValueError:
                continue
    return out


def align_to_dates(
    series: dict[str, float], dates: list[str]
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    last: float | None = None
    for d in dates:
        if d in series:
            last = series[d]
        out[d] = last
    return out


def semi_annual_dates(dates: list[str]) -> set[str]:
    out: set[str] = set()
    for d in dates:
        if d[5:7] in ("06", "12"):
            out.add(d)
    # Keep only the last session of each June/December.
    keep: dict[str, str] = {}
    for d in dates:
        if d[5:7] in ("06", "12"):
            keep[d[:7]] = d
    return set(keep.values())


def target_weights(
    use_crypto: bool,
    crypto_price: float | None,
    gold_price: float | None,
) -> dict[str, float]:
    w = {"eq": 0.50, "gold": 0.20, "debt": 0.20}
    if gold_price is None:
        w["gold"] = 0.0
        w["cash"] = w.get("cash", 0.0) + 0.20
    if use_crypto and crypto_price is not None:
        w["crypto"] = 0.10
    else:
        w["cash"] = w.get("cash", 0.0) + 0.10
    return w


def simulate(
    args: argparse.Namespace,
    dates: list[str],
    eq: dict[str, float | None],
    gold: dict[str, float | None],
    debt: dict[str, float | None],
    crypto: dict[str, float | None],
    *,
    use_crypto: bool,
    crash_harvest: bool,
    crash_on_index: bool = False,
) -> dict:
    semi = semi_annual_dates(dates)
    cash = args.capital
    units = {k: 0.0 for k in ASSETS}
    peak = args.capital
    crash_triggered = False
    index_peak: float | None = None
    index_crash_triggered = False
    total_costs = 0.0
    rebalances = []
    curve = []
    prev_date = None

    def price_of(asset: str, d: str) -> float | None:
        if asset == "cash":
            return 1.0
        if asset == "eq":
            return eq.get(d)
        if asset == "gold":
            return gold.get(d)
        if asset == "debt":
            return debt.get(d)
        if asset == "crypto":
            return crypto.get(d)
        return None

    def values_at(d: str) -> dict[str, float]:
        return {
            k: units[k] * (price_of(k, d) or 0.0)
            for k in ASSETS
        }

    def rebalance(d: str, reason: str) -> None:
        nonlocal cash, total_costs, peak, crash_triggered, index_crash_triggered
        vals = values_at(d)
        equity = sum(vals.values())
        if equity <= 0:
            return
        w = target_weights(use_crypto, crypto.get(d), gold.get(d))
        # Missing assets go to cash.
        for k in ("eq", "gold", "debt"):
            p = price_of(k, d)
            if p is None or p <= 0:
                w["cash"] = w.get("cash", 0.0) + w.get(k, 0.0)
                w[k] = 0.0
        desired = {k: equity * w.get(k, 0.0) for k in ASSETS}
        cost = sum(
            abs(desired[k] - vals.get(k, 0.0)) * COST[k] for k in ASSETS
        )
        scale = max(0.0, (equity - cost) / equity)
        for k in ASSETS:
            p = price_of(k, d)
            if p is None or p <= 0:
                units[k] = 0.0
                continue
            units[k] = (desired[k] * scale) / p
        total_costs += cost
        new_vals = values_at(d)
        new_equity = sum(new_vals.values())
        rebalances.append(
            {
                "date": d,
                "reason": reason,
                "equity_before": equity,
                "equity_after": new_equity,
                "cost": cost,
                "weights": {
                    k: (new_vals[k] / new_equity if new_equity else 0.0)
                    for k in ASSETS
                },
            }
        )
        if reason == "crash_harvest":
            if crash_on_index:
                index_crash_triggered = True
            else:
                crash_triggered = True
        if new_equity > peak:
            peak = new_equity
            crash_triggered = False

    # Initial allocation at the first close.
    first = dates[0]
    w0 = target_weights(use_crypto, crypto.get(first), gold.get(first))
    for k in ("eq", "gold", "debt"):
        p = price_of(k, first)
        if p is None or p <= 0:
            w0["cash"] = w0.get("cash", 0.0) + w0.get(k, 0.0)
            w0[k] = 0.0
    desired0 = {k: args.capital * w0.get(k, 0.0) for k in ASSETS}
    cost0 = sum(abs(desired0[k]) * COST[k] for k in ASSETS)
    scale0 = max(0.0, (args.capital - cost0) / args.capital)
    for k in ASSETS:
        p = price_of(k, first)
        units[k] = (desired0[k] * scale0 / p) if p and p > 0 else 0.0
    total_costs += cost0
    vals0 = values_at(first)
    eq0 = sum(vals0.values())
    rebalances.append(
        {
            "date": first,
            "reason": "initial",
            "equity_before": args.capital,
            "equity_after": eq0,
            "cost": cost0,
            "weights": {
                k: (vals0[k] / eq0 if eq0 else 0.0) for k in ASSETS
            },
        }
    )
    peak = eq0

    for i, d in enumerate(dates):
        days = 0
        if prev_date is not None:
            days = (ddate.fromisoformat(d) - ddate.fromisoformat(prev_date)).days
        if days > 0:
            # Equity index fund expense ratio reduces NAV continuously.
            units["eq"] *= 1.0 - args.equity_expense * days / 365.25

        vals = values_at(d)
        equity = sum(vals.values())
        if equity > peak:
            peak = equity
            crash_triggered = False
        dd = equity / peak - 1.0 if peak else 0.0

        idx_dd = None
        if crash_on_index:
            ip = eq.get(d)
            if ip is not None and ip > 0:
                if index_peak is None or ip > index_peak:
                    index_peak = ip
                    index_crash_triggered = False
                idx_dd = ip / index_peak - 1.0

        reason = None
        if i > 0 and d in semi:
            reason = "semi_annual"
        elif i > 0 and crash_harvest:
            if crash_on_index:
                if (
                    idx_dd is not None
                    and not index_crash_triggered
                    and idx_dd <= -args.crash_dd
                ):
                    reason = "crash_harvest"
            elif not crash_triggered and dd <= -args.crash_dd:
                reason = "crash_harvest"

        if reason is not None:
            rebalance(d, reason)
            vals = values_at(d)
            equity = sum(vals.values())
            if equity > peak:
                peak = equity
                crash_triggered = False
            dd = equity / peak - 1.0 if peak else 0.0
            if reason == "semi_annual" and crash_harvest:
                if crash_on_index:
                    if idx_dd is not None and idx_dd <= -args.crash_dd:
                        index_crash_triggered = True
                elif dd <= -args.crash_dd:
                    crash_triggered = True

        curve.append(
            {
                "date": d,
                "equity": equity,
                "drawdown": dd,
                "weights": {
                    k: (vals[k] / equity if equity else 0.0) for k in ASSETS
                },
            }
        )
        prev_date = d

    dd, peak_date, trough_date = max_drawdown(curve)
    first = curve[0]["date"]
    last = curve[-1]["date"]
    years = max(
        (ddate.fromisoformat(last) - ddate.fromisoformat(first)).days / 365.25,
        1e-9,
    )
    final = curve[-1]["equity"]
    cagr = (final / args.capital) ** (1.0 / years) - 1.0
    stats = daily_stats(curve)
    by_year = {}
    for d in dates:
        by_year.setdefault(d[:4], None)
    last_by_year = {}
    for r in curve:
        last_by_year[r["date"][:4]] = r["equity"]
    prev = args.capital
    for y in sorted(last_by_year):
        by_year[y] = last_by_year[y] / prev - 1.0
        prev = last_by_year[y]

    return {
        "curve": curve,
        "rebalances": rebalances,
        "summary": {
            "first_date": first,
            "last_date": last,
            "years": years,
            "final_equity": final,
            "total_return": final / args.capital - 1.0,
            "cagr": cagr,
            "max_drawdown": dd,
            "max_drawdown_peak": peak_date,
            "max_drawdown_trough": trough_date,
            "sharpe": stats.get("sharpe"),
            "sortino": stats.get("sortino"),
            "vol_annual": stats.get("vol_annual"),
            "calmar": cagr / abs(dd) if dd else None,
            "return_2025": period_return(curve, "2025-01-01", "2025-12-31"),
            "return_2026": period_return(curve, "2026-01-01"),
            "test_2025_2026_return": period_return(curve, "2025-01-01"),
            "total_costs": total_costs,
            "rebalances": len(rebalances),
            "crash_rebalances": sum(
                1 for r in rebalances if r["reason"] == "crash_harvest"
            ),
            "by_year": by_year,
        },
    }


def write_outputs(
    outdir: str,
    primary: dict,
    static: dict,
    cash_variant: dict,
    nifty: dict[str, float],
    dates: list[str],
    args: argparse.Namespace,
) -> None:
    os.makedirs(outdir, exist_ok=True)
    nifty_first = nifty[dates[0]]
    nifty_curve = [
        {
            "date": d,
            "equity": args.capital * nifty[d] / nifty_first,
        }
        for d in dates
        if d in nifty
    ]
    nifty_dd, _, _ = max_drawdown(nifty_curve)
    nifty_years = max(
        (
            ddate.fromisoformat(nifty_curve[-1]["date"])
            - ddate.fromisoformat(nifty_curve[0]["date"])
        ).days
        / 365.25,
        1e-9,
    )
    nifty_cagr = (
        nifty_curve[-1]["equity"] / args.capital
    ) ** (1.0 / nifty_years) - 1.0

    summary = {
        "setup": "all_weather_multi_asset",
        "phase": "4_frozen",
        "nifty": args.nifty,
        "gold": args.gold,
        "crypto": args.crypto,
        "start": dates[0],
        "end": dates[-1],
        "capital": args.capital,
        "target": "50% Nifty 50, 20% Gold BeES, 20% debt @7%, "
        "10% cash/BTC (BTC after 2017-08-17)",
        "debt_rate": args.debt_rate,
        "equity_expense": args.equity_expense,
        "crash_threshold": args.crash_dd,
        "crash_trigger": "nifty_index" if args.crash_on_index else "portfolio_equity",
        "primary": primary["summary"],
        "static_no_crash": static["summary"],
        "cash_instead_of_crypto": cash_variant["summary"],
        "nifty_buy_hold": {
            "cagr": nifty_cagr,
            "max_drawdown": nifty_dd,
            "total_return": nifty_curve[-1]["equity"] / args.capital - 1.0,
            "return_2025": period_return(nifty_curve, "2025-01-01", "2025-12-31"),
            "return_2026": period_return(nifty_curve, "2026-01-01"),
            "test_2025_2026_return": period_return(nifty_curve, "2025-01-01"),
        },
    }
    with open(os.path.join(outdir, "summary_all_weather.json"), "w") as f:
        json.dump(summary, f, indent=2)
    for name, result in (
        ("primary", primary),
        ("static_no_crash", static),
        ("cash_instead_of_crypto", cash_variant),
    ):
        with open(
            os.path.join(outdir, f"equity_curve_{name}.csv"), "w", newline=""
        ) as f:
            w = csv.DictWriter(
                f, fieldnames=["date", "equity", "drawdown"]
            )
            w.writeheader()
            for r in result["curve"]:
                w.writerow(
                    {
                        "date": r["date"],
                        "equity": r["equity"],
                        "drawdown": r["drawdown"],
                    }
                )
        with open(
            os.path.join(outdir, f"rebalances_{name}.csv"), "w", newline=""
        ) as f:
            fields = [
                "date",
                "reason",
                "equity_before",
                "equity_after",
                "cost",
                "eq_w",
                "gold_w",
                "debt_w",
                "crypto_w",
                "cash_w",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in result["rebalances"]:
                w.writerow(
                    {
                        "date": r["date"],
                        "reason": r["reason"],
                        "equity_before": r["equity_before"],
                        "equity_after": r["equity_after"],
                        "cost": r["cost"],
                        **{
                            f"{k}_w": r["weights"].get(k, 0.0)
                            for k in ASSETS
                        },
                    }
                )


def main() -> None:
    args = parse_args()
    nifty = load_close(args.nifty)
    gold_raw = load_close(args.gold)
    crypto_raw = load_close(args.crypto)
    dates = sorted(d for d in nifty if args.start <= d <= args.end)
    if not dates:
        raise SystemExit("no dates in range")
    gold = align_to_dates(gold_raw, dates)
    crypto = align_to_dates(crypto_raw, dates)
    start = ddate.fromisoformat(dates[0])
    debt = {
        d: (1.0 + args.debt_rate)
        ** ((ddate.fromisoformat(d) - start).days / 365.25)
        for d in dates
    }
    eq = {d: nifty[d] for d in dates}

    primary = simulate(
        args,
        dates,
        eq,
        gold,
        debt,
        crypto,
        use_crypto=True,
        crash_harvest=not args.no_crash_harvest,
        crash_on_index=args.crash_on_index,
    )
    static = simulate(
        args,
        dates,
        eq,
        gold,
        debt,
        crypto,
        use_crypto=True,
        crash_harvest=False,
    )
    cash_variant = simulate(
        args,
        dates,
        eq,
        gold,
        debt,
        crypto,
        use_crypto=False,
        crash_harvest=True,
        crash_on_index=args.crash_on_index,
    )
    write_outputs(args.outdir, primary, static, cash_variant, nifty, dates, args)
    p = primary["summary"]
    print(
        json.dumps(
            {
                "primary": {
                    k: p.get(k)
                    for k in (
                        "cagr",
                        "max_drawdown",
                        "max_drawdown_peak",
                        "max_drawdown_trough",
                        "sharpe",
                        "sortino",
                        "calmar",
                        "return_2025",
                        "return_2026",
                        "test_2025_2026_return",
                        "final_equity",
                        "total_costs",
                        "rebalances",
                        "crash_rebalances",
                    )
                },
                "static_no_crash": static["summary"],
                "cash_instead_of_crypto": cash_variant["summary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
