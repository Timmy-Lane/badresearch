"""claim_anchors -- the byte-identity citation-anchor store. dossier 08 §1.2;
schema verbatim from INTERFACES.md (anchor_id = quote_sha 8-char)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
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


CLAIM_ANCHORS_DDL = """
CREATE TABLE IF NOT EXISTS claim_anchors (
    anchor_id      TEXT PRIMARY KEY,   -- == quote_sha (8-char SHA-256 of quoted_support)
    note_id        TEXT NOT NULL,
    char_start     INTEGER NOT NULL,
    char_end       INTEGER NOT NULL,
    claim          TEXT NOT NULL,
    quoted_support TEXT NOT NULL,
    verified       INTEGER NOT NULL DEFAULT 0,
    verify_score   REAL
);
CREATE INDEX IF NOT EXISTS idx_claim_anchors_note ON claim_anchors(note_id);
"""


class AnchorStore:
    """Thin DAL over the claim_anchors table. Markdown/claims-*.json is truth;
    this table is a cache rebuilt by sync (dossier §1.2)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def init_schema(self) -> None:
        self.conn.executescript(CLAIM_ANCHORS_DDL)
        self.conn.commit()

    def upsert(self, anchor: ClaimAnchor) -> None:
        self.conn.execute(
            "INSERT INTO claim_anchors "
            "(anchor_id, note_id, char_start, char_end, claim, quoted_support, verified, verify_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(anchor_id) DO UPDATE SET "
            "  note_id=excluded.note_id, char_start=excluded.char_start, "
            "  char_end=excluded.char_end, claim=excluded.claim, "
            "  quoted_support=excluded.quoted_support",
            (
                anchor.anchor_id, anchor.note_id, anchor.char_start, anchor.char_end,
                anchor.claim, anchor.quoted_support, anchor.verified, anchor.verify_score,
            ),
        )
        self.conn.commit()

    def get(self, anchor_id: str) -> ClaimAnchor | None:
        row = self.conn.execute(
            "SELECT * FROM claim_anchors WHERE anchor_id = ?", (anchor_id,)
        ).fetchone()
        if row is None:
            return None
        return ClaimAnchor(
            note_id=row["note_id"], char_start=row["char_start"], char_end=row["char_end"],
            claim=row["claim"], quoted_support=row["quoted_support"],
            verified=row["verified"], verify_score=row["verify_score"],
            anchor_id=row["anchor_id"],
        )

    def all(self) -> Iterable[ClaimAnchor]:
        for row in self.conn.execute("SELECT * FROM claim_anchors"):
            yield ClaimAnchor(
                note_id=row["note_id"], char_start=row["char_start"], char_end=row["char_end"],
                claim=row["claim"], quoted_support=row["quoted_support"],
                verified=row["verified"], verify_score=row["verify_score"],
                anchor_id=row["anchor_id"],
            )

    def set_verified(self, anchor_id: str, *, verified: int, score: float | None) -> None:
        self.conn.execute(
            "UPDATE claim_anchors SET verified = ?, verify_score = ? WHERE anchor_id = ?",
            (verified, score, anchor_id),
        )
        self.conn.commit()
