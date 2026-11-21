"""Trained-artifact paths. Single source of truth so nothing hardcodes a path."""

from __future__ import annotations

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = os.path.join(ROOT, "config", "models.json")
RULES = os.path.join(ROOT, "memory", "rules.json")
MEMORY = os.path.join(ROOT, "memory", "memory.jsonl")
KNOWLEDGE = os.path.join(ROOT, "memory", "knowledge")
RAG_INDEX = os.path.join(ROOT, "memory", "rag", "index.json")

# The course has lived in two places across checkouts. Prefer the sibling
# ``course/`` directory that ships with this workspace; fall back to the
# older ``analysis/course`` layout so existing indexes remain reproducible.
_COURSE_SIBLING = os.path.abspath(os.path.join(ROOT, "..", "course"))
_COURSE_LEGACY = os.path.abspath(os.path.join(ROOT, "..", "analysis", "course"))
COURSE_DIR = (
    _COURSE_SIBLING if os.path.isdir(_COURSE_SIBLING) else _COURSE_LEGACY
)
