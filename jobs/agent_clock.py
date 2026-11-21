#!/usr/bin/env python3
"""Print live IST clock/market-session context as JSON."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.clock import snapshot  # noqa: E402


def main() -> int:
    print(json.dumps(snapshot().to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
