"""CitationVerifier -- the Stage-11.5 re-grounding pass. Cheapest-first:
Tier A byte-identity ($0) -> Tier B local NLI ($0) -> Tier C triage-LLM judge
(only the NLI-neutral band, batched). Tool-locked [Read]. dossier 08 §2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .anchors import ClaimAnchor, quote_sha


class VerifyVerdict(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


def tier_a_byte_identity(anchor: ClaimAnchor, note_body: str) -> bool:
    """True iff anchor.quoted_support still sits at [char_start:char_end] of the
    live body AND its SHA matches anchor_id. Catches anchor drift + fabricated
    quotes at $0 (dossier §2.2 Tier A)."""
    if quote_sha(anchor.quoted_support) != anchor.anchor_id:
        return False
    sliced = note_body[anchor.char_start:anchor.char_end]
    return sliced == anchor.quoted_support
