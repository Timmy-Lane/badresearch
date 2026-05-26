from __future__ import annotations

from bad_research.grounding.render import extract_citations, render_citation


def test_render_appends_single_index_per_sentence():
    out = render_citation("Latency fell to 12.4 ms.", [3])
    assert out == "Latency fell to 12.4 ms. [3]"


def test_render_multiple_indices_collapse_in_order():
    out = render_citation("Two trials agreed on the 91% figure.", [2, 7])
    assert out == "Two trials agreed on the 91% figure. [2] [7]"


def test_render_no_indices_returns_sentence_unchanged():
    assert render_citation("This report covers three regions.", []) == "This report covers three regions."


def test_extract_citations_finds_bracket_and_wikilink_tokens():
    sent = "Growth was 12.4% [4] per the regional digest [[source-note-12]]."
    assert extract_citations(sent) == ["4", "source-note-12"]
