"""DSS span extraction (Glean): turn a verbatim quoted_support into char offsets
inside the note body. Deterministic, $0 -- no LLM. dossier 08 §1.1."""

from __future__ import annotations


def extract_spans(
    claim: str,
    quoted_support: str,
    note_body: str,
) -> tuple[int, int] | None:
    """Return (char_start, char_end) of quoted_support inside note_body.

    char_end is exclusive: note_body[char_start:char_end] == quoted_support on
    an exact match. Returns None when the quote cannot be located (caller drops
    the claim -- a quote that isn't in the body is a hallucinated quote).
    """
    quote = quoted_support.strip()
    if not quote:
        return None
    idx = note_body.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))
    return None
