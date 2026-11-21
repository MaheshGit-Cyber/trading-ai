# Phase 0 — data source findings

Verified on device, 2026-11-20. Every claim below was tested, not assumed.

## 1. NSE full bhavcopy — primary source

```
https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
```

- Requires a browser User-Agent. Without one: 403.
- **Available from 2020 only.** 2015 and 2010 return 404.
- Columns: SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE,
  LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY,
  TURNOVER_LACS, NO_OF_TRADES, **DELIV_QTY, DELIV_PER**
- One day ≈ 400 KB, ≈ 3,550 rows across all series.
- `SERIES == "EQ"` filter gives ≈ 2,750 symbols per day.

Delivery quantity and delivery percentage are present. That is a real
input, not a proxy — the course corpus talks about delivery confirmation
but the bhavcopy is where it actually lives.

## 2. Older archive — blocked

```
https://archives.nseindia.com/content/historical/EQUITIES/2015/JAN/cm02JAN2015bhav.csv.zip  → 403
https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20150102_F_0000.csv.zip      → 404
```

So the usable daily history is **2020-01 → present, ≈ 6.9 years**.
That is enough for walk-forward (it contains COVID crash, 2021 bull,
2022 correction, 2023–24 bull, 2025–26), but it is not 25 years.

## 3. BSE bhavcopy — now usable

The earlier test used the wrong filename (`0_0000`). The correct UDiFF
filename has three zero groups:

```
https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV
```

- **2024-01-01 → present:** UDiFF CSV. Has ISIN, ticker, scrip code,
  OHLC, volume, turnover, trades. About 4,500–5,100 equity rows/day.
- **2020-01-01 → 2023-12-31:** old ZIP:

  ```
  https://www.bseindia.com/download/BhavCopy/Equity/EQDDMMYY_CSV.ZIP
  ```

  Old format has scrip code, name, group, OHLC, volume, turnover, trades.
  **No ISIN and no ticker.** Use `scrip_code` + `name` for identity.
- **Delivery (both eras):**

  ```
  https://www.bseindia.com/BSEDATA/gross/YYYY/SCBSEALLDDMM.zip
  ```

  Merge by scrip code. Delivery coverage is **100%** across the backfill.
- Holidays return HTTP 200 with the same **16 KB HTML shell**; the ingester
  rejects it. UDiFF rows are also date-gated by `TradDt`; delivery rows are
  date-gated by the report `DATE`.
- BSE publishes extra counters (`SBIN#`, etc.) with the same ISIN as the
  normal stock. These are excluded. ETFs (E/F), government securities
  (G/GC), InvIT/REIT (IF), preference shares (P), rights (R) and special
  counters are excluded. Equity allowlist:
  **A/B/T/Z/X/XT/M/MS/MT/TS/ZP**.

## 4. `adj_factor` — corporate actions, not `PREV_CLOSE`

**Correction (2026-11-20): the earlier claim that `PREV_CLOSE` is restated
for corporate actions was wrong.** NSE and BSE both publish the raw previous
close. The clearest example:

```
BAJFINANCE 2025-06-16
  previous close (2025-06-13) = 9,331.00
  PREV_CLOSE (2025-06-16)     = 9,331.00   <- raw, not restated
  close (2025-06-16)          = 938.00     <- after 4:1 bonus + 2->1 split
```

Using `CLOSE(t-1) / PREV_CLOSE(t)` gives 1.0 and misses a -90% corporate
action. The old formula is therefore retired.

The panel now uses explicit NSE/BSE corporate-action records:

```
BONUS  a:b (a new for b held) -> factor = b / (a + b)
SPLIT  old face value -> new  -> factor = new / old
RIGHTS a:b at issue price S   -> factor = (b + a*S/P) / (a + b)
                                  where P = ex-date previous close
                                  cap at 1.0 when the rights are out-of-the-money
OTHER  demerger/scheme/etc.    -> no factor; flagged ca_unadjusted
```

Events are applied at the **first row on/after the ex-date**, not only when
the ex-date has a bhavcopy row. This matters for suspended stocks and BSE-only
scrips. If the official factor disagrees with the observed open / last-close
ratio by more than 25%, the observed ratio is used and the row is flagged
`ca_observed_adjustment`; if the tape shows no move, factor 1.0 is used and
the row is flagged `ca_not_reflected`. Those flags are an audit trail, not
silent fixes.

Dividends are still **not** adjusted. The panel is price-return only.

## 5. CRITICAL: NSE serves the previous day's file for holidays

