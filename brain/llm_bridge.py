"""Formatting bridge: deterministic facts -> English/Teluglish brief.

The LLM is optional and is never allowed to own a number or a decision. The
default path is a pure formatter. ``refine_with_llm`` may rewrite that brief,
but it is rejected if it adds a number, promises a return, or issues a trade
instruction; on failure the deterministic text is returned.

This is deliberate: a fluent paragraph is not evidence. The score, sizing,
flags and disclaimers come from ``brain.scorer`` / ``brain.risk_guard`` /
``brain.allocator`` and are already audited.
"""

from __future__ import annotations

import re
from typing import Callable

from brain.contracts import Allocation, AssetScore, RiskSeverity, TradePlan

Reasoner = Callable[[str, str], str]

DISCLAIMER_EN = (
    "This is decision support, not an order and not a guarantee. "
    "Scores can be wrong, data can be stale, and prices can gap through a stop. "
    "Past or backtested performance does not predict future returns."
)
DISCLAIMER_TELUGLISH = (
    "Idi decision support matrame — order kadu, guarantee kadu. "
    "Score tappu ravachu, data stale avvachu, price stop ni gap tho daatachu. "
    "Past/backtest performance future returns ni guarantee cheyyadu."
)

SYSTEM = """You are a careful Indian-markets explainer.

Rewrite the deterministic brief you are given. Hard rules:
- Do not add any number that is not already in the brief.
- Do not forecast a price, give a price target, or say a stock will go up/down.
- Do not say guaranteed, risk-free, assured, sure profit, or buy/sell now.
- Keep every warning and data-quality caveat.
- Keep the language requested: English, or Teluglish in Roman script.
- Return plain text only, at most 180 words. No markdown table.
"""

_FORBIDDEN = re.compile(
    r"\b(guaranteed?|risk[- ]?free|assured|sure profit|sure return|"
    r"buy now|sell now|target price|price target|will reach|will hit|"
    r"pakka profit|guarantee ga)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _inr(value: float) -> str:
    """Indian digit grouping, e.g. 1000000 -> ₹10,00,000."""
    sign = "-" if value < 0 else ""
    text = f"{abs(value):.0f}"
    if len(text) <= 3:
        return f"{sign}₹{text}"
    head, tail = text[:-3], text[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups)},{tail}"


