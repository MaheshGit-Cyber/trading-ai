# A2 — Cross-Sectional Momentum: Results

**Status: FAIL** (pre-registered primary run: Nifty 200DMA ON, 1× costs).
**Date:** 2026-11-21
**Spec:** `docs/a2-cross-sectional-momentum-spec.md` (frozen before the run)
**Spec SHA-256:** `fa4aa76e8ea099bfbfd6d381aeab477c856f3926d71b92dec9f2b471907e5f1e`
**Job:** `jobs/backtest_a2_momentum.py`
**Outputs:** `data/backtest/a2_momentum/`

> The strategy was not changed after the out-of-sample result. The OFF
> regime run, the 2× cost run, the zero-recovery run and the equal-weight
> benchmark are diagnostics; they do not replace the pre-registered primary.

## 1. What was tested

- Panel: `data/curated/panel_nse_isin_v3.csv`, ISIN-continuous NSE stocks,
  2010-01-04..2026-11-19.
- Universe: point-in-time top 200 by 20-session average turnover, NSE `EQ`,
  raw price >= ₹20, 20D turnover >= ₹1 crore, at least 253 own sessions,
  ETF/REIT/InvIT and unresolved corporate-action flags excluded.
- Signal: 12–1 month momentum,
  `adj_close(D-21) / adj_close(D-252) - 1`, cross-sectional.
- Portfolio: long-only top decile (20 of 200), equal weight, monthly.
- Execution: month-end signal, next session open.
- Regime: Nifty 50 close > 200-session SMA. ON = cash when false; OFF =
  always invested.
- Costs: full delivery STT, exchange, SEBI, stamp, DP, GST, turnover-tier
  slippage; 2× slippage stress.
- Split: 2024-12-10. Test = 23 monthly rebalances (minimum 20).
- Delisting: 90-day write-off for names absent from the current NSE master;
  still-listed suspended names held at last close. Zero-recovery sensitivity
  reported separately.

## 2. Primary result (Nifty 200DMA ON, 1× costs)

| Segment | CAGR | Sharpe | Profit factor | Max drawdown | Months |
|---|---:|---:|---:|---:|---:|
| Full (net) | **9.38%** | 0.56 | 1.61 | **-43.74%** | 190 |
| Train (net) | **11.05%** | 0.63 | 1.66 | -43.74% | 167 |
| Test (net) | **-2.06%** | **-0.07** | **0.95** | -15.33% | 23 |
| Full (gross add-back) | 11.03% | 0.71 | 1.83 | -35.63% | 190 |
| Train (gross add-back) | 12.61% | 0.78 | 1.88 | -35.63% | 167 |
| Test (gross add-back) | 0.17% | 0.08 | 1.18 | -11.41% | 23 |

- Net full-sample CAGR is **below Nifty 50 price (10.31%)** and below the
  Nifty 50 total-return proxy (11.63%).
- Net full-sample maximum drawdown (-43.74%) is **worse than Nifty 50**
  (-38.44%).
- The maximum drawdown ran from 2018-01-23 to 2019-10-07.
- Gross test return is only +0.17%; after costs the test is negative. A
  positive gross return is not sufficient, and this one is not even positive
  after realistic frictions.

## 3. Stress and diagnostics

| Run | Full CAGR | Train CAGR | Test CAGR | Test Sharpe | Test PF | Test max DD |
|---|---:|---:|---:|---:|---:|---:|
| ON, 1× (primary, net) | 9.38% | 11.05% | **-2.06%** | -0.07 | 0.95 | -15.33% |
| ON, 2× (net) | 6.95% | 8.50% | **-3.77%** | -0.18 | 0.81 | -16.52% |
| OFF, 1× (net) | 13.56% | 14.96% | +3.74% | 0.27 | 1.27 | -27.83% |
| OFF, 2× (net) | 10.46% | 11.80% | +1.03% | 0.17 | 1.18 | -28.41% |
| Zero-recovery, ON, 1× | 9.22% | 10.85% | -2.01% | -0.06 | 0.96 | -15.47% |

- **The Nifty 200DMA filter did not add robust value.** It improved the test
  drawdown (-15.33% vs -27.83%) but turned the test return negative
  (-2.06% vs +3.74%). Over the full sample it slightly worsened the return
  (9.38% vs 13.56%) and barely changed the full drawdown (-43.74% vs
  -43.60%).
