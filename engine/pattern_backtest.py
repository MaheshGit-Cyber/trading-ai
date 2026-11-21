"""Deterministic pattern backtest.

The detector in :mod:`engine.patterns` supplies a trade frame
(entry / stop / T1 / T2). This module only simulates that frame on the
next bars and charges costs. No model, no network, no look-ahead.

Rules (fixed, not tuned per pattern):

* A bullish pattern triggers when a later bar trades at or above the
  pattern high; a bearish pattern triggers at or below the pattern low.
* The trigger is valid for ``wait_bars`` bars. A gap through the trigger
  fills at the open, which is the only price available.
* If the entry bar also trades through the stop before the trigger can
  be ordered, the trade is marked ``ambiguous`` and skipped. Daily OHLC
  cannot order the two touches.
* Exits are evaluated from the bar after entry. The entry bar is used
  only for the fill.
* T1 books ``t1_fraction`` and moves the stop to break-even. T2 books the
  rest. A stop and a target in the same bar are resolved as stop first.
* T1 and T2 in the same bar book T1 only; the remainder waits for the
  next bar. This is conservative.
* A time stop closes the remainder at the last bar's close.
* Costs are charged once, in R, as ``entry * cost_bps / 10000 / risk``.
  ``cost_bps`` is a round-trip assumption; it already includes slippage.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import Sequence

from engine.patterns import Candle, PatternHit, detect_all, infer_trend

DIRECTIONS = ("bullish", "bearish")
STATUSES = ("entered", "no_trigger", "ambiguous", "invalid", "no_data")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    wait_bars: int = 3
    max_hold_bars: int = 10
    cost_bps: float = 50.0
    cost_bps_stress: float | None = None
    t1_fraction: float = 0.5
    min_confidence: float = 0.0
    min_turnover_lacs: float = 0.0
    one_per_bar: bool = True
    trend_filter: str = "none"  # none | align | counter
    min_volume_ratio: float = 0.0
    regime_filter: str = "none"  # none | above | below | align
    exit_mode: str = "partial"  # partial | t1 | t2

    def __post_init__(self) -> None:
        if self.wait_bars < 1:
            raise ValueError("wait_bars must be >= 1")
        if self.max_hold_bars < 1:
            raise ValueError("max_hold_bars must be >= 1")
        if self.cost_bps < 0:
            raise ValueError("cost_bps must be >= 0")
        if self.cost_bps_stress is not None and self.cost_bps_stress < 0:
            raise ValueError("cost_bps_stress must be >= 0")
        if not 0.0 <= self.t1_fraction <= 1.0:
            raise ValueError("t1_fraction must be in [0, 1]")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        if self.min_turnover_lacs < 0:
            raise ValueError("min_turnover_lacs must be >= 0")
        if self.trend_filter not in ("none", "align", "counter"):
            raise ValueError("trend_filter must be none/align/counter")
        if self.min_volume_ratio < 0:
            raise ValueError("min_volume_ratio must be >= 0")
        if self.regime_filter not in ("none", "above", "below", "align"):
            raise ValueError("regime_filter must be none/above/below/align")
        if self.exit_mode not in ("partial", "t1", "t2"):
            raise ValueError("exit_mode must be partial/t1/t2")

    @property
    def stress_bps(self) -> float:
        if self.cost_bps_stress is not None:
            return self.cost_bps_stress
        return self.cost_bps * 2.0


@dataclass(frozen=True, slots=True)
class TradeResult:
    symbol: str
    pattern_id: str
    name: str
    direction: str
    signal_date: str
    signal_index: int
    confidence: float
    entry: float
    stop: float
    target1: float
    target2: float
    status: str
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    gross_r: float = 0.0
    cost_r: float = 0.0
    net_r: float = 0.0
    cost_r_stress: float = 0.0
    net_r_stress: float = 0.0
    bars_held: int = 0
    t1_hit: bool = False
    t2_hit: bool = False

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "pattern_id": self.pattern_id,
            "name": self.name,
            "direction": self.direction,
            "signal_date": self.signal_date,
            "signal_index": self.signal_index,
            "confidence": round(self.confidence, 6),
            "entry": round(self.entry, 6),
            "stop": round(self.stop, 6),
            "target1": round(self.target1, 6),
            "target2": round(self.target2, 6),
            "status": self.status,
            "entry_date": self.entry_date,
            "entry_price": round(self.entry_price, 6),
            "exit_date": self.exit_date,
            "exit_price": round(self.exit_price, 6),
            "exit_reason": self.exit_reason,
            "gross_r": round(self.gross_r, 6),
            "cost_r": round(self.cost_r, 6),
            "net_r": round(self.net_r, 6),
            "cost_r_stress": round(self.cost_r_stress, 6),
            "net_r_stress": round(self.net_r_stress, 6),
            "bars_held": self.bars_held,
            "t1_hit": self.t1_hit,
            "t2_hit": self.t2_hit,
        }


def _result(
    symbol: str,
    hit: PatternHit,
    signal_date: str,
    status: str,
    *,
    entry_date: str = "",
    entry_price: float = 0.0,
    exit_date: str = "",
    exit_price: float = 0.0,
    exit_reason: str = "",
    gross_r: float = 0.0,
    cost_r: float = 0.0,
    net_r: float = 0.0,
    cost_r_stress: float = 0.0,
    net_r_stress: float = 0.0,
    bars_held: int = 0,
    t1_hit: bool = False,
    t2_hit: bool = False,
) -> TradeResult:
    return TradeResult(
        symbol=symbol,
        pattern_id=hit.pattern_id,
        name=hit.name,
        direction=hit.direction,
        signal_date=signal_date,
        signal_index=hit.bar_index,
        confidence=hit.confidence,
        entry=hit.entry,
        stop=hit.stop,
        target1=hit.target1,
        target2=hit.target2,
        status=status,
        entry_date=entry_date,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_r=gross_r,
        cost_r=cost_r,
        net_r=net_r,
        cost_r_stress=cost_r_stress,
        net_r_stress=net_r_stress,
        bars_held=bars_held,
        t1_hit=t1_hit,
        t2_hit=t2_hit,
    )


def _valid_hit(hit: PatternHit) -> bool:
    if hit.direction not in DIRECTIONS:
        return False
    if min(hit.entry, hit.stop, hit.target1, hit.target2) <= 0:
        return False
    if hit.direction == "bullish":
        return hit.entry > hit.stop and hit.target1 > hit.entry
    return hit.stop > hit.entry and hit.target1 < hit.entry


def _trend_before(bars: Sequence, index: int) -> str:
    if index < 3:
        return "range"
    # infer_trend only reads the last 20 bars. Converting the full history
    # for every hit made the sweep quadratic; 20 is enough.
    start = max(0, index - 20)
    prior = [
        Candle(b.open, b.high, b.low, b.close) for b in bars[start:index]
    ]
    return infer_trend(prior)


def _volume_ratio_at(
    bars: Sequence, index: int, window: int = 20
) -> float | None:
    if index <= 0:
        return None
    start = max(0, index - window)
    prior = [
        float(getattr(b, "volume", 0.0) or 0.0)
        for b in bars[start:index]
    ]
    prior = [value for value in prior if value > 0]
    if not prior:
        return None
    average = sum(prior) / len(prior)
    if average <= 0:
        return None
    current = float(getattr(bars[index], "volume", 0.0) or 0.0)
    return current / average


def select_hits(
    hits: Sequence[PatternHit],
    bars: Sequence,
    config: BacktestConfig,
    *,
    start: str | None = None,
    end: str | None = None,
    regime_by_date: dict[str, bool] | None = None,
) -> list[PatternHit]:
    """Filter to tradable frames, then keep the best hit per bar.

    Context filters are applied before the one-per-bar choice, so a
    filtered-out high-confidence hit cannot hide a lower-confidence hit
    that actually passes the filters.
    """
    out: list[PatternHit] = []
    for hit in hits:
        if not _valid_hit(hit):
            continue
        if hit.confidence < config.min_confidence:
            continue
        if not 0 <= hit.bar_index < len(bars) - 1:
            continue
        if config.min_turnover_lacs > 0:
            turnover = float(
                getattr(bars[hit.bar_index], "turnover_lacs", 0.0) or 0.0
            )
            if turnover < config.min_turnover_lacs:
                continue
        date = bars[hit.bar_index].date
        if start and date < start:
            continue
        if end and date > end:
            continue
        if config.trend_filter != "none":
            trend = _trend_before(bars, hit.bar_index)
            want = "up" if hit.direction == "bullish" else "down"
            if config.trend_filter == "align":
                if trend != want:
                    continue
            else:  # counter
                if trend != ("down" if want == "up" else "up"):
                    continue
        if config.min_volume_ratio > 0:
            ratio = _volume_ratio_at(bars, hit.bar_index)
            if ratio is None or ratio < config.min_volume_ratio:
                continue
        if config.regime_filter != "none":
            if not regime_by_date:
                continue
            above = regime_by_date.get(date)
            if above is None:
                continue
            if config.regime_filter == "above" and not above:
                continue
            if config.regime_filter == "below" and above:
                continue
            if config.regime_filter == "align":
                want_above = hit.direction == "bullish"
                if above != want_above:
                    continue
        out.append(hit)
    if not config.one_per_bar:
        return out
    best: dict[int, PatternHit] = {}
    for hit in out:
        prev = best.get(hit.bar_index)
        if (
            prev is None
            or hit.confidence > prev.confidence
            or (
                hit.confidence == prev.confidence
                and hit.pattern_id < prev.pattern_id
            )
        ):
            best[hit.bar_index] = hit
    return [best[i] for i in sorted(best)]


def simulate_trade(
    symbol: str,
    bars: Sequence,
    hit: PatternHit,
    config: BacktestConfig,
) -> TradeResult:
    """Simulate one pattern frame. ``bars`` need date/open/high/low/close."""
    if not _valid_hit(hit):
        return _result(symbol, hit, "", "invalid")
    i = hit.bar_index
    if not 0 <= i < len(bars):
        return _result(symbol, hit, "", "invalid")
    signal_date = bars[i].date
    if i >= len(bars) - 1:
        return _result(symbol, hit, signal_date, "no_data")

    long = hit.direction == "bullish"
    entry = hit.entry
    stop = hit.stop
    t1 = hit.target1
    t2 = hit.target2

    # Find the trigger bar. A bar that trades through both the trigger and
    # the stop before entry is ambiguous; skip it rather than guess.
    entry_index = -1
    entry_price = 0.0
    last = min(i + config.wait_bars, len(bars) - 1)
    for j in range(i + 1, last + 1):
        bar = bars[j]
        if long:
            triggered = bar.high >= entry
            stopped = bar.low <= stop
            if triggered and stopped:
                return _result(symbol, hit, signal_date, "ambiguous")
            if not triggered:
                if stopped:
                    return _result(symbol, hit, signal_date, "no_trigger")
                continue
            entry_price = max(entry, bar.open) if bar.open >= entry else entry
        else:
            triggered = bar.low <= entry
            stopped = bar.high >= stop
            if triggered and stopped:
                return _result(symbol, hit, signal_date, "ambiguous")
            if not triggered:
                if stopped:
                    return _result(symbol, hit, signal_date, "no_trigger")
                continue
            entry_price = min(entry, bar.open) if bar.open <= entry else entry
        entry_index = j
        break

    if entry_index < 0:
        return _result(symbol, hit, signal_date, "no_trigger")
    if entry_index >= len(bars) - 1:
        return _result(
            symbol, hit, signal_date, "no_data",
            entry_date=bars[entry_index].date, entry_price=entry_price,
        )

    risk = abs(entry_price - stop)
    if risk <= 0:
        return _result(symbol, hit, signal_date, "invalid")
    cost_r = (entry_price * config.cost_bps / 10000.0) / risk
    cost_r_stress = (entry_price * config.stress_bps / 10000.0) / risk

    if config.exit_mode == "t1":
        t1_fraction = 1.0
    elif config.exit_mode == "t2":
        t1_fraction = 0.0
    else:
        t1_fraction = config.t1_fraction
    remaining = 1.0
    gross = 0.0
    stop_price = stop
    t1_done = False
    t2_done = False
    exit_index = entry_index
    exit_price = entry_price
    exit_reason = "time"

    end = min(entry_index + config.max_hold_bars, len(bars) - 1)
    for k in range(entry_index + 1, end + 1):
        bar = bars[k]
        exit_index = k

        if long:
            if bar.open <= stop_price:
                exit_price = bar.open
                exit_reason = "gap_be_stop" if t1_done else "gap_stop"
                break
            if not t1_done and bar.open >= t1:
                exit_price = bar.open
                exit_reason = "gap_t1"
                break
            if t1_done and bar.open >= t2:
                exit_price = bar.open
                exit_reason = "gap_t2"
                break

            stop_hit = bar.low <= stop_price
            t1_hit = (not t1_done) and bar.high >= t1
            t2_hit = t1_done and bar.high >= t2

            if stop_hit and (t1_hit or t2_hit):
                exit_price = stop_price
                exit_reason = "be_stop_first" if t1_done else "stop_first"
                break
            if stop_hit:
                exit_price = stop_price
                exit_reason = "be_stop" if t1_done else "stop"
                break
            if t2_hit:
                exit_price = t2
                exit_reason = "t2"
                t2_done = True
                break
            if t1_hit:
                r_t1 = (t1 - entry_price) / risk
                gross += t1_fraction * r_t1
                remaining -= t1_fraction
                t1_done = True
                stop_price = entry_price
                if remaining <= 1e-9:
                    exit_price = t1
                    exit_reason = "t1"
                    break
        else:
            if bar.open >= stop_price:
                exit_price = bar.open
                exit_reason = "gap_be_stop" if t1_done else "gap_stop"
                break
            if not t1_done and bar.open <= t1:
                exit_price = bar.open
                exit_reason = "gap_t1"
                break
            if t1_done and bar.open <= t2:
                exit_price = bar.open
                exit_reason = "gap_t2"
                break

            stop_hit = bar.high >= stop_price
            t1_hit = (not t1_done) and bar.low <= t1
            t2_hit = t1_done and bar.low <= t2

            if stop_hit and (t1_hit or t2_hit):
                exit_price = stop_price
                exit_reason = "be_stop_first" if t1_done else "stop_first"
                break
            if stop_hit:
                exit_price = stop_price
                exit_reason = "be_stop" if t1_done else "stop"
                break
            if t2_hit:
                exit_price = t2
                exit_reason = "t2"
                t2_done = True
                break
            if t1_hit:
                r_t1 = (entry_price - t1) / risk
                gross += t1_fraction * r_t1
                remaining -= t1_fraction
                t1_done = True
                stop_price = entry_price
                if remaining <= 1e-9:
                    exit_price = t1
                    exit_reason = "t1"
                    break

    if exit_reason == "time":
        exit_price = bars[exit_index].close

    if remaining > 1e-9:
        r_exit = (
            (exit_price - entry_price) / risk
            if long
            else (entry_price - exit_price) / risk
        )
        gross += remaining * r_exit

    net = gross - cost_r
    net_stress = gross - cost_r_stress
    return _result(
        symbol, hit, signal_date, "entered",
        entry_date=bars[entry_index].date,
        entry_price=entry_price,
        exit_date=bars[exit_index].date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_r=gross,
        cost_r=cost_r,
        net_r=net,
        cost_r_stress=cost_r_stress,
        net_r_stress=net_stress,
        bars_held=exit_index - entry_index,
        t1_hit=t1_done,
        t2_hit=t2_done,
    )


def detect_hits(bars: Sequence) -> list[PatternHit]:
    """Convert bars to candles and run the deterministic detector once."""
    if len(bars) < 3:
        return []
    candles = [
        Candle(
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=float(getattr(bar, "volume", 0.0) or 0.0),
        )
        for bar in bars
    ]
    return detect_all(candles)


def scan_symbol(
    symbol: str,
    bars: Sequence,
    config: BacktestConfig,
    *,
    start: str | None = None,
    end: str | None = None,
    regime_by_date: dict[str, bool] | None = None,
    hits: Sequence[PatternHit] | None = None,
) -> list[TradeResult]:
    """Detect (or reuse) hits, apply filters, then simulate."""
    detected = list(hits) if hits is not None else detect_hits(bars)
    selected = select_hits(
        detected, bars, config,
        start=start, end=end, regime_by_date=regime_by_date,
    )
    return [simulate_trade(symbol, bars, hit, config) for hit in selected]


def summarize(trades: Sequence[TradeResult], label: str) -> dict:
    entered = [t for t in trades if t.status == "entered"]
    if not entered:
        return {
            "label": label,
            "signals": len(trades),
            "entered": 0,
            "skipped_no_trigger": sum(
                1 for t in trades if t.status == "no_trigger"
            ),
            "skipped_ambiguous": sum(
                1 for t in trades if t.status == "ambiguous"
            ),
            "skipped_invalid": sum(
                1 for t in trades if t.status == "invalid"
            ),
            "skipped_no_data": sum(
                1 for t in trades if t.status == "no_data"
            ),
            "expectancy_R": None,
            "note": "no entered trades",
        }

    nets = [t.net_r for t in entered]
    stress = [t.net_r_stress for t in entered]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]

    ordered = sorted(entered, key=lambda t: (t.exit_date, t.entry_date))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in ordered:
        equity += trade.net_r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    reasons = sorted({t.exit_reason for t in entered})
    return {
        "label": label,
        "signals": len(trades),
        "entered": len(entered),
        "skipped_no_trigger": sum(
            1 for t in trades if t.status == "no_trigger"
        ),
        "skipped_ambiguous": sum(
            1 for t in trades if t.status == "ambiguous"
        ),
        "skipped_invalid": sum(
            1 for t in trades if t.status == "invalid"
        ),
        "skipped_no_data": sum(
            1 for t in trades if t.status == "no_data"
        ),
        "win_rate": len(wins) / len(nets),
        "expectancy_R": statistics.fmean(nets),
        "expectancy_R_stress": statistics.fmean(stress),
        "median_R": statistics.median(nets),
        "stdev_R": statistics.pstdev(nets) if len(nets) > 1 else 0.0,
        "avg_win_R": statistics.fmean(wins) if wins else 0.0,
        "avg_loss_R": statistics.fmean(losses) if losses else 0.0,
        "profit_factor": (
            sum(wins) / abs(sum(losses))
            if losses and sum(losses) != 0
            else None
        ),
        "max_drawdown_R": max_dd,
        "avg_cost_R": statistics.fmean(t.cost_r for t in entered),
        "avg_bars_held": statistics.fmean(t.bars_held for t in entered),
        "t1_hit_rate": sum(1 for t in entered if t.t1_hit) / len(entered),
        "t2_hit_rate": sum(1 for t in entered if t.t2_hit) / len(entered),
        "stop_rate": sum(
            1 for t in entered if "stop" in t.exit_reason
        ) / len(entered),
        "exit_reasons": {
            reason: sum(1 for t in entered if t.exit_reason == reason)
            for reason in reasons
        },
    }


def split_trades(
    trades: Sequence[TradeResult], split_date: str | None
) -> tuple[list[TradeResult], list[TradeResult]]:
    if not split_date:
        return list(trades), []
    train = [t for t in trades if t.signal_date < split_date]
    test = [t for t in trades if t.signal_date >= split_date]
    return train, test


def auto_split_date(
    trades: Sequence[TradeResult], fraction: float = 0.7
) -> str | None:
    if not 0.0 < fraction < 1.0:
        raise ValueError("fraction must be in (0, 1)")
    dates = sorted(
        t.signal_date for t in trades
        if t.status == "entered" and t.signal_date
    )
    if len(dates) < 2:
        return None
    index = min(max(int(len(dates) * fraction), 0), len(dates) - 1)
    return dates[index]


def _passes(
    summary: dict, min_expectancy: float, min_profit_factor: float
) -> bool:
    expectancy = summary.get("expectancy_R")
    if expectancy is None or expectancy <= min_expectancy:
        return False
    profit_factor = summary.get("profit_factor")
    if profit_factor is None:
        # No losing trades: the ratio is undefined, not bad.
        return summary.get("win_rate", 0.0) >= 1.0
    return profit_factor > min_profit_factor


def gate(
    summary: dict,
    *,
    min_sample: int = 100,
    min_expectancy: float = 0.0,
    min_profit_factor: float = 1.2,
) -> str:
    """Gate one sample (usually the OOS test)."""
    if summary.get("entered", 0) < min_sample:
        return "INSUFFICIENT"
    if not _passes(summary, min_expectancy, min_profit_factor):
        return "FAIL"
    return "PASS"


def gate_stable(
    all_summary: dict,
    train_summary: dict,
    test_summary: dict,
    *,
    min_sample: int = 100,
    min_expectancy: float = 0.0,
    min_profit_factor: float = 1.2,
) -> str:
    """Require the edge in the full sample, the train half and the test half.

    A pattern that is positive only in the test window is a regime
    artifact, not an edge. ``UNSTABLE`` says exactly that.
    """
    if all_summary.get("entered", 0) < min_sample:
        return "INSUFFICIENT"
    if test_summary.get("entered", 0) < min_sample:
        return "INSUFFICIENT_OOS"
    if not _passes(all_summary, min_expectancy, min_profit_factor):
        return "FAIL"
    if not _passes(train_summary, min_expectancy, 1.0):
        return "UNSTABLE"
    if not _passes(test_summary, min_expectancy, 1.0):
        return "UNSTABLE"
    return "PASS"
