# Phase 3 — Liquid Large-Cap Mean Reversion, Full History (2010–2026)

Status: **FAILED. Stop this family. Do not tune it.**

This is the frozen run approved by Antigravity on 2026-11-21. The
pre-registration is `docs/phase3-hypothesis.md`.

## What was tested

- Universe: NSE EQ, raw close >= ₹50, 20D turnover >= ₹5 crore, top 200 by
  20D turnover at each month-end; ETFs/REITs/InvITs excluded.
- Signal: `price > SMA200`, `SMA50 > SMA200`, `ret126 > 0`; then bottom 10 by
  `ret21` (most oversold).
- Portfolio: 10 positions, equal weight 10%, max 5% ADV, no leverage.
- Execution: month-end close signal, next-session open.
- Costs: full delivery STT, exchange, SEBI, stamp, GST, DP, slippage; 2×
  slippage stress.
- Period: first execution 2010-11-01, last date 2026-11-19; 193 rebalances.
- Delisting: unlisted-only 90-day writeoff; still-listed suspended/BE names are
  held at last close.

## Headline

| Metric | Primary | 2× slippage |
|---|---:|---:|
| Net CAGR | **−4.32%** | **−9.48%** |
| Max drawdown | **−66.62%** | **−80.99%** |
| Sharpe | −0.11 | −0.40 |
| Sortino | −0.15 | −0.52 |
| Calmar | −0.06 | −0.12 |
| 2025 return | −20.77% | −22.22% |
| 2026 YTD | −17.06% | −16.21% |
| 2025–26 | −34.67% | −35.37% |
| Turnover / yr | 19.21× | 18.98× |
| Cost drag / yr | 8.21% | 14.06% |
| Final equity | ₹4,92,527 | ₹2,02,286 |
| Max holdings | 14 | 14 |
| Avg stale value | 13.2% | 15.4% |
| Max stale value | 36.2% | 38.1% |
| Writeoffs | 3, ₹1.34L | 3, ₹1.08L |

Max drawdown: 2010-12-02 to 2020-03-23, **−66.62%**.

### Yearly returns, primary

| Year | Return | Year | Return |
|---|---:|---|---:|
| 2010 | −10.16% | 2019 | +6.43% |
| 2011 | −15.34% | 2020 | +12.98% |
| 2012 | +15.01% | 2021 | +18.62% |
| 2013 | −45.37% | 2022 | −0.70% |
| 2014 | +25.67% | 2023 | +22.97% |
| 2015 | −4.54% | 2024 | +0.66% |
| 2016 | −17.50% | 2025 | −20.38% |
| 2017 | +25.51% | 2026 | −17.54% |
| 2018 | −27.94% | | |

The 2013 loss is −45%, and the strategy is negative in both held-out years.
This is not a low-drawdown product.

## Benchmarks

| Series | CAGR | Max DD | Sharpe |
|---|---:|---:|---:|
| Strategy primary | −4.32% | −66.62% | −0.11 |
| Equal-weight top-200 universe, net of 0.30%/turnover | 16.58% | −37.05% | 0.82 |
| Nifty 50 buy-and-hold | 9.31% | −38.44% | — |
| Random top-10, seed 1 | −2.54% | −61.79% | −0.02 |
| Random top-10, seed 7 | −3.59% | −68.97% | −0.09 |
| Random top-10, seed 42 | +0.58% | −56.42% | 0.13 |

The strategy is worse than the equal-weight top-200 universe by ~21 points of
CAGR, and worse than Nifty by ~14 points. It is also below the average random
top-10 baseline. The signal has no edge.

Monthly excess versus the net equal-weight benchmark: **−1.65%/month, t =
−6.13, hit rate 34.4%** over 192 months. This is a statistically strong
underperformance, not noise.

Even adding back all reported costs, final equity would be about ₹12.8L, a
gross CAGR of only ~1.6%; the signal itself is far below the top-200
equal-weight universe. Costs make a bad signal worse, but costs are not the
only cause.

## Gate result

