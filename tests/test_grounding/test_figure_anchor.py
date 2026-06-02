"""Vision-grounding rung: a figure-derived claim is stored with its host
transcription as quoted_support + an asset-path anchor, so the existing gates
(Tier-A byte-identity, uncited gate, recitation gate, verify-citations) still
apply to figure-derived numbers. NOT an ungrounded escape hatch."""

from __future__ import annotations

import sqlite3

from bad_research.grounding.anchors import (
    AnchorStore,
    ClaimAnchor,
    build_figure_anchor,
    quote_sha,
)
from bad_research.grounding.verifier import _support_premise, tier_a_byte_identity


def _store() -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    return store


def test_claim_anchor_asset_path_defaults_none() -> None:
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    assert a.asset_path is None


def test_anchor_store_round_trips_asset_path() -> None:
    store = _store()
    a = ClaimAnchor(
        "fig-note", 0, 5, "C.", "abcde",
        asset_path="research/assets/fig-note/page-000-ab.png",
    )
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.asset_path == "research/assets/fig-note/page-000-ab.png"


def test_claim_anchors_ddl_has_asset_path() -> None:
    from bad_research.grounding.anchors import CLAIM_ANCHORS_DDL
    assert "asset_path" in CLAIM_ANCHORS_DDL


def test_init_schema_alters_legacy_table_to_add_asset_path() -> None:
    # Simulate a pre-vision-rung claim_anchors table (no asset_path column).
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE claim_anchors ("
        " anchor_id TEXT PRIMARY KEY, note_id TEXT NOT NULL, char_start INTEGER NOT NULL,"
        " char_end INTEGER NOT NULL, claim TEXT NOT NULL, quoted_support TEXT NOT NULL,"
        " verified INTEGER NOT NULL DEFAULT 0, verify_score REAL,"
        " line_start INTEGER, line_end INTEGER);"
    )
    store = AnchorStore(conn)
    store.init_schema()  # must ALTER in the new column without error
    cols = {r[1] for r in conn.execute("PRAGMA table_info(claim_anchors)")}
    assert "asset_path" in cols
    # and a round-trip works post-migration
    store.upsert(ClaimAnchor("n", 0, 3, "c", "abc", asset_path="p.png"))
    assert store.get(quote_sha("abc")).asset_path == "p.png"


# The host transcribed a figure VERBATIM into the note body. This is the note as it
# reads after the figure-reading skill ran: the transcription is real body text.
FIGURE_NOTE_BODY = (
    "## Figure 3 (transcribed from the chart)\n"
    "Model accuracy by size: 7B = 61.2%, 13B = 68.9%, 70B = 74.5% on MMLU.\n"
)
TRANSCRIPTION = "7B = 61.2%, 13B = 68.9%, 70B = 74.5% on MMLU"
ASSET = "research/assets/fig-note/page-002-deadbeef.png"


def test_build_figure_anchor_grounds_transcription_and_records_asset() -> None:
    store = _store()
    anchor = build_figure_anchor(
        store,
        note_id="fig-note",
        claim="The 70B model reaches 74.5% on MMLU.",
        transcription=TRANSCRIPTION,
        note_body=FIGURE_NOTE_BODY,
        asset_path=ASSET,
    )
    assert anchor is not None
    # The transcription IS stored as quoted_support and locates in the body.
    assert FIGURE_NOTE_BODY[anchor.char_start:anchor.char_end] == anchor.quoted_support
    assert "74.5%" in anchor.quoted_support
    assert anchor.asset_path == ASSET
    # Tier-A byte-identity still holds — a figure number is gated like a text quote.
    assert tier_a_byte_identity(anchor, FIGURE_NOTE_BODY) is True


def test_build_figure_anchor_drops_transcription_not_in_body() -> None:
    # A hallucinated transcription (not in the note body) is DROPPED — no escape hatch.
    store = _store()
    anchor = build_figure_anchor(
        store,
        note_id="fig-note",
        claim="Accuracy is 99%.",
        transcription="99% accuracy on every benchmark",  # not in the body
        note_body=FIGURE_NOTE_BODY,
        asset_path=ASSET,
    )
    assert anchor is None
    assert list(store.all()) == []


def test_support_premise_reshows_asset_to_judge() -> None:
    # The Tier-C judge premise for a figure anchor must point at the saved PNG so
    # the host re-reads the image on the neutral band.
    a = ClaimAnchor(
        "fig-note", 0, len(TRANSCRIPTION), "C.", TRANSCRIPTION, asset_path=ASSET,
    )
    premise = _support_premise(a, FIGURE_NOTE_BODY)
    assert TRANSCRIPTION in premise
    assert ASSET in premise
    assert "re-read this image" in premise


def test_support_premise_plain_for_text_anchor() -> None:
    # A non-figure anchor's premise is unchanged (no asset annotation).
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    assert _support_premise(a, "abcde body") == "abcde"
