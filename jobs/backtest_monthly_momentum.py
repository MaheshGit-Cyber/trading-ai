#!/usr/bin/env python3
"""Phase 2A monthly cross-sectional momentum rotation backtest.

Rules (frozen draft: docs/phase2-hypothesis.md):

- NSE EQ, raw price >= Rs 20, 20D turnover >= Rs 1 crore.
- At each month-end close: 63-session and 126-session returns, excess versus
  Nifty 50, cross-sectional percentile rank, average of the two ranks.
- Top 10 by composite RS, equal weight at 10% of current equity.
- Execute at the open of the first trading session of the next month.
- Full delivery costs; optional 2x slippage stress.
- Daily mark-to-market, max drawdown, turnover and cost drag.

This is Phase 2A: the current 2020-2026 panel. It is preliminary. Phase 2B
requires 2010-2026 adjusted data before any product claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict, deque
from datetime import date as ddate

EXCLUDE_TOKENS = (
    "ETF",
    "BEES",
    "EXCHANGE TRADED",
    "MUTUAL FUND",
    "REIT",
    "INVIT",
)

# Budget-2026 equity-delivery cost model.
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
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--outdir", default="data/backtest_monthly")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--target-weight", type=float, default=0.10)
    p.add_argument("--start", default="2020-07-01")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--min-price", type=float, default=20.0)
    p.add_argument("--min-turnover", type=float, default=100.0)
    p.add_argument("--max-adv-pct", type=float, default=0.05)
    p.add_argument(
        "--slippage-mult",
        type=float,
        default=1.0,
        help="2.0 = stress test with doubled slippage",
    )
    p.add_argument(
        "--selection-mode",
        choices=("primary", "random"),
        default="primary",
        help="primary = top RS; random = random eligible top-N baseline",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--writeoff-days",
        type=int,
        default=90,
        help="write off a holding after this many calendar days without a "
        "traded price; 0 disables. Zero recovery is conservative.",
    )
    p.add_argument(
        "--master",
        default="data/nse_equity_master.csv",
        help="current NSE master; used to separate still-listed BE/BZ names "
        "from genuinely delisted names",
    )
    p.add_argument(
        "--writeoff-unlisted-only",
        action="store_true",
        help="write off only names absent from the current NSE master; a "
        "still-listed but suspended name is held at last close",
    )
    return p.parse_args()


def pct_ranks(values: list[float]) -> list[float]:
    """Average-rank percentile in [0, 1]; ties share the average rank."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg / (n - 1)
        i = j + 1
    return out


def slip_one_way(turnover20_lacs: float) -> float:
    if turnover20_lacs >= 1000.0:
        return 0.0010
    if turnover20_lacs >= 100.0:
        return 0.0025
    return 0.0050


def buy_cost(value: float, turnover20: float, mult: float) -> float:
    exchange = EXCHANGE * value
    sebi = SEBI * value
    gst = GST * (exchange + sebi)
    slip = slip_one_way(turnover20) * mult * value
    return STT_BUY * value + exchange + sebi + STAMP_BUY * value + gst + slip


def sell_cost(value: float, turnover20: float, mult: float) -> float:
    exchange = EXCHANGE * value
    sebi = SEBI * value
    gst = GST * (exchange + sebi)
    slip = slip_one_way(turnover20) * mult * value
    return STT_SELL * value + exchange + sebi + gst + DP_SELL + slip


def load_listed_ids(path: str) -> set[str]:
    """Current NSE master symbols and ISINs, in both raw and NSE: forms."""
    ids: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name.strip(): i for i, name in enumerate(header)}
        sym_i = ix.get("SYMBOL", 0)
        isin_i = ix.get("ISIN NUMBER")
        for row in reader:
            if sym_i < len(row):
                sym = row[sym_i].strip()
                if sym:
                    ids.add(sym)
                    ids.add(f"NSE:{sym}")
            if isin_i is not None and isin_i < len(row):
                isin = row[isin_i].strip()
                if isin:
                    ids.add(isin)
                    ids.add(f"NSE:{isin}")
    return ids


