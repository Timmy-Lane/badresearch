"""claim_anchors -- the byte-identity citation-anchor store. dossier 08 §1.2;
schema verbatim from INTERFACES.md (anchor_id = quote_sha 8-char)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def quote_sha(quoted_support: str) -> str:
    """8-char SHA-256 of the verbatim quote -- the byte-identity key (frozen)."""
    return hashlib.sha256(quoted_support.encode("utf-8")).hexdigest()[:8]


@dataclass
class ClaimAnchor:
    """One claim->span binding. anchor_id == quote_sha(quoted_support)."""

    note_id: str
    char_start: int
    char_end: int
    claim: str
    quoted_support: str
    verified: int = 0  # 0 = unchecked; 1 = passed the verifier (§2)
    verify_score: float | None = None
    anchor_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.anchor_id:
            self.anchor_id = quote_sha(self.quoted_support)
