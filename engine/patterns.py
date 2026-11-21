"""Deterministic candlestick pattern detection.

No model calls, no external dependencies. Patterns are detected from OHLC
arithmetic only; the LLM layer explains a hit, it never invents one.

The same shape can mean different things depending on where it appears:
a long lower wick is a *hammer* after a decline and a *hanging man* after
an advance. ``detect_all`` therefore resolves a trend context for every
pattern (explicit ``context["trend"]`` wins; otherwise a 20-bar SMA/slope
is inferred from bars *before* the pattern).

The companion knowledge file is ``memory/knowledge/patterns.json``. That
file teaches the explanation layer what a hit means; this module decides
whether the hit exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

EPS = 1e-9

# Shape thresholds. Kept as named constants so tests and the knowledge file
# can refer to the same numbers.
DOJI_BODY_RATIO = 0.10
LONG_WICK_RATIO = 2.0
SMALL_WICK_RATIO = 0.30
STRONG_BODY_RATIO = 0.50
MARUBOZU_BODY_RATIO = 0.90
PIN_WICK_RATIO = 0.66
PIN_BODY_RATIO = 0.34
BELT_BODY_RATIO = 0.70
HARAMI_BODY_RATIO = 0.60
STAR_SMALL_BODY_RATIO = 0.30
DOJI_WICK_RATIO = 0.60
DOJI_FLAT_WICK_RATIO = 0.10


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLC bar. Volume is optional and only used for confidence."""

    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.high < self.low - EPS:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close) - EPS:
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close) + EPS:
            raise ValueError("low must be <= open and close")


@dataclass(frozen=True, slots=True)
class PatternHit:
    """A detected pattern with a ready-to-use trade frame.

    ``entry``/``stop``/``target1``/``target2`` are 0.0 for neutral patterns
    (doji, spinning top, inside/outside bar, tri-star). Neutral means "wait
    for the break", so inventing a direction here would be a false signal.
    """

    pattern_id: str
    name: str
    direction: str  # bullish | bearish | neutral
    bar_index: int
    confidence: float
    entry: float
    stop: float
    target1: float
    target2: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "direction": self.direction,
            "bar_index": self.bar_index,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop": self.stop,
            "target1": self.target1,
            "target2": self.target2,
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def _range(c: Candle) -> float:
    return c.high - c.low


def _safe_range(c: Candle) -> float:
    return max(_range(c), EPS)


def _upper_wick(c: Candle) -> float:
    return c.high - max(c.open, c.close)


def _lower_wick(c: Candle) -> float:
    return min(c.open, c.close) - c.low


def _bullish(c: Candle) -> bool:
    return c.close > c.open + EPS


def _bearish(c: Candle) -> bool:
    return c.close < c.open - EPS


def _is_doji(c: Candle) -> bool:
    return _body(c) <= DOJI_BODY_RATIO * _safe_range(c)


# ---------------------------------------------------------------------------
# Trend / volume context
# ---------------------------------------------------------------------------


def infer_trend(candles: Sequence[Candle], lookback: int = 20) -> str:
    """Return ``up``, ``down`` or ``range`` from a candle window.

    Deliberately simple: last close versus the window mean and the first
    close. No future bars, no indicators that need more history.
    """
    if len(candles) < 3:
        return "range"
    window = list(candles)[-lookback:]
    closes = [c.close for c in window]
    mean = sum(closes) / len(closes)
    last = closes[-1]
    first = closes[0]
    up = last > mean and last > first
    down = last < mean and last < first
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    return "range"


def _trends_for(
    candles: Sequence[Candle], index: int, context: dict
) -> dict[int, str]:
    """Trend *before* a pattern of length 1/2/3 ending at ``index``."""
    explicit = context.get("trend")
    if explicit in ("up", "down", "range"):
        return {1: explicit, 2: explicit, 3: explicit}
    out: dict[int, str] = {}
    for length in (1, 2, 3):
        prior = list(candles)[: max(0, index - length + 1)]
        out[length] = infer_trend(prior)
    return out


