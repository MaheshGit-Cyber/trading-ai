# Phase 4B — All-Weather + Dynamic Trend De-risking, Full History (2010–2026)

Status: **FAILED on the approved gate. Stop Phase 4B. Do not tune it.**

The drawdown objective was achieved, but the return/Calmar and 2026 gates
failed. The de-risking rule is a real risk-control improvement, not a
product-grade pass.

This is the frozen run approved by Antigravity on 2026-11-21. The
pre-registration is `docs/phase4b-hypothesis.md`. The engine is
`jobs/backtest_all_weather_derisk.py`; outputs are in
`data/backtest_all_weather_derisk_2010_2026/`.

## What was tested

- **Normal regime** (Nifty > 200DMA at month-end): 50% Nifty, 20% Gold BeES,
  20% debt at 7.0% p.a., 10% cash/BTC.
- **De-risking regime** (Nifty <= 200DMA at month-end): 15% Nifty, 45% Gold
  BeES, 40% debt, 0% cash/BTC.
- Regime checked at each month-end close; rebalance at the **next session
  open**.
- Semi-annual drift rebalance on the last session of June/December, also at
  the next open.
- No Phase 4 crash harvesting.
- Costs: 0.10% one-way equity/gold, 0.02% debt, 0.20% crypto; 0.20% p.a.
  equity expense; 7.0% debt yield; no capital-gains tax.
- Period: 2010-01-04 to 2026-11-19; initial ₹10,00,000.

## Headline

| Metric | Phase 4B |
|---|---:|
| Net CAGR | **11.08%** |
| Max drawdown, daily close | **−14.62%** (2026-01-29 to 2026-03-23) |
| Sharpe | 1.20 |
| Sortino | 1.77 |
| Volatility | 9.32% |
| Calmar | **0.76** |
| 2025 | +24.06% |
| 2026 YTD | **−8.64%** |
| 2025–26 | +13.61% |
| Final equity | ₹58,85,577 |
| CAGR 2010–2025 | 12.36% |
| Full-period CAGR | 11.08% |

The 2010–2025 CAGR is above 12%; the 2026 loss is what drags the full-period
CAGR below the gate. The 2026 year is the out-of-sample failure.

## Gate result

| Gate | Requirement | Result | Status |
|---|---:|---:|---|
| Max drawdown, daily close | < 18% | −14.62% | **PASS** |
| Net CAGR | > 12–15% | 11.08% | **FAIL** |
| Calmar | > 0.80 | 0.76 | **FAIL** |
| 2025 positive | > 0% | +24.06% | PASS |
| 2026 positive | > 0% | −8.64% | **FAIL** |
| Net CAGR > Nifty + 5% | > 14.84% | 11.08% | **FAIL** |

**Core gate fails** because CAGR is 0.92pp below 12% and Calmar is 0.04 below
0.80. The drawdown gate is genuinely met: −14.62% is below 18% (and below
15%). This is not a marginal drawdown failure like Phase 4; it is a
return/consistency failure.

## Yearly returns vs Phase 4

| Year | Phase 4B | Phase 4 | Difference |
|---|---:|---:|---:|
| 2010 | +14.15% | +14.15% | 0.00 |
| 2011 | +4.46% | −5.98% | **+10.44** |
| 2012 | +10.19% | +17.13% | −6.94 |
| 2013 | +3.00% | +3.65% | −0.65 |
| 2014 | +14.54% | +14.52% | +0.02 |
| 2015 | −4.43% | −2.27% | −2.15 |
| 2016 | +8.99% | +5.53% | +3.46 |
| 2017 | +14.70% | +15.73% | −1.03 |
| 2018 | −9.06% | −5.51% | **−3.55** |
| 2019 | +22.79% | +31.05% | **−8.27** |
| 2020 | +45.21% | +43.58% | +1.63 |
| 2021 | +17.43% | +17.67% | −0.24 |
| 2022 | −1.57% | −1.54% | −0.02 |
| 2023 | +24.55% | +27.52% | −2.97 |
| 2024 | +20.11% | +20.17% | −0.06 |
| 2025 | +24.06% | +19.36% | **+4.70** |
| 2026 | −8.64% | −3.27% | **−5.37** |

The rule helps in some crisis years (2011, 2020, 2025) and hurts in whipsaw
or gold-crash years (2012, 2015, 2018, 2019, 2023, 2026). Net CAGR is 0.64pp
lower than Phase 4, while max DD is 8.56pp lower.

## What worked: 2020 and 2011

- **2020:** max drawdown **−11.73%** vs Phase 4 **−23.18%**. The Feb 28
  de-risking signal (execute Mar 2) cut equity from 50% to 15% before most of
  the March collapse. 2020 return was +45.21%, slightly better than Phase 4.
- **2011:** +4.46% vs Phase 4 −5.98%. The Jan/May de-risking regime avoided
  the equity decline.
- **2025:** +24.06% vs Phase 4 +19.36%. The Jan–Apr de-risking regime held
  more gold into the 2025 gold rally.
- **Max DD:** −14.62%, below the 18% gate. The risk-control concept is
  validated.

## What failed: 2026 and the 45% gold concentration

The 2026 result is the key failure.

In the supplied data:

