#!/usr/bin/env python3
"""Backtest arithmetic tests: sizing, costs, slippage buckets."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobs.backtest_trend_pullback import (
    slip_one_way,
    size_position,
    trade_cost_r,
)


def test_position_cap():
    qty, risk_per_share, actual_risk = size_position(
        100.0, 99.0, 1000.0, 1_000_000.0, 0.01
    )
    assert risk_per_share == 1.0
    assert qty == 2_500  # 25% of capital, not the risk-only 10,000 shares
    assert actual_risk == 2_500.0


def test_slippage_buckets():
    assert slip_one_way(2_000.0) == 0.0010
    assert slip_one_way(500.0) == 0.0025
    assert slip_one_way(50.0) == 0.0050


def test_costs_are_positive_and_stress_hurts():
    base = trade_cost_r(100.0, 110.0, 1000, 10_000.0, 1000.0, 1.0)
    stress = trade_cost_r(100.0, 110.0, 1000, 10_000.0, 1000.0, 2.0)
    assert base > 0
    assert stress > base


if __name__ == "__main__":
    test_position_cap()
    test_slippage_buckets()
    test_costs_are_positive_and_stress_hurts()
    print("backtest math: 3/3 passed")
