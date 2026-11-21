"""Pre-registered strategy hypotheses and frozen promotion gates.

The agent may create hypotheses. It may not promote them. A backtest result can
mark a family ``gate_passed`` at most; product/paper approval is a separate
human decision. One research family at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Iterable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_REGISTRY = os.path.join(ROOT, "data", "agent", "strategies.jsonl")
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

STATUSES = ("research_only", "gate_passed", "failed", "paper_trading", "approved", "retired")
RESEARCH_GATE_KEYS = (
    "oos_expectancy_r",
    "trades",
    "walk_forward_windows",
    "costs_doubled_expectancy_r",
    "research_max_drawdown_pct",
    "product_max_drawdown_pct",
    "calmar",
    "nifty_excess_cagr_pp",
    "recent_years_positive",
)
PROMOTION_GATE_KEYS = ("paper_months",)
GATE_KEYS = RESEARCH_GATE_KEYS + PROMOTION_GATE_KEYS
FORBIDDEN_HYPOTHESIS = (
    "guaranteed",
    "guarantee",
    "sure shot",
    "no risk",
    "risk-free",
    "fixed return",
    "100%",
)


@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    requirement: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "requirement": self.requirement,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    name: str
    family: str
    hypothesis: str
    universe: str
    timeframe: str
    entry_rule: str
    exit_rule: str
    risk_rule: str
    created_at: str
    status: str = "research_only"
    note: str = ""

    def __post_init__(self) -> None:
        for field in ("strategy_id", "name", "family", "hypothesis", "universe",
                      "timeframe", "entry_rule", "exit_rule", "risk_rule", "created_at"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"strategy.{field} required")
        if self.status not in STATUSES:
            raise ValueError(f"strategy.status must be one of {STATUSES}")
        low = self.hypothesis.lower()
        bad = [w for w in FORBIDDEN_HYPOTHESIS if w in low]
        if bad:
            raise ValueError(f"strategy hypothesis contains forbidden certainty language: {bad}")
        if len(self.hypothesis.split()) < 5:
            raise ValueError("strategy hypothesis must be a substantive sentence")

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "family": self.family,
            "hypothesis": self.hypothesis,
            "universe": self.universe,
            "timeframe": self.timeframe,
            "entry_rule": self.entry_rule,
            "exit_rule": self.exit_rule,
            "risk_rule": self.risk_rule,
            "created_at": self.created_at,
            "status": self.status,
            "note": self.note,
        }


def _metric(metrics: dict, key: str) -> float | bool:
    if key not in metrics:
        raise ValueError(f"metrics missing {key}")
    value = metrics[key]
    if isinstance(value, bool):
        return value
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"metrics.{key} must be numeric or bool")
    return float(value)


def evaluate_gates(metrics: dict) -> tuple[GateResult, ...]:
    """Evaluate frozen gates. Missing metric = fail, never silently pass."""
    results: list[GateResult] = []

    def add(name: str, requirement: str, passed: bool, detail: str) -> None:
        results.append(GateResult(name, requirement, bool(passed), detail))

    try:
        v = _metric(metrics, "oos_expectancy_r")
        add("oos_expectancy_r", "> 0 after realistic costs", v > 0, f"{v:+.4f}R")
    except (KeyError, TypeError, ValueError) as exc:
        add("oos_expectancy_r", "> 0 after realistic costs", False, str(exc))

    try:
        v = _metric(metrics, "trades")
        add("trades", ">= 100 closed trades", v >= 100, f"{v:.0f}")
    except (KeyError, TypeError, ValueError) as exc:
        add("trades", ">= 100 closed trades", False, str(exc))

    try:
        v = _metric(metrics, "walk_forward_windows")
        add("walk_forward_windows", ">= 3 windows", v >= 3, f"{v:.0f}")
    except (KeyError, TypeError, ValueError) as exc:
        add("walk_forward_windows", ">= 3 windows", False, str(exc))

    try:
        v = _metric(metrics, "costs_doubled_expectancy_r")
        add("costs_doubled_expectancy_r", "> 0 at 2x costs", v > 0, f"{v:+.4f}R")
    except (KeyError, TypeError, ValueError) as exc:
        add("costs_doubled_expectancy_r", "> 0 at 2x costs", False, str(exc))

    try:
        v = _metric(metrics, "research_max_drawdown_pct")
        add("research_max_drawdown_pct", "<= 28%", v <= 28, f"{v:.2f}%")
    except (KeyError, TypeError, ValueError) as exc:
        add("research_max_drawdown_pct", "<= 28%", False, str(exc))

    try:
        v = _metric(metrics, "product_max_drawdown_pct")
        add("product_max_drawdown_pct", "<= 20%", v <= 20, f"{v:.2f}%")
    except (KeyError, TypeError, ValueError) as exc:
        add("product_max_drawdown_pct", "<= 20%", False, str(exc))

    try:
        v = _metric(metrics, "calmar")
        add("calmar", "> 0.8", v > 0.8, f"{v:.2f}")
    except (KeyError, TypeError, ValueError) as exc:
        add("calmar", "> 0.8", False, str(exc))

    try:
        v = _metric(metrics, "nifty_excess_cagr_pp")
        add("nifty_excess_cagr_pp", "> +5 percentage points", v > 5, f"{v:+.2f}pp")
    except (KeyError, TypeError, ValueError) as exc:
        add("nifty_excess_cagr_pp", "> +5 percentage points", False, str(exc))

    try:
        v = _metric(metrics, "recent_years_positive")
        add("recent_years_positive", "True", v is True, str(v))
    except (KeyError, TypeError, ValueError) as exc:
        add("recent_years_positive", "True", False, str(exc))

    return tuple(results)


def evaluate_promotion(metrics: dict) -> tuple[GateResult, ...]:
    """Post-research gate. All research gates must also pass."""
    results = list(evaluate_gates(metrics))
    try:
        v = _metric(metrics, "paper_months")
        results.append(
            GateResult("paper_months", ">= 3 months", v >= 3, f"{v:.1f}")
        )
    except (KeyError, TypeError, ValueError) as exc:
        results.append(GateResult("paper_months", ">= 3 months", False, str(exc)))
    return tuple(results)


def gate_summary(results: Iterable[GateResult]) -> dict:
    items = list(results)
    passed = sum(1 for r in items if r.passed)
    return {
        "passed": passed,
        "total": len(items),
        "all_passed": bool(items) and passed == len(items),
        "failed": [r.name for r in items if not r.passed],
    }


class StrategyRegistry:
    """Append-only registry. Latest event per strategy is the source of truth."""

    def __init__(self, path: str = DEFAULT_REGISTRY):
        self.path = path

    def _events(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out: list[dict] = []
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    out.append(json.loads(text))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"strategy registry corrupt line {i}: {exc}") from exc
        return out

    def _write(self, obj: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def register(self, spec: StrategySpec) -> None:
        for event in self._events():
            if event.get("strategy_id") == spec.strategy_id and event.get("event") == "registered":
                raise ValueError(f"strategy already registered: {spec.strategy_id}")
        self._write(
            {
                "ts": datetime.now(IST).isoformat(timespec="seconds"),
                "event": "registered",
                "strategy_id": spec.strategy_id,
                "status": "research_only",
                "spec": spec.to_dict(),
            }
        )

    def record_result(self, strategy_id: str, metrics: dict, *, note: str = "") -> dict:
        known = {e.get("strategy_id") for e in self._events() if e.get("event") == "registered"}
        if strategy_id not in known:
            raise ValueError(f"unknown strategy: {strategy_id}")
        results = evaluate_gates(metrics)
        summary = gate_summary(results)
        status = "gate_passed" if summary["all_passed"] else "failed"
        # A result can never jump to paper_trading/approved automatically.
        self._write(
            {
                "ts": datetime.now(IST).isoformat(timespec="seconds"),
                "event": "result",
                "strategy_id": strategy_id,
                "status": status,
                "metrics": metrics,
                "gates": [r.to_dict() for r in results],
                "summary": summary,
                "note": note,
            }
        )
        return {"status": status, "summary": summary, "gates": [r.to_dict() for r in results]}

    def latest(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for event in self._events():
            sid = event.get("strategy_id")
            if sid:
                out[sid] = event
        return out

    def list(self) -> list[dict]:
        return list(self.latest().values())
