import sqlite3

from bad_research.retrieval.anchors import create_provenance_tables


def test_sources_table_has_interfaces_columns(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    assert cols == {
        "source_id", "url", "domain", "domain_tier", "fetch_provider",
        "tier", "fetched_at", "document_date", "event_date",
    }
    # source_id is the primary key.
    pk = [r[1] for r in conn.execute("PRAGMA table_info(sources)") if r[5]]
    assert pk == ["source_id"]


def test_claim_anchors_table_has_interfaces_columns(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(claim_anchors)")}
    assert cols == {
        "anchor_id", "note_id", "char_start", "char_end", "claim",
        "quoted_support", "verified", "verify_score",
        "line_start", "line_end",
    }
    pk = [r[1] for r in conn.execute("PRAGMA table_info(claim_anchors)") if r[5]]
    assert pk == ["anchor_id"]


def test_create_is_idempotent(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    create_provenance_tables(conn)  # second call must not raise
    assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
