# A2 — Cross-Sectional Momentum: Pre-Registered Specification

**Status:** FROZEN before the first full run.
**Date:** 2026-11-21
**Owner:** Trading AI research
**Prompt:** `prompt.txt` (A2 Cross-Sectional Momentum)

> This file is the pre-registration. No rule, parameter, universe definition,
> cost assumption, split, or gate may change after the first full run. If a
> data gap forces a change, the change must be disclosed and the run labelled
> as a new, separate test.

## 1. Objective

Test whether a long-only, equal-weighted, top-decile 12–1 month momentum
portfolio on a point-in-time liquid NSE large-cap universe has a robust,
cost-adjusted edge after the 2024-12-10 out-of-sample split.

This is a new test. It is **not** the old Phase 2A/2B 63/126-session excess-RS
strategy. Phase 2B is closed and failed; its rules are not reused.

## 2. Data

| Item | Source | Notes |
|---|---|---|
| Prices | `data/curated/panel_nse_isin_v3.csv` | ISIN-continuous stock IDs, 2010-01-04..2026-11-19, adjusted OHLCV, raw close, 20D turnover, flags |
| Market index | `data/index/nifty50.csv` | Nifty 50 price index; used for the 200DMA regime and as the benchmark |
| Delisting classification | `data/nse_equity_master.csv` | Current NSE master; used only to distinguish still-listed suspended names from names absent from the master |
| Corporate actions | panel `adj_factor` / `flags` | Share-count adjustment; unresolved CA flags exclude a stock from selection |

Known data limitations, disclosed before the run:

- No point-in-time sector master exists locally. Sector concentration is
  reported with a **name-based sector proxy** and is diagnostic only.
- The benchmark is Nifty 50 **price** return. A total-return proxy adds a
  constant 1.2%/yr dividend yield. The proxy is labelled, not presented as
  licensed index data.
- No Nifty 200 index history is available locally. Nifty 50 is the appropriate
  large-cap benchmark for this universe; the Nifty 200 is not fabricated.
- The current NSE master is used for delisting classification. This is a
  look-ahead limitation for the *classification*, not for the signal or
  portfolio membership. The base treatment is the least biased of the
  available options.
- No circuit-limit fill model beyond the 5% ADV cap and the slippage tiers.

## 3. Universe (point-in-time, monthly)

At each month-end signal date `D`, a stock is eligible only if **all** hold:

1. NSE, series `EQ`.
2. `stock_id` is ISIN-continuous in the panel.
3. Raw close on `D` >= ₹20.
4. At least 253 own trading sessions of history up to and including `D`.
5. 20-session average turnover on `D` >= ₹100 lakh (₹1 crore).
6. The stock traded on `D` (no stale last-seen row).
7. Not an ETF, BEES, exchange-traded fund, mutual fund, REIT, or InvIT.
8. No unresolved corporate-action flag from:
   `ca_unadjusted`, `ca_rights_unknown`, `ca_split_unknown`,
   `ca_bonus_unknown`, `ca_not_reflected`.

From the eligible set, the **large-cap universe** is the top 200 by 20-session
average turnover on `D`. This is a point-in-time, liquidity-based proxy for a
liquid large-cap universe. No current index membership is used.

## 4. Signal

At each month-end close `D`:

```
mom_12_1 = adj_close(D - 21 sessions) / adj_close(D - 252 sessions) - 1
```

- The most recent 21 sessions (one month) are skipped.
- Both prices come from the stock's own trading sessions.
- The signal uses only data through `D`.
- Cross-sectional ranking is on `mom_12_1`, descending.
- No excess-versus-Nifty return is used in the signal. The Nifty is used for
  the regime filter and the benchmark only.

## 5. Portfolio

- Long-only, no shorting, no leverage.
- Top decile of the large-cap universe by `mom_12_1`:
  `N = max(1, floor(0.10 * len(large_cap_universe)))`.
- Equal weight: each selected stock targets `1/N` of current portfolio equity.
- Maximum 20 names (the decile of a 200-name universe).
- If fewer than `N` names are eligible, hold cash for the difference.
- No pyramiding, no averaging down, one position per stock.
- Maximum 5% of the stock's 20-session average daily turnover per position.
- No negative cash; buys are scaled down if costs would overdraw cash.

## 6. Rebalance and execution

- Signal date: the last NSE trading session of each calendar month.
- Execution: the open of the next NSE trading session (normally the first
  session of the next month).
- If a held stock has no valid open on the execution date, the sell is retried
  on the first later session with a valid open; it is cancelled if the stock
  re-enters the target.
- If a target stock has no valid open on the execution date, it is skipped for
  that month; no intraday substitution.
- Sells execute before buys.
- A stock that remains in the target is rebalanced to its target weight, not
  sold and rebought for no reason.
