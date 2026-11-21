#!/usr/bin/env python3
"""Daily paper runner safety tests (dry-run; no network, no ledger writes)."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "jobs", "daily_paper_refresh.py")
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


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "--no-update-nifty", "--dry-run", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_recorded_is_noop() -> None:
    p = run("--date", "2026-11-20")
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "already recorded" in p.stdout


def test_future_refused() -> None:
    p = run("--date", "2026-11-21")
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "after latest Nifty bar" in p.stdout


def test_non_session_refused() -> None:
    p = run("--date", "2026-11-15")
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "not a Nifty session" in p.stdout


def main() -> None:
    print("daily paper runner:")
    ok("recorded no-op", test_recorded_is_noop)
    ok("future refused", test_future_refused)
    ok("non-session refused", test_non_session_refused)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
