#!/usr/bin/env python3
"""Backtest every candlestick pattern on the local NSE panel.

Detection is the deterministic Phase-1 detector. The simulator is in
``engine.pattern_backtest``. Costs are charged in R. The headline gate is
out-of-sample: the last 30% of signal dates, by default.

Examples:

    python3 jobs/backtest_patterns.py --limit 20 --start 2018-01-01

    python3 jobs/backtest_patterns.py --symbols RELIANCE,TCS,INFY \\
        --start 2015-01-01 --cost-bps 75

No network. Reads the local adjusted panel only.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import DEFAULT_PANEL, load_panel_rows  # noqa: E402
from engine.pattern_backtest import (  # noqa: E402
    BacktestConfig,
    TradeResult,
    auto_split_date,
    gate,
    gate_stable,
    scan_symbol,
    split_trades,
    summarize,
)

DEFAULT_UNIVERSE = os.path.join(ROOT, "data", "curated", "rs_rank.csv")
DEFAULT_OUT = os.path.join(ROOT, "data", "backtest", "pattern_backtest.json")
DEFAULT_TRADES_OUT = os.path.join(
    ROOT, "data", "backtest", "pattern_backtest_trades.csv"
)


def _norm_symbol(value: str) -> str:
    value = (value or "").strip().upper()
    if value.startswith("NSE:"):
        value = value[4:]
    return value


def load_universe(
    path: str,
    limit: int = 50,
    universe_date: str | None = None,
    *,
    rank: bool = False,
    return_date: bool = False,
):
    """Read symbols from a CSV with ``symbol`` or ``stock_id``.

    ``rs_rank.csv`` uses ``stock_id`` like ``NSE:RELIANCE``; the ``NSE:``
    prefix is stripped to get the panel symbol.

    Point-in-time rule: when a ``date`` column is present and no date is
    given, the **earliest** date is used. Picking the latest date would
    select today's winners and bias the backtest. ``rank=True`` sorts by
    ``rs_pct`` (a momentum universe); the default is alphabetical, which
    is broad and has no performance selection.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return ([], None) if return_date else []
    selected_date = None
    if "date" in rows[0]:
        dates = [r.get("date") or "" for r in rows if r.get("date")]
        if universe_date is None:
            universe_date = min(dates)
        selected_date = universe_date
        rows = [r for r in rows if (r.get("date") or "") == universe_date]
    if rank and "rs_pct" in rows[0]:
        def _rs(row: dict) -> float:
            try:
                return float(row.get("rs_pct") or 0.0)
            except ValueError:
                return 0.0
        rows.sort(key=_rs, reverse=True)
    else:
        rows.sort(
            key=lambda r: _norm_symbol(
                r.get("symbol") or r.get("stock_id") or ""
            )
        )
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = _norm_symbol(row.get("symbol") or "")
        if not symbol:
            symbol = _norm_symbol(row.get("stock_id") or "")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
        if len(out) >= limit:
            break
    if return_date:
        return out, selected_date
    return out


def _load_rows(panel: str, symbol: str, as_of: str | None, max_bars: int):
    try:
        return load_panel_rows(
            panel, symbol=symbol, as_of=as_of, max_bars=max_bars
        )
    except LookupError:
        # A universe file may carry an ISIN instead of a symbol.
        if symbol.startswith("INE") and len(symbol) == 12:
            return load_panel_rows(
                panel, stock_id="NSE:" + symbol, as_of=as_of,
                max_bars=max_bars,
            )
        raise


