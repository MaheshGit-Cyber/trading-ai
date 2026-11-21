"""Fetch one BSE equity bhavcopy day, normalise it, merge delivery data.

    python3 jobs/fetch_bse_bhavcopy.py --date 2026-11-19

Sources (tested on device, 2026-11-20):
  1. UDiFF (2024-01-01 onward):
     https://www.bseindia.com/download/BhavCopy/Equity/
       BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV
  2. Old archive (2020-01-01 .. 2023-12-31):
     https://www.bseindia.com/download/BhavCopy/Equity/EQDDMMYY_CSV.ZIP
  3. Delivery report (both eras):
     https://www.bseindia.com/BSEDATA/gross/YYYY/SCBSEALLDDMM.zip

BSE returns a 16,912-byte HTML shell on holidays (HTTP 200), not a CSV.
That is treated as "no data", never as a valid day.

Output: data/bse/raw/bhavcopy_YYYY-MM-DD.csv
Columns: date, scrip_code, symbol, name, series, isin, open, high, low,
close, last, prev_close, volume, turnover_lacs, trades, deliv_qty,
deliv_per, source_format.
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

BASE = "https://www.bseindia.com"
UDIFF_URL = (
    BASE
    + "/download/BhavCopy/Equity/"
    "BhavCopy_BSE_CM_0_0_0_{yyyymmdd}_F_0000.CSV"
)
OLD_URL = BASE + "/download/BhavCopy/Equity/EQ{ddmmyy}_CSV.ZIP"
DELIV_URL = BASE + "/BSEDATA/gross/{yyyy}/SCBSEALL{ddmm}.zip"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "bse", "raw")
UDIFF_START = dt.date(2024, 1, 1)

# Equity share groups only. Excludes ETFs (E/F), government securities (G/GC),
# InvIT/REIT (IF), preference shares (P) and rights entitlements (R).
EQUITY_SERIES = {
    "A",
    "B",
    "T",
    "Z",
    "X",
    "XT",
    "M",
    "MS",
    "MT",
    "TS",
    "ZP",
}

COLS = [
    "date",
    "scrip_code",
    "symbol",
    "name",
    "series",
    "isin",
    "open",
    "high",
    "low",
    "close",
    "last",
    "prev_close",
    "volume",
    "turnover_lacs",
    "trades",
    "deliv_qty",
    "deliv_per",
    "source_format",
]


class BseHoliday(RuntimeError):
    """BSE has no bhavcopy for this date (holiday or not yet published)."""


def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": BASE + "/markets/MarketInfo/BhavCopy",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def _is_html(raw: bytes) -> bool:
    head = raw[:80].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def _unzip_text(raw: bytes) -> str:
    if raw[:2] != b"PK":
        return raw.decode("utf-8", "replace")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".csv", ".txt"))
        ]
        if not names:
            raise RuntimeError("BSE zip has no CSV/TXT payload")
        return archive.read(names[0]).decode("utf-8", "replace")


def _num(value: str) -> str:
    return value.strip()


def _turnover_lacs(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        return str(float(value) / 100000.0)
    except ValueError:
        return ""


def _normalise_code(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        return str(int(value))
    except ValueError:
        return value


def _parse_udiff(text: str, day: dt.date) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    rows = []
    for row in reader:
        if row.get("Sgmt", "").strip() != "CM":
            continue
        if row.get("FinInstrmTp", "").strip() != "STK":
            continue
        if row.get("SctySrs", "").strip() not in EQUITY_SERIES:
            continue
        symbol = row.get("TckrSymb", "").strip()
        # BSE also publishes special "#" counters (SBIN#, ...) with the same
        # ISIN as the normal stock. They are not separate equities.
        if "#" in symbol:
            continue
        trade_date = row.get("TradDt", "").strip()
        if trade_date != day.isoformat():
            raise BseHoliday(
                f"UDiFF date gate: requested {day}, file contains "
                f"{trade_date or 'blank'} -- rejected"
            )
        rows.append(
            {
                "date": day.isoformat(),
                "scrip_code": _normalise_code(row.get("FinInstrmId", "")),
                "symbol": row.get("TckrSymb", "").strip(),
                "name": row.get("FinInstrmNm", "").strip(),
                "series": row.get("SctySrs", "").strip(),
                "isin": row.get("ISIN", "").strip(),
                "open": _num(row.get("OpnPric", "")),
                "high": _num(row.get("HghPric", "")),
                "low": _num(row.get("LwPric", "")),
                "close": _num(row.get("ClsPric", "")),
                "last": _num(row.get("LastPric", "")),
                "prev_close": _num(row.get("PrvsClsgPric", "")),
                "volume": _num(row.get("TtlTradgVol", "")),
                "turnover_lacs": _turnover_lacs(row.get("TtlTrfVal", "")),
                "trades": _num(row.get("TtlNbOfTxsExctd", "")),
                "deliv_qty": "",
                "deliv_per": "",
                "source_format": "udiff",
            }
        )
    if not rows:
        raise RuntimeError("UDiFF has no CM/STK rows")
    return rows


def _parse_old(text: str, day: dt.date) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    rows = []
    for row in reader:
        # SC_TYPE == Q is equity. D/B/P are debentures, bonds, preference.
        if row.get("SC_TYPE", "").strip() != "Q":
            continue
        if row.get("SC_GROUP", "").strip() not in EQUITY_SERIES:
            continue
        rows.append(
            {
                "date": day.isoformat(),
                "scrip_code": _normalise_code(row.get("SC_CODE", "")),
                "symbol": "",
                "name": row.get("SC_NAME", "").strip(),
                "series": row.get("SC_GROUP", "").strip(),
                "isin": "",
                "open": _num(row.get("OPEN", "")),
                "high": _num(row.get("HIGH", "")),
                "low": _num(row.get("LOW", "")),
                "close": _num(row.get("CLOSE", "")),
                "last": _num(row.get("LAST", "")),
                "prev_close": _num(row.get("PREVCLOSE", "")),
                "volume": _num(row.get("NO_OF_SHRS", "")),
                "turnover_lacs": _turnover_lacs(row.get("NET_TURNOV", "")),
                "trades": _num(row.get("NO_TRADES", "")),
                "deliv_qty": "",
                "deliv_per": "",
                "source_format": "old",
            }
        )
    if not rows:
        raise RuntimeError("old BSE file has no SC_TYPE=Q rows")
    return rows


def _parse_delivery(text: str, day: dt.date) -> dict[str, tuple[int, float]]:
    lines = text.splitlines()
    if not lines:
        return {}
    out: dict[str, tuple[int, float]] = {}
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 7:
            continue
        date_text = parts[0].strip()
        if not date_text:
            continue
        try:
            delivery_date = dt.datetime.strptime(date_text, "%d%m%Y").date()
        except ValueError:
            continue
        if delivery_date != day:
            raise BseHoliday(
                f"delivery date gate: requested {day}, file contains "
                f"{delivery_date} -- rejected"
            )
        code = _normalise_code(parts[1])
        try:
            qty = int(parts[2])
            per = float(parts[6])
        except ValueError:
            continue
        if code:
            out[code] = (qty, per)
    return out


def _fetch_udiff(day: dt.date) -> list[dict] | None:
    try:
        raw = _get(UDIFF_URL.format(yyyymmdd=day.strftime("%Y%m%d")))
    except urllib.error.HTTPError:
        return None
    if _is_html(raw):
        return None
    return _parse_udiff(_unzip_text(raw), day)


def _fetch_old(day: dt.date) -> list[dict] | None:
    try:
        raw = _get(OLD_URL.format(ddmmyy=day.strftime("%d%m%y")))
    except urllib.error.HTTPError:
        return None
    if _is_html(raw):
        return None
    return _parse_old(_unzip_text(raw), day)


def _merge_delivery(rows: list[dict], day: dt.date) -> int:
    try:
        raw = _get(
            DELIV_URL.format(
                yyyy=day.strftime("%Y"), ddmm=day.strftime("%d%m")
            )
        )
    except urllib.error.HTTPError:
        return 0
    if _is_html(raw):
        return 0
    delivery = _parse_delivery(_unzip_text(raw), day)
    merged = 0
    for row in rows:
        match = delivery.get(row["scrip_code"])
        if match is None:
            continue
        qty, per = match
        row["deliv_qty"] = str(qty)
        row["deliv_per"] = f"{per:g}"
        merged += 1
    return merged


def download_day(day: dt.date) -> tuple[list[dict], str]:
    """Return (rows, source_format) or raise BseHoliday."""
    rows = None
    source = ""

    # UDiFF starts 2024-01-01. Before that, go straight to the old ZIP.
    if day >= UDIFF_START:
        try:
            rows = _fetch_udiff(day)
            source = "udiff"
        except BseHoliday:
            raise
        if rows is None:
            source = ""

    if rows is None:
        try:
            rows = _fetch_old(day)
            source = "old"
        except BseHoliday:
            raise

    if rows is None:
        raise BseHoliday(f"BSE returned no bhavcopy for {day}")

    _merge_delivery(rows, day)
    rows.sort(key=lambda row: (row["scrip_code"], row["symbol"]))
    return rows, source


def write_day(day: dt.date, rows: list[dict]) -> str:
    os.makedirs(RAW, exist_ok=True)
    out = os.path.join(RAW, f"bhavcopy_{day.isoformat()}.csv")
    tmp = out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.date)

    try:
        rows, source = download_day(day)
    except BseHoliday as exc:
        print(f"no data: {exc}")
        sys.exit(2)

    out = write_day(day, rows)
    delivery = sum(1 for row in rows if row["deliv_qty"])
    print(
        f"date={day} rows={len(rows)} delivery={delivery} "
        f"format={source} -> {os.path.relpath(out, ROOT)}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
