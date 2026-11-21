# Phase 5 — Risk Guard, Allocator, and Formatting Bridge

**Status:** Implemented (brain core, no UI, no execution).
**Date:** 2026-11-21
**Modules:** `brain/risk_guard.py`, `brain/allocator.py`, `brain/llm_bridge.py`
**Tests:** `tests/test_brain_risk_guard.py` (12), `tests/test_brain_allocator.py`
(11), `tests/test_brain_llm_bridge.py` (9), `tests/test_brain_panel_index.py`
(4), `tests/test_brain_paper.py` (4), plus 8 scorer tests.

> This is a signal-only decision-support layer. It does not place orders, does
> not promise profit, and does not turn a conditional engine into a guaranteed
> product.

## 1. Risk guard

### Position sizing

Default limits:

| Limit | Default |
|---|---:|
| Risk per trade | 1.0% of capital (hard max 2%) |
| Single position | 20% of capital |
| 20D ADV participation | 5% of average daily value |
| Minimum 20D ADV | ₹1 crore |
| Stale-data block | more than 3 calendar days |
| Corporate-action window | 10 calendar days |

The size is the **minimum** of:

1. risk-budget quantity = `capital × risk% ÷ (entry − stop)`
2. position-cap quantity = `capital × 20% ÷ entry`
3. ADV-cap quantity = `20D ADV × 5% ÷ entry`

The result is rounded down to the lot size. The output states which cap bound.
If any cap gives zero, `size_zero` is a block.

Example: ₹10,00,000 capital, RELIANCE entry ₹1,375.60, stop ₹1,306.82,
1% risk, 20% position cap, live 20D ADV. Result: **145 shares, ₹1,99,462
value, ₹9,973 risk (1.00%)**, binding cap = risk. This is a plan, not an order.

### Hard blocks

- no bars at/before `as_of`
- stale data beyond the limit
- zero/missing ADV, ADV below ₹1 crore
- zero-volume bar
- high == low (locked/illiquid proxy)
- corporate action inside the window:
  - **block:** split, bonus, rights, other corporate action
  - **warn:** AGM, EGM, dividend, buyback, interest
- zero position after caps

### Circuit limitation

The NSE panel has no exchange circuit flag. The guard therefore treats
`high == low` as a locked-circuit proxy and a ≥9.5% close-to-close move as a
near-circuit warning. It can over-block an illiquid stock; it cannot reliably
distinguish a real exchange circuit from a one-price day. A licensed feed with
the official circuit/ban flag is required before claiming exact circuit
coverage.

## 2. Allocator

### Engine governance

Only `all_weather_defender` (Phase 4B) is enabled. The allocator checks
`ENGINE_REGISTRY` and refuses:

- `momentum_alpha` — research-only, −49.75% max DD
- `largecap_meanrev` — failed
- `all_weather_static` — failed
- `a2_momentum` — failed 5/11 stable gates
- `clenow_momentum_semiannual` — research-only
- unknown engines

A refusal returns `allowed: false`, empty weights/amounts, and an explicit
flag. This is the technical enforcement of “Phase 2 is not Engine 2.”

### Regime

The frozen Phase 4B rule is reused:

- Nifty close > 200DMA → `normal`
- Nifty close ≤ 200DMA → `derisk`
- fewer than 200 sessions → `normal` with an `insufficient_history` flag

### Risk-score mapping (normal regime)

| Score | Nifty 50 | Gold BeES | Debt | Cash |
|---:|---:|---:|---:|---:|
| 1 | 20% | 20% | 50% | 10% |
| 2 | 25% | 20% | 45% | 10% |
| 3 | 30% | 20% | 40% | 10% |
| 4 | 35% | 20% | 35% | 10% |
| 5 | 40% | 20% | 30% | 10% |
| 6 | 45% | 20% | 25% | 10% |
| **7** | **50%** | **20%** | **20%** | **10%** |
| 8 | 55% | 20% | 15% | 10% |
| 9 | 60% | 20% | 10% | 10% |
| 10 | 65% | 20% | 5% | 10% |

Score 7 is the Phase 4B normal target. The 10% “cash” sleeve was cash/BTC in
the backtest; the product keeps it cash until a crypto sleeve is separately
approved.

