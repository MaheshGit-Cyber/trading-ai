# Phase 1D — H4 pre-registered hypothesis (frozen before the test)

**Date:** 2026-11-21
**Status:** frozen. No parameter changes after the first full run.
**Approved by:** Antigravity independent review (`docs/antigravity-review.md`)
**Previous:** H1 baseline, H2 Nifty filter, H3 pullback limit — all failed.

## Why H4 exists

H3 failed for three structural reasons:

1. Tight stop (0.75 ATR) doubled notional turnover and raised cost to 0.196R.
2. No portfolio cash constraint: max 84 concurrent positions, impossible with
   ₹10 lakh.
3. No stock-selection edge: 6,966 trades, about 1,000 per year.

H4 changes the selection, the stop, the holding period, and the execution
model. It does not tune H3.

## Universe

- NSE `EQ` only. ETFs, REITs, InvITs excluded.
- Price ≥ ₹20.
- 20-session average turnover ≥ ₹1 crore.
- Nifty 50 close > 200DMA on the signal date.

## Relative strength (RS)

- `ret63 = close / close 63 sessions ago − 1`.
- `ret126 = close / close 126 sessions ago − 1`.
- `ret63_excess = ret63_stock − ret63_nifty`.
- `ret126_excess = ret126_stock − ret126_nifty`.
- `rs_pct = average(percentile_rank(ret63_excess), percentile_rank(ret126_excess))`
  across the eligible NSE universe on that date.
- **Trade only if `rs_pct ≥ 0.90` (top 10%).**
- Ranks use only data available on the signal date. No future data.

## Trend

- Close > 200DMA.
- 50DMA > 200DMA.
- ADX(14) ≥ 20.
- 20-session 50DMA slope > 0.

## Pullback

- 5–15 sessions from a 20-bar swing high.
- Pullback low in the last 3 bars, including the signal bar.
- Pullback low ≥ 50DMA.
- No pullback close < 50DMA.
- RSI(14) at the low 40–60.
- Average pullback volume < 20-session average volume.
- Late-stage filter: signal close ≤ 50DMA × 1.15.

## Entry

- Limit buy at `pullback_low + 0.25 × ATR(14)`.
- Valid for 3 sessions. A gap below the limit fills at the open.
- No fill = no trade = 0R.
- **Same-day target is denied.** On the fill bar, only the stop is evaluated.

## Stop, target, exit

- Stop: `pullback_low − 1.0 × ATR(14)`.
- Minimum stop distance: `max(1.0 × ATR, 1% of entry)`.
- Target: `min(prior swing high, entry + 3.0R)`. Require at least 1.5R.
- Time exit: 20 sessions.
- Same-day stop and target: stop first. Gaps fill at the open.
- No trailing stop in the primary test.

## Portfolio and position sizing

- Capital: ₹10,00,000.
- Risk per trade: 1% of capital (₹10,000).
- Max 5 concurrent positions in the primary test. Max 10 is a sensitivity run.
- Max position value: 20% of capital (₹2,00,000).
- Max 5% of 20-session average daily turnover.
- Quantity = the smallest of the risk-based size, the 20% notional cap, and the
  5% ADV cap.
- Cash ledger: reserve `qty × entry` on entry, release on exit. No leverage.
- If several signals fire on the same day, rank by `rs_pct` descending and take
  until slots or cash are exhausted. Skipped signals are not queued.
- No pyramiding. One position per stock at a time.
- Equity is marked daily at the close. Max drawdown is computed on equity, not
  on the sum of trade R.

## Costs

Same as the baseline: STT 0.1% each side, exchange, SEBI, stamp, GST, ₹13.5 DP
sell, and one-way slippage of 0.10% / 0.25% / 0.50% by liquidity. Stress test
doubles slippage.

## Gate

- Overall and test net expectancy > +0.10R after costs.
- Test trades ≥ 100.
- Profit factor > 1.2.
- Portfolio max drawdown < 20% of equity.
- 2× slippage still positive.
- Beats random entry and buy-and-hold baselines.
- For a pass: PBO < 0.20 and deflated Sharpe > 0.95.
- Test period 2025–2026 must be positive.

## Trials

H4 is **one trial**. Sensitivity runs (max 10 positions, 63-day RS only, 126-day
RS only) are diagnostics. They are reported but do not change the gate.

## Kill rule

If H4 fails, do not tune it. Move to a different strategy family.

## Freeze

The rules above are written before the first full run. If a bug is found, fix it,
rerun, and report both the buggy and fixed results. Do not change a parameter
because the first result is disappointing.
