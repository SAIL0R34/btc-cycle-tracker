"""SQLite storage for the agent pane: live activity events + chat transcript.

Same two-table shape as the opportunity_pipeline agent stack, so the ported
AgentPanel component works unchanged: `agent_events` feeds the Live tab (via
SSE) and `agent_chat_messages` persists the conversation across refreshes.

Both tables are bounded: writes prune the oldest rows past the caps below
(same transaction), and initialization prunes once so a pre-existing grown
database is re-bounded on first use. The visible feed reads the last ~50
events and chat history the last 200-1000, so the caps are set generously
beyond any read path.
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

MAX_AGENT_EVENTS = 5000    # retention cap for the activity feed
MAX_CHAT_MESSAGES = 5000   # retention cap for the chat transcript


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


def _prune(conn: sqlite3.Connection) -> None:
    """Bound both tables, evicting the oldest rows first.

    Runs inside the caller's transaction (connect() commits), so an insert
    and its pruning land — or don't — together.
    """
    conn.execute(
        "DELETE FROM agent_events WHERE id NOT IN "
        "(SELECT id FROM agent_events ORDER BY id DESC LIMIT ?)",
        (MAX_AGENT_EVENTS,),
    )
    conn.execute(
        "DELETE FROM agent_chat_messages WHERE id NOT IN "
        "(SELECT id FROM agent_chat_messages ORDER BY id DESC LIMIT ?)",
        (MAX_CHAT_MESSAGES,),
    )


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
            _prune(conn)  # re-bound a database that grew under an older version
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
            _prune(conn)
    except Exception:  # noqa: BLE001 - activity logging must never break the app
        pass


def add_chat_message(role: str, content: str) -> None:
    """Record one chat turn; never raises."""
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO agent_chat_messages (role, content) VALUES (?, ?)",
                (role, content),
            )
            _prune(conn)
    except Exception:  # noqa: BLE001 - transcript logging must never break the app
        pass
