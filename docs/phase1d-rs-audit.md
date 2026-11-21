# Phase 1D — RS rank build audit

**Date:** 2026-11-21
**Script:** `jobs/build_rs_rank.py`
**Output:** `data/curated/rs_rank.csv`
**Manifest:** `data/curated/rs_rank_manifest.json`

## What was built

For every NSE `EQ` stock and every trading date in the panel:

```
ret63        = adj_close(D) / adj_close(63 sessions earlier) - 1
ret126       = adj_close(D) / adj_close(126 sessions earlier) - 1
ret63_excess = ret63 - Nifty50 ret63
ret126_excess= ret126 - Nifty50 ret126
rs_pct       = average(percentile_rank(ret63_excess),
                       percentile_rank(ret126_excess))
```

`percentile_rank` is the average-rank percentile in `[0, 1]` across the
eligible NSE universe on that date. Ties share the average rank. Only rows
with `rs_pct >= 0.80` are written; H4 trades the `>= 0.90` subset.

## Eligibility

Same as the H4 pre-registration:

- NSE, series `EQ`.
- ETFs, BEES, exchange-traded funds, mutual funds, REITs and InvITs excluded
  by symbol/name token.
- Raw close >= ₹20 (the trade engine uses raw close for this filter).
- 20-session average turnover >= ₹1 crore.
- At least 127 own-session closes, so both 63- and 126-session returns exist.

The Nifty 50 return uses the cleaned `data/index/nifty50.csv` series and the
same 63/126 own-session lookback.

## Counts

| Item | Value |
|---|---:|
| Dates with ranks | 1,575 |
| Eligible stock-days | 1,844,383 |
| Rows kept (`rs_pct >= 0.80`) | 309,636 |
| Rows in top decile (`rs_pct >= 0.90`) | 141,288 |
| Duplicate `(date, stock_id)` keys | 0 |
| Out-of-range `rs_pct` values | 0 |
| First date | 2020-07-07 |
| Last date | 2026-11-19 |

The first date is July 2020 because a stock needs 127 own sessions; the first
H4 signals need a 200DMA, so they start later (around October 2020).

## No-look-ahead checks

1. For a date `D`, every input close is on or before `D`.
2. The Nifty return for `D` uses Nifty closes on or before `D`.
3. Percentile ranks use only the cross-section on `D`.
4. The backtest reads the RS value for the signal date only and never reads a
   future date.
5. The stock history is the stock's own sessions, so a missing trading day does
   not pull in a future close.

**Sample recomputation:** for `2020-07-07`, the build was recomputed
independently from the panel. 725 stocks were eligible and 91 rows were stored
at `rs_pct >= 0.80`; all 91 stored `rs_pct`, `ret63_excess` and
`ret126_excess` values matched to 1e-6. Mismatches: 0.

## Caveats

- The panel is price-return only. Dividends are not included.
- Nifty data is Yahoo-identical, not an official licensed NSE feed.
- The NSE symbol/ISIN master is current, not point-in-time; historical
  survivorship is reduced but not eliminated.
- Adjusted prices use the corporate-action factors in the panel. This is the
  standard back-adjustment; returns across a split/bonus are economically
  correct, but the adjustment itself is not a live-data feed.
- A stock that is not in the top quintile file for a date has no RS row. The
  backtest treats that as "not eligible", which is conservative.
