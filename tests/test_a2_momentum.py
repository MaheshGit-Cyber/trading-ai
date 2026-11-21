#!/usr/bin/env python3
"""A2 cross-sectional momentum tests: signal, decile, regime, sector, gate."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jobs.backtest_a2_momentum import (  # noqa: E402
    add_dividend,
    build_nifty_regime,
    curve_stats,
    evaluate_gate,
    is_excluded,
    momentum_12_1,
    monthly_from_curve,
    next_month,
    parse_flags,
    profit_factor,
    sector_proxy,
    top_decile,
)
from jobs.backtest_monthly_momentum import run_portfolio  # noqa: E402


def test_momentum_12_1():
    closes = [100.0] + [0.0] * 230 + [120.0] + [0.0] * 21
    assert len(closes) == 253
    assert abs(momentum_12_1(closes) - 0.20) < 1e-12
    assert momentum_12_1([100.0] * 252) is None
    assert momentum_12_1([0.0] + [0.0] * 251 + [100.0]) is None


def test_top_decile():
    rows = [{"stock_id": f"S{i:03d}", "mom": float(i)} for i in range(200)]
    chosen = top_decile(rows, 0.10)
    assert len(chosen) == 20
    assert chosen[0]["mom"] == 199.0
    assert chosen[-1]["mom"] == 180.0
    assert len(top_decile(rows[:15], 0.10)) == 1
    assert top_decile([], 0.10) == []


def test_build_nifty_regime():
    dates = [f"d{i:03d}" for i in range(201)]
    closes = {d: 100.0 for d in dates}
    closes[dates[-1]] = 101.0
    regime = build_nifty_regime(dates, closes, window=200)
    assert dates[198] not in regime
    assert regime[dates[199]] is False
    assert regime[dates[200]] is True
    assert len(regime) == 2


def test_sector_proxy():
    assert sector_proxy("HDFC Bank") == "Banks"
    assert sector_proxy("Infosys") == "IT"
    assert sector_proxy("Sun Pharmaceutical Industries") == "Pharma/Healthcare"
    assert sector_proxy("Tata Steel") == "Metals"
    assert sector_proxy("Unknown Corp") == "Other"


def test_next_month():
    assert next_month("2024-01") == "2024-02"
    assert next_month("2024-12") == "2025-01"


def test_profit_factor():
    assert abs(profit_factor([0.1, -0.05, 0.2]) - 6.0) < 1e-12
    assert profit_factor([0.1, 0.2]) == float("inf")
    assert profit_factor([-0.1, -0.2]) == 0.0
    assert profit_factor([]) is None


def test_parse_flags_and_exclusions():
    assert parse_flags("ca_unadjusted;delivery_missing") == frozenset(
        {"ca_unadjusted", "delivery_missing"}
    )
    assert parse_flags("") == frozenset()
    assert is_excluded("NIFTYBEES", "Nippon India ETF Nifty BeES")
    assert not is_excluded("HDFCBANK", "HDFC Bank Limited")


def test_monthly_from_curve():
    curve = [
        {"date": "2024-01-02", "equity": 100.0},
        {"date": "2024-01-31", "equity": 110.0},
        {"date": "2024-02-29", "equity": 121.0},
    ]
    monthly = monthly_from_curve(curve)
    assert len(monthly) == 2
    assert monthly[0]["month"] == "2024-01"
    assert abs(monthly[0]["return"] - 0.10) < 1e-12
    assert monthly[1]["month"] == "2024-02"
    assert abs(monthly[1]["return"] - 0.10) < 1e-12


def test_curve_stats():
    curve = [
        {"date": "2024-01-02", "equity": 100.0},
        {"date": "2024-01-31", "equity": 110.0},
        {"date": "2024-02-29", "equity": 121.0},
    ]
    monthly = monthly_from_curve(curve)
    st = curve_stats(curve, monthly)
    assert abs(st["total_return"] - 0.21) < 1e-12
    assert st["months"] == 2
    assert st["max_drawdown"] == 0.0
    assert st["profit_factor"] == float("inf")


def test_run_portfolio_uses_weight():
    args = argparse.Namespace(
        capital=100_000.0,
        target_weight=0.10,
        max_adv_pct=0.05,
        slippage_mult=1.0,
        writeoff_days=0,
        writeoff_unlisted_only=False,
        master="",
        end="2024-02-01",
    )
    pairs = [("2024-01-31", "2024-02-01")]
    selections = {
        "2024-01-31": [
            {"stock_id": "A", "turnover20": 1000.0, "weight": 0.5},
            {"stock_id": "B", "turnover20": 1000.0, "weight": 0.5},
        ]
    }
    opens = {"A": {"2024-02-01": 100.0}, "B": {"2024-02-01": 100.0}}
    closes = {"A": {"2024-02-01": 100.0}, "B": {"2024-02-01": 100.0}}
    factors = {"A": {"2024-02-01": 1.0}, "B": {"2024-02-01": 1.0}}
    result = run_portfolio(
        args,
        pairs,
        selections,
        opens,
        closes,
        factors,
        ["2024-02-01"],
        {"2024-02-01": 100.0},
    )
    buys = [t for t in result["trades"] if t["side"] == "BUY"]
    assert len(buys) == 2
    # 50% weight at 100k / Rs 100 is ~500 shares, not the 10% fallback (100).
    assert all(t["qty"] >= 450 for t in buys)


def _fake_run(cagr, sharpe, dd, pf, months, stress_cagr=None):
    base = {
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": dd,
        "profit_factor": pf,
        "months": months,
    }
    return {
        "full": dict(base),
        "train": dict(base),
        "test": dict(base),
        "stress_cagr": stress_cagr,
    }


def test_evaluate_gate():
    on_1x = _fake_run(0.12, 1.0, -0.20, 1.5, 23)
    on_1x["train"]["cagr"] = 0.11
    on_1x["train"]["profit_factor"] = 1.3
    on_1x["test"]["cagr"] = 0.10
    on_1x["test"]["profit_factor"] = 1.2
    on_2x = _fake_run(0.12, 1.0, -0.20, 1.5, 23)
    on_2x["test"]["cagr"] = 0.05
    gate = evaluate_gate(on_1x, on_2x, 0.08, 20)
    assert gate["decision"] == "PASS"

    bad = _fake_run(0.12, 1.0, -0.20, 1.5, 23)
    bad["train"]["cagr"] = 0.11
    bad["train"]["profit_factor"] = 1.3
    bad["test"]["cagr"] = -0.01
    bad["test"]["profit_factor"] = 1.2
    gate = evaluate_gate(bad, on_2x, 0.08, 20)
    assert gate["decision"] == "FAIL"
    assert "test_net_cagr_positive" in gate["failed"]

    short = _fake_run(0.12, 1.0, -0.20, 1.5, 10)
    gate = evaluate_gate(short, on_2x, 0.08, 20)
    assert gate["decision"] == "INSUFFICIENT_OOS"


def test_add_dividend():
    assert abs(add_dividend(0.10, 0.012) - 0.1132) < 1e-12
    assert add_dividend(None, 0.012) is None


def main() -> None:
    tests = [
        test_momentum_12_1,
        test_top_decile,
        test_build_nifty_regime,
        test_sector_proxy,
        test_next_month,
        test_profit_factor,
        test_parse_flags_and_exclusions,
        test_monthly_from_curve,
        test_curve_stats,
        test_run_portfolio_uses_weight,
        test_evaluate_gate,
        test_add_dividend,
    ]
    for test in tests:
        test()
    print(f"a2 momentum: {len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    main()
