"""Hard permission boundary for the research agent.

The agent is allowed to read, research and write notes. It is not allowed to
place orders, move money, promote a strategy, change live rules or grant itself
permissions. This module is intentionally tiny and code-first.
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED = {
    "read_time",
    "read_calendar",
    "read_web",
    "search_web",
    "read_news",
    "read_local_data",
    "write_research_note",
    "write_research_code",
    "run_backtest",
    "append_memory",
    "register_hypothesis",
    "evaluate_gates",
    "paper_report",
}
DENIED = {
    "place_order",
    "cancel_order",
    "transfer_money",
    "set_position_size_live",
    "change_live_rules",
    "promote_strategy",
    "approve_strategy",
    "bypass_risk_gate",
    "grant_permission",
    "disable_audit_log",
    "use_unlicensed_data_in_product",
}


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    action: str
    allowed: bool
    reason: str

    def to_dict(self) -> dict:
        return {"action": self.action, "allowed": self.allowed, "reason": self.reason}


def check(action: str) -> PermissionDecision:
    action = (action or "").strip()
    if action in ALLOWED:
        return PermissionDecision(action, True, "research/read-only power")
    if action in DENIED:
        return PermissionDecision(action, False, "execution/authority power is permanently denied")
    return PermissionDecision(action, False, "unknown action; default deny")


def require(action: str) -> None:
    decision = check(action)
    if not decision.allowed:
        raise PermissionError(f"{decision.action}: {decision.reason}")
