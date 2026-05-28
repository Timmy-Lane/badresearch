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


from bad_research.grounding.extract import body_to_lines, char_span_to_line_range


def test_body_to_lines_basic():
    body = "line one\nline two\nline three\n"
    lines = body_to_lines(body)
    # 3 content lines + trailing newline produces 3 (char_start, char_end) pairs
    assert len(lines) == 3
    # first line: chars 0..8  ("line one")
    assert lines[0] == (0, 8)
    # second line: chars 9..17  ("line two")
    assert lines[1] == (9, 17)
    # third line: chars 18..28 ("line three")
    assert lines[2] == (18, 28)


def test_body_to_lines_crlf():
    body = "alpha\r\nbeta\r\n"
    lines = body_to_lines(body)
    assert len(lines) == 2
    # CRLF pair is treated as one line separator; offsets exclude the CR+LF
    assert body[lines[0][0]:lines[0][1]] == "alpha"
    assert body[lines[1][0]:lines[1][1]] == "beta"


def test_body_to_lines_no_trailing_newline():
    body = "first\nsecond"
    lines = body_to_lines(body)
    assert len(lines) == 2
    assert body[lines[0][0]:lines[0][1]] == "first"
    assert body[lines[1][0]:lines[1][1]] == "second"


def test_body_to_lines_empty():
    assert body_to_lines("") == []


def test_char_span_to_line_range_single_line():
    body = "alpha\nbeta\ngamma\n"
    lines = body_to_lines(body)
    # "beta" is entirely on line 2 (1-based)
    start = body.index("beta")
    end = start + len("beta")
    ls, le = char_span_to_line_range(lines, start, end)
    assert ls == 2 and le == 2


def test_char_span_to_line_range_multi_line():
    body = "alpha\nbeta\ngamma\n"
    lines = body_to_lines(body)
    # span from "beta" through "gamma"
    start = body.index("beta")
    end = body.index("gamma") + len("gamma")
    ls, le = char_span_to_line_range(lines, start, end)
    assert ls == 2 and le == 3


def test_char_span_to_line_range_clamps_to_valid():
    body = "only\n"
    lines = body_to_lines(body)
    # span beyond end clamps to last line
    ls, le = char_span_to_line_range(lines, 0, 9999)
    assert ls == 1 and le == len(lines)
