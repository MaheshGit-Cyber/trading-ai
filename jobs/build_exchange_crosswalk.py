"""Build BSE scrip master and NSE<->BSE ISIN crosswalk.

    python3 jobs/build_exchange_crosswalk.py

Inputs:
  data/bse/raw/bhavcopy_YYYY-MM-DD.csv   (latest UDiFF day)
  NSE EQUITY_L.csv                        (downloaded once)

Outputs:
  data/bse/scrip_master.csv
  data/nse_equity_master.csv
  data/crosswalk_nse_bse.csv
"""

from __future__ import annotations

import csv
import glob
import os
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BSE_MASTER = os.path.join(ROOT, "data", "bse", "scrip_master.csv")
NSE_MASTER = os.path.join(ROOT, "data", "nse_equity_master.csv")
CROSSWALK = os.path.join(ROOT, "data", "crosswalk_nse_bse.csv")
NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)


def load_bse_master() -> list[dict]:
    files = sorted(glob.glob(os.path.join(ROOT, "data", "bse", "raw", "bhavcopy_*.csv")))
    if not files:
        raise SystemExit("no BSE raw files found; run jobs/backfill_bse.py first")
    latest = files[-1]
    rows = []
    with open(latest, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row["scrip_code"]:
                continue
            rows.append(
                {
                    "scrip_code": row["scrip_code"],
                    "symbol": row["symbol"],
                    "isin": row["isin"],
                    "name": row["name"],
                    "series": row["series"],
                    "as_of": row["date"],
                }
            )
    return rows


def load_nse_master() -> list[dict]:
    if not os.path.exists(NSE_MASTER):
        request = urllib.request.Request(NSE_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        with open(NSE_MASTER, "wb") as handle:
            handle.write(data)

    rows = []
    with open(NSE_MASTER, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            clean = {key.strip(): value.strip() for key, value in row.items()}
            if clean.get("SERIES") != "EQ":
                continue
            rows.append(
                {
                    "nse_symbol": clean.get("SYMBOL", ""),
                    "nse_name": clean.get("NAME OF COMPANY", ""),
                    "isin": clean.get("ISIN NUMBER", ""),
                }
            )
    return rows


def main() -> None:
    bse = load_bse_master()
    nse = load_nse_master()

    with open(BSE_MASTER, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scrip_code", "symbol", "isin", "name", "series", "as_of"],
        )
        writer.writeheader()
        writer.writerows(bse)

    bse_by_isin = {}
    for row in bse:
        if row["isin"] and row["isin"] not in bse_by_isin:
            bse_by_isin[row["isin"]] = row

    crosswalk = []
    for row in nse:
        match = bse_by_isin.get(row["isin"])
        if match is None:
            continue
        crosswalk.append(
            {
                "isin": row["isin"],
                "nse_symbol": row["nse_symbol"],
                "nse_name": row["nse_name"],
                "bse_scrip_code": match["scrip_code"],
                "bse_symbol": match["symbol"],
                "bse_name": match["name"],
            }
        )

    with open(CROSSWALK, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "isin",
                "nse_symbol",
                "nse_name",
                "bse_scrip_code",
                "bse_symbol",
                "bse_name",
            ],
        )
        writer.writeheader()
        writer.writerows(crosswalk)

    print(f"BSE master: {len(bse)} scrips")
    print(f"NSE EQ master: {len(nse)} symbols")
    print(f"crosswalk by ISIN: {len(crosswalk)} pairs")


if __name__ == "__main__":
    main()
