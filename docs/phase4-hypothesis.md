# Phase 4 — All-Weather Multi-Asset Engine

**Status:** **CLOSED — FAILED Phase 4.** See `docs/phase4-results.md`.
**Date:** 2026-11-21
**Approval:** Antigravity -> OpenCode, 2026-11-21T09:44+05:30
(`bridge/to_opencode.md`).
**Predecessors:** Phase 2B monthly momentum and Phase 3 large-cap mean
reversion both failed.

> This is the approved specification, transcribed from the 09:44 bridge
> message. The implementation conventions below were fixed before the first
> full run. No allocation, threshold, rebalance date, cost, or gate may change
> after the result. The family is judged on **daily-close max drawdown**, net
> CAGR, and Calmar.

## Approval record

Antigravity approved and froze:

- Allocation: 50% equity index (Nifty 50), 20% gold (Nippon Gold BeES),
  20% sovereign debt / liquid yield at 7.0% p.a., 10% cash/crypto.
- Crypto sleeve: BTC/USDT from 2017 to 2026; before crypto history, cash.
- Rebalance: semi-annual, June 30 and December 31.
- Dynamic crash harvesting: when equity drawdown exceeds 15%, rebalance to
  harvest appreciated gold/debt and buy discounted equity.
- Product gate: max drawdown < 18%, net CAGR > 12–15%, Calmar > 0.80.
- Data supplied by Antigravity: Nifty 50, Gold BeES (split-adjusted), BTC/USDT,
  and a 7.0% p.a. sovereign-debt ledger.

## Allocation

| Sleeve | Target | Instrument |
|---|---:|---|
| Equity | 50% | Nifty 50 index |
| Gold | 20% | Nippon Gold BeES, split-adjusted |
| Debt | 20% | Sovereign/liquid debt, 7.0% p.a. compounding |
| Cash / crypto | 10% | Cash until 2017-08-17; BTC/USDT after |

- No leverage, no derivatives, no shorting.
- The portfolio is long-only and fully invested (the 10% sleeve is cash or
  BTC, not a tactical cash buffer).
- Starting capital: ₹10,00,000.

## Rebalance and execution

- Initial allocation on the first common session, 2010-01-04.
- Semi-annual rebalance on the **last NSE session of June and December**, at
  the close. The approved wording says June 30 / December 31; the last trading
  session is used when those dates are holidays.
- Crash harvesting:
  - Measure **portfolio equity drawdown** from its all-time high.
  - When drawdown reaches **−15%**, rebalance once to the target weights.
  - Reset the trigger only when the portfolio makes a new high.
  - This is one trigger per drawdown episode, not a daily re-trigger.
- Execution is close-to-close. Index funds/ETFs and crypto can be traded at or
  near the close; this is not a next-open equity execution model. The
  difference is small at semi-annual frequency but is a documented limitation.
- No intraday stop, no tactical overlay, no discretion.

### Interpretation note

The approval says “when Equity Drawdown exceeds >15%”. The primary run
interprets this as **portfolio equity-curve drawdown**, which is the standard
meaning for a strategy. A second run interprets it as **Nifty index drawdown**
and is reported only as a sensitivity. Both fail the gate; the primary is not
selected after seeing the result.

## Costs

| Item | Assumption |
|---|---:|
| Equity index transaction cost | 0.10% one-way |
| Gold ETF transaction cost | 0.10% one-way |
| Debt transaction cost | 0.02% one-way |
| Crypto transaction cost | 0.20% one-way |
| Equity index fund expense | 0.20% p.a., charged daily |
| Gold ETF expenses | Embedded in the Gold BeES price |
| Debt yield | 7.00% p.a., net, calendar-day compounding |
| Capital-gains tax | Not modelled; investor-specific |
| Advisory/platform fee | Not modelled |

Transaction costs are charged on the traded notional at each rebalance. The
equity expense is deducted from the equity sleeve continuously. There is no
STT/GST/stamp/DP model for the ETF trades; at semi-annual turnover the effect
is negligible relative to the gate failure, but it is a caveat for a live
product.

## Data

| Series | File | Coverage | Notes |
|---|---|---|---|
| Nifty 50 | `data/index/nifty50.csv` | 2010-01-04 to 2026-11-19, 4,146 sessions | Clean closes; price index, no dividends |
| Gold BeES | `data/gold/goldbees_daily_2010_2026.csv` | 2010-01-04 to 2026-11-19, 4,169 rows | Split-adjusted; 24 dates outside the Nifty calendar are forward-filled |
| BTC/USDT | `data/crypto/btcusdt_daily_2017_2026.csv` | 2017-08-17 to 2026-11-20, 3,383 bars | Binance daily close; aligned to Nifty sessions |
| Debt | Synthetic | 2010-01-04 to 2026-11-19 | `(1.07)^(calendar days / 365.25)` |

- `data/index/nifty50_2010_2026.csv` contains 29 rows with empty closes
  (holidays/weekends, plus 2026-11-20); it is not used as the calendar.
- `2021-11-04` is missing from the Nifty and gold series; the portfolio
  calendar skips it.
- Nifty is Yahoo `^NSEI` research data, not licensed NSE data. No Nifty total
  return / dividend series is used.
- Gold BeES is an ETF market price, not SGB NAV. Its own expense ratio is
  embedded; tracking error is not separately modelled.
- The debt sleeve is a **synthetic 7% ledger**, not the actual 10Y G-Sec or
  T-bill path. It assumes no duration risk, no credit risk, and no reinvestment
  friction.
- BTC is USDT-quoted; no INR conversion, Indian tax, or crypto regulatory risk
  is modelled.
- No AMFI mutual-fund NAV history, SGB cash flows, or RBI DBIE yield path was
  used in this phase.

## Gate

Approved Phase 4 gate:

| Gate | Requirement |
|---|---|
| Max drawdown, daily close | < 18% |
| Net CAGR | > 12–15% |
| Calmar | > 0.80 |

Additional reporting required by the earlier product discipline:

- 2025 and 2026 separately positive.
- Net CAGR > Nifty buy-and-hold + 5%.
- Beat a static 50/20/20/10 benchmark with no crash harvesting.
- Report the cash-instead-of-crypto sensitivity.
- Report the Nifty-index-drawdown trigger sensitivity.

## No-tuning rule

If the frozen run fails, **stop**. Do not change the equity weight, gold
weight, debt yield, crypto weight, rebalance frequency, crash threshold,
trigger definition, cost model, or measurement window on this result. A new
family requires a new pre-registration and fresh approval.
