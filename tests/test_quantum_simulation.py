#!/usr/bin/env python3
"""Unit tests for the Quantum Simulation Lab anti-overfitting shields."""

from __future__ import annotations

import csv
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jobs.deflated_sharpe import dsr_stats  # noqa: E402
from jobs.quantum_simulation_lab import (  # noqa: E402
    block_bootstrap_returns,
    build_quantum_selections,
    build_regime_states,
    build_state_targets,
    classify_regime,
    load_nifty_until,
    monte_carlo,
    path_metrics,
    period_returns,
    validate_window,
)

PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


def test_classify_regime() -> None:
    assert classify_regime(110.0, 105.0, 100.0) == 1
    assert classify_regime(101.0, 99.0, 100.0) == 2
    assert classify_regime(99.0, 95.0, 100.0) == 3
    # Crisis takes precedence even when the fast average is above the slow one.
    assert classify_regime(99.0, 101.0, 100.0) == 3
    assert classify_regime(100.0, 100.0, 100.0) == 2


def test_regime_states_prefix_invariance() -> None:
    dates = [f"d{i:04d}" for i in range(260)]
    closes = {d: 100.0 + i * 0.2 for i, d in enumerate(dates)}
    full = build_regime_states(dates, closes)
    prefix = build_regime_states(dates[:220], closes)
    assert prefix
    for d, state in prefix.items():
        assert full[d] == state, (d, state, full[d])
    assert full[dates[-1]] == 1


def test_state_targets() -> None:
    rows = [{"stock_id": "A", "symbol": "A", "weight": 0.5}]
    bull = build_state_targets(1, rows)
    assert bull[0]["stock_id"] == "A"

    bull_empty = build_state_targets(1, [])
    assert {x["stock_id"] for x in bull_empty} == {
        "NSE:INF732E01011",
        "NSE:INF732E01037",
    }
    assert abs(sum(x["weight"] for x in bull_empty) - 1.0) < 1e-12

    sideways = build_state_targets(2, [])
    assert {x["stock_id"] for x in sideways} == {
        "NSE:INF732E01011",
        "NSE:INF732E01037",
    }
    assert abs(sum(x["weight"] for x in sideways) - 1.0) < 1e-12

    crisis = build_state_targets(3, [])
    assert {x["stock_id"] for x in crisis} == {
        "GOLDBEES",
        "NSE:INF732E01037",
    }
    assert abs(sum(x["weight"] for x in crisis) - 1.0) < 1e-12


def test_quantum_selections_state_routing() -> None:
    pairs = [("d1", "e1"), ("d2", "e2"), ("d3", "e3")]
    states = {"d1": 1, "d2": 2, "d3": 3}
    fresh = {"d1": [{"stock_id": "A", "symbol": "A", "weight": 0.5}]}
    selections, counts = build_quantum_selections(pairs, states, fresh)
    assert counts == {1: 1, 2: 1, 3: 1}
    assert selections["d1"][0]["stock_id"] == "A"
    assert selections["d2"][0]["stock_id"] == "NSE:INF732E01011"
    assert selections["d3"][0]["stock_id"] == "GOLDBEES"
    for signal, execution in pairs:
        for row in selections[signal]:
            assert row["signal_date"] == signal
            assert row["execution_date"] == execution