- Daily mark-to-market at the close.

## 7. Market regime (Nifty 200DMA filter)

At signal date `D`:

```
regime_on = Nifty50_close(D) > 200-session SMA(Nifty50_close, D)
```

- **ON (primary):** if `regime_on` is false, the target portfolio for the next
  month is 100% cash. Existing holdings are sold at the next open. If
  `regime_on` is true, the top decile is held.
- **OFF (diagnostic):** always hold the top decile; no cash overlay.
- The regime is defined before the run. It is not tuned.
- The ON run is the primary gate run. The OFF run is a controlled comparison.

## 8. Costs

Full Budget-2026 equity-delivery model, charged on every trade:

- STT 0.1% buy, 0.1% sell.
- Exchange, SEBI, stamp duty, GST.
- DP ₹13.5 per sell.
- One-way slippage by 20D turnover:
  - >= ₹1,000 lakh: 0.10%
  - ₹100–1,000 lakh: 0.25%
  - < ₹100 lakh: 0.50%
- **Stress:** 2× the one-way slippage, same statutory charges.
- No brokerage beyond the above. A user's actual broker charges are additional.
- Costs are reported as annual turnover and annual cost drag, not assumed away.

## 9. Delisting and stale positions

Base treatment (primary):

- After 90 calendar days without a traded price, write off a holding at **zero**
  only if the stock is absent from the current NSE master.
- A still-listed but suspended name (present in the current master) is held at
  its last close until it trades again.
- Corporate-action share adjustments are applied from `adj_factor` before
  trading.

Sensitivity (reported, not the gate): zero recovery for **all** names with no
future panel row after 90 days. This is a conservative bound for `BE`/`BZ`
moves that the raw panel does not contain.

## 10. Split and sample

- Full sample: first signal after 253 sessions of history, 2011-01-01 onward,
  through 2026-11-19.
- Train: dates <= 2024-12-10.
- Test: dates > 2024-12-10.
- Minimum test sample: **20 monthly rebalances**. If fewer, return
  `INSUFFICIENT_OOS`.
- The split is fixed. No test data is used to choose the universe, signal,
  portfolio, regime, costs, or gates.

## 11. Benchmarks

- Nifty 50 buy-and-hold, price return.
- Nifty 50 total-return **proxy**: price return + 1.2%/yr dividend yield.
- Equal-weight large-cap universe, monthly rebalanced, **gross of costs**
  (diagnostic; survivorship-biased upward, so not a hard gate).
- The strategy is compared on CAGR, Sharpe, max drawdown, and test-period
  return. A positive gross return alone is not sufficient.

## 12. Required reported results

- Full, train, and test portfolio statistics.
- Gross and net returns. Gross is a cost add-back approximation:
  `gross_equity(t) = net_equity(t) + cumulative_costs(t)`.
- CAGR, Sharpe, Sortino, profit factor, maximum drawdown.
- Annual turnover and total transaction costs.
- Year-wise returns.
- Regime-wise returns (Nifty 200DMA ON vs OFF).
- Top-decile vs Nifty 50 price, Nifty 50 TR proxy, and equal-weight large-cap.
- Nifty 200DMA filter ON vs OFF comparison.
- Sector concentration (name-based proxy) and portfolio exposure.
- 2× slippage stress results.
- Delisting base vs zero-recovery sensitivity.
- Final gate decision: PASS, FAIL, or INSUFFICIENT_OOS.

## 13. Pre-registered gate (primary = regime ON, 1× costs)

`INSUFFICIENT_OOS` if test monthly rebalances < 20.

`PASS` only if **all** of the following hold:

1. Full net CAGR > 0.
2. Train net CAGR > 0.
3. Test net CAGR > 0.
4. Test net Sharpe > 0.
5. Test net CAGR at 2× slippage > 0.
6. Test maximum drawdown >= -28% (research gate).
7. Full profit factor > 1.2.
8. Train profit factor > 1.0.
9. Test profit factor > 1.0.
10. Test net CAGR > Nifty 50 TR proxy CAGR.
11. Test sample >= 20 monthly rebalances.

Otherwise `FAIL`.

Product-readiness target (reported, not the research gate):
test maximum drawdown >= -20% and test net CAGR > Nifty 50 TR proxy CAGR + 5%.

## 14. Diagnostics (not gates)

- Regime OFF run.
- Zero-recovery delisting bound.
- Equal-weight large-cap benchmark.
- Random top-decile baseline (same dates, same costs), if time permits.
- Sector proxy concentration.
- Monthly return distribution and hit rate.
- Bootstrap p-value for the test-period mean monthly net return.

Diagnostics do not change the gate. If the primary fails, the family is not
tuned on the test result.
