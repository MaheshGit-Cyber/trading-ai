#!/usr/bin/env python3
"""Append completed Nifty 50 daily bars from Yahoo Finance (research only).

    python3 jobs/update_nifty_from_yahoo.py \
        --target data/index/nifty50.csv \
        --target data/index/nifty50_2010_2026.csv

Rules:
  - Yahoo ^NSEI is research data, not licensed NSE data.
  - Never overwrite a valid close with a different value.
  - Fill a blank close (the current file can contain a partial row).
  - Never append today's row before the NSE close (15:30 IST); wait until 16:00.
  - Only append dates after the last complete row; do not silently backfill gaps.
  - Atomic CSV replace. No pandas, no network in tests.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date as ddate, datetime, time, timedelta, timezone
import json
import math
import os
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGETS = [
    os.path.join(ROOT, "data", "index", "nifty50.csv"),
    os.path.join(ROOT, "data", "index", "nifty50_2010_2026.csv"),
]
URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
    "?range={range}&interval=1d"
)
IST = timezone(timedelta(hours=5, minutes=30))
FIELDS = ["date", "open", "high", "low", "close", "volume"]


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def fetch_yahoo(range_: str = "1mo") -> list[dict]:
    req = urllib.request.Request(
        URL.format(range=range_),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows: list[dict] = []
    for i, ts in enumerate(timestamps):
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        o, h, l, c = (_num(quote[k][i]) for k in ("open", "high", "low", "close"))
        if not all(v is not None and v > 0 for v in (o, h, l, c)):
            continue
        if h < l or not (l <= o <= h) or not (l <= c <= h):
            continue
        volume = _num(quote.get("volume", [None] * len(timestamps))[i]) or 0.0
        rows.append(
            {
                "date": day,
                "open": f"{o:.10f}",
                "high": f"{h:.10f}",
                "low": f"{l:.10f}",
                "close": f"{c:.10f}",
                "volume": f"{max(0.0, volume):.0f}",
            }
        )
    rows.sort(key=lambda r: r["date"])
    return rows


def update_csv(path: str, fetched: list[dict], *, now: datetime | None = None) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    ready_today = now.time() >= time(16, 0)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path}: no header")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    for required in ("date", "open", "high", "low", "close", "volume"):
        if required not in fieldnames:
            raise ValueError(f"{path}: missing column {required}")
    if not rows:
        raise ValueError(f"{path}: no data rows")
    by_date: dict[str, dict] = {}
    for row in rows:
        day = (row.get("date") or "").strip()
        if not day:
            raise ValueError(f"{path}: blank date")
        if day in by_date:
            raise ValueError(f"{path}: duplicate date {day}")
        by_date[day] = row
    last = max(by_date)
    added = filled = skipped = 0
    for item in fetched:
        day = item["date"]
        if day > today or (day == today and not ready_today):
            skipped += 1
            continue
        if day < last and day not in by_date:
            skipped += 1
            continue
        current = by_date.get(day)
        if current is None:
            rows.append(item)
            by_date[day] = item
            last = max(last, day)
            added += 1
            continue
        old = _num(current.get("close"))
        new = _num(item.get("close"))
        if old is None or old <= 0:
            for key in ("open", "high", "low", "close", "volume"):
                current[key] = item[key]
            filled += 1
        elif new is not None and abs(old - new) > 1e-6:
            raise ValueError(
                f"{path}: {day} close mismatch: file={old} yahoo={new}; "
                "refusing to overwrite"
            )
        else:
            skipped += 1
    rows.sort(key=lambda r: (r.get("date") or "").strip())
    fd, tmp = tempfile.mkstemp(prefix=".nifty-", suffix=".csv", dir=os.path.dirname(path))
    os.close(fd)
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {
        "path": path,
        "rows": len(rows),
        "last": rows[-1]["date"],
        "added": added,
        "filled": filled,
        "skipped": skipped,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", action="append", default=None)
    p.add_argument("--range", default="1mo")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    targets = args.target or DEFAULT_TARGETS
    fetched = fetch_yahoo(args.range)
    print(f"yahoo rows: {len(fetched)}; latest={fetched[-1]['date'] if fetched else None}")
    if args.dry_run:
        print(json.dumps(fetched[-5:], indent=2))
        return 0
    for path in targets:
        result = update_csv(path, fetched)
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
