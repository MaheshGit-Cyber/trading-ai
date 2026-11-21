#!/usr/bin/env python3
"""Clock and market-session tests."""

from __future__ import annotations

from datetime import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.clock import IST, market_phase, snapshot, trading_day_status  # noqa: E402

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


def test_format() -> None:
    dt = datetime(2026, 11, 20, 10, 5, 7, 123456, tzinfo=IST)
    s = snapshot(dt, trading_dates={"2026-11-20"})
    assert s.date_ddmmyyyy == "20-11-2026"
    assert s.time_hhmmssmmm == "10:05:07.123"
    assert s.market_phase == "open"
    assert s.weekday == "Friday"
    assert s.trading_day_status == "trading_day"
    assert s.epoch_ms > 0


def test_phases() -> None:
    cases = [
        (datetime(2026, 11, 20, 8, 0, tzinfo=IST), "pre_market"),
        (datetime(2026, 11, 20, 9, 5, tzinfo=IST), "pre_open"),
        (datetime(2026, 11, 20, 9, 15, tzinfo=IST), "open"),
        (datetime(2026, 11, 20, 15, 30, tzinfo=IST), "post_close"),
        (datetime(2026, 11, 20, 17, 0, tzinfo=IST), "closed"),
        (datetime(2026, 11, 21, 10, 0, tzinfo=IST), "weekend"),
    ]
    for dt, expected in cases:
        assert market_phase(dt) == expected, (dt, market_phase(dt))


def test_trading_day_status() -> None:
    dates = {"2026-11-19", "2026-11-20"}
    assert trading_day_status("2026-11-20", dates) == "trading_day"
    assert trading_day_status("2026-11-21", dates) == "weekend"
    assert trading_day_status("2026-11-23", dates) == "unknown_future"
    assert trading_day_status("2026-11-18", dates) == "not_in_data"
    assert trading_day_status("bad", dates) == "invalid_date"


def test_missing_calendar() -> None:
    assert trading_day_status("2026-11-20", set()) == "unknown_no_calendar"


def main() -> None:
    print("agent clock:")
    ok("format", test_format)
    ok("phases", test_phases)
    ok("trading day", test_trading_day_status)
    ok("missing calendar", test_missing_calendar)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
