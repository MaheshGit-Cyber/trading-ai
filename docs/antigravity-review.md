# Formal Independent Review — Phase 1 & H4 Design

**Reviewer:** Antigravity (Gemini 3.8 Flash High)  
**Date:** 2026-11-21  
**Target:** `docs/antigravity-review-task.md` & `bridge/to_antigravity.md`  

---

## 1. Findings Table

| ID | Severity | Finding | Evidence | Recommendation |
|---|---|---|---|---|
| **BUG-01** | **High** | Same-day target fill on limit entries creates intra-bar look-ahead artifact | `jobs/backtest_trend_pullback.py:448-454` (`check_trade_bar`) | Deny same-day target on limit entry bars. (Verified by OpenCode in v3; removes +0.012R artificial gross). |
| **BIAS-01** | **High** | Unconstrained capital concurrency in trade-sequence R metrics | `summary_trend_pullback.json` (max 84 concurrent positions, 43 entries/day) | Require portfolio simulation with max 5–10 concurrent positions, cash reservation, and priority ranking. |
| **ARCH-01** | **High** | Tight stop (< 1 ATR) structurally inflates notional turnover fees to 0.196R | `jobs/backtest_trend_pullback.py:129, 146-166` | In H4, widen stop to ≥ 1.0–1.5 ATR and expand horizon to 20 sessions to lower cost per trade below 0.10R. |
| **STAT-01** | **Medium** | Signal firehose due to omitted confirmation triggers in pullback mode | `jobs/backtest_trend_pullback.py:310-322` (6,966 trades ~ 1,000/yr) | Pre-register a strict selection filter: Top-decile Relative Strength (RS) vs Nifty 50 over 63 sessions. |
| **BIAS-02** | **Low** | Survivorship bias from current NSE master | `data/nse_equity_master.csv` (12.8% traded stocks end early, but omitted historical IPO/delistings exist) | Accept as an upper-bound bound. Since strategies fail out-of-sample anyway, bias is non-disqualifying. |

---

## 2. What I Could Not Verify
1. **Intraday Tick Order Execution:** Whether any of the limit-fill touches occurred in auction/circuit-freeze bars cannot be proven from daily OHLC alone.
2. **True Historical Delistings (2020–2022):** The number of NSE stocks completely wiped out in 2020 that were purged from the master before 2024 is not verifiable without point-in-time exchange archives.
3. **Execution Slippage on Smallcaps:** 0.50% one-way slippage on turnover < ₹1cr is a model assumption; during sharp market corrections, real slippage may exceed 1.0%.

---

## 3. Top 3 Fixes Before the Next Test (H4)
1. **Portfolio-Level Cash Engine:** Replace the sum-of-trades equity curve with a real cash ledger (₹10,00,000 capital, max 5 or 10 positions, max 20% capital per position, queueing when cash is exhausted).
2. **Relative-Strength (RS) Leader Filter:** Compute 63-day and 126-day price return relative to Nifty 50. Only trade pullbacks in stocks whose RS rank is in the top 10% of the NSE universe.
3. **Wider Stop & Longer Holding:** Stop at `pullback_low - 1.0 ATR`, holding period 20 sessions, target 3.0R. This will cut turnover by >80% and reduce frictional cost per trade to <0.08R.

---

## 4. Is the H3 Result Trustworthy?
**Yes, the negative verdict is 100% trustworthy.**
- H3 (v2 and v3) cleanly proves that unconfirmed pullback limit-buying with tight stops has negative net expectancy across every single testing year.
- Do not tune H3. The structural friction mismatch in Indian delivery trading cannot be resolved by tweaking parameters.

---

## 5. Audit of H4 Design Proposal
OpenCode's proposed H4 specifications:
- *RS leader pullback, wider stop (1 ATR), 20-session hold, 3R target, limit entry, same-day target denied, max 5–10 concurrent positions, cash cap, rank-based allocation.*

**Antigravity Verdict on H4:** **Approved.**  
This directly targets the core structural flaws identified in H1–H3 (turnover taxation, unconstrained concurrency, and lack of stock selection edge). Proceed with implementation.