def _num(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _component_max(asset_class: str, key: str) -> int | None:
    if asset_class == "nse_equity":
        return {
            "trend": 30,
            "relative_strength": 30,
            "delivery_volume": 20,
            "downside_risk": 20,
        }.get(key)
    if asset_class == "crypto":
        return {"trend": 40, "momentum": 40, "downside_risk": 20}.get(key)
    return None


def _quality_line(score: AssetScore, language: str) -> str:
    q = score.data_quality
    if language == "te-en":
        if q.ok:
            return f"Data quality: OK ({q.bars} bars, stale {q.stale_days} days)."
        flags = ", ".join(q.flags) if q.flags else "unknown"
        return f"DATA WARNING: data quality OK kadu ({flags}). Score ni reliable ga treat cheyyaku."
    if q.ok:
        return f"Data quality: OK ({q.bars} bars, stale {q.stale_days} days)."
    flags = ", ".join(q.flags) if q.flags else "unknown"
    return f"DATA WARNING: data quality is not OK ({flags}). Do not treat this score as reliable."


def format_asset_brief(
    score: AssetScore,
    *,
    language: str = "en",
    max_reasons: int = 5,
) -> str:
    """Pure, deterministic explanation of one precomputed score."""
    if language not in ("en", "te-en"):
        raise ValueError("language must be 'en' or 'te-en'")

    if language == "te-en":
        lines = [
            f"{score.symbol} M-score: {_num(score.score)}/100 — {score.band}. "
            f"As of {score.as_of}.",
            _quality_line(score, language),
        ]
        comps = []
        for key, value in score.components.items():
            maximum = _component_max(score.asset_class, key)
            comps.append(
                f"{key} {_num(value)}/{maximum}" if maximum else f"{key} {_num(value)}"
            )
        if comps:
            lines.append("Components: " + "; ".join(comps) + ".")
        if score.reasons:
            lines.append("Mukhya points:")
        for reason in score.reasons[:max_reasons]:
            lines.append(f"- {reason}")
        lines.append(
            "Ee score descriptive matrame; recommendation kadu. "
            "Risk guard pass ayithe ne position size chupistundi."
        )
        lines.append(DISCLAIMER_TELUGLISH)
        return "\n".join(lines)

    lines = [
        f"{score.symbol} M-score: {_num(score.score)}/100 ({score.band}), "
        f"as of {score.as_of}.",
        _quality_line(score, language),
    ]
    comps = []
    for key, value in score.components.items():
        maximum = _component_max(score.asset_class, key)
        comps.append(
            f"{key} {_num(value)}/{maximum}" if maximum else f"{key} {_num(value)}"
        )
    if comps:
        lines.append("Components: " + "; ".join(comps) + ".")
    for reason in score.reasons[:max_reasons]:
        lines.append(f"- {reason}")
    lines.append(DISCLAIMER_EN)
    return "\n".join(lines)


def format_trade_brief(
    plan: TradePlan,
    *,
    language: str = "en",
) -> str:
    """Format the risk guard without turning it into an execution order."""
    if language not in ("en", "te-en"):
        raise ValueError("language must be 'en' or 'te-en'")
    s = plan.sizing
    blocks = [f for f in plan.flags if f.severity is RiskSeverity.BLOCK]
    warns = [f for f in plan.flags if f.severity is RiskSeverity.WARN]

    if language == "te-en":
        lines = [f"Risk guard: {'ALLOWED' if plan.allowed else 'BLOCKED'} — {plan.symbol}, {plan.as_of}."]
        if plan.allowed:
            lines.append(
                f"Position size: {s.quantity} shares; value {_inr(s.position_value)}; "
                f"risk {_inr(s.actual_risk)} (capital lo {_pct(s.actual_risk_pct)}); "
                f"binding cap: {s.binding_constraint}; stop {_num(s.stop)}."
            )
            lines.append("Idi plan matrame; order ivvabadaledu.")
        else:
            lines.append("Ippudu ee setup ki position size ivvabadadu; reasons kindha.")
        for flag in blocks:
            lines.append(f"- BLOCK {flag.code}: {flag.message}")
        for flag in warns[:5]:
            lines.append(f"- WARN {flag.code}: {flag.message}")
        lines.append(DISCLAIMER_TELUGLISH)
        return "\n".join(lines)

    lines = [
        f"Risk guard: {'ALLOWED' if plan.allowed else 'BLOCKED'} — "
        f"{plan.symbol}, {plan.as_of}."
    ]
    if plan.allowed:
        lines.append(
            f"Position size: {s.quantity} shares; value {_inr(s.position_value)}; "
            f"risk {_inr(s.actual_risk)} ({_pct(s.actual_risk_pct)} of capital); "
            f"binding cap: {s.binding_constraint}; stop {_num(s.stop)}."
        )
    else:
        lines.append("No position size is offered for this setup; see the blocks below.")
    for flag in blocks:
        lines.append(f"- BLOCK {flag.code}: {flag.message}")
    for flag in warns[:5]:
        lines.append(f"- WARN {flag.code}: {flag.message}")
    lines.append(DISCLAIMER_EN)
    return "\n".join(lines)


def format_allocation_brief(
    allocation: Allocation,
    *,
    language: str = "en",
) -> str:
    """Format sleeve weights and amounts, including conditional disclosures."""
    if language not in ("en", "te-en"):
        raise ValueError("language must be 'en' or 'te-en'")
    if not allocation.allowed:
        if language == "te-en":
            lines = [
                f"Allocation refused — engine {allocation.engine} "
                f"({allocation.engine_status}).",
                f"Reasons: {', '.join(allocation.flags)}.",
            ]
            lines.extend(f"- {w}" for w in allocation.warnings)
            lines.append(DISCLAIMER_TELUGLISH)
            return "\n".join(lines)
        lines = [
            f"Allocation refused — engine {allocation.engine} "
            f"({allocation.engine_status}).",
            f"Reasons: {', '.join(allocation.flags)}.",
        ]
        lines.extend(f"- {w}" for w in allocation.warnings)
        lines.append(DISCLAIMER_EN)
        return "\n".join(lines)

    if language == "te-en":
        lines = [
            f"Allocation — {allocation.engine} ({allocation.engine_status}), "
            f"regime {allocation.regime}, risk score {allocation.risk_score}/10.",
            f"Capital {_inr(allocation.capital)}.",
        ]
        for key, weight in allocation.weights.items():
            lines.append(
                f"- {key}: {_pct(weight)} / {_inr(allocation.amounts[key])}"
            )
        lines.append("Ee weights profile policy matrame; return forecast kadu.")
        for warning in allocation.warnings:
            lines.append(f"- Note: {warning}")
        lines.append(DISCLAIMER_TELUGLISH)
        return "\n".join(lines)

    lines = [
        f"Allocation — {allocation.engine} ({allocation.engine_status}), "
        f"regime {allocation.regime}, risk score {allocation.risk_score}/10.",
        f"Capital {_inr(allocation.capital)}.",
    ]
    for key, weight in allocation.weights.items():
        lines.append(f"- {key}: {_pct(weight)} / {_inr(allocation.amounts[key])}")
    for warning in allocation.warnings:
        lines.append(f"- Note: {warning}")
    lines.append(DISCLAIMER_EN)
    return "\n".join(lines)


def format_brief(
    *,
    score: AssetScore | None = None,
    plan: TradePlan | None = None,
    allocation: Allocation | None = None,
    language: str = "en",
) -> str:
    """Combine any available deterministic sections, with one disclaimer each."""
    if not any((score, plan, allocation)):
        raise ValueError("pass at least one of score/plan/allocation")
    sections: list[str] = []
    if score is not None:
        sections.append(format_asset_brief(score, language=language))
    if plan is not None:
        sections.append(format_trade_brief(plan, language=language))
    if allocation is not None:
        sections.append(format_allocation_brief(allocation, language=language))
    # Each formatter already ends with the disclaimer; keep one copy at the end.
    disclaimer = DISCLAIMER_TELUGLISH if language == "te-en" else DISCLAIMER_EN
    body = "\n\n".join(sections)
    body = body.replace(disclaimer, "").strip()
    return f"{body}\n\n{disclaimer}"


def _numbers(text: str) -> set[float]:
    out: set[float] = set()
    for token in _NUMBER.findall(text):
        try:
            out.add(round(float(token), 4))
        except ValueError:
            continue
    return out


def validate_rewrite(candidate: str, source: str) -> tuple[bool, str]:
    """Reject a rewrite that adds numbers, promises, or gives an instruction."""
    if not isinstance(candidate, str) or not candidate.strip():
        return False, "empty rewrite"
    if len(candidate) > 1600:
        return False, "rewrite too long"
    if _FORBIDDEN.search(candidate):
        return False, "forbidden promise/instruction language"
    source_numbers = _numbers(source)
    candidate_numbers = _numbers(candidate)
    added = candidate_numbers - source_numbers
    if added:
        return False, f"rewrite added numbers: {sorted(added)[:5]}"
    return True, "ok"


def refine_with_llm(
    deterministic_brief: str,
    complete: Reasoner,
    *,
    language: str = "en",
) -> str:
    """Optionally rewrite; any validation failure falls back to the facts.

    ``complete(system, user)`` is injected, so tests and offline use never
    touch the network. The deterministic brief is always the fallback.
    """
    if language not in ("en", "te-en"):
        raise ValueError("language must be 'en' or 'te-en'")
    if not isinstance(deterministic_brief, str) or not deterministic_brief.strip():
        raise ValueError("deterministic_brief required")
    prompt = (
        f"Language: {'Teluglish Roman' if language == 'te-en' else 'English'}\n"
        "Rewrite this brief exactly, keeping every number and caveat:\n\n"
        f"{deterministic_brief}"
    )
    try:
        candidate = complete(SYSTEM, prompt)
    except Exception:
        return deterministic_brief
    ok, _reason = validate_rewrite(candidate, deterministic_brief)
    if not ok:
        return deterministic_brief
    disclaimer = DISCLAIMER_TELUGLISH if language == "te-en" else DISCLAIMER_EN
    if disclaimer not in candidate:
        candidate = candidate.rstrip() + "\n\n" + disclaimer
    return candidate


def main() -> int:
    """Tiny manual smoke test; real data is supplied by the caller."""
    print("llm_bridge is a formatter. Import format_brief(...) with computed objects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
