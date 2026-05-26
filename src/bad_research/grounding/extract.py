"""DSS span extraction (Glean): turn a verbatim quoted_support into char offsets
inside the note body. Deterministic, $0 -- no LLM. dossier 08 §1.1."""

from __future__ import annotations

# rapidfuzz is the fuzzy-locate fallback for lightly-normalized quotes.
from rapidfuzz import fuzz

FUZZY_RATIO_FLOOR = 95.0  # dossier §1.1: partial-ratio >= 95 to accept a fuzzy locate


def extract_spans(
    claim: str,
    quoted_support: str,
    note_body: str,
) -> tuple[int, int] | None:
    """Return (char_start, char_end) of quoted_support inside note_body.

    1. Exact find (char_end exclusive; body[start:end] == quote).
    2. Fuzzy fallback: slide a window of len(quote) (+/- 20%) over the body,
       accept the best window with rapidfuzz partial-ratio >= 95.
    3. None when neither locates it -- the caller drops the claim (a quote that
       isn't in the body is a hallucinated quote; dossier §1.1).
    """
    quote = quoted_support.strip()
    if not quote:
        return None

    idx = note_body.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))

    return _fuzzy_locate(quote, note_body)


def _fuzzy_locate(quote: str, body: str) -> tuple[int, int] | None:
    qlen = len(quote)
    if qlen == 0 or qlen > len(body):
        # Quote longer than the whole body: try whole-body ratio once.
        if qlen > len(body) and fuzz.partial_ratio(quote, body) >= FUZZY_RATIO_FLOOR:
            return (0, len(body))
        return None

    best_score = 0.0
    best_span: tuple[int, int] | None = None
    # Window between 80% and 120% of the quote length, stepped to keep it cheap.
    win_min = max(1, int(qlen * 0.8))
    win_max = min(len(body), int(qlen * 1.2) + 1)
    step = max(1, qlen // 8)
    for start in range(0, len(body) - win_min + 1, step):
        for win in (qlen, win_min, win_max):
            end = min(start + win, len(body))
            score = fuzz.partial_ratio(quote, body[start:end])
            if score > best_score:
                best_score = score
                best_span = (start, end)
        if best_score >= 100.0:
            break

    if best_span is not None and best_score >= FUZZY_RATIO_FLOOR:
        return best_span
    return None
