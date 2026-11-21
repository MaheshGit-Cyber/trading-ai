# Phase 1 — first strategy backtest (failed gate)

**Date:** 2026-11-20  
**Strategy:** `trend_pullback` (daily swing, long-only)  
**Code:** `engine/features.py`, `jobs/backtest_trend_pullback.py`  
**Outputs:** `data/backtest/trades_trend_pullback.csv`, `data/backtest/summary_trend_pullback.json`, `data/backtest/variants.json`  
**Verdict:** **FAILED out-of-sample gate. Do not sell or build product around this strategy.**

This is the first honest test, not a product result. The purpose was to prove or
disprove one strategy family before spending money on UI, execution or legal
work. It did not pass.

## What was tested

Universe and data:

- NSE `EQ` rows only. BSE is excluded from this first proof because 2020–2023
  BSE identity is unresolved.
- 2020-01-01 → 2026-11-19, adjusted panel (`data/curated/panel.csv`).
- ETFs, REITs, InvITs and mutual-fund counters excluded.
- Raw price ≥ ₹20, 20D average turnover ≥ ₹1 crore.
- Only one open trade per stock at a time.

Signal (`trend_pullback`):

1. Regime `trend_up`: close > 200DMA, 50DMA > 200DMA, ADX(14) ≥ 20,
   20-session 50DMA slope > 0.
2. A 3–8 session pullback from a 15-bar swing high.
3. Pullback low holds above the 20DMA; no pullback close below the 50DMA.
4. RSI(14) at the pullback low between 40 and 65.
5. Pullback volume below the 20D average.
6. Entry trigger: close above the prior day's high, on volume ≥ 1.3 × 20D
   average.
7. The pullback low must be in the last 3 bars (no late entry after a long
   recovery).
8. Avoid entries more than 15% above the 50DMA (late-stage filter).

Execution:

- Entry at the **next open** after the close-based signal.
- Stop = closer of pullback low and entry − 1.5 × ATR(14).
- Reject stops tighter than max(0.5 × ATR, 1% of price); otherwise position size
  explodes and costs become meaningless.
- Target = prior swing high; if already exceeded, entry + 2.5R. Require at
  least 2R.
- Horizon 10 sessions; time exit at the horizon close.
- Same-day stop and target: **stop first**.
- Gap through stop/target: fill at the open.
- Position size: 1% capital risk, capped at 25% of capital and 5% of 20D
  average daily turnover.
- Costs: STT 0.1% each side, exchange, SEBI, stamp, GST, ₹13.5 DP sell charge.
- Slippage: 0.10% one-way for ≥ ₹10cr turnover, 0.25% for ₹1–10cr, 0.50% below
  ₹1cr. Stress test doubles slippage.

## Result — baseline

315 closed trades. All are primary (no unadjusted corporate-action risk).

| Metric | Gross | Net (base costs) | Net (2× slippage) |
|---|---:|---:|---:|
| Expectancy | **−0.082R** | **−0.194R** | **−0.256R** |
| Median R | — | −1.071R | — |
| Positive trades | — | 34.3% | — |
| Win rate ≥ 1R | — | 19.7% | — |
| Average win | — | +1.385R | — |
| Average loss | — | −1.018R | — |
| Profit factor | — | 0.710 | — |
| Max drawdown | — | −64.4R | — |
| Average cost | — | 0.112R | — |
| Average hold | — | 5.45 sessions | — |

Exit reasons: 148 stops, 21 same-day stops, 7 gap stops, 38 targets, 1 same-day
target, 2 gap targets, 98 time exits.

## Walk-forward split

No target/stop parameter was optimized on the test period. The final rules
were fixed before the final run. Implementation/data-quality fixes were made
after the first diagnostic exposed artifacts; see below.

| Period | Trades | Gross R | Net R | Net 2× slip | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Dev 2020–2022 | 92 | −0.178 | −0.288 | −0.349 | 0.60 | fail |
| Validation 2023–2024 | 154 | −0.012 | −0.125 | −0.187 | 0.80 | fail |
| Test 2025–2026 | 69 | −0.109 | −0.223 | −0.284 | 0.68 | **fail** |

The test period has fewer than the required 100 trades, negative expectancy
after costs, negative expectancy under 2× slippage, and profit factor below
1.2. Every gate is red.

## Diagnostic variants (not new strategies)

These were run only to locate the failure. They do **not** make the strategy
sellable.

