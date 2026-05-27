from __future__ import annotations

from bad_research.grounding.render import (
    coalesce_citations,
    extract_citations,
    render_citation,
)


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


# ── B-8 citation coalescing (2026-05-27 readability) ─────────────────────────


def test_coalesce_collapses_consecutive_same_source_set():
    # three consecutive sentences all citing {1,2,3} → one group cite at the end
    text = (
        "Latency fell to 12.4 ms. [1] [2] [3] "
        "Throughput doubled. [1] [2] [3] "
        "Error rate held flat. [1] [2] [3]"
    )
    out = coalesce_citations(text)
    # the run renders ONE group cite, not three repeats
    assert out.count("[1] [2] [3]") == 1
    # every sentence's prose survives verbatim (provenance/text preserved)
    assert "Latency fell to 12.4 ms." in out
    assert "Throughput doubled." in out
    assert "Error rate held flat." in out
    # the group cite trails the run (the last sentence of the group keeps it)
    assert out.rstrip().endswith("[1] [2] [3]")


def test_coalesce_leaves_distinct_source_sentence_with_its_own_cite():
    # a sentence with a DISTINCT source must keep its own citation — never merged
    text = (
        "Latency fell to 12.4 ms. [1] [2] "
        "A separate audit disagreed. [9] "
        "Throughput doubled. [1] [2]"
    )
    out = coalesce_citations(text)
    # the distinct [9] sentence is untouched and not absorbed into a {1,2} group
    assert "A separate audit disagreed. [9]" in out
    # the two {1,2} sentences are NOT coalesced across the [9] interruption
    assert out.count("[1] [2]") == 2


def test_coalesce_preserves_citation_to_source_mapping():
    # the SET of source tokens present is identical before and after coalescing
    text = (
        "Sentence one. [1] [2] [3] "
        "Sentence two. [1] [2] [3] "
        "Sentence three. [4]"
    )
    before = set(extract_citations(text))
    after = set(extract_citations(coalesce_citations(text)))
    assert before == after  # no source dropped, none invented


def test_coalesce_uncited_sentences_pass_through_unchanged():
    text = "This is background. Another transition sentence. A final note."
    assert coalesce_citations(text) == text


def test_coalesce_single_sentence_with_cite_unchanged():
    text = "Only one claim here. [5]"
    assert coalesce_citations(text) == text


def test_coalesce_run_then_break_then_new_run():
    # {1} run, break to {2}, then a {1} run again → three separate groups, the
    # later {1} run is its OWN group (we coalesce CONSECUTIVE same-set only)
    text = (
        "A. [1] B. [1] "
        "C. [2] "
        "D. [1] E. [1]"
    )
    out = coalesce_citations(text)
    # first {1} run coalesces, the {2} stands alone, the second {1} run coalesces
    assert out.count("[1]") == 2  # two groups of {1}
    assert out.count("[2]") == 1
    # order/prose preserved
    assert out.index("A.") < out.index("C.") < out.index("D.")


def test_coalesce_order_independent_same_set():
    # {1,2} and {2,1} are the same SOURCE SET → still coalesce
    text = "First. [1] [2] Second. [2] [1]"
    out = coalesce_citations(text)
    # one group cite for the run (set-equality, not sequence-equality)
    assert "First." in out and "Second." in out
    assert extract_citations(out).count("1") == 1
    assert extract_citations(out).count("2") == 1


def test_coalesce_handles_wikilink_sets():
    text = (
        "Alpha. [[note-a]] [[note-b]] "
        "Beta. [[note-a]] [[note-b]]"
    )
    out = coalesce_citations(text)
    assert "Alpha." in out and "Beta." in out
    assert extract_citations(out).count("note-a") == 1
    assert extract_citations(out).count("note-b") == 1
