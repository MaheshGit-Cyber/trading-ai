# Phase 2A — Monthly Cross-Sectional Momentum (2020–2026 Preliminary)

Status: **preliminary; product gate NOT passed. Do not tune this run.**

> Superseded by Phase 2B (2010–2026): the full-history run also fails the
> drawdown, cost-stress, and DSR gates. See `docs/phase2b-results.md`. The
> Phase 2A numbers below used a symbol-keyed panel; Phase 2B uses the corrected
> ISIN panel and is the final word on this strategy family.

## What was tested

Frozen draft: `docs/phase2-hypothesis.md`.

- Universe: NSE EQ only; raw price >= Rs 20; 20D average turnover >= Rs 1 crore; ETF/REIT/InvIT excluded.
- Signal: month-end close; 63-session and 126-session total returns, each ranked cross-sectionally and measured as excess versus Nifty 50; composite = average of the two percentile ranks.
- Portfolio: top 10 by composite RS, equal weight at 10% of current equity.
- Execution: open of the first trading session of the next month.
- Costs: full delivery STT, exchange, SEBI, stamp, GST, DP sell charge, and liquidity-tier slippage. The stress run doubles slippage.
- 5% of 20D turnover cap per position.
- Daily mark-to-market; cash ledger; no leverage.
- Period: first signal 2020-07-31, first execution 2020-08-03, last date 2026-11-19. 76 monthly rebalances.
- Phase 2B (2010–2026) is still required before any product claim.

## Results

| Run | Net CAGR | Max DD | 2025 | 2026 YTD | 2025–26 | Cost drag/yr | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primary | 38.28% | -32.50% | +29.02% | +11.81% | +44.37% | 3.42% | 1.18 |
| Primary, 2× slippage | 34.62% | -32.77% | +26.80% | +9.59% | +38.80% | 5.97% | 1.06 |
| Equal-weight eligible universe (gross) | 29.00% | -24.21% | — | — | — | — | 1.20 |
| Nifty 50 buy-and-hold | 14.48% | -17.23% | +10.05% | -2.42% | — | — | 0.84 |
| Random top-10 (seed 42) | 21.27% | -42.87% | -6.04% | -13.24% | -19.35% | 9.86% | 0.50 |

Primary run details:

- Final equity from Rs 10,00,000: Rs 76,89,927.
- Total return: +669.0%.
- Sharpe (daily, annualised): 1.50; Sortino: 2.40; annualised volatility: 23.8%.
- Max drawdown: -32.50%, peak 2022-04-11, trough 2022-06-23.
- Rebalances: 76; trades: 1,148.
- Annual turnover: 7.76×; annual cost drag: 3.42%.
- Average exposure: 99.9%; max holdings: 25 (stale/suspended names, not 10).
- Positive months: 47/76 (61.8%); best month +26.4%; worst month -14.5%.
- Monthly excess versus the equal-weight universe: +0.80%/month, t-stat 1.16, hit rate 49.3% over 75 months. This is not statistically convincing.

The equal-weight eligible universe is gross of costs; its Calmar is nevertheless slightly better than the primary strategy. The 2× cost run is worse on Calmar than the equal-weight universe. The strategy has a return edge but not a clear risk-adjusted edge.

## Gate check (draft Phase 2 gate)

| Condition | Result | Status |
|---|---|---|
| Net CAGR > 16% | 38.28% | PASS |
| Max DD < 28% | -32.50% | **FAIL** |
| 2025–26 OOS positive | +44.37% | PASS |
| Beat Nifty after costs | 38.28% vs 14.48% | PASS |
| Beat equal-weight universe after costs | 38.28% vs 29.00% gross | PASS on CAGR, but monthly alpha t=1.16 |
| 2× costs still positive | +34.62% | PASS |
| 2025 positive | +29.02% | PASS |
| 2026 positive | +11.81% YTD | PASS |
| Turnover measured | 7.76×/yr | PASS |
| PBO < 0.20 | not evaluated | NOT TESTED |
| DSR > 0.95 | 0.965 at 10 trials; 0.931 at 20; 0.866 at 50 | LIKELY FAIL |
| Product target: max DD < 20% | -32.50% | **FAIL** |
| Product target: net CAGR > Nifty + 5% | +23.80% over Nifty | PASS on CAGR |

**Overall: Phase 2A does not pass.** The drawdown failure is not marginal; it is 4.5 percentage points above the draft limit and 12.5 points above the product target. The risk-adjusted comparison is also weak.

## Execution audit

`jobs/audit_monthly_entries.py` checked all 760 selected stock/months against the raw execution-date row (latest run):

- 740 matched; 20 had no NSE EQ row on the execution date.
- Open-versus-previous-close gap: median +0.74%, p90 +4.17%, p99 +5.72%, max +10.0%.
- 1.76% of entries gapped more than 5%; none gapped more than 10%.
- 25 entries had open = high = low (possible locked/single-price session).
- No zero-volume rows were found in the matched set.

Gaps are not the main problem. The main problems are drawdown, cost drag, and stale holdings.

## Data and model caveats

- Only 2020–2026; the 2010–2019 history was not in this run. Phase 2B is mandatory.
- Stock IDs are exchange-symbol based in this run. Ticker changes and long suspensions can leave a position on an old ID. Max holdings reached 25 because some names could not be sold on a rebalance date; this dilutes new positions.
- NSE master is current, not point-in-time. Delisted/ticker-changed coverage is incomplete.
- No dividends; price-return only.
- No circuit-limit/impact model beyond the 5% ADV cap and slippage tiers.
- No point-in-time Nifty 100/200 membership. The tested universe is the broad liquid NSE EQ set, not the large-cap index set Antigravity originally suggested.
- PBO is not computed because only one configuration has been run. A proper PBO needs a pre-declared configuration grid.
- DSR sensitivity (monthly Sharpe 0.385, T=76, skew 0.30, kurtosis 3.34): 0.965 at 10 trials, 0.931 at 20 trials, 0.866 at 50 trials. Phase 1 plus Phase 2 has already consumed more than 20 trial-equivalents, so DSR should be treated as below the 0.95 gate, not as a pass.
- Legal/SEBI review and exchange-data licensing are not started.

## Decision

Do **not** tune top-N, lookback, rebalance timing, or costs on this result. That would turn Phase 2A into an in-sample fit.

Proceed to Phase 2B:

1. Build NSE 2010–2026 adjusted panel with ISIN-based continuous IDs.
2. Extend corporate actions to 2010–2019 (done: `data/corporate_actions/actions.csv` now covers 2010–2026).
3. Extend Nifty 50 history to 2010–2026 (done: `data/index/nifty50.csv`).
4. Run the same frozen rules on 2010–2026.
5. If Phase 2B still fails max DD / risk-adjusted tests, stop this family and move to liquid large-cap mean reversion, as pre-committed.

## Files

- Engine: `jobs/backtest_monthly_momentum.py`
- Entry audit: `jobs/audit_monthly_entries.py`
- Primary output: `data/backtest_monthly/`
- 2× stress: `data/backtest_monthly_stress2x/`
- Random baseline: `data/backtest_monthly_random42/`
- Primary log: `data/backtest_monthly.log`
