"""Fetch and parse NSE/BSE corporate actions for 2020 -> present.

    python3 jobs/fetch_corporate_actions.py --start 2020-01 --end 2026-11

Why this exists:
  NSE/BSE bhavcopy PREV_CLOSE is the *raw* previous close, not restated for
  splits/bonus. BAJFINANCE on 2025-06-16 shows prev_close 9331 and close 938
  after a 4:1 bonus + 2->1 split. Without an explicit action factor the panel
  would record a fake -90% return.

Sources:
  NSE: https://www.nseindia.com/api/corporates-corporateActions
       index=equities, month by month (the API can silently cap long ranges)
  BSE: https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w
       one call per year; needs a browser-like requests session

Raw JSON is saved under data/corporate_actions/{nse,bse}/.
Parsed rows go to data/corporate_actions/actions.csv.

Action factors:
  BONUS  a:b (a new for every b held) -> b / (a + b)
  SPLIT  old face value -> new face value -> new / old
  RIGHTS a:b at issue price S -> factor is computed at the ex-date using the
         previous close P: (b + a*S/P) / (a + b)
  OTHER  demerger / scheme / capital reduction -> no factor, flagged

NSE subjects are free text; BSE purposes are cleaner but BSE rights issues
usually do not include the ratio/price, so those are flagged as unknown.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from typing import Any

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_NSE = os.path.join(ROOT, "data", "corporate_actions", "nse")
RAW_BSE = os.path.join(ROOT, "data", "corporate_actions", "bse")
OUT = os.path.join(ROOT, "data", "corporate_actions", "actions.csv")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

NSE_ACTIONS = (
    "https://www.nseindia.com/api/corporates-corporateActions"
    "?index=equities&from_date={from_date}&to_date={to_date}"
)
BSE_ACTIONS = (
    "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w"
    "?scripcode=&Fdate={from_date}&TDate={to_date}&Purposecode="
    "&ddlcategorys=E&ddlindustrys=&segment=0&strSearch=S"
)

FIELDS = [
    "source",
    "ex_date",
    "symbol",
    "scrip_code",
    "isin",
    "face_val",
    "action",
    "ratio_a",
    "ratio_b",
    "old_fv",
    "new_fv",
    "issue_price",
    "factor",
    "purpose",
]


def nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": (
                "https://www.nseindia.com/companies-listing/"
                "corporate-filings-actions"
            ),
        }
    )
    session.get(
        "https://www.nseindia.com/companies-listing/corporate-filings-actions",
        timeout=30,
    )
    return session


def bse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.bseindia.com/corporates/corporate_act",
            "Origin": "https://www.bseindia.com",
        }
    )
    session.get("https://www.bseindia.com/corporates/corporate_act", timeout=30)
    return session


def month_range(start: str, end: str):
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    while (year, month) <= (end_year, end_month):
        yield year, month
        month += 1
        if month == 13:
            month = 1
            year += 1


def fetch_nse(session: requests.Session, year: int, month: int, force: bool) -> list[dict]:
    os.makedirs(RAW_NSE, exist_ok=True)
    path = os.path.join(RAW_NSE, f"{year:04d}-{month:02d}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    last_day = calendar.monthrange(year, month)[1]
    from_date = f"01-{month:02d}-{year:04d}"
    to_date = f"{last_day:02d}-{month:02d}-{year:04d}"
    url = NSE_ACTIONS.format(from_date=from_date, to_date=to_date)
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            rows = response.json()
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False)
            return rows
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2.0 * attempt)
            session.get(
                "https://www.nseindia.com/companies-listing/corporate-filings-actions",
                timeout=30,
            )
    return []


def fetch_bse(session: requests.Session, year: int, force: bool) -> list[dict]:
    os.makedirs(RAW_BSE, exist_ok=True)
    path = os.path.join(RAW_BSE, f"{year:04d}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    url = BSE_ACTIONS.format(from_date=f"{year:04d}0101", to_date=f"{year:04d}1231")
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            rows = response.json()
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False)
            return rows
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2.0 * attempt)
            session.get("https://www.bseindia.com/corporates/corporate_act", timeout=30)
    return []


def _num(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def _ratio(text: str) -> tuple[float, float] | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)",
        text,
        re.I,
    )
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def classify(purpose: str, face_val: str) -> dict[str, Any]:
    text = " ".join((purpose or "").split())
    low = text.lower()

    if "bonus" in low:
        # A bonus of NCRPS/preference shares/debentures does not change the
        # equity share count. Do not apply an equity price factor for it.
        if any(
            key in low
            for key in (
                "ncrps",
                "ncd",
                "preference",
                "pref share",
                "debenture",
                "non-convertible",
                "non convertible",
            )
        ):
            return {"action": "BONUS_NON_EQUITY", "factor": None}
        ratio = _ratio(text)
        if ratio:
            a, b = ratio
            if a > 0 and b > 0:
                return {
                    "action": "BONUS",
                    "ratio_a": a,
                    "ratio_b": b,
                    "factor": b / (a + b),
                }
        return {"action": "BONUS_UNKNOWN", "factor": None}

    if any(
        key in low
        for key in (
            "split",
            "sub-division",
            "sub division",
            "subdivision",
            "consolidation",
        )
    ):
        match = re.search(
            r"from\s*(?:rs\.?|re\.?)?\s*(\d+(?:\.\d+)?)"
            r".*?to\s*(?:rs\.?|re\.?)?\s*(\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if match:
            old_fv = float(match.group(1))
            new_fv = float(match.group(2))
            if old_fv > 0 and new_fv > 0:
                return {
                    "action": "SPLIT",
                    "old_fv": old_fv,
                    "new_fv": new_fv,
                    "factor": new_fv / old_fv,
                }
        return {"action": "SPLIT_UNKNOWN", "factor": None}

    if "right" in low:
        ratio = _ratio(text)
        premium = None
        match = re.search(
            r"premium\s*(?:rs\.?|re\.?)?\s*(\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if match:
            premium = float(match.group(1))
        issue_price = None
        fv = _num(face_val)
        if fv is not None and premium is not None:
            issue_price = fv + premium
        if ratio and issue_price is not None:
            return {
                "action": "RIGHTS",
                "ratio_a": ratio[0],
                "ratio_b": ratio[1],
                "issue_price": issue_price,
                "factor": None,
            }
        return {
            "action": "RIGHTS_UNKNOWN",
            "ratio_a": ratio[0] if ratio else None,
            "ratio_b": ratio[1] if ratio else None,
            "issue_price": issue_price,
            "factor": None,
        }

    if any(
        key in low
        for key in (
            "demerger",
            "scheme of arrangement",
            "capital reduction",
            "reduction of capital",
            "spin off",
            "spin-off",
        )
    ):
        return {"action": "OTHER", "factor": None}

    if any(
        key in low
        for key in (
            "dividend",
            "distribution",
            "interest payment",
            "buy back",
            "buyback",
        )
    ):
        return {"action": "IGNORE", "factor": None}

    return {"action": "UNKNOWN", "factor": None}


def parse_nse(row: dict) -> dict[str, Any] | None:
    ex_date = row.get("exDate")
    symbol = (row.get("symbol") or "").strip()
    if not ex_date or not symbol:
        return None
    try:
        day = dt.datetime.strptime(ex_date, "%d-%b-%Y").date()
    except ValueError:
        return None
    purpose = (row.get("subject") or "").strip()
    info = classify(purpose, row.get("faceVal") or "")
    return {
        "source": "NSE",
        "ex_date": day.isoformat(),
        "symbol": symbol,
        "scrip_code": "",
        "isin": (row.get("isin") or "").strip(),
        "face_val": (row.get("faceVal") or "").strip(),
        "purpose": purpose,
        **info,
    }


def parse_bse(row: dict) -> dict[str, Any] | None:
    symbol = (row.get("short_name") or "").strip()
    scrip_code = str(row.get("scrip_code") or "").strip()
    ex_date = row.get("exdate")
    if not ex_date or not scrip_code:
        return None
    try:
        day = dt.datetime.strptime(str(ex_date), "%Y%m%d").date()
    except ValueError:
        try:
            day = dt.datetime.strptime(row.get("Ex_date", ""), "%d %b %Y").date()
        except ValueError:
            return None
    purpose = (row.get("Purpose") or "").strip()
    info = classify(purpose, "")
    return {
        "source": "BSE",
        "ex_date": day.isoformat(),
        "symbol": symbol,
        "scrip_code": scrip_code,
        "isin": "",
        "face_val": "",
        "purpose": purpose,
        **info,
    }


def write_actions(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows.sort(key=lambda row: (row["source"], row["ex_date"], row["symbol"], row["scrip_code"]))
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01")
    parser.add_argument("--end", default=dt.date.today().strftime("%Y-%m"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="reparse saved raw JSON without making network requests",
    )
    args = parser.parse_args()

    os.makedirs(RAW_NSE, exist_ok=True)
    os.makedirs(RAW_BSE, exist_ok=True)

    actions: list[dict] = []
    if args.parse_only:
        for year, month in month_range(args.start, args.end):
            path = os.path.join(RAW_NSE, f"{year:04d}-{month:02d}.json")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                rows = json.load(handle)
            parsed = [parse_nse(row) for row in rows]
            actions.extend(row for row in parsed if row)
            print(
                f"[NSE] {year}-{month:02d}: {len(rows)} raw, {len(parsed)} parsed",
                flush=True,
            )
        for year in range(int(args.start[:4]), int(args.end[:4]) + 1):
            path = os.path.join(RAW_BSE, f"{year:04d}.json")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                rows = json.load(handle)
            parsed = [parse_bse(row) for row in rows]
            actions.extend(row for row in parsed if row)
            print(f"[BSE] {year}: {len(rows)} raw, {len(parsed)} parsed", flush=True)
    else:
        nse = nse_session()
        for year, month in month_range(args.start, args.end):
            rows = fetch_nse(nse, year, month, args.force)
            parsed = [parse_nse(row) for row in rows]
            actions.extend(row for row in parsed if row)
            print(
                f"[NSE] {year}-{month:02d}: {len(rows)} raw, {len(parsed)} parsed",
                flush=True,
            )
            time.sleep(0.15)

        bse = bse_session()
        for year in range(int(args.start[:4]), int(args.end[:4]) + 1):
            rows = fetch_bse(bse, year, args.force)
            parsed = [parse_bse(row) for row in rows]
            actions.extend(row for row in parsed if row)
            print(f"[BSE] {year}: {len(rows)} raw, {len(parsed)} parsed", flush=True)
            time.sleep(0.2)

    write_actions(actions)
    counts: dict[str, int] = {}
    for row in actions:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    print(f"wrote {len(actions)} actions -> {os.path.relpath(OUT, ROOT)}")
    print("counts:", dict(sorted(counts.items())))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted] raw files already saved; rerun to resume", flush=True)
        sys.exit(130)
