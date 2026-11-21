#!/usr/bin/env python3
"""A2 reporting helper: gross-of-costs add-back from the saved run files.

Gross is the pre-registered approximation:
``gross_equity(t) = net_equity(t) + cumulative_costs(t)``.
This is a reporting diagnostic, not a new strategy run.
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jobs.backtest_a2_momentum import (  # noqa: E402
    curve_stats,
    monthly_benchmark_stats,
    sanitize,
)


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def costs_by_date(trades: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in trades:
        d = t.get("date", "")
        if not d:
            continue
        out[d] = out.get(d, 0.0) + float(t.get("cost") or 0.0)
    return out


def gross_curve(curve: list[dict], trades: list[dict]) -> list[dict]:
    costs = costs_by_date(trades)
    out: list[dict] = []
    cum = 0.0
    for r in curve:
        cum += costs.get(r["date"], 0.0)
        out.append({"date": r["date"], "equity": float(r["equity"]) + cum})
    return out


def monthly_gross(curve: list[dict], capital: float) -> list[dict]:
    last_by_month: dict[str, float] = {}
    for r in curve:
        last_by_month[r["date"][:7]] = r["equity"]
    out: list[dict] = []
    prev = capital
    for ym in sorted(last_by_month):
        eq = last_by_month[ym]
        out.append({"month": ym, "equity": eq, "return": eq / prev - 1.0})
        prev = eq
    return out


def monthly_gross_from_net(
    net_monthly: list[dict], trades: list[dict], capital: float
) -> list[dict]:
    cost_by_month: dict[str, float] = {}
    for t in trades:
        ym = t.get("date", "")[:7]
        if not ym:
            continue
        cost_by_month[ym] = cost_by_month.get(ym, 0.0) + float(t.get("cost") or 0.0)
    out: list[dict] = []
    cum = 0.0
    prev = capital
    for m in net_monthly:
        ym = m["month"]
        cum += cost_by_month.get(ym, 0.0)
        eq = float(m["equity"]) + cum
        out.append({"month": ym, "equity": eq, "return": eq / prev - 1.0})
        prev = eq
    return out


def main() -> None:
    outdir = os.path.join(ROOT, "data", "backtest", "a2_momentum")
    summary_path = os.path.join(outdir, "summary_a2_momentum.json")
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)
    capital = float(summary["meta"]["capital"])
    split = summary["meta"]["split"]

    curve_on = read_csv(os.path.join(outdir, "curve_on.csv"))
    trades_on = read_csv(os.path.join(outdir, "trades_on.csv"))
    monthly_on_net = read_csv(os.path.join(outdir, "monthly_on.csv"))
    trades_off = read_csv(os.path.join(outdir, "trades_off.csv"))
    monthly_off_net = read_csv(os.path.join(outdir, "monthly_off.csv"))

    g_on_curve = gross_curve(curve_on, trades_on)
    g_on_monthly = monthly_gross(g_on_curve, capital)
    on_gross = {
        "method": "net_equity + cumulative_costs (cost add-back)",
        "full": curve_stats(g_on_curve, g_on_monthly),
        "train": curve_stats(
            g_on_curve, g_on_monthly, end=split, month_end="2024-12"
        ),
        "test": curve_stats(
            g_on_curve,
            g_on_monthly,
            start="2024-12-11",
            month_start="2025-01",
        ),
    }

    g_off_monthly = monthly_gross_from_net(monthly_off_net, trades_off, capital)
    off_gross = {
        "method": "net monthly equity + cumulative monthly costs (cost add-back)",
        **monthly_benchmark_stats(g_off_monthly),
    }

    payload = {
        "on_1x": on_gross,
        "off_1x": off_gross,
        "note": "Gross is an approximation that adds back actual costs; it is not a no-cost rerun. Net is the gate series.",
    }
    path = os.path.join(outdir, "gross_a2_momentum.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize(payload), f, indent=2)

    print("A2 gross-of-costs (cost add-back)")
    for label in ("full", "train", "test"):
        st = on_gross[label]
        print(
            f"  ON {label:5s} CAGR {st['cagr'] * 100:6.2f}%  "
            f"Sharpe {st['sharpe']:.2f}  maxDD {st['max_drawdown'] * 100:6.2f}%  "
            f"PF {st['profit_factor']:.2f}"
        )
    for label in ("full", "train", "test"):
        st = off_gross[label]
        print(
            f"  OFF {label:5s} CAGR {st['cagr'] * 100:6.2f}%  "
            f"Sharpe {st['sharpe']:.2f}  maxDD {st['max_drawdown'] * 100:6.2f}%  "
            f"PF {st['profit_factor']:.2f}"
        )
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
