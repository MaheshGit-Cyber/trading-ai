#!/usr/bin/env python3
"""Fetch NSE bhavcopy for Nifty trading dates missing from data/raw.

The weekday backfill intentionally skips Saturdays/Sundays. NSE occasionally
holds special sessions on a Saturday (for example 2025-02-01), and Nifty has a
row for those dates. This script uses the Nifty calendar as the authority and
only fetches dates that are absent from data/raw.

    python3 jobs/backfill_missing_calendar_days.py --start 2010-01-01 --end 2026-11-19
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_bhavcopy import RAW, HolidayGate, download_day, write_day


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nifty", default="data/index/nifty50.csv")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-11-19")
    ap.add_argument("--sleep", type=float, default=0.10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    dates = []
    with open(args.nifty, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("date") or "").strip()
            if d and (row.get("close") or "").strip() and args.start <= d <= args.end:
                dates.append(d)
    dates = sorted(set(dates))

    os.makedirs(RAW, exist_ok=True)
    ok = skipped = holidays = 0
    failed = []
    processed = 0
    for d in dates:
        if args.limit and processed >= args.limit:
            break
        processed += 1
        out = os.path.join(RAW, f"bhavcopy_{d}.csv")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            skipped += 1
            continue
        day = dt.date.fromisoformat(d)
        try:
            _, eq = download_day(day)
            write_day(day, eq)
            ok += 1
            print(f"[ok] {d} eq={len(eq)}", flush=True)
        except HolidayGate as exc:
            holidays += 1
            print(f"[holiday] {exc}", flush=True)
        except Exception as exc:
            failed.append((d, str(exc)[:160]))
            print(f"[fail] {d}: {exc}", flush=True)
        time.sleep(args.sleep)

    print(
        f"[done] dates={processed} ok={ok} skipped={skipped} "
        f"holidays={holidays} failed={len(failed)}",
        flush=True,
    )
    for d, err in failed[:20]:
        print(f"  {d}: {err}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted] rerun to resume", flush=True)
        sys.exit(130)
