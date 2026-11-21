#!/usr/bin/env python3
"""Read the append-only agent research memory."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.memory import AgentMemory  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list", action="store_true")
    p.add_argument("--kind", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--path", default=None)
    args = p.parse_args()
    mem = AgentMemory(args.path) if args.path else AgentMemory()
    events = mem.read(limit=args.limit, kind=args.kind)
    print(json.dumps([e.to_dict() for e in events], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
