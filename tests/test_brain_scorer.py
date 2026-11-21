#!/usr/bin/env python3
"""Contract and scorer tests for the Phase 5 brain core.

    python3 tests/test_brain_scorer.py

The important properties:
  - no look-ahead: adding future bars does not change an as-of score
  - the M-score is deterministic and 0-100
  - insufficient history is flagged, not hidden
  - crypto uses its own component set
  - the panel loader stops at as_of
"""

from __future__ import annotations

from datetime import date, timedelta
import csv
import json
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.contracts import (  # noqa: E402
    AssetClass,
    AssetScore,
    DataQuality,
    EngineInfo,
    EngineStatus,
)
from brain.data import PriceBar, load_panel_rows  # noqa: E402
from brain.scorer import score_crypto, score_nse_stock  # noqa: E402

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


def _series(
    symbol: str,
    n: int = 260,
    start: float = 100.0,
    step: float = 0.003,
    start_day: str = "2023-01-02",
    delivery: float = 50.0,
    volume: float = 1000.0,
) -> list[PriceBar]:
    first = date.fromisoformat(start_day)
    rows: list[PriceBar] = []
    for i in range(n):
        close = start * ((1.0 + step) ** i)
        rows.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol=symbol,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=volume,
                turnover_lacs=100.0,
                raw_close=close,
                deliv_per=delivery,
            )
        )
    return rows


def test_uptrend_scores_high() -> None:
    stock = _series("UPSTOCK", step=0.003)
    nifty = _series("NIFTY50", step=0.001)
    score = score_nse_stock(stock, nifty, symbol="UPSTOCK")
    assert score.score >= 65, score.score
    assert score.band in ("strong", "positive")
    assert score.data_quality.ok, score.data_quality.to_dict()
    assert score.components["trend"] == 30
    assert score.components["relative_strength"] > 0
    assert score.asset_class == AssetClass.NSE_EQUITY.value
    assert score.data_quality.bars == 260


def test_downtrend_scores_low() -> None:
    stock = _series("DOWNSTOCK", step=-0.002)
    nifty = _series("NIFTY50", step=0.001)
    score = score_nse_stock(stock, nifty, symbol="DOWNSTOCK")
    assert score.score < 45, score.score
    assert score.band in ("weak", "very_weak")


def test_no_lookahead_on_future_bars() -> None:
    stock = _series("CUTOFF", n=260, step=0.003)
    nifty = _series("NIFTY50", n=260, step=0.001)
    as_of = stock[-1].date
    base = score_nse_stock(stock, nifty, symbol="CUTOFF", as_of=as_of)

    future = list(stock)
    first = date.fromisoformat(stock[-1].date) + timedelta(days=1)
    for i in range(40):
        close = stock[-1].close * (0.90 ** (i + 1))
        future.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol="CUTOFF",
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1000.0,
                turnover_lacs=100.0,
                raw_close=close,
                deliv_per=50.0,
            )
        )
    after = score_nse_stock(future, nifty, symbol="CUTOFF", as_of=as_of)
    assert base.to_dict() == after.to_dict(), "future bars changed the as-of score"


def test_insufficient_history_is_flagged() -> None:
    stock = _series("SHORT", n=50)
    nifty = _series("NIFTY50", n=260)
    score = score_nse_stock(stock, nifty, symbol="SHORT")
    assert score.data_quality.ok is False
    assert "insufficient_history" in score.data_quality.flags
    assert score.score < 65


def test_crypto_components_and_qa() -> None:
    rows = _series("BTCUSDT", start=1000.0, step=0.004)
    score = score_crypto(rows, symbol="BTCUSDT")
    assert score.asset_class == AssetClass.CRYPTO.value
    assert set(score.components) == {"trend", "momentum", "downside_risk"}
    assert score.score >= 65, score.score
    assert score.data_quality.ok
    json.dumps(score.to_dict())


