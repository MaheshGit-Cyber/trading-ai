#!/usr/bin/env python3
"""Strategy registry and frozen gate tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.strategy_lab import (  # noqa: E402
    StrategyRegistry,
    StrategySpec,
    evaluate_gates,
    evaluate_promotion,
    gate_summary,
)

PASS = 0
FAIL = 0

GOOD = {
    "oos_expectancy_r": 0.20,
    "trades": 150,
    "walk_forward_windows": 4,
    "costs_doubled_expectancy_r": 0.05,
    "research_max_drawdown_pct": 25.0,
    "product_max_drawdown_pct": 18.0,
    "calmar": 0.90,
    "nifty_excess_cagr_pp": 6.0,
    "recent_years_positive": True,
}


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


def spec(sid: str = "s1") -> StrategySpec:
    return StrategySpec(
        strategy_id=sid,
        name="Test family",
        family="mean_reversion",
        hypothesis="A liquidity shock in large caps mean-reverts after two sessions.",
        universe="Nifty 100",
        timeframe="daily",
        entry_rule="Enter after a two-session drawdown with no new low.",
        exit_rule="Exit at 2R or after ten sessions.",
        risk_rule="1% risk; 20% position cap; 5% ADV cap.",
        created_at="2026-11-21T12:00:00+05:30",
    )


def test_gate_pass_and_promotion() -> None:
    results = evaluate_gates(GOOD)
    summary = gate_summary(results)
    assert summary["all_passed"], summary
    promoted = evaluate_promotion({**GOOD, "paper_months": 3})
    assert gate_summary(promoted)["all_passed"]


def test_fail_is_fail() -> None:
    bad = dict(GOOD)
    bad["trades"] = 40
    results = evaluate_gates(bad)
    summary = gate_summary(results)
    assert not summary["all_passed"]
    assert "trades" in summary["failed"]


def test_registry_never_auto_approves() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = StrategyRegistry(os.path.join(d, "s.jsonl"))
        s = spec()
        reg.register(s)
        try:
            reg.register(s)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate registered")
        result = reg.record_result("s1", GOOD)
        assert result["status"] == "gate_passed"
        assert result["status"] != "approved"
        latest = reg.latest()["s1"]
        assert latest["status"] == "gate_passed"


def test_forbidden_certainty() -> None:
    with tempfile.TemporaryDirectory() as d:
        bad = spec("s2")
        try:
            StrategySpec(**{**bad.to_dict(), "hypothesis": "Guaranteed 100% sure shot strategy."})
        except ValueError:
            return
    raise AssertionError("certainty language accepted")


def main() -> None:
    print("strategy lab:")
    ok("gate pass and promotion", test_gate_pass_and_promotion)
    ok("fail is fail", test_fail_is_fail)
    ok("registry never auto-approves", test_registry_never_auto_approves)
    ok("forbidden certainty", test_forbidden_certainty)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
