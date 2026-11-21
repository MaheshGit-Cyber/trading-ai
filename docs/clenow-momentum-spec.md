# Clenow Momentum + Quarterly Rebalance — Pre-registered Spec

**Status:** PRE-REGISTERED / TRAIN-FIRST  
**Created:** 2026-11-22  
**Split:** 2024-12-10 (train before, test after)  
**Primary job:** `jobs/backtest_clenow_momentum.py`  
**Helper:** `brain/scorer.py::calculate_clenow_momentum`

This document freezes the rules before the train run. No rule may be changed
after seeing test results. Train is evaluated first; test is not run until the
train gate passes (or an explicit `--force-test` override is recorded).

## 1. Hypothesis

A smooth, persistent 90-session log-linear trend, penalised by its regression
R², selects steadier compounders than raw 12-1 momentum. Quarterly
rebalancing and a 100DMA exit reduce turnover and cost drag. A Nifty 50
200DMA regime overlay de-risks into 50% GOLDBEES + 50% LIQUIDBEES instead of
idle cash.

## 2. Data

- **Equities:** `data/curated/panel_nse_isin_v3.csv` (ISIN-continuous NSE
  panel), NSE `EQ` series only.
- **Nifty regime:** `data/index/nifty50.csv`, close vs 200-session SMA.
- **GOLDBEES:** `data/gold/goldbees_daily_2010_2026.csv` (split-adjusted
  continuous series; the panel has two ISINs around the 2019 split).
- **LIQUIDBEES:** panel rows for `NSE:INF732E01037`.
- **Corporate actions:** use the panel's `adj_close` for the Clenow score and
  the 100DMA exit; use raw `open`/`close` plus `adj_factor` for portfolio
  accounting, matching the existing delivery-cost simulator.

## 3. Universe (point-in-time, no survivorship filter)

At each signal close:

1. NSE `EQ`, raw close ≥ ₹20.
2. 20-session average turnover ≥ ₹10 crore (`turnover_lacs ≥ 1000`).
3. Exclude ETFs, BeES, mutual funds, REITs and InvITs by name/symbol token.
4. Exclude names with corporate-action risk flags:
   `ca_unadjusted`, `ca_rights_unknown`, `ca_split_unknown`,
   `ca_bonus_unknown`, `ca_not_reflected`.
5. Exclude names with any circuit-locked bar in the last 20 sessions
   (`high <= low * 1.0001` as the local proxy; the panel has no dedicated
   circuit flag).
6. Rank the remaining names by 20-session average turnover and keep the
   **top 100**. This is a liquidity proxy for F&O eligibility because a
   point-in-time F&O list is not available locally.

## 4. Signal

For each eligible name with at least 100 adjusted closes:

- Clenow score = annualised slope of `log(adjusted close)` over the last 90
  sessions, multiplied by the regression R².
- Require `adjusted close > 100-session simple moving average`.
- Require `Clenow score > 0`.

Rank the top-100 liquid names by Clenow score descending and select the top
**10** (allowed range 10–15; 10 is the primary). Ties break by `stock_id`.

## 5. Position sizing

- Raw weight inversely proportional to 20-session ATR.
- Cap each name at **10%** of current equity; redistribute excess among
  uncapped names.
- If fewer than 10 names are eligible, the residual is held as cash.
- Maximum 15 names.

## 6. Rebalance and exits

- **Primary cadence:** quarterly top-up, every 63 Nifty trading sessions.
- **Full reconstitution:** every 126 sessions (semi-annual), or on a regime
  transition from OFF to ON.
- Signal at the session close; execute at the next session's open.
- **Quarterly top-up:** keep an existing holding if it is still in the
  point-in-time top-100 liquid universe and still above its 100DMA; hold its
  previous target weight. Fill empty slots with the highest-Clenow new names
  and size only the new names from the remaining cash. This is the
  "hold winners longer" rule.
- **Full reconstitution:** sell names outside the fresh top-10 and re-weight
  the fresh target by inverse ATR, capped at 10%.
- **100DMA exit (primary):** if a held stock's adjusted close falls below its
  100-session SMA, queue a sell for the next session's open. `--no-daily-dma-exit`
  is a lower-turnover diagnostic that checks the 100DMA only at rebalance.
- A name below its 100DMA is never eligible for entry.
- First signal is after a 100-session warm-up from the requested start date.

## 7. Regime / de-risk overlay

- Primary evaluation is at each rebalance signal close.
- If Nifty 50 close > 200-session SMA: hold the selected stocks.
- If Nifty 50 close ≤ 200-session SMA: hold **50% GOLDBEES + 50%
  LIQUIDBEES** until the next rebalance.
- No daily regime switching in the primary run; daily switching is left as a
  future diagnostic because it reintroduces the 200DMA whipsaw.

## 8. Costs and execution

Use the existing Budget-2026 equity-delivery model in
`jobs/backtest_monthly_momentum.py`:

- STT 0.10% each side, exchange 0.00297%, SEBI 0.0001%, stamp 0.015% buy,
  DP ₹13.5 sell, GST 18%.
- Slippage by 20-session turnover: 0.10% (≥ ₹10 crore), 0.25%
  (₹1–10 crore), 0.50% (< ₹1 crore) one-way.
- Primary run: 1× slippage. Stress run: 2× slippage.
- No leverage. No shorting. Delivery only.
- Delisting/stale positions: 90-day zero-recovery write-off for names that
  never trade again; still-listed suspended names are held at last close.

## 9. Train/test and gate

**Train:** first signal after warm-up through 2024-12-10.  
**Test:** 2024-12-11 through 2026-11-19.  
**Minimum test:** 4 quarterly rebalances.

### Train gate (must pass before test)

| Condition | Threshold |
|---|---|
| Net CAGR | > 0 |
| Net CAGR vs Nifty 50 TR proxy (price + 1.2%/yr) | > 0 excess |
| Net Sharpe | > 0.50 |
| Max drawdown | ≥ −28% |
| Profit factor (monthly) | > 1.20 |
| 2× slippage net CAGR | > 0 |
| Annual cost drag | < 0.50% |
| Annual turnover | < 1.5× |
| Quarterly rebalances | ≥ 12 |

### Test gate (only after train passes)

Same as train, except: test net CAGR > 0, test Sharpe > 0, test profit
factor > 1.00, test 2× CAGR > 0, test max drawdown ≥ −28%, test cost drag
< 0.50%/yr, test turnover < 1.5×/yr, and at least 4 quarterly rebalances.

Decision values: `TRAIN_PASS`, `TRAIN_FAIL`, `PASS`, `FAIL`,
`INSUFFICIENT_OOS`.

If train fails, the result is `TRAIN_FAIL`; no test result is reported and no
tuning is allowed on the test period.

## 10. Known limitations

- No point-in-time F&O eligibility list; top-100-by-turnover is a proxy.
- No point-in-time sector master; sector concentration is not measured here.
- No historical market-cap data; the universe is a liquidity proxy, not a
  true large-cap universe.
- GOLDBEES uses the split-adjusted gold file; LIQUIDBEES uses panel rows.
- Stock dividends are not modelled; the Nifty TR proxy is price + 1.2%/yr.
- Circuit-locked detection is a high/low proxy, not an exchange flag.
- The current NSE master is used only to distinguish still-listed from
  genuinely delisted names; classification look-ahead is documented.
- This is research, not investment advice.
