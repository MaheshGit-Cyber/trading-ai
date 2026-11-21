#!/usr/bin/env python3
"""Pattern backtest tests: simulation, costs, metrics, OOS gate, CLI."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.pattern_backtest import (  # noqa: E402
    BacktestConfig,
    TradeResult,
    auto_split_date,
    gate,
    gate_stable,
    scan_symbol,
    select_hits,
    simulate_trade,
    split_trades,
    summarize,
)
from engine.patterns import PatternHit  # noqa: E402
from jobs.backtest_patterns import load_universe  # noqa: E402

SCRIPT = os.path.join(ROOT, "jobs", "backtest_patterns.py")
PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001 - test runner reports
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    turnover_lacs: float = 0.0


def _bars(rows: list[tuple[float, float, float, float]]) -> list[Bar]:
    start = date(2024, 1, 1)
    return [
        Bar(
            date=(start + timedelta(days=i)).isoformat(),
            open=o, high=h, low=l, close=c,
        )
        for i, (o, h, l, c) in enumerate(rows)
    ]


def _hit(
    *,
    direction: str = "bullish",
    bar_index: int = 0,
    entry: float = 100.0,
    stop: float = 95.0,
    t1: float = 105.0,
    t2: float = 110.0,
    confidence: float = 0.8,
    pattern_id: str = "test",
    name: str = "Test",
) -> PatternHit:
    return PatternHit(
        pattern_id=pattern_id,
        name=name,
        direction=direction,
        bar_index=bar_index,
        confidence=confidence,
        entry=entry,
        stop=stop,
        target1=t1,
        target2=t2,
        reasons=(),
    )


def _trade(
    net: float,
    signal_date: str,
    reason: str,
    *,
    t1: bool = False,
    t2: bool = False,
    status: str = "entered",
) -> TradeResult:
    return TradeResult(
        symbol="X",
        pattern_id="p",
        name="P",
        direction="bullish",
        signal_date=signal_date,
        signal_index=0,
        confidence=0.8,
        entry=100.0,
        stop=95.0,
        target1=105.0,
        target2=110.0,
        status=status,
        entry_date=signal_date,
        entry_price=100.0,
        exit_date=signal_date,
        exit_price=100.0 + net * 5.0,
        exit_reason=reason,
        gross_r=net + 0.1,
        cost_r=0.1,
        net_r=net,
        cost_r_stress=0.2,
        net_r_stress=net - 0.1,
        bars_held=1,
        t1_hit=t1,
        t2_hit=t2,
    )


# ---------------------------------------------------------------------------
# Long simulation
# ---------------------------------------------------------------------------


def test_long_t2_win():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 100, 105),
        (105, 111, 105, 110),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.status == "entered", trade
    assert trade.entry_price == 100.0
    assert trade.exit_reason == "t2"
    assert abs(trade.gross_r - 1.5) < 1e-9
    assert abs(trade.cost_r - 0.1) < 1e-9
    assert abs(trade.net_r - 1.4) < 1e-9
    assert trade.t1_hit and trade.t2_hit
    assert trade.bars_held == 2


def test_long_stop():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101, 94, 95),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.exit_reason == "stop"
    assert abs(trade.gross_r + 1.0) < 1e-9
    assert abs(trade.net_r + 1.1) < 1e-9


def test_long_stop_first_same_bar():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 94, 100),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.exit_reason == "stop_first"
    assert abs(trade.gross_r + 1.0) < 1e-9


def test_long_t1_then_be_stop():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 100, 105),
        (100.5, 101, 99.5, 100),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.exit_reason == "be_stop"
    assert abs(trade.gross_r - 0.5) < 1e-9
    assert abs(trade.net_r - 0.4) < 1e-9
    assert trade.t1_hit and not trade.t2_hit


def test_long_time_stop():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (101, 103, 100, 102),
        (102, 103, 101, 102),
    ])
    trade = simulate_trade(
        "X", bars, _hit(), BacktestConfig(max_hold_bars=2)
    )
    assert trade.exit_reason == "time"
    assert trade.exit_price == 102.0
    assert abs(trade.gross_r - 0.4) < 1e-9
    assert abs(trade.net_r - 0.3) < 1e-9
    assert trade.bars_held == 2


def test_long_gap_entry():
    bars = _bars([
        (100, 101, 99, 100),
        (102, 103, 101, 102),
        (101, 110, 101, 109),
        (105, 112, 105, 111),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.entry_price == 102.0
    assert trade.exit_reason == "t2"
    gross = 0.5 * (105 - 102) / 7 + 0.5 * (110 - 102) / 7
    cost = 102 * 0.005 / 7
    assert abs(trade.gross_r - gross) < 1e-9
    assert abs(trade.net_r - (gross - cost)) < 1e-9


# ---------------------------------------------------------------------------
# Short simulation
# ---------------------------------------------------------------------------


def test_short_t2_win():
    bars = _bars([
        (100, 101, 99, 100),
        (99, 100, 98, 99),
        (98, 99, 96, 97),
        (96, 97, 94, 95),
    ])
    hit = _hit(
        direction="bearish", entry=99, stop=101, t1=97, t2=95
    )
    trade = simulate_trade("X", bars, hit, BacktestConfig())
    assert trade.status == "entered"
    assert trade.entry_price == 99.0
    assert trade.exit_reason == "t2"
    assert abs(trade.gross_r - 1.5) < 1e-9
    assert abs(trade.cost_r - 99 * 0.005 / 2) < 1e-9
    assert abs(trade.net_r - (1.5 - 99 * 0.005 / 2)) < 1e-9


# ---------------------------------------------------------------------------
# Entry filters
# ---------------------------------------------------------------------------


def test_no_trigger():
    bars = _bars([
        (100, 101, 99, 100),
        (101, 105, 100, 104),
        (103, 106, 102, 105),
        (104, 107, 103, 106),
    ])
    hit = _hit(entry=110, stop=100, t1=120, t2=130)
    trade = simulate_trade("X", bars, hit, BacktestConfig(wait_bars=3))
    assert trade.status == "no_trigger"


def test_ambiguous_entry():
    bars = _bars([
        (100, 101, 99, 100),
        (98, 101, 94, 100),
    ])
    trade = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert trade.status == "ambiguous"


def test_neutral_hit_skipped():
    bars = _bars([(100, 101, 99, 100)] * 5)
    hit = _hit(direction="neutral", entry=0, stop=0, t1=0, t2=0)
    assert select_hits([hit], bars, BacktestConfig()) == []


def test_one_per_bar_keeps_best_confidence():
    bars = _bars([(100, 101, 99, 100)] * 5)
    low = _hit(confidence=0.5, pattern_id="a")
    high = _hit(confidence=0.9, pattern_id="b")
    selected = select_hits([low, high], bars, BacktestConfig())
    assert len(selected) == 1
    assert selected[0].pattern_id == "b"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_summarize():
    trades = [
        _trade(1.0, "2024-01-01", "t2", t1=True, t2=True),
        _trade(-0.5, "2024-01-02", "stop"),
        _trade(2.0, "2024-01-03", "t2", t1=True, t2=True),
        _trade(-1.0, "2024-01-04", "stop"),
    ]
    summary = summarize(trades, "P")
    assert summary["entered"] == 4
    assert abs(summary["win_rate"] - 0.5) < 1e-9
    assert abs(summary["expectancy_R"] - 0.375) < 1e-9
    assert abs(summary["median_R"] - 0.25) < 1e-9
    assert abs(summary["profit_factor"] - 2.0) < 1e-9
    assert abs(summary["max_drawdown_R"] + 1.0) < 1e-9
    assert abs(summary["t1_hit_rate"] - 0.5) < 1e-9
    assert abs(summary["t2_hit_rate"] - 0.5) < 1e-9
    assert abs(summary["stop_rate"] - 0.5) < 1e-9
    assert summary["exit_reasons"] == {"stop": 2, "t2": 2}


def test_summarize_empty():
    summary = summarize([], "P")
    assert summary["entered"] == 0
    assert summary["expectancy_R"] is None


def test_split_trades():
    trades = [
        _trade(1.0, "2024-01-01", "t2"),
        _trade(1.0, "2024-06-01", "t2"),
        _trade(1.0, "2025-01-01", "t2"),
    ]
    train, test = split_trades(trades, "2024-12-31")
    assert len(train) == 2
    assert len(test) == 1


def test_auto_split_date():
    trades = [
        _trade(1.0, f"2024-01-{i:02d}", "t2") for i in range(1, 11)
    ]
    assert auto_split_date(trades, 0.7) == "2024-01-08"


def test_gate():
    base = {"entered": 100, "expectancy_R": 0.1,
            "profit_factor": 1.5, "win_rate": 0.6}
    assert gate({**base, "entered": 99}) == "INSUFFICIENT"
    assert gate(base) == "PASS"
    assert gate({**base, "expectancy_R": -0.1}) == "FAIL"
    assert gate({**base, "profit_factor": 1.1}) == "FAIL"
    assert gate({**base, "profit_factor": None, "win_rate": 1.0}) == "PASS"
    assert gate({**base, "profit_factor": None, "win_rate": 0.9}) == "FAIL"


# ---------------------------------------------------------------------------
# Detection -> simulation
# ---------------------------------------------------------------------------


def _hammer_rows() -> list[tuple[float, float, float, float]]:
    rows: list[tuple[float, float, float, float]] = []
    price = 120.0
    for _ in range(56):
        o = price
        c = price - 1.0
        rows.append((o, o + 0.5, c - 0.5, c))
        price = c
    rows.append((100.0, 101.2, 94.0, 101.2))  # hammer
    rows.append((100.5, 102.0, 100.0, 101.5))  # trigger
    rows.append((101.5, 109.0, 101.0, 108.0))  # T1
    rows.append((108.0, 116.0, 108.0, 115.0))  # T2
    return rows


def test_gate_stable():
    good = {"entered": 150, "expectancy_R": 0.2,
            "profit_factor": 1.5, "win_rate": 0.6}
    weak = {"entered": 150, "expectancy_R": -0.1,
            "profit_factor": 0.8, "win_rate": 0.45}
    small = {"entered": 50, "expectancy_R": 0.2,
             "profit_factor": 1.5, "win_rate": 0.6}
    assert gate_stable(good, good, good) == "PASS"
    assert gate_stable(good, weak, good) == "UNSTABLE"
    assert gate_stable(good, good, weak) == "UNSTABLE"
    assert gate_stable(weak, good, good) == "FAIL"
    assert gate_stable(small, good, good) == "INSUFFICIENT"
    assert gate_stable(good, good, small) == "INSUFFICIENT_OOS"


def test_trend_filter():
    bars = _bars(_hammer_rows())
    hit = _hit(bar_index=56)
    assert select_hits(
        [hit], bars, BacktestConfig(trend_filter="align")
    ) == []
    assert len(select_hits(
        [hit], bars, BacktestConfig(trend_filter="counter")
    )) == 1


def test_volume_filter():
    bars = [
        Bar("2024-01-01", 100, 101, 99, 100, 1000),
        Bar("2024-01-02", 100, 101, 99, 100, 1000),
        Bar("2024-01-03", 100, 101, 99, 100, 2000),
        Bar("2024-01-04", 100, 101, 99, 100, 1000),
    ]
    hit = _hit(bar_index=2)
    assert len(select_hits(
        [hit], bars, BacktestConfig(min_volume_ratio=1.5)
    )) == 1
    assert select_hits(
        [hit], bars, BacktestConfig(min_volume_ratio=3.0)
    ) == []


def test_regime_filter():
    bars = [
        Bar("2024-01-01", 100, 101, 99, 100, 1000),
        Bar("2024-01-02", 100, 101, 99, 100, 1000),
        Bar("2024-01-03", 100, 101, 99, 100, 1000),
        Bar("2024-01-04", 100, 101, 99, 100, 1000),
    ]
    hit = _hit(bar_index=0)
    above = {bars[0].date: True}
    below = {bars[0].date: False}
    assert len(select_hits(
        [hit], bars, BacktestConfig(regime_filter="above"),
        regime_by_date=above,
    )) == 1
    assert select_hits(
        [hit], bars, BacktestConfig(regime_filter="above"),
        regime_by_date=below,
    ) == []
    assert len(select_hits(
        [hit], bars, BacktestConfig(regime_filter="align"),
        regime_by_date=above,
    )) == 1
    assert select_hits(
        [hit], bars, BacktestConfig(regime_filter="align"),
        regime_by_date=below,
    ) == []
    assert select_hits(
        [hit], bars, BacktestConfig(regime_filter="above"),
        regime_by_date={},
    ) == []


def test_exit_modes():
    bars = _bars([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 100, 105),
        (105, 111, 105, 110),
    ])
    t1 = simulate_trade(
        "X", bars, _hit(), BacktestConfig(exit_mode="t1")
    )
    assert t1.exit_reason == "t1"
    assert abs(t1.gross_r - 1.0) < 1e-9
    assert t1.t1_hit and not t1.t2_hit

    t2 = simulate_trade(
        "X", bars, _hit(), BacktestConfig(exit_mode="t2")
    )
    assert t2.exit_reason == "t2"
    assert abs(t2.gross_r - 2.0) < 1e-9
    assert t2.t2_hit

    partial = simulate_trade("X", bars, _hit(), BacktestConfig())
    assert abs(partial.gross_r - 1.5) < 1e-9


def test_scan_symbol_hammer():
    bars = _bars(_hammer_rows())
    trades = scan_symbol(
        "X", bars, BacktestConfig(one_per_bar=False), start="2024-01-01"
    )
    hammer = [t for t in trades if t.pattern_id == "hammer"]
    assert hammer, [t.pattern_id for t in trades]
    entered = [t for t in hammer if t.status == "entered"]
    assert entered, hammer
    assert entered[0].exit_reason in ("t2", "gap_t2")


# ---------------------------------------------------------------------------
# Universe loader
# ---------------------------------------------------------------------------


def test_turnover_filter():
    bars = [
        Bar("2024-01-01", 100, 101, 99, 100, 0.0, 50.0),
        Bar("2024-01-02", 100, 101, 99, 100, 0.0, 50.0),
        Bar("2024-01-03", 100, 101, 99, 100, 0.0, 50.0),
    ]
    hit = _hit()
    assert select_hits(
        [hit], bars, BacktestConfig(min_turnover_lacs=100)
    ) == []
    assert len(select_hits(
        [hit], bars, BacktestConfig(min_turnover_lacs=10)
    )) == 1


def test_load_universe():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "rs.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "stock_id", "rs_pct"])
            w.writerow(["2026-11-18", "NSE:OLD", "0.99"])
            w.writerow(["2026-11-19", "NSE:LOW", "0.10"])
            w.writerow(["2026-11-19", "NSE:HIGH", "0.95"])
            w.writerow(["2026-11-19", "NSE:MID", "0.50"])
        # Default is the earliest date (point-in-time), alphabetical.
        assert load_universe(path, limit=2) == ["OLD"]
        symbols, selected = load_universe(path, limit=1, return_date=True)
        assert symbols == ["OLD"] and selected == "2026-11-18"
        # Latest date, alphabetical: broad, no performance selection.
        assert load_universe(
            path, limit=2, universe_date="2026-11-19"
        ) == ["HIGH", "LOW"]
        # Latest date, momentum rank: explicit opt-in.
        assert load_universe(
            path, limit=2, universe_date="2026-11-19", rank=True
        ) == ["HIGH", "MID"]


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _write_panel(path: str) -> None:
    rows = _hammer_rows()
    start = date(2024, 1, 1)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "stock_id", "market", "symbol", "name",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
            "close", "turnover_lacs", "deliv_per", "flags", "isin",
        ])
        for i, (o, h, l, c) in enumerate(rows):
            day = (start + timedelta(days=i)).isoformat()
            w.writerow([
                day, "NSE:INE000A01001", "NSE", "IDX", "Index Test",
                o, h, l, c, 1000, c, 1000, 50, "", "INE000A01001",
            ])


def test_cli_small_panel():
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        out = os.path.join(d, "report.json")
        trades_out = os.path.join(d, "trades.csv")
        _write_panel(panel)
        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--panel", panel,
                "--symbols", "IDX",
                "--start", "2024-01-01",
                "--limit", "1",
                "--min-sample", "1",
                "--split-date", "2024-01-01",
                "--no-one-per-bar",
                "--out", out,
                "--trades-out", trades_out,
                "--quiet",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        assert "hammer" in report["patterns"], list(report["patterns"])
        assert report["aggregate"]["entered"] >= 1
        assert os.path.exists(trades_out)
        with open(trades_out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert any(r["pattern_id"] == "hammer" for r in rows)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_long_t2_win,
    test_long_stop,
    test_long_stop_first_same_bar,
    test_long_t1_then_be_stop,
    test_long_time_stop,
    test_long_gap_entry,
    test_short_t2_win,
    test_no_trigger,
    test_ambiguous_entry,
    test_neutral_hit_skipped,
    test_one_per_bar_keeps_best_confidence,
    test_summarize,
    test_summarize_empty,
    test_split_trades,
    test_auto_split_date,
    test_gate,
    test_gate_stable,
    test_trend_filter,
    test_volume_filter,
    test_regime_filter,
    test_exit_modes,
    test_scan_symbol_hammer,
    test_turnover_filter,
    test_load_universe,
    test_cli_small_panel,
]


def main() -> None:
    print("pattern backtest:")
    for test in TESTS:
        ok(test.__name__, test)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
