# Phase 1C — pre-registered hypotheses (frozen before the test)

**Date:** 2026-11-21
**Status:** frozen. No parameter changes after the first full run.
**Baseline:** `trend_pullback`, 315 trades, net −0.194R, OOS gate failed.

## Why this phase exists

The first test failed for a specific reason: the entry was late. Median MAE was
−1.05R, 39.7% of trades never reached +0.5R, and 21 trades were stopped on the
entry day. The fix must change the entry, not tune the stop or the target on the
same data.

Two hypotheses are tested. They are separate. H2 is the user's regime idea. H3
is the new entry idea. Both are counted as trials.

## H2 — Nifty 200DMA regime overlay (minimal change)

**Statement:** Adding a Nifty 50 200DMA filter to the existing rules reduces
drawdown and may improve expectancy, but is not expected to create an edge if
the entry has none.

**Exact change:** no new entry when the Nifty 50 close is below its 200-session
moving average on the signal date. Every other rule is identical to the
baseline.

**Expected result:** lower drawdown, expectancy may stay negative. In bull
years the baseline gross edge was only about +0.01R, so a filter cannot rescue
it.

**Trials:** 1.

**Gate:** same as baseline — test net > 0, 2× slippage > 0, profit factor > 1.2,
test trades ≥ 100.

## H3 — pullback limit entry (new hypothesis)

**Statement:** Buying the pullback at support with a limit order, instead of
chasing the breakout at the next open, improves the entry price and turns gross
expectancy positive.

**Rules:**

- Universe and data filters: same as baseline (NSE `EQ`, price ≥ ₹20, 20D
  turnover ≥ ₹1 crore, ETFs/REITs/InvITs excluded).
- Regime: Nifty 50 close > 200DMA on the signal date.
- Trend: close > 200DMA, 50DMA > 200DMA, ADX(14) ≥ 20, 20-session 50DMA slope
  > 0.
- Pullback: 3–8 sessions from a 15-bar swing high; pullback low in the last 3
  bars including the signal bar; low ≥ 20DMA; no pullback close < 50DMA;
  RSI(14) at the low 40–65; average pullback volume < 20D average.
- Late-stage filter: signal close ≤ 50DMA × 1.15.
- Entry: limit buy at `pullback_low + 0.25 × ATR(14)`, valid for 2 sessions. A
  gap below the limit fills at the open. No fill = no trade = 0R.
- Stop: `pullback_low − 0.5 × ATR(14)`. Minimum stop distance remains
  `max(0.5 × ATR, 1% of entry)`.
- Target: `min(prior swing high, entry + 1.5R)`. Require at least 1.0R.
- Time exit: 10 sessions.
- Same-day stop and target: stop first. Gaps fill at the open.
- Size: 1% risk, max 25% of capital, max 5% of 20D average turnover.
- Costs: same as baseline; stress test doubles slippage.

**Trials:** 1.

**Diagnostic only:** H3 without the regime filter, to attribute the result. It is
not a new hypothesis and does not change the gate.

**Gate:**

- Overall and test net expectancy > +0.10R after costs.
- Test trades ≥ 100.
- Profit factor > 1.2.
- Max drawdown < 20R.
- 2× slippage still positive.
- Beats random entry and buy-and-hold baselines.

**Kill rule:** if H3 fails, do not tune it. Move to a second strategy family.

## Reporting

- Trade-level CSV and summary JSON for every run.
- Walk-forward: dev 2020–2022, validation 2023–2024, test 2025–2026.
- Bootstrap 10,000 samples.
- Later robustness: CPCV, PBO, deflated Sharpe, Monte Carlo, parameter
  perturbation, doubled costs.
- Negative results are reported in full.

## Freeze

The rules above are written before the first full run. If a bug is found, fix
it, rerun, and report both the buggy and fixed results. Do not change a
parameter because the first result is disappointing.
