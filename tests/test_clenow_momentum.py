#!/usr/bin/env python3
"""Unit tests for the Clenow momentum helper and backtest building blocks.

    python3 tests/test_clenow_momentum.py
"""

from __future__ import annotations

import math
import os
import sys
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.scorer import calculate_clenow_momentum  # noqa: E402
from jobs.backtest_clenow_momentum import (  # noqa: E402
    _atr,
    build_nifty_regime_hysteresis,
    build_rebalance_pairs,
    evaluate_clenow_gate,
    inverse_vol_weights,
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


def close(a: float, b: float, tol: float = 1e-9) -> None:
    if abs(a - b) > tol:
        raise AssertionError(f"{a!r} != {b!r} (tol {tol})")


def test_perfect_exponential() -> None:
    prices = [100.0 * math.exp(0.001 * i) for i in range(90)]
    score = calculate_clenow_momentum(prices, 90)
    close(score, 0.001 * 252.0, 1e-6)


def test_flat_series_is_zero() -> None:
    close(calculate_clenow_momentum([100.0] * 90, 90), 0.0)


def test_choppy_scores_lower_than_smooth() -> None:
    smooth = [100.0 * math.exp(0.001 * i) for i in range(90)]
    choppy = [
        100.0 * math.exp(0.001 * i) * (1.0 + 0.05 * math.sin(i))
        for i in range(90)
    ]
    smooth_score = calculate_clenow_momentum(smooth, 90)
    choppy_score = calculate_clenow_momentum(choppy, 90)
    if not choppy_score < smooth_score:
        raise AssertionError((choppy_score, smooth_score))


def test_insufficient_history_is_zero() -> None:
    close(calculate_clenow_momentum([100.0] * 89, 90), 0.0)


def test_non_positive_price_is_zero() -> None:
    prices = [100.0] * 89 + [0.0]
    close(calculate_clenow_momentum(prices, 90), 0.0)
    prices = [100.0] * 89 + [-1.0]
    close(calculate_clenow_momentum(prices, 90), 0.0)


def test_prefix_invariance() -> None:
    prices = [100.0 * math.exp(0.0005 * i) for i in range(130)]
    full = calculate_clenow_momentum(prices, 90)
    tail = calculate_clenow_momentum(prices[-90:], 90)
    close(full, tail)


def test_inverse_vol_weights_cap() -> None:
    rows = [{"atr20": 1.0 + i * 0.1} for i in range(10)]
    weights = inverse_vol_weights(rows, 0.10)
    if len(weights) != 10:
        raise AssertionError(weights)
    if any(w > 0.10 + 1e-12 for w in weights):
        raise AssertionError(weights)
    if abs(sum(weights) - 1.0) > 1e-9:
        raise AssertionError(sum(weights))
    if weights[0] <= weights[-1]:
        raise AssertionError(weights)


def test_inverse_vol_weights_fifteen_names() -> None:
    rows = [{"atr20": 1.0} for _ in range(15)]
    weights = inverse_vol_weights(rows, 0.10)
    close(sum(weights), 1.0)
    if any(abs(w - 1.0 / 15.0) > 1e-12 for w in weights):
        raise AssertionError(weights)


def test_atr_positive() -> None:
    highs = deque([101.0, 102.0, 103.0], maxlen=3)
    lows = deque([99.0, 100.0, 101.0], maxlen=3)
    closes = deque([100.0, 101.0, 102.0], maxlen=3)
    atr = _atr(highs, lows, closes, 2)
    if atr <= 0:
        raise AssertionError(atr)


def test_regime_hysteresis_buffer() -> None:
    dates = [f"d{i:04d}" for i in range(205)]
    closes = {d: 100.0 for d in dates[:200]}
    closes[dates[200]] = 101.0
    closes[dates[201]] = 99.0
    closes[dates[202]] = 97.9
    closes[dates[203]] = 100.1
    regime = build_nifty_regime_hysteresis(
        dates, closes, window=200, buffer=0.02
    )
    if regime[dates[199]] is not False:
        raise AssertionError(regime[dates[199]])
    if regime[dates[200]] is not True:
        raise AssertionError(regime[dates[200]])
    if regime[dates[201]] is not True:
        raise AssertionError(regime[dates[201]])
    if regime[dates[202]] is not False:
        raise AssertionError(regime[dates[202]])
    if regime[dates[203]] is not True:
        raise AssertionError(regime[dates[203]])


def test_rebalance_pairs_quarterly() -> None:
    dates = [f"2020-{1 + (i // 28):02d}-{1 + (i % 28):02d}" for i in range(400)]
    # Dates are only used as strings; uniqueness and order matter here.
    pairs = build_rebalance_pairs(dates, dates[0], dates[-1], 63, warmup=100)
    if not pairs:
        raise AssertionError("no pairs")
    if pairs[0][0] != dates[100]:
        raise AssertionError(pairs[0])
    if pairs[0][1] != dates[101]:
        raise AssertionError(pairs[0])
    if pairs[1][0] != dates[163]:
        raise AssertionError(pairs[1])
    for signal, exec_d in pairs:
        if signal > dates[-1] or exec_d > dates[-1]:
            raise AssertionError((signal, exec_d))


def _good_stats() -> dict:
    return {
        "cagr": 0.15,
        "sharpe": 0.9,
        "max_drawdown": -0.20,
        "profit_factor": 1.5,
    }


def _bad_stats() -> dict:
    return {
        "cagr": -0.05,
        "sharpe": 0.1,
        "max_drawdown": -0.45,
        "profit_factor": 0.8,
    }


def test_gate_train_fail() -> None:
    gate = evaluate_clenow_gate(
        _bad_stats(),
        None,
        _bad_stats(),
        None,
        {"cost_drag_annual": 0.01, "turnover_annual": 3.0},
        None,
        0.12,
        None,
        20,
        0,
        4,
    )
    if gate["decision"] != "TRAIN_FAIL":
        raise AssertionError(gate)
    if "train_net_cagr_positive" not in gate["train_failed"]:
        raise AssertionError(gate)


def test_gate_train_pass_without_test() -> None:
    gate = evaluate_clenow_gate(
        _good_stats(),
        None,
        _good_stats(),
        None,
        {"cost_drag_annual": 0.003, "turnover_annual": 0.8},
        None,
        0.12,
        None,
        20,
        0,
        4,
    )
    if gate["decision"] != "TRAIN_PASS":
        raise AssertionError(gate)


def test_gate_insufficient_oos() -> None:
    gate = evaluate_clenow_gate(
        _good_stats(),
        _good_stats(),
        _good_stats(),
        _good_stats(),
        {"cost_drag_annual": 0.003, "turnover_annual": 0.8},
        {"cost_drag_annual": 0.003, "turnover_annual": 0.8},
        0.12,
        0.12,
        20,
        2,
        4,
    )
    if gate["decision"] != "INSUFFICIENT_OOS":
        raise AssertionError(gate)


def main() -> None:
    tests = [
        ("perfect exponential", test_perfect_exponential),
        ("flat series", test_flat_series_is_zero),
        ("choppy vs smooth", test_choppy_scores_lower_than_smooth),
        ("insufficient history", test_insufficient_history_is_zero),
        ("non-positive price", test_non_positive_price_is_zero),
        ("prefix invariance", test_prefix_invariance),
        ("inverse-vol cap", test_inverse_vol_weights_cap),
        ("inverse-vol 15 names", test_inverse_vol_weights_fifteen_names),
        ("ATR positive", test_atr_positive),
        ("regime hysteresis", test_regime_hysteresis_buffer),
        ("quarterly pairs", test_rebalance_pairs_quarterly),
        ("gate train fail", test_gate_train_fail),
        ("gate train pass", test_gate_train_pass_without_test),
        ("gate insufficient OOS", test_gate_insufficient_oos),
    ]
    for name, fn in tests:
        ok(name, fn)
    print()
    print(f"clenow momentum: {PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
