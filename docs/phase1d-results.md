# Phase 1D — H4 results

**Date:** 2026-11-21
**Hypothesis:** relative-strength leader pullback (H4)
**Status:** **FAIL — do not tune. Move to a different strategy family.**
**Pre-registration:** `docs/phase1d-hypothesis.md` (frozen before the run)
**Implementation audit:** `docs/phase1d-h4-implementation.md`
**RS audit:** `docs/phase1d-rs-audit.md`

## Run

```bash
python3 jobs/backtest_trend_pullback.py \
  --regime nifty200 \
  --signal-mode rs_pullback \
  --entry-mode limit \
  --target-mode swing_3.0r \
  --stop-atr 1.0 \
  --horizon 20 \
  --limit-valid-bars 3 \
  --same-day-target deny \
  --max-notional-pct 0.20 \
  --rs-file data/curated/rs_rank.csv \
  --rs-min 0.90 \
  --outdir data/backtest_h4 \
  --bootstrap 10000
```

- Closed trades: **1,119** (1 still open at the end).
- Data-risk exclusions: 0.
- Average cost: **0.091R** per trade (H3 was 0.196R).

## Headline

| Metric | Overall | Dev 2020–22 | Validation 2023–24 | Test 2025–26 |
|---|---:|---:|---:|---:|
| Trades | 1,119 | 383 | 464 | 272 |
| Gross R | +0.1606 | +0.2056 | +0.2495 | −0.0543 |
| **Net R** | **+0.0694** | **+0.1128** | **+0.1635** | **−0.1523** |
| 2× slippage R | +0.0177 | +0.0564 | +0.1160 | −0.2046 |
| Profit factor | 1.105 | 1.171 | 1.261 | 0.788 |
| Win rate (1R) | 31.6% | 32.4% | 34.7% | 25.4% |
| Avg win / avg loss | 1.89 / −1.07 | 1.96 / −1.09 | 1.92 / −1.06 | 1.71 / −1.07 |
| Max drawdown in R | −63.9 | −35.1 | −36.2 | −52.8 |

Bootstrap (10,000 resamples of trade R): mean **+0.0699**, 5th percentile
**−0.0065**, 95th percentile **+0.1463**, probability mean > 0 = **93.6%**.
The mean is probably positive, but it is below the +0.10R gate and the test
period is negative.

## By year (net R)

| Year | Trades | Net R | Profit factor |
|---|---:|---:|---:|
| 2020 | 25 | +0.231 | 1.38 |
| 2021 | 153 | +0.193 | 1.31 |
| 2022 | 205 | +0.038 | 1.06 |
| 2023 | 179 | +0.334 | 1.60 |
| 2024 | 285 | +0.057 | 1.08 |
| 2025 | 224 | −0.101 | 0.85 |
| 2026 (to 19 Nov) | 48 | −0.390 | 0.53 |

The edge is concentrated in 2020–2024. It turns negative in 2025 and worse in
2026. That is the out-of-sample period, so it cannot be ignored as noise.

## Portfolio diagnostics

`jobs/portfolio_sim.py`, ₹10,00,000, max 20% of capital per position, same-day
entries ranked by RS, daily mark-to-market.

| Portfolio | Final equity | Total return | CAGR | Max drawdown | Avg exposure | Taken trades | Taken net R |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 positions | ₹9,45,099 | −5.49% | −0.82% | **−35.22%** | 40.5% | 569 | −0.003 |
| 10 positions | ₹12,38,975 | +23.90% | +3.16% | **−27.68%** | 58.0% | 813 | +0.039 |
| 5 positions, 2× costs | ₹6,00,460 | −39.95% | −7.14% | −51.48% | 39.3% | 558 | −0.068 |
| 10 positions, 2× costs | ₹7,00,990 | −29.90% | −5.03% | −44.45% | 46.5% | 666 | −0.039 |

Nifty 50 buy-and-hold over the same period: **+109.4% total, +11.34% CAGR**
(price return, no dividends).

