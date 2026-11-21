# Phase 3 — Liquid Large-Cap Mean Reversion

**Status:** **CLOSED — FAILED Phase 3.** See `docs/phase3-results.md`.
**Date:** 2026-11-21
**Predecessor:** Phase 2 monthly momentum failed (`docs/phase2b-results.md`).

> This is the pre-registration. No parameter may change after the first full
> run. The family is judged primarily on drawdown, not maximum CAGR.

## Approval record

Antigravity approved and froze:

- Universe: top 200 by 20-day turnover (>= ₹5 crore), raw close >= ₹50, NSE EQ.
- Signal: long-term uptrend (`SMA50 > SMA200`, `price > SMA200`, `ret126 > 0`)
  plus short-term pullback (bottom 10 by `ret21`).
- Execution: month-end signal, next-session open, equal weight 10%, 5% ADV cap.
- Gate: research max DD < 28%, product max DD < 20%, 2× slippage positive,
  DSR > 0.95.
- No BE/BZ refetch. The Phase 3 universe is large and liquid; the first proof
  stays on NSE EQ.
- Rights convention: reinvested rights adjustment factor is approved.
- Equal-weight benchmark: simple transaction-cost-deducted top-200 benchmark.

## Why this family

Phase 2 failed because a broad smallcap momentum book had ~50% drawdowns,
frequent suspensions, and 4.5–7.9% annual cost drag. Phase 3 attacks those
failure modes directly:

- **Large, liquid names** instead of the broad smallcap EQ set.
- **Mean reversion** instead of momentum: buy short-term oversold names in a
  long-term uptrend, sell the bounce.
- **Lower turnover** and no chasing extended winners.
- **Explicit drawdown gate**: <20% product, <28% research.

Mean reversion is not automatically safer. A falling knife can keep falling.
The trend filter and the large-cap universe reduce that risk; they do not
guarantee it.

## Universe (approved)

- NSE, series `EQ`.
- Raw close >= ₹50.
- 20-session average turnover >= ₹5 crore (500 lacs).
- Rank eligible names by 20-session average turnover at each month-end and
  keep the **top 200**.
- Exclude ETFs, BEES, mutual funds, REITs and InvITs.
- One share class per company where the data allows.
- No BSE-only stocks.
- This is a **liquid large-cap proxy**, not official Nifty 200 membership.
  Label the result accordingly.

## Signal (approved)

At each month-end close `D`, using only data through `D`:

```
sma200 = average(adj_close, 200 sessions)
sma50  = average(adj_close, 50 sessions)
ret21  = adj_close(D) / adj_close(21 sessions earlier) - 1
ret126 = adj_close(D) / adj_close(126 sessions earlier) - 1
```

Filter within the top-200 turnover universe:

- `adj_close(D) > sma200`
- `sma50 > sma200`
- `ret126 > 0`
- At least 200 sessions of history.

Rank the filtered names by `ret21` **ascending** (most oversold first).
Select the bottom 10. If fewer than 10 pass, hold cash for the difference; do
not relax the filter. If none pass, the target is cash.

This is “buy the dip in an uptrend”, not a pure reversal rule.

## Portfolio

- Starting capital: ₹10,00,000.
- Target 10 positions, equal weight: 10% of current portfolio equity each.
- Maximum 10 positions.
- Cash buffer for costs; no negative cash.
- Max 5% of 20-session average daily turnover per position.
- One position per stock.
- No leverage, no shorting, no intraday execution.
- No pyramiding, no averaging down.

## Rebalance and execution

- **Signal date:** last trading session of the calendar month.
- **Execution:** open of the first trading session of the next calendar month.
- If a stock leaves the target, sell at the next open.
- If a stock cannot trade (halt, no open, locked circuit), keep the cash and do
  not substitute a name intraday. Retry the exit on the next session with a
  valid open; cancel the exit if the stock re-enters the target.
- If a stock is already held and remains in the target, rebalance to 10%.
- No intraday stop; the monthly signal is the exit rule.
- No leverage, no derivatives.

## Costs

Same full Budget-2026 equity-delivery model as Phase 2:

- STT 0.1% buy, 0.1% sell.
- Exchange, SEBI, stamp duty, GST, DP sell charge.
- Liquidity-tier slippage; 2× slippage stress run.
- Equal-weight benchmark is reported net of a simple 0.30% per unit turnover
  cost, and gross for transparency.

## Data and model caveats

- NSE EQ only; raw bhavcopy has no BE/BZ rows. Large caps are usually EQ, but a
  move to BE/BZ can still disappear. This is documented, not refetched.
- No point-in-time Nifty 100/200 membership; top-200 turnover is the approved
  proxy.
- Delisting treatment: write off only names absent from the current NSE master
  after 90 days; hold still-listed suspended names at last close. Report the
  no-writeoff and zero-recovery bounds if the result is close to the gate.
- Corporate actions cover 2010–2026; rights convention approved. Residual
  rights-unknown/factor-mismatch flags remain.
- Delivery-missing rows exist; no delivery filter in this run.
- Nifty is Yahoo `^NSEI`, research-only, not licensed NSE data.
- No dividends: price returns only.
- No circuit-limit fill model beyond the 5% ADV cap and slippage tiers.

## Gate

The family passes only if **all** of these hold on 2010–2026, with 2025–2026
as the held-out test:

| Gate | Threshold |
|---|---|
| Net CAGR | > Nifty 50 CAGR + 5 percentage points |
| Max drawdown | < 28% research; < 20% product |
| 2025 and 2026 separately | Both positive |
| 2× slippage | Still > Nifty + 5% and max DD < 28% |
| Deflated Sharpe | > 0.95 at an honest trial count (>=20) |
| Benchmark | Beat the net equal-weight top-200 benchmark |
| Random baseline | Beat multiple random seeds |
| Turnover / cost drag | Reported; no hidden cost assumption |

PBO is reported if a pre-declared grid is available; it is not required for the
first run because the signal has no fitted parameters beyond the approved
fixed thresholds.

If the family fails, stop it. Do not tune the lookback, top-N, trend filter,
holding period, or costs after seeing the result.

## Known risks

- **Value trap / falling knife:** oversold large caps can be structurally
  broken. The trend filter reduces but does not eliminate this.
- **Low return:** large-cap mean reversion may not clear Nifty + 5% after costs.
  A low-drawdown but low-return strategy is not a sellable product either.
- **Crowding:** large-cap reversal is a well-known factor; the edge may be
  small.
- **Cash drag:** the trend filter may leave the book in cash for long periods.
- **Regime change:** a momentum-led market may not reward dip buying.
- **Data:** PIT membership, BE/BZ pricing, delistings, and rights remain
  imperfect.

## Result

**FAILED.** Net CAGR −4.32%, max drawdown −66.62%, 2× slippage CAGR −9.48%,
2025 −20.77%, 2026 −17.06%, DSR 0.013 at 20 trials. Equal-weight top-200
benchmark CAGR 16.58%, max DD −37.05%. The bottom-10 `ret21` signal
underperformed; realized turnover was 19.2×/yr with 8.21% cost drag. No parameter
was changed after the run. Full details: `docs/phase3-results.md`.
