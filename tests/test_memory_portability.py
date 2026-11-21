"""Proof that memory is model-independent.

The claim under test: "whatever AI model you swap in, this memory is its
own memory."

What is actually verifiable without spending quota:
  1. The prompt is built from files only -- provider is chosen AFTER the
     prompt exists, so the bytes sent are identical for every provider.
  2. rules.json, memory.jsonl and the RAG chunks all appear in the prompt.
  3. Adding a memory event grows the prompt (memory is really read, not
     decorative).

What is NOT verifiable here: whether a different model *obeys* the memory.
A 1.7B local model and a frontier model read the same text and behave
differently. Same memory, different competence.

    python3 tests/test_memory_portability.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import adapters.base as base  # noqa: E402
from engine import evidence, paths  # noqa: E402

PASS = 0
FAIL = 0

GOOD_EVIDENCE = {
    "symbol": "RELIANCE",
    "direction": "up",
    "regime": "trend",
    "confidence_band": "medium",
    "scores": {"momentum": 1, "trend": 1, "structure": 1, "volume": 1, "regime": 1},
    "weighted_total": 5,
    "devils_advocate": "Single synthetic snapshot, no outcome history, so the "
                       "signal is unproven until quarantined samples accumulate.",
    "notes": "portability test",
}

LAYER3 = {
    "demo": True, "symbol": "RELIANCE", "horizon": "5d", "direction": "up",
    "features": ["close_above_200dma", "volume_expansion"], "regime": "trend",
}


class Capture:
    """Stands in for any provider. Records exactly what the model would see."""

    def __init__(self) -> None:
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.system = system
        self.user = user
        return json.dumps(GOOD_EVIDENCE)


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def run_with(provider_name: str) -> Capture:
    cap = Capture()
    original = base.get_adapter
    base.get_adapter = lambda cfg, name=None: cap  # noqa: ARG005
    try:
        evidence.run(LAYER3, provider=provider_name, verbose=False)
    finally:
        base.get_adapter = original
    return cap


def main() -> None:
    rules = evidence.load_rules()
    events = evidence.load_memory()
    print(f"rules v{rules['version']} · {len(events)} memory event(s)\n")

    print("same-symbol memory is prioritised:")

    def _same_symbol_survives():
        evs = [
            {"ts": f"t{i}", "kind": "note",
             "symbol": "RELIANCE" if i == 0 else f"OTHER{i}",
             "evidence": {"scores": {}, "weighted_total": 0}}
            for i in range(7)
        ]
        got = evidence.memory_hits(evs, "RELIANCE", k=6)
        assert len(got) == 6, len(got)
        assert any(e["symbol"] == "RELIANCE" for e in got), "same-symbol event dropped"
    ok("same-symbol event survives six others", _same_symbol_survives)

    def _same_symbol_fills():
        evs = [
            {"ts": f"t{i}", "kind": "note",
             "symbol": "RELIANCE" if i < 8 else f"OTHER{i}",
             "evidence": {"scores": {}, "weighted_total": 0}}
            for i in range(16)
        ]
        got = evidence.memory_hits(evs, "RELIANCE", k=6)
        assert len(got) == 6 and all(e["symbol"] == "RELIANCE" for e in got)
    ok("same-symbol tail fills every slot", _same_symbol_fills)

    print()

    cli = run_with("opencode_cli")
    local = run_with("local_offline")
    paid = run_with("paid_api")

    print("same bytes for every provider:")
    ok("opencode_cli == local_offline", lambda: (
        cli.user == local.user or (_ for _ in ()).throw(AssertionError("prompts differ"))))
    ok("local_offline == paid_api", lambda: (
        local.user == paid.user or (_ for _ in ()).throw(AssertionError("prompts differ"))))
    ok("system prompt identical", lambda: (
        cli.system == local.system == paid.system or
        (_ for _ in ()).throw(AssertionError("system prompts differ"))))

    print("\nmemory is actually injected:")
    ok("rules version present", lambda: (
        f'"version": {rules["version"]}' in cli.user or
        (_ for _ in ()).throw(AssertionError("rules missing from prompt"))))
    ok("rules min_rr present", lambda: (
        f'"min_rr": {rules["min_rr"]}' in cli.user or
        (_ for _ in ()).throw(AssertionError("min_rr missing"))))

    if events:
        sym = events[-1].get("symbol", "")
        ok(f"last memory event ({sym}) present", lambda: (
            sym in cli.user or
            (_ for _ in ()).throw(AssertionError("memory event missing"))))
    else:
        print("  SKIP  no memory events yet")

    ok("RAG chunks present", lambda: (
        "Retrieved knowledge" in cli.user and
        ("::" in cli.user) or
        (_ for _ in ()).throw(AssertionError("no RAG block"))))
    ok("devil's-advocate rule present", lambda: (
        "Devil" in cli.system or
        (_ for _ in ()).throw(AssertionError("no devil's advocate rule"))))

    print("\nmemory grows the prompt (not decorative):")
    before = len(cli.user)
    probe = {
        "ts": "2026-11-20T23:59:59+0530", "kind": "note",
        "symbol": "PORTABILITY_PROBE",
        "evidence": {"scores": {}, "weighted_total": 0},
    }
    evidence.append_memory(probe)
    try:
        after_cap = run_with("opencode_cli")
        ok("prompt grows after append", lambda: (
            len(after_cap.user) > before or
            (_ for _ in ()).throw(AssertionError(
                f"prompt did not grow: {before} -> {len(after_cap.user)}"))))
        ok("new event visible to model", lambda: (
            "PORTABILITY_PROBE" in after_cap.user or
            (_ for _ in ()).throw(AssertionError("probe not in prompt"))))
    finally:
        # Remove the probe line so the log stays clean. This is the ONE
        # sanctioned rewrite: a test artifact, not a real event.
        with open(paths.MEMORY, encoding="utf-8") as f:
            lines = [ln for ln in f if "PORTABILITY_PROBE" not in ln]
        with open(paths.MEMORY, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("  (probe line removed)")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