- **Gross add-back for the OFF diagnostic:** full 14.78%, train 15.90%,
  test 6.94% (test Sharpe 0.42, PF 1.38, max drawdown -20.85%). The OFF
  gross test return is below the equal-weight large-cap benchmark (7.99%)
  and its test drawdown is still worse than the product target.
- **2025 vs 2026 whipsaw.** ON returned +2.97% in 2025 and -4.78% in 2026.
  OFF returned -7.29% in 2025 and +18.18% in 2026. The filter avoided the
  early-2025 fall but sat in cash through the 2026 rebound.
- **Delisting treatment does not change the conclusion.** Zero recovery for
  all stale names gives test CAGR -2.01% (base -2.06%).
- **Stress costs worsen the failure.** At 2× slippage the test CAGR is
  -3.77% and the test profit factor is 0.81.

## 4. Benchmark comparison

| Benchmark | Full CAGR | Train CAGR | Test CAGR | Full Sharpe | Full max DD |
|---|---:|---:|---:|---:|---:|
| A2 ON, net | 9.38% | 11.05% | -2.06% | 0.56 | -43.74% |
| A2 OFF, net | 13.56% | 14.96% | +3.74% | 0.66 | -43.60% |
| Nifty 50 price | 10.31% | 11.54% | +1.81% | 0.70 | -38.44% |
| Nifty 50 TR proxy (1.2%/yr) | 11.63% | 12.88% | +3.03% | — | — |
| Equal-weight top-200 large caps, gross | **17.73%** | **19.15%** | **+7.99%** | 0.85 | -40.94% |

- The 12–1 top-decile selection **destroyed value versus a simple
  equal-weight large-cap basket**. Even the gross A2 full return (11.03%)
  is far below the gross equal-weight benchmark (17.73%); the gross test
  return (0.17%) is far below 7.99%.
- The equal-weight benchmark is gross of costs and may be upward-biased by
  incomplete delisted-name coverage. The gap is too large to be explained by
  costs alone: the A2 cost drag is about 3.2%/yr (ON) and 3.6%/yr (OFF).
- No Nifty 200 index history is available locally. Nifty 50 is the
  appropriate large-cap benchmark; the total-return series is a 1.2%/yr
  dividend-yield proxy, not licensed TR data.

## 5. Pre-registered gate

| Condition | Result | Value |
|---|---|---:|
| Full net CAGR > 0 | PASS | 9.38% |
| Train net CAGR > 0 | PASS | 11.05% |
| Test net CAGR > 0 | **FAIL** | -2.06% |
| Test net Sharpe > 0 | **FAIL** | -0.07 |
| Test 2× stress CAGR > 0 | **FAIL** | -3.77% |
| Test max drawdown >= -28% | PASS | -15.33% |
| Full PF > 1.2 | PASS | 1.61 |
| Train PF > 1.0 | PASS | 1.66 |
| Test PF > 1.0 | **FAIL** | 0.95 |
| Test CAGR > Nifty 50 TR proxy | **FAIL** | -2.06% vs 3.03% |
| Test months >= 20 | PASS | 23 |

**Decision: FAIL.** Five of the eleven pre-registered conditions fail,
including the three core out-of-sample conditions (return, Sharpe, stress
return), the test profit factor, and the benchmark gate.

Product target (reported, not the research gate): the test drawdown is
within -20%, but the test CAGR does not beat the Nifty TR proxy by 5%.

## 6. Year-wise net returns

| Year | ON | OFF |
|---|---:|---:|
| 2011 | +5.11% | -10.97% |
| 2012 | +10.56% | +32.24% |
| 2013 | -26.74% | -18.07% |
| 2014 | +96.51% | +91.60% |
| 2015 | -17.47% | -10.62% |
| 2016 | -1.10% | -24.89% |
| 2017 | +62.23% | +79.42% |
| 2018 | -33.16% | -25.37% |
| 2019 | -0.10% | +10.94% |
| 2020 | +45.34% | +38.65% |
| 2021 | +54.60% | +54.53% |
| 2022 | -10.98% | +1.43% |
| 2023 | +17.83% | +36.38% |
| 2024 | +20.66% | +20.92% |
| 2025 | +2.97% | -7.29% |
| 2026 | -4.78% | +18.18% |

