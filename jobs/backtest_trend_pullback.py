#!/usr/bin/env python3
"""Honest daily backtest of the pre-specified ``trend_pullback`` setup.

Universe: NSE EQ rows from ``data/curated/panel.csv``. BSE is deliberately
excluded from the first proof because 2020-2023 BSE identity is unresolved.

Rules are taken from ``memory/knowledge/setups.json`` and are not tuned on the
test period. Entry is the next open after a close-based signal. Exits are
stop / target / 10-session time exit. Same-day stop+target assumes stop first.
Gaps fill at the open. Costs and slippage are charged in R.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.features import Bar, StockState


HORIZON_DAYS = 10
MIN_PRICE_RAW = 20.0
MIN_TURNOVER_LACS = 100.0  # 20D average, Rs 1 crore
MIN_STOP_ATR = 0.5  # reject noise-tight stops
MIN_STOP_PCT = 0.01  # and stops tighter than 1% of price
MAX_POSITION_PCT = 0.25  # cap notional at 25% of capital
PULLBACK_MIN = 3
PULLBACK_MAX = 8
PULLBACK_LOOKBACK = 15
MAX_BARS_SINCE_PULLBACK_LOW = 3
H4_PULLBACK_MIN = 5
H4_PULLBACK_MAX = 15
H4_PULLBACK_LOOKBACK = 20
RISK_FLAGS = frozenset(
    {
        "ca_unadjusted",
        "ca_rights_unknown",
        "ca_split_unknown",
        "ca_bonus_unknown",
        "ca_not_reflected",
    }
)

# Budget-2026 equity-delivery cost model (see memory/knowledge/costs.json).
STT_BUY = 0.001
STT_SELL = 0.001
EXCHANGE = 0.0000297
SEBI = 0.000001
STAMP_BUY = 0.00015
DP_SELL = 13.5
GST = 0.18


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel.csv")
    p.add_argument("--outdir", default="data/backtest")
    p.add_argument("--signal-start", default="2020-01-01")
    p.add_argument("--signal-end", default="2026-11-19")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--risk-pct", type=float, default=0.01)
    p.add_argument("--bootstrap", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--exit-mode",
        choices=("levels", "time"),
        default="levels",
        help="levels=stop/target/time; time=hold to horizon close (diagnostic)",
    )
    p.add_argument(
        "--trail",
        choices=("none", "breakeven", "one_r"),
        default="none",
        help="trailing-stop overlay; applied on the bar after the trigger",
    )
    p.add_argument(
        "--regime",
        choices=("none", "nifty200"),
        default="none",
        help="nifty200 = no new entry when Nifty 50 closes below its 200DMA",
    )
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument(
        "--signal-mode",
        choices=("breakout", "pullback", "rs_pullback"),
        default="breakout",
        help="breakout = old trigger; pullback = H3; rs_pullback = H4",
    )
    p.add_argument(
        "--entry-mode",
        choices=("next_open", "limit"),
        default="next_open",
        help="limit = buy at pullback low + buffer, valid for N bars",
    )
    p.add_argument("--limit-buffer-atr", type=float, default=0.25)
    p.add_argument("--limit-valid-bars", type=int, default=2)
    p.add_argument(
        "--target-mode",
        choices=("swing_2.5r", "swing_1.5r", "swing_3.0r"),
        default="swing_2.5r",
        help="swing_1.5r = H3; swing_3.0r = H4",
    )
    p.add_argument(
        "--same-day-target",
        choices=("allow", "deny"),
        default="allow",
        help="deny = no same-day target on a limit entry (no intraday order data)",
    )
    p.add_argument(
        "--stop-atr",
        type=float,
        default=0.5,
        help="stop distance below the pullback low, in ATR (H4 uses 1.0)",
    )
    p.add_argument(
        "--horizon",
        type=int,
        default=HORIZON_DAYS,
        help="time exit in sessions (H4 uses 20)",
    )
    p.add_argument(
        "--max-notional-pct",
        type=float,
        default=MAX_POSITION_PCT,
        help="max position value as a fraction of capital (H4 uses 0.20)",
    )
    p.add_argument("--rs-file", default="data/curated/rs_rank.csv")
    p.add_argument(
        "--rs-min",
        type=float,
        default=0.90,
        help="minimum cross-sectional RS percentile (H4 uses 0.90)",
    )
    return p.parse_args()


def slip_one_way(turnover20_lacs: float) -> float:
    """Conservative one-way slippage by 20D average turnover."""
    if turnover20_lacs >= 1000.0:
        return 0.0010
    if turnover20_lacs >= 100.0:
        return 0.0025
    return 0.0050


def size_position(
    entry: float,
    stop: float,
    turnover20_lacs: float,
    capital: float,
    risk_pct: float,
    max_notional_pct: float = MAX_POSITION_PCT,
) -> tuple[int, float, float]:
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return 0, 0.0, 0.0
    risk_amount = capital * risk_pct
    qty = int(risk_amount / risk_per_share)
    # Do not take more than 5% of 20D average daily turnover, and do not
    # let a tight stop create a position larger than 25% of capital.
    max_notional = min(
        turnover20_lacs * 100_000.0 * 0.05,
        capital * max_notional_pct,
    )
    qty = min(qty, int(max_notional / entry))
    if qty < 1:
        return 0, risk_per_share, 0.0
    return qty, risk_per_share, qty * risk_per_share


def trade_cost_r(
    entry: float,
    exit_: float,
    qty: int,
    actual_risk: float,
    turnover20_lacs: float,
    slippage_mult: float,
) -> float:
    if qty < 1 or actual_risk <= 0:
        return 0.0
    buy = entry * qty
    sell = exit_ * qty
    stt = STT_BUY * buy + STT_SELL * sell
    exchange = EXCHANGE * (buy + sell)
    sebi = SEBI * (buy + sell)
    stamp = STAMP_BUY * buy
    gst = GST * (exchange + sebi)
    dp = DP_SELL
    slippage = slip_one_way(turnover20_lacs) * slippage_mult * (buy + sell)
    total = stt + exchange + sebi + stamp + gst + dp + slippage
    return total / actual_risk


def load_nifty(path: str) -> tuple[list[str], dict[str, float], dict[str, float]]:
    """Load Nifty 50 closes and a 200-session moving average."""
    closes: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                closes[row["date"]] = float(row["close"])
            except (KeyError, ValueError):
                continue
    dates = sorted(closes)
    dma200: dict[str, float] = {}
    window: list[float] = []
    for date in dates:
        window.append(closes[date])
        if len(window) > 200:
            window.pop(0)
        if len(window) == 200:
            dma200[date] = sum(window) / 200.0
    return dates, closes, dma200


def regime_ok(
    date: str,
    dates: list[str],
    closes: dict[str, float],
    dma200: dict[str, float],
) -> bool:
    """True when the index closed above its 200DMA on or before ``date``."""
    i = bisect.bisect_right(dates, date) - 1
    if i < 0:
        return False
    d = dates[i]
    return d in dma200 and closes[d] > dma200[d]


def build_trade(
    stock_id: str,
    symbol: str,
    pending: dict,
    entry: float,
    bar: Bar,
    args: argparse.Namespace,
) -> dict | None:
    """Build a trade for either next-open or limit entry."""
    if entry <= 0:
        return None
    if args.entry_mode == "limit":
        stop = pending["pullback_low"] - args.stop_atr * pending["atr"]
    else:
        stop = max(pending["pullback_low"], entry - 1.5 * pending["atr"])
    risk = entry - stop
    min_risk = max(MIN_STOP_ATR * pending["atr"], MIN_STOP_PCT * entry)
    if risk < min_risk or entry <= stop:
        return None

    if args.target_mode == "swing_1.5r":
        cap = entry + 1.5 * risk
        if pending["prior_swing_high"] > entry:
            target = min(pending["prior_swing_high"], cap)
        else:
            target = cap
        if target < entry + 1.0 * risk:
            return None
    elif args.target_mode == "swing_3.0r":
        cap = entry + 3.0 * risk
        if pending["prior_swing_high"] > entry:
            target = min(pending["prior_swing_high"], cap)
        else:
            target = cap
        if target < entry + 1.5 * risk:
            return None
    else:
        if pending["prior_swing_high"] > entry:
            target = pending["prior_swing_high"]
        else:
            target = entry + 2.5 * risk
        if target < entry + 2.0 * risk or entry >= target:
            return None

    qty, rps, actual_risk = size_position(
        entry,
        stop,
        pending["turnover20"],
        args.capital,
        args.risk_pct,
        args.max_notional_pct,
    )
    if qty < 1:
        return None
    return {
        "stock_id": stock_id,
        "symbol": symbol,
        "signal_date": pending["signal_date"],
        "entry_date": bar.date,
        "last_bar_date": bar.date,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_per_share": rps,
        "qty": qty,
        "actual_risk": actual_risk,
        "turnover20": pending["turnover20"],
        "target_R": (target - entry) / risk,
        "exit_mode": args.exit_mode,
        "entry_mode": args.entry_mode,
        "trail": args.trail,
        "horizon": args.horizon,
        "rs_pct": pending.get("rs_pct"),
        "bars_held": 0,
        "mfe_R": 0.0,
        "mae_R": 0.0,
        "data_risk": bool(bar.flags & RISK_FLAGS),
        "risk_flags": set(bar.flags & RISK_FLAGS),
        "signal_flags": ";".join(sorted(pending["flags"])),
    }


def signal_from_bar(
    state: StockState, bar: Bar, signal_mode: str = "breakout"
) -> dict | None:
    """Return a pending signal, or None. Uses bars through ``bar`` only."""
    if len(state.bars) < 200:
        return None
    if bar.flags & RISK_FLAGS:
        return None
    if bar.dma20 is None or bar.dma50 is None or bar.dma200 is None:
        return None
    if bar.dma50_slope is None or bar.atr is None:
        return None
    if bar.rsi is None or bar.adx is None or bar.vol20 is None:
        return None
    if bar.turnover20 is None or bar.turnover20 < MIN_TURNOVER_LACS:
        return None
    if bar.raw_close < MIN_PRICE_RAW:
        return None

    # Regime: trend_up, measured from data.
    if not (
        bar.close > bar.dma200
        and bar.dma50 > bar.dma200
        and bar.adx >= 20.0
        and bar.dma50_slope > 0.0
    ):
        return None

    # Avoid late-stage entries (failure mode: >15% above the 50DMA).
    if bar.close > bar.dma50 * 1.15:
        return None
    if bar.close <= bar.dma50:
        return None
    if signal_mode == "breakout" and bar.close <= bar.dma20:
        return None

    if signal_mode == "breakout":
        # Breakout trigger: close above the prior day's high, on volume.
        if len(state.bars) < 2:
            return None
        if bar.close <= state.bars[-2].high:
            return None
        if bar.volume < 1.3 * bar.vol20:
            return None
        hist = list(state.bars)[:-1]
    else:
        # Pullback entry: evaluate the pullback as of today's close.
        hist = list(state.bars)
    if signal_mode == "rs_pullback":
        pb_min, pb_max, lookback, rsi_max = (
            H4_PULLBACK_MIN,
            H4_PULLBACK_MAX,
            H4_PULLBACK_LOOKBACK,
            60.0,
        )
    else:
        pb_min, pb_max, lookback, rsi_max = (
            PULLBACK_MIN,
            PULLBACK_MAX,
            PULLBACK_LOOKBACK,
            65.0,
        )
    if len(hist) < 20:
        return None
    recent = hist[-lookback:]
    high_idx = max(range(len(recent)), key=lambda i: recent[i].high)
    if high_idx >= len(recent) - 1:
        return None
    after = recent[high_idx + 1 :]
    low_rel = min(range(len(after)), key=lambda i: after[i].low)
    low_idx = high_idx + 1 + low_rel
    pullback_len = low_idx - high_idx
    if not (pb_min <= pullback_len <= pb_max):
        return None
    # The low must be recent; otherwise this is a late entry after a long
    # recovery, not a fresh pullback continuation.
    if low_idx < len(recent) - MAX_BARS_SINCE_PULLBACK_LOW:
        return None

    low_bar = recent[low_idx]
    if low_bar.dma20 is None or low_bar.dma50 is None:
        return None
    if signal_mode == "rs_pullback":
        if low_bar.low < low_bar.dma50:
            return None
    else:
        if low_bar.low < low_bar.dma20:
            return None
    if low_bar.rsi is None or not (40.0 <= low_bar.rsi <= rsi_max):
        return None
    if low_bar.vol20 is None or low_bar.vol20 <= 0:
        return None

    pullback = recent[high_idx + 1 : low_idx + 1]
    if not pullback:
        return None
    for b in pullback:
        if b.dma50 is None or b.close < b.dma50:
            return None
    avg_pullback_volume = sum(b.volume for b in pullback) / len(pullback)
    if avg_pullback_volume >= low_bar.vol20:
        return None

    return {
        "signal_date": bar.date,
        "pullback_low": low_bar.low,
        "prior_swing_high": recent[high_idx].high,
        "atr": bar.atr,
        "signal_close": bar.close,
        "turnover20": bar.turnover20,
        "flags": bar.flags,
    }


def finalize_trade(
    trade: dict,
    exit_price: float,
    exit_reason: str,
    capital: float,
    risk_pct: float,
) -> dict:
    entry = trade["entry"]
    risk = trade["risk_per_share"]
    gross_r = (exit_price - entry) / risk
    actual_risk = trade["actual_risk"]
    cost_r = trade_cost_r(
        entry,
        exit_price,
        trade["qty"],
        actual_risk,
        trade["turnover20"],
        1.0,
    )
    cost_r_stress = trade_cost_r(
        entry,
        exit_price,
        trade["qty"],
        actual_risk,
        trade["turnover20"],
        2.0,
    )
    trade.update(
        {
            "exit_date": trade["last_bar_date"],
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_R": gross_r,
            "cost_R": cost_r,
            "net_R": gross_r - cost_r,
            "cost_R_stress": cost_r_stress,
            "net_R_stress": gross_r - cost_r_stress,
        }
    )
    return trade


def check_trade_bar(
    trade: dict,
    bar: Bar,
    is_entry: bool,
    allow_same_day_target: bool = True,
) -> tuple[str, float] | None:
    """Update excursions and return ``(reason, fill_price)`` if closed."""
    trade["last_bar_date"] = bar.date
    if bar.flags & RISK_FLAGS:
        trade["data_risk"] = True
        trade["risk_flags"].update(bar.flags & RISK_FLAGS)
    entry = trade["entry"]
    risk = trade["risk_per_share"]
    prior_mfe = trade["mfe_R"]
    trade["mfe_R"] = max(trade["mfe_R"], (bar.high - entry) / risk)
    trade["mae_R"] = min(trade["mae_R"], (bar.low - entry) / risk)

    # Trailing overlay is applied from the *next* bar onward, using only
    # excursion information known before this bar.
    if not is_entry:
        if trade.get("trail") == "breakeven" and prior_mfe >= 1.0:
            trade["stop"] = max(trade["stop"], entry)
        elif trade.get("trail") == "one_r" and prior_mfe >= 1.5:
            trade["stop"] = max(trade["stop"], entry + risk)

    stop = trade["stop"]
    target = trade["target"]
    if trade.get("exit_mode") == "time":
        if is_entry:
            trade["bars_held"] = 1
            return None
        trade["bars_held"] += 1
        if trade["bars_held"] >= trade.get("horizon", HORIZON_DAYS):
            return "time", bar.close
        return None

    if is_entry:
        trade["bars_held"] = 1
        # Both levels touched on the entry bar: assume the stop first.
        if bar.low <= stop and bar.high >= target:
            return "stop_same_day", stop
        if bar.low <= stop:
            return "stop_same_day", stop
        # A limit fill can happen after the day's high. Without intraday
        # timestamps, do not award a same-day target on a limit entry.
        if not allow_same_day_target and trade.get("entry_mode") == "limit":
            return None
        if bar.high >= target:
            return "target_same_day", target
        return None

    # Gap fills first: the open is the only price available.
    if bar.open <= stop:
        return "gap_stop", bar.open
    if bar.open >= target:
        return "gap_target", bar.open
    # Daily OHLC cannot order the two touches; assume the stop first.
    if bar.low <= stop and bar.high >= target:
        return "stop_first", stop
    if bar.low <= stop:
        return "stop", stop
    if bar.high >= target:
        return "target", target

    trade["bars_held"] += 1
    if trade["bars_held"] >= trade.get("horizon", HORIZON_DAYS):
        return "time", bar.close
    return None


def summarize(trades: list[dict], label: str) -> dict:
    closed = [t for t in trades if t.get("net_R") is not None]
    primary = [t for t in closed if not t.get("data_risk")]
    nets = [t["net_R"] for t in primary]
    stress = [t["net_R_stress"] for t in primary]
    gross = [t["gross_R"] for t in primary]
    if not nets:
        return {
            "label": label,
            "n": 0,
            "expectancy_R": None,
            "note": "no primary trades",
        }
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    # Trade-sequence drawdown, ordered by exit date.
    ordered = sorted(primary, key=lambda t: (t["exit_date"], t["entry_date"]))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in ordered:
        equity += t["net_R"]
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return {
        "label": label,
        "n": len(nets),
        "gross_expectancy_R": statistics.fmean(gross),
        "expectancy_R": statistics.fmean(nets),
        "expectancy_R_stress": statistics.fmean(stress),
        "median_R": statistics.median(nets),
        "stdev_R": statistics.pstdev(nets) if len(nets) > 1 else 0.0,
        "positive_rate": len(wins) / len(nets),
        "win_rate_1R": sum(1 for x in nets if x >= 1.0) / len(nets),
        "avg_win_R": statistics.fmean(wins) if wins else 0.0,
        "avg_loss_R": statistics.fmean(losses) if losses else 0.0,
        "profit_factor": (
            sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else None
        ),
        "max_drawdown_R": max_dd,
        "avg_cost_R": statistics.fmean([t["cost_R"] for t in primary]),
        "avg_bars_held": statistics.fmean([t["bars_held"] for t in primary]),
        "data_risk_excluded": len(closed) - len(primary),
        "exit_reasons": dict(
            sorted(
                {
                    r: sum(1 for t in primary if t["exit_reason"] == r)
                    for r in {t["exit_reason"] for t in primary}
                }.items()
            )
        ),
    }


def bootstrap(nets: list[float], n: int, seed: int) -> dict:
    if not nets:
        return {}
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        sample = [nets[rng.randrange(len(nets))] for _ in range(len(nets))]
        means.append(statistics.fmean(sample))
    means.sort()
    return {
        "n": n,
        "mean_of_means": statistics.fmean(means),
        "p05": means[int(0.05 * (n - 1))],
        "p50": means[int(0.50 * (n - 1))],
        "p95": means[int(0.95 * (n - 1))],
        "prob_mean_positive": sum(1 for x in means if x > 0) / n,
    }


def main() -> int:
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    states: dict[str, StockState] = {}
    open_trades: dict[str, dict] = {}
    pending_by_stock: dict[str, dict] = {}
    trades: list[dict] = []
    rows = 0
    nse_rows = 0
    skipped_bad = 0

    regime_dates: list[str] = []
    regime_closes: dict[str, float] = {}
    regime_dma200: dict[str, float] = {}
    if args.regime == "nifty200":
        regime_dates, regime_closes, regime_dma200 = load_nifty(args.nifty)

    rs_lookup: dict[tuple[str, str], float] = {}
    if args.signal_mode == "rs_pullback":
        if not os.path.exists(args.rs_file):
            raise SystemExit(f"missing RS file: {args.rs_file}")
        with open(args.rs_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    rs = float(row["rs_pct"])
                except (KeyError, ValueError, TypeError):
                    continue
                if rs >= args.rs_min:
                    rs_lookup[(row["date"], row["stock_id"])] = rs
        if not rs_lookup:
            raise SystemExit("RS lookup is empty")

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            rows += 1
            if row[ix["market"]] != "NSE":
                continue
            nse_rows += 1
            stock_id = row[ix["stock_id"]]
            symbol = row[ix["symbol"]]
            name = row[ix["name"]].upper()
            date = row[ix["date"]]
            if row[ix["series"]] != "EQ":
                continue
            # NSE's EQ series also contains ETFs/REITs/InvITs. This strategy is
            # for operating companies, not pooled vehicles.
            if any(
                token in name or token in symbol.upper()
                for token in (
                    "ETF",
                    "BEES",
                    "EXCHANGE TRADED",
                    "MUTUAL FUND",
                    "REIT",
                    "INVIT",
                )
            ):
                continue
            try:
                o = float(row[ix["adj_open"]])
                h = float(row[ix["adj_high"]])
                l = float(row[ix["adj_low"]])
                c = float(row[ix["adj_close"]])
                v = float(row[ix["adj_volume"]])
                turnover = float(row[ix["turnover_lacs"]] or 0.0)
                raw_close = float(row[ix["close"]])
            except (ValueError, TypeError):
                skipped_bad += 1
                continue
            flags = frozenset(x for x in row[ix["flags"]].split(";") if x)

            st = states.get(stock_id)
            if st is None:
                st = StockState(symbol)
                states[stock_id] = st
            bar = st.update(date, o, h, l, c, v, turnover, raw_close, flags)
            if bar is None:
                skipped_bad += 1
                continue

            # Existing position: exits are checked before new signals.
            trade = open_trades.get(stock_id)
            if trade is not None:
                result = check_trade_bar(trade, bar, is_entry=False)
                if result is not None:
                    reason, price = result
                    finalize_trade(
                        trade, price, reason, args.capital, args.risk_pct
                    )
                    trades.append(trade)
                    del open_trades[stock_id]
                    trade = None

            # Pending signal handling.
            pending = pending_by_stock.get(stock_id)
            if trade is not None:
                pending = None
                pending_by_stock.pop(stock_id, None)

            if trade is None and pending is not None:
                if args.entry_mode == "next_open":
                    pending_by_stock.pop(stock_id, None)
                    sig_date = dt.date.fromisoformat(pending["signal_date"])
                    bar_date = dt.date.fromisoformat(bar.date)
                    if (bar_date - sig_date).days <= 3:
                        trade = build_trade(
                            stock_id, symbol, pending, bar.open, bar, args
                        )
                        if trade is not None:
                            result = check_trade_bar(
                                trade,
                                bar,
                                is_entry=True,
                                allow_same_day_target=(
                                    args.same_day_target == "allow"
                                ),
                            )
                            if result is not None:
                                reason, price = result
                                finalize_trade(
                                    trade,
                                    price,
                                    reason,
                                    args.capital,
                                    args.risk_pct,
                                )
                                trades.append(trade)
                                trade = None
                            else:
                                open_trades[stock_id] = trade
                else:
                    pending["bars_waited"] = pending.get("bars_waited", 0) + 1
                    limit_price = (
                        pending["pullback_low"]
                        + args.limit_buffer_atr * pending["atr"]
                    )
                    entry = None
                    if bar.open <= limit_price:
                        entry = bar.open
                    elif bar.low <= limit_price:
                        entry = limit_price
                    if entry is not None:
                        pending_by_stock.pop(stock_id, None)
                        trade = build_trade(
                            stock_id, symbol, pending, entry, bar, args
                        )
                        if trade is not None:
                            result = check_trade_bar(
                                trade,
                                bar,
                                is_entry=True,
                                allow_same_day_target=(
                                    args.same_day_target == "allow"
                                ),
                            )
                            if result is not None:
                                reason, price = result
                                finalize_trade(
                                    trade,
                                    price,
                                    reason,
                                    args.capital,
                                    args.risk_pct,
                                )
                                trades.append(trade)
                                trade = None
                            else:
                                open_trades[stock_id] = trade
                    elif pending["bars_waited"] >= args.limit_valid_bars:
                        pending_by_stock.pop(stock_id, None)

            # New signal at today's close, only if flat and no pending order.
            if (
                trade is None
                and stock_id not in open_trades
                and stock_id not in pending_by_stock
            ):
                if args.signal_start <= bar.date <= args.signal_end:
                    sig = signal_from_bar(st, bar, args.signal_mode)
                    if sig is not None and args.regime == "nifty200":
                        if not regime_ok(
                            bar.date,
                            regime_dates,
                            regime_closes,
                            regime_dma200,
                        ):
                            sig = None
                    if sig is not None and args.signal_mode == "rs_pullback":
                        rs = rs_lookup.get((bar.date, stock_id))
                        if rs is None or rs < args.rs_min:
                            sig = None
                        else:
                            sig["rs_pct"] = rs
                    if sig is not None:
                        sig["bars_waited"] = 0
                        pending_by_stock[stock_id] = sig

    open_at_end = len(open_trades)

    closed = [t for t in trades if t.get("net_R") is not None]
    primary = [t for t in closed if not t.get("data_risk")]
    nets = [t["net_R"] for t in primary]

    def year_stats(year: int) -> dict:
        subset = [t for t in primary if t["entry_date"][:4] == str(year)]
        return summarize(subset, str(year))

    summary = {
        "setup": "trend_pullback",
        "panel": args.panel,
        "universe": "NSE EQ only; BSE excluded from first proof",
        "signal_window": [args.signal_start, args.signal_end],
        "exit_mode": args.exit_mode,
        "trail": args.trail,
        "signal_mode": args.signal_mode,
        "entry_mode": args.entry_mode,
        "target_mode": args.target_mode,
        "regime": args.regime,
        "limit_buffer_atr": args.limit_buffer_atr,
        "limit_valid_bars": args.limit_valid_bars,
        "same_day_target": args.same_day_target,
        "stop_atr": args.stop_atr,
        "horizon": args.horizon,
        "max_notional_pct": args.max_notional_pct,
        "rs_file": args.rs_file,
        "rs_min": args.rs_min,
        "costs": {
            "capital": args.capital,
            "risk_pct": args.risk_pct,
            "stt_buy": STT_BUY,
            "stt_sell": STT_SELL,
            "exchange": EXCHANGE,
            "sebi": SEBI,
            "stamp_buy": STAMP_BUY,
            "dp_sell": DP_SELL,
            "gst": GST,
            "min_stop_atr": MIN_STOP_ATR,
            "min_stop_pct": MIN_STOP_PCT,
            "max_position_pct": MAX_POSITION_PCT,
            "slippage_one_way": {
                "largecap_ge_1000_lacs": 0.0010,
                "midcap_100_1000_lacs": 0.0025,
                "smallcap_lt_100_lacs": 0.0050,
            },
            "stress": "slippage doubled",
        },
        "rows_scanned": rows,
        "nse_rows": nse_rows,
        "stocks": len(states),
        "skipped_bad_rows": skipped_bad,
        "closed_trades": len(closed),
        "open_at_end": open_at_end,
        "primary_trades": len(primary),
        "data_risk_excluded": len(closed) - len(primary),
        "overall": summarize(closed, "all_closed"),
        "primary": summarize(primary, "primary_no_ca_risk"),
        "by_year": {str(y): year_stats(y) for y in range(2020, 2027)},
        "walk_forward": {
            "dev_2020_2022": summarize(
                [t for t in primary if t["entry_date"][:4] <= "2022"], "dev"
            ),
            "validation_2023_2024": summarize(
                [
                    t
                    for t in primary
                    if "2023" <= t["entry_date"][:4] <= "2024"
                ],
                "validation",
            ),
            "test_2025_2026": summarize(
                [t for t in primary if t["entry_date"][:4] >= "2025"], "test"
            ),
        },
        "bootstrap": bootstrap(nets, args.bootstrap, args.seed),
    }
    summary["gate"] = {
        "min_test_trades": 100,
        "test_expectancy_positive": (
            summary["walk_forward"]["test_2025_2026"].get("expectancy_R") or 0
        )
        > 0,
        "test_stress_positive": (
            summary["walk_forward"]["test_2025_2026"].get("expectancy_R_stress") or 0
        )
        > 0,
        "test_profit_factor_gt_1_2": (
            summary["walk_forward"]["test_2025_2026"].get("profit_factor") or 0
        )
        > 1.2,
        "test_sample_ok": summary["walk_forward"]["test_2025_2026"].get("n", 0)
        >= 100,
    }
    summary["gate"]["passed"] = all(
        summary["gate"][k]
        for k in (
            "test_expectancy_positive",
            "test_stress_positive",
            "test_profit_factor_gt_1_2",
            "test_sample_ok",
        )
    )

    trades_path = os.path.join(args.outdir, "trades_trend_pullback.csv")
    fields = [
        "stock_id",
        "symbol",
        "signal_date",
        "entry_date",
        "exit_date",
        "entry",
        "stop",
        "target",
        "exit_price",
        "exit_reason",
        "qty",
        "risk_per_share",
        "target_R",
        "turnover20",
        "rs_pct",
        "bars_held",
        "gross_R",
        "cost_R",
        "net_R",
        "cost_R_stress",
        "net_R_stress",
        "mfe_R",
        "mae_R",
        "data_risk",
        "risk_flags",
        "signal_flags",
    ]
    with open(trades_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in trades:
            row = dict(t)
            row["risk_flags"] = ";".join(sorted(t.get("risk_flags", set())))
            row["signal_flags"] = t.get("signal_flags", "")
            writer.writerow({k: row.get(k, "") for k in fields})

    summary_path = os.path.join(args.outdir, "summary_trend_pullback.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps({
        "trades": len(closed),
        "primary": len(primary),
        "overall": summary["overall"],
        "walk_forward": summary["walk_forward"],
        "gate": summary["gate"],
        "trades_path": trades_path,
        "summary_path": summary_path,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