def load_nifty(path: str):
    closes: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                closes[row["date"]] = float(row["close"])
            except (KeyError, ValueError, TypeError):
                continue
    dates = sorted(closes)
    rets: dict[str, tuple[float | None, float | None]] = {}
    for i, d in enumerate(dates):
        r63 = closes[d] / closes[dates[i - 63]] - 1.0 if i >= 63 else None
        r126 = closes[d] / closes[dates[i - 126]] - 1.0 if i >= 126 else None
        rets[d] = (r63, r126)
    return dates, closes, rets


def build_month_pairs(nifty_dates: list[str], start: str, end: str):
    """Return [(signal_date, execution_date), ...].

    Signal is the last trading session of a month; execution is the next
    trading session, which is the first session of the next month.
    """
    by_month: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for i, d in enumerate(nifty_dates):
        if start <= d <= end:
            by_month[d[:7]].append((i, d))
    pairs = []
    for ym in sorted(by_month):
        last_i, last_d = by_month[ym][-1]
        if last_i + 1 >= len(nifty_dates):
            continue
        exec_d = nifty_dates[last_i + 1]
        if exec_d[:7] <= ym:
            continue
        if exec_d > end:
            continue
        pairs.append((last_d, exec_d))
    return pairs


def build_selections(
    args: argparse.Namespace,
    nifty_rets: dict[str, tuple[float | None, float | None]],
    pairs: list[tuple[str, str]],
):
    signal_set = {s for s, _ in pairs}
    exec_by_signal = {s: e for s, e in pairs}
    closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=127))
    turns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))
    raw: dict[str, float] = {}
    last_seen: dict[str, str] = {}
    meta: dict[str, tuple[str, str]] = {}
    selections: dict[str, list[dict]] = {}
    universe: dict[str, list[tuple[str, float]]] = {}
    eligible_counts: dict[str, int] = {}
    rng = random.Random(args.seed)
    current_date: str | None = None

    def flush(d: str) -> None:
        if d not in signal_set:
            return
        nr = nifty_rets.get(d)
        if nr is None or nr[0] is None or nr[1] is None:
            return
        scored = []
        uni = []
        for sid, cs in closes.items():
            if len(cs) < 127:
                continue
            if last_seen.get(sid) != d:
                continue
            if raw.get(sid, 0.0) < args.min_price:
                continue
            ts = turns[sid]
            if len(ts) < 20:
                continue
            t20 = sum(ts) / 20.0
            if t20 < args.min_turnover:
                continue
            sym, name = meta.get(sid, ("", ""))
            if any(tok in sym.upper() or tok in name.upper() for tok in EXCLUDE_TOKENS):
                continue
            r63 = cs[-1] / cs[-64] - 1.0
            r126 = cs[-1] / cs[-127] - 1.0
            scored.append((sid, r63 - nr[0], r126 - nr[1], t20, cs[-1]))
            uni.append((sid, cs[-1]))
        if len(scored) < args.top_n:
            return
        p63 = pct_ranks([x[1] for x in scored])
        p126 = pct_ranks([x[2] for x in scored])
        ranked = [
            {
                "stock_id": x[0],
                "ret63_excess": x[1],
                "ret126_excess": x[2],
                "turnover20": x[3],
                "signal_close": x[4],
                "rs_pct": (p63[i] + p126[i]) / 2.0,
            }
            for i, x in enumerate(scored)
        ]
        ranked.sort(key=lambda r: (-r["rs_pct"], r["stock_id"]))
        if args.selection_mode == "random":
            chosen = rng.sample(ranked, args.top_n)
            chosen.sort(key=lambda r: r["stock_id"])
        else:
            chosen = ranked[: args.top_n]
        for i, row in enumerate(chosen, 1):
            row["rank"] = i
            row["signal_date"] = d
            row["execution_date"] = exec_by_signal[d]
        selections[d] = chosen
        universe[d] = uni
        eligible_counts[d] = len(scored)

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
            try:
                c = float(row[ix["adj_close"]])
                raw_c = float(row[ix["close"]])
                turn = float(row[ix["turnover_lacs"]] or 0.0)
            except (TypeError, ValueError):
                continue
            closes[sid].append(c)
            turns[sid].append(turn)
            raw[sid] = raw_c
            last_seen[sid] = d
            meta[sid] = (row[ix["symbol"]], row[ix["name"]])
    if current_date is not None:
        flush(current_date)
    return selections, universe, eligible_counts


