"""Contract tests. These are the deterministic gate -- run before trusting output.

    python3 tests/test_schema.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import schema  # noqa: E402

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


def expect_error(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        FAIL += 1
        print(f"  FAIL  {name}: expected SchemaError, got none")
    except schema.SchemaError:
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: wrong exception {type(e).__name__}: {e}")


RULES = {
    "version": 1, "min_rr": 2.0, "max_position_pct": 2.0,
    "evidence_weights": {"momentum": 1.0, "trend": 1.0, "structure": 1.0,
                         "volume": 1.0, "regime": 1.0},
    "devils_advocate": "mandatory",
    "learning": {"auto_learn": False},
}

GOOD_EV = {
    "symbol": "RELIANCE",
    "direction": "up",
    "regime": "trend",
    "confidence_band": "medium",
    "scores": {"momentum": 3, "trend": 3, "structure": 2, "volume": 2, "regime": 3},
    "weighted_total": 13,
    "devils_advocate": "The breakout follows a sector-wide move; if the index "
                       "reverses this fails first and the stop is only 2.5% away.",
    "notes": "volume expansion confirmed",
}


def main() -> None:
    print("rules:")
    ok("valid rules accepted", lambda: schema.validate_rules(RULES))
    expect_error("auto_learn=true rejected",
                 lambda: schema.validate_rules({**RULES, "learning": {"auto_learn": True}}))
    expect_error("missing weight rejected",
                 lambda: schema.validate_rules({**RULES, "evidence_weights": {"momentum": 1.0}}))

    print("evidence:")
    ok("valid evidence accepted", lambda: schema.validate_evidence(GOOD_EV, RULES))

    def _band_high():
        ev = schema.validate_evidence(
            {**GOOD_EV, "scores": {k: 4 for k in schema.SCORE_KEYS},
             "weighted_total": 20, "confidence_band": None}, RULES)
        assert ev["confidence_band"] == "high", ev["confidence_band"]
    ok("band high computed from weighted_total", _band_high)

    def _band_low():
        ev = schema.validate_evidence(
            {**GOOD_EV, "scores": {k: 1 for k in schema.SCORE_KEYS},
             "weighted_total": 5, "confidence_band": None}, RULES)
        assert ev["confidence_band"] == "low", ev["confidence_band"]
    ok("band low computed from weighted_total", _band_low)

    def _band_override():
        ev = schema.validate_evidence({**GOOD_EV, "confidence_band": "high"}, RULES)
        assert ev["confidence_band"] == "medium", ev["confidence_band"]
        assert ev.get("_band_overridden") == "high", ev.get("_band_overridden")
    ok("model band disagreement recorded, not honoured", _band_override)

    expect_error("generic devil's advocate rejected",
                 lambda: schema.validate_evidence(
                     {**GOOD_EV, "devils_advocate": "Markets can go down."}, RULES))
    expect_error("inverted band thresholds rejected",
                 lambda: schema.validate_rules(
                     {**RULES, "band_thresholds": {"high": 0.4, "medium": 0.6}}))

    expect_error("wrong weighted_total rejected",
                 lambda: schema.validate_evidence({**GOOD_EV, "weighted_total": 99}, RULES))
    expect_error("score out of range rejected",
                 lambda: schema.validate_evidence(
                     {**GOOD_EV, "scores": {**GOOD_EV["scores"], "trend": 9},
                      "weighted_total": 19}, RULES))
    expect_error("missing devil's advocate rejected",
                 lambda: schema.validate_evidence({**GOOD_EV, "devils_advocate": "ok"}, RULES))
    expect_error("empty direction rejected",
                 lambda: schema.validate_evidence({**GOOD_EV, "direction": "long"}, RULES))
    expect_error("price target in output rejected",
                 lambda: schema.validate_evidence(
                     {**GOOD_EV, "notes": "target price 1600"}, RULES))
    expect_error("buy instruction rejected",
                 lambda: schema.validate_evidence(
                     {**GOOD_EV, "notes": "buy now before it runs"}, RULES))

    print("memory:")
    ok("event accepted", lambda: schema.validate_memory_line({
        "ts": "2026-11-20T15:30:00+0530", "kind": "event",
        "symbol": "TCS", "evidence": {"scores": {}, "weighted_total": 0}}))
    ok("outcome accepted", lambda: schema.validate_memory_line({
        "ts": "2026-11-27T15:35:00+0530", "kind": "outcome",
        "ref": "x", "r_multiple": 1.4, "verdict": "win"}))
    expect_error("unknown kind rejected",
                 lambda: schema.validate_memory_line({"ts": "t", "kind": "training"}))
    expect_error("outcome without ref rejected",
                 lambda: schema.validate_memory_line({
                     "ts": "t", "kind": "outcome", "r_multiple": 1, "verdict": "win"}))

    print("extract_json:")
    ok("bare object", lambda: schema.extract_json('{"a":1}'))
    ok("fenced object", lambda: schema.extract_json('```json\n{"a":1}\n```'))
    ok("prose wrapped", lambda: schema.extract_json('Here it is: {"a":1} done.'))
    expect_error("no object", lambda: schema.extract_json("no json here"))
    expect_error("unbalanced", lambda: schema.extract_json('{"a": '))

    def _trailing():
        got = schema.extract_json('{"a":1} and some trailing prose')
        assert got == {"a": 1}, f"expected first object, got {got}"
    # Trailing prose is normal LLM behaviour -- take the first balanced
    # object rather than failing. Schema validation is the real gate.
    ok("first object extracted, trailing prose ignored", _trailing)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
