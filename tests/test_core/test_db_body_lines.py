from __future__ import annotations

import json
import sqlite3

import pytest

from bad_research.core.db import SCHEMA_VERSION, get_connection, init_schema


@pytest.fixture
def mem_conn():
    """Fresh in-memory DB fully migrated to current SCHEMA_VERSION."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        conn = get_connection(Path(d) / "test.db")
        init_schema(conn)
        yield conn
        conn.close()


def test_schema_version_is_10(mem_conn):
    row = mem_conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    assert int(row[0] if isinstance(row, tuple) else row["value"]) == 10


def test_note_content_has_body_lines_column(mem_conn):
    cols = {row[1] for row in mem_conn.execute("PRAGMA table_info(note_content)")}
    assert "body_lines" in cols


def test_body_lines_column_accepts_null_and_json(mem_conn):
    # Insert a stub note row first (FK required).
    mem_conn.execute(
        "INSERT INTO notes (id, title, path, status, type, created, file_mtime, content_hash, synced_at) "
        "VALUES ('n1', 'T', 'n1.md', 'draft', 'note', '2026-01-01T00:00:00Z', 0.0, 'abc', '2026-01-01T00:00:00Z')"
    )
    # NULL (old note without body_lines)
    mem_conn.execute(
        "INSERT INTO note_content (note_id, body, body_plain, body_lines) VALUES ('n1', 'hello\nworld', 'hello world', NULL)"
    )
    row = mem_conn.execute("SELECT body_lines FROM note_content WHERE note_id = 'n1'").fetchone()
    assert row["body_lines"] is None

    # JSON list of [char_start, char_end] pairs
    lines_json = json.dumps([[0, 5], [6, 11]])
    mem_conn.execute("UPDATE note_content SET body_lines = ? WHERE note_id = 'n1'", (lines_json,))
    row = mem_conn.execute("SELECT body_lines FROM note_content WHERE note_id = 'n1'").fetchone()
    parsed = json.loads(row["body_lines"])
    assert parsed == [[0, 5], [6, 11]]


def test_migration_is_idempotent(mem_conn):
    """Running init_schema twice on a fully-migrated DB must not raise."""
    init_schema(mem_conn)  # second call
    row = mem_conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    assert int(row[0] if isinstance(row, tuple) else row["value"]) == 10
