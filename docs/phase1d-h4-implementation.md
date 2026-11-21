# Phase 1D — H4 implementation audit

**Date:** 2026-11-21
**Engine:** `jobs/backtest_trend_pullback.py`
**Run command (primary):**

```bash
python3 jobs/backtest_trend_pullback.py \
  --regime nifty200 \
  --signal-mode rs_pullback \
  --entry-mode limit \
  --target-mode swing_3.0r \
  --stop-atr 1.0 \
  --horizon 20 \
  --limit-valid-bars 3 \
  --same-day-target deny \
  --max-notional-pct 0.20 \
  --rs-file data/curated/rs_rank.csv \
  --rs-min 0.90 \
  --outdir data/backtest_h4 \
  --bootstrap 10000
```

## Rule-to-code map

| H4 rule | Implementation |
|---|---|
| NSE EQ only; ETFs/REITs/InvITs excluded | panel filter in the main loop and RS builder |
| Price >= ₹20 | `bar.raw_close < MIN_PRICE_RAW` in `signal_from_bar` |
| 20D turnover >= ₹1 crore | `bar.turnover20 < MIN_TURNOVER_LACS` |
| Nifty close > 200DMA | `--regime nifty200` + `regime_ok()` |
| RS top decile | RS lookup keyed by `(date, stock_id)`, reject `< --rs-min` |
| Close > 200DMA, 50DMA > 200DMA | `signal_from_bar` trend block |
| ADX >= 20 | `bar.adx >= 20.0` |
| 20-session 50DMA slope > 0 | `bar.dma50_slope > 0.0` (20-session difference in `features.py`) |
| 5–15 sessions from 20-bar high | `H4_PULLBACK_MIN/MAX`, `H4_PULLBACK_LOOKBACK=20` |
| Pullback low in last 3 bars | `low_idx >= len(recent) - 3` |
| Pullback low >= 50DMA | `low_bar.low < low_bar.dma50` reject |
| No pullback close < 50DMA | loop over pullback bars rejects `b.close < b.dma50` |
| RSI at low 40–60 | `40.0 <= low_bar.rsi <= 60.0` |
| Average pullback volume < 20D volume | `avg_pullback_volume < low_bar.vol20` |
| Signal close <= 50DMA × 1.15 | `bar.close > bar.dma50 * 1.15` reject |
| Limit at low + 0.25 ATR | `pending["pullback_low"] + args.limit_buffer_atr * pending["atr"]` |
| Valid 3 sessions; gap fills at open | limit loop; `bar.open <= limit` else `bar.low <= limit` |
| Same-day target denied | `check_trade_bar(..., allow_same_day_target=False)` |
| Stop low − 1.0 ATR | `pending["pullback_low"] - args.stop_atr * pending["atr"]`, `--stop-atr 1.0` |
| Target min(prior high, 3R), >=1.5R | `swing_3.0r` branch in `build_trade` |
| Time exit 20 sessions | `--horizon 20`, used by `check_trade_bar` |
| No trailing stop | `--trail none` (default) |
| Max 20% notional | `--max-notional-pct 0.20` |
| 5% ADV cap | unchanged in `size_position` |
| Portfolio cash/slots | `jobs/portfolio_sim.py` |

## Ordering and no-look-ahead

- A signal is evaluated at the close of date `D`; the limit order starts on the
  next bar. The signal bar is never used as a same-day entry.
- Exits are checked before new entries for the same stock and date.
- The RS value is read for `bar.date` only.
- The limit fill uses the next bars' open/low, not the signal bar's low.
- The RS rank file is built from data through each date only; see
  `docs/phase1d-rs-audit.md`.

## Portfolio simulation

`jobs/portfolio_sim.py` replays the closed trades through a cash ledger:

- ₹10,00,000 starting capital.
- Max 5 concurrent positions primary; 10 is a sensitivity run.
- Max 20% of starting capital per position.
- Same-day entries ranked by `rs_pct` descending.
- Cash reserve = `qty × entry`; release = notional + net P&L.
- Daily mark-to-market at adjusted close; max drawdown on equity.
- `--stress` uses `net_R_stress` (2× slippage).

Skipped trades are not queued. The simulator does not downsize a trade to the
remaining cash; a trade that does not fit is skipped, as pre-registered.

## Trade-list audit

The 1,119 H4 trades were re-checked after the run:

- `rs_pct >= 0.90` for every trade.
- `target_R >= 1.5` for every trade.
- `entry_date > signal_date` for every trade.
- `exit_date >= entry_date` for every trade.
- Max notional ₹199,999.80 (20% cap respected).
- Max 5% ADV usage: 1.69% of 20D turnover (cap respected).
- Max holding: 20 sessions (time exit respected).
- No overlapping trades in the same stock.
- 0 violations.

## Known limitations

- The backtest sizes trades with fixed ₹10 lakh capital; the portfolio
  simulator enforces the cash ledger afterwards. This is valid because skipping
  a trade does not change the price path or the other trades' outcomes.
- Entry costs are charged in the trade P&L at exit, not reserved at entry; the
  cash ledger is therefore slightly optimistic on the entry day.
- The panel has no dividends, earnings dates, or intraday data.
- No PBO/DSR/baseline result is produced by this engine; those are separate
  validation steps.
