#!/usr/bin/env python3
"""Strategy registry CLI: register a hypothesis, run frozen gates, list status.

This CLI cannot approve or promote a strategy. A result is at most
``gate_passed``; paper/product approval is a human decision.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.strategy_lab import StrategyRegistry, StrategySpec  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--register", metavar="SPEC.json")
    p.add_argument("--evaluate", metavar="METRICS.json")
    p.add_argument("--strategy-id")
    p.add_argument("--list", action="store_true")
    p.add_argument("--path", default=None)
    args = p.parse_args()
    reg = StrategyRegistry(args.path) if args.path else StrategyRegistry()

    if args.register:
        with open(args.register, encoding="utf-8") as f:
            obj = json.load(f)
        spec = StrategySpec(**obj)
        reg.register(spec)
        print(json.dumps({"registered": spec.strategy_id}, indent=2))
    elif args.evaluate:
        if not args.strategy_id:
            p.error("--strategy-id required with --evaluate")
        with open(args.evaluate, encoding="utf-8") as f:
            metrics = json.load(f)
        result = reg.record_result(args.strategy_id, metrics)
        print(json.dumps(result, indent=2))
    elif args.list:
        print(json.dumps(reg.list(), indent=2, ensure_ascii=False))
    else:
        p.error("choose --register, --evaluate or --list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
