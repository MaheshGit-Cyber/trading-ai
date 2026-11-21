# Phase 4B — All-Weather + Dynamic Trend De-risking

**Status:** **CLOSED — FAILED Phase 4B.** See `docs/phase4b-results.md`.
**Date:** 2026-11-21
**Approval:** Antigravity -> OpenCode, 2026-11-21T10:00+05:30
(`bridge/to_opencode.md`), selecting Option 2: Dynamic De-risking Overlay.
**Predecessor:** Phase 4 all-weather failed its approved gate
(`docs/phase4-results.md`: 11.72% CAGR, −23.18% DD, 0.51 Calmar).

> This is a new family, not a Phase 4 parameter change. The regime rule is
> approved; the implementation details below are frozen before the first run.
> The claim that this “mathematically” brings drawdown below 15–18% is treated
> as a hypothesis, not a guarantee. No parameter may change after the result.

## Why this family

Phase 4 showed that a static 50% Nifty sleeve cannot meet a <18% drawdown
gate: in the 2020 crash, 50% × −38.44% = −19.22% before any other sleeve. The
approved fix is a monthly trend regime:

- When Nifty is above its 200-day moving average, hold the growth allocation.
- When Nifty is at or below the 200-day moving average at a month-end, cut
  equity and move to gold/debt.

The intent is to avoid the deep equity drawdowns of 2011, 2015, and March 2020
without abandoning the bull-market compounding. Whether it actually achieves
<18% DD and >12–15% CAGR is an empirical question.

## Regime signal

At each **month-end Nifty close**:

```
sma200 = average(Nifty close, last 200 sessions, including the month-end close)
normal  if Nifty close > sma200
derisk  if Nifty close <= sma200
```

- If fewer than 200 sessions are available, the regime is **normal**.
- The signal uses only data available at the month-end close.
- The regime is checked once per month. No intra-month signal.

## Target allocations

| Sleeve | Normal regime | De-risking regime |
|---|---:|---:|
| Nifty 50 | 50% | 15% |
| Gold BeES | 20% | 45% |
| Sovereign debt | 20% | 40% |
| Cash / BTC | 10% | 0% |

- Normal: 10% is cash until crypto history starts; BTC/USDT after 2017-08-17.
- De-risking: the cash/crypto sleeve is zero. BTC is sold; gold/debt are the
  defensive assets.
- No leverage, no derivatives, no shorting.
- If an asset price is unavailable, its target goes to cash; this does not
  happen for Nifty/gold/debt in the sample.
- Starting capital: ₹10,00,000.

## Rebalance and execution

- **Initial allocation:** first session, 2010-01-04, at the close, to the
  normal target.
- **Regime change:** if the month-end regime differs from the current regime,
  rebalance to the new target at the **next session open**. The signal is
  month-end close; execution is next open, so there is no same-close
  look-ahead.
- **Semi-annual drift rebalance:** last NSE session of June and December,
  rebalance to the **current** regime target at the **next session open**.
  If the regime also changes at that month-end, one rebalance to the new
  target is done.
- **Other month-ends:** no rebalance unless the regime changes.
- **No Phase 4 crash harvesting.** The 200-day regime replaces the pro-cyclical
  “buy equity after a 15% drawdown” rule, which Phase 4 showed does not control
  drawdown.
- If a scheduled execution date is missing, execute at the next available
  session.
- Execution is at the open; daily marks are at the close.
- No intraday stop, no discretionary override.

### Why regime-change + semi-annual, not monthly rebalancing

Monthly rebalancing inside a de-risking regime would keep buying equity as it
falls (to maintain 15%), which is pro-cyclical. Regime-change rebalancing plus
semi-annual drift control keeps turnover low and lets the defensive sleeve
work. This is a frozen implementation choice, not a result-dependent one.

## Costs

Same as Phase 4:

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

Transaction costs are charged on the traded notional at each open rebalance.
The equity expense is deducted continuously. At the expected turnover, costs
are not expected to be the binding constraint; they are reported.

## Data

| Series | File | Coverage | Notes |
|---|---|---|---|
| Nifty 50 | `data/index/nifty50.csv` | 2010-01-04 to 2026-11-19, 4,146 sessions | Price index; open and close |
| Gold BeES | `data/gold/goldbees_daily_2010_2026.csv` | 2010-01-04 to 2026-11-19, 4,169 rows | Split-adjusted; open and close |
| BTC/USDT | `data/crypto/btcusdt_daily_2017_2026.csv` | 2017-08-17 to 2026-11-20, 3,383 bars | Binance daily open/close |
| Debt | Synthetic | 2010-01-04 to 2026-11-19 | `(1.07)^(calendar days / 365.25)` |

- Nifty is Yahoo `^NSEI` research data, not licensed NSE data. Price index, no
  dividends.
- Gold BeES is an ETF market price; its expenses are embedded; tracking error
  and liquidity are not modelled. Dates outside the Nifty calendar are
  forward-filled.
- Debt is a synthetic 7% ledger, not the actual 10Y G-Sec/T-bill path. No
  duration/credit risk.
- BTC is Binance USDT; no INR conversion, Indian tax, or crypto regulatory
  risk.
- `2021-11-04` is missing from Nifty/gold; the calendar skips it.
- History starts in 2010; the 2008 crisis is not in the sample.

## Gate

Same approved product gate as Phase 4:

| Gate | Requirement |
|---|---|
| Max drawdown, daily close | < 18% |
| Net CAGR | > 12–15% |
| Calmar | > 0.80 |

Additional reporting:

- 2025 and 2026 separately positive.
- Net CAGR > Nifty buy-and-hold + 5%.
- Beat the Phase 4 static all-weather benchmark (11.62% CAGR, −23.26% DD,
  0.50 Calmar).
- Report regime changes, time in de-risking, turnover/cost drag, and the
  de-risking episodes.
- Report the no-crypto and no-semi-annual sensitivities only if they are
  pre-declared here. **They are not part of the primary test.** The primary is
  the rule above.

## No-tuning rule

If the frozen run fails, **stop**. Do not change the 200-day lookback, the
monthly check, the 15/45/40 de-risking weights, the normal 50/20/20/10
weights, the execution timing, the semi-annual rule, the cost model, or the
gate on this result. A further family requires a new pre-registration and
fresh approval.

## Known risks before the run

- **45% gold is a concentrated bet.** Gold had a −27.5% peak-to-trough
  drawdown in 2026 and a long 2013–2015 bear market. A de-risking regime that
  piles into gold can have its own drawdown.
- **The 200-day signal is lagged and whipsaws.** Month-end checks can de-risk
  after a fall and re-risk after a rally. 2011, 2015, 2018, 2019, 2022, 2023,
  2024, 2025, and 2026 all have regime flips in the sample.
- **The de-risking allocation has no cash.** It is 15% equity / 45% gold /
  40% debt. If gold and equity fall together, the “defensive” book is not
  defensive.
- **The “mathematically below 15–18%” claim is not proven by the allocation
  arithmetic.** The backtest decides.
- **CAGR may fall below 12%.** Cutting equity to 15% for ~27% of the sample
  can remove more compounding than drawdown.
