#!/usr/bin/env python3
"""Deterministic feature tests (stdlib only)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.features import StockState


def feed_flat(n=220, close=100.0, high=101.0, low=99.0, volume=1000.0):
    s = StockState("TEST")
    bar = None
    for i in range(n):
        bar = s.update(
            f"2024-01-{i + 1:02d}",
            close,
            high,
            low,
            close,
            volume,
            100.0,
            close,
            frozenset(),
        )
    return s, bar


def test_flat_series():
    s, b = feed_flat()
    assert s.n == 220
    assert abs(b.dma20 - 100.0) < 1e-9
    assert abs(b.dma50 - 100.0) < 1e-9
    assert abs(b.dma200 - 100.0) < 1e-9
    assert abs(b.atr - 2.0) < 1e-9
    assert abs(b.rsi - 50.0) < 1e-9
    assert abs(b.adx - 0.0) < 1e-9
    assert abs(b.dma50_slope - 0.0) < 1e-9
    assert abs(b.vol20 - 1000.0) < 1e-9
    assert abs(b.turnover20 - 100.0) < 1e-9


def test_uptrend():
    s = StockState("UP")
    b = None
    for i in range(220):
        c = 100.0 + i * 0.5
        b = s.update(
            f"2024-01-{i + 1:02d}",
            c - 0.2,
            c + 0.5,
            c - 0.5,
            c,
            1000.0,
            100.0,
            c,
            frozenset(),
        )
    assert b.dma20 > b.dma50 > b.dma200
    assert b.dma50_slope > 0
    assert b.rsi > 70
    assert b.adx > 20


def test_rolling_window_matches_manual_mean():
    s = StockState("ROLL")
    closes = []
    for i in range(60):
        c = 100.0 + i
        closes.append(c)
        b = s.update(
            f"2024-01-{i + 1:02d}",
            c,
            c + 1,
            c - 1,
            c,
            1000.0,
            100.0,
            c,
            frozenset(),
        )
    assert abs(b.dma20 - sum(closes[-20:]) / 20.0) < 1e-9
    assert abs(b.dma50 - sum(closes[-50:]) / 50.0) < 1e-9


def test_invalid_bar_is_rejected():
    s = StockState("BAD")
    assert s.update("2024-01-01", 100, 99, 101, 100, 1, 1, 100, frozenset()) is None
    assert s.update("2024-01-01", 100, 101, 99, 0, 1, 1, 100, frozenset()) is None
    assert s.n == 0


if __name__ == "__main__":
    test_flat_series()
    test_uptrend()
    test_rolling_window_matches_manual_mean()
    test_invalid_bar_is_rejected()
    print("features: 4/4 passed")
