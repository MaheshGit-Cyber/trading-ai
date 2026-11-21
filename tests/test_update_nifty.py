#!/usr/bin/env python3
"""Nifty updater tests: append, blank-fill, mismatch refusal, no partial day."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location(
    "update_nifty", os.path.join(ROOT, "jobs", "update_nifty_from_yahoo.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

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


HEADER = "date,open,high,low,close,volume\n"


def _write(path: str, body: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(body)


def _row(day: str, close: str = "100") -> dict:
    return {
        "date": day,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": "0",
    }


def test_append_and_blank_fill() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nifty.csv")
        _write(
            path,
            "2026-11-18,100,100,100,100,0\n"
            "2026-11-19,101,101,101,101,0\n"
            "2026-11-20,102,102,102,,0\n",
        )
        fetched = [_row("2026-11-19", "101"), _row("2026-11-20", "102"),
                   _row("2026-11-21", "103")]
        result = mod.update_csv(
            path, fetched, now=datetime(2026, 11, 21, 16, 30, tzinfo=mod.IST)
        )
        assert result["added"] == 1 and result["filled"] == 1
        assert result["last"] == "2026-11-21"


def test_refuse_overwrite_and_partial_day() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nifty.csv")
        _write(path, "2026-11-19,100,100,100,100,0\n")
        try:
            mod.update_csv(
                path, [_row("2026-11-19", "101")],
                now=datetime(2026, 11, 21, 16, 30, tzinfo=mod.IST),
            )
        except ValueError as exc:
            assert "close mismatch" in str(exc)
        else:
            raise AssertionError("different close overwritten")
        result = mod.update_csv(
            path, [_row("2026-11-21", "103")],
            now=datetime(2026, 11, 21, 15, 0, tzinfo=mod.IST),
        )
        assert result["added"] == 0
        assert result["last"] == "2026-11-19"


def main() -> None:
    print("nifty updater:")
    ok("append and blank fill", test_append_and_blank_fill)
    ok("overwrite refusal and partial-day skip", test_refuse_overwrite_and_partial_day)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
