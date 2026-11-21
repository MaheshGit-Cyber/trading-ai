#!/usr/bin/env python3
"""Assess one news item's credibility risk.

    python3 jobs/agent_news.py --title "..." --body "..." \
        --source "moneycontrol.com" --url "https://..." --published 2026-11-21T09:00:00+05:30
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.news_guard import assess_news  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--source", default="")
    p.add_argument("--url", default="")
    p.add_argument("--published", default=None)
    p.add_argument("--confirmations", type=int, default=0)
    args = p.parse_args()
    result = assess_news(
        title=args.title,
        body=args.body,
        source=args.source,
        url=args.url,
        published_at=args.published,
        confirmations=args.confirmations,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
