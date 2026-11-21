"""Paper-book evaluator for the append-only signal ledger.

Frozen convention (see docs/phase5-paper-trading.md):

- Start at the first snapshot's close with its target weights.
- Hold sleeve units between target changes; no daily rebalancing.
- A target change at session t is executed at the next recorded session's
  close, never at the same close that produced the signal.
- Costs: 10 bps one-way on Nifty/Gold BeES, 2 bps on debt, 0 on cash.
- Debt uses the snapshot's synthetic 7% price; cash stays at 1.0.

This is a paper book, not an executable order book.
"""

from __future__ import annotations

from dataclasses import dataclass

NON_CASH = ("nifty50", "gold_bees", "debt")
DEFAULT_COST_BPS = {"nifty50": 10.0, "gold_bees": 10.0, "debt": 2.0, "cash": 0.0}
RULE = (
    "Initial close-entry; hold units; execute a target change at the next "
    "recorded close; no interpolation; costs 10/10/2/0 bps."
)


@dataclass(frozen=True, slots=True)
class PaperDay:
    as_of: str
    gross_value: float
    value: float
    daily_return: float
    cumulative_return: float
    drawdown: float
    rebalanced: bool
    target_changed: bool
    turnover: float
    costs: float
    nifty_close: float

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "gross_value": round(self.gross_value, 2),
            "value": round(self.value, 2),
            "daily_return": round(self.daily_return, 6),
            "cumulative_return": round(self.cumulative_return, 6),
            "drawdown": round(self.drawdown, 6),
            "rebalanced": self.rebalanced,
            "target_changed": self.target_changed,
            "turnover": round(self.turnover, 2),
            "costs": round(self.costs, 2),
            "nifty_close": round(self.nifty_close, 4),
        }


@dataclass(frozen=True, slots=True)
class PaperReport:
    days: tuple[PaperDay, ...]
    initial_capital: float
    final_value: float
    total_return: float
    max_drawdown: float
    rebalances: int
    total_costs: float
    nifty_return: float
    rule: str = RULE

    def to_dict(self) -> dict:
        return {
            "days": [d.to_dict() for d in self.days],
            "initial_capital": round(self.initial_capital, 2),
            "final_value": round(self.final_value, 2),
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "rebalances": self.rebalances,
            "total_costs": round(self.total_costs, 2),
            "nifty_return": round(self.nifty_return, 6),
            "rule": self.rule,
        }


def _weights(snapshot) -> dict[str, float]:
    weights = (snapshot.allocation or {}).get("weights")
    if not isinstance(weights, dict):
        raise ValueError(f"{snapshot.as_of}: allocation.weights missing")
    allowed = {"nifty50", "gold_bees", "debt", "cash"}
    extra = set(str(k) for k in weights) - allowed
    if extra:
        raise ValueError(f"{snapshot.as_of}: unsupported paper sleeves {sorted(extra)}")
    clean = {str(k): float(v) for k, v in weights.items()}
    for key in allowed:
        clean.setdefault(key, 0.0)
    if any(v < 0 for v in clean.values()):
        raise ValueError(f"{snapshot.as_of}: negative target weight")
    if abs(sum(clean.values()) - 1.0) > 1e-6:
        raise ValueError(f"{snapshot.as_of}: target weights do not sum to 1")
    return clean


def _prices(snapshot) -> dict[str, float]:
    prices = {str(k): float(v) for k, v in (snapshot.sleeve_prices or {}).items()}
    for key in ("nifty50", "gold_bees", "debt", "cash"):
        if key not in prices or prices[key] <= 0:
            raise ValueError(f"{snapshot.as_of}: missing/zero sleeve price {key}")
    return prices


def _cost_bps(custom: dict | None) -> dict[str, float]:
    out = dict(DEFAULT_COST_BPS)
    if custom:
        for key, value in custom.items():
            if key not in out:
                raise ValueError(f"unknown cost sleeve: {key}")
            v = float(value)
            if v < 0:
                raise ValueError("cost bps cannot be negative")
            out[key] = v
    return out