| Requested | DATE1 inside the file | Verdict |
|---|---|---|
| 2026-10-19 | 19-Oct-2026 | ok |
| 2026-10-20 | **19-Oct-2026** | **duplicate of the previous day** |
| 2026-11-09 | 09-Nov-2026 | ok |
| 2026-11-10 | **09-Nov-2026** | **duplicate of the previous day** |

On a non-trading day the server returns HTTP 200 with the last available
file instead of 404. If you do not check `DATE1`, you get:

- two identical days in the series (zero return, corrupts volatility),
- and a fake "6,429 corporate actions" signal, because every symbol's
  `PREV_CLOSE` looks wrong relative to the duplicated prior bar.

**Rule: reject any file whose `DATE1` does not equal the requested date.**
This is now a hard gate in the ingester, not a warning.

## 6. Not yet solved

- **Survivorship**: bhavcopy is point-in-time, so a symbol appears only
  while listed. Building the universe from the union of all symbols ever
  seen is survivorship-free *if* delisted symbols are retained in the
  store. Must verify that delisted names actually appear before delisting.
- **Index constituents history**: needed for benchmark-relative features
  (`rs_leader_pullback`). Not yet sourced.
- **1-minute intraday**: not sourced. Daily only for Phase 1.
- **Dividends**: bhavcopy is price-return only. The panel adjusts
  splits/bonus/rights from corporate-action records, not dividend payouts.
  State this in every result.
- **BSE 2020–2023 identity**: the old BSE format has no ISIN or ticker.
  Use `scrip_code` + `name`; the current NSE↔BSE crosswalk is point-in-time
  only for 2024+. Do not backfill current ISINs into old rows as if they were
  historical.

## 7. Storage projection (measured, not guessed)

| Item | Measured | Projection |
|---|---|---|
| NSE raw daily CSV | 400 KB | 6.9 y × 250 d ≈ 690 MB raw |
| BSE raw daily (old / UDiFF) | ~100 KB / ~800 KB | **725 MB measured** |
| Combined NSE + BSE raw | — | **~1.04 GB measured** |
| Normalised parquet (if pyarrow) | ~8x smaller | ~130 MB |
| Normalised CSV + numpy .npy | ~2x smaller | ~500 MB |
| Full index + features | — | < 2 GB total |

Device: 147 GB free, 7.5 GB RAM (2.5 GB usable), 8 cores. Daily-only
system fits with room to spare. Tick data does not fit — that conclusion
is unchanged.

## 8. Environment

`python-numpy 2.5.5` installed via `pkg`. Without it, pure-Python loops
over ~3 M rows are minutes per pass instead of seconds. `pandas` and
`pyarrow` are still absent. `requests` is installed and used only by
`jobs/fetch_corporate_actions.py` for the BSE API; the core engine and
backtest use `csv` and the standard library.

## 9. Backfill result — measured 2026-11-20

| Metric | Value |
|---|---|
| Trading days | **1,701** |
| Date range | 2020-01-01 → 2026-11-19 |
| EQ rows | **3,176,800** |
| Delivery coverage | **99.943%** |
| Raw normalised size | **323.5 MB** |
| Structural integrity | **clean** (1 documented correction; see §10) |
| Non-trading weekdays rejected | 96 |
| Real trading-day gaps | **0** |

- 83 holidays returned the previous day's file and were rejected by the
  `DATE1` gate.
- 13 holidays returned HTTP 404 and are counted as holidays.
- **2022-08-08** was the only real trading-day gap. The primary URL served
  an XLSX (a `PK` zip containing `xl/` parts), not a CSV. Recovered from the
  old NSE archive:
  `.../2022/AUG/cm08AUG2022bhav.csv.zip` — 1,817 EQ rows. That day has no
  delivery columns; do not use delivery features for it without a flag.
- The ingester now detects `PK` payloads, parses a contained CSV when
  present, and falls back to the old archive CSV ZIP when the primary is an
  XLSX.
- Manifest: `data/raw/MANIFEST.json` (counts, by-year days, missing
  weekdays, delivery coverage).

Per-year trading days: 2020=250, 2021=247, 2022=247, 2023=245, 2024=246,
2025=248, 2026=217 (to 19 Nov). Low row counts in 2020 (≈1,400 EQ) are the
real NSE universe at that time, not missing data; the universe grows to
≈2,760 by 2026.

## 10. Integrity audit — measured 2026-11-20

| Check | Result |
|---|---|
| Files | 1,701 |
| Rows | 3,176,800 |
| Unique `(date, symbol)` pairs | 3,176,800 — **0 duplicates** |
| Duplicate files by SHA-256 | **0** |
| Non-EQ rows | **0** |
| Date / filename mismatch | **0** |
| OHLC violations | **0** |
| Non-positive prices | **0** |
| Delivery qty > volume | **0** |
| Missing trading days | **0** |