The return stream is highly uneven. Large up-years (2014, 2017, 2020,
2021) are followed by large down-years (2013, 2018). The full-sample
drawdown is a real risk, not a backtest artefact.

## 7. Regime-wise net returns

| Run | Regime | Months | Avg month | Hit rate | Compound | Worst month | Best month |
|---|---|---:|---:|---:|---:|---:|---:|
| ON | Risk-on | 134 | +1.37% | 57.5% | +358.1% | -18.37% | +21.33% |
| ON | Risk-off | 56 | -0.19% | 7.1% | -9.97% | -3.05% | +1.82% |
| OFF | Risk-on | 134 | +1.36% | 58.2% | +357.8% | -18.43% | +19.25% |
| OFF | Risk-off | 56 | +1.25% | 58.9% | +58.1% | -28.78% | +19.79% |

The always-invested strategy made money on average in Nifty-below-200DMA
months (+1.25%/month) but with a -28.78% worst month. The filter removed
that tail risk and also removed the rebound. The overlay is not robust.

## 8. Turnover, costs, exposure and delisting

| Metric | ON 1× | OFF 1× |
|---|---:|---:|
| Rebalances | 190 | 190 |
| Trades | 3,866 | 5,122 |
| Annual turnover | 7.59× | 8.85× |
| Total costs (₹, 2011–2026) | 11.00 lakh | 16.31 lakh |
| Annual cost drag | 3.16% | 3.61% |
| Average exposure | 70.8% | 99.1% |
| Maximum holdings | 28 | 28 |
| Average stale weight | 4.5% | 7.0% |
| Maximum stale weight | 30.3% | 30.3% |
| Write-offs | 7 names, ₹5.61 lakh | 7 names, ₹6.99 lakh |

Trade-level statistics:

| Run | Period | Trades | Buys | Sells | Write-offs | Trade value (₹ lakh) | Costs (₹ lakh) |
|---|---|---:|---:|---:|---:|---:|---:|
| ON | Full | 3,866 | 2,042 | 1,817 | 7 | 2,646.78 | 11.00 |
| ON | Train | 3,564 | 1,891 | 1,666 | 7 | 2,207.23 | 9.13 |
| ON | Test | 302 | 151 | 151 | 0 | 439.55 | 1.87 |
| OFF | Full | 5,122 | 2,800 | 2,315 | 7 | 3,993.86 | 16.31 |
| OFF | Train | 4,504 | 2,461 | 2,036 | 7 | 2,900.66 | 11.90 |
| OFF | Test | 618 | 339 | 279 | 0 | 1,093.20 | 4.40 |

Trade-level costs are execution costs. Round-trip trade P&L is not reported
because the monthly rebalance creates partial positions and overlapping
holds; the portfolio statistics above are the primary result.

- The ON cash overlay lowers average exposure to 70.8%, but the cost drag is
  still 3.16%/yr because the monthly rebalance and cash transitions are
  expensive.
- **Brokerage sensitivity:** the pre-registered base model assumes zero
  delivery brokerage (a discount-broker delivery account). A ₹20/order
  sensitivity adds ₹0.77 lakh (ON, 3,866 trades) or ₹1.02 lakh (OFF, 5,122
  trades) over the full run, roughly 0.2–0.5%/yr on capital. It cannot change
  the FAIL. The 2× slippage stress is the main cost sensitivity.
- Stale/suspended names can reach 30.3% of equity. The 90-day write-off and
  the zero-recovery sensitivity are reported; the conclusion is unchanged,
  but this is a real execution risk.

## 9. Sector concentration (data gap)

There is **no point-in-time sector master** in the local data. The reported
sector table is a name-based keyword proxy and is diagnostic only.

| Proxy sector | Average weight |
|---|---:|
| Other (unclassified) | **52.6%** |
| Financials | 9.9% |
| Pharma/Healthcare | 5.3% |
| Energy | 5.2% |
| IT | 4.8% |
| Auto | 3.6% |
| Chemicals | 2.9% |
| Banks | 2.7% |
| Metals | 2.3% |
| FMCG | 1.6% |

