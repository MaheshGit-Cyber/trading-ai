# Clenow Momentum — Train Results (No Test)

**Date:** 2026-11-22  
**Spec:** `docs/clenow-momentum-spec.md`  
**Job:** `jobs/backtest_clenow_momentum.py`  
**Split:** 2024-12-10  
**Decision:** **TRAIN_FAIL — do not run test, do not monetize.**

## Primary run (quarterly top-up + semi-annual full + daily 100DMA)

Command:

```bash
python3 jobs/backtest_clenow_momentum.py \
  --phase train \
  --outdir data/backtest/clenow_momentum_v3
```

Train window: first signal 2010-06-01 through 2024-12-10. 57 quarterly
signals. 10 names. Nifty 50 200DMA overlay into 50% GOLDBEES + 50%
LIQUIDBEES.

| Metric | Strategy | Nifty 50 B&H | Nifty TR proxy |
|---|---:|---:|---:|
| Net CAGR | **9.67%** | 11.57% | 12.91% |
| Net Sharpe | **0.61** | — | — |
| Max drawdown | **−36.27%** | −38.44% | — |
| Profit factor (monthly) | **1.59** | — | — |
| Annual cost drag | **1.19%** | — | — |
| Annual turnover (buy+sell) | **5.56×** | — | — |
| 2× slippage CAGR | **9.11%** | — | — |
| Rebalances | 57 | — | — |

### Gate

`TRAIN_FAIL`. Failed conditions:

- Net CAGR does not beat the Nifty 50 TR proxy (9.67% vs 12.91%).
- Max drawdown is worse than −28% (−36.27%).
- Cost drag is above 0.50%/yr (1.19%).
- Turnover is above 1.5×/yr (5.56× total, 2.78× one-way).

The strategy passes the CAGR-positive, Sharpe > 0.5, profit-factor, 2×
slippage, and 12-rebalance conditions.

## Diagnostics (train only, not used to select a test rule)

| Variant | Net CAGR | Sharpe | Max DD | Cost drag | Turnover | 2× CAGR |
|---|---:|---:|---:|---:|---:|---:|
| Quarterly full + daily 100DMA | 8.70% | 0.56 | −33.93% | 1.31% | 6.09× | 8.09% |
| Quarterly top-up + semi-annual full, rebalance-only 100DMA | 6.41% | 0.40 | −49.45% | 1.15% | 5.31× | 5.84% |
| Semi-annual full + daily 100DMA | 7.97% | 0.57 | −27.44% | 0.68% | 3.16× | 7.62% |
| Semi-annual full, rebalance-only 100DMA | 10.17% | 0.56 | −43.67% | 0.66% | 3.07× | 9.82% |

## Interpretation

- The Clenow score alone does not beat the Nifty 50 TR proxy over the train
  window.
- The 100DMA daily exit and the 200DMA regime switches are the main turnover
  drivers. Removing the daily exit lowers cost drag but raises drawdown.
- Even the lowest-turnover diagnostic is above the 1.5× total-turnover gate
  and above the 0.50%/yr cost gate. One-way turnover for the semi-annual
  no-daily variant is ~1.53×, close to the target, but the portfolio still
  fails the return and drawdown conditions.
- The 50/50 GOLDBEES + LIQUIDBEES overlay did not prevent the 2025–2026
  whipsaw problem in A2; the same regime logic remains a structural risk.

## Next

- Do not touch test data.
- Do not monetize or build UI/Telegram/app from this result.
- If this line is continued, the next pre-registered variant must reduce
  turnover structurally (for example, no daily 100DMA exit, semi-annual
  reconstitution, and a regime buffer) and be judged on train first.
- Otherwise, stop strategy research and move to the non-advisory product
  path.

---

## v4 Train Result (2026-11-22)

Pre-registration: `docs/clenow-momentum-v4-spec.md`.

Command:

```bash
python3 jobs/backtest_clenow_momentum.py \
  --phase train \
  --min-turnover 200.0 \
  --top-liquid 200 \
  --no-daily-dma-exit \
  --outdir data/backtest/clenow_momentum_v4 \
  --append-bridge
```

v4 changes: ₹2 crore liquidity floor, top-200 liquid universe, no daily
100DMA exit, quarterly top-up with a top-30 Clenow rank exit, semi-annual full
reconstitution, and 2% 200DMA hysteresis.

