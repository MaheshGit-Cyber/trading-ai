# External review request — Phase 1 trading strategy

You are an independent reviewer. **Do not optimize for a profitable result.**
Your job is to find bugs, biases, and logical errors. A negative result is a
valid result.

## Context

- Data: NSE `EQ` daily panel, 2020-01-01 to 2026-11-19, adjusted for corporate
  actions. BSE is excluded from the first proof because 2020-2023 BSE identity
  is unresolved.
- First strategy `trend_pullback` failed out of sample: 315 trades, net −0.194R.
- H2 added a Nifty 50 200DMA regime filter: 282 trades, net −0.205R, test
  −0.298R. Failed.
- H3 changed to a pullback limit entry: 6,966 trades, gross +0.045R, net
  −0.151R, test net −0.221R. Failed the gate.
- H3 average cost is 0.196R per trade; baseline was 0.113R.
- Key files:
  - `jobs/backtest_trend_pullback.py`
  - `engine/features.py`
  - `docs/phase1c-hypothesis.md` (pre-registered rules)
  - `docs/phase1c-results.md` (results)
  - `data/backtest_h3/summary_trend_pullback.json`
  - `data/backtest_h3/trades_trend_pullback.csv`

## Questions

1. **Look-ahead bias:** does `signal_from_bar` use only bars through the signal
   close? Does the limit-entry path use future bars correctly? Is there any
   point where the code sees the entry bar's high/low before deciding to enter?
2. **Survivorship bias:** the NSE ISIN map is a current master, not point-in-time.
   How large is the bias? Does the universe include stocks that later delisted?
3. **Corporate-action adjustment:** could the adjustment factor create
   look-ahead or price discontinuities? Are dividends excluded, and does that
   matter for a 10-day swing?
4. **Cost model:** are STT, exchange, SEBI, stamp, GST, DP, and slippage correct
   for delivery trades? Is 0.196R average cost plausible for H3?
5. **Stop-first assumption:** is it conservative? Any same-day entry/exit bug?
6. **Multiple testing:** H2 and H3 are two trials. Is the gate strong enough?
   What PBO and deflated Sharpe would you require before trusting a pass?
7. **Trade count:** H3 produced 6,966 trades (~1,000/year). Is the pullback
   signal too loose, or is there a bug? Check the pullback condition and the
   limit-fill logic.
8. **Gross edge:** is +0.045R gross economically plausible, or an artifact of
   the entry/exit mechanics?
9. **What would you fix before trusting any result?**
10. **Single most likely reason the strategy fails?**

## Rules

- Do not propose parameter values fitted to the test period.
- Do not claim a strategy is profitable.
- Point to exact lines and files.
- Separate "bug" from "idea".
- If you cannot verify something, say so.
