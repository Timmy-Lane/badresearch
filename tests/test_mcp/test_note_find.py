from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_vault(tmp_path: Path, note_id: str, body: str):
    """Return a minimal mock vault wired to an in-memory DB with one note."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS note_content "
        "(note_id TEXT PRIMARY KEY, body TEXT NOT NULL, body_plain TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO note_content (note_id, body, body_plain) VALUES (?, ?, ?)",
        (note_id, body, body),
    )
    conn.commit()

    vault = MagicMock()
    vault.db = conn
    return vault


def test_note_find_returns_matching_lines(tmp_path):
    from bad_research.mcp.server import note_find

    body = (
        "Introduction paragraph here.\n"
        "Vietnam reached 64.3% internet penetration in 2024.\n"
        "This exceeded the regional average by 8 percentage points.\n"
        "Further details in appendix.\n"
    )
    vault = _make_vault(tmp_path, "source-note-19", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("source-note-19", r"64\.3%", context_lines=0)

    result = json.loads(result_json)
    assert result["ok"] is True
    matches = result["matches"]
    assert len(matches) >= 1
    m = matches[0]
    assert m["line_start"] == 2
    assert m["line_end"] == 2
    assert "64.3%" in m["text"]
    assert "char_start" in m
    assert "char_end" in m


def test_note_find_with_context_lines(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Line A.\nLine B with 42%.\nLine C.\nLine D.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"42%", context_lines=1)

    result = json.loads(result_json)
    assert result["ok"] is True
    m = result["matches"][0]
    # context_lines=1 means the returned line range expands ±1
    assert m["line_start"] <= 2
    assert m["line_end"] >= 2


def test_note_find_no_match(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Nothing special here.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"xyzzy_absent_pattern_123")

    result = json.loads(result_json)
    assert result["ok"] is True
    assert result["matches"] == []


def test_note_find_note_not_found(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Some body.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("nonexistent-note", r"anything")

    result = json.loads(result_json)
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_note_find_invalid_regex(tmp_path):
    from bad_research.mcp.server import note_find

    vault = _make_vault(tmp_path, "n1", "body\n")

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"[invalid(regex")

    result = json.loads(result_json)
    assert result["ok"] is False
    assert "regex" in result["error"].lower() or "invalid" in result["error"].lower()
