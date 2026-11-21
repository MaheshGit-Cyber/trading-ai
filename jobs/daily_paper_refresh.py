#!/usr/bin/env python3
"""Daily paper-ledger refresh: Nifty -> bhavcopy -> Gold BeES -> snapshot.

Designed for a post-close scheduler (after 18:00 IST). It never invents a
session:

- updates completed Nifty bars from Yahoo research data
- refuses a date that is not present in the Nifty file
- fetches NSE bhavcopy; a holiday/failed fetch means no snapshot
- rebuilds the Gold BeES file from raw bhavcopies
- records one append-only snapshot; duplicates are a no-op

No broker, order, real money or UI.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.memory import AgentMemory  # noqa: E402
from brain.data import DEFAULT_NIFTY, load_nifty_rows  # noqa: E402
from brain.paper import (  # noqa: E402
    DEFAULT_GOLD,
    DEFAULT_PAPER_DIR,
    build_snapshot,
    load_snapshots,
    record_snapshot,
)

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
LOG = os.path.join(DEFAULT_PAPER_DIR, "daily_refresh.log")


def log(msg: str) -> None:
    line = f"{datetime.now(IST).isoformat(timespec='seconds')} {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_job(script: str, *args: str, timeout: int = 180) -> tuple[int, str]:
    cmd = [sys.executable, os.path.join(ROOT, "jobs", script), *args]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )
    out = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return proc.returncode, out


def latest_nifty_date() -> str:
    rows = load_nifty_rows(DEFAULT_NIFTY, max_bars=10_000)
    return rows[-1].date


def already_recorded(root: str, day: str) -> bool:
    return any(s.as_of == day for s in load_snapshots(root))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", help="signal date; defaults to latest completed Nifty bar")
    p.add_argument("--capital", type=float, default=1_000_000)
    p.add_argument("--risk-score", type=int, default=7)
    p.add_argument("--root", default=DEFAULT_PAPER_DIR)
    p.add_argument("--no-update-nifty", action="store_true")
    p.add_argument("--no-fetch", action="store_true", help="reuse existing bhavcopy/gold")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.no_update_nifty:
        code, out = run_job("update_nifty_from_yahoo.py", timeout=60)
        log(f"nifty_update rc={code} {out[-300:]}")
        if code != 0:
            log("Nifty update failed; continuing with existing local bars")

    latest = latest_nifty_date()
    day = args.date or latest
    if day > latest:
        log(f"refused: {day} is after latest Nifty bar {latest}")
        return 2
    dates = {r.date for r in load_nifty_rows(DEFAULT_NIFTY, as_of=day, max_bars=10_000)}
    if day not in dates:
        log(f"refused: {day} is not a Nifty session in local data")
        return 2
    if already_recorded(args.root, day):
        log(f"no-op: {day} already recorded")
        return 0
    if args.dry_run:
        log(f"dry-run: would record {day} from {latest}")
        return 0

    if not args.no_fetch:
        code, out = run_job("fetch_bhavcopy.py", "--date", day, timeout=120)
        log(f"bhavcopy rc={code} {out[-400:]}")
        if code != 0:
            log(f"no snapshot: bhavcopy unavailable for {day} (holiday/network?)")
            return 2
        code, out = run_job("extract_goldbees.py", timeout=120)
        log(f"goldbees rc={code} {out[-300:]}")
        if code != 0:
            log("no snapshot: Gold BeES extraction failed")
            return 2

    rows = load_nifty_rows(DEFAULT_NIFTY, as_of=day, max_bars=320)
    try:
        snap = build_snapshot(
            rows,
            capital=args.capital,
            risk_score=args.risk_score,
            gold_path=DEFAULT_GOLD,
            as_of=day,
        )
    except Exception as exc:
        log(f"no snapshot: build failed: {exc}")
        return 2
    if snap.as_of != day:
        log(f"no snapshot: allocator date {snap.as_of} != requested {day}")
        return 2
    try:
        path, ledger = record_snapshot(snap, root=args.root)
    except FileExistsError as exc:
        log(f"no-op: {exc}")
        return 0
    log(f"recorded {day} -> {path}")
    try:
        AgentMemory().append(
            "paper",
            f"paper snapshot recorded for {day}",
            snap.to_dict(),
            source="daily_paper_refresh",
            tags=("paper", "phase4b"),
        )
    except Exception as exc:
        log(f"memory append warning: {exc}")
    print(json.dumps({"as_of": day, "snapshot": path, "ledger": ledger}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
