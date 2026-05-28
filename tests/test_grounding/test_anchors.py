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


from bad_research.grounding.anchors import build_from_claims

NOTE_BODIES = {
    "source-note-12": (
        "Southeast Asian e-commerce GMV grew from $89B to $100B between 2023 and 2024, "
        "a 12.4% YoY expansion. Vietnam led the region."
    ),
}


def test_build_from_claims_upserts_located_drops_unlocatable():
    store = _store()
    claims = [
        {
            "claim": "SEA e-commerce GMV grew 12.4% YoY in 2024.",
            "quoted_support": "a 12.4% YoY expansion",
            "source_note_id": "source-note-12",
        },
        {
            "claim": "Revenue tripled to $4.2B.",  # quote not in any body -> dropped
            "quoted_support": "revenue tripled to $4.2B in Q4",
            "source_note_id": "source-note-12",
        },
    ]
    n = build_from_claims(store, claims, NOTE_BODIES)
    assert n == 1  # one located, one dropped
    anchors = list(store.all())
    assert len(anchors) == 1
    a = anchors[0]
    # Round-trip: the stored offsets slice the body back to the quote.
    body = NOTE_BODIES[a.note_id]
    assert body[a.char_start:a.char_end] == a.quoted_support


def test_build_from_claims_fuzzy_located_anchor_round_trips_tier_a():
    # A slightly-reworded quote (curly apostrophe + collapsed whitespace in the
    # body) only matches via the rapidfuzz fallback. The anchor MUST still store
    # offsets whose body slice equals quoted_support, so Tier-A byte-identity
    # would accept it (otherwise the rescued anchor is permanently unverifiable).
    store = _store()
    bodies = {
        "source-note-7": (
            "Researchers wrote: the model’s   accuracy reached 91% on the held-out set "  # noqa: RUF001 -- curly apostrophe is the fixture
            "after the second fine-tuning pass."
        ),
    }
    claims = [
        {
            "claim": "Accuracy hit 91% on the held-out set.",
            # straight apostrophe + single spaces -> NOT a byte-exact substring
            "quoted_support": "the model's accuracy reached 91% on the held-out set",
            "source_note_id": "source-note-7",
        },
    ]
    n = build_from_claims(store, claims, bodies)
    assert n == 1  # rescued by the fuzzy fallback, not dropped
    a = next(iter(store.all()))
    body = bodies[a.note_id]
    # Tier-A invariant: the stored quote IS the actual body slice (not the input).
    assert body[a.char_start:a.char_end] == a.quoted_support
    # anchor_id is the SHA of the stored (body-slice) quote, so quote_sha matches too.
    assert a.anchor_id == quote_sha(a.quoted_support)
    # The rescued quote covers the same evidence as the (normalized) input.
    assert "91%" in a.quoted_support


def _store_fresh() -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    return store


def test_claim_anchor_has_line_start_line_end_nullable():
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
    )
    assert a.line_start is None
    assert a.line_end is None


def test_claim_anchor_line_fields_accepted():
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
        line_start=42, line_end=44,
    )
    assert a.line_start == 42
    assert a.line_end == 44


def test_anchor_store_upsert_get_round_trips_line_fields():
    store = _store_fresh()
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
        line_start=42, line_end=44,
    )
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.line_start == 42
    assert got.line_end == 44


def test_anchor_store_upsert_null_line_fields_round_trips():
    store = _store_fresh()
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="legacy quote no lines",
    )
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.line_start is None
    assert got.line_end is None


def test_claim_anchors_ddl_has_line_columns():
    from bad_research.grounding.anchors import CLAIM_ANCHORS_DDL
    assert "line_start" in CLAIM_ANCHORS_DDL
    assert "line_end" in CLAIM_ANCHORS_DDL