def load_selected_prices(
    args: argparse.Namespace,
    selected_ids: set[str],
    first_exec: str,
):
    opens: dict[str, dict[str, float]] = defaultdict(dict)
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    factors: dict[str, dict[str, float]] = defaultdict(dict)
    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d < first_exec:
                continue
            if d > args.end:
                break
            if row[ix["market"]] != "NSE" or row[ix["series"]] not in (
                "EQ",
                "BE",
                "BZ",
            ):
                continue
            sid = row[ix["stock_id"]]
            if sid not in selected_ids:
                continue
            try:
                opens[sid][d] = float(row[ix["open"]])
                closes[sid][d] = float(row[ix["close"]])
                factors[sid][d] = float(row[ix["adj_factor"]])
            except (TypeError, ValueError):
                continue
    return opens, closes, factors


def max_drawdown(curve: list[dict]) -> tuple[float, str | None, str | None]:
    peak = None
    peak_date = None
    worst = 0.0
    worst_peak_date = None
    worst_date = None
    for row in curve:
        e = row["equity"]
        if peak is None or e > peak:
            peak = e
            peak_date = row["date"]
        dd = e / peak - 1.0 if peak else 0.0
        if dd < worst:
            worst = dd
            worst_peak_date = peak_date
            worst_date = row["date"]
    return worst, worst_peak_date, worst_date


def period_return(
    curve: list[dict], start: str, end: str | None = None
) -> float | None:
    sub = [
        r
        for r in curve
        if r["date"] >= start and (end is None or r["date"] <= end)
    ]
    if len(sub) < 2:
        return None
    return sub[-1]["equity"] / sub[0]["equity"] - 1.0


def daily_stats(curve: list[dict]) -> dict:
    rets = [
        curve[i]["equity"] / curve[i - 1]["equity"] - 1.0
        for i in range(1, len(curve))
    ]
    if not rets:
        return {"sharpe": None, "sortino": None, "vol_annual": None}
    mu = statistics.fmean(rets)
    sd = statistics.pstdev(rets)
    downside = [min(0.0, r) for r in rets]
    dsd = math.sqrt(sum(x * x for x in downside) / len(downside))
    return {
        "sharpe": (mu / sd * math.sqrt(252.0)) if sd else None,
        "sortino": (mu / dsd * math.sqrt(252.0)) if dsd else None,
        "vol_annual": sd * math.sqrt(252.0),
    }


