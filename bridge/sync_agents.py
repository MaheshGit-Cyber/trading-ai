#!/usr/bin/env python3
"""sync_agents.py — Automated Agent Communication Bridge (Method 3).

Watches OpenCode's SQLite database and the bridge/ directory.
Keeps conversation context synced between OpenCode and Antigravity.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRIDGE_DIR = os.path.join(ROOT, "bridge")
DB_PATH = "/data/data/com.termux/files/home/.local/share/opencode/opencode.db"
HISTORY_FILE = os.path.join(BRIDGE_DIR, "chat_history.jsonl")


def get_latest_opencode_assistant_msg(session_id: str | None = None) -> dict | None:
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if session_id:
        cur.execute(
            """
            SELECT id, type, time_created, data 
            FROM session_message 
            WHERE session_id = ? AND type = 'assistant'
            ORDER BY time_created DESC LIMIT 1;
        """,
            (session_id,),
        )
    else:
        cur.execute("""
            SELECT id, type, time_created, data 
            FROM session_message 
            WHERE type = 'assistant'
            ORDER BY time_created DESC LIMIT 1;
        """)
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    msg_id, msg_type, time_created, data_raw = row
    data = json.loads(data_raw)
    texts = [c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"]
    return {
        "id": msg_id,
        "time_created": time_created,
        "text": "\n".join(texts),
        "data": data,
    }


def sync_cycle() -> dict:
    os.makedirs(BRIDGE_DIR, exist_ok=True)
    latest_oc = get_latest_opencode_assistant_msg()
    status = {
        "timestamp": time.time(),
        "latest_opencode_msg_id": latest_oc["id"] if latest_oc else None,
        "latest_opencode_msg_len": len(latest_oc["text"]) if latest_oc else 0,
    }
    # Log to history
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(status) + "\n")
    return status


if __name__ == "__main__":
    res = sync_cycle()
    print("Sync complete:", json.dumps(res, indent=2))
