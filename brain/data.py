"""Point-in-time readers for the local research files.

No network calls. Every loader stops at ``as_of`` so the scorer cannot see a
future bar. The panel is large (~6.7M rows); a SQLite byte-offset index is used
when present, otherwise the loader streams the CSV once. The contract and the
score are look-ahead-free either way.
"""

from __future__ import annotations

from collections import deque
import csv
from dataclasses import dataclass
from datetime import date as ddate, timedelta
import os
import sqlite3

from brain.panel_index import query_rows as _query_index_rows

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_PANEL = os.path.join(
    ROOT, "data", "curated", "panel_nse_isin_v3.csv"
)
DEFAULT_NIFTY = os.path.join(ROOT, "data", "index", "nifty50.csv")
DEFAULT_CRYPTO_DIR = os.path.join(ROOT, "data", "crypto")
DEFAULT_ACTIONS = os.path.join(
    ROOT, "data", "corporate_actions", "actions.csv"
)
DEFAULT_PANEL_INDEX = os.path.join(ROOT, "data", "brain", "panel_index.sqlite")

CRYPTO_FILES = {
    "BTCUSDT": "btcusdt_daily_2017_2026.csv",
    "ETHUSDT": "ethusdt_daily_2017_2026.csv",
    "SOLUSDT": "solusdt_daily_2017_2026.csv",
    "BNBUSDT": "bnbusdt_daily_2017_2026.csv",
    "XRPUSDT": "xrpusdt_daily_2017_2026.csv",
}