def run_portfolio(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
    selections: dict[str, list[dict]],
    opens: dict[str, dict[str, float]],
    closes: dict[str, dict[str, float]],
    factors: dict[str, dict[str, float]],
    nifty_dates: list[str],
    nifty_closes: dict[str, float],
    *,
    exit_predicate=None,
    turnover_lookup=None,
):
    first_exec = pairs[0][1]
    last_signal = pairs[-1][0]
    rebalance = {
        exec_d: selections[s]
        for s, exec_d in pairs
        if s in selections
    }
    signal_by_exec = {exec_d: s for s, exec_d in pairs}
    dates = [d for d in nifty_dates if first_exec <= d <= args.end]
    cash = args.capital
    holdings: dict[str, int] = {}
    last_close: dict[str, float] = {}
    last_price_date: dict[str, str] = {}
    last_date_by_sid = {
        sid: max(prices) for sid, prices in closes.items() if prices
    }
    listed_ids = (
        load_listed_ids(args.master) if args.writeoff_unlisted_only else set()
    )
    last_factor: dict[str, float] = {}
    pending_sells: set[str] = set()
    curve = []
    rebalances = []
    trades = []
    total_costs = 0.0
    total_buy_value = 0.0
    total_sell_value = 0.0
    total_writeoff_value = 0.0
    writeoff_count = 0
    sum_exposure = 0.0
    max_holdings = 0
    holdings_snapshots: list[dict] = []
    sum_stale_pct = 0.0
    max_stale_pct = 0.0
    max_stale_count = 0

    for d in dates:
        # Apply corporate-action share adjustments before any trading.
        for sid in list(holdings):
            f = factors.get(sid, {}).get(d)
            if f is None:
                continue
            old = last_factor.get(sid)
            if old is not None and old > 0 and f != old:
                holdings[sid] = max(1, int(round(holdings[sid] * f / old)))
            last_factor[sid] = f

        sel_today = rebalance.get(d)
        target_today = {x["stock_id"] for x in sel_today} if sel_today else set()

        # Pending exit orders execute on the first session with a valid open,
        # not only on the next monthly rebalance. If the stock re-enters the
        # target, cancel the pending exit.
        for sid in list(pending_sells):
            if sid in target_today:
                pending_sells.discard(sid)
                continue
            p = opens.get(sid, {}).get(d)
            if p is None or p <= 0:
                continue
            qty = holdings.get(sid, 0)
            if qty <= 0:
                pending_sells.discard(sid)
                continue
            value = p * qty
            t20 = (turnover_lookup or {}).get(sid, 0.0)
            cost = sell_cost(value, t20, args.slippage_mult)
            cash += value - cost
            total_costs += cost
            total_sell_value += value
            trades.append(
                {
                    "date": d, "stock_id": sid, "side": "SELL",
                    "qty": qty, "price": p, "value": value, "cost": cost,
                    "reason": "pending_exit",
                }
            )
            del holdings[sid]
            pending_sells.discard(sid)

        sel = sel_today
        if sel is not None:
            def px_open(sid: str) -> float | None:
                p = opens.get(sid, {}).get(d)
                if p is None:
                    p = last_close.get(sid)
                return p

            equity_open = cash + sum(
                qty * (px_open(sid) or 0.0) for sid, qty in holdings.items()
            )
            target_ids = {x["stock_id"] for x in sel}
            target_by_id = {x["stock_id"]: x for x in sel}

            # Sells first: names leaving the target.
            for sid in list(holdings):
                if sid in target_ids:
                    continue
                p = opens.get(sid, {}).get(d)
                if p is None or p <= 0:
                    pending_sells.add(sid)
                    continue
                qty = holdings[sid]
                value = p * qty
                t20 = (turnover_lookup or {}).get(sid, 0.0)
                cost = sell_cost(value, t20, args.slippage_mult)
                cash += value - cost
                total_costs += cost
                total_sell_value += value
                trades.append(
                    {
                        "date": d, "stock_id": sid, "side": "SELL",
                        "qty": qty, "price": p, "value": value, "cost": cost,
                        "reason": "leave_top_n",
                    }
                )
                del holdings[sid]

            # Desired quantities at the new equal weight.
            desired: dict[str, int] = {}
            for sid, x in target_by_id.items():
                p = opens.get(sid, {}).get(d)
                if p is None or p <= 0:
                    continue
                target_value = x.get("weight", args.target_weight) * equity_open
                adv_cap = x["turnover20"] * 100_000.0 * args.max_adv_pct
                target_value = min(target_value, adv_cap)
                qty = int(target_value / p)
                if qty > 0:
                    desired[sid] = qty

            # Reductions.
            for sid, tq in desired.items():
                cur = holdings.get(sid, 0)
                if tq >= cur:
                    continue
                p = opens[sid][d]
                qty = cur - tq
                value = p * qty
                cost = sell_cost(value, target_by_id[sid]["turnover20"], args.slippage_mult)
                cash += value - cost
                total_costs += cost
                total_sell_value += value
                trades.append(
                    {
                        "date": d, "stock_id": sid, "side": "SELL",
                        "qty": qty, "price": p, "value": value, "cost": cost,
                        "reason": "rebalance_down",
                    }
                )
                if tq == 0:
                    del holdings[sid]
                else:
                    holdings[sid] = tq

            # Buys. Scale if needed so cash never goes negative after costs.
            buys = []
            for sid, tq in desired.items():
                cur = holdings.get(sid, 0)
                if tq > cur:
                    p = opens[sid][d]
                    buys.append((sid, tq - cur, p, target_by_id[sid]))
            if buys:
                full_value = sum(q * p for _, q, p, _ in buys)
                full_cost = sum(
                    buy_cost(q * p, x["turnover20"], args.slippage_mult)
                    for _, q, p, x in buys
                )
                scale = 1.0
                if full_value + full_cost > cash and full_value > 0:
                    scale = max(0.0, cash / (full_value + full_cost))
                for sid, q, p, x in buys:
                    q = int(q * scale)
                    if q < 1:
                        continue
                    value = q * p
                    cost = buy_cost(value, x["turnover20"], args.slippage_mult)
                    # Trim if the estimated cost would overdraw cash.
                    while q > 0 and value + cost > cash:
                        q = int(q * 0.99)
                        value = q * p
                        cost = buy_cost(value, x["turnover20"], args.slippage_mult)
                    if q < 1:
                        continue
                    cash -= value + cost
                    total_costs += cost
                    total_buy_value += value
                    holdings[sid] = holdings.get(sid, 0) + q
                    last_price_date[sid] = d
                    last_factor[sid] = factors.get(
                        sid, {}
                    ).get(d, last_factor.get(sid, 1.0))
                    trades.append(
                        {
                            "date": d, "stock_id": sid, "side": "BUY",
                            "qty": q, "price": p, "value": value, "cost": cost,
                            "reason": "enter_or_rebalance",
                        }
                    )

            # Drop zero positions.
            holdings = {sid: q for sid, q in holdings.items() if q > 0}
            max_holdings = max(max_holdings, len(holdings))
            signal_date = signal_by_exec.get(d, "")
            snapshot = []
            for sid, q in holdings.items():
                price = px_open(sid) or 0.0
                snapshot.append(
                    {
                        "signal_date": signal_date,
                        "execution_date": d,
                        "stock_id": sid,
                        "qty": q,
                        "price": price,
                        "value": q * price,
                        "in_target": sid in target_ids,
                    }
                )
            holdings_snapshots.extend(snapshot)
            stale = [x for x in snapshot if not x["in_target"]]
            stale_value = sum(x["value"] for x in stale)
            stale_pct = stale_value / equity_open if equity_open > 0 else 0.0
            sum_stale_pct += stale_pct
            max_stale_pct = max(max_stale_pct, stale_pct)
            max_stale_count = max(max_stale_count, len(stale))
            rebalances.append(
                {
                    "signal_date": signal_date,
                    "execution_date": d,
                    "equity_open": equity_open,
                    "cash_after": cash,
                    "holdings": len(holdings),
                    "stale_count": len(stale),
                    "stale_value": stale_value,
                    "stale_pct": stale_pct,
                    "target": ",".join(sorted(target_ids)),
                }
            )

        # Daily mark-to-market.
        for sid in holdings:
            p = closes.get(sid, {}).get(d)
            if p is not None:
                last_close[sid] = p
                last_price_date[sid] = d

        # Optional daily exit hook. A true result queues the position for the
        # next session's open; the default (None) preserves the old behaviour.
        if exit_predicate is not None:
            for sid in list(holdings):
                if exit_predicate(sid, d):
                    pending_sells.add(sid)

        # Conservative delisting/stale-position policy: after a long period
        # without any traded price, assume zero recovery. Without this, a
        # suspended stock is marked at its last close forever and can dominate
        # the portfolio without being sellable.
        if args.writeoff_days > 0:
            today = ddate.fromisoformat(d)
            for sid in list(holdings):
                seen = last_price_date.get(sid)
                if not seen:
                    continue
                if args.writeoff_unlisted_only and sid in listed_ids:
                    continue
                # Only write off a name that never trades again in the panel.
                # A temporary suspension (future rows exist) is held at its
                # last close, exactly as a real locked position would be.
                if last_date_by_sid.get(sid, "") > d:
                    continue
                if (today - ddate.fromisoformat(seen)).days <= args.writeoff_days:
                    continue
                qty = holdings.pop(sid)
                px = last_close.get(sid, 0.0)
                lost = qty * px
                total_writeoff_value += lost
                writeoff_count += 1
                pending_sells.discard(sid)
                trades.append(
                    {
                        "date": d,
                        "stock_id": sid,
                        "side": "WRITEOFF",
                        "qty": qty,
                        "price": px,
                        "value": 0.0,
                        "cost": 0.0,
                        "reason": "stale_writeoff",
                    }
                )

        mtm = sum(q * last_close.get(sid, 0.0) for sid, q in holdings.items())
        equity = cash + mtm
        exposure = (equity - cash) / equity if equity > 0 else 0.0
        sum_exposure += exposure
        curve.append(
            {
                "date": d,
                "cash": cash,
                "mtm": mtm,
                "equity": equity,
                "holdings": len(holdings),
                "exposure": exposure,
            }
        )

    dd, peak_date, dd_date = max_drawdown(curve)
    first = curve[0]["date"]
    last = curve[-1]["date"]
    years = max(
        (ddate.fromisoformat(last) - ddate.fromisoformat(first)).days / 365.25,
        1e-9,
    )
    final_equity = curve[-1]["equity"]
    total_return = final_equity / args.capital - 1.0
    cagr = (final_equity / args.capital) ** (1.0 / years) - 1.0
    avg_equity = statistics.fmean(r["equity"] for r in curve)
    turnover = (total_buy_value + total_sell_value) / avg_equity / years
    cost_drag = total_costs / avg_equity / years

    # Monthly returns from the daily curve.
    monthly = []
    last_by_month: dict[str, float] = {}
    for r in curve:
        last_by_month[r["date"][:7]] = r["equity"]
    prev = args.capital
    for ym in sorted(last_by_month):
        eq = last_by_month[ym]
        monthly.append({"month": ym, "equity": eq, "return": eq / prev - 1.0})
        prev = eq

    # By calendar year, using the last equity of each year.
    by_year = {}
    last_by_year: dict[str, float] = {}
    for r in curve:
        last_by_year[r["date"][:4]] = r["equity"]
    prev = args.capital
    for y in sorted(last_by_year):
        eq = last_by_year[y]
        by_year[y] = {"return": eq / prev - 1.0, "equity": eq}
        prev = eq

    # Nifty buy-and-hold over the same window.
    nifty_curve = []
    for d in dates:
        p = nifty_closes.get(d)
        if p is not None:
            nifty_curve.append({"date": d, "equity": p})
    nifty_dd, _, _ = max_drawdown(nifty_curve)
    nifty_first = nifty_curve[0]["equity"]
    nifty_last = nifty_curve[-1]["equity"]
    nifty_cagr = (nifty_last / nifty_first) ** (1.0 / years) - 1.0
    stats = daily_stats(curve)

    return {
        "curve": curve,
        "monthly": monthly,
        "trades": trades,
        "rebalances": rebalances,
        "holdings": holdings_snapshots,
        "summary": {
            "first_date": first,
            "last_date": last,
            "years": years,
            "final_equity": final_equity,
            "total_return": total_return,
            "cagr": cagr,
            "max_drawdown": dd,
            "max_drawdown_peak": peak_date,
            "max_drawdown_trough": dd_date,
            "avg_exposure": sum_exposure / len(curve),
            "max_holdings": max_holdings,
            "avg_stale_pct": (
                sum_stale_pct / len(rebalances) if rebalances else 0.0
            ),
            "max_stale_pct": max_stale_pct,
            "max_stale_count": max_stale_count,
            "rebalances": len(rebalances),
            "trades": len(trades),
            "total_costs": total_costs,
            "writeoff_days": args.writeoff_days,
            "writeoff_unlisted_only": args.writeoff_unlisted_only,
            "writeoff_count": writeoff_count,
            "writeoff_value": total_writeoff_value,
            "writeoff_pct_of_capital": total_writeoff_value / args.capital,
            "turnover_annual": turnover,
            "cost_drag_annual": cost_drag,
            "test_2025_2026_return": period_return(curve, "2025-01-01"),
            "return_2025": period_return(curve, "2025-01-01", "2025-12-31"),
            "return_2026": period_return(curve, "2026-01-01"),
            "sharpe": stats["sharpe"],
            "sortino": stats["sortino"],
            "vol_annual": stats["vol_annual"],
            "calmar": (cagr / abs(dd)) if dd else None,
            "nifty_buy_hold": {
                "cagr": nifty_cagr,
                "total_return": nifty_last / nifty_first - 1.0,
                "max_drawdown": nifty_dd,
                "test_2025_2026_return": period_return(nifty_curve, "2025-01-01"),
            },
            "by_year": by_year,
            "avg_equity": avg_equity,
        },
    }


