"""Live IST clock and market-session context.

The agent can read time; it cannot use time to claim a trade. Milliseconds are
included for logs and intraday work, not because a daily strategy needs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as ddate, datetime, time, timedelta, timezone
import os
from typing import Iterable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_PANEL_DATES = os.path.join(ROOT, "data", "index", "panel_dates.txt")
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_OPEN = time(9, 0)
POST_CLOSE = time(16, 0)


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    utc_iso: str
    ist_iso: str
    date_ddmmyyyy: str
    time_hhmmssmmm: str
    epoch_ms: int
    weekday: str
    market_phase: str
    is_weekday: bool
    trading_day_status: str
    trading_day_source: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "utc_iso": self.utc_iso,
            "ist_iso": self.ist_iso,
            "date_ddmmyyyy": self.date_ddmmyyyy,
            "time_hhmmssmmm": self.time_hhmmssmmm,
            "epoch_ms": self.epoch_ms,
            "weekday": self.weekday,
            "market_phase": self.market_phase,
            "is_weekday": self.is_weekday,
            "trading_day_status": self.trading_day_status,
            "trading_day_source": self.trading_day_source,
            "note": self.note,
        }


def load_trading_dates(path: str = DEFAULT_PANEL_DATES) -> set[str]:
    if not os.path.exists(path):
        return set()
    out: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            day = line.strip()
            if day and len(day) == 10 and day[4] == "-" and day[7] == "-":
                out.add(day)
    return out


def market_phase(dt: datetime) -> str:
    """Weekend/phase label. Does not know exchange holidays."""
    if dt.weekday() >= 5:
        return "weekend"
    t = dt.timetz().replace(tzinfo=None)
    if t < PRE_OPEN:
        return "pre_market"
    if t < MARKET_OPEN:
        return "pre_open"
    if t < MARKET_CLOSE:
        return "open"
    if t < POST_CLOSE:
        return "post_close"
    return "closed"


def trading_day_status(
    day: str,
    trading_dates: Iterable[str],
    *,
    source: str = DEFAULT_PANEL_DATES,
) -> str:
    """Classify a date without pretending to know a future holiday calendar."""
    dates = set(trading_dates)
    try:
        d = ddate.fromisoformat(day)
    except ValueError:
        return "invalid_date"
    if d.weekday() >= 5:
        return "weekend"
    if day in dates:
        return "trading_day"
    if dates and day > max(dates):
        return "unknown_future"
    if dates:
        return "not_in_data"
    return "unknown_no_calendar"


def snapshot(
    dt: datetime | None = None,
    *,
    trading_dates: Iterable[str] | None = None,
    source: str = DEFAULT_PANEL_DATES,
) -> ClockSnapshot:
    dt = dt or datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    utc = dt.astimezone(timezone.utc)
    ist = dt.astimezone(IST)
    dates = set(trading_dates) if trading_dates is not None else load_trading_dates(source)
    day = ist.date().isoformat()
    status = trading_day_status(day, dates, source=source)
    note = ""
    if status == "unknown_future":
        note = "Future exchange holiday calendar not loaded; do not assume a session exists."
    elif status == "not_in_data":
        note = "Weekday is absent from the local trading-date file; possible holiday or data gap."
    elif status == "unknown_no_calendar":
        note = "No local trading-date file; market phase is weekday/time only."
    return ClockSnapshot(
        utc_iso=utc.isoformat(timespec="milliseconds"),
        ist_iso=ist.isoformat(timespec="milliseconds"),
        date_ddmmyyyy=ist.strftime("%d-%m-%Y"),
        time_hhmmssmmm=ist.strftime("%H:%M:%S.") + f"{ist.microsecond // 1000:03d}",
        epoch_ms=int(utc.timestamp() * 1000),
        weekday=ist.strftime("%A"),
        market_phase=market_phase(ist),
        is_weekday=ist.weekday() < 5,
        trading_day_status=status,
        trading_day_source=source if os.path.exists(source) else "missing",
        note=note,
    )
