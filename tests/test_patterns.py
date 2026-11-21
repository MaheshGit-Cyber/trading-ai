#!/usr/bin/env python3
"""Deterministic candlestick pattern tests (stdlib only).

Every pattern in ``memory/knowledge/patterns.json`` has a positive test.
Shape-edge cases (doji vs hammer, pin bar vs hammer, marubozu vs belt hold)
are locked down separately so the dedupe rules cannot silently regress.

    python3 tests/test_patterns.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.patterns import (  # noqa: E402
    Candle,
    PATTERN_IDS,
    detect_all,
    detect_last,
    infer_trend,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS_JSON = os.path.join(ROOT, "memory", "knowledge", "patterns.json")


def c(o: float, h: float, l: float, cl: float, v: float = 1000.0) -> Candle:
    return Candle(o, h, l, cl, v)


def ids(candles, **ctx) -> list[str]:
    return [h.pattern_id for h in detect_all(candles, context=ctx)]


def has(candles, pattern_id: str, **ctx) -> bool:
    return pattern_id in ids(candles, **ctx)


# ---------------------------------------------------------------------------
# Single-candle patterns
# ---------------------------------------------------------------------------


def test_doji():
    assert has([c(100, 101, 99, 100.05)], "doji")


def test_dragonfly_doji():
    assert has([c(100, 100.1, 97, 100.05)], "dragonfly_doji")


def test_gravestone_doji():
    assert has([c(100, 103, 99.9, 100.05)], "gravestone_doji")


def test_hammer():
    assert has([c(100, 101, 95, 101)], "hammer", trend="down")


def test_hanging_man():
    assert has([c(100, 101, 95, 101)], "hanging_man", trend="up")


def test_inverted_hammer():
    assert has([c(100, 105, 100, 101)], "inverted_hammer", trend="down")


def test_shooting_star():
    assert has([c(100, 105, 100, 101)], "shooting_star", trend="up")


def test_bullish_marubozu():
    assert has([c(100, 110, 100, 110)], "bullish_marubozu")


def test_bearish_marubozu():
    assert has([c(110, 110, 100, 100)], "bearish_marubozu")


def test_spinning_top():
    assert has([c(100, 102, 98, 100.5)], "spinning_top")


def test_bullish_pin_bar():
    assert has([c(100, 101.2, 95, 100.8)], "bullish_pin_bar")


def test_bearish_pin_bar():
    assert has([c(100, 105, 99.5, 100.8)], "bearish_pin_bar")


def test_bullish_belt_hold():
    assert has([c(100, 110, 100, 108)], "bullish_belt_hold")


def test_bearish_belt_hold():
    assert has([c(110, 110, 100, 102)], "bearish_belt_hold")


# ---------------------------------------------------------------------------
# Two-candle patterns
# ---------------------------------------------------------------------------


def test_bullish_engulfing():
    assert has([c(105, 106, 99, 100), c(99, 107, 98, 106)], "bullish_engulfing")


def test_bearish_engulfing():
    assert has([c(100, 106, 99, 105), c(106, 107, 98, 99)], "bearish_engulfing")


def test_piercing_line():
    assert has([c(105, 106, 99, 100), c(98, 104, 97, 103)], "piercing_line")


def test_dark_cloud_cover():
    assert has([c(100, 106, 99, 105), c(107, 108, 101, 102)], "dark_cloud_cover")


def test_bullish_harami():
    assert has([c(105, 106, 99, 100), c(101, 104, 100.5, 103)], "bullish_harami")


def test_bearish_harami():
    assert has([c(100, 106, 99, 105), c(104, 105, 101, 102)], "bearish_harami")


def test_tweezer_bottom():
    assert has([c(105, 106, 99, 100), c(99, 104, 99, 103)], "tweezer_bottom")


def test_tweezer_top():
    assert has([c(100, 105, 99, 104), c(104, 105, 100, 101)], "tweezer_top")


def test_inside_bar():
    assert has([c(100, 110, 90, 105), c(103, 107, 95, 100)], "inside_bar")


def test_outside_bar():
    assert has([c(100, 105, 95, 102), c(102, 110, 90, 108)], "outside_bar")


def test_bullish_kicker():
    assert has([c(105, 106, 99, 100), c(107, 115, 106, 114)], "bullish_kicker")


def test_bearish_kicker():
    assert has([c(100, 106, 99, 105), c(98, 99, 90, 91)], "bearish_kicker")


# ---------------------------------------------------------------------------
# Three-candle patterns
# ---------------------------------------------------------------------------


def test_morning_star():
    assert has(
        [c(110, 111, 100, 101), c(99, 100, 98, 99.5), c(100, 109, 99, 108)],
        "morning_star",
    )


def test_evening_star():
    assert has(
        [c(100, 110, 99, 109), c(110, 111, 109, 110.5), c(109, 110, 100, 101)],
        "evening_star",
    )


def test_three_white_soldiers():
    assert has(
        [c(100, 104, 99, 103), c(103, 107, 102, 106), c(106, 110, 105, 109)],
        "three_white_soldiers",
    )


def test_three_black_crows():
    assert has(
        [c(109, 110, 105, 106), c(106, 107, 102, 103), c(103, 104, 99, 100)],
        "three_black_crows",
    )


def test_three_inside_up():
    assert has(
        [c(110, 111, 100, 101), c(102, 108, 101, 107), c(107, 112, 106, 111)],
        "three_inside_up",
    )


def test_three_inside_down():
    assert has(
        [c(100, 110, 99, 109), c(108, 109, 102, 103), c(103, 104, 98, 99)],
        "three_inside_down",
    )


def test_three_outside_up():
    assert has(
        [c(105, 106, 99, 100), c(99, 107, 98, 106), c(106, 110, 105, 109)],
        "three_outside_up",
    )


def test_three_outside_down():
    assert has(
        [c(100, 106, 99, 105), c(106, 107, 98, 99), c(99, 100, 95, 96)],
        "three_outside_down",
    )


def test_abandoned_baby_bullish():
    assert has(
        [c(110, 111, 100, 101), c(98, 99, 97, 98.05), c(101, 109, 100, 108)],
        "abandoned_baby_bullish",
    )


def test_abandoned_baby_bearish():
    assert has(
        [c(100, 109, 99, 108), c(111, 112, 110, 111.05), c(108, 109, 100, 101)],
        "abandoned_baby_bearish",
    )


def test_tri_star():
    assert has(
        [c(100, 101, 99, 100.05), c(100.1, 101, 99, 100.05),
         c(100, 101, 99, 100.05)],
        "tri_star",
    )


# ---------------------------------------------------------------------------
# Negative / edge cases
# ---------------------------------------------------------------------------


def test_negative_doji_requires_small_body():
    assert not has([c(100, 110, 99, 108)], "doji")


def test_negative_hammer_requires_long_lower_wick():
    # Lower wick is only 1x the body, not 2x.
    assert not has([c(100, 102, 98, 101)], "hammer", trend="down")


def test_negative_bullish_engulfing_when_both_bullish():
    assert not has([c(100, 105, 99, 104), c(103, 108, 102, 107)],
                   "bullish_engulfing")


def test_negative_bearish_engulfing_when_both_bearish():
    assert not has([c(105, 106, 99, 100), c(104, 105, 98, 99)],
                   "bearish_engulfing")


def test_negative_morning_star_weak_third_close():
    # Third close 102 is below the first body midpoint (105.5).
    assert not has(
        [c(110, 111, 100, 101), c(99, 100, 98, 99.5), c(100, 105, 99, 102)],
        "morning_star",
    )


def test_negative_tweezer_lows_not_equal():
    assert not has([c(105, 106, 99, 100), c(100, 104, 95, 103)],
                   "tweezer_bottom")


def test_negative_kicker_without_gap():
    assert not has([c(105, 106, 99, 100), c(101, 108, 100, 107)],
                   "bullish_kicker")


# ---------------------------------------------------------------------------
# Dedupe and contract tests
# ---------------------------------------------------------------------------


def test_dedupe_pin_bar_when_hammer_exists():
    result = ids([c(100, 101, 95, 101)], trend="down")
    assert "hammer" in result
    assert "bullish_pin_bar" not in result


def test_dedupe_belt_hold_when_marubozu_exists():
    result = ids([c(100, 110, 100, 110)])
    assert "bullish_marubozu" in result
    assert "bullish_belt_hold" not in result


def test_bullish_engulfing_levels():
    hits = detect_all([c(105, 106, 99, 100), c(99, 107, 98, 106)])
    hit = [h for h in hits if h.pattern_id == "bullish_engulfing"][0]
    assert hit.direction == "bullish"
    assert hit.entry == 107
    assert hit.stop == 98
    assert abs(hit.target1 - 116) < 1e-9
    assert abs(hit.target2 - 125) < 1e-9


def test_bearish_engulfing_levels():
    hits = detect_all([c(100, 106, 99, 105), c(106, 107, 98, 99)])
    hit = [h for h in hits if h.pattern_id == "bearish_engulfing"][0]
    assert hit.direction == "bearish"
    assert hit.entry == 98
    assert hit.stop == 107
    assert abs(hit.target1 - 89) < 1e-9
    assert abs(hit.target2 - 80) < 1e-9


def test_detect_last_only_last_bar():
    candles = [c(110, 111, 100, 101), c(99, 100, 98, 99.5),
               c(100, 109, 99, 108)]
    hits = detect_last(candles, context={"trend": "down"})
    assert hits, "expected at least one hit on the last bar"
    assert all(h.bar_index == len(candles) - 1 for h in hits)
    assert any(h.pattern_id == "morning_star" for h in hits)


def test_zero_range_does_not_crash():
    result = ids([c(100, 100, 100, 100)])
    assert "doji" in result


def test_invalid_candle_rejected():
    bad = [
        (100, 99, 101, 100),   # high < low
        (100, 101, 99, 102),   # high < close
        (100, 101, 99, 98),    # low > close
    ]
    for args in bad:
        try:
            Candle(*args)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid candle {args}")


def test_trend_inference():
    up = [c(100, 101, 99, 100), c(101, 102, 100, 101),
          c(102, 103, 101, 102), c(103, 104, 102, 103)]
    down = [c(103, 104, 102, 103), c(102, 103, 101, 102),
            c(101, 102, 100, 101), c(100, 101, 99, 100)]
    sideways = [c(100, 101, 99, 100), c(110, 111, 109, 110),
                c(100, 101, 99, 100), c(101, 102, 100, 101)]
    assert infer_trend(up) == "up"
    assert infer_trend(down) == "down"
    assert infer_trend(sideways) == "range"


def test_volume_context_raises_confidence():
    candles = [c(100, 101, 95, 101)]
    base = [h for h in detect_all(candles, context={"trend": "down"})
            if h.pattern_id == "hammer"][0]
    boosted = [h for h in detect_all(
        candles, context={"trend": "down", "volume_ratio": 2.0})
        if h.pattern_id == "hammer"][0]
    assert boosted.confidence > base.confidence


def test_patterns_json_schema():
    with open(PATTERNS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    patterns = data["patterns"]
    assert len(patterns) >= 30, f"only {len(patterns)} patterns"
    json_ids = {p["id"] for p in patterns}
    assert len(json_ids) == len(patterns), "duplicate pattern ids"
    assert json_ids == PATTERN_IDS, (
        f"json/code mismatch: {sorted(json_ids ^ PATTERN_IDS)}"
    )
    required = {
        "id", "name", "category", "direction", "bars", "structure",
        "psychology", "signal", "entry", "stop", "target1", "target2",
        "reliability", "context_required", "confirmation", "false_signal",
        "notes",
    }
    for p in patterns:
        missing = required - set(p)
        assert not missing, f"{p.get('id')} missing {sorted(missing)}"
        assert p["direction"] in {"bullish", "bearish", "neutral"}
        assert p["category"] in {"single_candle", "two_candle", "three_candle"}
        assert p["bars"] in {1, 2, 3}
        assert p["reliability"] in {"low", "medium", "high"}
        assert isinstance(p["context_required"], list) and p["context_required"]
        assert isinstance(p["confirmation"], list) and p["confirmation"]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_doji,
    test_dragonfly_doji,
    test_gravestone_doji,
    test_hammer,
    test_hanging_man,
    test_inverted_hammer,
    test_shooting_star,
    test_bullish_marubozu,
    test_bearish_marubozu,
    test_spinning_top,
    test_bullish_pin_bar,
    test_bearish_pin_bar,
    test_bullish_belt_hold,
    test_bearish_belt_hold,
    test_bullish_engulfing,
    test_bearish_engulfing,
    test_piercing_line,
    test_dark_cloud_cover,
    test_bullish_harami,
    test_bearish_harami,
    test_tweezer_bottom,
    test_tweezer_top,
    test_inside_bar,
    test_outside_bar,
    test_bullish_kicker,
    test_bearish_kicker,
    test_morning_star,
    test_evening_star,
    test_three_white_soldiers,
    test_three_black_crows,
    test_three_inside_up,
    test_three_inside_down,
    test_three_outside_up,
    test_three_outside_down,
    test_abandoned_baby_bullish,
    test_abandoned_baby_bearish,
    test_tri_star,
    test_negative_doji_requires_small_body,
    test_negative_hammer_requires_long_lower_wick,
    test_negative_bullish_engulfing_when_both_bullish,
    test_negative_bearish_engulfing_when_both_bearish,
    test_negative_morning_star_weak_third_close,
    test_negative_tweezer_lows_not_equal,
    test_negative_kicker_without_gap,
    test_dedupe_pin_bar_when_hammer_exists,
    test_dedupe_belt_hold_when_marubozu_exists,
    test_bullish_engulfing_levels,
    test_bearish_engulfing_levels,
    test_detect_last_only_last_bar,
    test_zero_range_does_not_crash,
    test_invalid_candle_rejected,
    test_trend_inference,
    test_volume_context_raises_confidence,
    test_patterns_json_schema,
]


def main() -> None:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001 - test runner reports, not hides
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")
    print(f"patterns: {passed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
