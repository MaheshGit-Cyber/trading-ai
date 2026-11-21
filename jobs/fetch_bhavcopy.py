"""Phase 0: fetch one NSE full bhavcopy day, validate it, normalise it.

    python3 jobs/fetch_bhavcopy.py --date 2026-11-19

Hard gates (from docs/phase0-findings.md, all measured on device):
  1. A browser User-Agent is required; without one NSE returns 403.
  2. On a non-trading day NSE returns HTTP 200 with the previous day's file.
     Reject any file whose DATE1 != the requested date. This is a gate, not
     a warning -- duplicates corrupt returns and fake corporate actions.
  3. Keep SERIES == "EQ" only. Delivery data is present for EQ, except
     the 2022-08-08 old-archive fallback, which has no delivery columns.

Output: data/raw/bhavcopy_YYYY-MM-DD.csv with snake_case columns.
No pandas, no pyarrow -- csv + urllib + zipfile only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys
import urllib.error
import urllib.request
import zipfile

URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
OLD_URL = (
    "https://archives.nseindia.com/content/historical/EQUITIES/"
    "{yyyy}/{mmm}/cm{dd}{mmm}{yyyy}bhav.csv.zip"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/csv,application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "raw")

# NSE header -> our column. NSE headers sometimes carry leading spaces.
COLS = [
    ("SYMBOL", "symbol"),
    ("SERIES", "series"),
    ("DATE1", "date"),
    ("PREV_CLOSE", "prev_close"),
    ("OPEN_PRICE", "open"),
    ("HIGH_PRICE", "high"),
    ("LOW_PRICE", "low"),
    ("LAST_PRICE", "last"),
    ("CLOSE_PRICE", "close"),
    ("AVG_PRICE", "avg"),
    ("TTL_TRD_QNTY", "volume"),
    ("TURNOVER_LACS", "turnover_lacs"),
    ("NO_OF_TRADES", "trades"),
    ("DELIV_QTY", "deliv_qty"),
    ("DELIV_PER", "deliv_per"),
    # Present only in the old archive. Keeping it lets the panel builder use
    # a point-in-time ISIN instead of the current NSE master.
    ("ISIN", "isin"),
]


class HolidayGate(RuntimeError):
    """The server returned a different date's file (holiday duplicate)."""


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch(day: dt.date) -> bytes:
    return _get(URL.format(ddmmyyyy=day.strftime("%d%m%Y")))


def fetch_old(day: dt.date) -> bytes:
    mmm = day.strftime("%b").upper()
    return _get(
        OLD_URL.format(
            yyyy=day.strftime("%Y"), mmm=mmm, dd=day.strftime("%d")
        )
    )


def parse_date(s: str) -> dt.date:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unparseable DATE1: {s!r}")


def _decode_payload(raw: bytes) -> str:
    """Return CSV text. NSE sometimes serves an XLSX/zip for a .csv URL."""
    if raw[:2] != b"PK":
        return raw.decode("utf-8", "replace")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError("zip payload has no csv")
        return z.read(names[0]).decode("utf-8", "replace")


def _parse_rows(text: str, day: dt.date) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        raise RuntimeError("empty response")
    header = [h.strip() for h in next(csv.reader([lines[0]]))]
    reader = csv.DictReader(lines[1:], fieldnames=header)
    rows = [r for r in reader if r.get("SYMBOL", "").strip()]
    if not rows:
        raise RuntimeError("no data rows")

    if "DATE1" in header:
        dates = {parse_date(r["DATE1"]) for r in rows}
        if dates != {day}:
            raise HolidayGate(
                f"holiday/duplicate gate: requested {day}, "
                f"file contains {sorted(dates)} -- rejected"
            )
        return rows

    # Old NSE archive format (pre-UDiFF). No delivery columns, but OHLCV
    # is complete; map it into the same row shape with blank delivery.
    if "TIMESTAMP" in header:
        dates = {parse_date(r["TIMESTAMP"]) for r in rows}
        if dates != {day}:
            raise HolidayGate(
                f"holiday/duplicate gate: requested {day}, "
                f"file contains {sorted(dates)} -- rejected"
            )
        out = []
        for r in rows:
            try:
                turnover = str(float(r["TOTTRDVAL"]) / 100000.0)
            except (KeyError, TypeError, ValueError):
                turnover = ""
            out.append(
                {
                    "SYMBOL": r.get("SYMBOL", ""),
                    "SERIES": r.get("SERIES", ""),
                    "DATE1": r.get("TIMESTAMP", ""),
                    "PREV_CLOSE": r.get("PREVCLOSE", ""),
                    "OPEN_PRICE": r.get("OPEN", ""),
                    "HIGH_PRICE": r.get("HIGH", ""),
                    "LOW_PRICE": r.get("LOW", ""),
                    "LAST_PRICE": r.get("LAST", ""),
                    "CLOSE_PRICE": r.get("CLOSE", ""),
                    "AVG_PRICE": "",
                    "TTL_TRD_QNTY": r.get("TOTTRDQTY", ""),
                    "TURNOVER_LACS": turnover,
                    "NO_OF_TRADES": r.get("TOTALTRADES", ""),
                    "DELIV_QTY": "",
                    "DELIV_PER": "",
                    "ISIN": r.get("ISIN", ""),
                }
            )
        return out

    raise RuntimeError(f"unrecognised header: {header[:5]}")


def download_day(day: dt.date) -> tuple[list[dict], list[dict]]:
    """Fetch and validate one day. Returns (all rows, EQ rows).

    Pre-2020 dates are not available at the current UDiFF URL. Any fetch or
    parse failure falls back to the old archive ZIP, which is also the right
    source for early history. A HolidayGate is never retried: it means the
    server returned a different date's file.
    """
    if day < dt.date(2020, 1, 1):
        try:
            raw = fetch_old(day)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise HolidayGate(f"{day}: old archive has no file (holiday)") from exc
            raise
        rows = _parse_rows(_decode_payload(raw), day)
    else:
        try:
            raw = fetch(day)
            rows = _parse_rows(_decode_payload(raw), day)
        except HolidayGate:
            raise
        except Exception:
            try:
                raw = fetch_old(day)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise HolidayGate(f"{day}: no current or old file (holiday)") from exc
                raise
            rows = _parse_rows(_decode_payload(raw), day)

    eq = [r for r in rows if r.get("SERIES", "").strip() == "EQ"]
    return rows, eq


def write_day(day: dt.date, eq: list[dict]) -> str:
    """Write atomically: a killed run never leaves a partial final file."""
    os.makedirs(RAW, exist_ok=True)
    out = os.path.join(RAW, f"bhavcopy_{day.isoformat()}.csv")
    tmp = out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([dst for _, dst in COLS])
        for r in eq:
            w.writerow([
                day.isoformat() if src == "DATE1" else r.get(src, "").strip()
                for src, _ in COLS
            ])
    os.replace(tmp, out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    want = dt.date.fromisoformat(args.date)

    rows, eq = download_day(want)
    out = write_day(want, eq)
    deliv = sum(1 for r in eq if r.get("DELIV_PER", "").strip() not in ("", "-"))
    print(
        f"date={want} rows={len(rows)} eq={len(eq)} "
        f"delivery={deliv} -> {os.path.relpath(out, ROOT)}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
