#!/usr/bin/env python3
"""Render a candlestick chart from the local NSE panel.

Examples:

    python3 jobs/render_chart.py --symbol RELIANCE --days 180 \
        --out charts/reliance.svg

    python3 jobs/render_chart.py --symbol RELIANCE --out charts/reliance.png \
        --entry 2940 --stop 2875 --t1 3090 --t2 3225 --pattern

No network. Reads the local adjusted panel only. PNG output needs Pillow;
SVG output has no third-party dependency.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import DEFAULT_PANEL, load_panel_rows  # noqa: E402
from engine.chart import (  # noqa: E402
    ChartAnnotation,
    ChartBar,
    ChartLevel,
    ChartSpec,
    render,
)
from engine.patterns import Candle, detect_last  # noqa: E402

LEVEL_STYLE = (
    ("entry", "Entry", "#f59e0b"),
    ("stop", "SL", "#ef4444"),
    ("t1", "T1", "#22c55e"),
    ("t2", "T2", "#16a34a"),
)


def _levels_from_args(args: argparse.Namespace) -> list[ChartLevel]:
    levels: list[ChartLevel] = []
    for attr, label, color in LEVEL_STYLE:
        value = getattr(args, attr)
        if value is not None:
            levels.append(ChartLevel(float(value), label, color))
    return levels


def _annotations(
    args: argparse.Namespace, bars: tuple[ChartBar, ...]
) -> tuple[list[ChartAnnotation], list[ChartLevel]]:
    if not args.pattern:
        return [], []
    candles = [
        Candle(b.open, b.high, b.low, b.close, b.volume) for b in bars
    ]
    context = {"trend": args.trend} if args.trend else None
    hits = detect_last(candles, context=context)
    annotations = [
        ChartAnnotation(
            bar_index=len(bars) - 1,
            text=hit.name,
            direction=hit.direction,
        )
        for hit in hits[: max(0, args.max_annotations)]
    ]
    auto_levels: list[ChartLevel] = []
    if hits:
        hit = hits[0]
        if hit.entry > 0 and hit.stop > 0:
            auto_levels = [
                ChartLevel(hit.entry, "Entry", "#f59e0b"),
                ChartLevel(hit.stop, "SL", "#ef4444"),
                ChartLevel(hit.target1, "T1", "#22c55e"),
                ChartLevel(hit.target2, "T2", "#16a34a"),
            ]
    return annotations, auto_levels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, help="NSE symbol, e.g. RELIANCE")
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--as-of", default=None, help="last date, inclusive")
    parser.add_argument("--days", type=int, default=180, help="number of bars")
    parser.add_argument("--out", default=None)
    parser.add_argument("--entry", type=float, default=None)
    parser.add_argument("--stop", type=float, default=None)
    parser.add_argument("--t1", type=float, default=None)
    parser.add_argument("--t2", type=float, default=None)
    parser.add_argument("--pattern", action="store_true",
                        help="detect and annotate the latest candle pattern")
    parser.add_argument("--trend", choices=("up", "down", "range"), default=None)
    parser.add_argument("--max-annotations", type=int, default=1)
    parser.add_argument("--title", default="")
    parser.add_argument("--source", default="NSE bhavcopy panel (adjusted)")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--no-volume", action="store_true")
    parser.add_argument("--no-rsi", action="store_true")
    parser.add_argument("--png", action="store_true",
                        help="default output to .png when --out is omitted")
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    if args.days < 2:
        print("[chart] error: --days must be >= 2", file=sys.stderr)
        return 2
    symbol = args.symbol.strip().upper()
    try:
        rows = load_panel_rows(
            args.panel,
            symbol=symbol,
            as_of=args.as_of,
            max_bars=args.days,
        )
    except (FileNotFoundError, LookupError, ValueError) as exc:
        print(f"[chart] error: {exc}", file=sys.stderr)
        return 2
    if len(rows) < 2:
        print(f"[chart] error: need >= 2 bars, got {len(rows)}", file=sys.stderr)
        return 2

    bars = tuple(
        ChartBar(
            date=row.date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    )

    levels = _levels_from_args(args)
    annotations, auto_levels = _annotations(args, bars)
    if not levels and auto_levels:
        levels = auto_levels

    spec = ChartSpec(
        symbol=symbol,
        bars=bars,
        timeframe="daily",
        title=args.title,
        levels=tuple(levels),
        annotations=tuple(annotations),
        show_volume=not args.no_volume,
        show_rsi=not args.no_rsi,
        width=args.width,
        height=args.height,
        theme=args.theme,
        source=args.source,
        generated_at=args.generated_at,
    )

    out = args.out
    if not out:
        ext = ".png" if args.png else ".svg"
        out = os.path.join(ROOT, "charts", f"{symbol}_daily{ext}")

    try:
        path = render(spec, out)
    except (RuntimeError, ValueError) as exc:
        print(f"[chart] error: {exc}", file=sys.stderr)
        return 2

    print(
        f"[chart] {path}  bars={len(bars)}  levels={len(levels)}  "
        f"annotations={len(annotations)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
