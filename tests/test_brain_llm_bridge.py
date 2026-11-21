#!/usr/bin/env python3
"""LLM bridge tests: deterministic facts, no invented numbers, safe fallback."""

from __future__ import annotations

from datetime import date, timedelta
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.allocator import allocate  # noqa: E402
from brain.data import PriceBar  # noqa: E402
from brain.llm_bridge import (  # noqa: E402
    DISCLAIMER_EN as EN,
    DISCLAIMER_TELUGLISH as TE,
    _inr,
    format_allocation_brief,
    format_asset_brief,
    format_brief,
    format_trade_brief,
    refine_with_llm,
    validate_rewrite,
)
from brain.risk_guard import build_trade_plan  # noqa: E402
from brain.scorer import score_nse_stock  # noqa: E402

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


def _series(symbol: str, n: int = 260, step: float = 0.003) -> list[PriceBar]:
    first = date(2023, 1, 2)
    rows = []
    for i in range(n):
        close = 100.0 * ((1.0 + step) ** i)
        rows.append(
            PriceBar(
                date=(first + timedelta(days=i)).isoformat(),
                symbol=symbol,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10000,
                turnover_lacs=1000.0,
                raw_close=close,
                deliv_per=50.0,
            )
        )
    return rows


def _score():
    stock = _series("TEST")
    nifty = _series("NIFTY50", step=0.001)
    return score_nse_stock(stock, nifty, symbol="TEST")


def _plan(allowed: bool = True):
    stock = _series("TEST")
    last = stock[-1]
    if not allowed:
        last = PriceBar(
            date=last.date,
            symbol=last.symbol,
            open=last.close,
            high=last.close,
            low=last.close,
            close=last.close,
            volume=0,
            turnover_lacs=last.turnover_lacs,
            raw_close=last.close,
        )
        stock = stock[:-1] + [last]
    return build_trade_plan(
        symbol="TEST",
        capital=1_000_000,
        entry=last.close,
        stop=last.close * 0.95,
        as_of=last.date,
        bars=stock,
        adv20_value=10_000_000,
    ), last


def test_asset_brief_english_and_teluglish() -> None:
    score = _score()
    en = format_asset_brief(score, language="en")
    te = format_asset_brief(score, language="te-en")
    assert "TEST" in en and "/100" in en and "M-score" in en
    assert "Idi decision support" in te
    assert "guarantee" not in en.lower().replace("not a guarantee", "")
    assert "Components:" in en


def test_quality_warning_is_not_hidden() -> None:
    stock = _series("SHORT", n=50)
    nifty = _series("NIFTY50")
    score = score_nse_stock(stock, nifty, symbol="SHORT")
    text = format_asset_brief(score)
    assert "DATA WARNING" in text
    assert "insufficient_history" in text


def test_trade_brief_allowed_and_blocked() -> None:
    allowed, _ = _plan(True)
    en = format_trade_brief(allowed)
    assert "ALLOWED" in en
    assert "Position size:" in en
    assert "shares" in en
    blocked, _ = _plan(False)
    text = format_trade_brief(blocked)
    assert "BLOCKED" in text
    assert "Position size:" not in text
    assert "BLOCK" in text


def test_allocation_briefs() -> None:
    normal = allocate(regime="normal", risk_score=7, capital=1_000_000)
    en = format_allocation_brief(normal)
    assert "nifty50" in en
    assert "50.0%" in en
    assert "₹5,00,000" in en
    assert "conditional" in en
    refused = allocate(
        engine="momentum_alpha", regime="normal", risk_score=5, capital=1_000_000
    )
    refused_text = format_allocation_brief(refused)
    assert "refused" in refused_text
    assert "research_only" in refused_text


def test_indian_currency_grouping() -> None:
    assert _inr(1_000_000) == "₹10,00,000"
    assert _inr(500_000) == "₹5,00,000"
    assert _inr(1_000) == "₹1,000"


def test_format_brief_has_one_disclaimer() -> None:
    score = _score()
    plan, _ = _plan(True)
    alloc = allocate(regime="normal", risk_score=7, capital=1_000_000)
    text = format_brief(score=score, plan=plan, allocation=alloc, language="en")
    assert text.count(EN) == 1, text.count(EN)
    assert "M-score" in text and "Risk guard" in text and "Allocation" in text


def test_rewrite_rejects_new_numbers_and_promises() -> None:
    source = "Score 31/100. Risk 1%."
    ok1, _ = validate_rewrite("Score 31/100. Risk 1%.", source)
    assert ok1
    ok2, reason = validate_rewrite("Score 31/100. Target 99%.", source)
    assert not ok2 and "numbers" in reason
    ok3, reason = validate_rewrite("This is guaranteed profit.", source)
    assert not ok3 and "forbidden" in reason


def test_refine_falls_back_on_bad_or_failed_llm() -> None:
    source = "Score 31/100. Risk 1%."
    assert refine_with_llm(source, lambda s, u: "Score 31/100. Risk 1%.") .startswith("Score")
    bad = refine_with_llm(source, lambda s, u: "Guaranteed 99% profit.")
    assert bad == source
    boom = refine_with_llm(source, lambda s, u: (_ for _ in ()).throw(RuntimeError("down")))
    assert boom == source


def test_refine_adds_disclaimer_when_missing() -> None:
    source = "Score 31/100. Risk 1%."
    out = refine_with_llm(source, lambda s, u: "Score 31/100. Risk 1%.")
    assert EN in out


def main() -> None:
    print("llm bridge:")
    ok("asset brief en/te", test_asset_brief_english_and_teluglish)
    ok("quality warning visible", test_quality_warning_is_not_hidden)
    ok("trade brief allowed/blocked", test_trade_brief_allowed_and_blocked)
    ok("allocation briefs", test_allocation_briefs)
    ok("Indian currency grouping", test_indian_currency_grouping)
    ok("one disclaimer", test_format_brief_has_one_disclaimer)
    ok("rewrite rejects new numbers/promises", test_rewrite_rejects_new_numbers_and_promises)
    ok("refine fallback", test_refine_falls_back_on_bad_or_failed_llm)
    ok("refine adds disclaimer", test_refine_adds_disclaimer_when_missing)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
