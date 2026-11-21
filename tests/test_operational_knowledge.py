"""Operational knowledge tests: does the teaching material exist, is it
internally consistent, and can the model actually retrieve it?

    python3 tests/test_operational_knowledge.py

Three separate failure modes are covered:

  1. The files exist and parse. (Trivial, but a missing file silently
     degrades the whole layer.)
  2. The arithmetic inside them is right. Stated costs must equal the
     rates. I got the SEBI fee wrong by 10x on the first pass.
  3. Retrieval reaches them. A rule the model cannot retrieve is a rule
     that does not exist at query time.
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from engine import paths, rag  # noqa: E402

PASS = 0
FAIL = 0

_spec = importlib.util.spec_from_file_location(
    "validate_knowledge", os.path.join(ROOT, "jobs", "validate_knowledge.py"))
vk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vk)

# Every one of these must appear in the top-5 retrieved chunks. Top-1 is
# not required -- the evidence layer feeds k=4, so top-5 coverage is the
# property that matters.
RETRIEVAL_CASES = [
    ("F&O ban period MWPL open interest", "execution.json"),
    ("STT rate options premium futures sell", "costs.json"),
    ("adj factor split bonus adjustment", "execution.json"),
    ("circuit limit upper lower band stock", "execution.json"),
    ("R multiple win loss scratch definition", "outcomes.json"),
    ("ADX uptrend regime definition 200DMA", "regimes.json"),
    ("false breakout failure mode volume", "failures.json"),
    ("earnings within horizon no trade calendar", "calendar.json"),
    ("trend pullback entry stop target", "setups.json"),
    ("MFE MAE maximum adverse excursion", "outcomes.json"),
    ("slippage largecap midcap smallcap", "costs.json"),
    ("freeze quantity tick size spread", "execution.json"),
    ("brokerage delivery zero intraday twenty", "costs.json"),
    ("regime trend_down no long setups", "regimes.json"),
    ("results season position size halve", "calendar.json"),
    ("what are the charges for equity delivery", "costs.json"),
    ("when is a stock in the ban list", "execution.json"),
    ("how do i label a scratch trade", "outcomes.json"),
]


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def main() -> None:
    print("files:")
    data = vk.load_all()

    def _counts():
        assert len(data) == 7, f"expected 7 files, got {len(data)}"
        assert len(data["setups"]["setups"]) >= 4, "too few setups"
    ok("7 knowledge files load", _counts)

    print("\ncost arithmetic:")
    calc = vk.recompute_costs(data["costs"])
    examples = data["costs"]["worked_examples"]
    for seg, got in calc.items():
        stated = examples[seg]["total"]

        def _match(s=stated, g=got["total"]):
            assert abs(s - g) <= 0.02 * max(1.0, abs(g)), f"{s} != {g}"
        ok(f"{seg} total {stated} matches rates", _match)

    print("\ninternal consistency:")
    setup_ids = {s["id"] for s in data["setups"]["setups"]}

    def _regime_refs():
        for reg in data["regimes"]["regimes"]:
            for sid in reg.get("tradeable_setups", []):
                assert sid in setup_ids, f"{reg['id']} -> unknown setup {sid}"
            for sid in reg.get("avoid", []):
                assert sid in setup_ids or sid == "all", \
                    f"{reg['id']} avoids unknown setup {sid}"
    ok("regime -> setup references resolve", _regime_refs)

    def _failure_coverage():
        fm = data["failures"]["by_setup"]
        for sid in setup_ids:
            assert sid in fm and len(fm[sid]) >= 2, f"{sid} lacks failure modes"
    ok("every setup has >= 2 failure modes", _failure_coverage)

    def _rr_floor():
        floor = data["setups"]["global_rules"]["min_rr"]
        for s in data["setups"]["setups"]:
            assert s["min_rr"] >= floor, f"{s['id']} below RR floor"
    ok("no setup below the global RR floor", _rr_floor)

    def _gaps_closed():
        ex = data["execution"]
        assert "fno_ban_period" in ex, "ban period missing"
        assert "adj_factor" in ex["corporate_actions"], "adj_factor missing"
        assert "circuit_limits" in ex, "circuit limits missing"
        assert len(data["calendar"]["hard_blocks"]) >= 4, "calendar too thin"
    ok("course gaps closed (ban/adj_factor/circuit/calendar)", _gaps_closed)

    print("\nretrieval (top-5 must contain the right knowledge file):")
    assert os.path.exists(paths.RAG_INDEX), "run jobs/teach.py --build-rag first"
    idx = rag.load(paths.RAG_INDEX)

    for q, want in RETRIEVAL_CASES:
        def _hit(q=q, want=want):
            res = rag.query(idx, q, k=5)
            srcs = [r["src"] for r in res]
            assert any(want in s for s in srcs), f"{want} not in top5: {srcs}"
        ok(f"{q[:40]:42s} -> {want}", _hit)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
