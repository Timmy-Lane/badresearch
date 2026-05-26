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
