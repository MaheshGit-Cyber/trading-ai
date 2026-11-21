#!/usr/bin/env python3
"""Clenow momentum + quarterly rebalance research backtest.

Spec: ``docs/clenow-momentum-spec.md``.

Rules in one line: point-in-time top-100-by-turnover NSE EQ names, Clenow
90-session log-linear slope x R^2, close above 100DMA, top 10-15, inverse
20DMA ATR weights capped at 10%, quarterly (63-session) rebalance at the next
open, daily 100DMA exits, Nifty 50 200DMA regime into 50% GOLDBEES + 50%
LIQUIDBEES, full delivery costs, 2x slippage stress, 2024-12-10 train/test
split.

The script is train-first by default. Test output requires ``--allow-test``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict, deque
from datetime import date as ddate, datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from brain.scorer import calculate_clenow_momentum  # noqa: E402
from jobs.backtest_a2_momentum import (  # noqa: E402
    add_dividend,
    curve_stats,
    is_excluded,
    monthly_from_curve,
    parse_flags,
    sanitize,
    write_csv,
)
from jobs.backtest_monthly_momentum import load_nifty, run_portfolio  # noqa: E402

LIQUIDBEES_ID = "NSE:INF732E01037"
GOLDBEES_ID = "GOLDBEES"
DEFENSIVE_IDS = (GOLDBEES_ID, LIQUIDBEES_ID)

RISK_FLAGS = frozenset(
    {
        "ca_unadjusted",
        "ca_rights_unknown",
        "ca_split_unknown",
        "ca_bonus_unknown",
        "ca_not_reflected",
    }
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel_nse_isin_v3.csv")
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--gold", default="data/gold/goldbees_daily_2010_2026.csv")
    p.add_argument("--master", default="data/nse_equity_master.csv")
    p.add_argument("--outdir", default="data/backtest/clenow_momentum")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--split", default="2024-12-10")
    p.add_argument("--min-price", type=float, default=20.0)
    p.add_argument("--min-turnover", type=float, default=1000.0)
    p.add_argument("--top-liquid", type=int, default=100)
    p.add_argument(
        "--exit-rank",
        type=int,
        default=30,
        help="quarterly top-up: drop a holding if its Clenow rank is worse than this",
    )
    p.add_argument("--holdings", type=int, default=10)
    p.add_argument("--max-weight", type=float, default=0.10)
    p.add_argument("--max-adv-pct", type=float, default=0.05)
    p.add_argument("--rebalance-days", type=int, default=63)
    p.add_argument(
        "--full-reconstitution-days",
        type=int,
        default=126,
        help="full reconstitution cadence; 0 = every rebalance",
    )
    p.add_argument(
        "--daily-dma-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="exit on a daily 100DMA break (default: on)",
    )
    p.add_argument("--clenow-window", type=int, default=90)
    p.add_argument("--dma-exit", type=int, default=100)
    p.add_argument("--atr-window", type=int, default=20)
    p.add_argument("--regime-window", type=int, default=200)
    p.add_argument(
        "--regime-buffer",
        type=float,
        default=0.02,
        help="200DMA hysteresis: defensive below SMA*(1-buffer), "
        "re-risk above SMA",
    )
    p.add_argument("--dividend-yield", type=float, default=0.012)
    p.add_argument("--writeoff-days", type=int, default=90)
    p.add_argument("--min-test-rebalances", type=int, default=4)
    p.add_argument(
        "--phase",
        choices=("train", "test", "full"),
        default="train",
        help="train = through the split only; test/full require --allow-test",
    )
    p.add_argument("--allow-test", action="store_true")
    p.add_argument("--force-test", action="store_true")
    p.add_argument("--append-bridge", action="store_true")
    return p.parse_args()


def _atr(
    highs: deque[float],
    lows: deque[float],
    closes: deque[float],
    window: int = 20,
) -> float:
    """Average true range over the last ``window`` sessions.

    All three deques must be aligned and contain at least ``window + 1``
    values. The caller enforces that; returning 0.0 here keeps a bad row from
    crashing.
    """
    need = window + 1
    n = min(len(highs), len(lows), len(closes))
    if n < need:
        return 0.0
    h = list(highs)[-need:]
    l = list(lows)[-need:]
    c = list(closes)[-need:]
    trs = []
    for i in range(1, need):
        prev = c[i - 1]
        trs.append(max(h[i] - l[i], abs(h[i] - prev), abs(l[i] - prev)))
    return sum(trs) / len(trs) if trs else 0.0


def inverse_vol_weights(rows: list[dict], max_weight: float = 0.10) -> list[float]:
    """Inverse-ATR weights, capped per name, with residual cash allowed."""
    n = len(rows)
    if n == 0:
        return []
    inv = []
    for row in rows:
        atr = row.get("atr20") or 0.0
        inv.append(1.0 / atr if atr > 0 else 1.0)
    total = sum(inv)
    if total <= 0:
        return [min(1.0 / n, max_weight)] * n

    raw = [x / total for x in inv]
    weights = raw[:]
    capped: set[int] = set()
    for _ in range(n + 1):
        over = [i for i, w in enumerate(weights) if w > max_weight + 1e-12]
        if not over:
            break
        for i in over:
            weights[i] = max_weight
            capped.add(i)
        remaining = 1.0 - sum(weights[i] for i in capped)
        uncapped = [i for i in range(n) if i not in capped]
        if not uncapped or remaining <= 0:
            break
        base = sum(raw[i] for i in uncapped)
        if base <= 0:
            for i in uncapped:
                weights[i] = remaining / len(uncapped)
        else:
            for i in uncapped:
                weights[i] = remaining * raw[i] / base
    return [min(w, max_weight) for w in weights]


def defensive_targets() -> list[dict]:
    return [
        {
            "stock_id": GOLDBEES_ID,
            "symbol": "GOLDBEES",
            "name": "Gold BeES",
            "weight": 0.5,
            "turnover20": 1e9,
            "atr20": 0.0,
            "clenow": 0.0,
            "rank": 1,
        },
        {
            "stock_id": LIQUIDBEES_ID,
            "symbol": "LIQUIDBEES",
            "name": "Liquid BeES",
            "weight": 0.5,
            "turnover20": 1e9,
            "atr20": 0.0,
            "clenow": 0.0,
            "rank": 2,
        },
    ]


def build_rebalance_pairs(
    nifty_dates: list[str],
    start: str,
    end: str,
    step: int,
    warmup: int = 100,
) -> list[tuple[str, str]]:
    """Signal/next-open pairs every ``step`` sessions, after warm-up."""
    idx = [i for i, d in enumerate(nifty_dates) if start <= d <= end]
    if not idx:
        return []
    i = idx[0] + warmup
    out: list[tuple[str, str]] = []
    while i < len(nifty_dates):
        signal = nifty_dates[i]
        if signal > end:
            break
        if i + 1 >= len(nifty_dates):
            break
        exec_d = nifty_dates[i + 1]
        if exec_d > end:
            break
        out.append((signal, exec_d))
        i += step
    return out


def build_nifty_regime_hysteresis(
    dates: list[str],
    closes: dict[str, float],
    window: int = 200,
    buffer: float = 0.02,
) -> dict[str, bool]:
    """200DMA regime with a confirmed-breakdown buffer.

    Equities -> defensive only when close is below ``SMA * (1 - buffer)``.
    Defensive -> equities when close is back above the SMA. The first
    observation uses the plain close-vs-SMA state.
    """
    out: dict[str, bool] = {}
    q: deque[float] = deque()
    total = 0.0
    state: bool | None = None
    for d in dates:
        x = closes.get(d)
        if x is None:
            continue
        q.append(x)
        total += x
        if len(q) > window:
            total -= q.popleft()
        if len(q) < window:
            continue
        sma = total / window
        if state is None:
            state = x > sma
        elif state:
            if x < sma * (1.0 - buffer):
                state = False
        else:
            if x > sma:
                state = True
        out[d] = state
    return out


def build_clenow_selections(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
    regime: dict[str, bool],
):
    signal_set = {s for s, _ in pairs}
    exec_by_signal = {s: e for s, e in pairs}
    history = max(100, args.clenow_window, args.dma_exit)
    atr_history = args.atr_window + 1
    closes: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=history)
    )
    highs: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )
    lows: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )
    atr_closes: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )
    turns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))
    locked: dict[str, deque[bool]] = defaultdict(lambda: deque(maxlen=20))
    raw: dict[str, float] = {}
    last_seen: dict[str, str] = {}
    meta: dict[str, tuple[str, str]] = {}
    flags: dict[str, frozenset[str]] = {}
    names: dict[str, str] = {}
    selections: dict[str, list[dict]] = {}
    stock_selections: dict[str, list[dict]] = {}
    fresh_selections: dict[str, list[dict]] = {}
    universe: dict[str, list[tuple[str, float]]] = {}
    eligible_counts: dict[str, int] = {}
    liquid_counts: dict[str, int] = {}
    regime_off_counts: dict[str, int] = {}
    prev_target: list[dict] = []
    prev_regime_on = False
    signal_counter = 0
    if args.full_reconstitution_days <= 0:
        full_every = 1
    else:
        full_every = max(
            1,
            int(
                round(
                    args.full_reconstitution_days / args.rebalance_days
                )
            ),
        )
    current_date: str | None = None

    def flush(d: str) -> None:
        nonlocal prev_target, prev_regime_on, signal_counter
        if d not in signal_set:
            return
        eligible: list[dict] = []
        for sid, cs in closes.items():
            if len(cs) < max(args.clenow_window, args.dma_exit):
                continue
            if last_seen.get(sid) != d:
                continue
            if raw.get(sid, 0.0) < args.min_price:
                continue
            ts = turns[sid]
            if len(ts) < 20:
                continue
            turnover20 = sum(ts) / len(ts)
            if turnover20 < args.min_turnover:
                continue
            symbol, name = meta.get(sid, ("", ""))
            if is_excluded(symbol, name):
                continue
            if flags.get(sid, frozenset()) & RISK_FLAGS:
                continue
            if any(locked[sid]):
                continue
            if (
                len(highs[sid]) < args.atr_window + 1
                or len(lows[sid]) < args.atr_window + 1
                or len(atr_closes[sid]) < args.atr_window + 1
            ):
                continue
            atr = _atr(highs[sid], lows[sid], atr_closes[sid], args.atr_window)
            if atr <= 0:
                continue
            clenow = calculate_clenow_momentum(list(cs), args.clenow_window)
            if clenow <= 0:
                continue
            dma_values = list(cs)[-args.dma_exit:]
            dma100 = sum(dma_values) / len(dma_values)
            if cs[-1] <= dma100:
                continue
            eligible.append(
                {
                    "stock_id": sid,
                    "symbol": symbol,
                    "name": names.get(sid, name or symbol),
                    "clenow": clenow,
                    "atr20": atr,
                    "turnover20": turnover20,
                    "dma100": dma100,
                    "signal_close": raw.get(sid, 0.0),
                }
            )

        eligible_counts[d] = len(eligible)
        liquid = sorted(
            eligible, key=lambda x: (-x["turnover20"], x["stock_id"])
        )[: args.top_liquid]
        liquid_counts[d] = len(liquid)
        universe[d] = [(x["stock_id"], x["turnover20"]) for x in liquid]
        liquid_by_id = {x["stock_id"]: x for x in liquid}
        clenow_ranked = sorted(
            liquid, key=lambda x: (-x["clenow"], x["stock_id"])
        )
        rank_by_id = {
            x["stock_id"]: i for i, x in enumerate(clenow_ranked, 1)
        }
        ranked = clenow_ranked[: args.holdings]
        weights = inverse_vol_weights(ranked, args.max_weight)
        fresh_rows: list[dict] = []
        for rank, (row, weight) in enumerate(zip(ranked, weights), 1):
            item = dict(row)
            item["rank"] = rank
            item["weight"] = weight
            item["signal_date"] = d
            item["execution_date"] = exec_by_signal[d]
            item["rebalance_type"] = "fresh"
            fresh_rows.append(item)
        fresh_selections[d] = fresh_rows

        regime_on = regime.get(d, False)
        transition = regime_on != prev_regime_on
        if not regime_on:
            selections[d] = defensive_targets()
            stock_selections[d] = []
            prev_target = []
            prev_regime_on = False
            regime_off_counts[d] = 1
            signal_counter += 1
            print(
                f"signal {d}: eligible={len(eligible)} liquid={len(liquid)} "
                f"selected=0 regime=OFF type=defensive"
            )
            return

        do_full = transition or not prev_target or signal_counter % full_every == 0
        if do_full:
            target_rows = [dict(x) for x in fresh_rows]
            for rank, item in enumerate(target_rows, 1):
                item["rank"] = rank
                item["rebalance_type"] = "full"
            rebalance_type = "full"
        else:
            kept: list[dict] = []
            for prev in prev_target:
                row = liquid_by_id.get(prev["stock_id"])
                if row is None:
                    continue
                if rank_by_id.get(prev["stock_id"], 10**9) > args.exit_rank:
                    continue
                item = dict(row)
                item["weight"] = min(
                    float(prev.get("weight", 0.0)), args.max_weight
                )
                item["signal_date"] = d
                item["execution_date"] = exec_by_signal[d]
                item["rebalance_type"] = "topup"
                kept.append(item)
            kept_ids = {x["stock_id"] for x in kept}
            kept_weight = sum(x["weight"] for x in kept)
            if kept_weight > 1.0:
                for item in kept:
                    item["weight"] /= kept_weight
                kept_weight = 1.0
            remaining = max(0.0, 1.0 - kept_weight)
            slots = max(0, args.holdings - len(kept))
            new_candidates = [
                x for x in ranked if x["stock_id"] not in kept_ids
            ][:slots]
            new_weights = inverse_vol_weights(
                new_candidates, args.max_weight
            )
            new_total = sum(new_weights)
            if new_total > 0 and remaining > 0:
                scale = remaining / new_total
                new_weights = [w * scale for w in new_weights]
            else:
                new_weights = []
            target_rows = kept
            for row, weight in zip(new_candidates, new_weights):
                item = dict(row)
                item["weight"] = weight
                item["signal_date"] = d
                item["execution_date"] = exec_by_signal[d]
                item["rebalance_type"] = "topup"
                target_rows.append(item)
            target_rows.sort(key=lambda x: (-x["clenow"], x["stock_id"]))
            for rank, item in enumerate(target_rows, 1):
                item["rank"] = rank
            rebalance_type = "topup"

        stock_selections[d] = target_rows
        selections[d] = target_rows
        prev_target = target_rows
        prev_regime_on = True
        regime_off_counts[d] = 0
        signal_counter += 1
        print(
            f"signal {d}: eligible={len(eligible)} liquid={len(liquid)} "
            f"selected={len(target_rows)} regime=ON type={rebalance_type}"
        )

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d > args.end:
                break
            if d != current_date:
                if current_date is not None:
                    flush(current_date)
                current_date = d
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sid = row[ix["stock_id"]]
            symbol = row[ix["symbol"]]
            name = row[ix["name"]]
            if is_excluded(symbol, name):
                continue
            try:
                adj_close = float(row[ix["adj_close"]])
                adj_high = float(row[ix["adj_high"]])
                adj_low = float(row[ix["adj_low"]])
                raw_close = float(row[ix["close"]])
                turn = float(row[ix["turnover_lacs"]] or 0.0)
            except (TypeError, ValueError):
                continue
            if adj_close <= 0 or adj_high <= 0 or adj_low <= 0 or raw_close <= 0:
                continue
            closes[sid].append(adj_close)
            highs[sid].append(adj_high)
            lows[sid].append(adj_low)
            atr_closes[sid].append(adj_close)
            turns[sid].append(turn)
            locked[sid].append(adj_high <= adj_low * 1.0001)
            raw[sid] = raw_close
            last_seen[sid] = d
            meta[sid] = (symbol, name)
            flags[sid] = parse_flags(row[ix["flags"]])
            names[sid] = name or symbol
    if current_date is not None:
        flush(current_date)

    return (
        selections,
        stock_selections,
        fresh_selections,
        universe,
        eligible_counts,
        liquid_counts,
        regime_off_counts,
        names,
    )


def load_stock_prices(
    args: argparse.Namespace,
    selected_ids: set[str],
    first_exec: str,
):
    """Raw execution prices, adjusted closes, 100DMA and ATR20 by date."""
    opens: dict[str, dict[str, float]] = defaultdict(dict)
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    factors: dict[str, dict[str, float]] = defaultdict(dict)
    adj_closes: dict[str, dict[str, float]] = defaultdict(dict)
    dma100: dict[str, dict[str, float]] = defaultdict(dict)
    atr20: dict[str, dict[str, float]] = defaultdict(dict)
    history = max(100, args.dma_exit)
    atr_history = args.atr_window + 1
    q_close: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=history)
    )
    q_high: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )
    q_low: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )
    q_atr_close: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=atr_history)
    )

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d > args.end:
                break
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sid = row[ix["stock_id"]]
            if sid not in selected_ids:
                continue
            try:
                raw_open = float(row[ix["open"]])
                raw_close = float(row[ix["close"]])
                adj_close = float(row[ix["adj_close"]])
                adj_high = float(row[ix["adj_high"]])
                adj_low = float(row[ix["adj_low"]])
                factor = float(row[ix["adj_factor"]] or 1.0)
            except (TypeError, ValueError):
                continue
            if (
                raw_open <= 0
                or raw_close <= 0
                or adj_close <= 0
                or adj_high <= 0
                or adj_low <= 0
            ):
                continue
            q_close[sid].append(adj_close)
            q_high[sid].append(adj_high)
            q_low[sid].append(adj_low)
            q_atr_close[sid].append(adj_close)
            if d < first_exec:
                continue
            opens[sid][d] = raw_open
            closes[sid][d] = raw_close
            factors[sid][d] = factor
            adj_closes[sid][d] = adj_close
            if len(q_close[sid]) >= args.dma_exit:
                dma_values = list(q_close[sid])[-args.dma_exit:]
                dma100[sid][d] = sum(dma_values) / len(dma_values)
            if len(q_high[sid]) >= args.atr_window + 1:
                atr20[sid][d] = _atr(
                    q_high[sid], q_low[sid], q_atr_close[sid], args.atr_window
                )
    return opens, closes, factors, adj_closes, dma100, atr20


def load_goldbees(args: argparse.Namespace, first_exec: str):
    opens: dict[str, float] = {}
    closes: dict[str, float] = {}
    factors: dict[str, float] = {}
    with open(args.gold, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row["date"]
            if d < first_exec or d > args.end:
                continue
            try:
                o = float(row["open"])
                c = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
            if o <= 0 or c <= 0:
                continue
            opens[d] = o
            closes[d] = c
            factors[d] = 1.0
    return opens, closes, factors


def next_day(s: str) -> str:
    return (ddate.fromisoformat(s) + timedelta(days=1)).isoformat()


def period_cost_stats(run: dict, start: str, end: str) -> dict:
    curve = [r for r in run["curve"] if start <= r["date"] <= end]
    trades = [t for t in run["trades"] if start <= t["date"] <= end]
    if len(curve) < 2:
        return {
            "years": None,
            "avg_equity": None,
            "costs": None,
            "cost_drag_annual": None,
            "turnover_annual": None,
            "trades": 0,
        }
    first = curve[0]["date"]
    last = curve[-1]["date"]
    years = max(
        (ddate.fromisoformat(last) - ddate.fromisoformat(first)).days / 365.25,
        1e-9,
    )
    avg_equity = statistics.fmean(r["equity"] for r in curve)
    costs = sum(float(t.get("cost", 0.0)) for t in trades)
    buy_value = sum(
        float(t.get("value", 0.0)) for t in trades if t.get("side") == "BUY"
    )
    sell_value = sum(
        float(t.get("value", 0.0)) for t in trades if t.get("side") == "SELL"
    )
    return {
        "years": years,
        "avg_equity": avg_equity,
        "costs": costs,
        "cost_drag_annual": costs / avg_equity / years if avg_equity else None,
        "turnover_annual": (
            (buy_value + sell_value) / avg_equity / years if avg_equity else None
        ),
        "trades": len(trades),
    }


def evaluate_clenow_gate(
    train: dict,
    test: dict | None,
    train_stress: dict,
    test_stress: dict | None,
    train_cost: dict,
    test_cost: dict | None,
    nifty_tr_train: float | None,
    nifty_tr_test: float | None,
    train_rebalances: int,
    test_rebalances: int,
    min_test_rebalances: int,
) -> dict:
    def gt(x, y) -> bool:
        return x is not None and y is not None and x > y

    def ge(x, y) -> bool:
        return x is not None and y is not None and x >= y

    train_conditions = [
        {
            "name": "train_net_cagr_positive",
            "pass": gt(train.get("cagr"), 0.0),
            "value": train.get("cagr"),
            "threshold": 0.0,
        },
        {
            "name": "train_beats_nifty_tr_proxy",
            "pass": gt(train.get("cagr"), nifty_tr_train),
            "value": train.get("cagr"),
            "threshold": nifty_tr_train,
        },
        {
            "name": "train_net_sharpe_gt_0_5",
            "pass": gt(train.get("sharpe"), 0.5),
            "value": train.get("sharpe"),
            "threshold": 0.5,
        },
        {
            "name": "train_max_drawdown_within_28pct",
            "pass": ge(train.get("max_drawdown"), -0.28),
            "value": train.get("max_drawdown"),
            "threshold": -0.28,
        },
        {
            "name": "train_profit_factor_gt_1_2",
            "pass": gt(train.get("profit_factor"), 1.2),
            "value": train.get("profit_factor"),
            "threshold": 1.2,
        },
        {
            "name": "train_stress_2x_cagr_positive",
            "pass": gt(train_stress.get("cagr"), 0.0),
            "value": train_stress.get("cagr"),
            "threshold": 0.0,
        },
        {
            "name": "train_cost_drag_below_0_5pct",
            "pass": gt(0.005, train_cost.get("cost_drag_annual")),
            "value": train_cost.get("cost_drag_annual"),
            "threshold": 0.005,
        },
        {
            "name": "train_turnover_below_1_5x",
            "pass": gt(1.5, train_cost.get("turnover_annual")),
            "value": train_cost.get("turnover_annual"),
            "threshold": 1.5,
        },
        {
            "name": "train_rebalances_at_least_12",
            "pass": ge(train_rebalances, 12),
            "value": train_rebalances,
            "threshold": 12,
        },
    ]
    train_failed = [c["name"] for c in train_conditions if not c["pass"]]
    if train_failed:
        return {
            "decision": "TRAIN_FAIL",
            "train_conditions": train_conditions,
            "train_failed": train_failed,
            "test_conditions": [],
            "test_failed": [],
        }
    if test is None:
        return {
            "decision": "TRAIN_PASS",
            "train_conditions": train_conditions,
            "train_failed": [],
            "test_conditions": [],
            "test_failed": [],
        }

    test_conditions = [
        {
            "name": "test_net_cagr_positive",
            "pass": gt(test.get("cagr"), 0.0),
            "value": test.get("cagr"),
            "threshold": 0.0,
        },
        {
            "name": "test_beats_nifty_tr_proxy",
            "pass": gt(test.get("cagr"), nifty_tr_test),
            "value": test.get("cagr"),
            "threshold": nifty_tr_test,
        },
        {
            "name": "test_net_sharpe_positive",
            "pass": gt(test.get("sharpe"), 0.0),
            "value": test.get("sharpe"),
            "threshold": 0.0,
        },
        {
            "name": "test_max_drawdown_within_28pct",
            "pass": ge(test.get("max_drawdown"), -0.28),
            "value": test.get("max_drawdown"),
            "threshold": -0.28,
        },
        {
            "name": "test_profit_factor_gt_1_0",
            "pass": gt(test.get("profit_factor"), 1.0),
            "value": test.get("profit_factor"),
            "threshold": 1.0,
        },
        {
            "name": "test_stress_2x_cagr_positive",
            "pass": gt(test_stress.get("cagr"), 0.0) if test_stress else False,
            "value": test_stress.get("cagr") if test_stress else None,
            "threshold": 0.0,
        },
        {
            "name": "test_cost_drag_below_0_5pct",
            "pass": gt(0.005, (test_cost or {}).get("cost_drag_annual")),
            "value": (test_cost or {}).get("cost_drag_annual"),
            "threshold": 0.005,
        },
        {
            "name": "test_turnover_below_1_5x",
            "pass": gt(1.5, (test_cost or {}).get("turnover_annual")),
            "value": (test_cost or {}).get("turnover_annual"),
            "threshold": 1.5,
        },
        {
            "name": "test_rebalances_at_least_min",
            "pass": ge(test_rebalances, min_test_rebalances),
            "value": test_rebalances,
            "threshold": min_test_rebalances,
        },
    ]
    if test_rebalances < min_test_rebalances:
        return {
            "decision": "INSUFFICIENT_OOS",
            "train_conditions": train_conditions,
            "train_failed": [],
            "test_conditions": test_conditions,
            "test_failed": ["test_rebalances_at_least_min"],
        }
    test_failed = [c["name"] for c in test_conditions if not c["pass"]]
    return {
        "decision": "PASS" if not test_failed else "FAIL",
        "train_conditions": train_conditions,
        "train_failed": [],
        "test_conditions": test_conditions,
        "test_failed": test_failed,
    }


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.2f}%"


def num(x, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def append_bridge(
    summary: dict,
    run_1x: dict,
    run_2x: dict,
    train: dict,
    test: dict | None,
    full: dict,
    train_cost: dict,
    test_cost: dict | None,
    nifty_train: dict,
    nifty_test: dict | None,
    gate: dict,
    args: argparse.Namespace,
) -> None:
    path = os.path.join(ROOT, "bridge", "to_antigravity.md")
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "",
        "---",
        "",
        "## Clenow Momentum — Train-First Run",
        "",
        f"**Timestamp:** {ts}  ",
        f"**Phase:** {args.phase}  ",
        f"**Spec:** `docs/clenow-momentum-spec.md`  ",
        f"**Command:** `{' '.join(sys.argv)}`",
        "",
        "### Train (through 2024-12-10)",
        "",
        "| Metric | Strategy | Nifty 50 B&H | Nifty TR proxy |",
        "|---|---:|---:|---:|",
        f"| Net CAGR | {pct(train.get('cagr'))} | {pct(nifty_train.get('cagr'))} | {pct(add_dividend(nifty_train.get('cagr'), args.dividend_yield))} |",
        f"| Sharpe | {num(train.get('sharpe'))} | {num(nifty_train.get('sharpe'))} | — |",
        f"| Max drawdown | {pct(train.get('max_drawdown'))} | {pct(nifty_train.get('max_drawdown'))} | — |",
        f"| Profit factor | {num(train.get('profit_factor'))} | {num(nifty_train.get('profit_factor'))} | — |",
        f"| Cost drag / yr | {pct(train_cost.get('cost_drag_annual'))} | — | — |",
        f"| Turnover / yr | {num(train_cost.get('turnover_annual'))}x | — | — |",
        f"| 2x slippage CAGR | {pct(curve_stats(run_2x['curve'], run_2x['monthly'], end=args.split).get('cagr'))} | — | — |",
        "",
        f"**Train gate:** `{gate['decision']}`",
        "",
    ]
    if gate.get("train_failed"):
        lines.append(f"Failed train conditions: `{', '.join(gate['train_failed'])}`")
        lines.append("")
    if test is not None:
        lines.extend(
            [
                "### Test (after 2024-12-10)",
                "",
                f"- Net CAGR: **{pct(test.get('cagr'))}**",
                f"- Sharpe: **{num(test.get('sharpe'))}**",
                f"- Max drawdown: **{pct(test.get('max_drawdown'))}**",
                f"- Profit factor: **{num(test.get('profit_factor'))}**",
                f"- Cost drag / yr: **{pct((test_cost or {}).get('cost_drag_annual'))}**",
                f"- Turnover / yr: **{num((test_cost or {}).get('turnover_annual'))}x**",
                f"- Nifty TR proxy CAGR: **{pct(add_dividend((nifty_test or {}).get('cagr'), args.dividend_yield))}**",
                f"- Gate: **{gate['decision']}**",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Test was not run. This is the required train-first checkpoint.",
                "",
            ]
        )
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    if args.phase in ("test", "full") and not args.allow_test:
        raise SystemExit(
            "test/full requires --allow-test; run --phase train first"
        )
    if not 10 <= args.holdings <= 15:
        raise SystemExit("--holdings must be between 10 and 15")
    if args.rebalance_days <= 0:
        raise SystemExit("--rebalance-days must be positive")

    nifty_dates, nifty_closes, _ = load_nifty(args.nifty)
    regime = build_nifty_regime_hysteresis(
        nifty_dates,
        nifty_closes,
        args.regime_window,
        args.regime_buffer,
    )
    run_end = args.split if args.phase == "train" else args.end
    pairs = build_rebalance_pairs(
        nifty_dates,
        args.start,
        run_end,
        args.rebalance_days,
        warmup=max(100, args.clenow_window, args.dma_exit),
    )
    if not pairs:
        raise SystemExit("no rebalance pairs in range")
    print(
        f"pairs={len(pairs)} first={pairs[0]} last={pairs[-1]} "
        f"end={run_end} phase={args.phase}"
    )

    run_args = argparse.Namespace(**vars(args))
    run_args.end = run_end
    run_args.target_weight = args.max_weight
    run_args.writeoff_unlisted_only = True

    (
        selections,
        stock_selections,
        fresh_selections,
        universe,
        eligible_counts,
        liquid_counts,
        regime_off_counts,
        names,
    ) = build_clenow_selections(run_args, pairs, regime)
    if not selections:
        raise SystemExit("no selections produced")

    selected_ids = {
        x["stock_id"]
        for rows in stock_selections.values()
        for x in rows
    }
    selected_ids.add(LIQUIDBEES_ID)
    first_exec = pairs[0][1]
    opens, closes, factors, adj_closes, dma100, atr20 = load_stock_prices(
        run_args, selected_ids, first_exec
    )
    gold_opens, gold_closes, gold_factors = load_goldbees(run_args, first_exec)
    if not gold_closes:
        raise SystemExit("GOLDBEES series is empty")
    opens[GOLDBEES_ID] = gold_opens
    closes[GOLDBEES_ID] = gold_closes
    factors[GOLDBEES_ID] = gold_factors
    if not closes.get(LIQUIDBEES_ID):
        raise SystemExit("LIQUIDBEES series is empty")
    print(
        f"loaded prices: stocks={len(selected_ids) - 1} "
        f"gold={len(gold_closes)} liquid={len(closes.get(LIQUIDBEES_ID, {}))}"
    )

    turnover_lookup: dict[str, float] = {}
    for rows in stock_selections.values():
        for x in rows:
            sid = x["stock_id"]
            turnover_lookup[sid] = max(
                turnover_lookup.get(sid, 0.0), x["turnover20"]
            )
    turnover_lookup[GOLDBEES_ID] = 1e9
    turnover_lookup[LIQUIDBEES_ID] = 1e9

    def exit_predicate(sid: str, d: str) -> bool:
        if sid in DEFENSIVE_IDS:
            return False
        if sid not in dma100:
            return False
        ac = adj_closes.get(sid, {}).get(d)
        dma = dma100.get(sid, {}).get(d)
        return ac is not None and dma is not None and ac < dma

    def run(mult: float) -> dict:
        a = argparse.Namespace(**vars(run_args))
        a.slippage_mult = mult
        return run_portfolio(
            a,
            pairs,
            selections,
            opens,
            closes,
            factors,
            nifty_dates,
            nifty_closes,
            exit_predicate=(
                exit_predicate if args.daily_dma_exit else None
            ),
            turnover_lookup=turnover_lookup,
        )

    run_1x = run(1.0)
    run_2x = run(2.0)

    monthly_1x = run_1x["monthly"]
    monthly_2x = run_2x["monthly"]
    full = curve_stats(run_1x["curve"], monthly_1x)
    train = curve_stats(run_1x["curve"], monthly_1x, end=args.split)
    test = (
        curve_stats(run_1x["curve"], monthly_1x, start=next_day(args.split))
        if run_end > args.split
        else None
    )
    train_stress = curve_stats(
        run_2x["curve"], monthly_2x, end=args.split
    )
    test_stress = (
        curve_stats(run_2x["curve"], monthly_2x, start=next_day(args.split))
        if run_end > args.split
        else None
    )

    curve_start = run_1x["curve"][0]["date"]
    curve_end = run_1x["curve"][-1]["date"]
    train_cost = period_cost_stats(run_1x, curve_start, args.split)
    test_cost = (
        period_cost_stats(run_1x, next_day(args.split), curve_end)
        if run_end > args.split
        else None
    )
    full_cost = period_cost_stats(run_1x, curve_start, curve_end)
    train_rebalances = sum(
        1 for r in run_1x["rebalances"] if r["execution_date"] <= args.split
    )
    test_rebalances = sum(
        1 for r in run_1x["rebalances"] if r["execution_date"] > args.split
    )

    nifty_curve = [
        {"date": d, "equity": nifty_closes[d]}
        for d in nifty_dates
        if first_exec <= d <= run_end and d in nifty_closes
    ]
    nifty_monthly = monthly_from_curve(nifty_curve)
    nifty_full = curve_stats(nifty_curve, nifty_monthly)
    nifty_train = curve_stats(nifty_curve, nifty_monthly, end=args.split)
    nifty_test = (
        curve_stats(nifty_curve, nifty_monthly, start=next_day(args.split))
        if run_end > args.split
        else None
    )
    nifty_tr_train = add_dividend(nifty_train.get("cagr"), args.dividend_yield)
    nifty_tr_test = add_dividend(
        (nifty_test or {}).get("cagr"), args.dividend_yield
    )

    gate = evaluate_clenow_gate(
        train,
        test,
        train_stress,
        test_stress,
        train_cost,
        test_cost,
        nifty_tr_train,
        nifty_tr_test,
        train_rebalances,
        test_rebalances,
        args.min_test_rebalances,
    )
    if (
        gate["decision"] == "TRAIN_FAIL"
        and args.phase in ("test", "full")
        and not args.force_test
    ):
        print(
            "TRAIN GATE FAILED — suppressing test output; "
            "use --force-test to override"
        )
        test = None
        test_stress = None
        test_cost = None
        nifty_test = None
        test_rebalances = 0
        nifty_tr_test = None
        gate = evaluate_clenow_gate(
            train,
            None,
            train_stress,
            None,
            train_cost,
            None,
            nifty_tr_train,
            None,
            train_rebalances,
            0,
            args.min_test_rebalances,
        )

    os.makedirs(args.outdir, exist_ok=True)
    summary = {
        "strategy": "clenow_momentum_quarterly",
        "spec": "docs/clenow-momentum-spec.md",
        "args": vars(args),
        "run_end": run_end,
        "pairs": len(pairs),
        "first_signal": pairs[0][0],
        "last_signal": pairs[-1][0],
        "first_exec": first_exec,
        "last_exec": pairs[-1][1],
        "eligible_counts": eligible_counts,
        "liquid_counts": liquid_counts,
        "regime_off_counts": regime_off_counts,
        "selected_stock_ids": len(selected_ids) - 1,
        "run_1x": {
            "full": full,
            "train": train,
            "test": test,
            "full_cost": full_cost,
            "train_cost": train_cost,
            "test_cost": test_cost,
            "summary": run_1x["summary"],
        },
        "run_2x": {
            "full": curve_stats(run_2x["curve"], monthly_2x),
            "train": train_stress,
            "test": test_stress,
            "summary": run_2x["summary"],
        },
        "nifty": {
            "full": nifty_full,
            "train": nifty_train,
            "test": nifty_test,
            "train_tr_proxy": nifty_tr_train,
            "test_tr_proxy": nifty_tr_test,
        },
        "train_rebalances": train_rebalances,
        "test_rebalances": test_rebalances,
        "gate": gate,
    }
    with open(
        os.path.join(args.outdir, "summary_clenow_momentum.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(sanitize(summary), f, indent=2)
        f.write("\n")
    write_csv(
        os.path.join(args.outdir, "curve_clenow_momentum.csv"),
        run_1x["curve"],
    )
    write_csv(
        os.path.join(args.outdir, "curve_clenow_momentum_2x.csv"),
        run_2x["curve"],
    )
    write_csv(
        os.path.join(args.outdir, "trades_clenow_momentum.csv"),
        run_1x["trades"],
    )
    write_csv(
        os.path.join(args.outdir, "rebalances_clenow_momentum.csv"),
        run_1x["rebalances"],
    )
    write_csv(
        os.path.join(args.outdir, "holdings_clenow_momentum.csv"),
        run_1x["holdings"],
    )
    selection_rows = []
    for signal_date, rows in stock_selections.items():
        for x in rows:
            selection_rows.append(dict(x))
    write_csv(
        os.path.join(args.outdir, "selections_clenow_momentum.csv"),
        selection_rows,
    )
    fresh_rows = []
    for signal_date, rows in fresh_selections.items():
        for x in rows:
            fresh_rows.append(dict(x))
    write_csv(
        os.path.join(args.outdir, "fresh_selections_clenow_momentum.csv"),
        fresh_rows,
    )
    target_rows = []
    for signal_date, rows in selections.items():
        for x in rows:
            row = dict(x)
            row["signal_date"] = signal_date
            row["regime"] = "OFF" if x["stock_id"] in DEFENSIVE_IDS else "ON"
            target_rows.append(row)
    write_csv(
        os.path.join(args.outdir, "targets_clenow_momentum.csv"),
        target_rows,
    )

    print()
    print("=== TRAIN ===")
    print(
        f"net CAGR {pct(train.get('cagr'))} | Sharpe {num(train.get('sharpe'))} "
        f"| maxDD {pct(train.get('max_drawdown'))} | PF {num(train.get('profit_factor'))}"
    )
    print(
        f"Nifty B&H CAGR {pct(nifty_train.get('cagr'))} | "
        f"TR proxy {pct(nifty_tr_train)} | "
        f"Nifty maxDD {pct(nifty_train.get('max_drawdown'))}"
    )
    print(
        f"cost drag {pct(train_cost.get('cost_drag_annual'))} | "
        f"turnover {num(train_cost.get('turnover_annual'))}x | "
        f"2x CAGR {pct(train_stress.get('cagr'))} | "
        f"rebalances {train_rebalances}"
    )
    print(f"gate: {gate['decision']}")
    if gate.get("train_failed"):
        print("failed:", ", ".join(gate["train_failed"]))
    if test is not None:
        print()
        print("=== TEST ===")
        print(
            f"net CAGR {pct(test.get('cagr'))} | Sharpe {num(test.get('sharpe'))} "
            f"| maxDD {pct(test.get('max_drawdown'))} | PF {num(test.get('profit_factor'))}"
        )
        print(
            f"Nifty B&H CAGR {pct((nifty_test or {}).get('cagr'))} | "
            f"TR proxy {pct(nifty_tr_test)} | "
            f"cost drag {pct((test_cost or {}).get('cost_drag_annual'))} | "
            f"turnover {num((test_cost or {}).get('turnover_annual'))}x | "
            f"2x CAGR {pct((test_stress or {}).get('cagr'))}"
        )
        print(f"gate: {gate['decision']}")
        if gate.get("test_failed"):
            print("failed:", ", ".join(gate["test_failed"]))
    else:
        print("Test not run (train-first checkpoint).")

    if args.append_bridge:
        append_bridge(
            summary,
            run_1x,
            run_2x,
            train,
            test,
            full,
            train_cost,
            test_cost,
            nifty_train,
            nifty_test,
            gate,
            args,
        )
        print(f"appended report to bridge/to_antigravity.md")


if __name__ == "__main__":
    main()
