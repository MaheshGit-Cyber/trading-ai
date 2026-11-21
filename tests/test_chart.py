#!/usr/bin/env python3
"""Chart renderer tests (stdlib + optional Pillow).

The SVG path must work with no third-party dependency. The PNG path is
tested only when Pillow is importable.

    python3 tests/test_chart.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.chart import (  # noqa: E402
    ChartAnnotation,
    ChartBar,
    ChartLevel,
    ChartSpec,
    render,
    render_png,
    render_svg,
    rsi,
    sma,
)

SCRIPT = os.path.join(ROOT, "jobs", "render_chart.py")
PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001 - test runner reports, not hides
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


def _bars(n: int = 80) -> tuple[ChartBar, ...]:
    start = date(2026, 1, 1)
    out: list[ChartBar] = []
    for i in range(n):
        base = 100.0 + i * 0.5
        out.append(
            ChartBar(
                date=(start + timedelta(days=i)).isoformat(),
                open=base,
                high=base + 1.0,
                low=base - 1.0,
                close=base + 0.4,
                volume=1000.0 + i * 10.0,
            )
        )
    return tuple(out)


def _spec(**kwargs) -> ChartSpec:
    params = {
        "symbol": "RELIANCE",
        "bars": _bars(),
        "source": "test panel",
    }
    params.update(kwargs)
    return ChartSpec(**params)


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_invalid_period():
    try:
        sma([1, 2, 3], 0)
    except ValueError:
        return
    raise AssertionError("accepted period=0")


def test_rsi_bounds():
    values = [100.0 + i for i in range(40)]
    series = rsi(values, 14)
    assert all(v is None or 0.0 <= v <= 100.0 for v in series)
    assert series[-1] is not None and series[-1] > 70.0

    down = rsi([100.0 - i for i in range(40)], 14)
    assert down[-1] is not None and down[-1] < 30.0


def test_rsi_flat_is_neutral():
    series = rsi([100.0] * 40, 14)
    assert series[-1] == 50.0


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def test_render_svg_contains_elements():
    svg = render_svg(_spec())
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "<rect" in svg
    assert "<line" in svg
    assert "<polyline" in svg
    assert "<text" in svg
    assert "RELIANCE" in svg
    assert "MA20" in svg
    assert "Volume" in svg
    assert "RSI(14)" in svg


def test_render_svg_escapes_symbol():
    svg = render_svg(_spec(symbol="A&B<C>"))
    assert "A&amp;B&lt;C&gt;" in svg
    assert "A&B<C>" not in svg


def test_render_svg_levels():
    spec = _spec(
        levels=(
            ChartLevel(120.0, "Entry", "#f59e0b"),
            ChartLevel(110.0, "SL", "#ef4444"),
            ChartLevel(135.0, "T1", "#22c55e"),
            ChartLevel(150.0, "T2", "#16a34a"),
        )
    )
    svg = render_svg(spec)
    for label in ("Entry", "SL", "T1", "T2"):
        assert label in svg


def test_off_chart_levels_are_combined():
    spec = _spec(
        levels=(
            ChartLevel(500.0, "Entry", "#f59e0b"),
            ChartLevel(480.0, "SL", "#ef4444"),
        )
    )
    svg = render_svg(spec)
    assert "↑ Entry 500.00" in svg
    assert "SL 480.00" in svg


def test_render_svg_annotation():
    spec = _spec(
        annotations=(
            ChartAnnotation(len(_bars()) - 1, "Bullish Engulfing", "bullish"),
        )
    )
    svg = render_svg(spec)
    assert "Bullish Engulfing" in svg
    assert "<polygon" in svg


def test_render_svg_without_volume_or_rsi():
    svg = render_svg(_spec(show_volume=False, show_rsi=False))
    assert "Volume" not in svg
    assert "RSI(14)" not in svg


def test_render_svg_light_theme():
    svg = render_svg(_spec(theme="light"))
    assert 'fill="#ffffff"' in svg


def test_render_svg_to_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "chart.svg")
        returned = render_svg(_spec(), path)
        assert returned == path
        assert os.path.getsize(path) > 1000
        with open(path, encoding="utf-8") as f:
            assert f.read().startswith("<svg")


# ---------------------------------------------------------------------------
# PNG (optional)
# ---------------------------------------------------------------------------


def _pillow_available() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def test_render_png():
    if not _pillow_available():
        return  # environment without Pillow: SVG remains the supported path
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "chart.png")
        returned = render_png(_spec(), path)
        assert returned == path
        assert os.path.getsize(path) > 1000
        with open(path, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Validation / dispatch
# ---------------------------------------------------------------------------


def test_empty_bars_rejected():
    try:
        ChartSpec(symbol="X", bars=())
    except ValueError:
        return
    raise AssertionError("accepted empty bars")


def test_annotation_index_rejected():
    try:
        ChartSpec(
            symbol="X",
            bars=_bars(10),
            annotations=(ChartAnnotation(99, "bad"),),
        )
    except ValueError:
        return
    raise AssertionError("accepted out-of-range annotation")


def test_bad_theme_rejected():
    try:
        ChartSpec(symbol="X", bars=_bars(10), theme="neon")
    except ValueError:
        return
    raise AssertionError("accepted unknown theme")


def test_dispatch_bad_extension():
    with tempfile.TemporaryDirectory() as d:
        try:
            render(_spec(), os.path.join(d, "chart.txt"))
        except ValueError:
            return
    raise AssertionError("accepted .txt output")


# ---------------------------------------------------------------------------
# CLI integration (small temp panel, no network)
# ---------------------------------------------------------------------------


def _write_panel(path: str, n: int = 40) -> None:
    start = date(2026, 1, 1)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "stock_id", "market", "symbol", "name",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
            "close", "turnover_lacs", "deliv_per", "flags", "isin",
        ])
        for i in range(n):
            base = 100.0 + i * 0.5
            w.writerow([
                (start + timedelta(days=i)).isoformat(),
                "NSE:INE000A01001", "NSE", "IDX", "Index Test",
                base, base + 1.0, base - 1.0, base + 0.4, 1000 + i * 10,
                base + 0.4, 1000, 50, "", "INE000A01001",
            ])


def test_cli_render_from_csv():
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        out = os.path.join(d, "chart.svg")
        _write_panel(panel)
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--panel", panel, "--symbol", "IDX",
             "--days", "30", "--out", out],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        assert os.path.exists(out)
        with open(out, encoding="utf-8") as f:
            assert "IDX" in f.read()


def test_cli_pattern_auto_levels():
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        out = os.path.join(d, "chart.svg")
        # A clear bullish engulfing on the final bar.
        rows = [
            ("2026-01-01", 105, 106, 99, 100),
            ("2026-01-02", 99, 107, 98, 106),
        ]
        with open(panel, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "date", "stock_id", "market", "symbol", "name",
                "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
                "close", "turnover_lacs", "deliv_per", "flags", "isin",
            ])
            for day, o, h, l, c in rows:
                w.writerow([day, "NSE:INE000A01001", "NSE", "IDX", "Index Test",
                            o, h, l, c, 1000, c, 1000, 50, "", "INE000A01001"])
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--panel", panel, "--symbol", "IDX",
             "--days", "2", "--out", out, "--pattern", "--trend", "down"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        with open(out, encoding="utf-8") as f:
            svg = f.read()
        assert "Entry" in svg
        assert "SL" in svg
        assert "Bullish Engulfing" in svg


def test_cli_missing_symbol():
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        _write_panel(panel, n=5)
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--panel", panel, "--symbol", "NOPE",
             "--out", os.path.join(d, "chart.svg")],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 2
        assert "no rows" in (proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_sma_basic,
    test_sma_invalid_period,
    test_rsi_bounds,
    test_rsi_flat_is_neutral,
    test_render_svg_contains_elements,
    test_render_svg_escapes_symbol,
    test_render_svg_levels,
    test_off_chart_levels_are_combined,
    test_render_svg_annotation,
    test_render_svg_without_volume_or_rsi,
    test_render_svg_light_theme,
    test_render_svg_to_file,
    test_render_png,
    test_empty_bars_rejected,
    test_annotation_index_rejected,
    test_bad_theme_rejected,
    test_dispatch_bad_extension,
    test_cli_render_from_csv,
    test_cli_pattern_auto_levels,
    test_cli_missing_symbol,
]


def main() -> None:
    print("chart renderer:")
    for test in TESTS:
        ok(test.__name__, test)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
