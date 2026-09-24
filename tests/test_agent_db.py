"""Tests for the agent pane's SQLite storage (bounded retention)."""

from __future__ import annotations

import sqlite3

import pytest

from btc_cycle_tracker.web import agent_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point the module at a temporary database and reset init state."""
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(agent_db, "_DB_PATH", db_path)
    monkeypatch.setattr(agent_db, "_initialized", False)
    return db_path


def _count(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _ids(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute(f"SELECT id FROM {table} ORDER BY id")]
    finally:
        conn.close()


class TestEventRetention:
    def test_events_pruned_past_cap_oldest_first(self, fresh_db, monkeypatch):
        monkeypatch.setattr(agent_db, "MAX_AGENT_EVENTS", 5)
        for i in range(8):
            agent_db.emit_event("completed", f"run {i}", task_id="analysis")

        assert _count(fresh_db, "agent_events") == 5
        assert _ids(fresh_db, "agent_events") == [4, 5, 6, 7, 8]  # newest survive

    def test_events_below_cap_untouched(self, fresh_db, monkeypatch):
        monkeypatch.setattr(agent_db, "MAX_AGENT_EVENTS", 50)
        for i in range(3):
            agent_db.emit_event("started", f"run {i}", task_id="analysis")

        assert _count(fresh_db, "agent_events") == 3

    def test_event_fields_stored_correctly(self, fresh_db):
        agent_db.emit_event("started", "Analysis run: BTC-USD 5m", task_id="analysis")

        with agent_db.connect() as conn:
            row = conn.execute("SELECT * FROM agent_events").fetchone()
        assert row["task_id"] == "analysis"
        assert row["event_type"] == "started"
        assert row["message"] == "Analysis run: BTC-USD 5m"


class TestChatRetention:
    def test_chat_messages_pruned_past_cap_oldest_first(self, fresh_db, monkeypatch):
        monkeypatch.setattr(agent_db, "MAX_CHAT_MESSAGES", 4)
        for i in range(7):
            agent_db.add_chat_message("user", f"message {i}")

        assert _count(fresh_db, "agent_chat_messages") == 4
        assert _ids(fresh_db, "agent_chat_messages") == [4, 5, 6, 7]
        with agent_db.connect() as conn:
            roles = [r[0] for r in conn.execute("SELECT role FROM agent_chat_messages")]
        assert roles == ["user"] * 4

    def test_interleaved_writes_prune_both_tables(self, fresh_db, monkeypatch):
        monkeypatch.setattr(agent_db, "MAX_AGENT_EVENTS", 3)
        monkeypatch.setattr(agent_db, "MAX_CHAT_MESSAGES", 3)
        for i in range(6):
            agent_db.emit_event("completed", f"e{i}", task_id="t")
            agent_db.add_chat_message("assistant", f"m{i}")

        assert _count(fresh_db, "agent_events") == 3
        assert _count(fresh_db, "agent_chat_messages") == 3
        assert _ids(fresh_db, "agent_events") == [4, 5, 6]
        assert _ids(fresh_db, "agent_chat_messages") == [4, 5, 6]


class TestBackfillBounding:
    def test_preexisting_grown_db_rebounded_on_init(self, fresh_db, monkeypatch):
        # A database that grew under an older, unbounded version.
        conn = sqlite3.connect(fresh_db)
        try:
            conn.executescript(agent_db._SCHEMA)
            for i in range(10):
                conn.execute(
                    "INSERT INTO agent_events (task_id, event_type, message) VALUES (?, ?, ?)",
                    ("t", "completed", f"old {i}"),
                )
                conn.execute(
                    "INSERT INTO agent_chat_messages (role, content) VALUES (?, ?)",
                    ("user", f"old {i}"),
                )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr(agent_db, "MAX_AGENT_EVENTS", 4)
        monkeypatch.setattr(agent_db, "MAX_CHAT_MESSAGES", 4)
        agent_db._ensure_initialized()  # first use re-bounds it

        assert _count(fresh_db, "agent_events") == 4
        assert _count(fresh_db, "agent_chat_messages") == 4
        assert _ids(fresh_db, "agent_events") == [7, 8, 9, 10]
        assert _ids(fresh_db, "agent_chat_messages") == [7, 8, 9, 10]
