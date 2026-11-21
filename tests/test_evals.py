"""Offline regression tests for the eval scripts. No model calls, no quota.

The bug these lock down: `fact_eval.py` built RAG context into `taught_ctx`
but passed an undefined `pack_body` to the taught call. The script crashed
with NameError, and the documented result could not be reproduced from the
committed code. `hard_eval.py` passed no context at all, so its "taught"
condition was byte-identical to baseline.

    python3 tests/test_evals.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval import fact_eval, hard_eval  # noqa: E402

PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


class Capture:
    """Records the user prompt and returns one empty answer per question."""

    def __init__(self) -> None:
        self.users: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.users.append(user)
        n = user.count("In the course section")
        return json.dumps({str(i): "" for i in range(1, n + 1)})


class Echo:
    def __init__(self) -> None:
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.user = user
        return json.dumps({"1": "x"})


def test_fact_eval_taught_uses_rag() -> None:
    cap = Capture()
    old_get, old_sleep, old_argv = fact_eval.get_adapter, fact_eval.time.sleep, sys.argv
    fact_eval.get_adapter = lambda cfg, name=None: cap  # noqa: ARG005
    fact_eval.time.sleep = lambda _s: None
    sys.argv = ["fact_eval.py", "--n", "2"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fact_eval.main()
    finally:
        fact_eval.get_adapter, fact_eval.time.sleep, sys.argv = old_get, old_sleep, old_argv

    assert len(cap.users) == 2, f"expected 2 calls, got {len(cap.users)}"
    assert "Course reference material" not in cap.users[0], "baseline got context"
    assert "Course reference material" in cap.users[1], "taught got no context"
    assert "### " in cap.users[1], "taught context has no RAG chunks"


def test_fact_eval_ask_injects_pack() -> None:
    e = Echo()
    fact_eval.ask(e, ["What is X?"], pack="PACK-CONTENT")
    assert "PACK-CONTENT" in e.user, "pack not injected"


def test_hard_eval_ask_injects_pack() -> None:
    e = Echo()
    hard_eval.ask(e, ["The value is ____."], pack="PACK-CONTENT")
    assert "PACK-CONTENT" in e.user, "pack not injected"


def main() -> None:
    print("eval scripts inject the taught context:")
    ok("fact_eval taught call carries RAG chunks", test_fact_eval_taught_uses_rag)
    ok("fact_eval.ask injects a pack", test_fact_eval_ask_injects_pack)
    ok("hard_eval.ask injects a pack", test_hard_eval_ask_injects_pack)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
