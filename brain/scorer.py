"""Deterministic M-score for NSE equities and momentum score for crypto.

This is the audited "M" part of the proposed DVM score. It deliberately does
**not** claim durability (D) or valuation (V): the local panel has no debt,
interest-coverage, EPS, book-value, P/E or P/B history. A D/V score would be
invented, not measured.

The score is descriptive, not a trade instruction. It is computed only from
bars at or before ``as_of``; the tests lock that down.

    python3 -m brain.scorer --symbol RELIANCE --as-of 2026-11-19
    python3 -m brain.scorer --crypto BTCUSDT --as-of 2026-11-20
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import date as ddate
import json
import math
import os
from typing import Sequence

from brain.contracts import AssetClass, AssetScore, DataQuality, ScoreBand
from brain.data import (
    CRYPTO_FILES,
    DEFAULT_CRYPTO_DIR,
    DEFAULT_NIFTY,
    DEFAULT_PANEL,
    PriceBar,
    load_crypto_rows,
    load_nifty_rows,
    load_panel_rows,
)
from engine.features import StockState

REQUIRED_BARS = 200
ENGINE = "brain.scorer.m1.v1"


def _return(closes: Sequence[float], sessions: int) -> float | None:
    if len(closes) <= sessions or closes[-1 - sessions] <= 0:
        return None
    return closes[-1] / closes[-1 - sessions] - 1.0


def calculate_clenow_momentum(
    prices_series: Sequence[float], window: int = 90
) -> float:
    """Annualized log-linear regression slope multiplied by R^2.

    This is the Clenow momentum score: a smooth, consistent exponential
    trend scores higher than a choppy series with the same endpoint. The
    calculation is deliberately pure-Python so ``brain.scorer`` keeps its
    stdlib-only contract.

    Returns ``0.0`` for insufficient history, non-positive prices, a flat
    series, or any non-finite value. The caller decides whether zero means
    "no signal" or "not enough data".
    """
    if window < 2 or len(prices_series) < window:
        return 0.0
    values = [float(x) for x in prices_series[-window:]]
    if any((not math.isfinite(x)) or x <= 0.0 for x in values):
        return 0.0

    y = [math.log(x) for x in values]
    n = window
    x_mean = (n - 1) / 2.0
    y_mean = sum(y) / n
    sxx = sum((i - x_mean) ** 2 for i in range(n))
    if sxx <= 0.0:
        return 0.0
    sxy = sum((i - x_mean) * (y[i] - y_mean) for i in range(n))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    ss_tot = sum((v - y_mean) ** 2 for v in y)
    if ss_tot <= 0.0:
        return 0.0
    ss_res = sum((y[i] - (intercept + slope * i)) ** 2 for i in range(n))
    r_squared = max(0.0, min(1.0, 1.0 - ss_res / ss_tot))
    return float(slope * 252.0 * r_squared)


def _max_drawdown(closes: Sequence[float], sessions: int) -> float | None:
    window = list(closes[-sessions:]) if len(closes) >= sessions else list(closes)
    if len(window) < 2:
        return None
    peak = window[0]
    worst = 0.0
    for value in window[1:]:
        if value > peak:
            peak = value
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def _annualised_vol(closes: Sequence[float], sessions: int = 20) -> float | None:
    if len(closes) < sessions + 1:
        return None
    window = list(closes[-(sessions + 1):])
    returns = [
        window[i] / window[i - 1] - 1.0
        for i in range(1, len(window))
        if window[i - 1] > 0
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(max(variance, 0.0) * 252.0)


def _excess_points(value: float | None, maximum: float = 15.0) -> float:
    """Piecewise, transparent, and intentionally not fitted to a backtest."""
    if value is None:
        return 0.0
    if value >= 0.20:
        return maximum
    if value >= 0.10:
        return maximum * 0.80
    if value >= 0.00:
        return maximum * 0.5333
    if value >= -0.10:
        return maximum * 0.2667
    return 0.0


def _volume_points(ratio: float | None, maximum: float = 10.0) -> float:
    if ratio is None:
        return 0.0
    if ratio >= 1.50:
        return maximum
    if ratio >= 1.20:
        return maximum * 0.80
    if ratio >= 1.00:
        return maximum * 0.60
    if ratio >= 0.70:
        return maximum * 0.30
    return 0.0


def _delivery_points(ratio: float | None, maximum: float = 10.0) -> float:
    return _volume_points(ratio, maximum)


def _vol_points(value: float | None, maximum: float = 10.0) -> float:
    if value is None:
        return 0.0
    if value <= 0.20:
        return maximum
    if value <= 0.30:
        return maximum * 0.70
    if value <= 0.40:
        return maximum * 0.40
    return 0.0


def _drawdown_points(value: float | None, maximum: float = 10.0) -> float:
    if value is None:
        return 0.0
    if value >= -0.10:
        return maximum
    if value >= -0.20:
        return maximum * 0.70
    if value >= -0.30:
        return maximum * 0.40
    return 0.0


def _crypto_momentum_points(value: float | None, maximum: float = 20.0) -> float:
    if value is None:
        return 0.0
    if value >= 0.30:
        return maximum
    if value >= 0.15:
        return maximum * 0.80
    if value >= 0.00:
        return maximum * 0.50
    if value >= -0.15:
        return maximum * 0.20
    return 0.0


def _crypto_vol_points(value: float | None, maximum: float = 10.0) -> float:
    if value is None:
        return 0.0
    if value <= 0.60:
        return maximum
    if value <= 0.90:
        return maximum * 0.70
    if value <= 1.20:
        return maximum * 0.40
    return 0.0


def _crypto_drawdown_points(value: float | None, maximum: float = 10.0) -> float:
    if value is None:
        return 0.0
    if value >= -0.30:
        return maximum
    if value >= -0.50:
        return maximum * 0.70
    if value >= -0.70:
        return maximum * 0.40
    return 0.0


def _band(score: float) -> str:
    if score >= 80:
        return ScoreBand.STRONG.value
    if score >= 65:
        return ScoreBand.POSITIVE.value
    if score >= 45:
        return ScoreBand.NEUTRAL.value
    if score >= 30:
        return ScoreBand.WEAK.value
    return ScoreBand.VERY_WEAK.value


def _stale_days(as_of: str, last_bar_date: str) -> int:
    try:
        delta = ddate.fromisoformat(as_of) - ddate.fromisoformat(last_bar_date)
    except ValueError:
        return 0
    return max(0, delta.days)


def _filter_asof(rows: Sequence[PriceBar], as_of: str | None) -> list[PriceBar]:
    out = [r for r in rows if not as_of or r.date <= as_of]
    out.sort(key=lambda b: b.date)
    return out


def score_nse_stock(
    rows: Sequence[PriceBar],
    nifty_rows: Sequence[PriceBar],
    *,
    symbol: str | None = None,
    as_of: str | None = None,
) -> AssetScore:
    """Score one NSE stock with the audited M framework (0-100).

    Components:
      - trend: 30 points (close > 200DMA, 50DMA > 200DMA, rising 50DMA)
      - relative_strength: 30 points (63D and 126D excess vs Nifty)
      - delivery_volume: 20 points (volume and delivery vs 20D average)
      - downside_risk: 20 points (20D volatility and 126D max drawdown)

    No D/V component is present. ``data_quality.ok`` is false when history is
    insufficient or the Nifty benchmark is unavailable.
    """
    bars = _filter_asof(rows, as_of)
    if not bars:
        raise LookupError("no NSE bars at or before as_of")
    cutoff = as_of or bars[-1].date
    name = symbol or bars[-1].symbol

    state = StockState(name)
    delivery_history: deque[float] = deque(maxlen=20)
    reasons: list[str] = []
    flags: set[str] = set()

    for row in bars:
        bar = state.update(
            row.date,
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            row.turnover_lacs,
            row.raw_close,
            frozenset(row.flags),
        )
        if bar is not None and row.deliv_per is not None:
            delivery_history.append(float(row.deliv_per))

    if not state.bars:
        raise LookupError("no valid NSE bars after validation")
    last = state.bars[-1]
    closes = list(state.closes)
    if state.n < REQUIRED_BARS:
        flags.add("insufficient_history")
    if last.dma200 is None:
        flags.add("dma200_missing")

    # Trend: 30 points.
    trend = 0.0
    if last.dma200 is not None:
        if last.close > last.dma200:
            trend += 10.0
            reasons.append(
                f"Close {last.close:.2f} above 200DMA {last.dma200:.2f}"
            )
        else:
            reasons.append(
                f"Close {last.close:.2f} below 200DMA {last.dma200:.2f}"
            )
    else:
        reasons.append("200DMA unavailable")

    if last.dma50 is not None and last.dma200 is not None:
        if last.dma50 > last.dma200:
            trend += 10.0
            reasons.append(
                f"50DMA {last.dma50:.2f} above 200DMA {last.dma200:.2f}"
            )
        else:
            reasons.append(
                f"50DMA {last.dma50:.2f} below 200DMA {last.dma200:.2f}"
            )
    else:
        reasons.append("50DMA unavailable")

    if last.dma50_slope is not None:
        if last.dma50_slope > 1e-12:
            trend += 10.0
            reasons.append(
                f"50DMA rising ({last.dma50_slope:+.2f} over 20 sessions)"
            )
        elif abs(last.dma50_slope) <= 1e-12:
            trend += 5.0
            reasons.append("50DMA flat over 20 sessions")
        else:
            reasons.append(
                f"50DMA falling ({last.dma50_slope:+.2f} over 20 sessions)"
            )
    else:
        reasons.append("50DMA slope unavailable")

    # Relative strength vs Nifty: 30 points.
    nifty = _filter_asof(nifty_rows, cutoff)
    nifty_closes = [r.close for r in nifty]
    stock_ret63 = _return(closes, 63)
    stock_ret126 = _return(closes, 126)
    nifty_ret63 = _return(nifty_closes, 63)
    nifty_ret126 = _return(nifty_closes, 126)
    excess63 = (
        stock_ret63 - nifty_ret63
        if stock_ret63 is not None and nifty_ret63 is not None
        else None
    )
    excess126 = (
        stock_ret126 - nifty_ret126
        if stock_ret126 is not None and nifty_ret126 is not None
        else None
    )
    if excess63 is None or excess126 is None:
        flags.add("nifty_missing")
    rs = _excess_points(excess63) + _excess_points(excess126)
    if excess63 is not None:
        reasons.append(f"63D excess vs Nifty {excess63:+.1%}")
    if excess126 is not None:
        reasons.append(f"126D excess vs Nifty {excess126:+.1%}")

    # Delivery and volume: 20 points.
    volume_ratio = (
        last.volume / last.vol20
        if last.vol20 is not None and last.vol20 > 0
        else None
    )
    delivery_ratio = None
    last_delivery = bars[-1].deliv_per
    if last_delivery is None or not delivery_history:
        flags.add("delivery_missing")
        reasons.append("Delivery data missing")
    else:
        average_delivery = sum(delivery_history) / len(delivery_history)
        if average_delivery > 0:
            delivery_ratio = float(last_delivery) / average_delivery
        if len(delivery_history) < 20:
            flags.add("delivery_history_short")
        reasons.append(
            f"Delivery {last_delivery:.1f}% vs "
            f"{average_delivery:.1f}% 20D average"
        )
    volume_pts = _volume_points(volume_ratio)
    delivery_pts = _delivery_points(delivery_ratio)
    if volume_ratio is not None:
        reasons.append(f"Volume {volume_ratio:.2f}x 20D average")
    else:
        reasons.append("Volume average unavailable")

    # Downside risk: 20 points.
    vol20 = _annualised_vol(closes, 20)
    dd126 = _max_drawdown(closes, 126)
    risk = _vol_points(vol20) + _drawdown_points(dd126)
    if vol20 is not None:
        reasons.append(f"20D annualised volatility {vol20:.1%}")
    if dd126 is not None:
        reasons.append(f"126D max drawdown {dd126:.1%}")

    components = {
        "trend": round(trend, 2),
        "relative_strength": round(rs, 2),
        "delivery_volume": round(volume_pts + delivery_pts, 2),
        "downside_risk": round(risk, 2),
    }
    score = round(sum(components.values()), 2)
    quality = DataQuality(
        as_of=cutoff,
        bars=state.n,
        required_bars=REQUIRED_BARS,
        stale_days=_stale_days(cutoff, last.date),
        flags=tuple(sorted(flags)),
    )
    return AssetScore(
        symbol=name,
        asset_class=AssetClass.NSE_EQUITY.value,
        as_of=cutoff,
        score=score,
        band=_band(score),
        components=components,
        reasons=tuple(reasons),
        data_quality=quality,
        engine=ENGINE,
    )


def score_crypto(
    rows: Sequence[PriceBar],
    *,
    symbol: str | None = None,
    as_of: str | None = None,
) -> AssetScore:
    """Score one crypto pair (trend 40, momentum 40, downside risk 20)."""
    bars = _filter_asof(rows, as_of)
    if not bars:
        raise LookupError("no crypto bars at or before as_of")
    cutoff = as_of or bars[-1].date
    name = symbol or bars[-1].symbol
    closes = [r.close for r in bars]
    if len(closes) < REQUIRED_BARS:
        flags = {"insufficient_history"}
    else:
        flags = set()

    dma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    dma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
    ret63 = _return(closes, 63)
    ret126 = _return(closes, 126)
    vol30 = _annualised_vol(closes, 30)
    dd126 = _max_drawdown(closes, 126)
    reasons: list[str] = []

    trend = 0.0
    if dma200 is not None and closes[-1] > dma200:
        trend += 20.0
        reasons.append(f"Close {closes[-1]:.2f} above 200DMA {dma200:.2f}")
    else:
        reasons.append("Close below 200DMA")
    if dma50 is not None and dma200 is not None and dma50 > dma200:
        trend += 20.0
        reasons.append(f"50DMA {dma50:.2f} above 200DMA {dma200:.2f}")
    else:
        reasons.append("50DMA below 200DMA")

    momentum = (
        _crypto_momentum_points(ret63)
        + _crypto_momentum_points(ret126)
    )
    if ret63 is not None:
        reasons.append(f"63D return {ret63:+.1%}")
    if ret126 is not None:
        reasons.append(f"126D return {ret126:+.1%}")

    risk = _crypto_vol_points(vol30) + _crypto_drawdown_points(dd126)
    if vol30 is not None:
        reasons.append(f"30D annualised volatility {vol30:.1%}")
    if dd126 is not None:
        reasons.append(f"126D max drawdown {dd126:.1%}")

    components = {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "downside_risk": round(risk, 2),
    }
    score = round(sum(components.values()), 2)
    quality = DataQuality(
        as_of=cutoff,
        bars=len(bars),
        required_bars=REQUIRED_BARS,
        stale_days=_stale_days(cutoff, bars[-1].date),
        flags=tuple(sorted(flags)),
    )
    return AssetScore(
        symbol=name,
        asset_class=AssetClass.CRYPTO.value,
        as_of=cutoff,
        score=score,
        band=_band(score),
        components=components,
        reasons=tuple(reasons),
        data_quality=quality,
        engine=ENGINE,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", help="NSE symbol, e.g. RELIANCE")
    parser.add_argument("--stock-id", help="continuous NSE stock_id (preferred)")
    parser.add_argument(
        "--crypto",
        choices=sorted(CRYPTO_FILES),
        help="crypto pair, e.g. BTCUSDT",
    )
    parser.add_argument("--as-of", help="last allowed date, YYYY-MM-DD")
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--nifty", default=DEFAULT_NIFTY)
    parser.add_argument("--crypto-dir", default=DEFAULT_CRYPTO_DIR)
    parser.add_argument("--max-bars", type=int, default=320)
    args = parser.parse_args(argv)

    if bool(args.symbol or args.stock_id) == bool(args.crypto):
        parser.error("pass exactly one of --symbol/--stock-id or --crypto")

    if args.crypto:
        rows = load_crypto_rows(
            args.crypto,
            directory=args.crypto_dir,
            as_of=args.as_of,
            max_bars=args.max_bars,
        )
        score = score_crypto(rows, symbol=args.crypto, as_of=args.as_of)
    else:
        rows = load_panel_rows(
            args.panel,
            symbol=args.symbol,
            stock_id=args.stock_id,
            as_of=args.as_of,
            max_bars=args.max_bars,
        )
        nifty = load_nifty_rows(
            args.nifty, as_of=args.as_of, max_bars=args.max_bars
        )
        score = score_nse_stock(
            rows,
            nifty,
            symbol=args.symbol or args.stock_id,
            as_of=args.as_of,
        )

    print(json.dumps(score.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