### Risk-score mapping (de-risk regime)

| Score | Nifty 50 | Gold BeES | Debt | Cash |
|---:|---:|---:|---:|---:|
| 1 | 5% | 35% | 60% | 0% |
| 2 | 7% | 38% | 55% | 0% |
| 3 | 10% | 40% | 50% | 0% |
| 4 | 12% | 42% | 46% | 0% |
| **5** | **15%** | **45%** | **40%** | **0%** |
| 6 | 15% | 47% | 38% | 0% |
| 7 | 15% | 50% | 35% | 0% |
| 8 | 15% | 52% | 33% | 0% |
| 9 | 15% | 55% | 30% | 0% |
| 10 | 15% | 58% | 27% | 0% |

Score 5 is the Phase 4B de-risking target. Higher scores hold more gold and
less debt inside a de-risking regime. That is a profile policy, not a
backtested optimum. Gold is a concentrated, volatile sleeve, not capital
preservation.

Every allocation carries these disclosures:

- Phase 4B is conditional: 11.08% CAGR, −14.62% max DD, 2026 −8.64%.
- Debt was a synthetic 7% ledger in the backtest; actual G-Sec/liquid-fund
  returns and duration risk differ.
- The de-risking sleeve can be 45%+ gold; gold fell about 27.5%
  peak-to-trough in 2026.
- No tax, STT/GST/stamp duty, advisory fee, tracking error, or slippage is
  included.
- It is a profile allocation, not a guarantee.

### Actual 2026-11-19 check

Nifty close 25,514.30 vs 200DMA 23,995.50 → `normal`. Risk score 7 →
50% Nifty / 20% gold / 20% debt / 10% cash. The `momentum_alpha` request was
refused with `engine_status: research_only`.

## 3. Formatting bridge

Default path is deterministic:

- English brief
- Teluglish Roman brief
- data-quality warning is shown, not hidden
- risk-guard blocks/warnings are shown
- allocation refusals and conditional disclosures are shown
- exactly one disclaimer in a combined brief

Optional `refine_with_llm(brief, complete, language=...)`:

- uses an injected completion function; tests never touch the network
- rejects any rewrite that adds a number not in the deterministic brief
- rejects guarantees, risk-free claims, price targets, “buy/sell now,” and
  similar language
- falls back to the deterministic brief on transport failure or validation
  failure
- appends the disclaimer if the rewrite omitted it

The LLM cannot change the score, size, weights, flags, or data-quality status.
It is a language layer only.

Example English fragment:

> Risk guard: ALLOWED — RELIANCE, 2026-11-19.
> Position size: 145 shares; value ₹1,99,462; risk ₹9,973 (1.0% of capital);
> binding cap: risk; stop 1,306.82.

Example Teluglish fragment:

> Risk guard: ALLOWED — RELIANCE, 2026-11-19.
> Position size: 145 shares; value ₹1,99,462; risk ₹9,973 (1.0% of capital);
> binding cap: risk; stop 1,306.82.
> Idi decision support matrame — order kadu, guarantee kadu.

## 4. What is still missing

- **Query latency (resolved):** a SQLite byte-offset index is built at
  `data/brain/panel_index.sqlite` (6,688,924 rows, 743 MB, 1m03s build).
  RELIANCE score now takes ~0.31s and the risk plan ~0.54s. Rebuild with
  `python3 jobs/build_brain_panel_index.py --force` after a panel refresh.
  The index is a local research cache; do not ship it to users.
- Official NSE circuit/ban flags and F&O ban list.
- Point-in-time earnings dates; `actions.csv` is not a complete earnings
  calendar.
- Real AMFI NAV, SGB cash flows, and RBI G-Sec/T-bill history.
- Paper trading, legal/SEBI review, data licensing, tax and fee modelling.
- No UI, Telegram bot, mobile app, or execution integration has been built.

## 5. Tests

```bash
python3 tests/test_brain_scorer.py
python3 tests/test_brain_risk_guard.py
python3 tests/test_brain_allocator.py
python3 tests/test_brain_llm_bridge.py
python3 tests/test_brain_panel_index.py
python3 tests/test_brain_paper.py
```

All 83 tests pass as of 2026-11-21 (50 brain/paper/updater tests + 33 agent/paper-book tests).