def test_block_bootstrap_deterministic() -> None:
    returns = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    a = block_bootstrap_returns(returns, 5, 3, 7)
    b = block_bootstrap_returns(returns, 5, 3, 7)
    assert a == b
    assert len(a) == 5
    assert all(len(path) == len(returns) for path in a)
    assert all(x in returns for path in a for x in path)
    for bad in ([],):
        try:
            block_bootstrap_returns(bad, 1, 3, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("empty returns accepted")
    try:
        block_bootstrap_returns(returns, 1, 0, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("zero block accepted")


def test_path_metrics() -> None:
    m = path_metrics([0.10, -0.10])
    assert abs(m["final_equity"] - 0.99) < 1e-12
    assert abs(m["max_drawdown"] - (-0.10)) < 1e-12
    assert m["cagr"] < 0

    up = path_metrics([0.01] * 12)
    assert up["final_equity"] > 1.0
    assert up["max_drawdown"] == 0.0
    assert up["cagr"] > 0

    empty = path_metrics([])
    assert empty["final_equity"] == 1.0
    assert empty["cagr"] is None


def test_monte_carlo_percentiles() -> None:
    returns = [
        0.01,
        -0.02,
        0.03,
        0.0,
        0.02,
        -0.01,
        0.015,
        0.005,
        -0.005,
        0.01,
        0.02,
        -0.01,
    ]
    summary, metrics = monte_carlo(
        returns, n_paths=100, block_size=3, seed=1
    )
    assert len(metrics) == 100
    assert summary["cagr_p2_5"] <= summary["cagr_p5"]
    assert summary["cagr_p5"] <= summary["cagr_median"]
    assert summary["cagr_median"] <= summary["cagr_p95"]
    assert summary["cagr_p95"] <= summary["cagr_p97_5"]
    assert summary["maxdd_p2_5"] <= summary["maxdd_p5"]
    assert summary["maxdd_p5"] <= summary["maxdd_median"]


def test_deflated_sharpe() -> None:
    returns = [
        0.02,
        0.01,
        0.03,
        0.015,
        0.025,
        0.01,
        0.02,
        0.015,
        0.03,
        0.01,
        0.02,
        0.025,
    ]
    low_n = dsr_stats(returns, 2)
    high_n = dsr_stats(returns, 100)
    assert 0.0 <= low_n["dsr"] <= 1.0
    assert 0.0 <= high_n["dsr"] <= 1.0
    assert low_n["dsr"] > high_n["dsr"]
    assert high_n["sr_annual"] > high_n["sr_monthly"]

    negative = dsr_stats([-x for x in returns], 100)
    assert negative["dsr"] < 0.5

    for bad_returns, bad_trials in (([0.1, 0.2], 10), (returns, 1)):
        try:
            dsr_stats(bad_returns, bad_trials)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid DSR input accepted")


def test_period_returns() -> None:
    monthly = [
        {"month": "2018-12", "return": 0.5},
        {"month": "2019-01", "return": 0.1},
        {"month": "2024-12", "return": 0.2},
        {"month": "2025-01", "return": 0.9},
    ]
    got = period_returns(monthly, "2019-01-01", "2024-12-10")
    assert got == [0.1, 0.2]


def test_validate_window() -> None:
    validate_window("2024-12-10")
    try:
        validate_window("2024-12-11")
    except SystemExit:
        pass
    else:
        raise AssertionError("frozen test window accepted")


def test_load_nifty_until() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", newline="", delete=False
    ) as f:
        path = f.name
        w = csv.writer(f)
        w.writerow(["date", "close"])
        w.writerow(["2024-12-09", "100"])
        w.writerow(["2024-12-10", "101"])
        w.writerow(["2024-12-11", "999"])
    try:
        dates, closes = load_nifty_until(path, "2024-12-10")
        assert dates == ["2024-12-09", "2024-12-10"]
        assert closes == {"2024-12-09": 100.0, "2024-12-10": 101.0}
    finally:
        os.unlink(path)


def main() -> None:
    print("quantum simulation lab:")
    ok("three-state classifier", test_classify_regime)
    ok("regime prefix invariance", test_regime_states_prefix_invariance)
    ok("state targets", test_state_targets)
    ok("state routing", test_quantum_selections_state_routing)
    ok("block bootstrap", test_block_bootstrap_deterministic)
    ok("path metrics", test_path_metrics)
    ok("Monte Carlo percentiles", test_monte_carlo_percentiles)
    ok("deflated Sharpe", test_deflated_sharpe)
    ok("period returns", test_period_returns)
    ok("frozen window guard", test_validate_window)
    ok("Nifty stops at end", test_load_nifty_until)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
