# Task for Antigravity CLI

You are an **independent reviewer** for a trading-strategy backtest. Work
**read-only**. Do not modify code, data, or rules. Write your report to
`docs/antigravity-review.md`.

**Workspace:** `/storage/emulated/0/Mahvex/trading-ai`

## Read these files first

- `jobs/backtest_trend_pullback.py`
- `engine/features.py`
- `docs/phase1c-hypothesis.md`
- `docs/phase1c-results.md`
- `data/backtest_h3_v2/summary_trend_pullback.json`
- `data/backtest_h3_v2/trades_trend_pullback.csv`
- `data/curated/MANIFEST.json`
- `jobs/build_adjusted_panel.py` (corporate-action adjustment logic)
- `memory/knowledge/setups.json`
- `memory/knowledge/costs.json`

## Context

- NSE `EQ` daily panel, 2020-01-01 to 2026-11-19, adjusted for corporate
  actions. BSE excluded from the first proof.
- Baseline `trend_pullback`: 315 trades, net −0.194R, failed.
- H2 (Nifty 200DMA filter): 282 trades, net −0.205R, test −0.298R, failed.
- H3 (pullback limit entry): 6,966 trades, gross +0.045R, net −0.151R,
  test net −0.221R, failed. Average cost 0.196R per trade.
- The question is not "how to make it profitable". The question is "is the
  result trustworthy, and where are the bugs or biases?"

## Checks

1. **Look-ahead bias.** Does `signal_from_bar` use only bars through the signal
   close? Does the limit-entry path use future bars correctly? Is the entry
   bar's high/low ever used to decide the signal?
2. **Survivorship bias.** The NSE ISIN map is a current master, not
   point-in-time. How large is the bias? Are delisted stocks missing?
3. **Corporate-action adjustment.** Could the adjustment factor create
   look-ahead or price discontinuities? Are dividends excluded, and does that
   matter for a 10-day swing?
4. **Cost model.** Are STT, exchange, SEBI, stamp, GST, DP, and slippage correct
   for delivery trades? Is 0.196R average cost plausible for H3?
5. **Stop-first and gaps.** Is the same-day stop-first assumption conservative?
   Are gap fills at the open correct? Any same-day entry/exit bug?
6. **Multiple testing.** H2 and H3 are two trials. Is the gate strong enough?
   What PBO and deflated Sharpe would you require before trusting a pass?
7. **Trade count.** H3 produced 6,966 trades (~1,000/year). Is the pullback
   signal too loose, or is there a bug? Check the pullback condition and the
   limit-fill logic. Count how many signals one stock can generate in a month.
8. **Drawdown metric.** The reported max drawdown is trade-sequence drawdown,
   not portfolio equity drawdown. What is the correct way to measure portfolio
   drawdown with max 5 concurrent positions?
9. **Gross edge.** Is +0.045R gross economically plausible, or an artifact of
   the entry/exit mechanics? Compute the standard error.
10. **Single most likely reason the strategy fails.**

## Output format

Write `docs/antigravity-review.md` with:

1. A table: `ID | Severity (blocker/high/medium/low) | Finding | Evidence
   (file:line or command output) | Recommendation`.
2. "What I could not verify" — be explicit.
3. "Top 3 fixes before the next test."
4. "Is the H3 result trustworthy? Yes/No/Partially — why."

## Hard rules

- Do not propose parameter values fitted to the test period.
- Do not claim the strategy is profitable.
- Separate "bug" from "idea".
- Point to exact lines and files.
- If you cannot verify something, say so.
