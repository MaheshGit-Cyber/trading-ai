# Verification of the Antigravity review

**Date:** 2026-11-21
**Review file:** `docs/external-review-response.md`
**Verified by:** OpenCode, against code and trade data

## Verdict

The review is useful and directionally correct. Two points need correction:

1. **Survivorship bias is overstated.** The panel is not built only from current
   survivors.
2. **The H3 gross edge is not just "economically meaningless" — it is an
   artifact.** Once same-day target fills on limit entries are removed, gross
   expectancy turns negative.

The review's biggest contribution is the same-day target caveat. It is real and
material.

## Claim-by-claim

### 1. Look-ahead bias — correct

- `signal_from_bar` uses `state.bars` through the signal close. No future bar.
- The limit fill logic is correct: gap below the limit fills at the open,
  otherwise a touch fills at the limit.
- **Same-day target caveat is real.** `check_trade_bar` (lines 445–454) awards
  `target_same_day` when `bar.high >= target`, even if the limit fill happened
  later in the day. Daily OHLC cannot order the high and the fill.
- **Materiality:** 740 of 6,966 trades (10.6%) are `target_same_day`, average
  net +1.280R.

A static exclusion (treating those trades as 0R or removing them) gives a
worst-case gross of −0.127R. That is an upper bound, not the true
counterfactual, because many of those trades would have hit the target on a
later bar.

The dynamic rerun with `--same-day-target deny` is the correct test:

| View | Gross avg | Net avg |
|---|---:|---:|
| H3 v2 (same-day target allowed) | +0.045R | −0.151R |
| H3 v3 (same-day target denied) | **+0.033R** | **−0.163R** |
| H3 v3 test period (849 trades) | **+0.000R** | **−0.209R** |

So the optimistic fill inflates gross by about **0.012R**, not the whole edge.
The gross edge is real but too small; net is negative and the test period has no
gross edge. The conclusion (fail) is unchanged.

Fix implemented: `--same-day-target deny`. H3 v3 is complete.

### 2. Survivorship bias — overstated

The reviewer says the universe comes from the current master and delisted stocks
are omitted. The data does not support that:

- Panel has **3,473 unique NSE EQ stocks**.
- **469** have a last date before 2026: 63 in 2020, 61 in 2021, 83 in 2022,
  111 in 2023, 74 in 2024, 77 in 2025.
- Of the **1,519 stocks traded by H3, 194 (12.8%)** stop before 2026-11-19.

So the panel includes stocks that later stopped trading, while they were still
trading. Residual bias remains because the ISIN map is a current master and some
names may be missing entirely, but "moderate to high" is not supported by the
data. Direction is right; magnitude is unproven.

### 3. Corporate-action adjustment — correct

Backward adjustment is standard. Dividends are excluded, which is immaterial for
a 10-session swing. No change.

### 4. Cost model — correct

- Average cost is 0.196R, or **0.537% of notional**.
- Average notional is **₹246,356**, about 24.6% of ₹10 lakh. The 25% notional cap
  binds often, so actual risk is below 1% of capital. That raises cost_R.
- The H3 stop (0.75 ATR) roughly halves risk per share versus the baseline
  (1.5 ATR), so notional roughly doubles and cost_R roughly doubles. The math is
  right.

### 5. Stop-first assumption — correct

`check_trade_bar` assumes stop first when both levels are touched. This is the
conservative daily-bar assumption. No change.

### 6. Multiple testing — correct for rejection

Both H2 and H3 failed. DSR and PBO are not needed to reject the null. For any
future pass, they are required. No change.

### 7. Trade-count explosion — correct

The pullback mode skips the breakout close, the 1.3× volume trigger, and the
close-above-20DMA filter. The result is a firehose:

- 6,966 trades, 998 entry days, max 43 entries/day, mean 6.98.
- 486 days with more than 5 entries, 212 with more than 10, 40 with more than 20.
- 1,519 unique stocks, max 18 trades per stock.
- 26.7% of consecutive same-stock trades are within 30 days.

### 8. Gross edge — understated

The reviewer says +0.045R is economically meaningless. The data says it is an
artifact: excluding same-day target fills, gross is **−0.127R**. The true gross
edge is negative. This is the most important correction to the review.

### 9. Fixes — correct

- **Portfolio simulation is missing.** Max concurrent positions: **84**, mean
  **17.4**. Days with more than 5 concurrent: 1,069; more than 10: 803; more than
  20: 446; more than 50: 51. With ₹10 lakh and a 25% notional cap, 84 positions
  would need about ₹2.07 crore. The current backtest is not capital-constrained.
- **Same-day target on limit entries must be denied.** Implemented as
  `--same-day-target deny`; H3 v3 is running.

### 10. Single most likely reason — directionally correct

High friction plus short-horizon mean reversion. The same-day target artifact
makes the true gross edge negative, so the structural mismatch is even stronger
than the review states.

## What to fix before the next strategy

1. Use `--same-day-target deny` for every limit-entry test.
2. Add a portfolio simulator: max 5–10 concurrent positions, cash cap, and
   rank-based allocation.
3. Keep the pre-registered gate; add DSR and PBO for any future pass.
4. Do not tune H3. Move to a low-turnover hypothesis.

## Bottom line

The review found a real bias, but its impact is smaller than the static
exclusion suggested. The dynamic rerun gives gross +0.033R and test gross
+0.000R. The gross edge is real but too small; net is negative. The survivorship
claim is overstated, but the direction is right. The next strategy must be
portfolio-constrained and must deny same-day target fills on limit entries.
