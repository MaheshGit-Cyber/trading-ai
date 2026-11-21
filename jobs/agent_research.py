#!/usr/bin/env python3
"""Agent web/news research CLI (read-only; no orders).

    python3 jobs/agent_research.py --search "NSE SEBI news"
    python3 jobs/agent_research.py --news "Nifty earnings"
    python3 jobs/agent_research.py --fetch "https://www.nseindia.com/..." --assess
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.web_research import ResearchError, WebResearch  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--search")
    group.add_argument("--news")
    group.add_argument("--fetch")
    p.add_argument("--max-results", type=int, default=5)
    p.add_argument("--assess", action="store_true")
    args = p.parse_args()
    tool = WebResearch()
    try:
        if args.search:
            out = [item.to_dict() for item in tool.search(args.search, max_results=args.max_results)]
            print(json.dumps({"query": args.search, "results": out}, indent=2, ensure_ascii=False))
        elif args.news:
            out = [item.to_dict() for item in tool.news(args.news, max_results=args.max_results)]
            print(json.dumps({"query": args.news, "news": out}, indent=2, ensure_ascii=False))
        else:
            page = tool.fetch(args.fetch, assess=args.assess)
            print(json.dumps(page.to_dict(), indent=2, ensure_ascii=False))
    except ResearchError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
