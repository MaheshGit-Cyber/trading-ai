#!/usr/bin/env python3
"""Append-only agent memory tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.memory import AgentMemory  # noqa: E402

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


def test_append_read() -> None:
    with tempfile.TemporaryDirectory() as d:
        mem = AgentMemory(os.path.join(d, "m.jsonl"))
        mem.append("news", "SEBI circular", {"risk": "low"}, source="sebi.gov.in", tags=["SEBI"])
        mem.append("lesson", "Do not trade headlines", {"reason": "noise"}, tags=["discipline"])
        events = mem.read()
        assert len(events) == 2
        assert events[0].kind == "news"
        assert events[1].tags == ("discipline",)
        assert mem.by_tag("sebi")[0].summary == "SEBI circular"


def test_append_only() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.jsonl")
        mem = AgentMemory(path)
        mem.append("research", "first")
        with open(path, encoding="utf-8") as f:
            before = f.read()
        mem.append("research", "second")
        with open(path, encoding="utf-8") as f:
            after = f.read()
        assert after.startswith(before)
        assert len(after.splitlines()) == 2


def test_bad_kind_and_corrupt() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.jsonl")
        mem = AgentMemory(path)
        try:
            mem.append("unknown", "x")
        except ValueError:
            pass
        else:
            raise AssertionError("bad kind accepted")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not-json}\n")
        try:
            mem.read()
        except ValueError as exc:
            assert "corrupt" in str(exc)
        else:
            raise AssertionError("corrupt line ignored")


def main() -> None:
    print("agent memory:")
    ok("append/read", test_append_read)
    ok("append-only", test_append_only)
    ok("bad kind/corrupt", test_bad_kind_and_corrupt)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
