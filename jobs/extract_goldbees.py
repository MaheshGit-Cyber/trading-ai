#!/usr/bin/env python3
"""
extract_goldbees.py - Extract continuous split-adjusted daily OHLCV for GOLDBEES from raw bhavcopies.
Split: 1:100 split on 2019-12-19 (prices before 2019-12-19 divided by 100).
Output: data/gold/goldbees_daily_2010_2026.csv
"""

import os
import glob
import csv

RAW_DIR = "/storage/emulated/0/Mahvex/trading-ai/data/raw"
OUT_DIR = "/storage/emulated/0/Mahvex/trading-ai/data/gold"
OUT_FILE = os.path.join(OUT_DIR, "goldbees_daily_2010_2026.csv")

os.makedirs(OUT_DIR, exist_ok=True)

files = sorted(glob.glob(os.path.join(RAW_DIR, "bhavcopy_*.csv")))
print(f"[*] Processing {len(files)} raw bhavcopies for GOLDBEES...")

rows = []

for f in files:
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        reader = csv.reader(fp)
        for parts in reader:
            if len(parts) >= 9 and parts[0] == "GOLDBEES" and parts[1] == "EQ":
                # Schema: symbol,series,date,prev_close,open,high,low,last,close,...
                date_str = parts[2]
                try:
                    open_p = float(parts[4])
                    high_p = float(parts[5])
                    low_p = float(parts[6])
                    close_p = float(parts[8]) if parts[8] else float(parts[7])
                    vol = float(parts[10]) if len(parts) > 10 and parts[10] else 0.0
                except (ValueError, IndexError):
                    continue

                # Adjust for 1:100 split on 2019-12-19
                if date_str < "2019-12-19":
                    open_p /= 100.0
                    high_p /= 100.0
                    low_p /= 100.0
                    close_p /= 100.0
                    vol *= 100.0

                rows.append({
                    "date": date_str,
                    "open": f"{open_p:.4f}",
                    "high": f"{high_p:.4f}",
                    "low": f"{low_p:.4f}",
                    "close": f"{close_p:.4f}",
                    "volume": f"{vol:.0f}"
                })
                break

rows.sort(key=lambda x: x["date"])
print(f"[+] Extracted {len(rows)} daily bars for GOLDBEES")

with open(OUT_FILE, "w", newline="", encoding="utf-8") as fp:
    writer = csv.DictWriter(fp, fieldnames=["date", "open", "high", "low", "close", "volume"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"[+] Saved to {OUT_FILE}")
