# Phase 1 — final conclusions

**Date:** 2026-11-21
**Status:** **CLOSED. No strategy passed. Waiting for Mahesh's direction.**
**Independent review:** `docs/antigravity-h4-review.md`

## What Phase 1 tested

| Hypothesis | Trades | Gross R | Net R | Test net R | Gate |
|---|---:|---:|---:|---:|---|
| H1 baseline breakout | 315 | −0.082 | −0.194 | — | FAIL |
| H2 Nifty 200DMA filter | 282 | −0.092 | −0.205 | −0.298 | FAIL |
| H3 pullback limit | 6,966 | +0.045 | −0.151 | −0.221 | FAIL |
| H3 v3 same-day target denied | 6,850 | +0.033 | −0.163 | −0.209 | FAIL |
| H4 RS leader pullback | 1,119 | +0.161 | +0.069 | −0.152 | FAIL |

**No hypothesis cleared the pre-registered out-of-sample gate.**

## H4 in one paragraph

H4 fixed H3's structural problems: the stop widened to 1.0 ATR, cost fell from
0.196R to 0.091R, holding extended to 20 sessions, and the portfolio was capped
at 5 or 10 positions. The gross edge was +0.161R overall, but net was only
+0.069R and the 2025–2026 test period was −0.152R with profit factor 0.788. The
5-position portfolio lost 5.5% with a 35.2% drawdown; the 10-position portfolio
made 3.16% CAGR with a 27.7% drawdown. Nifty buy-and-hold made 11.34% CAGR over
the same period.

## Why the strategies failed

1. **Indian cash-delivery friction is heavy.** STT, stamp duty, GST, DP charges
   and slippage consume a large part of a small daily edge. H4's cost was still
   0.091R per trade.
2. **Daily swing signals are noisy.** The win rate needed to overcome the
   payoff was not reached out of sample.
3. **High-RS leaders get crowded.** Ranking by the highest relative strength
   selected extended names that fell hardest when the market pulled back. The
   5-position taken subset was −0.003R while the skipped signals were +0.144R
   counterfactually.
4. **The edge was regime-dependent.** 2020–2024 worked; 2025–2026 did not. A
   strategy that only works in the development window is not sellable.
5. **Portfolio feasibility matters.** H3 had up to 84 concurrent positions with
   ₹10 lakh; H4 fixed that, but the remaining edge was not enough.

## What is blocked

- Paper trading: blocked.
- Live trading: blocked.
- Sellable product: blocked.
- Commercial data purchase: not justified yet.
- SEBI/legal review: not started; not useful until a strategy passes.

## Independent reviewer's recommendation

Antigravity concurred with the failure and recommended:

1. **Primary next family:** monthly cross-sectional momentum rotation on
   Nifty 100 / Nifty 200. Monthly rebalancing cuts turnover and friction by
   roughly 95% and avoids daily noise.
2. **Alternative:** liquid large-cap mean reversion on Nifty 50 names, with a
   quick 2–3 day bounce.
3. **Data:** stay on free NSE EOD bhavcopy. Do not spend on commercial data or
   SEBI advisory filings until a family passes out-of-sample, stress, and paper
   trading.
4. **PBO/DSR:** unnecessary on a failed hypothesis; the null already stands.

## Decision required from Mahesh

Phase 1 is closed. Before any new run:

- Choose the next family: **monthly momentum rotation** or **liquid large-cap
  mean reversion** (or something else).
- Freeze the new hypothesis in writing before testing.
- Keep the same rule: one family, one pre-registered test, no tuning after the
  result.
- No paper trading, live trading, product build, or data purchase until a
  family passes.

## Honest position

A 100% profit guarantee is impossible. What can be promised is 100% process
discipline: pre-registered tests, real data, costs, out-of-sample checks, and a
clear stop when the evidence says no. Phase 1 did its job: it stopped four weak
ideas before they reached the product or anyone's money.
