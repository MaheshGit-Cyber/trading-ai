# Quantum Simulation Lab — Pre-registered Spec

**Status:** EXPERIMENTAL / TRAIN + VALIDATION ONLY  
**Date:** 2026-11-22  
**Job:** `jobs/quantum_simulation_lab.py`  
**Test:** `tests/test_quantum_simulation.py`  
**Frozen test:** 2024-12-11 onward is never loaded or evaluated.

## Objective

Test whether the failed strategy families can be unified by a simple
macro-regime router, without micro-parameter tuning or p-hacking.

## The 4 Anti-Overfitting Shields

### 1. Occam: three structural states

Only the Nifty 50DMA and 200DMA are used. No RSI/MA length search.

| State | Rule | Route |
|---|---|---|
| 1 Bull | Nifty > 200DMA **and** 50DMA > 200DMA | Clenow top 10 |
| 2 Sideways / transition | otherwise, with Nifty >= 200DMA | 50% NIFTYBEES + 50% LIQUIDBEES |
| 3 Crisis | Nifty < 200DMA | 50% GOLDBEES + 50% LIQUIDBEES |

Precedence is **crisis first, then bull, then sideways**. This makes the states
mutually exclusive and exhaustive. The state is computed at the signal close
and executed at the next session's open.

State 2 is a low-beta broad-index / cash anchor. It is deliberately not a
low-vol stock-selection model, which would add another fitted rule.

State 1 uses the frozen Clenow selector: point-in-time top-100-by-turnover
NSE EQ names, 90-session log-linear slope × R², close > 100DMA, top 10,
inverse-20DMA-ATR weights, 10% per-name cap. No daily 100DMA exit is added.

### 2. Walk-forward partition

| Set | Window |
|---|---|
| In-sample | 2010-01-01 .. 2018-12-31 |
| Validation (OOS1) | 2019-01-01 .. 2024-12-10 |
| Frozen test (OOS2) | 2024-12-11 onward — untouched |

The job hard-fails if `--end` is later than 2024-12-10. Nifty data is read only
through the end date; the panel and gold readers also stop at the end date.

### 3. Monte Carlo block bootstrap

- 1,000 paths.
- 6-month circular block bootstrap of OOS1 monthly net returns.
- Preserves local dependence; no IID resampling.
- Gate:
  - 5th percentile path CAGR > 0.
  - 5th percentile path max drawdown no worse than −30%.

Report the 2.5th/5th/median/95th/97.5th percentiles for CAGR and max drawdown.

### 4. Deflated Sharpe Ratio

Bailey / Lopez de Prado formula, using `jobs/deflated_sharpe.py` logic.

- Observed Sharpe: OOS1 monthly net returns.
- Trials `N = 100` by default. This is a conservative floor for the Phase 1
  pattern variants, Phase 3 sweeps, A2, and Clenow v1–v4 already evaluated.
  The true count is larger, so this is not an optimistic deflation.
- Gate: DSR >= 0.95.
- Sensitivity is reported for N = 10, 20, 50, 100.

## Cost model

The existing NSE delivery cost model in `jobs/backtest_monthly_momentum.py` is
used unchanged: STT, exchange, SEBI, stamp, DP, GST, and turnover-dependent
slippage. No 2× stress is applied in this first lab run.

## Gate

`PASS` only if all of these hold:

- OOS1 net CAGR > 0
- OOS1 net Sharpe > 0
- OOS1 max drawdown >= −30%
- Monte Carlo 5th percentile CAGR > 0
- Monte Carlo 5th percentile max drawdown >= −30%
- DSR >= 0.95

If the gate fails, the result is `FAIL`. No test-set rescue is allowed.

## Exact command

```bash
python3 jobs/quantum_simulation_lab.py \
  --trials 100 \
  --mc-paths 1000 \
  --mc-block 6 \
  --seed 42 \
  --append-bridge
```

## Known limitations

- No point-in-time F&O list, sector master, or historical market-cap.
- NIFTYBEES and LIQUIDBEES are panel series; GOLDBEES uses the split-adjusted
  gold file because the panel has a 2019 split.
- The state rule is a coarse 50/200DMA router; it cannot detect a fast crash
  between monthly rebalances.
- The lab is not a product, not advice, and not allocatable.