The proxy leaves 52.6% of holdings unclassified, and some rebalances are
100% "Other". **No valid sector-concentration conclusion can be drawn from
this table.** A point-in-time sector master is required before a sector
claim is made.

## 10. Data quality and sample

- 190 monthly signals, 2011-01-31..2026-10-30; 190 rebalances.
- Eligible universe: min 296, median 694, max 1,415 stocks.
- Large-cap universe: always 200 stocks.
- Selected: 20 stocks in every invested month; 0 in risk-off months.
- Unique selected over the full run: 613 stocks.
- Regime signals: 134 risk-on, 56 risk-off.
- Test: 23 monthly rebalances (minimum 20 met).
- Test bootstrap p-value for mean monthly net return > 0: **0.534**;
  test mean monthly return -0.045%. No statistical evidence of an edge.

## 11. Interpretation

1. **No out-of-sample edge.** The primary strategy loses money after costs
   in the test period, loses more at 2× slippage, and has a test profit
   factor below 1.
2. **The full-sample result is also weak.** Lower CAGR than Nifty 50, worse
   maximum drawdown, lower Sharpe. The strategy is dominated by the index
   on a full-sample risk-adjusted basis.
3. **The 12–1 top-decile selection did not add value.** A simple
   equal-weight top-200 large-cap basket earned 17.73% gross full and 7.99%
   gross test; the strategy earned 11.03% gross full and 0.17% gross test.
   The selection is the problem, not only the costs.
4. **The Nifty 200DMA overlay is not a robust fix.** It reduced the test
   drawdown but turned the test return negative and did not reduce the
   full-sample drawdown. It whipsawed in 2025–2026.
5. **The risk is too high for a product.** A -43.74% full-sample drawdown,
   -33.16% in 2018, -26.74% in 2013, and 30.3% stale exposure are not
   compatible with a retail signals product.
6. **Costs are material.** 3.16–3.61%/yr cost drag; the gross test return is
   only +0.17%, so the net result is negative.

## 12. Decision

**FAIL. Do not monetize. Do not tune this strategy on the test result.**

The A2 family (12–1 top-decile large-cap momentum with a Nifty 200DMA
overlay) is not validated. The OFF variant is better in the test period but
was not the pre-registered primary, still underperforms the equal-weight
large-cap benchmark, and has a -27.83% test drawdown. It is not a substitute
for a validated edge.

If research continues, the next step must be a **new pre-registered
hypothesis**, not a parameter change to A2. The open options are:

- A1: Quantpedia-style 1-day pullback on liquid large caps/ETFs.
- A3: real-time tick infrastructure (no validated edge yet).
- Stop the momentum/pullback family and reassess.

## 13. Limitations

- No Nifty 200 index history; Nifty 50 price + 1.2%/yr TR proxy is used.
- No historical market-cap data; the large-cap universe is a
  top-200-by-turnover liquidity proxy, not a market-cap index.
- No point-in-time sector master; sector concentration is not validly
  measured. The name-based proxy also uses the latest company name.
- Current NSE master is used for delisting classification (look-ahead in the
  classification only, not in the signal or portfolio membership).
- The base cost model assumes zero delivery brokerage; the ₹20/order
  sensitivity is reported above.
- No circuit-limit fill model beyond the 5% ADV cap and slippage tiers.
- Equal-weight benchmark is gross and may be upward-biased by incomplete
  delisted-name coverage.
- The test window is 23 months; it meets the pre-registered minimum but is
  statistically short.

## 14. Artifacts

- `data/backtest/a2_momentum/summary_a2_momentum.json` — primary and
  diagnostic runs, gate, benchmarks, regime-wise, sector proxy.
- `data/backtest/a2_momentum/gross_a2_momentum.json` — gross cost add-back.
- `data/backtest/a2_momentum/monthly_on.csv`, `monthly_off.csv` — monthly net
  returns.
- `data/backtest/a2_momentum/trades_on.csv`, `trades_off.csv` — trades.
- `data/backtest/a2_momentum/holdings_on.csv` — rebalance holdings.
- `data/backtest/a2_momentum/curve_on.csv` — daily net equity curve.
- `jobs/backtest_a2_momentum.py` — backtest.
- `jobs/analyze_a2_momentum.py` — gross add-back report.
- `tests/test_a2_momentum.py` — 12 tests.
