#!/usr/bin/env python3
"""Filter + exit sweep for candlestick patterns.

The Phase-3 backtest showed no stable raw-pattern edge. This job asks the
next question: does a context filter (trend, volume, Nifty 200DMA regime)
or a different exit (T1 only, T2 only) change that?

Detection runs once per symbol. Every config reuses the same hits, so the
sweep is cheap and the comparison is clean.

Examples:

    python3 jobs/pattern_filter_sweep.py --limit 50

    python3 jobs/pattern_filter_sweep.py --symbols RELIANCE,TCS,INFY \\
        --filters base,trend_align --exits partial,t1

No network. Reads the local panel and the local Nifty file.
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

from brain.data import DEFAULT_PANEL, load_nifty_rows  # noqa: E402
from engine.pattern_backtest import (  # noqa: E402
    BacktestConfig,
    auto_split_date,
    detect_hits,
    gate,
    gate_stable,
    scan_symbol,
    split_trades,
    summarize,
)
from jobs.backtest_patterns import (  # noqa: E402
    DEFAULT_UNIVERSE,
    load_symbol_rows,
    load_universe,
)

DEFAULT_OUT = os.path.join(
    ROOT, "data", "backtest", "pattern_filter_sweep.json"
)
DEFAULT_CSV = os.path.join(
    ROOT, "data", "backtest", "pattern_filter_sweep.csv"
)

FILTERS: dict[str, dict] = {
    "base": {},
    "trend_align": {"trend_filter": "align"},
    "trend_counter": {"trend_filter": "counter"},
    "volume_1.2": {"min_volume_ratio": 1.2},
    "regime_align": {"regime_filter": "align"},
    "trend+volume": {"trend_filter": "align", "min_volume_ratio": 1.2},
    "trend+regime": {"trend_filter": "align", "regime_filter": "align"},
    "all": {
        "trend_filter": "align",
        "min_volume_ratio": 1.2,
        "regime_filter": "align",
    },
}
EXITS = ("partial", "t1", "t2")


def load_regime(max_bars: int = 10000) -> dict[str, bool]:
    """True when Nifty closed above its 200DMA on that date."""
    rows = load_nifty_rows(max_bars=max_bars)
    closes = [row.close for row in rows]
    regime: dict[str, bool] = {}
    total = 0.0
    for i, row in enumerate(rows):
        total += row.close
        if i >= 200:
            total -= closes[i - 200]
        if i >= 199:
            regime[row.date] = row.close > total / 200.0
    return regime


def _selected(value: str, allowed: tuple[str, ...], what: str) -> list[str]:
    if not value.strip():
        return list(allowed)
    out = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in out if item not in allowed]
    if unknown:
        raise SystemExit(f"unknown {what}: {unknown}; allowed: {allowed}")
    return out


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _write_csv(path: str, results: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fields = [
        "config", "exit_mode", "trend_filter", "min_volume_ratio",
        "regime_filter", "entered", "oos_entered", "oos_win_rate",
        "oos_expectancy_R", "oos_expectancy_R_stress",
        "oos_profit_factor", "oos_max_drawdown_R", "gate", "oos_gate",
    ]
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for name, summary in sorted(results.items()):
            test = summary["test"]
            cfg = summary["config"]
            writer.writerow({
                "config": name,
                "exit_mode": cfg["exit_mode"],
                "trend_filter": cfg["trend_filter"],
                "min_volume_ratio": cfg["min_volume_ratio"],
                "regime_filter": cfg["regime_filter"],
                "entered": summary.get("entered", 0),
                "oos_entered": test.get("entered", 0),
                "oos_win_rate": test.get("win_rate"),
                "oos_expectancy_R": test.get("expectancy_R"),
                "oos_expectancy_R_stress": test.get("expectancy_R_stress"),
                "oos_profit_factor": test.get("profit_factor"),
                "oos_max_drawdown_R": test.get("max_drawdown_R"),
                "gate": summary["gate"],
                "oos_gate": summary["oos_gate"],
            })
    os.replace(tmp, path)


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _print_table(results: dict) -> None:
    header = (
        f"{'config':<26} {'n':>6} {'oos_n':>6} {'win%':>6} "
        f"{'oosR':>7} {'PF':>6} {'gate':>16}"
    )
    print(header)
    print("-" * len(header))

    def _sort_key(summary: dict):
        expectancy = summary["test"].get("expectancy_R")
        return (
            expectancy is None,
            -(expectancy or 0.0),
            -summary.get("entered", 0),
        )

    for summary in sorted(results.values(), key=_sort_key):
        test = summary["test"]
        win = test.get("win_rate")
        print(
            f"{summary['label'][:26]:<26} "
            f"{summary.get('entered', 0):>6} "
            f"{test.get('entered', 0):>6} "
            f"{'-' if win is None else f'{win * 100:.1f}':>6} "
            f"{_fmt(test.get('expectancy_R')):>7} "
            f"{_fmt(test.get('profit_factor')):>6} "
            f"{summary['gate']:>16}"
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", default="")
    p.add_argument("--universe", default=DEFAULT_UNIVERSE)
    p.add_argument("--universe-date", default=None)
    p.add_argument("--universe-rank", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--panel", default=DEFAULT_PANEL)
    p.add_argument("--start", default="2020-07-07")
    p.add_argument("--end", default=None)
    p.add_argument("--max-bars", type=int, default=10000)
    p.add_argument("--wait-bars", type=int, default=3)
    p.add_argument("--max-hold-bars", type=int, default=10)
    p.add_argument("--cost-bps", type=float, default=50.0)
    p.add_argument("--cost-bps-stress", type=float, default=None)
    p.add_argument("--t1-fraction", type=float, default=0.5)
    p.add_argument("--min-confidence", type=float, default=0.0)
    p.add_argument("--min-turnover-lacs", type=float, default=100.0)
    p.add_argument("--one-per-bar", action=argparse.BooleanOptionalAction,
                   default=True)
    p.add_argument("--filters", default="",
                   help="comma-separated subset; default all")
    p.add_argument("--exits", default="",
                   help="comma-separated subset of partial,t1,t2")
    p.add_argument("--split-date", default=None)
    p.add_argument("--split-frac", type=float, default=0.7)
    p.add_argument("--min-sample", type=int, default=100)
    p.add_argument("--min-pf", type=float, default=1.2)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--csv-out", default=DEFAULT_CSV)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    filter_names = _selected(args.filters, tuple(FILTERS), "filter")
    exit_names = _selected(args.exits, EXITS, "exit")

    universe_date = None
    if args.symbols.strip():
        symbols = []
        seen: set[str] = set()
        for raw in args.symbols.split(","):
            symbol = raw.strip().upper()
            if symbol.startswith("NSE:"):
                symbol = symbol[4:]
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
            print(f"[sweep] error: {exc}", file=sys.stderr)
            return 2
    if not symbols:
        print("[sweep] error: no symbols", file=sys.stderr)
        return 2

    configs: dict[str, BacktestConfig] = {}
    for exit_name in exit_names:
        for filter_name in filter_names:
            name = f"{exit_name}/{filter_name}"
            configs[name] = BacktestConfig(
                wait_bars=args.wait_bars,
                max_hold_bars=args.max_hold_bars,
                cost_bps=args.cost_bps,
                cost_bps_stress=args.cost_bps_stress,
                t1_fraction=args.t1_fraction,
                min_confidence=args.min_confidence,
                min_turnover_lacs=args.min_turnover_lacs,
                one_per_bar=args.one_per_bar,
                exit_mode=exit_name,
                **FILTERS[filter_name],
            )

    regime = load_regime()
    buckets: dict[str, list] = {name: [] for name in configs}
    warnings: list[str] = []

    for index, symbol in enumerate(symbols, 1):
        try:
            rows = load_symbol_rows(
                args.panel, symbol, args.end, args.max_bars
            )
        except (LookupError, FileNotFoundError, ValueError) as exc:
            warnings.append(f"{symbol}: {exc}")
            if not args.quiet:
                print(f"[{index}/{len(symbols)}] {symbol:<14} skipped: {exc}")
            continue
        if len(rows) < 60:
            warnings.append(f"{symbol}: only {len(rows)} bars, skipped")
            continue
        hits = detect_hits(rows)
        if not hits:
            warnings.append(f"{symbol}: no patterns")
            continue
        for name, config in configs.items():
            buckets[name].extend(
                scan_symbol(
                    symbol, rows, config,
                    start=args.start, end=args.end,
                    regime_by_date=regime, hits=hits,
                )
            )
        if not args.quiet:
            print(
                f"[{index}/{len(symbols)}] {symbol:<14} "
                f"bars={len(rows):>5} hits={len(hits):>4}"
            )

    if not any(buckets.values()):
        print("[sweep] error: no pattern signals", file=sys.stderr)
        return 2

    base_trades = buckets.get("partial/base") or next(
        (items for items in buckets.values() if items), []
    )
    split_date = args.split_date or auto_split_date(
        base_trades, args.split_frac
    )

    results: dict[str, dict] = {}
    for name, trades in buckets.items():
        if not trades:
            continue
        summary = summarize(trades, name)
        train, test = split_trades(trades, split_date)
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
        summary["config"] = {
            "exit_mode": configs[name].exit_mode,
            "trend_filter": configs[name].trend_filter,
            "min_volume_ratio": configs[name].min_volume_ratio,
            "regime_filter": configs[name].regime_filter,
        }
        summary["patterns"] = {}
        by_pattern: dict[str, list] = {}
        for trade in trades:
            by_pattern.setdefault(trade.pattern_id, []).append(trade)
        for pattern_id in sorted(by_pattern):
            group = by_pattern[pattern_id]
            detail = summarize(group, group[0].name)
            p_train, p_test = split_trades(group, split_date)
            detail["train"] = summarize(p_train, "train")
            detail["test"] = summarize(p_test, "test")
            detail["gate"] = gate_stable(
                detail, detail["train"], detail["test"],
                min_sample=args.min_sample,
                min_profit_factor=args.min_pf,
            )
            detail["oos_gate"] = gate(
                detail["test"],
                min_sample=args.min_sample,
                min_profit_factor=args.min_pf,
            )
            summary["patterns"][pattern_id] = detail
        results[name] = summary

    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "config": {
            "wait_bars": args.wait_bars,
            "max_hold_bars": args.max_hold_bars,
            "cost_bps": args.cost_bps,
            "cost_bps_stress": (
                args.cost_bps_stress
                if args.cost_bps_stress is not None
                else args.cost_bps * 2.0
            ),
            "t1_fraction": args.t1_fraction,
            "min_confidence": args.min_confidence,
            "min_turnover_lacs": args.min_turnover_lacs,
            "one_per_bar": args.one_per_bar,
            "min_sample": args.min_sample,
            "min_profit_factor": args.min_pf,
            "filters": filter_names,
            "exits": exit_names,
        },
        "universe": symbols,
        "universe_date": universe_date,
        "split_date": split_date,
        "results": results,
        "warnings": warnings,
    }

    _write_json(args.out, report)
    _write_csv(args.csv_out, results)

    print()
    print(
        f"symbols={len(symbols)} universe={universe_date or '-'} "
        f"configs={len(results)} split={split_date or '-'} "
        f"(test = dates >= split)"
    )
    _print_table(results)
    print("gate = full sample + train + test; oos_gate is in the JSON")
    print()
    print(f"wrote {args.out}")
    print(f"wrote {args.csv_out}")
    if warnings:
        print(f"warnings: {len(warnings)} (see JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