- Gold BeES peaked at **₹146.53 on 2026-01-29**.
- It fell to **₹110.72 by 2026-03-23**, a **−24.4%** crash.
- Nifty de-risked at the 2026-02-27 month-end (Nifty 25,178.65 vs 200DMA
  25,347.92).
- The portfolio moved to 15% equity / **45% gold** / 40% debt at the
  2026-03-02 open, buying gold at **₹140.10** — just before the crash.
- March 2026 portfolio return: **−6.84%**; 2026 YTD: **−8.64%**.
- Gold bought at ₹140.10 on 2026-03-02 was ₹106.30 on 2026-11-19, **−24.1%**.
  A 45% sleeve alone was about a **−10.9pp** drag on that capital before
  rebalancing and the debt/equity offsets.
- 2026 max drawdown: **−14.62%**, worse than Phase 4’s 2026 drawdown of
  −12.80%.

The rule de-risked **out of equity and into gold after gold had already
spiked 32%**, then gold crashed. The “defensive” sleeve was the source of the
loss. This is not a small timing error; it is a structural weakness of a fixed
45% gold allocation. Gold is not a stable hedge; it has its own bubbles and
bear markets.

## Whipsaws and missed rallies

There were **33 regime changes** in 16.9 years (~2 per year), and the
portfolio spent **27.2%** of sessions in de-risking. The 200-day month-end
signal is lagged:

- 2012: de-risk May 31, re-risk June 29; +10.19% vs Phase 4 +17.13%.
- 2015: de-risk April, re-risk May, de-risk August–December; −4.43% vs
  −2.27%.
- 2018: de-risk March, re-risk April, de-risk October, re-risk November;
  −9.06% vs −5.51%.
- 2019: de-risk January–March and July–September; +22.79% vs +31.05%.
- 2023: de-risk February–April; +24.55% vs +27.52%.
- 2026: de-risk February onward; −8.64% vs −3.27%.

The rule is a return-for-drawdown trade, not a free improvement.

## Turnover and costs

- 64 rebalances: 1 initial, 33 regime changes, 30 semi-annual.
- Transaction costs ₹65,872 total, ~0.15%/yr of average equity.
- Equity expense ~0.10%/yr; total cost drag ~0.25%/yr.
- Costs are higher than Phase 4 (₹10,622) but still too small to explain the
  CAGR failure. The failure is the 2026 gold crash and the whipsaw.

## Why it failed

1. **The drawdown gate was met, but the return gate was not.** 11.08% vs 12%,
   and Calmar 0.76 vs 0.80. The risk reduction is real but expensive.
2. **45% gold is not a defensive allocation.** In 2026, gold spiked and then
   crashed; the de-risking rule bought it near the peak. The portfolio lost
   −8.64% in 2026 while Phase 4 lost −3.27%.
3. **The 200-day signal whipsaws.** It helps in 2011/2020/2025 but misses
   recoveries in 2012/2019/2023 and gets chopped in 2015/2018.
4. **2010–2025 CAGR is 12.36%, but 2026 is −8.64%.** The current-year loss is
   the OOS failure; without it, the CAGR would clear 12%.
5. **The “mathematically below 15–18%” claim is half right.** The DD is
   −14.62%, so the drawdown ceiling is met. The claim did not account for the
   return cost, the Calmar gate, or a gold crash.

## Data caveats

- Same data as Phase 4: Nifty price index (no dividends), Gold BeES
  split-adjusted price, synthetic 7% debt, Binance BTC.
- 2026 data includes a **2026-01-01 session**, a large Nifty gap on
  2026-02-03, and a gold spike/crash. These prints are used as supplied, not
  cleaned. If the 2026 gold path is revised, the 2026 conclusion should be
  rechecked.
- 2008 is not in the sample; a 2008-type equity crash is not tested.
- No AMFI NAV, SGB cash flows, RBI DBIE yields, INR crypto conversion,
  capital-gains tax, STT/GST/stamp/DP detail, or platform fee.
- Next-open execution is used for regime/semi-annual rebalances; daily marks
  are at the close.

## Decision

**Stop Phase 4B. Do not change the 200-day window, the monthly check, the
15/45/40 de-risking weights, the 50/20/20/10 normal weights, the execution
timing, the semi-annual rule, the cost model, or the gate on this result.**

The result is a genuine partial success:

- Max DD **−14.62%**, below 18%.
- Sharpe **1.20**, Sortino **1.77**.
- 2025 +24.06%, 2020 +45.21%, 2011 +4.46%.
- But CAGR **11.08%**, Calmar **0.76**, 2026 **−8.64%**.

The next decision belongs to the Operator/Antigravity:

1. **Accept a lower-vol product with a relaxed gate** — for example DD <18%,
   CAGR ~10–12%, Calmar >0.70. The product is a capital-preservation /
   equity-participation engine, not a Nifty+5% alpha product.
2. **Pre-register a new family that fixes the defensive sleeve** — replace
   part of the 45% gold with cash/short debt, cap gold, or add a gold trend
   filter. This is a new hypothesis, not a Phase 4B parameter change. Do not
   run it until frozen and approved.
3. **Stop the multi-asset direction** and reassess.

No product build, paper trading, legal/SEBI review, or data licensing is
approved by this result.
