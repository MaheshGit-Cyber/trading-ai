# Phase 2 — Monthly Cross-Sectional Momentum Rotation

**Status:** **CLOSED — FAILED Phase 2B.** See `docs/phase2b-results.md`.
**Date:** 2026-11-21
**Source:** Antigravity proposal, `bridge/to_opencode.md`, 2026-11-21T01:53+05:30
**Predecessor:** Phase 1 closed with no passing strategy (`docs/phase1-final-conclusions.md`)

> This document is the pre-registration draft. It becomes frozen only after
> Mahesh/Antigravity sign off. No parameter may change after the first full run.

## Why this family

Daily cash-delivery swing trading failed because the gross edge was too small
relative to Indian friction. Monthly rotation changes the economics:

- Rebalance once a month instead of daily.
- Hold 10 liquid stocks instead of dozens of concurrent swing trades.
- Let the position size be 10% of capital per name, not a risk-based daily stop.
- Cut turnover, STT, stamp duty, GST, DP charges and slippage.

The family is still momentum, so it is exposed to momentum crashes, crowding
and regime change. The 2025–2026 test must prove it survives those conditions.

## Scope: two stages

### Phase 2A — preliminary, current panel

Use the existing adjusted panel, 2020-01-01 to 2026-11-19.

- Earliest monthly signal: around January 2021 (needs 126 sessions).
- Development: 2021–2024.
- Test: 2025–2026.
- This is a **preliminary** result. It has only ~5 years, mostly a bull market,
  and is not enough to claim a durable monthly momentum edge.

### Phase 2B — full-history proof, required before product

Extend NSE data to 2010-01-01 (or the earliest clean date available) and rerun.

- Development: 2010–2024.
- Test: 2025–2026.
- Includes 2011, 2013, 2015, 2018, 2020, 2022 and 2025–2026 regimes.
- Requires adjusted prices and corporate actions for the full history.
- Point-in-time universe / delisted stocks preferred. If not available, the
  result must be labelled “current-master survivorship” and cannot be used as
  final product proof.

Phase 2A can start now. Phase 2B is mandatory before any subscription launch.

## Universe

- NSE, series `EQ`.
- Raw close >= ₹20.
- 20-session average turnover >= ₹1 crore.
- ETFs, BEES, exchange-traded funds, mutual funds, REITs and InvITs excluded.
- One share class per company where the data allows.
- No BSE-only stocks in the first proof.

The Antigravity proposal mentions Nifty 100/200 but specifies a broad NSE EQ
universe. This draft uses the broad liquid universe as primary because it is
testable on the current panel. A Nifty 100/200 point-in-time sensitivity is a
separate diagnostic once point-in-time membership is available.

## Factor

At each month-end close `D`:

```
ret63  = adj_close(D) / adj_close(63 sessions earlier) - 1
ret126 = adj_close(D) / adj_close(126 sessions earlier) - 1
excess63  = ret63  - Nifty50 ret63
excess126 = ret126 - Nifty50 ret126
rs_pct = average(percentile_rank(excess63),
                 percentile_rank(excess126))
```

- Ranks are cross-sectional across the eligible universe on `D`.
- Only data through `D` is used.
- Rank by `rs_pct` descending.
- Select the top 10.

No future data, no current-master membership used as a signal.

## Rebalance and execution

- **Signal date:** last trading session of the calendar month.
- **Execution:** open of the first trading session of the next calendar month.
- If the first session is a holiday, use the next trading session.
- If a stock is already held and remains in the top 10, rebalance it to target
  weight; do not sell and rebuy for no reason.
- If a stock leaves the top 10, sell at the next open.
- If a stock cannot trade (halt, upper circuit, no open), keep the cash and do
  not substitute a name intraday. Re-evaluate next month.
- No leverage, no shorting, no intraday execution.

This definition removes the ambiguity in “rebalance on the first session” plus
“next open after rebalance date.” The signal is formed on the prior month-end;
the trade happens on the next month’s first open.

## Portfolio

- Starting capital: ₹10,00,000.
- Target 10 positions, equal weight: 10% of current portfolio equity each.
- Maximum 10 positions.
- Cash buffer for costs; no negative cash.
- Max 5% of 20-session average daily turnover per position.
- If fewer than 10 eligible stocks, hold cash for the difference.
- No pyramiding, no averaging down.
- One position per stock.

Equal weight is intentional: it avoids the H4 mistake of ranking a pullback
entry by the most extended RS name. The factor already selects the names; the
portfolio does not add a second momentum bet.

## Costs

Full Budget-2026 equity-delivery model:

- STT 0.1% buy, 0.1% sell.
- Exchange, SEBI, stamp duty, GST.
- DP charge ₹13.5 per sell.
- One-way slippage by 20D turnover: 0.10% / 0.25% / 0.50%.
- 2× slippage stress test.
- No brokerage assumption beyond the above; if the user’s broker charges,
  deduct it separately.

