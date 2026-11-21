# Phase 1 — adjusted NSE+BSE panel

**Built:** 2026-11-20  
**Output:** `data/curated/panel.csv` (plain CSV, ~1.8 GB)  
**Manifest:** `data/curated/MANIFEST.json`  
**Builder:** `jobs/build_adjusted_panel.py`  
**Actions:** `jobs/fetch_corporate_actions.py` → `data/corporate_actions/actions.csv`

## Counts

| Item | Value |
|---|---:|
| Rows | **7,071,544** |
| Trading days | **1,702** |
| Date range | **2020-01-01 → 2026-11-19** |
| NSE rows | **3,176,800** |
| BSE rows | **3,894,744** |
| BSE old (2020–2023) | **2,109,575** |
| BSE UDiFF (2024+) | **1,785,169** |
| Unique stocks | **8,970** |

The row count is one row per `date + stock_id`. NSE is primary. BSE is used
only when NSE has no row for that company on that date, or for BSE-only
companies. 2021-11-04 is a BSE-only special session; it is included and
flagged `bse_only_date`.

## Schema

```
date, stock_id, market, symbol, name, series, isin, isin_source,
nse_symbol, source, open, high, low, close, last, prev_close, volume,
turnover_lacs, trades, deliv_qty, deliv_per, adj_open, adj_high,
adj_low, adj_close, adj_last, adj_volume, adj_deliv_qty, adj_factor,
ca_factor, ca_action, flags
```

- `stock_id` is the stable key: `NSE:<symbol>` or `BSE:<scrip_code>`.
- Raw OHLC/volume/delivery columns are preserved.
- `adj_*` columns are back-adjusted to the latest scale: the latest row for
  each stock has `adj_factor = 1.0`; earlier rows are multiplied by future
  corporate-action factors.
- Adjusted volume and delivery quantity are divided by the same factor.
- `ca_factor` is the factor applied on that row's ex-date (1.0 if none).
- `ca_action` shows the action names applied on that row.
- `flags` is semicolon-separated; use it to filter.

## Adjustment method

1. Fetch NSE/BSE corporate actions from the official JSON APIs.
2. Parse:
   - `BONUS a:b` → `b / (a + b)` (a new for b held)
   - `SPLIT old → new` → `new / old`
   - `RIGHTS a:b @ price S` → `(b + a*S/P) / (a + b)`, where `P` is the
     ex-date previous close; capped at 1.0 when out-of-the-money.
   - `OTHER` (demerger/scheme/capital reduction) → no factor; flagged
     `ca_unadjusted`.
   - `BONUS_NON_EQUITY` (NCRPS/preference/debenture bonus) → no equity
     factor; flagged `ca_bonus_non_equity`.
3. Apply events at the **first row on/after the ex-date**. This handles
   suspended stocks and scrips with no bhavcopy row on the ex-date.
4. Reconcile with the tape. If the official factor differs from
   `open / last_close` by more than 25%:
   - use the observed ratio and flag `ca_observed_adjustment`, or
   - use 1.0 when the tape shows no move and flag `ca_not_reflected`.
5. Flag every mismatch with `ca_factor_mismatch`; nothing is silently
   overwritten.

## Audit result

| Check | Result |
|---|---|
| Duplicate `(date, stock_id)` | **0** |
| Duplicate `(date, isin)` | **0** |
| Adjusted OHLC violations | **0** |
| Non-positive adjusted close | **0** |
| Negative adjusted volume | **0** |
| Latest `adj_factor != 1.0` | **0** |
| Unexplained action mismatches | **0** |
| `ca_factor_mismatch` | **116** |
| `ca_observed_adjustment` | **111** |
| `ca_not_reflected` | **5** |
| `ca_unadjusted` | **194** |
| `ca_rights_unknown` | **480** |
| `delivery_missing` | **1,821** |

`ca_factor_mismatch` is not an error count. It means the official action and
the tape disagreed; 111 rows used the observed ratio and 5 rows used 1.0.
The audit trail is in `flags`.

## Important flags

| Flag | Meaning |
|---|---|
| `bse_only` | No NSE match; BSE row is the only price |
| `bse_fallback` | NSE symbol exists, but NSE had no row that date; BSE used |
| `bse_unmatched` | Old BSE row with no current crosswalk; possible duplicate of a delisted NSE name |
| `old_bse_no_isin` | 2020–2023 BSE row; no ISIN/ticker in source |
| `identity_change` | BSE scrip had a real ISIN/name/symbol change |
| `bse_only_date` | 2021-11-04 BSE-only session |
| `ca_late` | Action applied at the first row after the ex-date |
| `ca_observed_adjustment` | Official factor replaced by observed price ratio |
| `ca_not_reflected` | Official action not visible in the tape; factor set to 1.0 |
| `ca_unadjusted` | Demerger/scheme/other; no price factor |
| `ca_rights_unknown` | Rights action without ratio/price; not adjusted |
| `delivery_flag` | NSE delivery data internally inconsistent on that date |
| `delivery_missing` | Delivery quantity/percentage is blank or `-` |

## Known limitations

- **No dividends**: price-return only. Do not use for total-return studies.
- **NSE `isin` is current**, not point-in-time (`isin_source=nse_master_current`).
  BSE 2024+ ISIN is point-in-time. BSE 2020–2023 has no ISIN.
- **Old BSE identity**: 2020–2023 BSE rows are matched by current
  `scrip_code` crosswalk where possible. 1,653,106 rows are `bse_unmatched`;
  they may include delisted dual-listed names. Do not treat them as a clean
  NSE complement without checking.
- **`bse_fallback`** rows can have different liquidity/microstructure from NSE.
- **Corporate actions are parsed from free text**. 20 `SPLIT_UNKNOWN`, 480
  `RIGHTS_UNKNOWN`, 194 `ca_unadjusted` rows are deliberately not adjusted.
  Exclude them from return studies or review them individually.
- **No minute/intraday, options, tick, or index-constituent history** yet.

## Commands

```bash
# refresh corporate actions (network)
python3 jobs/fetch_corporate_actions.py --start 2020-01 --end 2026-11

# reparse saved raw JSON without network
python3 jobs/fetch_corporate_actions.py --parse-only --start 2020-01 --end 2026-11

# rebuild the panel
python3 jobs/build_adjusted_panel.py \
  --start 2020-01-01 --end 2026-11-19 \
  --output data/curated/panel.csv \
  --manifest data/curated/MANIFEST.json
```

## Next

Features and the first honest backtest are now built:

- `engine/features.py` — deterministic DMA/ATR/RSI/ADX/volume state.
- `jobs/backtest_trend_pullback.py` — next-open entry, stop/target, costs,
  slippage, walk-forward split.
- Result: **failed** the out-of-sample gate. See `docs/phase1-backtest.md`.

Do not build the sellable product on this strategy. The next step is a second
pre-registered setup or a market-regime overlay, then walk-forward/CPCV/Monte
Carlo with costs.