| Variant | Trades | Gross R | Net R | Test net R |
|---|---:|---:|---:|---:|
| Baseline stop/target | 315 | −0.082 | −0.194 | −0.223 |
| Hold to 10-day close | 315 | +0.017 | −0.095 | −0.213 |
| Move stop to breakeven after +1R | 315 | −0.052 | −0.165 | −0.202 |

The 10-day hold is the only variant with positive gross expectancy, and it is
still negative after costs. The validation period (2023–2024) was positive on
that variant, but the test period was not. That is not an edge; it is regime
dependence.

## What changed after the first diagnostic

The first run produced 510 trades and exposed two artifacts that had to be
fixed before any result could be trusted:

1. **ETF contamination.** NSE's `EQ` series includes ETFs. They were excluded.
2. **Absurdly tight stops.** Some pullback lows sat 0.03–0.4% below entry.
   Position size then exploded, and a 0.05-point move created 72R excursions.
   A minimum stop of max(0.5 × ATR, 1% of price) and a 25%-of-capital position
   cap were added. These are execution sanity filters, not profit filters.
3. **Late pullback entries.** The pullback low was allowed to be up to 14 bars
   old, which is a recovery entry, not a fresh pullback. The low is now
   required in the last 3 bars.

The final baseline still lost money. The fixes did not rescue the edge; they
only removed results that were mechanically invalid.

## Why it failed

1. **No gross edge.** The baseline is roughly flat before costs. A strategy
   must clear costs before it can be sold.
2. **Costs are not small.** Average cost is 0.112R. The signal needs more than
   0.11R of gross edge just to break even.
3. **Target is too far for the holding period.** Median MFE is about 0.79R;
   only ~13% of trades reach the 2R+ target. The 2.5R target is not being
   earned often enough.
4. **Short-term breakout entries mean-revert.** Buying the close above the
   prior day's high and entering the next open gives up the edge and often buys
   the exhaustion bar.
5. **No market-wide filter.** The rules allow trades in a weak/choppy market as
   long as the individual stock looks strong. 2025–2026 exposed that.
6. **Sample and period.** 69 test trades is below the 100-trade floor; the
   result is not statistically strong in either direction. But the burden of
   proof is on the strategy, not on the skeptic.

## Honest limitations

- **Survivorship bias:** the NSE master is current. Delisted stocks are absent.
  This usually makes a strategy look *better*, not worse.
- **No Nifty/VIX:** no index history yet, so no market-wide regime filter.
- **No earnings dates:** an earnings event inside the 10-day hold is not
  filtered.
- **No delivery data:** delivery % is not used.
- **No BSE:** the first proof is NSE-only.
- **Daily bars only:** no intraday order, no real-time slippage.
- **Adjusted data:** corporate actions are applied, but unknown/demerger
  actions are excluded from the primary sample only when flagged; this run had
  zero such trades.
- **Costs are assumptions:** re-verify against a real contract note before any
  product claim.
- **Trade-level, not portfolio-level:** trades across different stocks can
  overlap. The R statistics are per-trade; max drawdown is trade-sequence R,
  not an account equity curve. A portfolio simulation is still needed.
- **No CPCV yet:** the summary includes a 10,000-sample trade bootstrap, but
  no combinatorial purged cross-validation. That is a later gate, not a
  substitute for a positive test period.

## Decision

**Do not build the sellable product on this strategy.** The data layer is
ready, but the first strategy has no proven out-of-sample edge. Selling it now
would be selling a backtest, not a business.

## Next options

1. **Second pre-registered setup** — test `range_breakout` or
   `rs_leader_pullback` with a benchmark series. Do not tune
   `trend_pullback` until it passes; that is curve-fitting.
2. **Market-regime overlay** — build Nifty/VIX or a breadth proxy, then test a
   pre-registered variant. This is a new hypothesis, not a rescue of the old
   result.
3. **Stop strategy work** — keep the data layer and focus on the memory/brain
   product until a strategy passes. The product can be sold only after the
   gate, legal review and data licensing.

## Reproduce

```bash
cd /storage/emulated/0/Mahvex/trading-ai
python3 tests/test_features.py
python3 tests/test_backtest_math.py
python3 jobs/backtest_trend_pullback.py \
  --signal-start 2020-01-01 --signal-end 2026-11-19 \
  --bootstrap 10000 --exit-mode levels --trail none \
  --outdir data/backtest
```

Diagnostic variants:

```bash
python3 jobs/backtest_trend_pullback.py --exit-mode time --outdir data/backtest_time
python3 jobs/backtest_trend_pullback.py --trail breakeven --outdir data/backtest_be
```