def equal_weight_benchmark(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
    universe: dict[str, list[tuple[str, float]]],
    nifty_dates: list[str],
):
    """Monthly equal-weight eligible-universe benchmark, gross of costs."""
    monthly = []
    prev_map: dict[str, float] | None = None
    equity = args.capital
    for signal, _exec in pairs:
        cur = {sid: px for sid, px in universe.get(signal, [])}
        if prev_map:
            rets = [
                cur[sid] / px - 1.0
                for sid, px in prev_map.items()
                if sid in cur and px > 0
            ]
            if rets:
                r = statistics.fmean(rets)
                equity *= 1.0 + r
                monthly.append({"month": signal[:7], "return": r, "equity": equity})
        prev_map = cur
    if not monthly:
        return {"cagr": None, "total_return": None, "max_drawdown": None}
    first = monthly[0]["equity"] / (1.0 + monthly[0]["return"])
    last = monthly[-1]["equity"]
    years = len(monthly) / 12.0
    cagr = (last / first) ** (1.0 / years) - 1.0
    peak = first
    worst = 0.0
    for r in monthly:
        peak = max(peak, r["equity"])
        worst = min(worst, r["equity"] / peak - 1.0)
    rets = [r["return"] for r in monthly]
    ret_sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    return {
        "cagr": cagr,
        "total_return": last / first - 1.0,
        "max_drawdown": worst,
        "months": len(monthly),
        "sharpe": (
            statistics.fmean(rets) / ret_sd * math.sqrt(12.0)
            if ret_sd
            else None
        ),
        "monthly": monthly,
    }