Costs are charged on every rebalance trade, including partial weight changes.
The model must report annual turnover and total cost drag, not assume “95%
lower” without measurement.

## Benchmark and baselines

- Nifty 50 buy-and-hold (price return).
- Equal-weight eligible universe, monthly rebalanced.
- Random top-10 rotation from the eligible universe (same dates, same costs).
- Nifty 200 Momentum 30 index, if a clean historical series is available;
  otherwise omit and say so.
- The strategy must beat the Nifty and the equal-weight universe after costs,
  not just have a positive absolute return.

## Gate

Antigravity’s proposed gate:

- CAGR > 16.0%.
- Max drawdown < 28%.
- Out-of-sample 2025–2026 positive net return.

Mandatory additions before a pass can be accepted:

- Net of all costs, including 2× slippage.
- Beats Nifty buy-and-hold and equal-weight universe after costs.
- No look-ahead: signal uses month-end data, execution at next open.
- Phase 2B full-history result, not only Phase 2A.
- Turnover and cost drag reported.
- Capacity check at ₹10 lakh and ₹1 crore.
- PBO < 0.20 and deflated Sharpe > 0.95 for a pass.
- 2025 and 2026 reported separately; one good year is not enough.

**Product-readiness target (stricter than the backtest gate):** max drawdown
< 20% and net CAGR > Nifty + 5%. A 28% drawdown is acceptable for a research
gate, not for a subscription product without a clear risk warning.

## Trials and kill rule

- Primary: top 10, equal weight, 63+126 composite RS, monthly.
- Diagnostics only: top 20, 63-only, 126-only, Nifty 100/200 universe,
  volatility scaling, trend filter. Diagnostics do not change the gate.
- If the primary fails Phase 2B, do not tune it. Move to the next family
  (liquid large-cap mean reversion) or reassess the product.
- No parameter search on the test period.

## Data prerequisites

### Phase 2A (available now)

- `data/curated/panel.csv` (2020–2026, adjusted NSE+BSE; NSE used).
- `data/index/nifty50.csv` (2018–2026).
- `data/curated/rs_rank.csv` or a monthly rebuild from the same logic.

### Phase 2B (required before product)

- NSE bhavcopy 2010-01-01 to 2026-11-19, EQ only.
- Corporate actions 2010–2026 for adjustment factors.
- Nifty 50 daily closes 2010–2026.
- Delisted-stock coverage and point-in-time universe, or an explicit
  survivorship label.
- If 2010 data cannot be cleaned, use the earliest clean year and state it.
  Do not call a 2020–2026 result “30-year evidence.”

## Implementation

New job: `jobs/backtest_monthly_momentum.py`.

Inputs:

- panel
- Nifty closes
- monthly rebalance calendar
- optional RS file or in-job monthly rank builder

Outputs:

- `summary_monthly_momentum.json`
- `equity_curve.csv`
- `holdings.csv`
- `rebalance_trades.csv`
- `monthly_returns.csv`
- `attribution.csv` (optional)

Engine requirements:

- Deterministic month-end signal and next-open execution.
- Cash ledger and equal-weight rebalance to target.
- Full cost model and 2× stress.
- Daily mark-to-market and max drawdown.
- Benchmark and random/equal-weight baselines.
- No look-ahead; unit tests for rebalance dates, weights, costs and delisted
  names.

## Timeline (realistic)

| Step | Time |
|---|---|
| Freeze this hypothesis after approval | 1 day |
| Data audit + monthly calendar + universe checks | 1–2 days |
| Build monthly engine and portfolio ledger | 2–3 days |
| Validation (look-ahead, costs, weights) | 1–2 days |
| Phase 2A run + review | 1–2 days |
| 2010–2026 data extension + adjustment audit | 1–2 weeks |
| Phase 2B run + review | 2–3 days |
| Paper-trading plan (only if pass) | 2–3 months |

First Phase 2A result: about **1 week** after approval.
Full Phase 2B proof: about **2–4 weeks**, depending on historical data quality.

## Known failure modes

1. Momentum crash in a choppy market (the H4 killer).
2. Crowding in the top-RS names.
3. Survivorship / current-master bias.
4. Bad corporate-action adjustment in the longer history.
5. Higher turnover than assumed; cost drag eats the edge.
6. Sector concentration in the top 10.
7. Gap risk at the next open.
8. Delisting / halt / upper circuit.
9. Data snooping across the many monthly variants.
10. Benchmark mismatch (price return vs total return).
11. Taxes at the user level (STCG/LTCG) not captured in the model.
12. SEBI research-analyst / investment-adviser rules for a paid signal product.

## Freeze block

- Primary factor: 63+126 composite RS, top 10, equal weight, monthly.
- Universe: NSE EQ, raw price >= ₹20, 20D turnover >= ₹1 crore, exclusions.
- Execution: month-end signal, next month first open.
- Costs: full delivery model, 2× stress.
- Gate: as above, including Phase 2B.
- No tuning after the first full run.

**Awaiting approval to freeze.**
