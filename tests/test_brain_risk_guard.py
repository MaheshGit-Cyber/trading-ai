#!/usr/bin/env python3
"""Risk guard tests: sizing, ADV, staleness, circuits, corporate actions.

    python3 tests/test_brain_risk_guard.py
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import csv
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import ActionEvent, PriceBar, load_actions  # noqa: E402
from brain.risk_guard import (  # noqa: E402
    build_trade_plan,
    event_flags,
    freshness_flags,
    size_position,
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


def _bars(n: int = 30, *, last_day: str = "2026-11-19") -> list[PriceBar]:
    end = date.fromisoformat(last_day)
    first = end - timedelta(days=n - 1)
    rows = []
    for i in range(n):
        close = 100.0 * (1.001 ** i)
        rows.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol="TEST",
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10000,
                turnover_lacs=1000.0,
                raw_close=close,
                deliv_per=50.0,
                isin="INE000A01001",
            )
        )
    return rows


def test_risk_and_position_caps() -> None:
    s = size_position(1_000_000, 100, 95, adv20_value=10_000_000)
    assert s.quantity == 2000, s.quantity
    assert abs(s.actual_risk - 10_000) < 1e-6
    assert abs(s.actual_risk_pct - 0.01) < 1e-9
    assert s.binding_constraint in ("risk", "position")


def test_adv_cap_binds() -> None:
    s = size_position(1_000_000, 100, 95, adv20_value=1_000_000)
    assert s.quantity == 500, s.quantity
    assert s.binding_constraint == "adv"
    assert s.position_value <= 50_000


def test_stop_above_entry_rejected() -> None:
    try:
        size_position(1_000_000, 100, 101)
    except ValueError:
        return
    raise AssertionError("stop above entry accepted")


def test_risk_above_two_percent_rejected() -> None:
    try:
        size_position(1_000_000, 100, 95, risk_per_trade_pct=0.03)
    except ValueError:
        return
    raise AssertionError("3% risk per trade accepted")


def test_plan_allows_clean_trade() -> None:
    bars = _bars()
    plan = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=bars[-1].close,
        stop=bars[-1].close * 0.95,
        as_of=bars[-1].date,
        bars=bars,
        actions=[],
        adv20_value=10_000_000,
    )
    assert plan.allowed is True, plan.to_dict()
    assert plan.sizing.quantity > 0
    assert not any(f.severity.value == "block" for f in plan.flags)


def test_locked_circuit_blocks() -> None:
    bars = _bars()
    last = replace(
        bars[-1],
        open=bars[-1].close,
        high=bars[-1].close,
        low=bars[-1].close,
    )
    bars = bars[:-1] + [last]
    plan = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=last.close,
        stop=last.close * 0.95,
        as_of=last.date,
        bars=bars,
        adv20_value=10_000_000,
    )
    assert plan.allowed is False
    assert any(f.code == "circuit_locked" for f in plan.flags)


def test_stale_data_blocks() -> None:
    bars = _bars()
    plan = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=bars[-1].close,
        stop=bars[-1].close * 0.95,
        as_of="2026-12-10",
        bars=bars,
        adv20_value=10_000_000,
    )
    assert plan.allowed is False
    assert any(f.code == "stale_data" for f in plan.flags)


def test_low_liquidity_blocks() -> None:
    bars = _bars()
    plan = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=bars[-1].close,
        stop=bars[-1].close * 0.95,
        as_of=bars[-1].date,
        bars=bars,
        adv20_value=1_000_000,
    )
    assert plan.allowed is False
    assert any(f.code == "low_liquidity" for f in plan.flags)


def test_split_event_blocks_and_agm_warns() -> None:
    bars = _bars()
    split = ActionEvent(
        ex_date="2026-11-24",
        symbol="TEST",
        isin="INE000A01001",
        source="NSE",
        action="SPLIT",
        purpose="Stock split",
    )
    plan = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=bars[-1].close,
        stop=bars[-1].close * 0.95,
        as_of=bars[-1].date,
        bars=bars,
        actions=[split],
        adv20_value=10_000_000,
    )
    assert plan.allowed is False
    assert any(f.code == "event_split" for f in plan.flags)

    agm = ActionEvent(
        ex_date="2026-11-24",
        symbol="TEST",
        isin="INE000A01001",
        source="NSE",
        action="UNKNOWN",
        purpose="Annual General Meeting",
    )
    plan2 = build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=bars[-1].close,
        stop=bars[-1].close * 0.95,
        as_of=bars[-1].date,
        bars=bars,
        actions=[agm],
        adv20_value=10_000_000,
    )
    assert plan2.allowed is True
    assert any(f.code == "event_agm" for f in plan2.flags)


def test_action_window_and_dedupe() -> None:
    action = ActionEvent(
        ex_date="2026-11-24",
        symbol="TEST",
        isin="INE000A01001",
        source="NSE",
        action="BONUS",
        purpose="Bonus 1:1",
    )
    flags = event_flags([action, action], "2026-11-19", horizon_days=10)
    assert len(flags) == 2, len(flags)  # dedupe happens in build_trade_plan
    assert all(f.severity.value == "block" for f in flags)
    outside = event_flags([action], "2026-11-19", horizon_days=2)
    assert outside == []


def test_freshness_weekend_warns_not_blocks() -> None:
    flags = freshness_flags("2026-11-19", "2026-11-21")
    assert len(flags) == 1
    assert flags[0].severity.value == "warn"


def test_load_actions_filters_and_isin_fallback() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", newline="", delete=False
    ) as f:
        path = f.name
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "ex_date",
                "symbol",
                "scrip_code",
                "isin",
                "face_val",
                "action",
                "ratio_a",
                "ratio_b",
                "old_fv",
                "new_fv",
                "issue_price",
                "factor",
                "purpose",
            ]
        )
        w.writerow(
            ["NSE", "2026-11-24", "TEST", "", "INE000A01001", "", "SPLIT", "", "", "", "", "", "", "split"]
        )
        w.writerow(
            ["BSE", "2026-11-25", "TEST", "", "", "", "UNKNOWN", "", "", "", "", "", "", "AGM"]
        )
        w.writerow(
            ["NSE", "2026-12-20", "TEST", "", "INE000A01001", "", "BONUS", "", "", "", "", "", "", "later"]
        )
    try:
        rows = load_actions(
            path,
            as_of="2026-11-19",
            horizon_days=10,
            symbol="TEST",
            isin="INE000A01001",
        )
        assert len(rows) == 2, rows
        assert rows[0].action == "SPLIT"
        assert rows[1].action == "UNKNOWN"
    finally:
        os.unlink(path)


def main() -> None:
    print("risk guard:")
    ok("risk and position caps", test_risk_and_position_caps)
    ok("ADV cap binds", test_adv_cap_binds)
    ok("stop above entry rejected", test_stop_above_entry_rejected)
    ok("risk above 2% rejected", test_risk_above_two_percent_rejected)
    ok("clean trade allowed", test_plan_allows_clean_trade)
    ok("locked circuit blocks", test_locked_circuit_blocks)
    ok("stale data blocks", test_stale_data_blocks)
    ok("low liquidity blocks", test_low_liquidity_blocks)
    ok("split blocks / AGM warns", test_split_event_blocks_and_agm_warns)
    ok("event window and dedupe input", test_action_window_and_dedupe)
    ok("weekend freshness warns", test_freshness_weekend_warns_not_blocks)
    ok("actions loader filters", test_load_actions_filters_and_isin_fallback)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
