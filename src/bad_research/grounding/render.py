"""Per-sentence single-index [N] citation render (Perplexity; SPEC §9).
No References section in prose -- sources live off-band (the anchor map)."""

from __future__ import annotations

import re

# [4] numeric indices, and [[note-id]] wiki-links -- both are citation tokens.
_NUMERIC_CITE = re.compile(r"\[(\d+)\]")
_WIKILINK_CITE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def render_citation(sentence: str, anchor_indices: list[int]) -> str:
    """Append ` [N]` per index, in order, after the sentence's terminal text.

    A sentence with no indices is returned unchanged (background/transition
    sentences carry no [N] -- dossier §1.3)."""
    base = sentence.rstrip()
    if not anchor_indices:
        return base
    tail = " ".join(f"[{i}]" for i in anchor_indices)
    return f"{base} {tail}"


def extract_citations(sentence: str) -> list[str]:
    """Return the citation tokens in/adjacent to a sentence: numeric [N] indices
    (as strings) and [[note-id]] wiki-link targets (pipe display stripped)."""
    out: list[str] = []
    for m in re.finditer(r"\[(\d+)\]|\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", sentence):
        out.append(m.group(1) if m.group(1) is not None else m.group(2).strip())
    return out