def write_outputs(args, result, selections, eligible_counts):
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "summary_monthly_momentum.json"), "w") as f:
        json.dump(
            {
                "setup": "monthly_cross_sectional_momentum",
                "phase": "2A_preliminary",
                "panel": args.panel,
                "nifty": args.nifty,
                "selection_mode": args.selection_mode,
                "seed": args.seed,
                "capital": args.capital,
                "top_n": args.top_n,
                "target_weight": args.target_weight,
                "slippage_mult": args.slippage_mult,
                "universe": "NSE EQ; raw price >= 20; 20D turnover >= 100 lacs; ETF/REIT/InvIT excluded",
                "signal_rule": "month-end close, execute next month first open",
                "monthly_signals": len(selections),
                "eligible_counts": {
                    "min": min(eligible_counts.values()) if eligible_counts else 0,
                    "median": statistics.median(eligible_counts.values()) if eligible_counts else 0,
                    "max": max(eligible_counts.values()) if eligible_counts else 0,
                },
                "portfolio": result["summary"],
            },
            f,
            indent=2,
        )
    with open(os.path.join(args.outdir, "equity_curve.csv"), "w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "cash", "mtm", "equity", "holdings", "exposure"]
        )
        w.writeheader()
        w.writerows(result["curve"])
    with open(os.path.join(args.outdir, "monthly_returns.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "equity", "return"])
        w.writeheader()
        w.writerows(result["monthly"])
    ew_monthly = result["summary"].get("equal_weight_universe", {}).get(
        "monthly", []
    )
    if ew_monthly:
        with open(
            os.path.join(args.outdir, "equal_weight_monthly.csv"), "w", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=["month", "return", "equity"])
            w.writeheader()
            w.writerows(ew_monthly)
    excess = result["summary"].get("excess_vs_equal_weight", {}).get("monthly", [])
    if excess:
        with open(
            os.path.join(args.outdir, "monthly_excess.csv"), "w", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=["month", "excess"])
            w.writeheader()
            w.writerows(excess)
    with open(os.path.join(args.outdir, "rebalance_trades.csv"), "w", newline="") as f:
        fields = ["date", "stock_id", "side", "qty", "price", "value", "cost", "reason"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in result["trades"]:
            w.writerow({k: t.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "selections.csv"), "w", newline="") as f:
        fields = [
            "signal_date", "execution_date", "rank", "stock_id", "rs_pct",
            "ret63_excess", "ret126_excess", "turnover20", "signal_close",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in sorted(selections):
            for row in selections[d]:
                w.writerow({k: row.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "rebalances.csv"), "w", newline="") as f:
        fields = [
            "signal_date",
            "execution_date",
            "equity_open",
            "cash_after",
            "holdings",
            "stale_count",
            "stale_value",
            "stale_pct",
            "target",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in result["rebalances"]:
            w.writerow({k: r.get(k, "") for k in fields})
    with open(os.path.join(args.outdir, "holdings.csv"), "w", newline="") as f:
        fields = [
            "signal_date",
            "execution_date",
            "stock_id",
            "qty",
            "price",
            "value",
            "in_target",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in result["holdings"]:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> None:
    args = parse_args()
    nifty_dates, nifty_closes, nifty_rets = load_nifty(args.nifty)
    pairs = build_month_pairs(nifty_dates, args.start, args.end)
    if not pairs:
        raise SystemExit("no monthly rebalance pairs in range")
    print(f"rebalance pairs: {len(pairs)} first={pairs[0]} last={pairs[-1]}")
    selections, universe, eligible_counts = build_selections(args, nifty_rets, pairs)
    if not selections:
        raise SystemExit("no monthly selections")
    selected_ids = {x["stock_id"] for rows in selections.values() for x in rows}
    first_exec = pairs[0][1]
    opens, closes, factors = load_selected_prices(args, selected_ids, first_exec)
    result = run_portfolio(
        args, pairs, selections, opens, closes, factors, nifty_dates, nifty_closes
    )
    ew = equal_weight_benchmark(args, pairs, universe, nifty_dates)
    result["summary"]["equal_weight_universe"] = ew
    strat_by_month = {r["month"]: r["return"] for r in result["monthly"]}
    ew_by_month = {r["month"]: r["return"] for r in ew.get("monthly", [])}
    common = sorted(set(strat_by_month) & set(ew_by_month))
    excess = [strat_by_month[m] - ew_by_month[m] for m in common]
    if len(excess) > 2:
        mu = statistics.fmean(excess)
        sd = statistics.pstdev(excess)
        result["summary"]["excess_vs_equal_weight"] = {
            "months": len(excess),
            "mean_monthly": mu,
            "t_stat": mu / (sd / math.sqrt(len(excess))) if sd else None,
            "hit_rate": sum(1 for x in excess if x > 0) / len(excess),
            "monthly": [
                {"month": m, "excess": strat_by_month[m] - ew_by_month[m]}
                for m in common
            ],
        }
    write_outputs(args, result, selections, eligible_counts)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
