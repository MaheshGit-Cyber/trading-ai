# Independent External Review Response — Phase 1 Trading Strategy

**Reviewer:** Antigravity (Gemini 3.8 Flash High)  
**Date:** 2026-11-21  
**Target:** `trading-ai/docs/external-review-prompt.md`  
**Verdict:** **Audit complete. Concur with OpenCode: H2 and H3 are definitive failures. Do not optimize parameters.**

---

### 1. Look-ahead bias: Low / Clean (Minor Intra-bar Caveat)
- **Signal Generation (`signal_from_bar`, L274-360):** Clean. All features (`dma`, `atr`, `rsi`, `vol20`, `recent`) use `state.bars` strictly up to the current day's close.
- **Limit Entry Path (L660-674):** If `bar.open <= limit_price`, fills at `bar.open`. Else if `bar.low <= limit_price`, fills at `limit_price`. This correctly mimics a GTC/day limit order placed prior to market open.
- **Caveat (Intra-bar Same-Day Target Fill, L676-688):** If a limit order fills during the day (`bar.open > limit` and `bar.low <= limit`), and the bar also touches target (`bar.high >= target` while `bar.low > stop`), the engine awards `target_same_day`. On daily bars, there is no proof that `high` occurred after the limit fill (the high could have occurred at 9:30 AM and the limit fill at 2:30 PM). This creates a minor optimistic intra-bar bias for same-day target hits.

---

### 2. Survivorship Bias: Moderate to High Positive Bias
- The universe is derived from current `data/nse_equity_master.csv`. Companies suspended, liquidated, or delisted between 2020 and 2026 are omitted.
- **Impact:** Survivorship bias almost always inflates returns (+0.05R to +0.20R). The fact that H2 and H3 **still fail with negative net expectancy despite survivorship bias** proves that the underlying edge is deeply negative in the real world.

---

### 3. Corporate-Action Adjustment: Sound Architecture
- Backward adjustment via cumulative product is standard quant methodology and does not leak future price levels into indicator thresholds because normalized returns are preserved.
- **Dividends:** Omitted. For a 10-session swing horizon, unadjusted cash dividends (~0.2% to 1.5% annually, ex-date once/twice a year) are immaterial to the negative expectancy.

---

### 4. Cost Model: Accurate Math Explains the 0.196R Cost Explosion
- **Tax & Fee Schedule:** STT (0.1% buy + 0.1% sell), Exchange (0.00297%), SEBI (0.0001%), Stamp (0.015%), GST (18%), DP charge (₹13.5), and turnover-tiered slippage match Budget 2026 delivery reality.
- **Why H3 Cost jumped to 0.196R (from 0.113R):**
  - Baseline risk was ~1.5 ATR. H3 tightened stop to `pullback_low - 0.5 ATR` and limit entry to `pullback_low + 0.25 ATR` (risk per share = ~0.75 ATR).
  - Risk per share halved $\rightarrow$ Position size (quantity) doubled $\rightarrow$ Notional position value doubled $\rightarrow$ Turnover taxes doubled.
  - Since $Cost_R = \frac{\text{Total Turnover Fees}}{\text{Fixed Capital Risk}}$, doubling notional turnover doubled $Cost_R$ to **0.196R**.
  - **Verdict:** 0.196R is mathematically inevitable for tight-stop equity delivery in India.

---

### 5. Stop-First Assumption: Highly Conservative & Correct
- Lines 448 & 463: When both stop and target are touched within the same daily OHLC bar, the simulator assumes `stop first`.
- This is the gold-standard conservative assumption in daily bar backtesting, preventing illusory target fills.

---

### 6. Multiple Testing: Clean Gate Integrity
- Counting H2 and H3 as explicit distinct trials preserves experimental integrity.
- Because both trials failed resoundingly across out-of-sample periods, Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO) corrections are unnecessary to reject the null hypothesis. The null hypothesis stands: there is no edge.

---

### 7. Trade Count Explosion (6,966 trades ~ 1,000/year): Signal Filter Omission
- **Root Cause:** In baseline (`breakout`), signals required:
  1. `close > prior_day_high`
  2. `volume >= 1.3 * vol20`
  3. `close > dma20`
- In H3 (`pullback`), these 3 restrictive confirmation filters were removed. It merely asked: "Is the stock in a pullback from a 15-day high with RSI 40-65?"
- Across 2,000 NSE stocks in a secular bull market, dozens of stocks satisfy this loose condition daily. Without a volume or price reversal confirmation trigger, it became an unconstrained firehose.

---

### 8. Gross Edge (+0.045R): Economically Meaningless
- Pullback limit buying provides liquidity on dips, naturally capturing a tiny bid-ask/dip bounce (+0.045R).
- However, against a 0.196R tax/friction hurdle, a +0.045R gross edge is commercially unviable (net deficit of -0.151R).

---

### 9. What Must Be Fixed Before Trusting Any Future Strategy Result
1. **Portfolio-Level Capital Simulation:**
   - 6,966 trades cannot be executed simultaneously with a 25% capital allocation cap. When 50 stocks trigger on Monday, an account can only take 4 positions. A realistic portfolio simulation with cash constraints and rank-based allocation is required.
2. **Disallow Same-Day Limit Entry + Target Fill:**
   - On the bar of a limit entry fill, exit should only evaluate stop, not same-day target, unless tick/intraday timestamp data verifies ordering.

---

### 10. Single Most Likely Reason the Strategy Fails
> **The Structural Mismatch Between High-Friction Equity Delivery Taxes and Short-Horizon Mean Reversion.**
>
> Indian Cash Delivery trading has a mandatory ~0.25% - 0.40% round-trip tax/slippage friction. When using tight stops (0.75 ATR) on a 10-day swing, friction consumes 20% of your risk unit on EVERY trade. A short-term mean-reversion setup on unconfirmed pullbacks simply cannot generate the > +0.25R gross edge needed to clear Indian delivery friction.