| Gate | Result | Status |
|---|---|---|
| Net CAGR > Nifty + 5% | −4.32% vs 14.31% | **FAIL** |
| Research max DD < 28% | −66.62% | **FAIL** |
| Product max DD < 20% | −66.62% | **FAIL** |
| 2025 and 2026 separately positive | −20.77% / −17.06% | **FAIL** |
| 2× slippage > Nifty + 5% and DD < 28% | −9.48% / −80.99% | **FAIL** |
| DSR > 0.95 | 0.013 at 20 trials | **FAIL** |
| Beat net equal-weight top-200 | −4.32% vs 16.58% | **FAIL** |
| Beat random seeds | worse than average random | **FAIL** |
| Turnover / cost drag reported | 19.21× / 8.21% | PASS reporting |

**Overall: Phase 3 fails every substantive gate.** The drawdown is worse than
Phase 2, not better.

## Execution audit

`jobs/audit_monthly_entries.py` checked 1,930 selected stock/months:

- 1,930 matched; 0 missing execution rows.
- Open-versus-previous-close gap: median +0.28%, p90 +1.22%, p99 +3.71%,
  max +8.00%, min −5.51%.
- 0.10% of entries gapped more than 5%; none gapped more than 10%.
- 0 locked/single-price sessions; 0 zero-volume rows.

Execution is clean. The failure is signal and turnover, not fills.

## Why it failed

1. **The “lower turnover” premise was wrong.** The bottom-10 by `ret21` is
   almost completely replaced every month. Realized turnover is **19.2×/yr**,
   higher than Phase 2’s 10.1×. At ~0.4% per side, that is ~8.2% annual cost
   drag; at 2× slippage it is 14.1%.
2. **The reversal signal has negative gross alpha in this universe.** The
   bottom-10 oversold large caps underperformed the top-200 equal-weight
   universe by ~21 points of CAGR. The trend filter did not prevent falling
   knives.
3. **Drawdown is worse, not better.** −66.6% versus Phase 2’s −49.8% and the
   equal-weight benchmark’s −37.1%. Large-cap size alone does not make a
   reversal book safe.
4. **Both held-out years are negative.** 2025 −20.8%, 2026 −17.1%. There is no
   OOS support.
5. **Random 10-name monthly replacement is also weak.** Random seed 42 is only
   +0.58% CAGR; the 10-name monthly full-replacement structure is structurally
   cost-heavy. The equal-weight 200-name benchmark is the only thing that
   works, and it is not an alpha strategy.

## Decision

**Stop Phase 3. Do not tune the holding period, lookback, trend filter, top-N,
or costs on this result.** That would be an in-sample fit.

The next step should not be another 10-name monthly equity factor. The evidence
now says:

- Broad equal-weight top-200 equity is a reasonable return engine, but it is
  not a sellable “alpha” claim and still has ~37% drawdown.
- 10-name monthly replacement has 10–20× turnover and 4–14% cost drag; it needs
  a much larger gross edge than either Phase 2 or Phase 3 found.
- A product-grade subscription needs a **lower-turnover, multi-asset
  allocation** with explicit drawdown control, not another single-factor equity
  rotation.

Recommended next family from the approved master plan:

**Profile 1 — Passive Builder / All-Weather Multi-Asset Engine.**

- 50% equity index (Nifty 50 / LargeMid 250), 20% gold, 20% G-Sec/liquid debt,
  10% cash/crypto.
- Semi-annual rebalancing; harvest debt into equity when equity drawdown >15%.
- Target: lower drawdown, no leverage, no stock-specific delisting risk.
- Data needed: AMFI NAV history, gold ETF/SGB, 10Y G-Sec/T-bill yields. Crypto
  BTC/ETH data already exists.
- Gate: max DD <20%, positive 2025/2026, net return above a static 50/20/20/10
  benchmark, DSR/reality checks where applicable.

This is a product pivot, not a new alpha claim. It needs Antigravity/Operator
approval and the missing data before a backtest.

## Files

- `jobs/backtest_largecap_meanrev.py` — Phase 3 engine.
- `docs/phase3-hypothesis.md` — frozen pre-registration.
- `data/backtest_meanrev_2010_2026/` — primary.
- `data/backtest_meanrev_2010_2026_stress2x/` — 2× stress.
- `data/backtest_meanrev_2010_2026_random{1,7,42}/` — random baselines.
- `data/backtest_meanrev_2010_2026/entry_audit.json` — entry audit.