def _num(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number


def _flags(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    parts = text.replace("|", ",").split(",")
    return tuple(sorted({p.strip() for p in parts if p.strip()}))


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One adjusted OHLCV bar. ``raw_close`` is only for price filters."""

    date: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover_lacs: float
    raw_close: float
    deliv_per: float | None = None
    flags: tuple[str, ...] = ()
    isin: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.date, str) or not self.date:
            raise ValueError("bar.date required")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("bar.symbol required")
        if not all(
            isinstance(x, (int, float)) and not isinstance(x, bool)
            for x in (
                self.open,
                self.high,
                self.low,
                self.close,
                self.volume,
                self.turnover_lacs,
                self.raw_close,
            )
        ):
            raise TypeError("bar prices/volume must be numeric")
        if min(self.open, self.high, self.low, self.close, self.raw_close) <= 0:
            raise ValueError("bar prices must be > 0")
        if self.high < max(self.open, self.close, self.low) - 1e-9:
            raise ValueError("bar.high is inconsistent")
        if self.low > min(self.open, self.high, self.close) + 1e-9:
            raise ValueError("bar.low is inconsistent")
        if self.volume < 0 or self.turnover_lacs < 0:
            raise ValueError("bar volume/turnover must be >= 0")
        if self.deliv_per is not None:
            if not isinstance(self.deliv_per, (int, float)):
                raise TypeError("bar.deliv_per must be numeric or None")
            if not 0 <= float(self.deliv_per) <= 100:
                raise ValueError("bar.deliv_per must be in [0, 100]")


def _panel_bar(row: dict[str, str]) -> PriceBar | None:
    symbol = (row.get("symbol") or "").strip().upper()
    date = (row.get("date") or "").strip()
    if not symbol or not date:
        return None
    close = _num(row.get("adj_close")) or _num(row.get("close"))
    open_ = _num(row.get("adj_open")) or _num(row.get("open"))
    high = _num(row.get("adj_high")) or _num(row.get("high"))
    low = _num(row.get("adj_low")) or _num(row.get("low"))
    volume = _num(row.get("adj_volume")) or _num(row.get("volume")) or 0.0
    raw_close = _num(row.get("close")) or close
    deliv = _num(row.get("deliv_per"))
    try:
        return PriceBar(
            date=date,
            symbol=symbol,
            open=float(open_ or 0),
            high=float(high or 0),
            low=float(low or 0),
            close=float(close or 0),
            volume=float(volume),
            turnover_lacs=float(_num(row.get("turnover_lacs")) or 0.0),
            raw_close=float(raw_close or 0),
            deliv_per=deliv,
            flags=_flags(row.get("flags")),
            isin=(row.get("isin") or "").strip().upper(),
        )
    except (TypeError, ValueError):
        return None


def load_panel_rows(
    path: str = DEFAULT_PANEL,
    *,
    symbol: str | None = None,
    stock_id: str | None = None,
    as_of: str | None = None,
    max_bars: int = 320,
    index_path: str | None = None,
) -> list[PriceBar]:
    """Load the last ``max_bars`` rows for one stock, inclusive of ``as_of``.

    ``stock_id`` is safer than ``symbol`` because it survives symbol changes.
    A lookup with neither is rejected rather than scanning/returning all rows.

    If an offset index exists, the loader seeks only the matching lines. The
    default index is used only with the default panel; a caller passing a
    different CSV must pass ``index_path`` explicitly. Missing/corrupt indexes
    fall back to streaming.
    """
    if not symbol and not stock_id:
        raise ValueError("pass symbol or stock_id")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if max_bars < 1:
        raise ValueError("max_bars must be >= 1")
    want_symbol = symbol.strip().upper() if symbol else None
    resolved_index = index_path
    if resolved_index is None and os.path.abspath(path) == os.path.abspath(DEFAULT_PANEL):
        resolved_index = DEFAULT_PANEL_INDEX
    if resolved_index and os.path.exists(resolved_index):
        try:
            raw_rows = _query_index_rows(
                path,
                resolved_index,
                symbol=symbol,
                stock_id=stock_id,
                as_of=as_of,
                max_bars=max_bars,
            )
        except (FileNotFoundError, LookupError, sqlite3.DatabaseError):
            raw_rows = None
        if raw_rows:
            rows = []
            for raw in raw_rows:
                date = (raw.get("date") or "").strip()
                if as_of and date > as_of:
                    continue
                if stock_id and (raw.get("stock_id") or "").strip() != stock_id:
                    continue
                if want_symbol and (raw.get("symbol") or "").strip().upper() != want_symbol:
                    continue
                bar = _panel_bar(raw)
                if bar is not None:
                    rows.append(bar)
            rows.sort(key=lambda b: b.date)
            if rows:
                return rows

    keep: deque[PriceBar] = deque(maxlen=max_bars)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            date = (row.get("date") or "").strip()
            if as_of and date > as_of:
                continue
            if stock_id and (row.get("stock_id") or "").strip() != stock_id:
                continue
            if want_symbol and (row.get("symbol") or "").strip().upper() != want_symbol:
                continue
            bar = _panel_bar(row)
            if bar is not None:
                keep.append(bar)
    rows = list(keep)
    rows.sort(key=lambda b: b.date)
    if not rows:
        target = stock_id or symbol
        raise LookupError(f"no rows for {target!r} up to {as_of!r}")
    return rows


def load_nifty_rows(
    path: str = DEFAULT_NIFTY,
    *,
    as_of: str | None = None,
    max_bars: int = 320,
) -> list[PriceBar]:
    """Load Nifty 50 index closes up to ``as_of``."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    keep: deque[PriceBar] = deque(maxlen=max_bars)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            date = (row.get("date") or "").strip()
            if as_of and date > as_of:
                continue
            close = _num(row.get("close"))
            if not date or not close:
                continue
            try:
                keep.append(
                    PriceBar(
                        date=date,
                        symbol="NIFTY50",
                        open=float(_num(row.get("open")) or close),
                        high=float(_num(row.get("high")) or close),
                        low=float(_num(row.get("low")) or close),
                        close=float(close),
                        volume=0.0,
                        turnover_lacs=0.0,
                        raw_close=float(close),
                    )
                )
            except (TypeError, ValueError):
                continue
    rows = list(keep)
    rows.sort(key=lambda b: b.date)
    if not rows:
        raise LookupError(f"no Nifty rows up to {as_of!r}")
    return rows


def crypto_path(symbol: str, directory: str = DEFAULT_CRYPTO_DIR) -> str:
    key = symbol.strip().upper()
    if key not in CRYPTO_FILES:
        raise ValueError(
            f"unknown crypto symbol {symbol!r}; expected {sorted(CRYPTO_FILES)}"
        )
    return os.path.join(directory, CRYPTO_FILES[key])


def load_crypto_rows(
    symbol: str,
    *,
    directory: str = DEFAULT_CRYPTO_DIR,
    as_of: str | None = None,
    max_bars: int = 320,
) -> list[PriceBar]:
    """Load Binance daily OHLCV for one supported crypto pair."""
    path = crypto_path(symbol, directory)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    key = symbol.strip().upper()
    keep: deque[PriceBar] = deque(maxlen=max_bars)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            date = (row.get("date") or "").strip()
            if as_of and date > as_of:
                continue
            close = _num(row.get("close"))
            if not date or not close:
                continue
            try:
                keep.append(
                    PriceBar(
                        date=date,
                        symbol=key,
                        open=float(_num(row.get("open")) or close),
                        high=float(_num(row.get("high")) or close),
                        low=float(_num(row.get("low")) or close),
                        close=float(close),
                        volume=float(_num(row.get("volume")) or 0.0),
                        turnover_lacs=0.0,
                        raw_close=float(close),
                    )
                )
            except (TypeError, ValueError):
                continue
    rows = list(keep)
    rows.sort(key=lambda b: b.date)
    if not rows:
        raise LookupError(f"no crypto rows for {key} up to {as_of!r}")
    return rows


@dataclass(frozen=True, slots=True)
class ActionEvent:
    """One corporate-action row. ``IGNORE`` is still useful as a warning."""

    ex_date: str
    symbol: str
    isin: str
    source: str
    action: str
    purpose: str

    def __post_init__(self) -> None:
        if not self.ex_date:
            raise ValueError("action.ex_date required")
        if not self.symbol and not self.isin:
            raise ValueError("action needs symbol or isin")


def load_actions(
    path: str = DEFAULT_ACTIONS,
    *,
    as_of: str | None = None,
    horizon_days: int | None = None,
    symbol: str | None = None,
    isin: str | None = None,
    max_events: int = 10_000,
) -> list[ActionEvent]:
    """Load future corporate actions for one symbol/ISIN.

    ``as_of`` + ``horizon_days`` select the event-shield window. If ``as_of``
    is omitted, the loader returns matching rows without a date window. An
    ISIN match is preferred; a symbol match is used only when the action row
    has no ISIN (BSE rows often do not).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if horizon_days is not None:
        if horizon_days < 0:
            raise ValueError("horizon_days must be >= 0")
        if not as_of:
            raise ValueError("as_of is required when horizon_days is set")
    start = as_of
    end = None
    if as_of and horizon_days is not None:
        end = (ddate.fromisoformat(as_of) + timedelta(days=horizon_days)).isoformat()
    want_symbol = symbol.strip().upper() if symbol else None
    want_isin = isin.strip().upper() if isin else None
    out: list[ActionEvent] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ex_date = (row.get("ex_date") or "").strip()
            if not ex_date:
                continue
            if start and ex_date < start:
                continue
            if end and ex_date > end:
                continue
            row_symbol = (row.get("symbol") or "").strip().upper()
            row_isin = (row.get("isin") or "").strip().upper()
            matched = False
            if want_isin:
                matched = row_isin == want_isin
                if not matched and not row_isin and want_symbol:
                    matched = row_symbol == want_symbol
            elif want_symbol:
                matched = row_symbol == want_symbol
            else:
                matched = True
            if not matched:
                continue
            try:
                event = ActionEvent(
                    ex_date=ex_date,
                    symbol=row_symbol,
                    isin=row_isin,
                    source=(row.get("source") or "").strip().upper(),
                    action=(row.get("action") or "").strip().upper(),
                    purpose=(row.get("purpose") or "").strip(),
                )
            except ValueError:
                continue
            out.append(event)
            if len(out) >= max_events:
                break
    out.sort(key=lambda e: e.ex_date)
    return out
