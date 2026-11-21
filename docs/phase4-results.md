# Phase 4 — All-Weather Multi-Asset Engine, Full History (2010–2026)

Status: **FAILED. Stop Phase 4. Do not tune it.**

This is the frozen run approved by Antigravity on 2026-11-21. The
pre-registration is `docs/phase4-hypothesis.md`. The engine is
`jobs/backtest_all_weather.py`; the primary run is in
`data/backtest_all_weather_2010_2026/`.

## What was tested

- 50% Nifty 50, 20% Gold BeES, 20% sovereign debt at 7.0% p.a., 10% cash/BTC.
- Cash until crypto history starts; BTC/USDT from the next semi-annual
  rebalance after 2017-08-17 (2017-12-29).
- Semi-annual rebalance on the last NSE session of June and December, at the
  close.
- Crash harvesting: at a −15% portfolio equity drawdown, rebalance to target
  once per drawdown episode; reset on a new high.
- No leverage, no derivatives, no shorting.
- Costs: 0.10% one-way equity/gold, 0.02% debt, 0.20% crypto; 0.20% p.a.
  equity-index expense; 7.0% debt yield; no capital-gains tax.
- Period: 2010-01-04 to 2026-11-19, 4,146 Nifty sessions.
- Starting capital: ₹10,00,000.

## Headline

| Metric | Primary |
|---|---:|
| Net CAGR | **11.72%** |
| Max drawdown, daily close | **−23.18%** (2020-02-12 to 2020-03-23) |
| Sharpe | 1.14 |
| Sortino | 1.64 |
| Calmar | **0.51** |
| 2025 calendar year | +19.36% |
| 2026 YTD (to 2026-11-19) | −3.27% |
| 2025–26 | +15.00% |
| Final equity | ₹64,90,301 |
| Transaction costs | ₹10,622 total (~0.023%/yr of average equity) |
| Rebalances | 36 (1 initial, 33 semi-annual, 2 crash) |

The 2026 row uses calendar-year close-to-close (`by_year`). The JSON also
reports `return_2026 = −3.51%` using the first 2026 session as the base; the
difference is the 2025-12-31 to 2026-01-02 move.

### Yearly returns, primary

| Year | Return | Year | Return |
|---|---:|---|---:|
| 2010 | +14.15% | 2019 | +31.05% |
| 2011 | −5.98% | 2020 | +43.58% |
| 2012 | +17.13% | 2021 | +17.67% |
| 2013 | +3.65% | 2022 | −1.54% |
| 2014 | +14.52% | 2023 | +27.52% |
| 2015 | −2.27% | 2024 | +20.17% |
| 2016 | +5.53% | 2025 | +19.36% |
| 2017 | +15.73% | 2026 YTD | −3.27% |
| 2018 | −5.51% | | |

Five negative years: 2011, 2015, 2018, 2022, 2026. The worst calendar year is
−5.98%; the worst intra-year daily drawdown is −23.18%. The portfolio is much
smoother than Nifty, but 2026 is negative because equity, gold, and BTC all
fell together.

## Gate result

| Gate | Requirement | Result | Status |
|---|---:|---:|---|
| Max drawdown, daily close | < 18% | −23.18% | **FAIL** |
| Net CAGR | > 12–15% | 11.72% | **FAIL** |
| Calmar | > 0.80 | 0.51 | **FAIL** |

Additional product expectations:

| Expectation | Result | Status |
|---|---:|---|
| 2025 and 2026 separately positive | +19.36% / −3.27% | **FAIL** |
| Net CAGR > Nifty + 5% | 11.72% vs 14.84% | **FAIL** |
| Beat static 50/20/20/10 with no crash harvest | +0.10pp CAGR, +0.08pp DD | Marginal |
| Cash instead of crypto passes gate | 9.08% / −19.94% / 0.46 | **FAIL** |

**Phase 4 fails all three approved gates.** The failure is not marginal on
drawdown and Calmar; CAGR misses the 12% lower bound by 0.28pp and would not
reach the 15% target even with a generous dividend adjustment.

## Benchmarks and sensitivities

| Series | CAGR | Max DD | Sharpe | Calmar | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| Primary: crash harvest + BTC | 11.72% | −23.18% | 1.14 | 0.51 | +19.36% | −3.27% |
| Static, no crash harvest + BTC | 11.62% | −23.26% | 1.14 | 0.50 | +19.36% | −3.27% |
| Crash harvest + cash instead of BTC | 9.08% | −19.94% | 1.07 | 0.46 | +19.80% | −0.42% |
| Static, no crash + cash | 9.01% | −19.16% | — | 0.47 | — | — |
| Nifty 50 buy-and-hold | 9.84% | −38.44% | — | — | +10.05% | −2.42% |
| Primary, Nifty-index crash trigger | 11.58% | −24.15% | 1.13 | 0.48 | +19.14% | −3.35% |
| Cash, Nifty-index crash trigger | 9.03% | −20.18% | 1.07 | 0.45 | +19.59% | −0.09% |

