"""Negation-guarded semantic query cache (dossier 04 §4.1-§4.3).

0.92-cosine over cached query embeddings; a HIT is suppressed when the new
query adds a negation marker the cached query lacked (NIA's documented defect —
the embedder is negation-blind, so an affirmative query and its negation embed
nearly identically; without this guard the cache would serve the wrong answer)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from bad_research.embed.base import EmbedProvider
from bad_research.retrieval.constants import NEGATION_PATTERN, SEMANTIC_CACHE_THRESHOLD

_NEG_RE = re.compile(NEGATION_PATTERN, re.IGNORECASE)

_DDL = """
CREATE TABLE IF NOT EXISTS query_cache (
    query_text   TEXT PRIMARY KEY,
    embedding    TEXT NOT NULL,   -- json list[float]
    has_negation INTEGER NOT NULL,
    payload      TEXT NOT NULL,   -- json
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def has_negation(query: str) -> bool:
    return bool(_NEG_RE.search(query))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


class SemanticCache:
    def __init__(self, db_path: Path, embedder: EmbedProvider,
                 *, threshold: float = SEMANTIC_CACHE_THRESHOLD):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.threshold = threshold
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def get(self, query: str) -> dict[str, Any] | None:
        qv = self.embedder.embed([query], input_type="query")[0]
        q_neg = has_negation(query)
        best = None
        best_sim = -1.0
        for row in self.conn.execute(
            "SELECT query_text, embedding, has_negation, payload FROM query_cache"
        ):
            cv = json.loads(row["embedding"])
            if len(cv) != len(qv):
                continue
            sim = _cosine(qv, cv)
            if sim > best_sim:
                best_sim, best = sim, row
        if best is None or best_sim < self.threshold:
            return None
        # Negation guard: a HIT requires the new query and the cached query to
        # AGREE on negation. If they disagree (one negates, the other doesn't),
        # force a miss (NIA §4.3) — negation-blind embeddings make them look
        # near-identical, but they are semantically opposite.
        if q_neg != bool(best["has_negation"]):
            return None
        return {"payload": json.loads(best["payload"]),
                "cache_similarity": best_sim,
                "original_query": best["query_text"]}

    def put(self, query: str, payload: dict[str, Any]) -> None:
        qv = self.embedder.embed([query], input_type="query")[0]
        self.conn.execute(
            "INSERT OR REPLACE INTO query_cache (query_text, embedding, has_negation, payload) "
            "VALUES (?, ?, ?, ?)",
            (query, json.dumps(qv), int(has_negation(query)), json.dumps(payload)),
        )
        self.conn.commit()
