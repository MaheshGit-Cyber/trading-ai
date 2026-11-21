# Phase 5 — Internal Paper Trading (Signal Ledger)

**Status:** Active; baseline + first forward session recorded.
**Date:** 2026-11-21
**Modules:** `brain/paper.py`, `jobs/paper_snapshot.py`,
`jobs/update_nifty_from_yahoo.py`
**Ledger:** `data/paper_trading/ledger.jsonl`
**Tests:** `tests/test_brain_paper.py` (4), `tests/test_update_nifty.py` (2),
`tests/test_brain_paper_book.py` (6); **83 tests total** across the project

> No order is placed. No real money is involved. This is an append-only signal
> ledger used to build an honest track record before charging anyone.

## What is recorded

One immutable snapshot per trading date:

- `as_of` — the actual Nifty data date, never a fake future date
- `created_at` — UTC timestamp of the run
- capital, engine, regime, risk score
- target allocation weights and rupee amounts
- sleeve reference prices: Nifty close, Gold BeES close, synthetic debt index,
  cash
- every warning and conditional-engine disclosure
- a note that this is paper only, not an order

The same `Allocation` object used by the product is used here. There is no
separate “paper” formula.

## Recorded sessions

### 2026-11-19 — baseline

- Capital ₹10,00,000, risk score 7, Engine 1.
- Regime normal (Nifty 25,514.30 > 200DMA 23,995.50).
- Target: 50% Nifty / 20% Gold BeES / 20% debt / 10% cash.
- Sleeve prices: Nifty 25,514.30; Gold BeES 106.30; synthetic debt 3.1319;
  cash 1.0.

### 2026-11-20 — first forward session

- Nifty closed 25,800.60 (+1.12%).
- Gold BeES closed 102.21 (**−3.85%** in one session).
- Regime stayed normal; target stayed 50/20/20/10.
- Sleeve prices: Nifty 25,800.60; Gold BeES 102.21; synthetic debt 3.1324;
  cash 1.0.
- If the 2026-11-19 target weights had simply been held, the one-session
  mark-to-market was about **−0.21% before costs**. This is arithmetic, not a
  track record; no rebalance, tax or cost is modelled.

The 2–3 month clock is now **started at 2026-11-20**, but two snapshots are not
evidence. Do not call this a winning or losing strategy yet.

### Daily automation

`jobs/daily_paper_refresh.py` runs the full sequence (Nifty update, bhavcopy,
Gold BeES rebuild, snapshot) and refuses weekends/holidays/missing data.
`jobs/run_paper_daily.sh` is the idempotent wrapper; job 4701 is registered
in Termux with a 6-hour period. Scheduling, phone limitations and the
2027-02-20 target are documented in `docs/paper-automation.md`.

### Frozen paper report (2 sessions)

```bash
python3 jobs/paper_report.py
```

- final value **₹9,97,207.28**
- net return **−0.279%**
- max drawdown **−0.205%**
- Nifty over same closes **+1.122%**
- costs **₹740**, one rebalance (initial entry only)

This is arithmetic on two sessions. It is not a track record.

## Daily protocol

After the market close, on a real trading day:

```bash
# 1. Append the completed Nifty bar from Yahoo ^NSEI (research data)
python3 jobs/update_nifty_from_yahoo.py

# 2. Fetch that day's NSE bhavcopy (the script rejects a wrong DATE1/holiday)
python3 jobs/fetch_bhavcopy.py --date YYYY-MM-DD

# 3. Rebuild the Gold BeES series from raw bhavcopies
python3 jobs/extract_goldbees.py

# 4. Record the snapshot; duplicate dates are refused
python3 jobs/paper_snapshot.py --as-of YYYY-MM-DD \
    --capital 1000000 --risk-score 7
```

Engine 1 paper allocation uses only Nifty, Gold BeES, synthetic debt and cash.
A full panel/index rebuild is **not** required for this ledger. Rebuild
`data/brain/panel_index.sqlite` only when stock-level scores are refreshed.

Rules:

1. `--as-of` cannot be later than the latest Nifty bar. No fabricated days.
2. A date can be recorded once. `FileExistsError` on a duplicate.
3. The ledger is append-only; do not edit old lines.
4. If the data is stale, fix the data pipeline; do not repeat the old date.
5. Do not change capital, risk score, engine or weights mid-stream without a
   new versioned protocol. A paper track record is invalid if the rules drift.
6. A holiday or a failed bhavcopy fetch means **no snapshot**, not a fake one.

## Frozen evaluation convention (set before results)

The ledger records signals, not orders. To keep the eventual paper track record
honest, the evaluation rule is fixed now:

1. Start the hypothetical book at the **2026-11-19 close** with the recorded
   target weights. This baseline is arithmetic, not a trade.
2. Between target changes, **hold units**; do not rebalance daily. This avoids
   inventing turnover that the strategy did not specify.
3. If a target changes at session `t`, execute the new target at the **next
   recorded session's close** (`t+1`), not at `t`'s close. A signal computed
   from `t`'s close cannot be executed at that same close without look-ahead.
4. Costs: 10 bps one-way on Nifty/Gold BeES, 2 bps on debt, 0 on cash; apply
   on traded value, including the initial entry. Taxes and advisory fees are
   separate and must be added before any product claim.
5. Debt uses the snapshot's synthetic 7% ledger; cash stays at 1.0. No
   interpolation of missing sessions. If a session is missing, mark across the
   gap at the next recorded snapshot and disclose it.
6. Report gross and net marks, max drawdown on recorded closes, number of
   rebalances, every rule change, and the same-period Nifty return.

These rules are frozen. Changing them after seeing results invalidates the
paper track record.

Required report:

| Item | Requirement |
|---|---|
| Period | actual snapshots, no synthetic days |
| Signals | one per trading session, N >= ~40 sessions |
| Net return | after estimated costs, not gross |
| Max drawdown | daily close-to-close |
| Benchmark | Nifty buy-and-hold over the same dates |
| Backtest comparison | live paper vs Phase 4B expectations |
| Rule changes | list every change and its date |
| Data quality | missing/stale days counted, not hidden |

Do not charge a subscription on the strength of the backtest alone. Publish the
paper ledger and the losses, not only the wins.

## Honest limitations

- Debt is a **synthetic 7% calendar ledger**, not an actual G-Sec/liquid-fund
  NAV. Real debt returns and duration risk differ.
- Gold is Gold BeES market price; expenses are embedded in the ETF price, but
  tracking error and liquidity are not modelled.
- Nifty is research data, not licensed NSE data; no dividends.
- The 10% cash sleeve was cash/BTC in Phase 4B; this ledger keeps it cash.
- No STT/GST/stamp duty, advisory fee, slippage, capital-gains tax or tracking
  error is deducted in the snapshot. Evaluation must add cost assumptions.
- Phase 4B is conditional: 11.08% CAGR, −14.62% max DD, 2026 −8.64%.
- The ledger currently has two sessions (2026-11-19 and 2026-11-20). The
  2–3 month clock started on 2026-11-20 but is **not** evidence yet.
- Nifty updates use Yahoo `^NSEI` (research only), not a licensed NSE feed;
  this must change before a paid product or advertised track record.
- No UI, broker integration or paid product exists.

## Tests

```bash
python3 tests/test_brain_paper.py
python3 tests/test_update_nifty.py
```

Covers snapshot construction, append-only write, duplicate refusal, failed-engine
refusal, synthetic debt accrual, the de-risking allocation, Nifty append,
blank-close fill, close-mismatch refusal, and the no-partial-day rule.