**Cross-source check.** Compared against the old NSE archive CSV ZIP for
2020-04-13, 2020-07-13, 2022-11-18 and 2023-11-17. OHLCV matched exactly
except one row: GTLINFRA on 2020-07-13.

### Correction

GTLINFRA 2020-07-13 in the new full bhavcopy had:

| Field | New bhavcopy | Old archive | Verdict |
|---|---|---|---|
| `volume` | 6,161,122,183 | 1,573,668 | new file corrupted |
| `turnover_lacs` | 14.16 | 1,416,301.2 / 1e5 = 14.16 | matches old |
| `deliv_qty` | 1,571,668 | — | consistent with old volume |
| `avg` | 0.00 | 1,416,301.2 / 1,573,668 = 0.90 | new file corrupted |

Corrected `volume` to 1,573,668 and `avg` to 0.90. Original file backed up
under `data/raw/.backup/`; full old/new values in
`data/raw/CORRECTIONS.json`. After the fix, the row's delivery percentage
is consistent (99.87%).

### Delivery-percentage flags

`DELIV_PER` does **not** equal `100 * DELIV_QTY / TTL_TRD_QNTY` on three
dates:

| Date | Mismatch rows / delivery rows | Action |
|---|---|---|
| 2020-04-13 | 1,369 / 1,515 (90.4%) | exclude delivery features |
| 2025-10-21 | 33 / 2,291 (1.4%) | exclude affected symbols or the date |
| 2026-09-11 | 2,513 / 2,636 (95.3%) | exclude delivery features |

OHLCV on 2020-04-13 matched the old archive exactly, so the problem is
confined to the delivery columns. 2022-08-08 has blank `avg`, `deliv_qty`
and `deliv_per` by construction (old-archive fallback). None of these are
fabricated rows; they are NSE source inconsistencies and are flagged for
Phase 1.

## 11. BSE backfill result — measured 2026-11-20

| Metric | Value |
|---|---|
| Trading days | **1,702** |
| Date range | 2020-01-01 → 2026-11-19 |
| EQ rows | **6,274,702** |
| Delivery coverage | **100%** |
| ISIN coverage | **47.47% overall** (2024+ 100%, 2020–2023 0%) |
| Raw size | **725 MB** |
| Non-trading weekdays rejected | 95 |
| Real trading-day gaps | **0** |
| BSE-only date | **2021-11-04** |

- 2020–2023: old ZIP format, 3,296,118 rows, no ISIN/ticker.
- 2024–2026: UDiFF format, 2,978,584 rows, point-in-time ISIN/ticker.
- 2021-11-04 is present in BSE but absent from NSE. It was a special/Muhurat
  session; keep it flagged, and use the date intersection for cross-exchange
  panels.
- Per-year trading days: 2020=250, 2021=248, 2022=248, 2023=245, 2024=246,
  2025=248, 2026=217.
- Per-year rows: 2020=691,453; 2021=818,004; 2022=875,373; 2023=911,288;
  2024=983,906; 2025=1,036,108; 2026=958,570.

## 12. BSE integrity audit — measured 2026-11-20

| Check | Result |
|---|---|
| Files | 1,702 |
| Rows | 6,274,702 |
| Unique `(date, scrip_code)` pairs | 6,274,702 — **0 duplicates** |
| Non-equity rows | **0** (equity allowlist applied) |
| Date / filename mismatch | **0** |
| OHLC violations | **0** |
| Delivery qty > volume | **0** |
| Delivery % inconsistency | **0** |
| Days with duplicate ISIN | **0** |
| Delivery coverage | **100%** |

**Identity changes.** 356 scrips have more than one ISIN in the UDiFF era.
These are real corporate actions (face-value splits/bonus), not corruption.
76 of those also changed name or ticker (renames/mergers/demergers). Full
list: `data/bse/raw/IDENTITY_CHANGES.csv`. Use date-specific ISIN and do not
assume one identity for the full history.

**Cross-exchange check.** Current NSE↔BSE ISIN crosswalk:
`data/crosswalk_nse_bse.csv`, **2,257 pairs**. On 2026-11-19, the median
absolute NSE/BSE close difference across 2,253 matched pairs was **0.128%**;
93 pairs were above 2%, consistent with last-trade timing and market
microstructure differences. BSE has many more small/illiquid scrips than NSE.

**BSE manifest:** `data/bse/raw/MANIFEST.json`.
