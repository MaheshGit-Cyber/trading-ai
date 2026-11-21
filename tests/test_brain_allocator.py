#!/usr/bin/env python3
"""Allocator tests: Engine 1 only, risk mapping, regime and refusals."""

from __future__ import annotations

from datetime import date, timedelta
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.allocator import (  # noqa: E402
    DERISK_WEIGHTS,
    NORMAL_WEIGHTS,
    allocate,
    allocate_from_nifty,
    nifty_regime,
)
from brain.data import PriceBar  # noqa: E402

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


def _nifty(n: int = 260, step: float = 0.001) -> list[PriceBar]:
    first = date(2025, 1, 1)
    rows = []
    for i in range(n):
        close = 100.0 * ((1.0 + step) ** i)
        rows.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol="NIFTY50",
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=0,
                turnover_lacs=0,
                raw_close=close,
            )
        )
    return rows


def test_tables_sum_to_one() -> None:
    for score in range(1, 11):
        n = NORMAL_WEIGHTS[score]
        d = DERISK_WEIGHTS[score]
        assert abs(sum(n.values()) - 1.0) < 1e-9, (score, n)
        assert abs(sum(d.values()) - 1.0) < 1e-9, (score, d)
        assert all(v >= 0 for v in n.values())
        assert all(v >= 0 for v in d.values())


def test_phase4b_targets_are_present() -> None:
    assert NORMAL_WEIGHTS[7] == {
        "nifty50": 0.50,
        "gold_bees": 0.20,
        "debt": 0.20,
        "cash": 0.10,
    }
    assert DERISK_WEIGHTS[5] == {
        "nifty50": 0.15,
        "gold_bees": 0.45,
        "debt": 0.40,
        "cash": 0.00,
    }


def test_normal_allocation() -> None:
    a = allocate(regime="normal", risk_score=7, capital=1_000_000, as_of="2026-11-19")
    assert a.allowed is True
    assert a.engine_status == "conditional"
    assert a.weights["nifty50"] == 0.50
    assert a.amounts["nifty50"] == 500_000
    assert abs(sum(a.amounts.values()) - 1_000_000) <= 1.0
    assert "engine_conditional" in a.flags
    assert any("2026 -8.64%" in w for w in a.warnings)


def test_derisk_allocation_and_gold_flag() -> None:
    a = allocate(regime="derisk", risk_score=5, capital=500_000)
    assert a.allowed is True
    assert a.weights["gold_bees"] == 0.45
    assert a.amounts["gold_bees"] == 225_000
    assert "regime_derisk" in a.flags
    assert "gold_concentration" in a.flags


def test_momentum_is_refused() -> None:
    a = allocate(
        engine="momentum_alpha",
        regime="normal",
        risk_score=5,
        capital=1_000_000,
    )
    assert a.allowed is False
    assert a.engine_status == "research_only"
    assert a.flags == ("engine_not_allocatable",)
    assert a.weights == {}


def test_failed_engine_is_refused() -> None:
    a = allocate(
        engine="largecap_meanrev",
        regime="normal",
        risk_score=5,
        capital=1_000_000,
    )
    assert a.allowed is False
    assert a.engine_status == "failed"


def test_a2_momentum_is_refused() -> None:
    a = allocate(
        engine="a2_momentum",
        regime="normal",
        risk_score=5,
        capital=1_000_000,
    )
    assert a.allowed is False
    assert a.engine_status == "failed"
    assert a.flags == ("engine_not_allocatable",)
    assert a.weights == {}


def test_clenow_semiannual_is_refused() -> None:
    a = allocate(
        engine="clenow_momentum_semiannual",
        regime="normal",
        risk_score=5,
        capital=1_000_000,
    )
    assert a.allowed is False
    assert a.engine_status == "research_only"
    assert a.flags == ("engine_not_allocatable",)
    assert a.weights == {}


def test_unknown_engine_is_refused() -> None:
    a = allocate(
        engine="new_hot_thing",
        regime="normal",
        risk_score=5,
        capital=1_000_000,
    )
    assert a.allowed is False
    assert a.engine_status == "failed"
    assert a.flags == ("engine_unknown",)


def test_invalid_inputs_rejected() -> None:
    for kwargs in (
        {"regime": "normal", "risk_score": 0, "capital": 1_000_000},
        {"regime": "normal", "risk_score": 11, "capital": 1_000_000},
        {"regime": "risk_on", "risk_score": 5, "capital": 1_000_000},
        {"regime": "normal", "risk_score": 5, "capital": 0},
    ):
        try:
            allocate(**kwargs)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"invalid input accepted: {kwargs}")


def test_regime_up_and_down() -> None:
    up = nifty_regime(_nifty(260, 0.001))
    assert up.regime == "normal", up.to_dict()
    assert up.sma200 is not None
    down = nifty_regime(_nifty(260, -0.002))
    assert down.regime == "derisk", down.to_dict()


def test_regime_insufficient_history_defaults_normal() -> None:
    view = nifty_regime(_nifty(100, 0.001))
    assert view.regime == "normal"
    assert "insufficient_history" in view.flags
    assert "regime_defaults_to_normal" in view.flags


def test_allocate_from_nifty() -> None:
    view, a = allocate_from_nifty(_nifty(260, 0.001), risk_score=7, capital=1_000_000)
    assert view.regime == "normal"
    assert a.allowed is True
    assert a.regime == "normal"


def main() -> None:
    print("allocator:")
    ok("tables sum to one", test_tables_sum_to_one)
    ok("Phase 4B targets present", test_phase4b_targets_are_present)
    ok("normal allocation", test_normal_allocation)
    ok("de-risk allocation and gold flag", test_derisk_allocation_and_gold_flag)
    ok("momentum refused", test_momentum_is_refused)
    ok("failed engine refused", test_failed_engine_is_refused)
    ok("A2 momentum refused", test_a2_momentum_is_refused)
    ok("Clenow semi-annual refused", test_clenow_semiannual_is_refused)
    ok("unknown engine refused", test_unknown_engine_is_refused)
    ok("invalid inputs rejected", test_invalid_inputs_rejected)
    ok("regime up/down", test_regime_up_and_down)
    ok("regime insufficient history", test_regime_insufficient_history_defaults_normal)
    ok("allocate from Nifty", test_allocate_from_nifty)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
