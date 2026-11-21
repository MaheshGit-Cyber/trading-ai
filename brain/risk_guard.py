"""Risk guard: position sizing, liquidity, circuit and event checks.

This module is intentionally conservative. It does not decide whether a signal
is good; it answers a narrower question: *if* a user acts on a precomputed
score, what size keeps the stated risk budget and what should block the trade?

Rules:

- Long-only. A stop must be below entry.
- Risk per trade is capped at 1% by default (2% hard maximum).
- Single-position value is capped at 20% of capital by default.
- 20-day average daily value (ADV) is capped at 5% of ADV.
- No trade if ADV is missing, below ₹1 crore, or the last bar is locked.
- No trade inside a split/bonus/rights/other corporate-action window.
- AGM/EGM/dividend/buyback events are warnings, not silent facts.
- No execution, no broker call, no price target. This is a plan, not an order.

All functions are pure except the CLI loaders.
"""

from __future__ import annotations

import argparse
from datetime import date as ddate, timedelta
import json
import math
from typing import Sequence

from brain.contracts import (
    PositionSize,
    RiskFlag,
    RiskSeverity,
    TradePlan,
)
from brain.data import (
    DEFAULT_ACTIONS,
    DEFAULT_PANEL,
    ActionEvent,
    PriceBar,
    load_actions,
    load_panel_rows,
)

DEFAULT_RISK_PER_TRADE_PCT = 0.01
DEFAULT_MAX_POSITION_PCT = 0.20
DEFAULT_ADV_CAP_PCT = 0.05
DEFAULT_MIN_ADV_VALUE = 10_000_000.0  # ₹1 crore 20D average daily value
DEFAULT_EVENT_HORIZON_DAYS = 10
DEFAULT_MAX_STALE_DAYS = 3


