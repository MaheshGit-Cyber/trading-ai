#!/usr/bin/env python3
"""Paper ledger tests: snapshot, append-only write, no fake dates."""

from __future__ import annotations

from datetime import date, timedelta
import csv
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import PriceBar  # noqa: E402
from brain.paper import (  # noqa: E402
    build_snapshot,
    load_snapshots,
    record_snapshot,
    synthetic_debt_price,
)

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


def _nifty(n: int = 260, step: float = 0.001) -> list[PriceBar]:
    first = date(2025, 1, 1)
    rows = []
    for i in range(n):
        close = 100.0 * ((1.0 + step) ** i)
        rows.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol="NIFTY50",
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=0,
                turnover_lacs=0,
                raw_close=close,
            )
        )
    return rows


def _gold(path: str, as_of: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        w.writerow([as_of, "100", "101", "99", "100", "1000"])


def test_build_and_record() -> None:
    nifty = _nifty()
    cutoff = nifty[-1].date
    with tempfile.TemporaryDirectory() as d:
        gold = os.path.join(d, "gold.csv")
        _gold(gold, cutoff)
        snap = build_snapshot(
            nifty,
            capital=1_000_000,
            risk_score=7,
            gold_path=gold,
            as_of=cutoff,
            created_at="2026-11-21T00:00:00+00:00",
        )
        assert snap.as_of == cutoff
        assert snap.regime == "normal"
        assert snap.sleeve_prices["nifty50"] > 0
        assert snap.sleeve_prices["gold_bees"] == 100
        assert snap.allocation["allowed"] is True
        assert "no order" in " ".join(snap.warnings).lower()
        path, ledger = record_snapshot(snap, root=d)
        assert os.path.exists(path) and os.path.exists(ledger)
        loaded = load_snapshots(d)
        assert len(loaded) == 1
        assert loaded[0].to_dict() == snap.to_dict()
        try:
            record_snapshot(snap, root=d)
        except FileExistsError:
            pass
        else:
            raise AssertionError("duplicate snapshot accepted")


def test_refuses_failed_engine() -> None:
    nifty = _nifty()
    cutoff = nifty[-1].date
    with tempfile.TemporaryDirectory() as d:
        gold = os.path.join(d, "gold.csv")
        _gold(gold, cutoff)
        try:
            build_snapshot(
                nifty,
                capital=1_000_000,
                risk_score=7,
                engine="momentum_alpha",
                gold_path=gold,
                as_of=cutoff,
            )
        except ValueError as exc:
            assert "refused" in str(exc)
            return
    raise AssertionError("failed engine accepted")


def test_debt_ledger_is_calendar_based() -> None:
    a = synthetic_debt_price("2026-01-01")
    b = synthetic_debt_price("2026-11-21")
    assert b > a > 1.0


def test_de_risk_regime_snapshot() -> None:
    nifty = _nifty(step=-0.002)
    cutoff = nifty[-1].date
    with tempfile.TemporaryDirectory() as d:
        gold = os.path.join(d, "gold.csv")
        _gold(gold, cutoff)
        snap = build_snapshot(
            nifty,
            capital=500_000,
            risk_score=5,
            gold_path=gold,
            as_of=cutoff,
            created_at="2026-11-21T00:00:00+00:00",
        )
        assert snap.regime == "derisk"
        assert snap.allocation["weights"]["gold_bees"] == 0.45
        assert any("Gold sleeve is 45%" in w for w in snap.warnings)


def main() -> None:
    print("paper ledger:")
    ok("build and record", test_build_and_record)
    ok("failed engine refused", test_refuses_failed_engine)
    ok("debt ledger calendar", test_debt_ledger_is_calendar_based)
    ok("de-risk snapshot", test_de_risk_regime_snapshot)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
