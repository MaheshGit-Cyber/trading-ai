#!/usr/bin/env python3
"""Agent permission-boundary tests."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.permissions import check, require  # noqa: E402

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


def test_allowed() -> None:
    for action in ("read_web", "search_web", "append_memory", "register_hypothesis"):
        assert check(action).allowed, action


def test_denied() -> None:
    for action in ("place_order", "transfer_money", "promote_strategy", "bypass_risk_gate"):
        assert not check(action).allowed, action
        try:
            require(action)
        except PermissionError:
            continue
        raise AssertionError(f"require accepted {action}")


def test_unknown_default_deny() -> None:
    assert not check("do_magic").allowed


def main() -> None:
    print("agent permissions:")
    ok("allowed research powers", test_allowed)
    ok("denied execution powers", test_denied)
    ok("unknown default deny", test_unknown_default_deny)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
