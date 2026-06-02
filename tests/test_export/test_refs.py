"""Tests for export.refs — citation marker collection + reference resolution."""

from __future__ import annotations

from bad_research.export.refs import (
    SourceRef,
    collect_markers,
    render_references_markdown,
    resolve_references,
    source_refs_from_notes,
)

_SOURCES_JSON = {
    "solar-note": '---\ntitle: "IEA Renewables 2023"\nsource: "https://iea.org/r"\n---\n\nbody',
    "wind-note": '---\ntitle: "GWEC Wind Report"\nsource: "https://gwec.net/w"\n---\n\nbody',
}

_REPORT = (
    "# Energy\n\n"
    "Solar grew fast [[solar-note]].\n"
    "Wind grew slower [[wind-note]].\n"
    "Projections continue [1].\n"
    "\n## Sources\n\n- some pre-existing junk [[solar-note]]\n"
)


def test_source_refs_from_notes_parses_title_and_url():
    refs = source_refs_from_notes(_SOURCES_JSON)
    assert refs["solar-note"] == SourceRef("solar-note", "IEA Renewables 2023", "https://iea.org/r")
    assert refs["wind-note"].url == "https://gwec.net/w"


def test_source_ref_label_falls_back_to_title_only_when_no_url():
    r = SourceRef("x", "Title Only", None)
    assert r.label() == "Title Only"
    r2 = SourceRef("x", "Title", "https://u")
    assert "https://u" in r2.label()


def test_collect_markers_reading_order_dedup_and_excludes_existing_sources():
    # Markers below the `## Sources` heading are NOT collected (we emit our own).
    markers = collect_markers(_REPORT)
    assert markers == ["solar-note", "wind-note", "1"]


def test_collect_markers_strips_line_anchor_suffix():
    md = "Claim [[note-a:L10-L20]]. Another [[note-a:L30-L40]]."
    # Same note id, distinct line ranges -> one distinct source key.
    assert collect_markers(md) == ["note-a"]


def test_resolve_references_numeric_is_positional():
    refs = source_refs_from_notes(_SOURCES_JSON)
    md = "First [1]. Second [2]. Third [3]."
    resolved = resolve_references(md, refs)
    assert resolved[0].ref.note_id == "solar-note"   # [1] -> first key
    assert resolved[1].ref.note_id == "wind-note"    # [2] -> second key
    assert resolved[2].ref is None                   # [3] -> out of range (dangling)


def test_resolve_references_wikilink_direct_and_dangling():
    refs = source_refs_from_notes(_SOURCES_JSON)
    md = "Known [[solar-note]]. Unknown [[ghost-note]]."
    resolved = resolve_references(md, refs)
    assert resolved[0].ref.title == "IEA Renewables 2023"
    assert resolved[1].ref is None  # dangling, honestly flagged


def test_render_references_markdown_flags_dangling():
    refs = source_refs_from_notes(_SOURCES_JSON)
    md = "A [[solar-note]]. B [[ghost]]."
    out = render_references_markdown(resolve_references(md, refs))
    assert "## References" in out
    assert "1. IEA Renewables 2023" in out
    assert "[unresolved citation: `ghost`]" in out


def test_render_references_markdown_empty_when_no_markers():
    assert render_references_markdown([]) == ""