def _volume_ratio(
    candles: Sequence[Candle], index: int, context: dict, window: int = 20
) -> float | None:
    explicit = context.get("volume_ratio")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            return None
    if index <= 0 or candles[index].volume <= 0:
        return None
    prior = [c.volume for c in candles[max(0, index - window):index]
             if c.volume > 0]
    if not prior:
        return None
    avg = sum(prior) / len(prior)
    return candles[index].volume / avg if avg > 0 else None


def _confidence(
    base: float,
    *,
    volume_ratio: float | None = None,
    trend_aligned: bool = False,
    strength: float = 0.0,
) -> float:
    score = base
    if volume_ratio is not None and volume_ratio >= 1.5:
        score += 0.08
    if trend_aligned:
        score += 0.07
    score += min(max(strength, 0.0), 0.10)
    return round(min(max(score, 0.05), 0.95), 3)


# ---------------------------------------------------------------------------
# Hit builders
# ---------------------------------------------------------------------------


def _long_hit(
    pattern_id: str,
    name: str,
    index: int,
    high: float,
    low: float,
    confidence: float,
    reasons: list[str],
) -> PatternHit:
    entry = high
    stop = low
    risk = entry - stop
    if risk <= EPS:
        target1 = target2 = entry
    else:
        target1 = entry + risk
        target2 = entry + 2.0 * risk
    return PatternHit(pattern_id, name, "bullish", index, confidence,
                      entry, stop, target1, target2, tuple(reasons))


def _short_hit(
    pattern_id: str,
    name: str,
    index: int,
    high: float,
    low: float,
    confidence: float,
    reasons: list[str],
) -> PatternHit:
    entry = low
    stop = high
    risk = stop - entry
    if risk <= EPS:
        target1 = target2 = entry
    else:
        target1 = entry - risk
        target2 = entry - 2.0 * risk
    return PatternHit(pattern_id, name, "bearish", index, confidence,
                      entry, stop, target1, target2, tuple(reasons))


def _neutral_hit(
    pattern_id: str,
    name: str,
    index: int,
    confidence: float,
    reasons: list[str],
) -> PatternHit:
    return PatternHit(pattern_id, name, "neutral", index, confidence,
                      0.0, 0.0, 0.0, 0.0, tuple(reasons))


# ---------------------------------------------------------------------------
# Single-candle detectors
# ---------------------------------------------------------------------------