def _same(a: dict[str, float], b: dict[str, float]) -> bool:
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= 1e-9 for k in set(a) | set(b))


def evaluate_snapshots(snapshots, *, cost_bps: dict | None = None) -> PaperReport:
    """Evaluate sorted PaperSnapshot objects under the frozen paper rule."""
    snaps = sorted(snapshots, key=lambda s: s.as_of)
    if not snaps:
        raise ValueError("no paper snapshots")
    dates = [s.as_of for s in snaps]
    if len(set(dates)) != len(dates):
        raise ValueError("duplicate paper snapshot date")
    capital = float(snaps[0].capital)
    if capital <= 0:
        raise ValueError("paper capital must be > 0")
    for s in snaps:
        if abs(float(s.capital) - capital) > 1e-6:
            raise ValueError(f"{s.as_of}: paper capital changed; protocol violation")
    bps = _cost_bps(cost_bps)

    w0 = _weights(snaps[0])
    p0 = _prices(snaps[0])
    units: dict[str, float] = {}
    initial_turnover = 0.0
    initial_cost = 0.0
    for key in NON_CASH:
        value = capital * w0[key]
        initial_turnover += value
        initial_cost += value * bps[key] / 10_000.0
        units[key] = value / p0[key]
    units["cash"] = capital * w0["cash"] - initial_cost
    active = dict(w0)
    pending: dict[str, float] | None = None
    value0 = sum(units[k] * p0[k] for k in units)
    days: list[PaperDay] = [
        PaperDay(
            as_of=snaps[0].as_of,
            gross_value=capital,
            value=value0,
            daily_return=value0 / capital - 1.0,
            cumulative_return=value0 / capital - 1.0,
            drawdown=0.0,
            rebalanced=True,
            target_changed=False,
            turnover=initial_turnover,
            costs=initial_cost,
            nifty_close=p0["nifty50"],
        )
    ]
    peak = value0
    prev_value = value0
    total_costs = initial_cost
    rebalances = 1

    for snap in snaps[1:]:
        w = _weights(snap)
        p = _prices(snap)
        gross = sum(units[k] * p[k] for k in units)

        # Latest target cancels a pending rebalance that would just undo itself.
        if pending is not None and _same(w, active):
            pending = None

        rebalanced = False
        turnover = 0.0
        costs = 0.0
        if pending is not None:
            target_values = {k: gross * pending[k] for k in NON_CASH}
            for k in NON_CASH:
                turnover += abs(target_values[k] - units[k] * p[k])
                costs += abs(target_values[k] - units[k] * p[k]) * bps[k] / 10_000.0
            for k in NON_CASH:
                units[k] = target_values[k] / p[k]
            units["cash"] = gross * pending["cash"] - costs
            active = dict(pending)
            pending = None
            rebalanced = True
            rebalances += 1
            total_costs += costs

        target_changed = not _same(w, active)
        value = gross - costs if rebalanced else gross
        daily = value / prev_value - 1.0 if prev_value > 0 else 0.0
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak > 0 else 0.0
        days.append(
            PaperDay(
                as_of=snap.as_of,
                gross_value=gross,
                value=value,
                daily_return=daily,
                cumulative_return=value / capital - 1.0,
                drawdown=drawdown,
                rebalanced=rebalanced,
                target_changed=target_changed,
                turnover=turnover,
                costs=costs,
                nifty_close=p["nifty50"],
            )
        )
        prev_value = value
        if not _same(w, active):
            pending = dict(w)

    return PaperReport(
        days=tuple(days),
        initial_capital=capital,
        final_value=days[-1].value,
        total_return=days[-1].value / capital - 1.0,
        max_drawdown=min(d.drawdown for d in days),
        rebalances=rebalances,
        total_costs=total_costs,
        nifty_return=days[-1].nifty_close / days[0].nifty_close - 1.0,
    )
