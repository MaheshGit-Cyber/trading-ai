"""Validate the operational knowledge files. No model calls.

The point is not "does the JSON parse". It is:

  * Do the cost worked-examples actually equal the stated rates?
    (I got the SEBI fee wrong by 10x on the first pass. This catches that.)
  * Does every setup referenced by a regime exist?
  * Does every setup have at least one failure mode? A setup without a
    stated failure mode is an advertisement, not a specification.
  * Is any RR floor below the rules.json minimum?

    python3 jobs/validate_knowledge.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import paths  # noqa: E402

K = os.path.join(paths.ROOT, "memory", "knowledge")
FILES = ["setups", "outcomes", "regimes", "costs", "failures", "execution", "calendar"]
TOL = 0.02  # 2% tolerance on money

PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def load_all() -> dict:
    out = {}
    for name in FILES:
        p = os.path.join(K, f"{name}.json")
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
        with open(p, encoding="utf-8") as f:
            out[name] = json.load(f)
    return out


def recompute_costs(costs: dict) -> dict:
    """Recompute each worked example from the rate table. Rs 1,00,000 basis."""
    turnover = 100_000.0
    a = costs["assumptions"]
    out = {}
    for seg, r in costs["segments"].items():
        if seg == "equity_delivery":
            brok = a["brokerage_delivery"] * turnover * 2
        else:
            per_side = min(a["brokerage_intraday_flat"],
                           a["brokerage_intraday_pct"] * turnover)
            brok = per_side * 2
        stt = (r["stt_buy_pct"] + r["stt_sell_pct"]) * turnover
        stamp = r["stamp_duty_buy_pct"] * turnover
        exch = r["exchange_txn_pct"] * turnover * 2
        sebi = r["sebi_fee_pct"] * turnover * 2
        gst = a["gst_rate"] * (brok + exch + sebi)
        dp = r.get("dp_charge_sell", 0.0)
        total = brok + stt + stamp + exch + sebi + gst + dp
        out[seg] = {"total": round(total, 2), "bps": round(total / turnover * 10000, 2)}
    return out


def main() -> None:
    print("load:")
    data = load_all()
    ok("all 7 files parse", lambda: None)

    setups = data["setups"]["setups"]
    setup_ids = {s["id"] for s in setups}
    print(f"\nsetups: {len(setups)} -> {sorted(setup_ids)}")

    print("\ncost arithmetic (recomputed from rates, Rs 1,00,000):")
    calc = recompute_costs(data["costs"])
    examples = data["costs"]["worked_examples"]
    for seg, got in calc.items():
        stated = examples.get(seg, {}).get("total")
        if stated is None:
            continue
        ok(f"{seg}: stated {stated} == computed {got['total']}",
           lambda s=stated, g=got["total"]: (
               abs(s - g) <= TOL * max(1.0, abs(g)) or
               (_ for _ in ()).throw(AssertionError(f"{s} vs {g}"))))

    print("\ncross-references:")
    for reg in data["regimes"]["regimes"]:
        for sid in reg.get("tradeable_setups", []):
            if sid == "all":
                continue
            ok(f"regime {reg['id']} -> setup {sid} exists",
               lambda sid=sid: (
                   sid in setup_ids or
                   (_ for _ in ()).throw(AssertionError(f"unknown setup {sid}"))))

    fm = data["failures"]["by_setup"]
    for sid in sorted(setup_ids):
        ok(f"setup {sid} has failure modes",
           lambda sid=sid: (
               sid in fm and len(fm[sid]) >= 2 or
               (_ for _ in ()).throw(AssertionError("missing or thin"))))

    print("\nrisk floors:")
    min_rr = data["outcomes"].get("aggregation", {}).get("min_sample")
    ok("outcomes min_sample >= 100", lambda: (
        min_rr is not None and min_rr >= 100 or
        (_ for _ in ()).throw(AssertionError(f"min_sample={min_rr}"))))
    floor = data["setups"]["global_rules"]["min_rr"]
    for s in setups:
        ok(f"{s['id']} min_rr {s['min_rr']} >= global {floor}",
           lambda s=s, floor=floor: (
               s["min_rr"] >= floor or
               (_ for _ in ()).throw(AssertionError("below floor"))))

    print("\nexecution / calendar coverage:")
    ex = data["execution"]
    ok("ban period documented", lambda: (
        "fno_ban_period" in ex or
        (_ for _ in ()).throw(AssertionError("missing ban period"))))
    ok("adj_factor documented", lambda: (
        "adj_factor" in ex["corporate_actions"] or
        (_ for _ in ()).throw(AssertionError("missing adj_factor"))))
    ok("circuit limits documented", lambda: (
        "circuit_limits" in ex or
        (_ for _ in ()).throw(AssertionError("missing circuit limits"))))
    cal = data["calendar"]
    ok("hard blocks present", lambda: (
        len(cal.get("hard_blocks", [])) >= 4 or
        (_ for _ in ()).throw(AssertionError("too few hard blocks"))))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
