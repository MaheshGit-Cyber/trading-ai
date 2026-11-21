# Quantum Simulation Lab — Results

**Date:** 2026-11-22  
**Spec:** `docs/quantum-simulation-lab-spec.md`  
**Job:** `jobs/quantum_simulation_lab.py`  
**Output:** `data/backtest/quantum_simulation_lab/`  
**Decision:** `FAIL` (3 of 6 gate conditions failed)  
**Frozen test:** 2024-12-11 onward was not loaded or evaluated.

## Command

```bash
python3 jobs/quantum_simulation_lab.py \
  --trials 100 \
  --mc-paths 1000 \
  --mc-block 6 \
  --seed 42 \
  --append-bridge
```

## Run shape

- Monthly signal / next-open execution, 170 rebalances.
- State counts: **Bull 110**, **Sideways 17**, **Crisis 43**.
- State 1: frozen Clenow top-10 selector.
- State 2: 50% NIFTYBEES + 50% LIQUIDBEES.
- State 3: 50% GOLDBEES + 50% LIQUIDBEES.
- 403 stock IDs loaded plus the three ETFs.
- Full-period turnover: **12.27×/yr**.
- Full-period cost drag: **2.69%/yr**.
- 1,925 trades; 3 stale writeoffs (0.19% of capital).

## Walk-forward (net of costs)

| Period | CAGR | Sharpe | Max DD |
|---|---:|---:|---:|
| IS 2010–2018 | **−5.11%** | −0.12 | −50.65% |
| OOS1 2019–2024-12-10 | **19.64%** | 0.92 | −25.53% |
| Full 2010–2024-12-10 | **4.59%** | 0.32 | −58.86% |
| Nifty 50 OOS1 | 14.89% | 0.86 | −38.44% |

The validation window looks strong, but the in-sample window is negative and the
full-period drawdown is −58.86%. That is not a stable all-weather result.

## Monte Carlo (1,000 block-bootstrap paths)

OOS1 monthly net returns, 6-month circular blocks.

| Statistic | CAGR | Max DD |
|---|---:|---:|
| 2.5th percentile | −3.73% | −49.39% |
| **5th percentile** | **−0.02%** | **−45.54%** |
| Median | 18.67% | −27.50% |
| 95th percentile | 45.35% | −15.17% |
| 97.5th percentile | 50.18% | −13.44% |

The 5th percentile CAGR is essentially zero (slightly negative), and the 5th
percentile max drawdown is −45.54%. The MC shield fails both conditions.

## Deflated Sharpe Ratio

| Item | Value |
|---|---:|
| OOS1 monthly Sharpe | 0.2691 |
| OOS1 annual Sharpe | 0.93 |
| Trials N | 100 |
| **DSR** | **0.4265** |
| Full-period DSR | 0.0876 |

DSR sensitivity for OOS1:

| Trials | DSR |
|---:|---:|
| 10 | 0.7795 |
| 20 | 0.6717 |
| 50 | 0.5275 |
| 100 | 0.4265 |

Even at N=10 the DSR is below 0.95. The result is not strong enough to rule out
statistical luck after the number of trials already spent on this research line.

## Gate

| Condition | Result |
|---|---|
| OOS1 net CAGR > 0 | PASS (19.64%) |
| OOS1 net Sharpe > 0 | PASS (0.92) |
| OOS1 max DD ≥ −30% | PASS (−25.53%) |
| MC 5th percentile CAGR > 0 | **FAIL** (−0.02%) |
| MC 5th percentile max DD ≥ −30% | **FAIL** (−45.54%) |
| DSR ≥ 0.95 | **FAIL** (0.4265) |

**Decision: `FAIL`.**

## Interpretation

- The 3-state router produced a strong 2019–2024 validation window, but it did
  not survive the Monte Carlo or deflated-Sharpe shields.
- The in-sample 2010–2018 period lost money; the full-period result is only
  4.59% CAGR with a −58.86% drawdown. This is regime-dependent, not robust.
- Turnover is very high (12.27×/yr) because the monthly router re-selects
  Clenow names and switches ETFs. Cost drag is 2.69%/yr, far above the Clenow
  cost target.
- The 5th-percentile max drawdown of −45.54% breaches the −30% risk gate.
- No test-set run, no tuning on OOS1, and no monetization or UI work follows
  from this result.

## Next

This experimental line is closed at `FAIL` unless a new pre-registered
architecture is explicitly requested. Do not tune the state thresholds, block
size, or trial count on these results.