| Metric | Strategy | Nifty 50 B&H | Nifty TR proxy |
|---|---:|---:|---:|
| Net CAGR | **6.29%** | 11.57% | 12.91% |
| Sharpe | **0.38** | 0.76 | — |
| Max drawdown | **−57.86%** | −38.44% | — |
| Profit factor | **1.33** | 1.77 | — |
| Cost drag | **1.47%/yr** | — | — |
| Turnover | **6.11×/yr** | — | — |
| 2× slippage CAGR | **5.43%** | — | — |
| Rebalances | 57 | — | — |

**Gate: `TRAIN_FAIL`.** Failed: beats Nifty TR, Sharpe > 0.50, max DD ≥
−28%, cost drag < 0.50%/yr, turnover < 1.5×/yr. Test was not run.

### v4 interpretation

- The wider universe fixed the 2010–2015 eligibility starvation, but the
  extra depth did not produce alpha: CAGR fell and drawdown widened.
- Removing the daily 100DMA exit reduced reaction speed; the −57.86% drawdown
  is worse than every v3 diagnostic.
- Turnover and cost drag remain above target because semi-annual full
  reconstitution, top-up replacements, and regime switches still trade too
  much.
- The 2% hysteresis buffer alone does not solve the regime whipsaw.

---

## Final Strategy Closure (2026-11-22)

**Status:** strategy research line closed. No test run, no live runner, no
monetization from these results.

### Registry lock

`brain/contracts.py` is now a read-only `ENGINE_REGISTRY`:

- `a2_momentum` — `FAILED`, CAGR −2.06%, max DD −15.33%,
  note: “Failed 5/11 stable gates. Do not tune or allocate.”
- `clenow_momentum_semiannual` — `RESEARCH_ONLY`, CAGR 10.17%,
  max DD −27.44%, Calmar 0.3706, note: “Semi-annual 6-month Top 100
  Clenow momentum with Gold BeES shield. Delivered +13% in 2020 COVID
  and +76% in 2021. Research-only sleeve.”

Neither engine is allocatable. The allocator refuses both.

### Year-by-year returns (train, net of costs)

Source: `data/backtest/clenow_momentum` — the quarterly-full + daily-100DMA
variant that produced the closure directive’s yearly figures.

| Year | Return |
|---|---:|
| 2010 | −3.53% |
| 2011 | +7.85% |
| 2012 | +9.97% |
| 2013 | −21.77% |
| 2014 | +48.43% |
| 2015 | −11.03% |
| 2016 | +27.44% |
| 2017 | +18.79% |
| 2018 | −7.17% |
| 2019 | −7.25% |
| 2020 | +13.04% |
| 2021 | +76.76% |
| 2022 | −14.62% |
| 2023 | +22.20% |
| 2024 | +4.19% |

This run has 9 positive and 6 negative calendar years. The “10 positive
years” wording in the closure directive is not reproduced by this table.

### Final semi-annual variant

The final architecture is the semi-annual (6-month) full reconstitution with
the Nifty 200DMA → 50% GOLDBEES + 50% LIQUIDBEES shield. Two train variants
were measured:

| Variant | CAGR | Max DD | Cost drag | Turnover | 2× CAGR |
|---|---:|---:|---:|---:|---:|
| Semi-annual full + daily 100DMA | 7.97% | −27.44% | 0.68% | 3.16× | 7.62% |
| Semi-annual full, rebalance-only 100DMA | 10.17% | −43.67% | 0.66% | 3.07× | 9.82% |

**Conclusion:** the daily-100DMA semi-annual variant passes the −28% drawdown
gate but fails the Nifty TR return, cost-drag, and turnover gates. The
no-daily variant improves CAGR but breaches the drawdown gate. Neither is
approved for allocation or monetization.

### Metric provenance note

The registry closure metrics (CAGR 10.17%, max DD −27.44%, Calmar 0.3706) are
the operator-approved 2026-11-22 directive values. They are not from a single
backtest: 10.17% is the no-daily semi-annual CAGR, while −27.44% is the
daily-100DMA semi-annual max drawdown. The year-by-year table above is from the
quarterly-full + daily-100DMA run. This is disclosed rather than hidden.

### What was not done

- Test split (2024-12-11 onward) was not loaded or evaluated.
- No live runner, broker adapter, UI, website, app, or Telegram bot was built.
- No engine was promoted to `APPROVED` or made allocatable.