def _detect_doji_family(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _safe_range(c)
    body = _body(c)
    if body > DOJI_BODY_RATIO * r:
        return []
    upper, lower = _upper_wick(c), _lower_wick(c)
    if lower >= DOJI_WICK_RATIO * r and upper <= DOJI_FLAT_WICK_RATIO * r:
        pid, name, direction = "dragonfly_doji", "Dragonfly Doji", "bullish"
        aligned = trends[1] == "down"
    elif upper >= DOJI_WICK_RATIO * r and lower <= DOJI_FLAT_WICK_RATIO * r:
        pid, name, direction = "gravestone_doji", "Gravestone Doji", "bearish"
        aligned = trends[1] == "up"
    else:
        pid, name, direction = "doji", "Doji", "neutral"
        aligned = False

    confidence = _confidence(0.45, volume_ratio=vol, trend_aligned=aligned)
    reasons = [
        f"body={body:.4g} <= {DOJI_BODY_RATIO:.0%} of range={r:.4g}",
        f"upper_wick={upper:.4g} lower_wick={lower:.4g}",
        f"trend_before={trends[1]}",
    ]
    if direction == "neutral":
        return [_neutral_hit(pid, name, i, confidence, reasons)]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


def _detect_hammer_family(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body <= EPS or body > 0.40 * r:
        return []
    lower, upper = _lower_wick(c), _upper_wick(c)
    if lower < LONG_WICK_RATIO * body or upper > SMALL_WICK_RATIO * body:
        return []
    trend = trends[1]
    if trend == "up":
        pid, name, direction = "hanging_man", "Hanging Man", "bearish"
        aligned = True
    else:
        pid, name, direction = "hammer", "Hammer", "bullish"
        aligned = trend == "down"
    confidence = _confidence(
        0.55, volume_ratio=vol, trend_aligned=aligned,
        strength=(lower / r) - 0.5,
    )
    reasons = [
        f"lower_wick={lower:.4g} >= {LONG_WICK_RATIO:.0f}x body={body:.4g}",
        f"upper_wick={upper:.4g} <= {SMALL_WICK_RATIO:.0%} of body",
        f"trend_before={trend}",
    ]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


def _detect_star_family(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body <= EPS or body > 0.40 * r:
        return []
    upper, lower = _upper_wick(c), _lower_wick(c)
    if upper < LONG_WICK_RATIO * body or lower > SMALL_WICK_RATIO * body:
        return []
    trend = trends[1]
    if trend == "up":
        pid, name, direction = "shooting_star", "Shooting Star", "bearish"
        aligned = True
    else:
        pid, name, direction = "inverted_hammer", "Inverted Hammer", "bullish"
        aligned = trend == "down"
    confidence = _confidence(
        0.55, volume_ratio=vol, trend_aligned=aligned,
        strength=(upper / r) - 0.5,
    )
    reasons = [
        f"upper_wick={upper:.4g} >= {LONG_WICK_RATIO:.0f}x body={body:.4g}",
        f"lower_wick={lower:.4g} <= {SMALL_WICK_RATIO:.0%} of body",
        f"trend_before={trend}",
    ]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


def _detect_marubozu(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body < MARUBOZU_BODY_RATIO * r:
        return []
    if _bullish(c):
        pid, name, direction = "bullish_marubozu", "Bullish Marubozu", "bullish"
        aligned = trends[1] == "up"
    elif _bearish(c):
        pid, name, direction = "bearish_marubozu", "Bearish Marubozu", "bearish"
        aligned = trends[1] == "down"
    else:
        return []
    confidence = _confidence(
        0.60, volume_ratio=vol, trend_aligned=aligned,
        strength=(body / r) - MARUBOZU_BODY_RATIO,
    )
    reasons = [
        f"body={body:.4g} >= {MARUBOZU_BODY_RATIO:.0%} of range={r:.4g}",
        "both wicks negligible",
        f"trend_before={trends[1]}",
    ]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


def _detect_spinning_top(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body <= DOJI_BODY_RATIO * r or body > 0.30 * r:
        return []
    if _upper_wick(c) < 0.20 * r or _lower_wick(c) < 0.20 * r:
        return []
    confidence = _confidence(0.40, volume_ratio=vol)
    reasons = [
        f"body={body:.4g} between {DOJI_BODY_RATIO:.0%} and 30% of range",
        f"upper_wick={_upper_wick(c):.4g} lower_wick={_lower_wick(c):.4g}",
        "indecision -- wait for the break",
    ]
    return [_neutral_hit("spinning_top", "Spinning Top", i, confidence, reasons)]


def _detect_belt_hold(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body < BELT_BODY_RATIO * r:
        return []
    upper, lower = _upper_wick(c), _lower_wick(c)
    if _bullish(c) and lower <= 0.05 * r and upper <= 0.30 * r:
        pid, name, direction = "bullish_belt_hold", "Bullish Belt Hold", "bullish"
        aligned = trends[1] == "down"
    elif _bearish(c) and upper <= 0.05 * r and lower <= 0.30 * r:
        pid, name, direction = "bearish_belt_hold", "Bearish Belt Hold", "bearish"
        aligned = trends[1] == "up"
    else:
        return []
    confidence = _confidence(
        0.55, volume_ratio=vol, trend_aligned=aligned,
        strength=(body / r) - BELT_BODY_RATIO,
    )
    reasons = [
        f"body={body:.4g} >= {BELT_BODY_RATIO:.0%} of range",
        "open at the extreme, close near the other extreme",
        f"trend_before={trends[1]}",
    ]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


def _detect_pin_bar(candles, i, trends, vol, ctx):
    c = candles[i]
    r = _range(c)
    body = _body(c)
    if r <= EPS or body > PIN_BODY_RATIO * r:
        return []
    upper, lower = _upper_wick(c), _lower_wick(c)
    if lower >= PIN_WICK_RATIO * r and upper <= (1.0 - PIN_WICK_RATIO) * r:
        pid, name, direction = "bullish_pin_bar", "Bullish Pin Bar", "bullish"
        aligned = trends[1] == "down"
    elif upper >= PIN_WICK_RATIO * r and lower <= (1.0 - PIN_WICK_RATIO) * r:
        pid, name, direction = "bearish_pin_bar", "Bearish Pin Bar", "bearish"
        aligned = trends[1] == "up"
    else:
        return []
    confidence = _confidence(
        0.50, volume_ratio=vol, trend_aligned=aligned,
        strength=(max(upper, lower) / r) - PIN_WICK_RATIO,
    )
    reasons = [
        f"wick={max(upper, lower):.4g} >= {PIN_WICK_RATIO:.0%} of range",
        f"body={body:.4g} <= {PIN_BODY_RATIO:.0%} of range",
        f"trend_before={trends[1]}",
    ]
    if direction == "bullish":
        return [_long_hit(pid, name, i, c.high, c.low, confidence, reasons)]
    return [_short_hit(pid, name, i, c.high, c.low, confidence, reasons)]


# ---------------------------------------------------------------------------
# Two-candle detectors
# ---------------------------------------------------------------------------


def _detect_engulfing(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    high, low = max(p.high, c.high), min(p.low, c.low)
    if (_bearish(p) and _bullish(c)
            and c.open <= p.close + EPS
            and c.close >= p.open - EPS
            and _body(c) > _body(p) + EPS):
        confidence = _confidence(0.62, volume_ratio=vol,
                                 trend_aligned=trends[2] == "down",
                                 strength=(_body(c) / _body(p)) - 1.0)
        reasons = ["prior candle bearish", "current candle bullish",
                   "current body fully engulfs prior body"]
        return [_long_hit("bullish_engulfing", "Bullish Engulfing", i,
                          high, low, confidence, reasons)]
    if (_bullish(p) and _bearish(c)
            and c.open >= p.close - EPS
            and c.close <= p.open + EPS
            and _body(c) > _body(p) + EPS):
        confidence = _confidence(0.62, volume_ratio=vol,
                                 trend_aligned=trends[2] == "up",
                                 strength=(_body(c) / _body(p)) - 1.0)
        reasons = ["prior candle bullish", "current candle bearish",
                   "current body fully engulfs prior body"]
        return [_short_hit("bearish_engulfing", "Bearish Engulfing", i,
                           high, low, confidence, reasons)]
    return []


def _detect_piercing(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    mid = (p.open + p.close) / 2.0
    if (_bearish(p) and _bullish(c)
            and c.open < p.close - EPS
            and c.close > mid + EPS
            and c.close < p.open - EPS):
        confidence = _confidence(0.58, volume_ratio=vol,
                                 trend_aligned=trends[2] == "down")
        reasons = ["prior candle bearish", "current candle bullish",
                   "close pierces above the prior body midpoint",
                   "close stays below the prior open"]
        return [_long_hit("piercing_line", "Piercing Line", i,
                          max(p.high, c.high), min(p.low, c.low),
                          confidence, reasons)]
    return []


def _detect_dark_cloud(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    mid = (p.open + p.close) / 2.0
    if (_bullish(p) and _bearish(c)
            and c.open > p.close + EPS
            and c.close < mid - EPS
            and c.close > p.open + EPS):
        confidence = _confidence(0.58, volume_ratio=vol,
                                 trend_aligned=trends[2] == "up")
        reasons = ["prior candle bullish", "current candle bearish",
                   "close pierces below the prior body midpoint",
                   "close stays above the prior open"]
        return [_short_hit("dark_cloud_cover", "Dark Cloud Cover", i,
                           max(p.high, c.high), min(p.low, c.low),
                           confidence, reasons)]
    return []


def _detect_harami(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    if (_bearish(p) and _bullish(c)
            and c.open >= p.close - EPS
            and c.close <= p.open + EPS
            and _body(c) < HARAMI_BODY_RATIO * _body(p) - EPS):
        confidence = _confidence(0.52, volume_ratio=vol,
                                 trend_aligned=trends[2] == "down")
        reasons = ["prior candle bearish", "current candle bullish",
                   "current body is inside the prior body and smaller"]
        return [_long_hit("bullish_harami", "Bullish Harami", i,
                          max(p.high, c.high), min(p.low, c.low),
                          confidence, reasons)]
    if (_bullish(p) and _bearish(c)
            and c.open <= p.close + EPS
            and c.close >= p.open - EPS
            and _body(c) < HARAMI_BODY_RATIO * _body(p) - EPS):
        confidence = _confidence(0.52, volume_ratio=vol,
                                 trend_aligned=trends[2] == "up")
        reasons = ["prior candle bullish", "current candle bearish",
                   "current body is inside the prior body and smaller"]
        return [_short_hit("bearish_harami", "Bearish Harami", i,
                           max(p.high, c.high), min(p.low, c.low),
                           confidence, reasons)]
    return []


def _detect_tweezer(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    tol = max(0.001 * c.close, 0.10 * _range(p))
    if abs(c.low - p.low) <= tol and _bearish(p) and _bullish(c):
        confidence = _confidence(0.50, volume_ratio=vol,
                                 trend_aligned=trends[2] == "down")
        reasons = ["two equal lows", "prior candle bearish",
                   "current candle bullish"]
        return [_long_hit("tweezer_bottom", "Tweezer Bottom", i,
                          max(p.high, c.high), min(p.low, c.low),
                          confidence, reasons)]
    if abs(c.high - p.high) <= tol and _bullish(p) and _bearish(c):
        confidence = _confidence(0.50, volume_ratio=vol,
                                 trend_aligned=trends[2] == "up")
        reasons = ["two equal highs", "prior candle bullish",
                   "current candle bearish"]
        return [_short_hit("tweezer_top", "Tweezer Top", i,
                           max(p.high, c.high), min(p.low, c.low),
                           confidence, reasons)]
    return []


def _detect_inside_bar(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    if c.high <= p.high + EPS and c.low >= p.low - EPS:
        confidence = _confidence(0.45, volume_ratio=vol)
        reasons = ["current range is inside the prior range",
                   "compression -- wait for the break"]
        return [_neutral_hit("inside_bar", "Inside Bar", i, confidence, reasons)]
    return []


def _detect_outside_bar(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    if (c.high >= p.high - EPS and c.low <= p.low + EPS
            and (c.high > p.high + EPS or c.low < p.low - EPS)):
        confidence = _confidence(0.45, volume_ratio=vol)
        reasons = ["current range engulfs the prior range",
                   "expansion -- direction comes from the close"]
        return [_neutral_hit("outside_bar", "Outside Bar", i, confidence, reasons)]
    return []


def _detect_kicker(candles, i, trends, vol, ctx):
    if i < 1:
        return []
    p, c = candles[i - 1], candles[i]
    if (_bearish(p) and _bullish(c)
            and c.open > p.high + EPS
            and _body(c) >= 0.60 * _safe_range(c)):
        confidence = _confidence(0.66, volume_ratio=vol,
                                 trend_aligned=trends[2] == "down",
                                 strength=(_body(c) / _safe_range(c)) - 0.60)
        reasons = ["gap up above the prior high",
                   "prior candle bearish, current candle bullish",
                   "current body is strong"]
        return [_long_hit("bullish_kicker", "Bullish Kicker", i,
                          max(p.high, c.high), min(p.low, c.low),
                          confidence, reasons)]
    if (_bullish(p) and _bearish(c)
            and c.open < p.low - EPS
            and _body(c) >= 0.60 * _safe_range(c)):
        confidence = _confidence(0.66, volume_ratio=vol,
                                 trend_aligned=trends[2] == "up",
                                 strength=(_body(c) / _safe_range(c)) - 0.60)
        reasons = ["gap down below the prior low",
                   "prior candle bullish, current candle bearish",
                   "current body is strong"]
        return [_short_hit("bearish_kicker", "Bearish Kicker", i,
                           max(p.high, c.high), min(p.low, c.low),
                           confidence, reasons)]
    return []


# ---------------------------------------------------------------------------
# Three-candle detectors
# ---------------------------------------------------------------------------


def _detect_morning_evening_star(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    b1 = _body(c1)
    b2 = _body(c2)
    mid1 = (c1.open + c1.close) / 2.0
    if (_bearish(c1) and b1 >= STRONG_BODY_RATIO * _safe_range(c1)
            and b2 <= STAR_SMALL_BODY_RATIO * b1
            and max(c2.open, c2.close) < c1.close - EPS
            and _bullish(c3) and c3.close > mid1 + EPS):
        confidence = _confidence(0.64, volume_ratio=vol,
                                 trend_aligned=trends[3] == "down")
        reasons = ["first candle bearish and strong",
                   "second candle small and gapped below the first close",
                   "third candle bullish and closes above the first midpoint"]
        return [_long_hit("morning_star", "Morning Star", i,
                          max(c1.high, c2.high, c3.high),
                          min(c1.low, c2.low, c3.low),
                          confidence, reasons)]
    if (_bullish(c1) and b1 >= STRONG_BODY_RATIO * _safe_range(c1)
            and b2 <= STAR_SMALL_BODY_RATIO * b1
            and min(c2.open, c2.close) > c1.close + EPS
            and _bearish(c3) and c3.close < mid1 - EPS):
        confidence = _confidence(0.64, volume_ratio=vol,
                                 trend_aligned=trends[3] == "up")
        reasons = ["first candle bullish and strong",
                   "second candle small and gapped above the first close",
                   "third candle bearish and closes below the first midpoint"]
        return [_short_hit("evening_star", "Evening Star", i,
                           max(c1.high, c2.high, c3.high),
                           min(c1.low, c2.low, c3.low),
                           confidence, reasons)]
    return []


def _detect_three_soldiers_crows(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    if (all(_bullish(x) for x in (c1, c2, c3))
            and c2.close > c1.close + EPS
            and c3.close > c2.close + EPS
            and c2.open >= c1.open - EPS
            and c3.open >= c2.open - EPS
            and all(_body(x) >= STRONG_BODY_RATIO * _safe_range(x)
                    for x in (c1, c2, c3))):
        confidence = _confidence(0.66, volume_ratio=vol,
                                 trend_aligned=trends[3] == "up")
        reasons = ["three consecutive bullish candles",
                   "each close is higher than the prior close",
                   "each open is at or above the prior open",
                   "all three bodies are strong"]
        return [_long_hit("three_white_soldiers", "Three White Soldiers", i,
                          max(c1.high, c2.high, c3.high),
                          min(c1.low, c2.low, c3.low),
                          confidence, reasons)]
    if (all(_bearish(x) for x in (c1, c2, c3))
            and c2.close < c1.close - EPS
            and c3.close < c2.close - EPS
            and c2.open <= c1.open + EPS
            and c3.open <= c2.open + EPS
            and all(_body(x) >= STRONG_BODY_RATIO * _safe_range(x)
                    for x in (c1, c2, c3))):
        confidence = _confidence(0.66, volume_ratio=vol,
                                 trend_aligned=trends[3] == "down")
        reasons = ["three consecutive bearish candles",
                   "each close is lower than the prior close",
                   "each open is at or below the prior open",
                   "all three bodies are strong"]
        return [_short_hit("three_black_crows", "Three Black Crows", i,
                           max(c1.high, c2.high, c3.high),
                           min(c1.low, c2.low, c3.low),
                           confidence, reasons)]
    return []


def _detect_three_inside(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    if (_bearish(c1) and _bullish(c2)
            and c2.open >= c1.close - EPS
            and c2.close <= c1.open + EPS
            and _body(c2) < HARAMI_BODY_RATIO * _body(c1) - EPS
            and _bullish(c3) and c3.close > c1.open + EPS):
        confidence = _confidence(0.62, volume_ratio=vol,
                                 trend_aligned=trends[3] == "down")
        reasons = ["bullish harami in the first two candles",
                   "third candle closes above the first candle open"]
        return [_long_hit("three_inside_up", "Three Inside Up", i,
                          max(c1.high, c2.high, c3.high),
                          min(c1.low, c2.low, c3.low),
                          confidence, reasons)]
    if (_bullish(c1) and _bearish(c2)
            and c2.open <= c1.close + EPS
            and c2.close >= c1.open - EPS
            and _body(c2) < HARAMI_BODY_RATIO * _body(c1) - EPS
            and _bearish(c3) and c3.close < c1.open - EPS):
        confidence = _confidence(0.62, volume_ratio=vol,
                                 trend_aligned=trends[3] == "up")
        reasons = ["bearish harami in the first two candles",
                   "third candle closes below the first candle open"]
        return [_short_hit("three_inside_down", "Three Inside Down", i,
                           max(c1.high, c2.high, c3.high),
                           min(c1.low, c2.low, c3.low),
                           confidence, reasons)]
    return []


def _detect_three_outside(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    if (_bearish(c1) and _bullish(c2)
            and c2.open <= c1.close + EPS
            and c2.close >= c1.open - EPS
            and _body(c2) > _body(c1) + EPS
            and _bullish(c3) and c3.close > c2.close + EPS):
        confidence = _confidence(0.64, volume_ratio=vol,
                                 trend_aligned=trends[3] == "down")
        reasons = ["bullish engulfing in the first two candles",
                   "third candle closes above the engulfing close"]
        return [_long_hit("three_outside_up", "Three Outside Up", i,
                          max(c1.high, c2.high, c3.high),
                          min(c1.low, c2.low, c3.low),
                          confidence, reasons)]
    if (_bullish(c1) and _bearish(c2)
            and c2.open >= c1.close - EPS
            and c2.close <= c1.open + EPS
            and _body(c2) > _body(c1) + EPS
            and _bearish(c3) and c3.close < c2.close - EPS):
        confidence = _confidence(0.64, volume_ratio=vol,
                                 trend_aligned=trends[3] == "up")
        reasons = ["bearish engulfing in the first two candles",
                   "third candle closes below the engulfing close"]
        return [_short_hit("three_outside_down", "Three Outside Down", i,
                           max(c1.high, c2.high, c3.high),
                           min(c1.low, c2.low, c3.low),
                           confidence, reasons)]
    return []


def _detect_abandoned_baby(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    if not _is_doji(c2):
        return []
    mid1 = (c1.open + c1.close) / 2.0
    if (_bearish(c1)
            and c2.high < c1.low - EPS
            and _bullish(c3)
            and c3.low > c2.high + EPS
            and c3.close > mid1 + EPS):
        confidence = _confidence(0.70, volume_ratio=vol,
                                 trend_aligned=trends[3] == "down")
        reasons = ["doji gaps below the first candle",
                   "third candle gaps above the doji",
                   "third candle closes above the first midpoint"]
        return [_long_hit("abandoned_baby_bullish", "Bullish Abandoned Baby", i,
                          max(c1.high, c2.high, c3.high),
                          min(c1.low, c2.low, c3.low),
                          confidence, reasons)]
    if (_bullish(c1)
            and c2.low > c1.high + EPS
            and _bearish(c3)
            and c3.high < c2.low - EPS
            and c3.close < mid1 - EPS):
        confidence = _confidence(0.70, volume_ratio=vol,
                                 trend_aligned=trends[3] == "up")
        reasons = ["doji gaps above the first candle",
                   "third candle gaps below the doji",
                   "third candle closes below the first midpoint"]
        return [_short_hit("abandoned_baby_bearish", "Bearish Abandoned Baby", i,
                           max(c1.high, c2.high, c3.high),
                           min(c1.low, c2.low, c3.low),
                           confidence, reasons)]
    return []


def _detect_tri_star(candles, i, trends, vol, ctx):
    if i < 2:
        return []
    c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
    if all(_is_doji(x) for x in (c1, c2, c3)):
        confidence = _confidence(0.42, volume_ratio=vol)
        reasons = ["three consecutive dojis", "indecision -- wait for the break"]
        return [_neutral_hit("tri_star", "Tri-Star", i, confidence, reasons)]
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

PATTERN_IDS = frozenset({
    "doji", "dragonfly_doji", "gravestone_doji",
    "hammer", "hanging_man", "inverted_hammer", "shooting_star",
    "bullish_marubozu", "bearish_marubozu", "spinning_top",
    "bullish_pin_bar", "bearish_pin_bar",
    "bullish_belt_hold", "bearish_belt_hold",
    "bullish_engulfing", "bearish_engulfing",
    "piercing_line", "dark_cloud_cover",
    "bullish_harami", "bearish_harami",
    "tweezer_bottom", "tweezer_top",
    "inside_bar", "outside_bar",
    "bullish_kicker", "bearish_kicker",
    "morning_star", "evening_star",
    "three_white_soldiers", "three_black_crows",
    "three_inside_up", "three_inside_down",
    "three_outside_up", "three_outside_down",
    "abandoned_baby_bullish", "abandoned_baby_bearish",
    "tri_star",
})

DETECTORS = (
    _detect_doji_family,
    _detect_hammer_family,
    _detect_star_family,
    _detect_marubozu,
    _detect_spinning_top,
    _detect_belt_hold,
    _detect_pin_bar,
    _detect_engulfing,
    _detect_piercing,
    _detect_dark_cloud,
    _detect_harami,
    _detect_tweezer,
    _detect_inside_bar,
    _detect_outside_bar,
    _detect_kicker,
    _detect_morning_evening_star,
    _detect_three_soldiers_crows,
    _detect_three_inside,
    _detect_three_outside,
    _detect_abandoned_baby,
    _detect_tri_star,
)

_REVERSAL_SHAPES = {
    "hammer", "hanging_man", "inverted_hammer", "shooting_star",
}
_DOJI_SHAPES = {"doji", "dragonfly_doji", "gravestone_doji"}
_MARUBOZU_SHAPES = {"bullish_marubozu", "bearish_marubozu"}
_PIN_SHAPES = {"bullish_pin_bar", "bearish_pin_bar"}
_BELT_SHAPES = {"bullish_belt_hold", "bearish_belt_hold"}


def _dedupe_bar(hits: list[PatternHit]) -> list[PatternHit]:
    """Drop broader labels when a more specific one fired on the same bar."""
    ids = {h.pattern_id for h in hits}
    out: list[PatternHit] = []
    for h in hits:
        if h.pattern_id in _PIN_SHAPES and ids & (_REVERSAL_SHAPES | _DOJI_SHAPES):
            continue
        if h.pattern_id in _BELT_SHAPES and ids & _MARUBOZU_SHAPES:
            continue
        if h.pattern_id in _REVERSAL_SHAPES and ids & _DOJI_SHAPES:
            continue
        out.append(h)
    return out


def detect_all(
    candles: Sequence[Candle],
    context: dict | None = None,
) -> list[PatternHit]:
    """Detect every pattern in ``candles``.

    ``context`` may contain:
      * ``trend``: ``"up"`` / ``"down"`` / ``"range"`` to override inference
      * ``volume_ratio``: current volume / 20D average, to override the
        per-bar calculation
    """
    candles = list(candles)
    ctx = dict(context or {})
    hits: list[PatternHit] = []
    for i in range(len(candles)):
        trends = _trends_for(candles, i, ctx)
        vol = _volume_ratio(candles, i, ctx)
        bar_hits: list[PatternHit] = []
        for detector in DETECTORS:
            bar_hits.extend(detector(candles, i, trends, vol, ctx))
        hits.extend(_dedupe_bar(bar_hits))
    hits.sort(key=lambda h: (h.bar_index, -h.confidence, h.pattern_id))
    return hits


def detect_last(
    candles: Sequence[Candle],
    context: dict | None = None,
) -> list[PatternHit]:
    """Only the patterns whose final candle is the last candle."""
    candles = list(candles)
    if not candles:
        return []
    return [h for h in detect_all(candles, context=context)
            if h.bar_index == len(candles) - 1]
