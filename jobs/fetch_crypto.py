#!/usr/bin/env python3
"""
fetch_crypto.py - Ingest daily OHLCV historical data for Crypto assets (BTC/USDT, ETH/USDT)
Source: Binance public official REST API (no auth needed).
Coverage: 2017-08-17 to current (full available history).
Outputs: data/crypto/{symbol}_daily_2017_2026.csv
Dependencies: Standard library only (csv, urllib, json, time, datetime).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

OUT_DIR = "/storage/emulated/0/Mahvex/trading-ai/data/crypto"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]

def fetch_klines(symbol: str, interval: str = "1d", start_ts: int | None = None, end_ts: int | None = None, limit: int = 1000) -> list:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    if start_ts is not None:
        url += f"&startTime={start_ts}"
    if end_ts is not None:
        url += f"&endTime={end_ts}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_full_history(symbol: str) -> str | None:
    print(f"[*] Starting download for {symbol}...")
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # Binance earliest BTCUSDT is 2017-08-17 (approx 1502928000000)
    current_ts = int(datetime(2017, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
    now_ts = int(time.time() * 1000)
    
    all_rows = {}
    
    while current_ts < now_ts:
        try:
            klines = fetch_klines(symbol, interval="1d", start_ts=current_ts, limit=1000)
            if not klines:
                break
            
            for k in klines:
                open_time = k[0]
                date_str = datetime.fromtimestamp(open_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                open_p = f"{float(k[1]):.4f}"
                high_p = f"{float(k[2]):.4f}"
                low_p = f"{float(k[3]):.4f}"
                close_p = f"{float(k[4]):.4f}"
                volume = f"{float(k[5]):.6f}"
                quote_vol = f"{float(k[7]):.2f}"
                trades = int(k[8])
                all_rows[date_str] = {
                    "date": date_str,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": volume,
                    "turnover_usdt": quote_vol,
                    "trades": trades
                }
            
            last_ts = klines[-1][0]
            next_ts = last_ts + (24 * 3600 * 1000)
            if next_ts <= current_ts:
                break
            current_ts = next_ts
            time.sleep(0.1)  # Rate limit safety
        except Exception as e:
            print(f"[!] Warning for {symbol} at {current_ts}: {e}")
            time.sleep(2)
            continue

    if not all_rows:
        print(f"[!] No rows downloaded for {symbol}")
        return None

    sorted_dates = sorted(all_rows.keys())
    out_file = os.path.join(OUT_DIR, f"{symbol.lower()}_daily_2017_2026.csv")
    
    fieldnames = ["date", "open", "high", "low", "close", "volume", "turnover_usdt", "trades"]
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in sorted_dates:
            writer.writerow(all_rows[d])

    print(f"[+] Saved {len(sorted_dates)} daily bars for {symbol} to {out_file}")
    print(f"    Date range: {sorted_dates[0]} to {sorted_dates[-1]}")
    return out_file

def main():
    for sym in SYMBOLS:
        download_full_history(sym)
    print("[+] Crypto historical data ingestion completed.")

if __name__ == "__main__":
    main()
