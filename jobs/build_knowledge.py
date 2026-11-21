"""Build the always-loadable knowledge pack from analysis/course.

Why a pack when RAG exists:
  * RAG retrieves on query. Core definitions should not depend on a
    retrieval hit -- if the query words differ, retrieval misses.
  * The pack must FIT in context. The full course is ~94K tokens and
    cannot be loaded. The glossary alone is ~2K tokens.

Extraction is mechanical and deterministic: glossary terms + module
outline + numeric thresholds. No LLM rewriting -- a rewritten summary
can silently change a definition, and then the eval measures the
rewrite rather than the course.

    python3 jobs/build_knowledge.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import paths  # noqa: E402

OUT = os.path.join(paths.ROOT, "memory", "knowledge", "pack.json")

# - **Term** — definition   (em dash, en dash, or hyphen)
_GLOSSARY = re.compile(r"^-\s*\*\*(.+?)\*\*\s*(?:—|–|-)\s*(.+?)\s*$")
_H12 = re.compile(r"^(#{1,2})\s+(.*)$")
# "2% risk", "1:2 R:R", "N >= 100", "10 orders/sec" -- keep as-is, verbatim.
_THRESH = re.compile(
    r"[^\n.]*?\b(?:\d+(?:\.\d+)?\s*%|\d+\s*:\s*\d+|N\s*>=?\s*\d+|"
    r"\d+\s*orders?/sec|₹\s?[\d,]+)[^\n.]*"
)
_STOP = set(
    """a an the and or but of in on at to for with from by as is are was were be
    this that it its we you they not no so than too very can will just about""".split()
)


def _terms(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower())
            if len(w) > 2 and w not in _STOP}


def build_glossary() -> dict[str, str]:
    src = os.path.join(paths.COURSE_DIR, "resources", "glossary.md")
    out: dict[str, str] = {}
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _GLOSSARY.match(line.strip())
            if m:
                term = m.group(1).strip()
                if term not in out:  # first definition wins
                    out[term] = m.group(2).strip()
    return out


def build_outline() -> dict[str, list[str]]:
    """Module -> [h1/h2 headings]. Gives the model the map of the corpus."""
    outline: dict[str, list[str]] = {}
    for root, _d, files in sorted(os.walk(paths.COURSE_DIR)):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, paths.COURSE_DIR)
            heads: list[str] = []
            with open(full, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = _H12.match(line)
                    if m:
                        t = m.group(2).strip()
                        # Drop decorative emoji headings' icons only.
                        t = re.sub(r"^[^\w(]+", "", t).strip()
                        if t:
                            heads.append(t)
            if heads:
                outline[rel] = heads[:14]  # cap per file
    return outline


def build_thresholds() -> list[str]:
    """Verbatim numeric rules from the corpus -- these are the ones that bite."""
    seen: set[str] = set()
    out: list[str] = []
    for root, _d, files in os.walk(paths.COURSE_DIR):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as f:
                text = f.read()
            for m in _THRESH.finditer(text):
                s = m.group(0).strip()
                s = re.sub(r"\s+", " ", s)
                if not (12 <= len(s) <= 160):
                    continue
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(s)
    return out[:120]


def main() -> None:
    glossary = build_glossary()
    outline = build_outline()
    thresholds = build_thresholds()

    pack = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": paths.COURSE_DIR,
        "note": ("Mechanically extracted from analysis/course. Definitions are "
                 "verbatim from resources/glossary.md -- do not paraphrase them "
                 "when answering. This is a fallback for core terms; deeper "
                 "material comes from RAG over the same corpus."),
        "glossary": glossary,
        "outline": outline,
        "thresholds": thresholds,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)

    body = json.dumps(pack, ensure_ascii=False)
    print(f"[knowledge] glossary   : {len(glossary)} terms")
    print(f"[knowledge] outline    : {len(outline)} files, "
          f"{sum(len(v) for v in outline.values())} headings")
    print(f"[knowledge] thresholds : {len(thresholds)} verbatim rules")
    print(f"[knowledge] pack size  : {len(body):,} chars "
          f"(~{len(body)//4:,} tokens) -> {OUT}")
    if len(body) // 4 > 8000:
        print("[knowledge] WARNING: pack exceeds ~8K tokens -- trim before "
              "putting it in a system prompt")


if __name__ == "__main__":
    main()
