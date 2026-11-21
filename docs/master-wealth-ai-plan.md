# Master Wealth & Trading AI — Architectural Specification & Data Blueprint

**Date:** 2026-11-21  
**Author:** Antigravity (Auditor & Architect)  
**Operator:** Mahesh  
**Target Platform:** Autonomous Multi-Asset Wealth & Trading Engine  
**Execution Agent:** OpenCode  

---

> **Execution status (2026-11-21):** Phase 2B monthly momentum failed
> (`docs/phase2b-results.md`: max DD −49.75%), Phase 3 large-cap mean reversion
> failed (`docs/phase3-results.md`: net CAGR −4.32%, max DD −66.62%), and
> Phase 4 all-weather multi-asset failed its approved gate
> (`docs/phase4-results.md`: net CAGR 11.72%, max DD −23.18%, Calmar 0.51,
> 2026 −3.27%). Phase 4B dynamic trend de-risking met the drawdown gate
> (`docs/phase4b-results.md`: max DD −14.62%) but failed return, Calmar, and
> 2026: CAGR 11.08%, Calmar 0.76, 2026 −8.64%. Its 45% gold de-risking sleeve
> bought gold near the 2026 peak and crashed with it. Do not tune Phase 4 or
> Phase 4B. No product claim is approved yet. Phase 5 brain core is implemented:
> `brain/contracts.py`, `brain/data.py`, `brain/scorer.py` provide a deterministic
> M-score (no D/V, because the panel has no fundamentals); `brain/risk_guard.py`
> sizes/blocks trades; `brain/allocator.py` refuses failed/research-only engines
> and allocates Engine 1 only; `brain/llm_bridge.py` formats English/Teluglish
> briefs without inventing numbers. Phase 2 momentum is research-only and is not
> allocatable. See `docs/phase5-brain-scorer.md` and
> `docs/phase5-brain-risk-allocator.md`. A SQLite byte-offset index
> (`data/brain/panel_index.sqlite`, 743 MB) cuts a single-stock query from
> ~1m26s to ~0.3s; rebuild with `jobs/build_brain_panel_index.py --force`
> after a panel refresh. An internal paper ledger is active
> (`brain/paper.py`, `jobs/paper_snapshot.py`,
> `jobs/update_nifty_from_yahoo.py`): baseline 2026-11-19 and first forward
> session 2026-11-20 are recorded. The 2–3 month clock started 2026-11-20,
> but two snapshots are not evidence. Next: run the daily refresh and
> snapshots through ~2027-02, then legal/SEBI and data licensing, before any
> UI or launch claim. See `docs/phase5-paper-trading.md`. Phase 6 research
> agent powers are now implemented in `agent/`: live IST clock/calendar,
> safe web/news research, fake-news credibility risk scoring (not a truth
> oracle), append-only research memory, a pre-registered strategy lab with
> frozen gates, and a paper-book report. The agent is research-only: no
> order, real-money, self-promotion or risk-gate bypass authority. See
> `docs/phase6-agent-research.md`.

---

## 1. Executive Summary & Vision

The objective is to build a commercial, subscription-grade (₹999/month target) AI Wealth & Trading Platform ("motham dabbu ni mana ai nadapali"). Retail users range from conservative salaried employees doing ₹1,000 monthly SIPs to aggressive intraday and crypto traders.

To ensure long-term retention and zero capital blowup, the system provides an **Institutional-Grade Analytical Brain** that evaluates every asset class mathematically, enforces risk control, and routes capital according to user risk profile and market regime.

---

## 2. The 5 Core Asset Pillars

| # | Asset Class | Instrument Focus | Role in Portfolio | Ingestion Source |
|---|---|---|---|---|
| **1** | **Indian Equities & Momentum** | NSE EQ Top 200, Mid/Small Leaders | High Capital Growth (18–35% CAGR) | NSE Official Bhavcopy Archives (2010–2026) |
| **2** | **Mutual Funds & SIPs** | Nifty 50 Index, Flexi-cap, Smallcap Funds | Stress-free Compounder for Retail | AMFI Daily NAV Official Feed (2006–2026) |
| **3** | **Gold & SGBs** | Nippon Gold BeES, Sovereign Gold Bonds | Crisis Shield & Currency Hedge | NSE ETF Bhavcopy & RBI SGB Issue Archives |
| **4** | **Govt Bonds & Debt** | 10-Yr Benchmark G-Sec, 91-Day T-Bills | 100% Capital Preservation & Yield | RBI DBIE Yield Data |
| **5** | **Crypto Assets** | BTC/USDT, ETH/USDT, USDT (USD Hedge) | 24/7 Global Alpha & Dollar Reserve | Binance Official REST API (2017–2026) |

---

## 3. The 4 User Archetypes & Engine Routing