The all-weather engine does what it was designed to do relative to Nifty:

- CAGR is **+1.88pp** higher.
- Max drawdown is **15.3pp lower**.
- 2025–26 is **+15.00%** versus Nifty **+7.46%**.
- Sharpe is 1.14.

It is a respectable lower-volatility portfolio. It is **not** the approved
product gate, and it does not beat Nifty by 5%.

## The structural problem: 50% equity cannot meet a <18% drawdown gate

This is the most important finding.

Nifty fell **−38.44%** from 2020-01-14 to 2020-03-23. A 50% equity sleeve
alone therefore contributes:

```
0.50 × −38.44% = −19.22%
```

That is already worse than the 18% product gate, before gold, debt, or crypto
are considered. The cash-instead-of-crypto variant, which removes BTC
entirely, still has a **−19.94%** max drawdown. The primary with 10% BTC has
**−23.18%**.

In other words:

- The <18% gate and the 50% Nifty allocation are internally inconsistent in a
  2020-type crash.
- No crash-harvest rule that **buys more equity** after a 15% drawdown can fix
  this. It is a pro-cyclical rule: it sells gold/debt and adds equity into a
  falling market.
- To meet <18% consistently, the family needs either a lower equity weight, a
  genuine de-risking overlay (reduce equity when trend/volatility deteriorates),
  a hedged equity sleeve, or a relaxed drawdown gate.

This is an allocation/risk-budget problem, not a parameter-tuning problem.
Changing the crash threshold, gold weight, or rebalance month would not change
the arithmetic of a 50% equity sleeve in a −38% equity crash.

## Crash harvesting did not control drawdown

The approved crash rule was tested exactly as written, with two
interpretations:

| Trigger | Crash rebalances | CAGR | Max DD | Calmar |
|---|---:|---:|---:|---:|
| Portfolio equity drawdown | 2 | 11.72% | −23.18% | 0.51 |
| Nifty index drawdown | 6 | 11.58% | −24.15% | 0.48 |
| No crash harvest | 0 | 11.62% | −23.26% | 0.50 |

- Portfolio trigger dates: 2020-03-12 and 2022-06-16.
- Index trigger dates: 2011-02-08, 2015-09-07, 2020-03-09, 2022-06-15,
  2025-02-28, 2026-03-30.
- The portfolio trigger adds only **+0.10pp CAGR** and improves max DD by
  **0.08pp**. It is economically irrelevant.
- The Nifty trigger is worse: buying equity earlier in a drawdown increases
  the drawdown to −24.15% and lowers CAGR to 11.58%.
- In the cash variant, crash harvesting actually **worsens** max DD
  (−19.94% vs −19.16% with no crash harvest).

**Conclusion:** “harvest appreciated gold/debt and buy discounted equity” is a
rebalancing/return rule, not a drawdown-control rule. It cannot deliver a
<18% DD gate. A de-risking rule is the opposite: it must **reduce** equity
exposure when the portfolio/equity trend is deteriorating.

## Crypto sleeve: return booster, not a hedge

The 10% BTC sleeve is the difference between the primary and the cash variant:

| Metric | BTC sleeve | Cash sleeve | Difference |
|---|---:|---:|---:|
| CAGR | 11.72% | 9.08% | **+2.64pp** |
| Max DD | −23.18% | −19.94% | **−3.24pp worse** |
| 2018 | −5.51% | +4.20% | **−9.71pp worse** |
| 2026 | −3.27% | −0.42% | **−2.85pp worse** |
| 2025 | +19.36% | +19.80% | −0.44pp |

BTC has a 33.46% CAGR over 2017–2026, but with an −83% drawdown in 2018 and a
−53% drawdown in 2025–26. In this portfolio it adds return and volatility; it
does **not** behave like a dollar reserve or a crisis hedge. The 2018 result is
particularly clear: a diversified 50/20/20/10 with cash made +4.20%; with BTC
it lost −5.51%.

The BTC allocation also starts at the 2017-12-29 semi-annual rebalance, which
was near the 2017 crypto peak. That is a schedule artifact, not look-ahead: the
rule says semi-annual rebalance, and the next scheduled date after data starts
was December 2017. It is documented, not tuned.

## Why CAGR misses 12%

The asset-level CAGRs over the common history are:

| Asset | CAGR | 2025 | 2026 |
|---|---:|---:|---:|
| Nifty 50 price index | 9.84% | +10.05% | −2.42% |
| Gold BeES | 11.66% | +71.11% | −3.82% |
| Debt | 7.00% | +7.00% | +7.00% |
| BTC/USDT (from 2017-08-17) | 33.46% | −7.34% | −30.23% |

