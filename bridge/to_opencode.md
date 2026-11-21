# Antigravity -> OpenCode: Quantum Simulation Lab (Anti-Overfitting Architecture)

**Timestamp:** 2026-11-22T02:12+05:30  
**Status:** ACTIVE SPECIFICATION & EXPERIMENTAL LAB DIRECTIVE

Operator Mahesh has approved running the advanced multi-dimensional simulation, with a **non-negotiable mandate: Zero Curve-Fitting / P-Hacking**.

The objective is to test whether the failed strategies (Phase 1, Phase 3, A2) can be dynamically unified into a single robust engine using **Macro-Regime Switching + Monte Carlo Stress Testing**, without overfitting to past noise.

---

### The 4 Anti-Overfitting Shields (Mathematical Armor)

1. **Occam’s Razor (Strictly Minimal Parameters):**
   - Zero micro-parameter tweaking (no RSI 14 vs 15, no MA 19 vs 21).
   - Only 3 structural macro states derived from Nifty:
     - **State 1 (Bull Trend):** Nifty > 200DMA & 50DMA > 200DMA ➡️ Route to Clenow Momentum / Alpha.
     - **State 2 (Sideways / Mean-Reverting):** Nifty between 50DMA & 200DMA ➡️ Route to Low-Vol / Cash Anchor.
     - **State 3 (Structural Crisis):** Nifty < 200DMA ➡️ Route to 50% Gold BeES + 50% Liquid BeES.

2. **Walk-Forward Out-of-Sample Partitioning:**
   - **Optimization Set (In-Sample):** 2010–2018.
   - **Validation Set (Out-of-Sample 1):** 2019–2024-12-10 (includes 2020 COVID crash, 2021 bull run, 2022 inflation).
   - **Frozen Test Set (Out-of-Sample 2):** 2024-12-11 to present (STRICTLY UNTOUCHED).

3. **Monte Carlo 1,000-Path Permutation Stress Test:**
   - Block bootstrap and reshuffle trade return sequences across 1,000 simulated parallel market worlds.
   - The strategy must demonstrate that its 5th percentile worst-case path maintains positive equity growth and Max Drawdown $\le -30\%$.

4. **Deflated Sharpe Ratio (DSR) Penalty (Marcos Lopez de Prado Formula):**
   - Penalize the observed Sharpe ratio using `jobs/deflated_sharpe.py` logic based on the number of trials ($N$) evaluated:
     $$DSR = \Phi\left(\frac{(SR - SR_0)\sqrt{T-1}}{\sqrt{1 - \hat{\gamma}_3 SR + \frac{\hat{\gamma}_4 - 1}{4}SR^2}}\right)$$
   - Must achieve $DSR \ge 0.95$ (less than 5% probability that the result is pure statistical luck/curve-fitting).

---

### Implementation Task for OpenCode (`jobs/quantum_simulation_lab.py`)

1. Build `jobs/quantum_simulation_lab.py` adhering strictly to the 4 Anti-Overfitting Shields.
2. Simulate the 3-State Regime Switching engine on the 2010–2024-12-10 train/validation split.
3. Compute and output:
   - Walk-Forward Net CAGR, Net Sharpe, and Max Drawdown.
   - Monte Carlo 1,000-path 95% Confidence Interval (Worst-case DD, Median CAGR).
   - Deflated Sharpe Ratio (DSR).
4. Run `python3 tests/test_quantum_simulation.py` to ensure unit test coverage and report findings to `bridge/to_antigravity.md`.
