"""Internal paper-trading ledger: daily signals, no orders, no real money.

The ledger is deliberately boring:

- one immutable JSON snapshot per trading date
- one append-only JSONL line per snapshot
- target weights, sleeve reference prices, warnings and the data date
- no broker, no execution, no return claim

The 2–3 month clock starts only when daily NSE data is actually available. A
snapshot is never written for a date after the latest Nifty bar; otherwise the
“track record” would contain fabricated days.
"""

from __future__ import annotations

import csv
from datetime import date as ddate, datetime, timezone
import json
import os
from typing import Sequence

from brain.allocator import ENGINE, allocate_from_nifty
from brain.contracts import PaperSnapshot
from brain.data import PriceBar

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_GOLD = os.path.join(ROOT, "data", "gold", "goldbees_daily_2010_2026.csv")
DEFAULT_PAPER_DIR = os.path.join(ROOT, "data", "paper_trading")
DEBT_BASE_DATE = "2010-01-04"
DEBT_YIELD = 0.07


def _last_close(path: str, as_of: str) -> tuple[float, str]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    last: tuple[float, str] | None = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            day = (row.get("date") or "").strip()
            if not day or day > as_of:
                continue
            try:
                close = float(row.get("close") or 0)
            except (TypeError, ValueError):
                continue
            if close > 0:
                last = (close, day)
    if last is None:
        raise LookupError(f"no close for {path} up to {as_of}")
    return last


def synthetic_debt_price(as_of: str) -> float:
    """A 7% calendar-day ledger. This is a proxy, not a traded G-Sec."""
    days = (ddate.fromisoformat(as_of) - ddate.fromisoformat(DEBT_BASE_DATE)).days
    if days < 0:
        raise ValueError("as_of before debt base date")
    return (1.0 + DEBT_YIELD) ** (days / 365.25)


def build_snapshot(
    nifty_rows: Sequence[PriceBar],
    *,
    capital: float,
    risk_score: int,
    engine: str = ENGINE,
    gold_path: str = DEFAULT_GOLD,
    as_of: str | None = None,
    created_at: str | None = None,
) -> PaperSnapshot:
    """Build one paper snapshot from the same allocator used by the product."""
    view, allocation = allocate_from_nifty(
        nifty_rows,
        risk_score=risk_score,
        capital=capital,
        engine=engine,
        as_of=as_of,
    )
    if not allocation.allowed:
        raise ValueError(
            f"engine {engine!r} refused: {', '.join(allocation.flags)}"
        )
    cutoff = view.as_of
    if allocation.as_of and allocation.as_of != cutoff:
        raise ValueError("allocation/data date mismatch")
    nifty_close = view.nifty_close
    if nifty_close is None or nifty_close <= 0:
        raise ValueError("Nifty close missing")
    gold_close, gold_date = _last_close(gold_path, cutoff)
    warnings = list(allocation.warnings)
    if gold_date != cutoff:
        warnings.append(
            f"Gold price date {gold_date} does not match signal date {cutoff}."
        )
    warnings.append(
        "Paper ledger only: no order was placed and no real money is involved."
    )
    prices = {
        "nifty50": nifty_close,
        "gold_bees": gold_close,
        "debt": synthetic_debt_price(cutoff),
        "cash": 1.0,
    }
    return PaperSnapshot(
        as_of=cutoff,
        created_at=created_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        capital=float(capital),
        engine=engine,
        regime=view.regime,
        risk_score=risk_score,
        allocation=allocation.to_dict(),
        sleeve_prices=prices,
        warnings=tuple(warnings),
        note=(
            "Append-only internal paper signal. Target weights are not an order. "
            "Debt is a synthetic 7% ledger; gold/Nifty are research data."
        ),
    )


def record_snapshot(
    snapshot: PaperSnapshot,
    *,
    root: str = DEFAULT_PAPER_DIR,
) -> tuple[str, str]:
    """Write one snapshot and append one ledger line. Never overwrite a date."""
    snap_dir = os.path.join(root, "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    path = os.path.join(snap_dir, f"{snapshot.as_of}.json")
    ledger = os.path.join(root, "ledger.jsonl")
    if os.path.exists(path):
        raise FileExistsError(f"snapshot already exists: {path}")
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    old = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"corrupt ledger line: {ledger}") from exc
                if old.get("as_of") == snapshot.as_of:
                    raise FileExistsError(
                        f"ledger already has {snapshot.as_of}; snapshot file missing"
                    )
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True))
        f.write("\n")
    return path, ledger


def load_snapshots(root: str = DEFAULT_PAPER_DIR) -> list[PaperSnapshot]:
    ledger = os.path.join(root, "ledger.jsonl")
    if not os.path.exists(ledger):
        return []
    out: list[PaperSnapshot] = []
    with open(ledger, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            out.append(PaperSnapshot(**obj))
    out.sort(key=lambda s: s.as_of)
    return out


def latest_snapshot(root: str = DEFAULT_PAPER_DIR) -> PaperSnapshot | None:
    snaps = load_snapshots(root)
    return snaps[-1] if snaps else None


def main() -> int:
    print("Use jobs/paper_snapshot.py to record a daily signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
