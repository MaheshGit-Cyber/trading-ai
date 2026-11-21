"""Append-only agent research memory.

This is separate from ``memory/memory.jsonl`` (the evidence/outcome log). It
stores research events, news assessments, hypotheses, lessons and errors.
Nothing is auto-promoted from this log into production rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Iterable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_PATH = os.path.join(ROOT, "data", "agent", "agent_memory.jsonl")
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
KINDS = ("research", "news", "hypothesis", "lesson", "strategy_result", "error", "clock", "paper")
STATUSES = ("logged", "quarantined", "rejected", "promoted_by_human")


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    ts: str
    kind: str
    summary: str
    payload: dict
    source: str = ""
    tags: tuple[str, ...] = ()
    status: str = "logged"

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "kind": self.kind,
            "summary": self.summary,
            "payload": self.payload,
            "source": self.source,
            "tags": list(self.tags),
            "status": self.status,
        }


class AgentMemory:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path

    def append(
        self,
        kind: str,
        summary: str,
        payload: dict | None = None,
        *,
        source: str = "",
        tags: Iterable[str] = (),
        status: str = "logged",
        ts: datetime | None = None,
    ) -> MemoryEvent:
        if kind not in KINDS:
            raise ValueError(f"agent_memory.kind must be one of {KINDS}")
        if status not in STATUSES:
            raise ValueError(f"agent_memory.status must be one of {STATUSES}")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("agent_memory.summary required")
        payload = payload or {}
        if not isinstance(payload, dict):
            raise TypeError("agent_memory.payload must be a dict")
        clean_tags = tuple(str(t).strip().lower() for t in tags if str(t).strip())
        now = ts or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        event = MemoryEvent(
            ts=now.astimezone(IST).isoformat(timespec="seconds"),
            kind=kind,
            summary=summary.strip(),
            payload=payload,
            source=str(source or ""),
            tags=clean_tags,
            status=status,
        )
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def read(self, *, limit: int = 100, kind: str | None = None) -> list[MemoryEvent]:
        if limit <= 0:
            return []
        if not os.path.exists(self.path):
            return []
        out: list[MemoryEvent] = []
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"agent_memory corrupt line {i}: {exc}") from exc
                event = MemoryEvent(
                    ts=str(obj["ts"]),
                    kind=str(obj["kind"]),
                    summary=str(obj["summary"]),
                    payload=dict(obj.get("payload") or {}),
                    source=str(obj.get("source") or ""),
                    tags=tuple(obj.get("tags") or ()),
                    status=str(obj.get("status") or "logged"),
                )
                if kind is None or event.kind == kind:
                    out.append(event)
        return out[-limit:]

    def by_tag(self, tag: str, *, limit: int = 50) -> list[MemoryEvent]:
        wanted = tag.strip().lower()
        return [e for e in self.read(limit=10_000) if wanted in e.tags][-limit:]