Key observations:

- H4 fixed H3's 84-concurrent-position problem: max concurrent is 5 or 10.
- The 5-position portfolio takes only 569 of 1,119 signals. The taken subset has
  **−0.003R**; the skipped subset was +0.144R counterfactually. The highest-RS
  names did not produce the best portfolio.
- The 10-position portfolio earns +3.16% CAGR but still has a 27.7% drawdown and
  loses money at 2× costs.
- Both portfolios lose to Nifty buy-and-hold by a wide margin.
- The cash ledger matters: with a 20% position cap, 10 full positions would be
  200% of capital. The 10-position run holds 10 names only by taking smaller
  positions; 244 signals are skipped for cash.

## Gate

| Gate | Requirement | Result | Verdict |
|---|---|---:|---|
| Overall net expectancy | > +0.10R | +0.069R | FAIL |
| Test net expectancy | > +0.10R | −0.152R | FAIL |
| Test trades | ≥ 100 | 272 | PASS |
| Profit factor | > 1.2 | 1.105 overall / 0.788 test | FAIL |
| Portfolio max drawdown | < 20% | −35.2% (5) / −27.7% (10) | FAIL |
| 2× slippage still positive | > 0 | +0.018 overall / −0.205 test | FAIL |
| Beats buy-and-hold | > Nifty | −0.82% / +3.16% vs +11.34% CAGR | FAIL |
| Beats random entry | > random | not run; gate already failed | NOT REACHED |
| PBO | < 0.20 | not computed; gate already failed | NOT REACHED |
| Deflated Sharpe | > 0.95 | not computed; gate already failed | NOT REACHED |
| Test 2025–26 positive | > 0 | −0.152R | FAIL |

**Verdict: FAIL.** Per the frozen kill rule, H4 is not tuned.

## Why it failed (structural, not a parameter tweak)

1. **The gross edge did not survive costs and the test regime.** Gross +0.161R
   overall, but cost 0.091R leaves +0.069R. In the test period the gross edge
   itself is −0.054R.
2. **The win rate is too low for the payoff.** At 1.89 average win and 1.07
   average loss, breakeven needs about 36.2% wins. Overall is 38.6% gross
   (31.6% after the 1R win definition), test is 33.1%.
3. **The portfolio selection did not add value.** Ranking by RS and filling only
   5 slots produced a taken subset at −0.003R. The skipped signals were better
   counterfactually. This is a warning about chasing the highest-RS, most
   extended names.
4. **The edge is period-dependent.** 2020–2024 works; 2025–2026 does not. A
   strategy that only works in the development window is not sellable.
5. **Cost and cash constraints are real.** H4's wider stop cut cost from 0.196R
   to 0.091R, which is an improvement, but not enough to create a robust edge.

## What this means for Phase 1

- Phase 1D (the strategy-proof phase) is complete.
- **No strategy has passed out-of-sample.** H1, H2, H3, H3 v3 and H4 all failed
  the pre-registered gate.
- Paper trading, live trading, and the sellable product remain blocked.
- Do not tune H4. The next step is a different strategy family, not another
  parameter set on the same pullback idea.

## Next-family options

1. **Liquid large-cap mean reversion / oversold bounce.** Different family from
   pullback momentum; testable on the existing daily panel; lower turnover.
2. **Monthly cross-sectional momentum rotation.** Lower turnover and a natural
   portfolio construction, but still momentum and still exposed to the same
   crowding/regime risk that hurt H4 in 2025–26.
3. **Event-driven (earnings, corporate actions).** Needs new data (earnings
   dates, surprise metrics) and a longer build.
4. **Reassess the product.** If no price-only technical family survives costs,
   the sellable product may need licensed data, a different value proposition
   (analytics/education), or a longer paper-trading track record.

Recommendation: test **liquid large-cap mean reversion** next, with a strict
index/volatility filter and low turnover. It is the most different from H4 and
can be tested on the current panel without new data. Do not start it until the
next hypothesis is frozen in writing.
