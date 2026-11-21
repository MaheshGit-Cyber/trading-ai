#!/usr/bin/env python3
"""Quantum Simulation Lab: 3-state macro-regime switching with anti-overfitting.

Spec: ``docs/quantum-simulation-lab-spec.md``.

This is an experimental lab, not a production strategy. It uses only the
2010-01-01 .. 2024-12-10 train/validation window. The 2024-12-11 onward frozen
test is never loaded or evaluated.

The four shields:

1. Occam: only three structural states from Nifty 50DMA/200DMA, no micro
   parameter search.
2. Walk-forward: in-sample 2010-2018, validation 2019-2024-12-10, frozen test
   after 2024-12-10.
3. Monte Carlo: 1,000 block-bootstrap paths; 5th percentile CAGR must be
   positive and 5th percentile max drawdown must be no worse than -30%.
4. Deflated Sharpe: Bailey / Lopez de Prado DSR with an honest trial count.

State routing:

- State 1 (bull): Nifty > 200DMA and 50DMA > 200DMA -> Clenow top 10.
- State 2 (sideways/transition): otherwise, with Nifty >= 200DMA -> 50%
  NIFTYBEES + 50% LIQUIDBEES.
- State 3 (crisis): Nifty < 200DMA -> 50% GOLDBEES + 50% LIQUIDBEES.

The precedence is crisis first, then bull, then sideways. This makes the three
states mutually exclusive and exhaustive.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import os
import random
import statistics
import sys
from collections import deque
from datetime import datetime
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jobs.backtest_a2_momentum import (  # noqa: E402
    curve_stats,
    monthly_from_curve,
    sanitize,
    write_csv,
)
from jobs.backtest_clenow_momentum import (  # noqa: E402
    GOLDBEES_ID,
    LIQUIDBEES_ID,
    build_clenow_selections,
    load_goldbees,
    load_stock_prices,
)
from jobs.backtest_monthly_momentum import build_month_pairs, run_portfolio  # noqa: E402
from jobs.deflated_sharpe import dsr_stats  # noqa: E402

NIFTYBEES_ID = "NSE:INF732E01011"
FROZEN_TEST_START = "2024-12-11"
SPLIT = "2024-12-10"
IS_END = "2018-12-31"
OOS_START = "2019-01-01"
DEFENSIVE_IDS = (GOLDBEES_ID, LIQUIDBEES_ID, NIFTYBEES_ID)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel_nse_isin_v3.csv")
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--gold", default="data/gold/goldbees_daily_2010_2026.csv")
    p.add_argument("--master", default="data/nse_equity_master.csv")
    p.add_argument("--outdir", default="data/backtest/quantum_simulation_lab")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--is-end", default=IS_END)
    p.add_argument("--oos-start", default=OOS_START)
    p.add_argument("--split", default=SPLIT)
    p.add_argument(
        "--end",
        default=SPLIT,
        help="must not exceed the split; OOS2 is frozen",
    )
    p.add_argument("--min-price", type=float, default=20.0)
    p.add_argument("--min-turnover", type=float, default=1000.0)
    p.add_argument("--top-liquid", type=int, default=100)
    p.add_argument("--holdings", type=int, default=10)
    p.add_argument("--max-weight", type=float, default=0.10)
    p.add_argument("--max-adv-pct", type=float, default=0.05)
    p.add_argument("--clenow-window", type=int, default=90)
    p.add_argument("--dma-exit", type=int, default=100)
    p.add_argument("--atr-window", type=int, default=20)
    p.add_argument("--trials", type=int, default=100)
    p.add_argument("--mc-paths", type=int, default=1000)
    p.add_argument("--mc-block", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--append-bridge", action="store_true")
    return p.parse_args()


def validate_window(end: str, split: str = SPLIT) -> None:
    """Hard guard: the frozen test set must never be loaded."""
    if end > split:
        raise SystemExit(
            f"--end {end} is beyond the frozen split {split}; "
            "OOS2 is strictly untouched"
        )


def load_nifty_until(path: str, end: str):
    """Load Nifty closes only through ``end``; no OOS2 rows enter memory."""
    closes: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = row.get("date", "")
            if d > end:
                break
            try:
                closes[d] = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(closes), closes


def classify_regime(close: float, sma50: float, sma200: float) -> int:
    """Return 1=bull, 2=sideways/transition, 3=crisis.

    Crisis takes precedence, then bull, then sideways. This is the only
    structural state rule; no thresholds are tuned.
    """
    if close < sma200:
        return 3
    if close > sma200 and sma50 > sma200:
        return 1
    return 2


def build_regime_states(
    dates: list[str],
    closes: dict[str, float],
    fast: int = 50,
    slow: int = 200,
) -> dict[str, int]:
    """Point-in-time 3-state labels from trailing SMAs only."""
    q_fast: deque[float] = deque()
    q_slow: deque[float] = deque()
    sum_fast = 0.0
    sum_slow = 0.0
    out: dict[str, int] = {}
    for d in dates:
        x = closes.get(d)
        if x is None:
            continue
        q_fast.append(x)
        sum_fast += x
        if len(q_fast) > fast:
            sum_fast -= q_fast.popleft()
        q_slow.append(x)
        sum_slow += x
        if len(q_slow) > slow:
            sum_slow -= q_slow.popleft()
        if len(q_fast) < fast or len(q_slow) < slow:
            continue
        out[d] = classify_regime(x, sum_fast / fast, sum_slow / slow)
    return out


def _etf_target(
    stock_id: str,
    symbol: str,
    name: str,
    weight: float,
    rank: int,
) -> dict:
    return {
        "stock_id": stock_id,
        "symbol": symbol,
        "name": name,
        "weight": weight,
        "turnover20": 1e9,
        "atr20": 0.0,
        "clenow": 0.0,
        "rank": rank,
    }


def build_state_targets(state: int, clenow_rows: list[dict]) -> list[dict]:
    """Map a macro state to target rows. Cash is the default fallback."""
    if state == 1:
        rows = [dict(x) for x in clenow_rows]
        if rows:
            return rows
        # No eligible Clenow names in a bull tape: hold the low-beta anchor.
        return [
            _etf_target(NIFTYBEES_ID, "NIFTYBEES", "Nifty BeES", 0.5, 1),
            _etf_target(LIQUIDBEES_ID, "LIQUIDBEES", "Liquid BeES", 0.5, 2),
        ]
    if state == 2:
        return [
            _etf_target(NIFTYBEES_ID, "NIFTYBEES", "Nifty BeES", 0.5, 1),
            _etf_target(LIQUIDBEES_ID, "LIQUIDBEES", "Liquid BeES", 0.5, 2),
        ]
    if state == 3:
        return [
            _etf_target(GOLDBEES_ID, "GOLDBEES", "Gold BeES", 0.5, 1),
            _etf_target(LIQUIDBEES_ID, "LIQUIDBEES", "Liquid BeES", 0.5, 2),
        ]
    raise ValueError(f"unknown state: {state}")


def build_quantum_selections(
    pairs: list[tuple[str, str]],
    states: dict[str, int],
    fresh_clenow: dict[str, list[dict]],
):
    """Build state-routed target rows and count state usage."""
    selections: dict[str, list[dict]] = {}
    counts = {1: 0, 2: 0, 3: 0}
    for signal, execution in pairs:
        state = states.get(signal)
        if state is None:
            continue
        rows = build_state_targets(state, fresh_clenow.get(signal, []))
        for i, row in enumerate(rows, 1):
            row = dict(row)
            row["state"] = state
            row["rank"] = i
            row["signal_date"] = signal
            row["execution_date"] = execution
            rows[i - 1] = row
        selections[signal] = rows
        counts[state] += 1
    return selections, counts


def build_clenow_fresh(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
):
    """Reuse the frozen Clenow selector; ignore its own regime overlay."""
    clenow_args = SimpleNamespace(
        panel=args.panel,
        end=args.end,
        min_price=args.min_price,
        min_turnover=args.min_turnover,
        top_liquid=args.top_liquid,
        holdings=args.holdings,
        max_weight=args.max_weight,
        exit_rank=30,
        clenow_window=args.clenow_window,
        dma_exit=args.dma_exit,
        atr_window=args.atr_window,
        rebalance_days=21,
        full_reconstitution_days=0,
    )
    dummy_regime = {s: True for s, _ in pairs}
    with contextlib.redirect_stdout(io.StringIO()):
        (
            _selections,
            stock_selections,
            fresh_selections,
            _universe,
            _eligible_counts,
            _liquid_counts,
            _regime_off_counts,
            _names,
        ) = build_clenow_selections(clenow_args, pairs, dummy_regime)
    return stock_selections, fresh_selections


def period_returns(monthly: list[dict], start: str, end: str) -> list[float]:
    return [
        float(m["return"])
        for m in monthly
        if start[:7] <= m["month"] <= end[:7]
    ]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def path_metrics(returns: list[float]) -> dict:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, equity / peak - 1.0)
    years = len(returns) / 12.0
    cagr = (
        equity ** (1.0 / years) - 1.0
        if years > 0 and equity > 0
        else None
    )
    return {
        "final_equity": equity,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "months": len(returns),
    }


def block_bootstrap_returns(
    returns: list[float],
    n_paths: int,
    block_size: int,
    seed: int,
) -> list[list[float]]:
    """Circular block bootstrap, preserving local return dependence."""
    if not returns:
        raise ValueError("returns must not be empty")
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if n_paths < 1:
        raise ValueError("n_paths must be >= 1")
    rng = random.Random(seed)
    n = len(returns)
    paths: list[list[float]] = []
    for _ in range(n_paths):
        path: list[float] = []
        while len(path) < n:
            start = rng.randrange(n)
            for j in range(block_size):
                path.append(returns[(start + j) % n])
                if len(path) == n:
                    break
        paths.append(path)
    return paths


def monte_carlo(
    returns: list[float],
    n_paths: int = 1000,
    block_size: int = 6,
    seed: int = 42,
):
    paths = block_bootstrap_returns(returns, n_paths, block_size, seed)
    metrics = [path_metrics(p) for p in paths]
    cagrs = [m["cagr"] for m in metrics if m["cagr"] is not None]
    dds = [m["max_drawdown"] for m in metrics]
    summary = {
        "paths": n_paths,
        "block_size": block_size,
        "seed": seed,
        "cagr_p2_5": percentile(cagrs, 2.5),
        "cagr_p5": percentile(cagrs, 5.0),
        "cagr_median": percentile(cagrs, 50.0),
        "cagr_p95": percentile(cagrs, 95.0),
        "cagr_p97_5": percentile(cagrs, 97.5),
        "maxdd_p2_5": percentile(dds, 2.5),
        "maxdd_p5": percentile(dds, 5.0),
        "maxdd_median": percentile(dds, 50.0),
        "maxdd_p95": percentile(dds, 95.0),
        "maxdd_p97_5": percentile(dds, 97.5),
    }
    return summary, metrics


def evaluate_gate(
    oos1: dict,
    mc: dict,
    dsr: dict,
) -> dict:
    def gt(x, y) -> bool:
        return x is not None and y is not None and x > y

    def ge(x, y) -> bool:
        return x is not None and y is not None and x >= y

    conditions = [
        {
            "name": "oos1_net_cagr_positive",
            "pass": gt(oos1.get("cagr"), 0.0),
            "value": oos1.get("cagr"),
            "threshold": 0.0,
        },
        {
            "name": "oos1_net_sharpe_positive",
            "pass": gt(oos1.get("sharpe"), 0.0),
            "value": oos1.get("sharpe"),
            "threshold": 0.0,
        },
        {
            "name": "oos1_maxdd_within_30pct",
            "pass": ge(oos1.get("max_drawdown"), -0.30),
            "value": oos1.get("max_drawdown"),
            "threshold": -0.30,
        },
        {
            "name": "mc_p5_cagr_positive",
            "pass": gt(mc.get("cagr_p5"), 0.0),
            "value": mc.get("cagr_p5"),
            "threshold": 0.0,
        },
        {
            "name": "mc_p5_maxdd_within_30pct",
            "pass": ge(mc.get("maxdd_p5"), -0.30),
            "value": mc.get("maxdd_p5"),
            "threshold": -0.30,
        },
        {
            "name": "dsr_ge_0_95",
            "pass": ge(dsr.get("dsr"), 0.95),
            "value": dsr.get("dsr"),
            "threshold": 0.95,
        },
    ]
    failed = [c["name"] for c in conditions if not c["pass"]]
    return {
        "decision": "PASS" if not failed else "FAIL",
        "conditions": conditions,
        "failed": failed,
    }


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.2f}%"


def num(x, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def append_bridge(summary: dict) -> None:
    path = os.path.join(ROOT, "bridge", "to_antigravity.md")
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    full = summary["walk_forward"]["full"]
    is_stats = summary["walk_forward"]["is"]
    oos1 = summary["walk_forward"]["oos1"]
    mc = summary["monte_carlo"]
    dsr = summary["dsr_oos1"]
    gate = summary["gate"]
    lines = [
        "",
        "---",
        "",
        "## Quantum Simulation Lab — 3-State Regime + 4 Shields",
        "",
        f"**Timestamp:** {ts}  ",
        f"**Spec:** `docs/quantum-simulation-lab-spec.md`  ",
        f"**Command:** `{' '.join(sys.argv)}`  ",
        f"**Window:** {summary['start']} .. {summary['end']} (OOS2 frozen)  ",
        "",
        "### Walk-forward (net of costs)",
        "",
        "| Period | CAGR | Sharpe | Max DD |",
        "|---|---:|---:|---:|",
        f"| IS 2010–2018 | {pct(is_stats.get('cagr'))} | {num(is_stats.get('sharpe'))} | {pct(is_stats.get('max_drawdown'))} |",
        f"| OOS1 2019–2024-12-10 | {pct(oos1.get('cagr'))} | {num(oos1.get('sharpe'))} | {pct(oos1.get('max_drawdown'))} |",
        f"| Full 2010–2024-12-10 | {pct(full.get('cagr'))} | {num(full.get('sharpe'))} | {pct(full.get('max_drawdown'))} |",
        "",
        "### Monte Carlo (1,000 block-bootstrap paths)",
        "",
        f"- 5th percentile CAGR: **{pct(mc.get('cagr_p5'))}**",
        f"- Median CAGR: **{pct(mc.get('cagr_median'))}**",
        f"- 95% CAGR interval: **{pct(mc.get('cagr_p2_5'))} .. {pct(mc.get('cagr_p97_5'))}**",
        f"- 5th percentile max DD: **{pct(mc.get('maxdd_p5'))}**",
        f"- Median max DD: **{pct(mc.get('maxdd_median'))}**",
        f"- 95% max DD interval: **{pct(mc.get('maxdd_p2_5'))} .. {pct(mc.get('maxdd_p97_5'))}**",
        "",
        "### Deflated Sharpe Ratio",
        "",
        f"- OOS1 monthly SR: **{num(dsr.get('sr_monthly'), 4)}**",
        f"- OOS1 annual SR: **{num(dsr.get('sr_annual'), 2)}**",
        f"- Trials N: **{summary['trials']}**",
        f"- DSR: **{num(dsr.get('dsr'), 4)}**",
        "",
        f"**Gate: `{gate['decision']}`**",
        "",
    ]
    if gate.get("failed"):
        lines.append(f"Failed: `{', '.join(gate['failed'])}`")
        lines.append("")
    lines.append(
        "**Provenance:** state routing is 50/200DMA with crisis-first "
        "precedence; State 1 uses the frozen Clenow top-10 selector; "
        "State 2 is 50% NIFTYBEES + 50% LIQUIDBEES; State 3 is 50% GOLDBEES "
        "+ 50% LIQUIDBEES. OOS2 was not loaded."
    )
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    validate_window(args.end, args.split)
    if args.end < args.split:
        print(f"warning: end={args.end} is before split={args.split}")
    if args.trials < 2:
        raise SystemExit("--trials must be >= 2")
    if args.mc_paths < 1 or args.mc_block < 1:
        raise SystemExit("--mc-paths and --mc-block must be positive")

    nifty_dates, nifty_closes = load_nifty_until(args.nifty, args.end)
    states = build_regime_states(nifty_dates, nifty_closes)
    pairs = build_month_pairs(nifty_dates, args.start, args.end)
    pairs = [(s, e) for s, e in pairs if s in states]
    if not pairs:
        raise SystemExit("no monthly signal/execution pairs in range")
    print(
        f"pairs={len(pairs)} first={pairs[0]} last={pairs[-1]} "
        f"end={args.end} (OOS2 frozen at {FROZEN_TEST_START})"
    )

    stock_selections, fresh_clenow = build_clenow_fresh(args, pairs)
    selections, state_counts = build_quantum_selections(
        pairs, states, fresh_clenow
    )
    if not selections:
        raise SystemExit("no quantum selections produced")
    print(f"state counts: {state_counts}")

    selected_ids = {
        x["stock_id"]
        for rows in selections.values()
        for x in rows
        if x["stock_id"] != GOLDBEES_ID
    }
    selected_ids.add(NIFTYBEES_ID)
    selected_ids.add(LIQUIDBEES_ID)
    first_exec = pairs[0][1]

    price_args = SimpleNamespace(
        panel=args.panel,
        end=args.end,
        dma_exit=args.dma_exit,
        atr_window=args.atr_window,
    )
    opens, closes, factors, _adj_closes, _dma100, _atr20 = load_stock_prices(
        price_args, selected_ids, first_exec
    )
    gold_args = SimpleNamespace(gold=args.gold, end=args.end)
    gold_opens, gold_closes, gold_factors = load_goldbees(
        gold_args, first_exec
    )
    if not gold_closes:
        raise SystemExit("GOLDBEES series is empty")
    opens[GOLDBEES_ID] = gold_opens
    closes[GOLDBEES_ID] = gold_closes
    factors[GOLDBEES_ID] = gold_factors
    for sid, label in (
        (NIFTYBEES_ID, "NIFTYBEES"),
        (LIQUIDBEES_ID, "LIQUIDBEES"),
    ):
        if not closes.get(sid):
            raise SystemExit(f"{label} series is empty")
    print(
        f"loaded prices: stocks={len(selected_ids) - 2} "
        f"niftybees={len(closes.get(NIFTYBEES_ID, {}))} "
        f"liquidbees={len(closes.get(LIQUIDBEES_ID, {}))} "
        f"gold={len(gold_closes)}"
    )

    turnover_lookup: dict[str, float] = {}
    for rows in selections.values():
        for x in rows:
            sid = x["stock_id"]
            turnover_lookup[sid] = max(
                turnover_lookup.get(sid, 0.0),
                float(x.get("turnover20", 0.0)),
            )
    for sid in DEFENSIVE_IDS:
        turnover_lookup[sid] = 1e9

    run_args = SimpleNamespace(
        capital=args.capital,
        end=args.end,
        target_weight=args.max_weight,
        max_adv_pct=args.max_adv_pct,
        slippage_mult=1.0,
        writeoff_days=90,
        writeoff_unlisted_only=True,
        master=args.master,
    )
    run = run_portfolio(
        run_args,
        pairs,
        selections,
        opens,
        closes,
        factors,
        nifty_dates,
        nifty_closes,
        turnover_lookup=turnover_lookup,
    )
    monthly = run["monthly"]
    full = curve_stats(
        run["curve"], monthly, start=args.start, end=args.end
    )
    is_stats = curve_stats(
        run["curve"], monthly, start=args.start, end=args.is_end
    )
    oos1 = curve_stats(
        run["curve"], monthly, start=args.oos_start, end=args.end
    )

    nifty_curve = [
        {"date": d, "equity": nifty_closes[d]}
        for d in nifty_dates
        if first_exec <= d <= args.end and d in nifty_closes
    ]
    nifty_monthly = monthly_from_curve(nifty_curve)
    nifty_full = curve_stats(
        nifty_curve, nifty_monthly, start=args.start, end=args.end
    )
    nifty_oos1 = curve_stats(
        nifty_curve, nifty_monthly, start=args.oos_start, end=args.end
    )

    oos1_returns = period_returns(monthly, args.oos_start, args.end)
    full_returns = period_returns(monthly, args.start, args.end)
    mc, mc_metrics = monte_carlo(
        oos1_returns, args.mc_paths, args.mc_block, args.seed
    )
    try:
        dsr_oos1 = dsr_stats(oos1_returns, args.trials)
    except ValueError as exc:
        dsr_oos1 = {"error": str(exc), "dsr": None, "trials": args.trials}
    try:
        dsr_full = dsr_stats(full_returns, args.trials)
    except ValueError as exc:
        dsr_full = {"error": str(exc), "dsr": None, "trials": args.trials}
    dsr_sensitivity = {}
    for n in (10, 20, 50, 100):
        if n < 2:
            continue
        try:
            dsr_sensitivity[n] = dsr_stats(oos1_returns, n)["dsr"]
        except ValueError:
            dsr_sensitivity[n] = None

    gate = evaluate_gate(oos1, mc, dsr_oos1)
    summary = {
        "strategy": "quantum_simulation_lab",
        "spec": "docs/quantum-simulation-lab-spec.md",
        "args": vars(args),
        "start": args.start,
        "end": args.end,
        "is_end": args.is_end,
        "oos_start": args.oos_start,
        "split": args.split,
        "frozen_test_start": FROZEN_TEST_START,
        "pairs": len(pairs),
        "first_signal": pairs[0][0],
        "last_signal": pairs[-1][0],
        "first_exec": first_exec,
        "last_exec": pairs[-1][1],
        "state_counts": state_counts,
        "selected_ids": sorted(selected_ids),
        "walk_forward": {
            "is": is_stats,
            "oos1": oos1,
            "full": full,
        },
        "nifty": {
            "oos1": nifty_oos1,
            "full": nifty_full,
        },
        "run_summary": run["summary"],
        "oos1_returns": oos1_returns,
        "monte_carlo": mc,
        "dsr_oos1": dsr_oos1,
        "dsr_full": dsr_full,
        "dsr_sensitivity": dsr_sensitivity,
        "trials": args.trials,
        "gate": gate,
    }

    os.makedirs(args.outdir, exist_ok=True)
    with open(
        os.path.join(args.outdir, "summary_quantum_simulation.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(sanitize(summary), f, indent=2)
        f.write("\n")
    write_csv(
        os.path.join(args.outdir, "curve_quantum_simulation.csv"),
        run["curve"],
    )
    write_csv(
        os.path.join(args.outdir, "trades_quantum_simulation.csv"),
        run["trades"],
    )
    write_csv(
        os.path.join(args.outdir, "monthly_quantum_simulation.csv"),
        monthly,
    )
    write_csv(
        os.path.join(args.outdir, "mc_paths_quantum_simulation.csv"),
        mc_metrics,
    )
    regime_rows = []
    for signal, rows in selections.items():
        for x in rows:
            regime_rows.append(
                {
                    "signal_date": signal,
                    "execution_date": x.get("execution_date", ""),
                    "state": x.get("state", ""),
                    "rank": x.get("rank", ""),
                    "stock_id": x.get("stock_id", ""),
                    "symbol": x.get("symbol", ""),
                    "weight": x.get("weight", ""),
                }
            )
    write_csv(
        os.path.join(args.outdir, "regime_quantum_simulation.csv"),
        regime_rows,
    )

    print()
    print("=== WALK-FORWARD (net) ===")
    for label, st in (
        ("IS 2010-2018", is_stats),
        ("OOS1 2019-2024-12-10", oos1),
        ("Full 2010-2024-12-10", full),
    ):
        print(
            f"{label}: CAGR {pct(st.get('cagr'))} | "
            f"Sharpe {num(st.get('sharpe'))} | "
            f"maxDD {pct(st.get('max_drawdown'))}"
        )
    print(
        f"Nifty OOS1: CAGR {pct(nifty_oos1.get('cagr'))} | "
        f"maxDD {pct(nifty_oos1.get('max_drawdown'))}"
    )
    print()
    print("=== MONTE CARLO (1,000 paths) ===")
    print(
        f"CAGR p2.5 {pct(mc.get('cagr_p2_5'))} | "
        f"p5 {pct(mc.get('cagr_p5'))} | "
        f"median {pct(mc.get('cagr_median'))} | "
        f"p95 {pct(mc.get('cagr_p95'))} | "
        f"p97.5 {pct(mc.get('cagr_p97_5'))}"
    )
    print(
        f"MaxDD p2.5 {pct(mc.get('maxdd_p2_5'))} | "
        f"p5 {pct(mc.get('maxdd_p5'))} | "
        f"median {pct(mc.get('maxdd_median'))} | "
        f"p95 {pct(mc.get('maxdd_p95'))} | "
        f"p97.5 {pct(mc.get('maxdd_p97_5'))}"
    )
    print()
    print("=== DEFLATED SHARPE ===")
    print(
        f"OOS1 SR monthly {num(dsr_oos1.get('sr_monthly'), 4)} | "
        f"annual {num(dsr_oos1.get('sr_annual'))} | "
        f"trials {args.trials} | DSR {num(dsr_oos1.get('dsr'), 4)}"
    )
    print(f"DSR sensitivity: {dsr_sensitivity}")
    print()
    print(f"gate: {gate['decision']}")
    if gate.get("failed"):
        print("failed:", ", ".join(gate["failed"]))
    print(f"outputs: {args.outdir}")

    if args.append_bridge:
        append_bridge(summary)
        print("appended report to bridge/to_antigravity.md")


if __name__ == "__main__":
    main()
