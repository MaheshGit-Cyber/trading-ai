#!/usr/bin/env python3
"""Paper-book evaluator tests for the frozen no-look-ahead rule."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.contracts import PaperSnapshot  # noqa: E402
from brain.paper_book import evaluate_snapshots  # noqa: E402

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


def snap(day: str, weights: dict, prices: dict, capital: float = 1000.0) -> PaperSnapshot:
    return PaperSnapshot(
        as_of=day,
        created_at="2026-11-21T12:00:00+05:30",
        capital=capital,
        engine="all_weather_defender",
        regime="normal",
        risk_score=7,
        allocation={"weights": weights, "allowed": True},
        sleeve_prices=prices,
        warnings=(),
        note="test",
    )


def p(nifty: float = 100.0, gold: float = 100.0, debt: float = 1.0, cash: float = 1.0) -> dict:
    return {"nifty50": nifty, "gold_bees": gold, "debt": debt, "cash": cash}


def test_hold_marks() -> None:
    s0 = snap("2026-11-19", {"nifty50": 0.5, "cash": 0.5}, p(100))
    s1 = snap("2026-11-20", {"nifty50": 0.5, "cash": 0.5}, p(110))
    r = evaluate_snapshots([s0, s1], cost_bps={"nifty50": 0, "gold_bees": 0, "debt": 0, "cash": 0})
    assert abs(r.final_value - 1050) < 1e-9
    assert abs(r.days[1].daily_return - 0.05) < 1e-9
    assert r.days[1].rebalanced is False
    assert r.days[1].target_changed is False
    assert r.rebalances == 1


def test_target_change_executes_next_close() -> None:
    w0 = {"nifty50": 0.5, "cash": 0.5}
    w1 = {"nifty50": 1.0, "cash": 0.0}
    s0 = snap("2026-11-19", w0, p(100))
    s1 = snap("2026-11-20", w1, p(100))
    s2 = snap("2026-11-21", w1, p(100))
    r = evaluate_snapshots([s0, s1, s2], cost_bps={"nifty50": 0, "gold_bees": 0, "debt": 0, "cash": 0})
    assert r.days[1].target_changed is True
    assert r.days[1].rebalanced is False
    assert r.days[2].rebalanced is True
    assert r.days[2].value == 1000
    assert r.rebalances == 2


def test_target_revert_cancels_pending() -> None:
    w0 = {"nifty50": 0.5, "cash": 0.5}
    w1 = {"nifty50": 1.0, "cash": 0.0}
    s0 = snap("2026-11-19", w0, p(100))
    s1 = snap("2026-11-20", w1, p(100))
    s2 = snap("2026-11-21", w0, p(100))
    r = evaluate_snapshots([s0, s1, s2], cost_bps={"nifty50": 0, "gold_bees": 0, "debt": 0, "cash": 0})
    assert r.days[2].rebalanced is False
    assert r.days[2].target_changed is False


def test_costs_reduce_value() -> None:
    s0 = snap("2026-11-19", {"nifty50": 0.5, "cash": 0.5}, p(100))
    s1 = snap("2026-11-20", {"nifty50": 0.5, "cash": 0.5}, p(110))
    r = evaluate_snapshots([s0, s1])
    assert r.total_costs > 0
    assert r.final_value < 1050
    assert r.days[0].value < 1000


def test_missing_price_rejected() -> None:
    s0 = snap("2026-11-19", {"nifty50": 0.5, "cash": 0.5}, {"cash": 1.0})
    try:
        evaluate_snapshots([s0])
    except ValueError:
        return
    raise AssertionError("missing price accepted")


def test_extra_sleeve_rejected() -> None:
    s0 = snap("2026-11-19", {"nifty50": 0.5, "crypto": 0.5}, p(100))
    try:
        evaluate_snapshots([s0])
    except ValueError as exc:
        assert "unsupported" in str(exc)
        return
    raise AssertionError("unsupported sleeve accepted")


def main() -> None:
    print("paper book:")
    ok("hold marks", test_hold_marks)
    ok("target change next close", test_target_change_executes_next_close)
    ok("target revert cancels", test_target_revert_cancels_pending)
    ok("costs reduce value", test_costs_reduce_value)
    ok("missing price rejected", test_missing_price_rejected)
    ok("extra sleeve rejected", test_extra_sleeve_rejected)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
