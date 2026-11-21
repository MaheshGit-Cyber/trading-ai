"""Deterministic price/volume features for the daily NSE panel.

No external dependencies. One ``StockState`` per symbol, fed one row at a
time. All indicators use only bars seen so far; the caller must not feed a
future row.

Conventions:
- Prices are adjusted prices from ``data/curated/panel.csv``.
- Volume is adjusted volume. Turnover is raw rupees-lakhs (liquidity).
- ``raw_close`` is the unadjusted close, used only for point-in-time price
  filters (a back-adjusted price can be far below the real traded price).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass(slots=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover_lacs: float
    raw_close: float
    dma20: float | None
    dma50: float | None
    dma200: float | None
    dma50_slope: float | None
    atr: float | None
    rsi: float | None
    adx: float | None
    vol20: float | None
    turnover20: float | None
    flags: frozenset[str]


class StockState:
    """Rolling indicator state for one stock."""

    __slots__ = (
        "symbol",
        "bars",
        "closes",
        "volumes",
        "turnovers",
        "sum20",
        "sum50",
        "sum200",
        "vol_sum",
        "turnover_sum",
        "n",
        "prev_close",
        "tr_smooth",
        "plus_smooth",
        "minus_smooth",
        "atr",
        "avg_gain",
        "avg_loss",
        "rsi",
        "dx_values",
        "adx",
        "last_date",
    )

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bars: deque[Bar] = deque(maxlen=260)
        self.closes: deque[float] = deque(maxlen=200)
        self.volumes: deque[float] = deque(maxlen=20)
        self.turnovers: deque[float] = deque(maxlen=20)
        self.sum20 = 0.0
        self.sum50 = 0.0
        self.sum200 = 0.0
        self.vol_sum = 0.0
        self.turnover_sum = 0.0
        self.n = 0
        self.prev_close: float | None = None
        self.tr_smooth = 0.0
        self.plus_smooth = 0.0
        self.minus_smooth = 0.0
        self.atr: float | None = None
        self.avg_gain = 0.0
        self.avg_loss = 0.0
        self.rsi: float | None = None
        self.dx_values: deque[float] = deque(maxlen=14)
        self.adx: float | None = None
        self.last_date: str | None = None

    def update(
        self,
        date: str,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        turnover_lacs: float,
        raw_close: float,
        flags: frozenset[str],
    ) -> Bar | None:
        """Feed one bar. Returns ``None`` if the bar is structurally invalid."""
        vals = (open_, high, low, close, volume, turnover_lacs, raw_close)
        if not all(math.isfinite(v) for v in vals):
            return None
        if close <= 0 or high <= 0 or low <= 0 or open_ <= 0:
            return None
        if high < max(open_, close, low) - 1e-9:
            return None
        if low > min(open_, high, close) + 1e-9:
            return None
        if high < low - 1e-9:
            return None
        if volume < 0 or turnover_lacs < 0:
            return None

        self.n += 1
        prev = self.prev_close

        # True range / directional movement.
        if prev is None:
            tr = high - low
            plus_dm = 0.0
            minus_dm = 0.0
        else:
            tr = max(high - low, abs(high - prev), abs(low - prev))
            up_move = high - self.bars[-1].high
            down_move = self.bars[-1].low - low
            plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        # Wilder ATR and ADX smoothing.
        if self.n <= 14:
            self.tr_smooth += tr
            self.plus_smooth += plus_dm
            self.minus_smooth += minus_dm
            if self.n == 14:
                self.atr = self.tr_smooth / 14.0
        else:
            self.tr_smooth = self.tr_smooth - self.tr_smooth / 14.0 + tr
            self.plus_smooth = self.plus_smooth - self.plus_smooth / 14.0 + plus_dm
            self.minus_smooth = self.minus_smooth - self.minus_smooth / 14.0 + minus_dm
            self.atr = self.tr_smooth / 14.0

        if self.n >= 14:
            if self.tr_smooth > 0:
                plus_di = 100.0 * self.plus_smooth / self.tr_smooth
                minus_di = 100.0 * self.minus_smooth / self.tr_smooth
                denom = plus_di + minus_di
                dx = 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0
            else:
                dx = 0.0
            self.dx_values.append(dx)
            if len(self.dx_values) == 14:
                self.adx = sum(self.dx_values) / 14.0
            elif self.adx is not None:
                self.adx = (self.adx * 13.0 + dx) / 14.0

        # Wilder RSI.
        if prev is None:
            gain = 0.0
            loss = 0.0
        else:
            change = close - prev
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
        if self.n <= 14:
            self.avg_gain += gain
            self.avg_loss += loss
            if self.n == 14:
                self.avg_gain /= 14.0
                self.avg_loss /= 14.0
                self.rsi = self._rsi(self.avg_gain, self.avg_loss)
        else:
            self.avg_gain = (self.avg_gain * 13.0 + gain) / 14.0
            self.avg_loss = (self.avg_loss * 13.0 + loss) / 14.0
            self.rsi = self._rsi(self.avg_gain, self.avg_loss)

        # Rolling sums. Subtract the bar that will fall out of each window
        # before appending the new close.
        if len(self.closes) == 200:
            self.sum200 -= self.closes[0]
        if len(self.closes) >= 50:
            self.sum50 -= self.closes[-50]
        if len(self.closes) >= 20:
            self.sum20 -= self.closes[-20]
        self.closes.append(close)
        self.sum20 += close
        self.sum50 += close
        self.sum200 += close

        if len(self.volumes) >= 20:
            self.vol_sum -= self.volumes[-20]
        self.volumes.append(volume)
        self.vol_sum += volume

        if len(self.turnovers) >= 20:
            self.turnover_sum -= self.turnovers[-20]
        self.turnovers.append(turnover_lacs)
        self.turnover_sum += turnover_lacs

        dma20 = self.sum20 / 20.0 if len(self.closes) >= 20 else None
        dma50 = self.sum50 / 50.0 if len(self.closes) >= 50 else None
        dma200 = self.sum200 / 200.0 if len(self.closes) >= 200 else None
        vol20 = self.vol_sum / 20.0 if len(self.volumes) >= 20 else None
        turnover20 = (
            self.turnover_sum / 20.0
            if len(self.turnovers) >= 20
            else None
        )

        bar = Bar(
            date=date,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            turnover_lacs=turnover_lacs,
            raw_close=raw_close,
            dma20=dma20,
            dma50=dma50,
            dma200=dma200,
            dma50_slope=None,
            atr=self.atr,
            rsi=self.rsi,
            adx=self.adx,
            vol20=vol20,
            turnover20=turnover20,
            flags=flags,
        )
        self.bars.append(bar)

        # 20-session slope of the 50DMA, using only bars already seen.
        if len(self.bars) >= 21:
            old = self.bars[-21].dma50
            if old is not None and bar.dma50 is not None:
                bar.dma50_slope = bar.dma50 - old

        self.prev_close = close
        self.last_date = date
        return bar

    @staticmethod
    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 50.0 if avg_gain == 0 else 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)
