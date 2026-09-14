"""SQLite-backed state: which emails were processed, and which events exist.

Two jobs:
  1. Never process the same email twice (dedupe by RFC-822 Message-ID).
  2. Never create the same calendar event twice, even if a bill/appointment is
     emailed more than once (dedupe by a stable event key).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id  TEXT PRIMARY KEY,
    folder      TEXT,
    processed_at REAL,
    category    TEXT,
    action      TEXT,
    event_id    TEXT
);
CREATE TABLE IF NOT EXISTS created_events (
    event_key   TEXT PRIMARY KEY,
    event_id    TEXT,
    calendar_id TEXT,
    category    TEXT,
    summary     TEXT,
    created_at  REAL
);
"""


class State:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # --- messages ---
    def is_message_processed(self, message_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
        )
        return cur.fetchone() is not None

    def mark_message_processed(
        self,
        message_id: str,
        folder: str,
        category: str,
        action: str,
        event_id: str | None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO processed_messages "
            "(message_id, folder, processed_at, category, action, event_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message_id, folder, time.time(), category, action, event_id),
        )
        self.conn.commit()

    # --- events ---
    def event_exists(self, event_key: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM created_events WHERE event_key = ?", (event_key,)
        )
        return cur.fetchone() is not None

    def record_event(
        self,
        event_key: str,
        event_id: str,
        calendar_id: str,
        category: str,
        summary: str,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO created_events "
            "(event_key, event_id, calendar_id, category, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_key, event_id, calendar_id, category, summary, time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