def load_symbol_rows(
    panel: str, symbol: str, as_of: str | None, max_bars: int
):
    """Public wrapper used by the filter sweep."""
    return _load_rows(panel, symbol, as_of, max_bars)


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}"


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _write_trades(path: str, trades: list[TradeResult]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fields = list(TradeResult.__dataclass_fields__)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for trade in sorted(
            trades,
            key=lambda t: (t.signal_date, t.symbol, t.pattern_id),
        ):
            writer.writerow(trade.as_dict())
    os.replace(tmp, path)


def _print_table(patterns: dict, aggregate: dict) -> None:
    header = (
        f"{'pattern':<34} {'n':>5} {'win%':>6} {'avgR':>7} "
        f"{'PF':>6} {'maxDD':>8} {'gate':>13}"
    )
    print(header)
    print("-" * len(header))

    def _sort_key(summary: dict):
        test = summary["test"]
        expectancy = test.get("expectancy_R")
        return (
            expectancy is None,
            -(expectancy or 0.0),
            -summary.get("entered", 0),
        )

    for summary in sorted(patterns.values(), key=_sort_key):
        test = summary["test"]
        print(
            f"{summary['label'][:34]:<34} "
            f"{test.get('entered', 0):>5} "
            f"{_fmt_pct(test.get('win_rate')):>6} "
            f"{_fmt(test.get('expectancy_R')):>7} "
            f"{_fmt(test.get('profit_factor')):>6} "
            f"{_fmt(test.get('max_drawdown_R'), 1):>8} "
            f"{summary['gate']:>13}"
        )

    test = aggregate["test"]
    print("-" * len(header))
    print(
        f"{'AGGREGATE':<34} "
        f"{test.get('entered', 0):>5} "
        f"{_fmt_pct(test.get('win_rate')):>6} "
        f"{_fmt(test.get('expectancy_R')):>7} "
        f"{_fmt(test.get('profit_factor')):>6} "
        f"{_fmt(test.get('max_drawdown_R'), 1):>8} "
        f"{aggregate['gate']:>13}"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", default="",
                   help="comma-separated symbols; overrides --universe")
    p.add_argument("--universe", default=DEFAULT_UNIVERSE)
    p.add_argument("--universe-date", default=None,
                   help="default: the earliest date in the universe file")
    p.add_argument("--universe-rank", action="store_true",
                   help="sort by rs_pct (momentum universe); default is "
                        "alphabetical and has no performance selection")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--panel", default=DEFAULT_PANEL)
    p.add_argument("--start", default="2020-07-07",
                   help="default matches the first rs_rank date")
    p.add_argument("--end", default=None)
    p.add_argument("--max-bars", type=int, default=10000)
    p.add_argument("--wait-bars", type=int, default=3)
    p.add_argument("--max-hold-bars", type=int, default=10)
    p.add_argument("--cost-bps", type=float, default=50.0,
                   help="round-trip cost in basis points, including slippage")
    p.add_argument("--cost-bps-stress", type=float, default=None,
                   help="stress cost; default is 2x --cost-bps")
    p.add_argument("--t1-fraction", type=float, default=0.5)
    p.add_argument("--min-confidence", type=float, default=0.0)
    p.add_argument("--min-turnover-lacs", type=float, default=100.0,
                   help="signal-bar 20D turnover floor in Rs lakh; 100 = "
                        "Rs 1 crore")
    p.add_argument("--one-per-bar", action=argparse.BooleanOptionalAction,
                   default=True)
    p.add_argument("--split-date", default=None,
                   help="out-of-sample start date; default is the 70th "
                        "percentile of signal dates")
    p.add_argument("--split-frac", type=float, default=0.7)
    p.add_argument("--min-sample", type=int, default=100)
    p.add_argument("--min-pf", type=float, default=1.2)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--trades-out", default=DEFAULT_TRADES_OUT)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        print("[backtest] error: --limit must be >= 1", file=sys.stderr)
        return 2

    universe_date = None
    if args.symbols.strip():
        symbols = []
        seen: set[str] = set()
        for raw in args.symbols.split(","):
            symbol = _norm_symbol(raw)
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    else:
        try:
            symbols, universe_date = load_universe(
                args.universe, limit=args.limit,
                universe_date=args.universe_date,
                rank=args.universe_rank,
                return_date=True,
            )
        except FileNotFoundError as exc:
            print(f"[backtest] error: {exc}", file=sys.stderr)
            return 2
    if not symbols:
        print("[backtest] error: no symbols", file=sys.stderr)
        return 2

    config = BacktestConfig(
        wait_bars=args.wait_bars,
        max_hold_bars=args.max_hold_bars,
        cost_bps=args.cost_bps,
        cost_bps_stress=args.cost_bps_stress,
        t1_fraction=args.t1_fraction,
        min_confidence=args.min_confidence,
        min_turnover_lacs=args.min_turnover_lacs,
        one_per_bar=args.one_per_bar,
    )

    all_trades: list[TradeResult] = []
    warnings: list[str] = []
    for index, symbol in enumerate(symbols, 1):
        try:
            rows = _load_rows(
                args.panel, symbol, args.end, args.max_bars
            )
        except (LookupError, FileNotFoundError, ValueError) as exc:
            warnings.append(f"{symbol}: {exc}")
            if not args.quiet:
                print(f"[{index}/{len(symbols)}] {symbol:<14} skipped: {exc}")
            continue
        if len(rows) < 60:
            warnings.append(f"{symbol}: only {len(rows)} bars, skipped")
            if not args.quiet:
                print(
                    f"[{index}/{len(symbols)}] {symbol:<14} "
                    f"skipped: {len(rows)} bars"
                )
            continue
        trades = scan_symbol(
            symbol, rows, config, start=args.start, end=args.end
        )
        all_trades.extend(trades)
        if not args.quiet:
            entered = sum(1 for t in trades if t.status == "entered")
            print(
                f"[{index}/{len(symbols)}] {symbol:<14} "
                f"bars={len(rows):>5} signals={len(trades):>4} "
                f"entered={entered:>4}"
            )

    if not all_trades:
        print("[backtest] error: no pattern signals", file=sys.stderr)
        return 2

    split_date = args.split_date or auto_split_date(
        all_trades, args.split_frac
    )

    patterns: dict[str, dict] = {}
    for pattern_id in sorted({t.pattern_id for t in all_trades}):
        group = [t for t in all_trades if t.pattern_id == pattern_id]
        summary = summarize(group, group[0].name)
        train, test = split_trades(group, split_date)
        summary["train"] = summarize(train, "train")
        summary["test"] = summarize(test, "test")
        summary["gate"] = gate_stable(
            summary, summary["train"], summary["test"],
            min_sample=args.min_sample,
            min_profit_factor=args.min_pf,
        )
        summary["oos_gate"] = gate(
            summary["test"],
            min_sample=args.min_sample,
            min_profit_factor=args.min_pf,
        )
        summary["gate_all"] = gate(
            summary,
            min_sample=args.min_sample,
            min_profit_factor=args.min_pf,
        )
        patterns[pattern_id] = summary

    aggregate = summarize(all_trades, "ALL")
    train, test = split_trades(all_trades, split_date)
    aggregate["train"] = summarize(train, "train")
    aggregate["test"] = summarize(test, "test")
    aggregate["gate"] = gate_stable(
        aggregate, aggregate["train"], aggregate["test"],
        min_sample=args.min_sample,
        min_profit_factor=args.min_pf,
    )
    aggregate["oos_gate"] = gate(
        aggregate["test"],
        min_sample=args.min_sample,
        min_profit_factor=args.min_pf,
    )
    aggregate["gate_all"] = gate(
        aggregate,
        min_sample=args.min_sample,
        min_profit_factor=args.min_pf,
    )

    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "config": {
            "wait_bars": config.wait_bars,
            "max_hold_bars": config.max_hold_bars,
            "cost_bps": config.cost_bps,
            "cost_bps_stress": config.stress_bps,
            "t1_fraction": config.t1_fraction,
            "min_confidence": config.min_confidence,
            "min_turnover_lacs": config.min_turnover_lacs,
            "one_per_bar": config.one_per_bar,
            "min_sample": args.min_sample,
            "min_profit_factor": args.min_pf,
        },
        "universe": symbols,
        "universe_date": universe_date,
        "date_range": {"start": args.start, "end": args.end},
        "split_date": split_date,
        "aggregate": aggregate,
        "patterns": patterns,
        "warnings": warnings,
    }

    _write_json(args.out, report)
    _write_trades(args.trades_out, all_trades)

    print()
    print(
        f"symbols={len(symbols)} universe={universe_date or '-'} "
        f"signals={len(all_trades)} entered={aggregate['entered']} "
        f"split={split_date or '-'} (test = dates >= split)"
    )
    _print_table(patterns, aggregate)
    print("gate = full sample + train + test; oos_gate is in the JSON")
    print()
    print(f"wrote {args.out}")
    print(f"wrote {args.trades_out}")
    if warnings:
        print(f"warnings: {len(warnings)} (see JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
