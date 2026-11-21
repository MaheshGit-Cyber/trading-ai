# Phase 5 — Deterministic M-Score (Brain Core, Phase 1)

**Status:** Implemented. `M` only. `D` and `V` are deliberately absent.
**Date:** 2026-11-21
**Modules:** `brain/contracts.py`, `brain/data.py`, `brain/scorer.py`
**Tests:** `tests/test_brain_scorer.py` (8 tests, all passing)

> This is a descriptive score, not a buy/sell instruction. It is computed only
> from bars at or before `as_of`. The LLM layer may explain it; it may not
> invent numbers or change the score.

## Why M only

The proposed DVM score needs:

| Part | Inputs | Available in the local panel? |
|---|---|---|
| **D** — durability | debt/equity, interest coverage, profitability history | **No** |
| **V** — valuation | EPS, book value, P/E/P/B history | **No** |
| **M** — momentum/trend | adjusted OHLCV, turnover, delivery %, Nifty | **Yes** |

`data/curated/panel_nse_isin_v3.csv` has price, volume, turnover and delivery,
but no fundamentals. Calling a made-up score “DVM” would be fake precision.
Phase 1 therefore ships the audited M-score. Full DVM waits for a licensed,
point-in-time fundamentals dataset.

## NSE M-score (0–100)

| Component | Max | Rule |
|---|---:|---|
| **Trend** | 30 | 10 if close > 200DMA; 10 if 50DMA > 200DMA; 10 if 50DMA slope > 0 (5 if flat) |
| **Relative strength** | 30 | 15 for 63D excess vs Nifty; 15 for 126D excess. Piecewise: ≥+20% full, ≥+10% 80%, ≥0% 53%, ≥−10% 27%, else 0 |
| **Delivery & volume** | 20 | 10 for volume vs 20D average; 10 for delivery % vs 20D average. ≥1.5× full, ≥1.2× 80%, ≥1.0× 60%, ≥0.7× 30% |
| **Downside risk** | 20 | 10 for 20D annualised volatility (≤20% full, ≤30% 70%, ≤40% 40%); 10 for 126D max drawdown (≥−10% full, ≥−20% 70%, ≥−30% 40%) |

Bands:

- **strong** ≥ 80
- **positive** ≥ 65
- **neutral** ≥ 45
- **weak** ≥ 30
- **very_weak** < 30

## Crypto score (0–100)

| Component | Max | Rule |
|---|---:|---|
| **Trend** | 40 | 20 if close > 200DMA; 20 if 50DMA > 200DMA |
| **Momentum** | 40 | 20 for 63D return; 20 for 126D return. ≥+30% full, ≥+15% 80%, ≥0% 50%, ≥−15% 20% |
| **Downside risk** | 20 | 30D annualised volatility; 126D max drawdown. Crypto thresholds are wider than equity thresholds |

Supported pairs: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`.
The source is Binance daily USDT data; no INR conversion, Indian crypto tax, or
regulatory handling is modelled.

## Data quality

`AssetScore.data_quality` reports:

- `bars`: valid bars used
- `required_bars`: 200
- `stale_days`: calendar days between the last bar and `as_of`
- `flags`: e.g. `insufficient_history`, `nifty_missing`, `delivery_missing`,
  `delivery_history_short`, plus panel corporate-action flags
- `ok`: false when history is insufficient, the Nifty benchmark is missing, or
  the data is more than 5 calendar days stale

A low score is not the same as a data error. Check `data_quality` before
showing a score to a user.

## No look-ahead

- `brain/data.py` stops every loader at `as_of`.
- `brain/scorer.py` filters again defensively.
- `engine.features.StockState` is causal; it receives one bar at a time.
- Nifty returns use only closes at or before the stock's `as_of`.
- `tests/test_brain_scorer.py` adds 40 future crash bars and proves the as-of
  score is byte-identical.

## Run

```bash
# NSE stock
python3 -m brain.scorer --symbol RELIANCE --as-of 2026-11-19

# Continuous ID is safer across symbol changes
python3 -m brain.scorer --stock-id NSE:INE002A01018 --as-of 2026-11-19

# Crypto
python3 -m brain.scorer --crypto BTCUSDT --as-of 2026-11-20

# Tests
python3 tests/test_brain_scorer.py
```

Example from 2026-11-19: RELIANCE scored **31 / weak** because price was above
the 200DMA but the 50DMA was below it and falling, relative strength was
negative, volume was below average, and 20D volatility was 44%. This is a
description, not a recommendation.

## Engine governance

`brain/contracts.py` contains the only audited engines:

| Engine | Status | Allocatable? |
|---|---|---|
| All-Weather Defender (Phase 4B) | **conditional** | Yes, with disclosures |
| Momentum Alpha (Phase 2B) | **research_only** | **No** (-49.75% DD) |
| Large-Cap Mean Reversion (Phase 3) | **failed** | No |
| All-Weather Static (Phase 4) | **failed** | No |

The future allocator must call `EngineInfo.can_allocate` and refuse
`research_only` / `failed` engines. This is how Phase 2 is kept out of the
product even if a UI or prompt later asks for it.

## Known limitations

- **NSE query speed (resolved):** the first streaming query took ~1m26s. A
  SQLite byte-offset index now lives at `data/brain/panel_index.sqlite`
  (6,688,924 rows, 743 MB, built in 1m03s). The same RELIANCE query now takes
  **~0.31s**. The index stores offsets only, not a second copy of prices.
  Rebuild it if the panel changes:
  `python3 jobs/build_brain_panel_index.py --force`. If the index is missing
  or corrupt, the loader falls back to streaming.
- No fundamentals, no D/V, no sector-relative RS (sector map absent).
- `deliv_per` is total exchange delivery, not FII/DII institutional flow.
- Nifty is Yahoo `^NSEI` research data, not licensed NSE data.
- No dividends; adjusted prices are price-return only.
- No point-in-time NSE master; symbol/ISIN mapping uses the current master.
- Crypto is Binance USDT; no INR, tax, or Indian regulatory layer.
- The score weights are transparent heuristics, not a backtested alpha model.
  Do not market them as a proven return forecast.
