#!/usr/bin/env python3
"""Panel offset-index tests: build, seek, filter, fallback."""

from __future__ import annotations

import csv
from datetime import date, timedelta
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import load_panel_rows  # noqa: E402
from brain.panel_index import build_index, query_rows  # noqa: E402

PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


def _write_panel(path: str, n: int = 300) -> list[dict[str, str]]:
    first = date(2025, 1, 1)
    rows: list[dict[str, str]] = []
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "date",
                "stock_id",
                "market",
                "symbol",
                "name",
                "adj_open",
                "adj_high",
                "adj_low",
                "adj_close",
                "adj_volume",
                "close",
                "turnover_lacs",
                "deliv_per",
                "flags",
                "isin",
            ]
        )
        for i in range(n):
            close = 100.0 * (1.001 ** i)
            row = {
                "date": (first + timedelta(days=i)).isoformat(),
                "stock_id": "NSE:INE000A01001",
                "market": "NSE",
                "symbol": "IDX",
                "name": "Index Test",
                "adj_open": str(close),
                "adj_high": str(close * 1.01),
                "adj_low": str(close * 0.99),
                "adj_close": str(close),
                "adj_volume": "10000",
                "close": str(close),
                "turnover_lacs": "1000",
                "deliv_per": "50",
                "flags": "",
                "isin": "INE000A01001",
            }
            rows.append(row)
            w.writerow([row[k] for k in row])
    return rows


def test_build_and_query() -> None:
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        index = os.path.join(d, "panel.sqlite")
        rows = _write_panel(panel)
        meta = build_index(panel, index, batch_size=50, force=True, progress=False)
        assert meta["rows"] == len(rows), meta
        loaded = load_panel_rows(
            panel,
            symbol="IDX",
            as_of=rows[199]["date"],
            max_bars=320,
            index_path=index,
        )
        assert len(loaded) == 200, len(loaded)
        assert loaded[-1].date == rows[199]["date"]
        assert loaded[0].date == rows[0]["date"]
        assert loaded[-1].isin == "INE000A01001"

        by_id = load_panel_rows(
            panel,
            stock_id="NSE:INE000A01001",
            as_of=rows[10]["date"],
            max_bars=320,
            index_path=index,
        )
        assert len(by_id) == 11
        assert by_id[-1].date == rows[10]["date"]


def test_query_limit_and_order() -> None:
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        index = os.path.join(d, "panel.sqlite")
        rows = _write_panel(panel)
        build_index(panel, index, batch_size=50, force=True, progress=False)
        raw = query_rows(panel, index, symbol="IDX", as_of=rows[-1]["date"], max_bars=5)
        assert len(raw) == 5
        assert raw[0]["date"] == rows[-5]["date"]
        assert raw[-1]["date"] == rows[-1]["date"]


def test_missing_index_falls_back() -> None:
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        rows = _write_panel(panel, n=30)
        loaded = load_panel_rows(
            panel,
            symbol="IDX",
            as_of=rows[-1]["date"],
            index_path=os.path.join(d, "missing.sqlite"),
        )
        assert len(loaded) == 30


def test_corrupt_index_falls_back() -> None:
    with tempfile.TemporaryDirectory() as d:
        panel = os.path.join(d, "panel.csv")
        index = os.path.join(d, "panel.sqlite")
        rows = _write_panel(panel, n=30)
        with open(index, "w", encoding="utf-8") as f:
            f.write("not sqlite")
        loaded = load_panel_rows(
            panel,
            symbol="IDX",
            as_of=rows[-1]["date"],
            index_path=index,
        )
        assert len(loaded) == 30


def main() -> None:
    print("panel index:")
    ok("build and query", test_build_and_query)
    ok("query limit and order", test_query_limit_and_order)
    ok("missing index falls back", test_missing_index_falls_back)
    ok("corrupt index falls back", test_corrupt_index_falls_back)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