```
                          ┌────────────────────────┐
                          │   USER QUERY / LOGIN   │
                          └───────────┬────────────┘
                                      │
                         [Risk Profiling & Intent]
                                      │
         ┌───────────────────┬────────┴───────────┬───────────────────┐
         ▼                   ▼                    ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Profile 1:       │ │ Profile 2:       │ │ Profile 3:       │ │ Profile 4:       │
│ Passive Builder  │ │ Monthly Momentum │ │ Weekly Swing     │ │ Intraday/Options │
│ (SIP / All-      │ │ Compounder       │ │ Breakout Trader  │ │ & Crypto 24/7    │
│  Weather Wealth) │ │ (Phase 2 Focus)  │ │ (Institutional)  │ │ (High Velocity)  │
└──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Profile 1: Passive Builder (SIP / All-Weather Engine)
* **Capital:** ₹1,000/mo to ₹50,000/mo.
* **Allocation Model:**
  * 50% Equity Index Funds (Nifty 50 / LargeMid 250)
  * 20% Gold BeES (Crisis hedge)
  * 20% Govt G-Sec / Liquid Debt (Safe interest)
  * 10% Cash / Crypto BTC (Optional growth booster)
* **Auto-Rebalancing:** Semi-annual rebalancing. When equity crashes >15%, debt is harvested to buy equity at discounts.
* **Status (2026-11-21):** Phase 4 static failed (<18% DD, >12–15% CAGR,
  >0.80 Calmar): 11.72% CAGR, −23.18% DD, 0.51 Calmar. Phase 4B trend
  de-risking met DD (−14.62%) but failed CAGR/Calmar/2026: 11.08%, 0.76,
  −8.64%. Not approved for product. See `docs/phase4-results.md` and
  `docs/phase4b-results.md`.

### Profile 2: Smart Compounder (Monthly Momentum Rotation — Research Only)
* **Status (2026-11-21):** Phase 2B failed the drawdown gate: 19.97% CAGR,
  −49.75% max DD. Do not tune it and do not allocate users to it. A new
  risk-managed momentum family requires a fresh pre-registration and approval.
* **Capital (research only):** ₹1 Lakh to ₹50 Lakhs.
* **Cadence:** Once per month (rebalance on the first trading session).
* **Strategy:** Top 10 relative-strength leaders (composite 63-day + 126-day
  excess vs Nifty), 10% equal weight, 5% ADV cap.
* **Friction:** The unconstrained version still produced a −49.75% drawdown;
  cost drag is not the binding problem.

### Profile 3: Active Swing Breakout Trader (Institutional Accumulation)
* **Capital:** ₹50,000 to ₹5 Lakhs.
* **Cadence:** 3 to 10 trading sessions hold.
* **Rules:**
  * Proof of Delivery Spike (Delivery volume > 200% of 20-day average).
  * 1:2 to 1:3 Risk-to-Reward minimum.
  * Stop-loss enforced strictly at swing low / 1 ATR.

### Profile 4: Intraday, Options & Crypto 24/7 Specialist
* **Capital:** High-risk discretionary funds.
* **Equities/Derivatives:** Pre-market 8:45 AM briefing (GIFT Nifty, Global Cues), Option Chain PCR, Max Pain, Volatility Breakout.
* **Crypto (BTC/ETH):** 24/7 Trend Following via ATR channel breakout & funding rate arbitrage.
* **Risk Gate:** Maximum 1.5% to 2.0% total portfolio risk per single trade.

---

## 4. Data Repository Blueprint

```
trading-ai/data/
├── raw/                              # Daily NSE Bhavcopies 2010–2026 (Continuous)
│   ├── bhavcopy_2010-01-04.csv
│   └── ...
├── index/                            # Historical Index benchmarks
│   ├── nifty50.csv                   # Clean official Nifty 50 (2018–2026)
│   └── nifty50_2010_2026.csv         # Full 16-year Nifty daily closes
├── corporate_actions/                # Splits, bonuses, face-value adjustments
│   └── actions.csv                   # Historical actions 2010–2026
├── crypto/                           # 24/7 Crypto Daily & Hourly Data
│   ├── btcusdt_daily_2017_2026.csv   # 3,383 bars (Clean Binance official feed)
│   └── ethusdt_daily_2017_2026.csv   # 3,383 bars (Clean Binance official feed)
├── mutual_funds/                     # AMFI Official Daily NAVs (to be ingested)
│   └── nav_history.csv
└── macro_debt/                       # RBI 10Y G-Sec & T-Bill yields
    └── gsec_10y_daily.csv
```

---

## 5. Decision Engine Modules (`brain/` Architecture)

1. **`brain/allocator.py` — Multi-Asset Allocator:**
   * Computes risk parity and modern portfolio allocation across Stocks, Mutual Funds, Gold, and Crypto based on user risk score (1 to 10).

2. **`brain/scorer.py` — Universal Asset Scorer ("Ask My Stock"):**
   * Computes a multi-factor score (0 to 100) for any stock or asset:
     * Trend & 200DMA Alignment (30 pts)
     * Relative Strength vs Nifty / Sector (30 pts)
     * Institutional Delivery & Volume (20 pts)
     * Volatility & Downside Risk (20 pts)
   * Answers user questions with institutional facts instead of guesswork.

3. **`brain/risk_guard.py` — Devil's Advocate Engine:**
   * Calculates exact position size based on user capital and stop-loss distance.
   * Blocks trades in circuit-locked stocks or low-liquidity illiquid names.

---

## 6. Phased Implementation Plan for OpenCode

* **Step 1 (Immediate):**
  * Complete 2010–2019 Bhavcopy backfill.
  * Execute Phase 2B (2010–2026 16-Year Monthly Momentum Backtest).
* **Step 2 (Data Ingestion Pipeline):**
  * Crypto data already fetched in `data/crypto/` (`fetch_crypto.py`).
  * Add AMFI NAV ingestion job (`jobs/fetch_amfi_nav.py`).
* **Step 3 (Engine Integration):**
  * Connect `brain/scorer.py` to both NSE Bhavcopy panel and Crypto CSVs.
* **Step 4 (User Interface Layer):**
  * Build CLI/API endpoint to query any asset score or generate rebalance orders.
