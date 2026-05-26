import sqlite3

from bad_research.retrieval.fts_chunks import (
    create_chunk_fts,
    index_chunk_fts,
    search_chunk_fts,
)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_chunk_fts(c)
    return c


def test_search_returns_matching_chunk_ids():
    conn = _conn()
    index_chunk_fts(conn, [
        {"chunk_id": "c0", "note_id": "n0", "body": "python async await concurrency"},
        {"chunk_id": "c1", "note_id": "n1", "body": "rust ownership borrow checker"},
    ])
    hits = search_chunk_fts(conn, "python async", limit=10)
    ids = [cid for cid, _ in hits]
    assert "c0" in ids
    assert "c1" not in ids


def test_scores_are_positive_and_higher_is_better():
    conn = _conn()
    index_chunk_fts(conn, [
        {"chunk_id": "c0", "note_id": "n0", "body": "python python python async"},
        {"chunk_id": "c1", "note_id": "n1", "body": "python once only here"},
    ])
    hits = dict(search_chunk_fts(conn, "python", limit=10))
    assert all(s >= 0 for s in hits.values())
    # The chunk with more matches scores higher (abs bm25).
    assert hits["c0"] > hits["c1"]


def test_reindex_replaces_chunk_body():
    conn = _conn()
    index_chunk_fts(conn, [{"chunk_id": "c0", "note_id": "n0", "body": "alpha"}])
    index_chunk_fts(conn, [{"chunk_id": "c0", "note_id": "n0", "body": "beta gamma"}])
    assert [cid for cid, _ in search_chunk_fts(conn, "alpha", limit=10)] == []
    assert [cid for cid, _ in search_chunk_fts(conn, "beta", limit=10)] == ["c0"]
