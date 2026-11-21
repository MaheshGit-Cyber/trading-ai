#!/usr/bin/env python3
"""Phase 4B: All-Weather + Dynamic Trend De-risking.

Frozen rule (docs/phase4b-hypothesis.md):
  - Normal regime (Nifty > 200DMA at month-end):
      50% Nifty, 20% Gold BeES, 20% debt, 10% cash/BTC.
  - De-risking regime (Nifty <= 200DMA at month-end):
      15% Nifty, 45% Gold BeES, 40% debt, 0% cash/BTC.
  - Signal at month-end close; execute at next session open.
  - Rebalance on a regime change, plus a semi-annual drift rebalance on the
    last session of June/December. No Phase 4 crash harvesting.

    python3 jobs/backtest_all_weather_derisk.py \
        --outdir data/backtest_all_weather_derisk_2010_2026
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date as ddate

from backtest_all_weather import align_to_dates, load_close
from backtest_monthly_momentum import daily_stats, max_drawdown, period_return


ASSETS = ("eq", "gold", "debt", "crypto", "cash")
COST = {
    "eq": 0.0010,
    "gold": 0.0010,
    "debt": 0.0002,
    "crypto": 0.0020,
    "cash": 0.0,
}
NORMAL = {"eq": 0.50, "gold": 0.20, "debt": 0.20}
DERISK = {"eq": 0.15, "gold": 0.45, "debt": 0.40}
SMA_WINDOW = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--gold", default="data/gold/goldbees_daily_2010_2026.csv")
    p.add_argument("--crypto", default="data/crypto/btcusdt_daily_2017_2026.csv")
    p.add_argument("--start", default="2010-01-04")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--debt-rate", type=float, default=0.07)
    p.add_argument("--equity-expense", type=float, default=0.0020)
    p.add_argument("--outdir", required=True)
    return p.parse_args()


def load_field(path: str, field: str) -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = (row.get("date") or "").strip()
            v = (row.get(field) or "").strip()
            if not d or not v:
                continue
            try:
                x = float(v)
            except ValueError:
                continue
            if x > 0:
                out[d] = x
    return out


def open_series(
    raw_open: dict[str, float],
    raw_close: dict[str, float],
    dates: list[str],
) -> dict[str, float | None]:
    """Forward-fill open, falling back to the close when open is missing."""
    out: dict[str, float | None] = {}
    last_open: float | None = None
    last_close: float | None = None
    for d in dates:
        if d in raw_open:
            last_open = raw_open[d]
        if d in raw_close:
            last_close = raw_close[d]
        out[d] = last_open if last_open is not None else last_close
    return out


def month_end_dates(dates: list[str]) -> set[str]:
    """Last session of each completed month.

    The final month is excluded because the data may end mid-month; it is not
    a valid month-end signal.
    """
    by_month: dict[str, str] = {}
    for d in dates:
        by_month[d[:7]] = d
    months = sorted(by_month)
    if len(months) <= 1:
        return set()
    return {by_month[m] for m in months[:-1]}


def target_weights(
    regime: str,
    crypto_price: float | None,
    gold_price: float | None,
) -> dict[str, float]:
    base = dict(NORMAL if regime == "normal" else DERISK)
    base.setdefault("cash", 0.0)
    base.setdefault("crypto", 0.0)

    if regime == "normal":
        if crypto_price is not None:
            base["crypto"] = 0.10
        else:
            base["cash"] = base.get("cash", 0.0) + 0.10
    # De-risking has no cash/crypto sleeve by the approved rule.

    if gold_price is None:
        base["cash"] = base.get("cash", 0.0) + base.get("gold", 0.0)
        base["gold"] = 0.0
    return base


def main() -> None:
    args = parse_args()
    nifty = load_close(args.nifty)
    nifty_open_raw = load_field(args.nifty, "open")
    gold_close_raw = load_close(args.gold)
    gold_open_raw = load_field(args.gold, "open")
    crypto_close_raw = load_close(args.crypto)
    crypto_open_raw = load_field(args.crypto, "open")

    dates = sorted(d for d in nifty if args.start <= d <= args.end)
    if not dates:
        raise SystemExit("no dates in range")

    eq = {d: nifty[d] for d in dates}
    gold = align_to_dates(gold_close_raw, dates)
    crypto = align_to_dates(crypto_close_raw, dates)
    eq_open = open_series(nifty_open_raw, nifty, dates)
    gold_open = open_series(gold_open_raw, gold_close_raw, dates)
    crypto_open = open_series(crypto_open_raw, crypto_close_raw, dates)

    start = ddate.fromisoformat(dates[0])
    debt = {
        d: (1.0 + args.debt_rate)
        ** ((ddate.fromisoformat(d) - start).days / 365.25)
        for d in dates
    }

    month_ends = month_end_dates(dates)
    semi = {d for d in month_ends if d[5:7] in ("06", "12")}
    date_index = {d: i for i, d in enumerate(dates)}

    units = {k: 0.0 for k in ASSETS}
    regime = "normal"
    pending: dict | None = None
    peak = args.capital
    total_costs = 0.0
    rebalances: list[dict] = []
    regime_changes: list[dict] = []
    curve: list[dict] = []
    prev_date: str | None = None

    def price_of(asset: str, d: str, field: str) -> float | None:
        if asset == "cash":
            return 1.0
        if asset == "eq":
            return eq_open.get(d) if field == "open" else eq.get(d)
        if asset == "gold":
            return gold_open.get(d) if field == "open" else gold.get(d)
        if asset == "debt":
            return debt.get(d)
        if asset == "crypto":
            return crypto_open.get(d) if field == "open" else crypto.get(d)
        return None

    def values_at(d: str, field: str) -> dict[str, float]:
        return {
            k: units[k] * (price_of(k, d, field) or 0.0) for k in ASSETS
        }

    def rebalance_at_open(d: str, reason: str, signal_date: str) -> None:
        nonlocal total_costs, peak
        vals = values_at(d, "open")
        equity = sum(vals.values())
        if equity <= 0:
            return
        w = target_weights(
            regime,
            crypto_open.get(d),
            gold_open.get(d),
        )
        for k in ("eq", "gold", "debt"):
            p = price_of(k, d, "open")
            if p is None or p <= 0:
                w["cash"] = w.get("cash", 0.0) + w.get(k, 0.0)
                w[k] = 0.0
        desired = {k: equity * w.get(k, 0.0) for k in ASSETS}
        cost = sum(
            abs(desired[k] - vals.get(k, 0.0)) * COST[k] for k in ASSETS
        )
        scale = max(0.0, (equity - cost) / equity)
        for k in ASSETS:
            p = price_of(k, d, "open")
            if p is None or p <= 0:
                units[k] = 0.0
                continue
            units[k] = (desired[k] * scale) / p
        total_costs += cost
        new_vals = values_at(d, "open")
        new_equity = sum(new_vals.values())
        rebalances.append(
            {
                "signal_date": signal_date,
                "execution_date": d,
                "reason": reason,
                "regime": regime,
                "equity_before": equity,
                "equity_after": new_equity,
                "cost": cost,
                "weights": {
                    k: (new_vals[k] / new_equity if new_equity else 0.0)
                    for k in ASSETS
                },
            }
        )
        if new_equity > peak:
            peak = new_equity

    # Initial allocation at the first close, normal regime.
    first = dates[0]
    w0 = target_weights("normal", crypto.get(first), gold.get(first))
    desired0 = {k: args.capital * w0.get(k, 0.0) for k in ASSETS}
    cost0 = sum(abs(desired0[k]) * COST[k] for k in ASSETS)
    scale0 = max(0.0, (args.capital - cost0) / args.capital)
    for k in ASSETS:
        p = price_of(k, first, "close")
        units[k] = (desired0[k] * scale0 / p) if p and p > 0 else 0.0
    total_costs += cost0
    vals0 = values_at(first, "close")
    eq0 = sum(vals0.values())
    rebalances.append(
        {
            "signal_date": first,
            "execution_date": first,
            "reason": "initial",
            "regime": "normal",
            "equity_before": args.capital,
            "equity_after": eq0,
            "cost": cost0,
            "weights": {
                k: (vals0[k] / eq0 if eq0 else 0.0) for k in ASSETS
            },
        }
    )
    peak = eq0
    curve.append(
        {
            "date": first,
            "equity": eq0,
            "drawdown": 0.0,
            "regime": regime,
        }
    )
    prev_date = first

    for i in range(1, len(dates)):
        d = dates[i]
        days = (
            ddate.fromisoformat(d) - ddate.fromisoformat(prev_date)
        ).days
        if days > 0:
            units["eq"] *= 1.0 - args.equity_expense * days / 365.25

        if pending is not None:
            rebalance_at_open(d, pending["reason"], pending["signal_date"])
            pending = None

        vals = values_at(d, "close")
        equity = sum(vals.values())
        if equity > peak:
            peak = equity
        dd = equity / peak - 1.0 if peak else 0.0

        # Month-end regime signal at the close.
        if d in month_ends:
            idx = date_index[d]
            sma200 = None
            if idx >= SMA_WINDOW - 1:
                window = [
                    eq[dates[j]]
                    for j in range(idx - SMA_WINDOW + 1, idx + 1)
                ]
                sma200 = sum(window) / SMA_WINDOW
            new_regime = (
                "normal"
                if sma200 is None or eq[d] > sma200
                else "derisk"
            )
            changed = new_regime != regime
            if changed:
                regime_changes.append(
                    {
                        "date": d,
                        "old_regime": regime,
                        "new_regime": new_regime,
                        "nifty": eq[d],
                        "sma200": sma200,
                    }
                )
                regime = new_regime
            if (changed or d in semi) and i + 1 < len(dates):
                pending = {
                    "signal_date": d,
                    "reason": "regime_change" if changed else "semi_annual",
                }

        curve.append(
            {
                "date": d,
                "equity": equity,
                "drawdown": dd,
                "regime": regime,
            }
        )
        prev_date = d

    dd, peak_date, trough_date = max_drawdown(curve)
    first = curve[0]["date"]
    last = curve[-1]["date"]
    years = max(
        (ddate.fromisoformat(last) - ddate.fromisoformat(first)).days
        / 365.25,
        1e-9,
    )
    final = curve[-1]["equity"]
    cagr = (final / args.capital) ** (1.0 / years) - 1.0
    stats = daily_stats(curve)

    by_year: dict[str, float] = {}
    last_by_year: dict[str, float] = {}
    for r in curve:
        last_by_year[r["date"][:4]] = r["equity"]
    prev = args.capital
    for y in sorted(last_by_year):
        by_year[y] = last_by_year[y] / prev - 1.0
        prev = last_by_year[y]

    derisk_days = sum(1 for r in curve if r["regime"] == "derisk")

    # Nifty buy-and-hold benchmark.
    nifty_curve = [
        {
            "date": d,
            "equity": args.capital * nifty[d] / nifty[dates[0]],
        }
        for d in dates
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
    nifty_by_year: dict[str, float] = {}
    nifty_last: dict[str, float] = {}
    for r in nifty_curve:
        nifty_last[r["date"][:4]] = r["equity"]
    prev = args.capital
    for y in sorted(nifty_last):
        nifty_by_year[y] = nifty_last[y] / prev - 1.0
        prev = nifty_last[y]

    phase4_path = "data/backtest_all_weather_2010_2026/summary_all_weather.json"
    phase4 = None
    if os.path.exists(phase4_path):
        with open(phase4_path) as f:
            phase4 = json.load(f)

    summary = {
        "setup": "all_weather_derisk",
        "phase": "4b_frozen",
        "start": first,
        "end": last,
        "capital": args.capital,
        "sma_window": SMA_WINDOW,
        "normal": NORMAL,
        "derisk": DERISK,
        "debt_rate": args.debt_rate,
        "equity_expense": args.equity_expense,
        "primary": {
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
            "by_year": by_year,
            "return_2025": period_return(curve, "2025-01-01", "2025-12-31"),
            "return_2026": period_return(curve, "2026-01-01"),
            "test_2025_2026_return": period_return(curve, "2025-01-01"),
            "total_costs": total_costs,
            "rebalances": len(rebalances),
            "regime_rebalances": sum(
                1 for r in rebalances if r["reason"] == "regime_change"
            ),
            "semi_rebalances": sum(
                1 for r in rebalances if r["reason"] == "semi_annual"
            ),
            "regime_changes": len(regime_changes),
            "derisk_days": derisk_days,
            "derisk_day_share": derisk_days / len(curve),
        },
        "regime_changes": regime_changes,
        "nifty_buy_hold": {
            "cagr": nifty_cagr,
            "max_drawdown": nifty_dd,
            "by_year": nifty_by_year,
            "return_2025": period_return(nifty_curve, "2025-01-01", "2025-12-31"),
            "return_2026": period_return(nifty_curve, "2026-01-01"),
            "test_2025_2026_return": period_return(nifty_curve, "2025-01-01"),
        },
        "phase4_reference": (
            {
                "primary": phase4.get("primary"),
                "static_no_crash": phase4.get("static_no_crash"),
                "cash_instead_of_crypto": phase4.get("cash_instead_of_crypto"),
            }
            if phase4
            else None
        ),
    }
    s = summary["primary"]
    gate = {
        "max_dd_lt_18": s["max_drawdown"] > -0.18,
        "cagr_gt_12": s["cagr"] > 0.12,
        "cagr_gt_15": s["cagr"] > 0.15,
        "calmar_gt_080": (s["calmar"] or 0.0) > 0.80,
        "2025_positive": by_year.get("2025", -1.0) > 0.0,
        "2026_positive": by_year.get("2026", -1.0) > 0.0,
        "nifty_plus_5": s["cagr"] > nifty_cagr + 0.05,
    }
    gate["core_pass"] = (
        gate["max_dd_lt_18"]
        and gate["cagr_gt_12"]
        and gate["calmar_gt_080"]
    )
    gate["product_pass"] = (
        gate["core_pass"]
        and gate["2025_positive"]
        and gate["2026_positive"]
        and gate["nifty_plus_5"]
    )
    summary["gate"] = gate

    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "summary_derisk.json"), "w") as f:
        json.dump(summary, f, indent=2)

    with open(
        os.path.join(args.outdir, "equity_curve_derisk.csv"), "w", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=["date", "equity", "drawdown", "regime"])
        w.writeheader()
        for r in curve:
            w.writerow(r)

    with open(
        os.path.join(args.outdir, "rebalances_derisk.csv"), "w", newline=""
    ) as f:
        fields = [
            "signal_date",
            "execution_date",
            "reason",
            "regime",
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
        for r in rebalances:
            w.writerow(
                {
                    "signal_date": r["signal_date"],
                    "execution_date": r["execution_date"],
                    "reason": r["reason"],
                    "regime": r["regime"],
                    "equity_before": r["equity_before"],
                    "equity_after": r["equity_after"],
                    "cost": r["cost"],
                    **{f"{k}_w": r["weights"].get(k, 0.0) for k in ASSETS},
                }
            )

    with open(
        os.path.join(args.outdir, "regime_changes.csv"), "w", newline=""
    ) as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "old_regime", "new_regime", "nifty", "sma200"],
        )
        w.writeheader()
        for r in regime_changes:
            w.writerow(r)

    print(
        json.dumps(
            {
                "primary": {
                    k: s.get(k)
                    for k in (
                        "cagr",
                        "max_drawdown",
                        "max_drawdown_peak",
                        "max_drawdown_trough",
                        "sharpe",
                        "sortino",
                        "calmar",
                        "final_equity",
                        "return_2025",
                        "return_2026",
                        "test_2025_2026_return",
                        "total_costs",
                        "regime_changes",
                        "derisk_day_share",
                    )
                },
                "gate": gate,
                "by_year": by_year,
                "nifty": {
                    "cagr": nifty_cagr,
                    "max_drawdown": nifty_dd,
                    "return_2025": summary["nifty_buy_hold"]["return_2025"],
                    "return_2026": summary["nifty_buy_hold"]["return_2026"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
