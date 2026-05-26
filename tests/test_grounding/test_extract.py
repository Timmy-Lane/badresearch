from __future__ import annotations

from bad_research.grounding.extract import extract_spans

NOTE_BODY = (
    "# Source note\n\n"
    "The study found that latency dropped to 12.4 ms under load. "
    "A separate trial reported no regression.\n"
)


def test_exact_find_returns_span_that_round_trips():
    quote = "latency dropped to 12.4 ms under load"
    span = extract_spans("Latency fell to 12.4 ms.", quote, NOTE_BODY)
    assert span is not None
    start, end = span
    # The load-bearing invariant: slicing the body by the offsets reproduces the quote.
    assert NOTE_BODY[start:end] == quote
    assert end - start == len(quote)


def test_fuzzy_fallback_locates_lightly_normalized_quote():
    # Body has a curly apostrophe / collapsed whitespace the extractor quoted plainly.
    body = "Researchers wrote: the model’s   accuracy reached 91% on the held-out set."
    quote = "the model's accuracy reached 91% on the held-out set"  # straight apostrophe, single spaces
    span = extract_spans("Accuracy hit 91%.", quote, body)
    assert span is not None
    start, end = span
    # Matched span is a real substring of the body covering the same evidence.
    assert "91%" in body[start:end]
    assert start >= 0 and end <= len(body)


def test_fabricated_quote_returns_none():
    body = "The report covered three regions and two time periods."
    quote = "revenue tripled to $4.2B in the fourth quarter"  # never appears
    assert extract_spans("Revenue tripled.", quote, body) is None
