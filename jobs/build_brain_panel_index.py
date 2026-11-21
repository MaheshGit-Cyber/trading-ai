#!/usr/bin/env python3
"""Build the SQLite byte-offset index for the NSE adjusted panel.

    python3 jobs/build_brain_panel_index.py
    python3 jobs/build_brain_panel_index.py --force

The index stores offsets only, not a second copy of prices. It is a local
research cache; do not ship it to users.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brain.data import DEFAULT_PANEL  # noqa: E402
from brain.panel_index import DEFAULT_INDEX, build_index  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default=DEFAULT_PANEL)
    p.add_argument("--out", default=DEFAULT_INDEX)
    p.add_argument("--batch-size", type=int, default=50_000)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    meta = build_index(
        args.panel,
        args.out,
        batch_size=args.batch_size,
        force=args.force,
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
