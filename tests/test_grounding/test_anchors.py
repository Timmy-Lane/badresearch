from __future__ import annotations

import hashlib

from bad_research.grounding.anchors import ClaimAnchor, quote_sha


def test_quote_sha_is_first_8_chars_of_sha256():
    q = "latency dropped to 12.4 ms under load"
    expected = hashlib.sha256(q.encode("utf-8")).hexdigest()[:8]
    assert quote_sha(q) == expected
    assert len(quote_sha(q)) == 8


def test_claim_anchor_anchor_id_defaults_to_quote_sha():
    a = ClaimAnchor(
        note_id="source-note-12",
        char_start=10,
        char_end=47,
        claim="Latency fell to 12.4 ms.",
        quoted_support="latency dropped to 12.4 ms under load",
    )
    assert a.anchor_id == quote_sha(a.quoted_support)
    assert a.verified == 0
    assert a.verify_score is None


import sqlite3

from bad_research.grounding.anchors import AnchorStore


def _store() -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    return store


def test_upsert_then_get_round_trips():
    store = _store()
    a = ClaimAnchor("n1", 10, 47, "Latency fell.", "latency dropped to 12.4 ms under load")
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.note_id == "n1"
    assert got.char_start == 10 and got.char_end == 47
    assert got.quoted_support == a.quoted_support
    assert got.verified == 0


def test_upsert_is_idempotent_on_anchor_id():
    store = _store()
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    store.upsert(a)
    store.upsert(a)  # same quote_sha -> no duplicate row
    rows = store.conn.execute("SELECT COUNT(*) AS c FROM claim_anchors").fetchone()
    assert rows["c"] == 1


def test_set_verified_persists_flag_and_score():
    store = _store()
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    store.upsert(a)
    store.set_verified(a.anchor_id, verified=1, score=0.82)
    got = store.get(a.anchor_id)
    assert got.verified == 1
    assert abs(got.verify_score - 0.82) < 1e-9