def test_contract_rejects_bad_score() -> None:
    q = DataQuality(as_of="2026-01-01", bars=200, required_bars=200)
    base = dict(
        symbol="X",
        asset_class="nse_equity",
        as_of="2026-01-01",
        band="neutral",
        reasons=(),
        data_quality=q,
    )
    try:
        AssetScore(score=101, components={"trend": 101}, **base)
    except ValueError:
        pass
    else:
        raise AssertionError("score=101 accepted")

    try:
        AssetScore(score=10, components={"trend": 9}, **base)
    except ValueError:
        pass
    else:
        raise AssertionError("component-sum mismatch accepted")

    try:
        AssetScore(score=float("nan"), components={"trend": 0}, **base)
    except ValueError:
        pass
    else:
        raise AssertionError("NaN score accepted")


def test_loader_stops_at_as_of() -> None:
    rows = _series("LOADER", n=260)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", newline="", delete=False
    ) as f:
        path = f.name
        writer = csv.writer(f)
        writer.writerow(
            [
                "date",
                "stock_id",
                "symbol",
                "adj_open",
                "adj_high",
                "adj_low",
                "adj_close",
                "adj_volume",
                "close",
                "turnover_lacs",
                "deliv_per",
                "flags",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.date,
                    "NSE:TEST",
                    r.symbol,
                    r.open,
                    r.high,
                    r.low,
                    r.close,
                    r.volume,
                    r.close,
                    r.turnover_lacs,
                    r.deliv_per,
                    "",
                ]
            )
    try:
        cutoff = rows[120].date
        loaded = load_panel_rows(path, symbol="LOADER", as_of=cutoff, max_bars=320)
        assert len(loaded) == 121, len(loaded)
        assert loaded[-1].date == cutoff
        assert all(r.date <= cutoff for r in loaded)
    finally:
        os.unlink(path)


def test_engine_registry_governance() -> None:
    from brain.contracts import ENGINE_REGISTRY

    assert len(ENGINE_REGISTRY) == 6
    assert ENGINE_REGISTRY["momentum_alpha"].status is EngineStatus.RESEARCH_ONLY
    assert ENGINE_REGISTRY["momentum_alpha"].can_allocate is False
    assert ENGINE_REGISTRY["all_weather_defender"].can_allocate is True
    assert ENGINE_REGISTRY["largecap_meanrev"].status is EngineStatus.FAILED

    a2 = ENGINE_REGISTRY["a2_momentum"]
    assert a2.status is EngineStatus.FAILED
    assert a2.can_allocate is False
    assert abs(a2.cagr - (-0.0206)) < 1e-12
    assert abs(a2.max_drawdown - (-0.1533)) < 1e-12

    clenow = ENGINE_REGISTRY["clenow_momentum_semiannual"]
    assert clenow.status is EngineStatus.RESEARCH_ONLY
    assert clenow.can_allocate is False
    assert abs(clenow.cagr - 0.1017) < 1e-12
    assert abs(clenow.max_drawdown - (-0.2744)) < 1e-12
    assert abs(clenow.calmar - 0.3706) < 1e-12

    try:
        ENGINE_REGISTRY["new_engine"] = a2
    except TypeError:
        pass
    else:
        raise AssertionError("ENGINE_REGISTRY is not read-only")


def main() -> None:
    print("brain contracts and scorer:")
    ok("uptrend scores high", test_uptrend_scores_high)
    ok("downtrend scores low", test_downtrend_scores_low)
    ok("no look-ahead on future bars", test_no_lookahead_on_future_bars)
    ok("insufficient history flagged", test_insufficient_history_is_flagged)
    ok("crypto components and JSON", test_crypto_components_and_qa)
    ok("bad scores rejected", test_contract_rejects_bad_score)
    ok("panel loader stops at as_of", test_loader_stops_at_as_of)
    ok("engine registry governance", test_engine_registry_governance)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
