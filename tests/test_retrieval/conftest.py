"""Deterministic, offline fixtures for retrieval tests."""
from __future__ import annotations

import hashlib
import math

import pytest

from bad_research.retrieval.base import Chunk


class StubEmbedder:
    """Hash-seeded deterministic embedder. dim=8. L2-normalized.

    Same text -> same vector. Two texts that share a token prefix get
    correlated vectors (so paraphrase-vs-different-topic tests behave)."""

    name = "stub"
    dim = 8

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        # Token-bag hashing so paraphrases (shared tokens) stay close,
        # different topics stay far. Negation words are ordinary tokens here —
        # the negation GUARD lives in the cache, not the embedder (matches NIA's
        # documented negation-blindness; §4.3).
        for tok in text.lower().split():
            h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "little")
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts, *, input_type):  # input_type ignored by the stub
        return [self._vec(t) for t in texts]


@pytest.fixture
def stub_embedder():
    return StubEmbedder()


def make_chunk(chunk_id="c", note_id="n", text="hello world",
               char_start=0, char_end=11, score=0.0, source_id="s") -> Chunk:
    return Chunk(chunk_id=chunk_id, note_id=note_id, text=text,
                 char_start=char_start, char_end=char_end, score=score, source_id=source_id)


@pytest.fixture
def chunk_factory():
    return make_chunk


from bad_research.llm.base import LLMResponse  # noqa: E402


class FakeLLMProvider:
    """Records the messages sent to complete() and replays a scripted text reply.
    Implements the bad_research.llm.base.LLMProvider Protocol surface used by
    ClaudeCodeReranker (only .complete and .name are touched)."""

    name = "fake"

    def __init__(self, reply_text: str = "[]"):
        self.reply_text = reply_text
        self.calls: list[dict] = []

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        self.calls.append({
            "messages": messages, "tier": tier, "tools": tools,
            "cache": cache, "max_tokens": max_tokens, "temperature": temperature,
        })
        return LLMResponse(text=self.reply_text, tool_calls=[], usage={}, model="fake")


@pytest.fixture
def fake_llm():
    return FakeLLMProvider


import sqlite3 as _sqlite3  # noqa: E402


@pytest.fixture
def stub_links_db(tmp_path):
    """A minimal `links` table matching core/db.py: (source_id, target_ref,
    target_id, line_number, context). Returns the db path after seeding edges."""
    def _make(edges: list[tuple[str, str]]) -> object:
        path = tmp_path / "links.db"
        conn = _sqlite3.connect(str(path))
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS links ("
            "  source_id TEXT NOT NULL, target_ref TEXT NOT NULL, target_id TEXT,"
            "  line_number INTEGER NOT NULL DEFAULT 0, context TEXT,"
            "  PRIMARY KEY (source_id, target_ref, line_number));"
        )
        for src, tgt in edges:
            conn.execute(
                "INSERT OR IGNORE INTO links (source_id, target_ref, target_id, line_number) "
                "VALUES (?, ?, ?, 0)", (src, tgt, tgt))
        conn.commit()
        conn.close()
        return path
    return _make