The weighted asset return is roughly 12.0% before costs/rebalancing; the
portfolio realizes 11.72% after ~0.12%/yr of costs. The 2025 gold spike
(+71.1%) is a major contributor to the +19.36% year; 2026 is negative because
Nifty, gold, and BTC all fell.

The Nifty series is a **price index**, not a total-return index. A Nifty 50
index fund would also receive dividends; at ~1.2% dividend yield on a 50%
sleeve, that is roughly +0.6pp portfolio CAGR. Even a generous adjustment
would put the portfolio near 12.3%, not 15%, and it would not fix the −23%
drawdown or 0.51 Calmar. The dividend adjustment is **not** included in the
reported result because no dividend series is available.

## Measurement caveat: daily vs month-end

The approved gate is evaluated on **daily closes**, consistent with Phases
1–3:

- Daily max DD: **−23.18%** → fails <18%.
- Month-end max DD: **−15.68%** → would pass <18% on month-end data.
- Month-end Calmar: 11.72% / 15.68% = **0.75** → still fails >0.80.

The month-end number is not used to claim a pass. It still fails CAGR and
Calmar, and it hides real intra-month risk. A product that reports only
month-end drawdown would be misleading.

## Data and execution caveats

- Nifty is Yahoo `^NSEI` research data, not licensed NSE data. Price index,
  no dividends.
- Gold BeES is an ETF market price, split-adjusted; its expenses are embedded,
  but tracking error and liquidity are not modelled. 24 gold dates outside the
  Nifty calendar are forward-filled.
- Debt is a **synthetic 7% p.a. ledger**, not the actual 10Y G-Sec/T-bill path.
  No duration, credit, or reinvestment risk. This is a best-case assumption.
- BTC is Binance USDT daily data; no INR conversion, Indian tax, or crypto
  regulatory risk.
- No AMFI NAV history, SGB cash flows, or RBI DBIE yields were used in this
  phase.
- Execution is close-to-close. Semi-annual ETF/index/crypto rebalancing at the
  close is reasonable, but it is not the next-open equity model used in
  Phases 2–3.
- No capital-gains tax, STT/GST/stamp/DP detail, advisory fee, or platform fee
  is modelled. At ~0.12%/yr, transaction/expense drag is too small to explain
  the gate failure; taxes would make the net result worse, not better.
- `2021-11-04` is missing from the Nifty/gold series; the portfolio calendar
  skips it.
- History starts in 2010. The 2008 crisis is **not** in the sample. A 50%
  equity sleeve in a 2008-type ~−60% Nifty crash would likely breach the 18%
  gate by a much wider margin. This is not a through-cycle stress test.

## Why it failed

1. **The drawdown gate and the allocation are inconsistent.** 50% Nifty in a
   −38.4% crash is −19.2% before anything else. The cash variant is −19.94%;
   BTC makes it −23.18%.
2. **Crash harvesting is pro-cyclical.** It buys equity into a drawdown. It
   added +0.10pp CAGR and 0.08pp DD, and the Nifty-trigger version was worse.
3. **Crypto is not a hedge.** It added +2.64pp CAGR but +3.24pp DD and turned
   2018 from +4.20% to −5.51%.
4. **CAGR is just below the lower gate.** 11.72% vs 12%; the price-index
   dividend omission could close that specific gap, but not the DD/Calmar gap.
5. **2026 is negative.** Nifty, gold, and BTC fell together; diversification
   reduced the loss but did not produce a positive year.

## Decision

**Stop Phase 4. Do not tune the equity weight, gold weight, debt yield, crypto
weight, rebalance month, crash threshold, trigger definition, cost model, or
measurement window on this result.**

The all-weather engine is a usable **lower-volatility portfolio**:

- 11.72% CAGR, −23.18% max DD, Sharpe 1.14, +15.0% in 2025–26.
- It beats Nifty by 1.88pp CAGR with 15.3pp less drawdown.
- It does **not** meet the approved <18% DD / >12–15% CAGR / >0.80 Calmar gate,
  and it does not beat Nifty by 5%.

The next decision belongs to the Operator/Antigravity:

1. **Reclassify as a lower-vol product** with an honest gate (for example,
   DD <25%, CAGR ~10–12%, Calmar >0.50). This is a commercial positioning
   decision; it must not be sold as an alpha or Nifty+5% product.
2. **Pre-register a new family with genuine de-risking** — lower equity weight
   and/or a trend/volatility overlay that reduces equity before deep drawdowns.
   This is a new hypothesis, not a Phase 4 parameter change. Do not run it
   until approved.
3. **Stop the multi-asset direction** and reassess the product thesis.

No product build, paper trading, legal/SEBI review, or data licensing is
approved by this result.
