"""Backfill NSE full bhavcopy, 2020 -> present. Resumable.

    python3 jobs/backfill_bhavcopy.py --start 2020-01-01 --end 2026-11-19

Properties:
  - Skips days whose output file already exists and is non-empty.
  - Rejects holiday duplicates via fetch_bhavcopy.HolidayGate.
  - Retries transient network errors with backoff.
  - Writes each day atomically (tmp + os.replace).
  - Polite delay between requests (default 0.25 s).

No pandas, no pyarrow. One CSV per trading day in data/raw/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_bhavcopy import RAW, HolidayGate, download_day, write_day


def weekdays(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += dt.timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--limit", type=int, default=0, help="max weekdays to process")
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if start > end:
        raise SystemExit("start is after end")

    os.makedirs(RAW, exist_ok=True)
    ok = skipped = holidays = 0
    failed: list[tuple[str, str]] = []
    processed = 0
    t0 = time.time()

    for day in weekdays(start, end):
        if args.limit and processed >= args.limit:
            break
        processed += 1
        out = os.path.join(RAW, f"bhavcopy_{day.isoformat()}.csv")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            skipped += 1
            continue

        for attempt in range(1, args.retries + 1):
            try:
                _, eq = download_day(day)
                write_day(day, eq)
                ok += 1
                break
            except HolidayGate as exc:
                holidays += 1
                print(f"[holiday] {exc}", flush=True)
                break
            except Exception as exc:  # network / parse
                if attempt >= args.retries:
                    failed.append((day.isoformat(), str(exc)[:160]))
                    print(f"[fail] {day}: {exc}", flush=True)
                else:
                    time.sleep(1.5 * attempt)

        if processed % 50 == 0:
            elapsed = time.time() - t0
            print(
                f"[progress] {processed} weekdays | ok={ok} skip={skipped} "
                f"holiday={holidays} fail={len(failed)} | {elapsed:.0f}s",
                flush=True,
            )
        time.sleep(args.sleep)

    elapsed = time.time() - t0
    print(
        f"\n[done] weekdays={processed} ok={ok} skipped={skipped} "
        f"holidays={holidays} failed={len(failed)} in {elapsed:.0f}s",
        flush=True,
    )
    if failed:
        print("[failed dates]", flush=True)
        for day, err in failed[:20]:
            print(f"  {day}: {err}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted] partial files are safe; rerun to resume", flush=True)
        sys.exit(130)
