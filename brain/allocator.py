"""Engine allocator: Engine 1 only, with a visible risk-score mapping.

This is **not** a return forecast and **not** an execution order. It maps a
user's 1–10 risk score to a sleeve mix for the conditional Phase 4B
All-Weather Defender engine. It refuses every failed or research-only engine
through ``ENGINE_REGISTRY``.

Why only Engine 1:

- Phase 2B momentum (-49.75% max DD) is research-only.
- Phase 3 mean reversion and Phase 4 static both failed.
- A2 cross-sectional momentum failed 5/11 stable gates.
- Semi-annual Clenow momentum is research-only, not an allocatable sleeve.
- Phase 4B passed the drawdown gate only; CAGR/Calmar/2026 still failed.
  It is therefore ``conditional``, not approved, and the brief must disclose
  the 2026 -8.64% loss.

The mapping is a transparent profile table, not a fitted optimiser. Changing a
weight is a product-policy decision and must be versioned, not silently tuned.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from typing import Sequence

from brain.contracts import (
    ENGINE_REGISTRY,
    Allocation,
    EngineStatus,
)
from brain.data import DEFAULT_NIFTY, PriceBar, load_nifty_rows

ENGINE = "all_weather_defender"
PRODUCT_ENGINES = (ENGINE,)

# Phase 4B normal target is risk score 7: 50% Nifty / 20% gold / 20% debt /
# 10% cash. The 10% was cash/BTC in the backtest; this allocator keeps it in
# cash until a crypto product sleeve is separately approved.
NORMAL_WEIGHTS: dict[int, dict[str, float]] = {
    1: {"nifty50": 0.20, "gold_bees": 0.20, "debt": 0.50, "cash": 0.10},
    2: {"nifty50": 0.25, "gold_bees": 0.20, "debt": 0.45, "cash": 0.10},
    3: {"nifty50": 0.30, "gold_bees": 0.20, "debt": 0.40, "cash": 0.10},
    4: {"nifty50": 0.35, "gold_bees": 0.20, "debt": 0.35, "cash": 0.10},
    5: {"nifty50": 0.40, "gold_bees": 0.20, "debt": 0.30, "cash": 0.10},
    6: {"nifty50": 0.45, "gold_bees": 0.20, "debt": 0.25, "cash": 0.10},
    7: {"nifty50": 0.50, "gold_bees": 0.20, "debt": 0.20, "cash": 0.10},
    8: {"nifty50": 0.55, "gold_bees": 0.20, "debt": 0.15, "cash": 0.10},
    9: {"nifty50": 0.60, "gold_bees": 0.20, "debt": 0.10, "cash": 0.10},
    10: {"nifty50": 0.65, "gold_bees": 0.20, "debt": 0.05, "cash": 0.10},
}

# Phase 4B de-risking target is risk score 5: 15% Nifty / 45% gold / 40%
# debt / 0% cash. Higher scores hold more gold and less debt; no leverage.
DERISK_WEIGHTS: dict[int, dict[str, float]] = {
    1: {"nifty50": 0.05, "gold_bees": 0.35, "debt": 0.60, "cash": 0.00},
    2: {"nifty50": 0.07, "gold_bees": 0.38, "debt": 0.55, "cash": 0.00},
    3: {"nifty50": 0.10, "gold_bees": 0.40, "debt": 0.50, "cash": 0.00},
    4: {"nifty50": 0.12, "gold_bees": 0.42, "debt": 0.46, "cash": 0.00},
    5: {"nifty50": 0.15, "gold_bees": 0.45, "debt": 0.40, "cash": 0.00},
    6: {"nifty50": 0.15, "gold_bees": 0.47, "debt": 0.38, "cash": 0.00},
    7: {"nifty50": 0.15, "gold_bees": 0.50, "debt": 0.35, "cash": 0.00},
    8: {"nifty50": 0.15, "gold_bees": 0.52, "debt": 0.33, "cash": 0.00},
    9: {"nifty50": 0.15, "gold_bees": 0.55, "debt": 0.30, "cash": 0.00},
    10: {"nifty50": 0.15, "gold_bees": 0.58, "debt": 0.27, "cash": 0.00},
}

DISCLOSURES = (
    "Phase 4B is conditional: 11.08% CAGR, -14.62% max drawdown, 2026 -8.64%.",
    "Debt was a synthetic 7% ledger in the backtest; actual G-Sec/liquid-fund "
    "returns and duration risk differ.",
    "The de-risking sleeve can be 45%+ gold; gold fell about 27.5% peak-to-trough "
    "in 2026.",
    "No capital-gains tax, STT/GST/stamp duty, advisory fee, tracking error or "
    "slippage is included here.",
    "This is a profile allocation, not a guarantee of return or capital "
    "preservation.",
)


@dataclass(frozen=True, slots=True)
class RegimeView:
    regime: str
    as_of: str
    nifty_close: float | None
    sma200: float | None
    bars: int
    flags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "as_of": self.as_of,
            "nifty_close": self.nifty_close,
            "sma200": self.sma200,
            "bars": self.bars,
            "flags": list(self.flags),
        }


def nifty_regime(
    nifty_rows: Sequence[PriceBar],
    *,
    as_of: str | None = None,
    lookback: int = 200,
) -> RegimeView:
    """Phase 4B regime: normal if Nifty close > 200DMA, else de-risk.

    Fewer than 200 sessions means normal, exactly as the frozen Phase 4B rule.
    That is a data limitation, not evidence of safety.
    """
    if lookback < 2:
        raise ValueError("lookback must be >= 2")
    bars = [r for r in nifty_rows if not as_of or r.date <= as_of]
    bars.sort(key=lambda b: b.date)
    if not bars:
        raise LookupError("no Nifty bars at/before as_of")
    cutoff = as_of or bars[-1].date
    closes = [r.close for r in bars]
    if len(closes) < lookback:
        return RegimeView(
            regime="normal",
            as_of=cutoff,
            nifty_close=closes[-1],
            sma200=None,
            bars=len(closes),
            flags=("insufficient_history", "regime_defaults_to_normal"),
        )
    sma = sum(closes[-lookback:]) / lookback
    regime = "normal" if closes[-1] > sma else "derisk"
    return RegimeView(
        regime=regime,
        as_of=cutoff,
        nifty_close=round(closes[-1], 4),
        sma200=round(sma, 4),
        bars=len(closes),
    )


def allocate(
    *,
    engine: str = ENGINE,
    regime: str,
    risk_score: int,
    capital: float,
    as_of: str = "",
) -> Allocation:
    """Return a sleeve allocation, or an explicit refusal for a bad engine."""
    if regime not in ("normal", "derisk"):
        raise ValueError("regime must be normal|derisk")
    if not isinstance(risk_score, int) or not 1 <= risk_score <= 10:
        raise ValueError("risk_score must be an int 1..10")
    if not isinstance(capital, (int, float)) or isinstance(capital, bool):
        raise TypeError("capital must be a number")
    capital = float(capital)
    if capital <= 0:
        raise ValueError("capital must be > 0")

    info = ENGINE_REGISTRY.get(engine)
    if info is None:
        return Allocation(
            engine=engine,
            engine_status=EngineStatus.FAILED.value,
            regime=regime,
            risk_score=risk_score,
            capital=capital,
            weights={},
            amounts={},
            allowed=False,
            flags=("engine_unknown",),
            warnings=(),
            as_of=as_of,
            note="Unknown engine; allocator refuses it.",
        )

    if engine not in PRODUCT_ENGINES or not info.can_allocate:
        return Allocation(
            engine=engine,
            engine_status=info.status.value,
            regime=regime,
            risk_score=risk_score,
            capital=capital,
            weights={},
            amounts={},
            allowed=False,
            flags=("engine_not_allocatable",),
            warnings=(info.note,),
            as_of=as_of,
            note=(
                "This engine is not enabled for product allocation. "
                "Research-only/failed engines are refused."
            ),
        )

    table = NORMAL_WEIGHTS if regime == "normal" else DERISK_WEIGHTS
    weights = dict(table[risk_score])
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"weights for {regime}/{risk_score} do not sum to 1")

    amounts = {key: round(capital * weight, 2) for key, weight in weights.items()}
    residual = round(capital - sum(amounts.values()), 2)
    if abs(residual) >= 0.01:
        # Put rounding residue in debt, or cash if debt is zero.
        key = "debt" if weights.get("debt", 0) > 0 else "cash"
        amounts[key] = round(amounts[key] + residual, 2)

    flags: list[str] = ["engine_conditional"]
    warnings: list[str] = list(DISCLOSURES)
    if regime == "derisk":
        flags.append("regime_derisk")
        if weights.get("gold_bees", 0) >= 0.45:
            flags.append("gold_concentration")
            warnings.append(
                "Gold sleeve is 45% or more; this is a concentrated defensive "
                "bet, not capital preservation."
            )
    else:
        flags.append("regime_normal")
    if risk_score >= 9:
        flags.append("high_risk_profile")

    return Allocation(
        engine=engine,
        engine_status=info.status.value,
        regime=regime,
        risk_score=risk_score,
        capital=capital,
        weights=weights,
        amounts=amounts,
        allowed=True,
        flags=tuple(flags),
        warnings=tuple(warnings),
        as_of=as_of,
        note=(
            "Engine 1 only; Phase 2 momentum is research-only and is not "
            "allocatable. Weights are a profile policy, not a return forecast."
        ),
    )


def allocate_from_nifty(
    nifty_rows: Sequence[PriceBar],
    *,
    risk_score: int,
    capital: float,
    engine: str = ENGINE,
    as_of: str | None = None,
) -> tuple[RegimeView, Allocation]:
    view = nifty_regime(nifty_rows, as_of=as_of)
    allocation = allocate(
        engine=engine,
        regime=view.regime,
        risk_score=risk_score,
        capital=capital,
        as_of=view.as_of,
    )
    return view, allocation


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", default=ENGINE)
    p.add_argument("--risk-score", type=int, default=5)
    p.add_argument("--capital", type=float, default=1_000_000)
    p.add_argument("--regime", choices=("auto", "normal", "derisk"), default="auto")
    p.add_argument("--nifty", default=DEFAULT_NIFTY)
    p.add_argument("--as-of")
    args = p.parse_args(argv)

    if args.regime == "auto":
        rows = load_nifty_rows(args.nifty, as_of=args.as_of, max_bars=320)
        view, allocation = allocate_from_nifty(
            rows,
            risk_score=args.risk_score,
            capital=args.capital,
            engine=args.engine,
            as_of=args.as_of,
        )
        print(json.dumps({"regime_view": view.to_dict(), "allocation": allocation.to_dict()}, indent=2))
    else:
        allocation = allocate(
            engine=args.engine,
            regime=args.regime,
            risk_score=args.risk_score,
            capital=args.capital,
            as_of=args.as_of or "",
        )
        print(json.dumps(allocation.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
