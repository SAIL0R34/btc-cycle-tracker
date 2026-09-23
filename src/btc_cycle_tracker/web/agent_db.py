"""SQLite storage for the agent pane: live activity events + chat transcript.

Same two-table shape as the opportunity_pipeline agent stack, so the ported
AgentPanel component works unchanged: `agent_events` feeds the Live tab (via
SSE) and `agent_chat_messages` persists the conversation across refreshes.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from btc_cycle_tracker.settings import settings

_DB_PATH = settings.data_path / "agent.db"
_init_lock = threading.Lock()
_initialized = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT DEFAULT '',
    event_type TEXT NOT NULL,
    message TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS agent_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


@contextmanager
def connect():
    """Context-managed connection with dict-style rows and autocommit."""
    _ensure_initialized()
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def emit_event(event_type: str, message: str, task_id: str = "chat") -> None:
    """Record an agent activity event; never raises."""
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO agent_events (task_id, event_type, message) VALUES (?, ?, ?)",
                (task_id, event_type, message),
            )
    except Exception:  # noqa: BLE001 - activity logging must never break the app
        pass
