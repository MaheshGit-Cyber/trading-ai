# Clenow Momentum v4 — Pre-registered Train Spec

**Status:** PRE-REGISTERED / TRAIN-ONLY  
**Date:** 2026-11-22  
**Parent spec:** `docs/clenow-momentum-spec.md`  
**Job:** `jobs/backtest_clenow_momentum.py`  
**Split:** 2024-12-10  
**Test:** not run in this step.

## Changes from v3

v4 addresses the v1–v3 train diagnostics without touching test data:

1. **Liquidity depth:** `--min-turnover 200` (₹2 crore / 200 lacs) instead of
   ₹10 crore, so 2010–2016 is not starved of eligible compounders.
2. **Wider liquid universe:** `--top-liquid 200` point-in-time liquid NSE EQ
   names instead of 100, while still selecting only the top 10 by Clenow.
3. **No daily DMA churn:** `--no-daily-dma-exit`. The 100DMA check is applied
   at the quarterly rebalance, not every day.
4. **Quarterly rank exit:** on a quarterly top-up, drop a holding if its
   close is below its 100DMA or its Clenow rank is worse than **30** among
   the point-in-time top-200 liquid names. This is the `--exit-rank 30`
   default.
5. **Regime hysteresis:** `--regime-buffer 0.02`.
   - Equities → defensive only when Nifty close < 200DMA × 0.98.
   - Defensive → equities when Nifty close > 200DMA.
   - This replaces the zero-buffer flip-flop.

## Unchanged rules

- Clenow score: 90-session log-linear slope × R², annualised.
- Entry requires adjusted close > 100DMA and Clenow score > 0.
- Top 10 names; inverse 20-session ATR weights; 10% per-name cap.
- Quarterly top-up every 63 sessions; full reconstitution every 126
  sessions; signal at close, execute next open.
- Nifty 200DMA regime into 50% GOLDBEES + 50% LIQUIDBEES.
- Full delivery costs and 2× slippage stress.
- Train gate and split are unchanged from `docs/clenow-momentum-spec.md`.

## Exact train command

```bash
python3 jobs/backtest_clenow_momentum.py \
  --phase train \
  --min-turnover 200.0 \
  --top-liquid 200 \
  --no-daily-dma-exit \
  --outdir data/backtest/clenow_momentum_v4 \
  --append-bridge
```

## Gate

Train must pass before test:

- net CAGR > 0 and > Nifty 50 TR proxy (price + 1.2%/yr)
- net Sharpe > 0.50
- max drawdown ≥ −28%
- monthly profit factor > 1.20
- 2× slippage CAGR > 0
- annual cost drag < 0.50%
- annual turnover (buy+sell) < 1.5×
- at least 12 quarterly rebalances

If train fails, the decision is `TRAIN_FAIL`; test is not run.

## Known limitations

Same as the parent spec: no point-in-time F&O list, no sector master, no
historical market-cap, GOLDBEES from the split-adjusted gold file, LIQUIDBEES
from the panel, and a high/low proxy for circuit-locked bars.
