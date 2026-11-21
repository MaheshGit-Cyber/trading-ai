"""Typed contracts for the deterministic brain layer.

Rules:

1. Nothing in this module reads files, calls a model, or touches the network.
2. Every output is JSON-serialisable through ``to_dict()``.
3. Scores are descriptive, not trade instructions. The LLM layer may explain
   them, but may not change them.
4. An engine that failed its gate stays marked ``research_only`` or ``failed``.
   The allocator is expected to refuse those statuses.

Stdlib only. No numpy, no pydantic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType


class AssetClass(str, Enum):
    NSE_EQUITY = "nse_equity"
    CRYPTO = "crypto"
    GOLD = "gold"
    DEBT = "debt"
    CASH = "cash"
    INDEX = "index"


class EngineStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    RESEARCH_ONLY = "research_only"
    FAILED = "failed"


class ScoreBand(str, Enum):
    STRONG = "strong"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    WEAK = "weak"
    VERY_WEAK = "very_weak"


SCORE_BANDS = tuple(b.value for b in ScoreBand)
ASSET_CLASSES = tuple(a.value for a in AssetClass)


def _finite(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class DataQuality:
    """What the score was computed from, so the UI can hide bad queries."""

    as_of: str
    bars: int
    required_bars: int
    stale_days: int = 0
    flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, str) or not self.as_of:
            raise ValueError("data_quality.as_of required")
        if not isinstance(self.bars, int) or self.bars < 0:
            raise ValueError("data_quality.bars must be an int >= 0")
        if not isinstance(self.required_bars, int) or self.required_bars < 1:
            raise ValueError("data_quality.required_bars must be an int >= 1")
        if not isinstance(self.stale_days, int) or self.stale_days < 0:
            raise ValueError("data_quality.stale_days must be an int >= 0")
        object.__setattr__(self, "flags", tuple(str(f) for f in self.flags))

    @property
    def ok(self) -> bool:
        """Enough history, not stale, and no critical data gap."""
        critical = {"insufficient_history", "nifty_missing"}
        return (
            self.bars >= self.required_bars
            and self.stale_days <= 5
            and not (set(self.flags) & critical)
        )

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "bars": self.bars,
            "required_bars": self.required_bars,
            "stale_days": self.stale_days,
            "flags": list(self.flags),
            "ok": self.ok,
        }


@dataclass(frozen=True, slots=True)
class AssetScore:
    """One deterministic score for one asset at one as-of timestamp."""

    symbol: str
    asset_class: str
    as_of: str
    score: float
    band: str
    components: dict[str, float]
    reasons: tuple[str, ...]
    data_quality: DataQuality
    engine: str = "brain.scorer.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("asset_score.symbol required")
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError(
                f"asset_score.asset_class must be one of {ASSET_CLASSES}"
            )
        if not isinstance(self.as_of, str) or not self.as_of:
            raise ValueError("asset_score.as_of required")
        score = _finite(self.score, "asset_score.score")
        if not 0.0 <= score <= 100.0:
            raise ValueError("asset_score.score must be in [0, 100]")
        object.__setattr__(self, "score", round(score, 2))
        if self.band not in SCORE_BANDS:
            raise ValueError(f"asset_score.band must be one of {SCORE_BANDS}")
        if not isinstance(self.components, dict):
            raise TypeError("asset_score.components must be a dict")
        clean: dict[str, float] = {}
        for key, value in self.components.items():
            if not isinstance(key, str) or not key:
                raise ValueError("component keys must be non-empty strings")
            v = _finite(value, f"component {key}")
            if v < 0:
                raise ValueError(f"component {key} must be >= 0")
            clean[key] = round(v, 4)
        object.__setattr__(self, "components", clean)
        total = sum(clean.values())
        if abs(total - score) > 0.51:
            raise ValueError(
                f"component sum {round(total, 2)} != score {round(score, 2)}"
            )
        object.__setattr__(
            self, "reasons", tuple(str(r) for r in self.reasons if str(r))
        )
        if not isinstance(self.data_quality, DataQuality):
            raise TypeError("asset_score.data_quality must be a DataQuality")
        if not isinstance(self.engine, str) or not self.engine:
            raise ValueError("asset_score.engine required")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "as_of": self.as_of,
            "score": self.score,
            "band": self.band,
            "components": {
                k: round(v, 2) for k, v in self.components.items()
            },
            "reasons": list(self.reasons),
            "data_quality": self.data_quality.to_dict(),
            "engine": self.engine,
        }


@dataclass(frozen=True, slots=True)
class EngineInfo:
    """Governance record for an engine. The allocator must check status."""

    name: str
    status: EngineStatus
    cagr: float | None = None
    max_drawdown: float | None = None
    calmar: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("engine.name required")
        if not isinstance(self.status, EngineStatus):
            raise TypeError("engine.status must be an EngineStatus")
        for field_name, value in (
            ("cagr", self.cagr),
            ("max_drawdown", self.max_drawdown),
            ("calmar", self.calmar),
        ):
            if value is not None:
                _finite(value, f"engine.{field_name}")

    @property
    def can_allocate(self) -> bool:
        return self.status in (EngineStatus.APPROVED, EngineStatus.CONDITIONAL)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "cagr": self.cagr,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
            "can_allocate": self.can_allocate,
            "note": self.note,
        }


# The only audited results allowed into the product. Do not add an engine here
# just because it has a high backtest CAGR; the drawdown gate is binding.
#
# LOCKED 2026-11-22: the strategy research line is closed. New engines require
# a new written directive and a fresh pre-registered gate. The mapping is
# read-only so the allocator cannot be changed by a stray runtime mutation.
ENGINE_REGISTRY: Mapping[str, EngineInfo] = MappingProxyType(
    {
        "all_weather_defender": EngineInfo(
            name="All-Weather Defender (Phase 4B)",
            status=EngineStatus.CONDITIONAL,
            cagr=0.1108,
            max_drawdown=-0.1462,
            calmar=0.7576,
            note=(
                "Lower-volatility, drawdown-aware anchor. CAGR gate and 2026 "
                "positive-year gate failed; -8.64% in 2026 must be disclosed."
            ),
        ),
        "momentum_alpha": EngineInfo(
            name="Momentum Alpha (Phase 2B)",
            status=EngineStatus.RESEARCH_ONLY,
            cagr=0.1997,
            max_drawdown=-0.4975,
            calmar=0.40,
            note=(
                "Research only. -49.75% max drawdown breaches product and "
                "research gates. Not allocatable."
            ),
        ),
        "largecap_meanrev": EngineInfo(
            name="Large-Cap Mean Reversion (Phase 3)",
            status=EngineStatus.FAILED,
            cagr=-0.0432,
            max_drawdown=-0.6662,
            calmar=-0.0648,
            note="Failed. Do not tune or allocate.",
        ),
        "all_weather_static": EngineInfo(
            name="All-Weather Static (Phase 4)",
            status=EngineStatus.FAILED,
            cagr=0.1172,
            max_drawdown=-0.2318,
            calmar=0.5058,
            note="Failed drawdown gate. Superseded by Phase 4B for product use.",
        ),
        "a2_momentum": EngineInfo(
            name="A2 Cross-Sectional Momentum",
            status=EngineStatus.FAILED,
            cagr=-0.0206,
            max_drawdown=-0.1533,
            calmar=None,
            note="Failed 5/11 stable gates. Do not tune or allocate.",
        ),
        "clenow_momentum_semiannual": EngineInfo(
            name="Clenow Momentum Semi-Annual (Gold Shield)",
            status=EngineStatus.RESEARCH_ONLY,
            cagr=0.1017,
            max_drawdown=-0.2744,
            calmar=0.3706,
            note=(
                "Semi-annual 6-month Top 100 Clenow momentum with Gold BeES "
                "shield. Delivered +13% in 2020 COVID and +76% in 2021. "
                "Research-only sleeve."
            ),
        ),
    }
)


class RiskSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class RiskFlag:
    """One explicit, auditable reason a trade is warned or blocked."""

    code: str
    severity: RiskSeverity
    message: str
    date: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("risk_flag.code required")
        if not isinstance(self.severity, RiskSeverity):
            raise TypeError("risk_flag.severity must be a RiskSeverity")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("risk_flag.message required")
        if not isinstance(self.date, str):
            raise TypeError("risk_flag.date must be a string")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "date": self.date,
        }


@dataclass(frozen=True, slots=True)
class PositionSize:
    """Risk-budgeted long-only position size. Not an execution order."""

    capital: float
    entry: float
    stop: float
    quantity: int
    position_value: float
    risk_per_trade_pct: float
    risk_budget: float
    per_share_risk: float
    actual_risk: float
    actual_risk_pct: float
    binding_constraint: str
    adv20_value: float | None
    adv_cap_pct: float
    max_position_pct: float
    lot_size: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("capital", self.capital),
            ("entry", self.entry),
            ("stop", self.stop),
            ("position_value", self.position_value),
            ("risk_per_trade_pct", self.risk_per_trade_pct),
            ("risk_budget", self.risk_budget),
            ("per_share_risk", self.per_share_risk),
            ("actual_risk", self.actual_risk),
            ("actual_risk_pct", self.actual_risk_pct),
            ("adv_cap_pct", self.adv_cap_pct),
            ("max_position_pct", self.max_position_pct),
        ):
            _finite(value, f"position.{name}")
        if self.capital <= 0 or self.entry <= 0 or self.stop <= 0:
            raise ValueError("position capital/entry/stop must be > 0")
        if self.stop >= self.entry:
            raise ValueError("position stop must be below entry for a long")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool):
            raise TypeError("position.quantity must be an int")
        if self.quantity < 0:
            raise ValueError("position.quantity must be >= 0")
        if not isinstance(self.lot_size, int) or self.lot_size < 1:
            raise ValueError("position.lot_size must be an int >= 1")
        if not 0 < self.risk_per_trade_pct <= 0.02:
            raise ValueError("position.risk_per_trade_pct must be in (0, 0.02]")
        if not 0 < self.max_position_pct <= 1.0:
            raise ValueError("position.max_position_pct must be in (0, 1]")
        if not 0 < self.adv_cap_pct <= 1.0:
            raise ValueError("position.adv_cap_pct must be in (0, 1]")
        if self.adv20_value is not None:
            _finite(self.adv20_value, "position.adv20_value")
            if self.adv20_value < 0:
                raise ValueError("position.adv20_value must be >= 0")
        if self.position_value > self.capital * self.max_position_pct + 1e-6:
            raise ValueError("position value exceeds max position cap")
        if not isinstance(self.binding_constraint, str) or not self.binding_constraint:
            raise ValueError("position.binding_constraint required")

    @property
    def allowed(self) -> bool:
        return self.quantity > 0

    def to_dict(self) -> dict:
        return {
            "capital": round(self.capital, 2),
            "entry": round(self.entry, 4),
            "stop": round(self.stop, 4),
            "quantity": self.quantity,
            "position_value": round(self.position_value, 2),
            "risk_per_trade_pct": round(self.risk_per_trade_pct, 4),
            "risk_budget": round(self.risk_budget, 2),
            "per_share_risk": round(self.per_share_risk, 4),
            "actual_risk": round(self.actual_risk, 2),
            "actual_risk_pct": round(self.actual_risk_pct, 4),
            "binding_constraint": self.binding_constraint,
            "adv20_value": (
                round(self.adv20_value, 2)
                if self.adv20_value is not None
                else None
            ),
            "adv_cap_pct": round(self.adv_cap_pct, 4),
            "max_position_pct": round(self.max_position_pct, 4),
            "lot_size": self.lot_size,
            "allowed": self.allowed,
        }


@dataclass(frozen=True, slots=True)
class TradePlan:
    """Risk guard output: sizing plus every warning/block, never silent."""

    symbol: str
    as_of: str
    allowed: bool
    sizing: PositionSize
    flags: tuple[RiskFlag, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("trade_plan.symbol required")
        if not isinstance(self.as_of, str) or not self.as_of:
            raise ValueError("trade_plan.as_of required")
        if not isinstance(self.allowed, bool):
            raise TypeError("trade_plan.allowed must be bool")
        if not isinstance(self.sizing, PositionSize):
            raise TypeError("trade_plan.sizing must be a PositionSize")
        object.__setattr__(self, "flags", tuple(self.flags))
        for flag in self.flags:
            if not isinstance(flag, RiskFlag):
                raise TypeError("trade_plan.flags must contain RiskFlag")
        blocks = [f for f in self.flags if f.severity is RiskSeverity.BLOCK]
        if self.allowed and blocks:
            raise ValueError("trade_plan cannot be allowed with a BLOCK flag")
        if self.allowed and not self.sizing.allowed:
            raise ValueError("trade_plan cannot be allowed with zero quantity")
        object.__setattr__(
            self, "warnings", tuple(str(w) for w in self.warnings if str(w))
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "allowed": self.allowed,
            "sizing": self.sizing.to_dict(),
            "flags": [f.to_dict() for f in self.flags],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class Allocation:
    """Sleeve weights and rupee amounts. Conditional engine only."""

    engine: str
    engine_status: str
    regime: str
    risk_score: int
    capital: float
    weights: dict[str, float]
    amounts: dict[str, float]
    allowed: bool
    flags: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    as_of: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.engine, str) or not self.engine:
            raise ValueError("allocation.engine required")
        if self.engine_status not in tuple(s.value for s in EngineStatus):
            raise ValueError("allocation.engine_status invalid")
        if self.regime not in ("normal", "derisk"):
            raise ValueError("allocation.regime must be normal|derisk")
        if not isinstance(self.risk_score, int) or not 1 <= self.risk_score <= 10:
            raise ValueError("allocation.risk_score must be an int 1..10")
        capital = _finite(self.capital, "allocation.capital")
        if capital <= 0:
            raise ValueError("allocation.capital must be > 0")
        if not isinstance(self.allowed, bool):
            raise TypeError("allocation.allowed must be bool")
        if self.allowed:
            if not self.weights:
                raise ValueError("allowed allocation needs weights")
            if not self.amounts:
                raise ValueError("allowed allocation needs amounts")
            clean_w: dict[str, float] = {}
            for key, value in self.weights.items():
                v = _finite(value, f"weight {key}")
                if not 0 <= v <= 1:
                    raise ValueError(f"weight {key} must be in [0, 1]")
                clean_w[str(key)] = round(v, 8)
            if abs(sum(clean_w.values()) - 1.0) > 1e-6:
                raise ValueError(
                    f"allocation weights sum {sum(clean_w.values())} != 1"
                )
            clean_a: dict[str, float] = {}
            for key, value in self.amounts.items():
                v = _finite(value, f"amount {key}")
                if v < 0:
                    raise ValueError(f"amount {key} must be >= 0")
                clean_a[str(key)] = round(v, 2)
            if abs(sum(clean_a.values()) - capital) > 1.0:
                raise ValueError(
                    f"allocation amounts sum {sum(clean_a.values())} != {capital}"
                )
            object.__setattr__(self, "weights", clean_w)
            object.__setattr__(self, "amounts", clean_a)
        object.__setattr__(self, "flags", tuple(str(f) for f in self.flags))
        object.__setattr__(
            self, "warnings", tuple(str(w) for w in self.warnings if str(w))
        )

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "engine_status": self.engine_status,
            "regime": self.regime,
            "risk_score": self.risk_score,
            "capital": round(self.capital, 2),
            "allowed": self.allowed,
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "amounts": {k: round(v, 2) for k, v in self.amounts.items()},
            "flags": list(self.flags),
            "warnings": list(self.warnings),
            "as_of": self.as_of,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class PaperSnapshot:
    """Append-only daily paper signal. No order, no broker, no real money."""

    as_of: str
    created_at: str
    capital: float
    engine: str
    regime: str
    risk_score: int
    allocation: dict
    sleeve_prices: dict[str, float]
    warnings: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, str) or not self.as_of:
            raise ValueError("paper.as_of required")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("paper.created_at required")
        capital = _finite(self.capital, "paper.capital")
        if capital <= 0:
            raise ValueError("paper.capital must be > 0")
        if not isinstance(self.engine, str) or not self.engine:
            raise ValueError("paper.engine required")
        if self.regime not in ("normal", "derisk"):
            raise ValueError("paper.regime must be normal|derisk")
        if not isinstance(self.risk_score, int) or not 1 <= self.risk_score <= 10:
            raise ValueError("paper.risk_score must be 1..10")
        if not isinstance(self.allocation, dict) or not self.allocation:
            raise ValueError("paper.allocation required")
        if not isinstance(self.sleeve_prices, dict) or not self.sleeve_prices:
            raise ValueError("paper.sleeve_prices required")
        clean_prices: dict[str, float] = {}
        for key, value in self.sleeve_prices.items():
            v = _finite(value, f"paper price {key}")
            if v <= 0:
                raise ValueError(f"paper price {key} must be > 0")
            clean_prices[str(key)] = round(v, 4)
        object.__setattr__(self, "sleeve_prices", clean_prices)
        object.__setattr__(self, "warnings", tuple(str(w) for w in self.warnings if str(w)))
        if not isinstance(self.note, str):
            raise TypeError("paper.note must be a string")

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "created_at": self.created_at,
            "capital": round(self.capital, 2),
            "engine": self.engine,
            "regime": self.regime,
            "risk_score": self.risk_score,
            "allocation": self.allocation,
            "sleeve_prices": self.sleeve_prices,
            "warnings": list(self.warnings),
            "note": self.note,
        }