def _num(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def size_position(
    capital: float,
    entry: float,
    stop: float,
    *,
    risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    adv20_value: float | None = None,
    adv_cap_pct: float = DEFAULT_ADV_CAP_PCT,
    lot_size: int = 1,
) -> PositionSize:
    """Size a long position from capital, stop distance, position and ADV caps."""
    capital = _num(capital, "capital")
    entry = _num(entry, "entry")
    stop = _num(stop, "stop")
    risk_per_trade_pct = _num(risk_per_trade_pct, "risk_per_trade_pct")
    max_position_pct = _num(max_position_pct, "max_position_pct")
    adv_cap_pct = _num(adv_cap_pct, "adv_cap_pct")
    if capital <= 0:
        raise ValueError("capital must be > 0")
    if entry <= 0 or stop <= 0:
        raise ValueError("entry and stop must be > 0")
    if stop >= entry:
        raise ValueError("stop must be below entry for a long")
    if not 0 < risk_per_trade_pct <= 0.02:
        raise ValueError("risk_per_trade_pct must be in (0, 0.02]")
    if not 0 < max_position_pct <= 1.0:
        raise ValueError("max_position_pct must be in (0, 1]")
    if not 0 < adv_cap_pct <= 1.0:
        raise ValueError("adv_cap_pct must be in (0, 1]")
    if not isinstance(lot_size, int) or lot_size < 1:
        raise ValueError("lot_size must be an int >= 1")
    if adv20_value is not None:
        adv20_value = _num(adv20_value, "adv20_value")
        if adv20_value < 0:
            raise ValueError("adv20_value must be >= 0")

    per_share_risk = entry - stop
    risk_budget = capital * risk_per_trade_pct
    risk_qty = math.floor(risk_budget / per_share_risk)
    position_qty = math.floor((capital * max_position_pct) / entry)

    candidates: list[tuple[str, int]] = [
        ("risk", risk_qty),
        ("position", position_qty),
    ]
    if adv20_value is not None:
        candidates.append(
            ("adv", math.floor((adv20_value * adv_cap_pct) / entry))
        )

    binding, raw_qty = min(candidates, key=lambda pair: pair[1])
    quantity = (raw_qty // lot_size) * lot_size
    if quantity <= 0:
        binding = "zero"
    position_value = quantity * entry
    actual_risk = quantity * per_share_risk
    actual_risk_pct = actual_risk / capital

    return PositionSize(
        capital=capital,
        entry=entry,
        stop=stop,
        quantity=quantity,
        position_value=position_value,
        risk_per_trade_pct=risk_per_trade_pct,
        risk_budget=risk_budget,
        per_share_risk=per_share_risk,
        actual_risk=actual_risk,
        actual_risk_pct=actual_risk_pct,
        binding_constraint=binding,
        adv20_value=adv20_value,
        adv_cap_pct=adv_cap_pct,
        max_position_pct=max_position_pct,
        lot_size=lot_size,
    )


def _flag(
    code: str,
    severity: RiskSeverity,
    message: str,
    date: str = "",
) -> RiskFlag:
    return RiskFlag(code=code, severity=severity, message=message, date=date)


def _dedupe(flags: Sequence[RiskFlag]) -> tuple[RiskFlag, ...]:
    seen: set[tuple[str, str, str]] = set()
    out: list[RiskFlag] = []
    for flag in flags:
        key = (flag.code, flag.severity.value, flag.message)
        if key not in seen:
            seen.add(key)
            out.append(flag)
    return tuple(out)


def freshness_flags(
    last_bar_date: str,
    as_of: str,
    *,
    max_stale_days: int = DEFAULT_MAX_STALE_DAYS,
) -> list[RiskFlag]:
    """Block clearly stale data; warn after one calendar day."""
    if not last_bar_date or not as_of:
        return [_flag("stale_unknown", RiskSeverity.BLOCK, "bar date or as_of missing")]
    try:
        stale = (ddate.fromisoformat(as_of) - ddate.fromisoformat(last_bar_date)).days
    except ValueError:
        return [_flag("stale_unknown", RiskSeverity.BLOCK, "invalid bar/as_of date")]
    if stale < 0:
        return [_flag("future_bar", RiskSeverity.BLOCK, "bar is after as_of")]
    if stale > max_stale_days:
        return [
            _flag(
                "stale_data",
                RiskSeverity.BLOCK,
                f"last bar is {stale} calendar days old",
                last_bar_date,
            )
        ]
    if stale > 1:
        return [
            _flag(
                "stale_data",
                RiskSeverity.WARN,
                f"last bar is {stale} calendar days old; verify the trading calendar",
                last_bar_date,
            )
        ]
    return []


def liquidity_flags(
    adv20_value: float | None,
    *,
    min_adv_value: float = DEFAULT_MIN_ADV_VALUE,
) -> list[RiskFlag]:
    """ADV is in rupees. Missing/zero is a block, not a neutral value."""
    if adv20_value is None:
        return [_flag("adv_missing", RiskSeverity.BLOCK, "20D ADV is unavailable")]
    if not math.isfinite(adv20_value) or adv20_value <= 0:
        return [_flag("adv_missing", RiskSeverity.BLOCK, "20D ADV is zero/invalid")]
    if adv20_value < min_adv_value:
        return [
            _flag(
                "low_liquidity",
                RiskSeverity.BLOCK,
                f"20D ADV ₹{adv20_value / 1e7:.2f} crore is below "
                f"₹{min_adv_value / 1e7:.2f} crore",
            )
        ]
    if adv20_value < min_adv_value * 2:
        return [
            _flag(
                "thin_liquidity",
                RiskSeverity.WARN,
                f"20D ADV ₹{adv20_value / 1e7:.2f} crore is thin; 5% cap applies",
            )
        ]
    return []


def circuit_flags(
    bars: Sequence[PriceBar],
    *,
    lookback: int = 3,
) -> list[RiskFlag]:
    """Detect a locked/near-locked bar from OHLC, without an exchange flag.

    A true exchange circuit flag is not present in the panel, so this is a
    conservative proxy: high == low is treated as locked; a >=9.5% close-to-close
    move in the lookback is a warning. It can over-block, never under-block.
    """
    if not bars:
        return [_flag("no_bars", RiskSeverity.BLOCK, "no price bars")]
    recent = list(bars[-max(1, lookback):])
    flags: list[RiskFlag] = []
    for bar in recent:
        if bar.volume <= 0:
            flags.append(
                _flag(
                    "no_volume",
                    RiskSeverity.BLOCK,
                    "zero volume on the bar",
                    bar.date,
                )
            )
        scale = max(1e-6, abs(bar.close) * 1e-6)
        if abs(bar.high - bar.low) <= scale:
            flags.append(
                _flag(
                    "circuit_locked",
                    RiskSeverity.BLOCK,
                    "high == low; treated as a locked circuit/illiquid bar",
                    bar.date,
                )
            )
    for prev, cur in zip(recent, recent[1:]):
        if prev.close > 0:
            move = cur.close / prev.close - 1.0
            if abs(move) >= 0.095:
                flags.append(
                    _flag(
                        "near_circuit_move",
                        RiskSeverity.WARN,
                        f"close-to-close move {move:+.1%} is near a 10% band",
                        cur.date,
                    )
                )
    return flags


def _action_class(action: str, purpose: str) -> tuple[str, RiskSeverity]:
    a = action.upper().strip()
    p = purpose.lower().strip()
    if a.startswith("SPLIT"):
        return "split", RiskSeverity.BLOCK
    if a.startswith("BONUS"):
        return "bonus", RiskSeverity.BLOCK
    if a.startswith("RIGHTS"):
        return "rights", RiskSeverity.BLOCK
    if a.startswith("OTHER"):
        return "other_corporate_action", RiskSeverity.BLOCK
    if "annual general" in p or "agm" in p:
        return "agm", RiskSeverity.WARN
    if "extraordinary general" in p or "egm" in p:
        return "egm", RiskSeverity.WARN
    if "dividend" in p:
        return "dividend", RiskSeverity.WARN
    if "buy back" in p or "buyback" in p:
        return "buyback", RiskSeverity.WARN
    if "interest" in p:
        return "interest", RiskSeverity.WARN
    if a == "IGNORE":
        return "other_event", RiskSeverity.WARN
    if a == "UNKNOWN":
        return "unknown_event", RiskSeverity.WARN
    return "other_event", RiskSeverity.WARN


def event_flags(
    actions: Sequence[ActionEvent],
    as_of: str,
    *,
    horizon_days: int = DEFAULT_EVENT_HORIZON_DAYS,
) -> list[RiskFlag]:
    """Corporate-action shield. Future split/bonus/rights/other => BLOCK."""
    if horizon_days < 0:
        raise ValueError("horizon_days must be >= 0")
    try:
        start = ddate.fromisoformat(as_of)
    except ValueError:
        return [_flag("event_date_invalid", RiskSeverity.BLOCK, "invalid as_of")]
    end = start + timedelta(days=horizon_days)
    flags: list[RiskFlag] = []
    for event in actions:
        try:
            ex_date = ddate.fromisoformat(event.ex_date)
        except ValueError:
            continue
        if ex_date < start or ex_date > end:
            continue
        category, severity = _action_class(event.action, event.purpose)
        label = event.purpose[:80] if event.purpose else event.action
        flags.append(
            _flag(
                f"event_{category}",
                severity,
                f"{category} ex-date {event.ex_date}: {label}",
                event.ex_date,
            )
        )
    return flags


def build_trade_plan(
    *,
    symbol: str,
    capital: float,
    entry: float,
    stop: float,
    as_of: str,
    bars: Sequence[PriceBar],
    actions: Sequence[ActionEvent] = (),
    adv20_value: float | None = None,
    risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    adv_cap_pct: float = DEFAULT_ADV_CAP_PCT,
    lot_size: int = 1,
    min_adv_value: float = DEFAULT_MIN_ADV_VALUE,
    max_stale_days: int = DEFAULT_MAX_STALE_DAYS,
    event_horizon_days: int = DEFAULT_EVENT_HORIZON_DAYS,
) -> TradePlan:
    """Combine sizing and every hard check into one auditable trade plan."""
    bars_at = [b for b in bars if not as_of or b.date <= as_of]
    bars_at.sort(key=lambda b: b.date)
    flags: list[RiskFlag] = []
    if not bars_at:
        flags.append(_flag("no_bars", RiskSeverity.BLOCK, "no bars at/before as_of"))
    else:
        flags.extend(circuit_flags(bars_at))
        flags.extend(freshness_flags(bars_at[-1].date, as_of, max_stale_days=max_stale_days))
    flags.extend(liquidity_flags(adv20_value, min_adv_value=min_adv_value))
    flags.extend(event_flags(actions, as_of, horizon_days=event_horizon_days))

    sizing = size_position(
        capital,
        entry,
        stop,
        risk_per_trade_pct=risk_per_trade_pct,
        max_position_pct=max_position_pct,
        adv20_value=adv20_value,
        adv_cap_pct=adv_cap_pct,
        lot_size=lot_size,
    )
    if sizing.quantity <= 0:
        flags.append(
            _flag(
                "size_zero",
                RiskSeverity.BLOCK,
                f"position size is zero; binding constraint={sizing.binding_constraint}",
            )
        )
    unique = _dedupe(flags)
    allowed = sizing.quantity > 0 and not any(
        f.severity is RiskSeverity.BLOCK for f in unique
    )
    warnings = tuple(f.message for f in unique if f.severity is RiskSeverity.WARN)
    return TradePlan(
        symbol=symbol,
        as_of=as_of,
        allowed=allowed,
        sizing=sizing,
        flags=unique,
        warnings=warnings,
    )


def _adv20_from_rows(rows: Sequence[PriceBar]) -> float:
    """Average the last 20 daily turnover values (rupees-lakhs -> rupees)."""
    values = [b.turnover_lacs for b in rows[-20:] if b.turnover_lacs > 0]
    if not values:
        return 0.0
    return (sum(values) / len(values)) * 100_000.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--capital", type=float, required=True)
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--panel", default=DEFAULT_PANEL)
    p.add_argument("--actions", default=DEFAULT_ACTIONS)
    p.add_argument("--risk-pct", type=float, default=DEFAULT_RISK_PER_TRADE_PCT)
    p.add_argument("--max-position-pct", type=float, default=DEFAULT_MAX_POSITION_PCT)
    p.add_argument("--adv-cap-pct", type=float, default=DEFAULT_ADV_CAP_PCT)
    p.add_argument("--min-adv", type=float, default=DEFAULT_MIN_ADV_VALUE)
    p.add_argument("--event-horizon-days", type=int, default=DEFAULT_EVENT_HORIZON_DAYS)
    args = p.parse_args(argv)

    rows = load_panel_rows(
        args.panel,
        symbol=args.symbol,
        as_of=args.as_of,
        max_bars=60,
    )
    last = rows[-1]
    adv = _adv20_from_rows(rows)
    actions = load_actions(
        args.actions,
        as_of=args.as_of,
        horizon_days=args.event_horizon_days,
        symbol=args.symbol,
        isin=last.isin or None,
    )
    plan = build_trade_plan(
        symbol=args.symbol,
        capital=args.capital,
        entry=args.entry,
        stop=args.stop,
        as_of=args.as_of,
        bars=rows,
        actions=actions,
        adv20_value=adv,
        risk_per_trade_pct=args.risk_pct,
        max_position_pct=args.max_position_pct,
        adv_cap_pct=args.adv_cap_pct,
        min_adv_value=args.min_adv,
        event_horizon_days=args.event_horizon_days,
    )
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
