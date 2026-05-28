import sqlite3

from bad_research.core.db import SCHEMA_VERSION, init_schema


def test_embeddings_table_is_gone_after_init():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "embeddings" not in names
    # Provenance tables are created.
    assert "sources" in names
    assert "claim_anchors" in names


def test_schema_version_is_10():
    assert SCHEMA_VERSION == 10


def test_migration_drops_preexisting_embeddings_table():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Simulate a v8 vault that already has the dead table.
    conn.execute("CREATE TABLE embeddings (note_id TEXT PRIMARY KEY, model TEXT, "
                 "dimensions INTEGER, vector BLOB, created_at TEXT)")
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO _meta VALUES ('schema_version', '8')")
    conn.commit()
    init_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "embeddings" not in names
