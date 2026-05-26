"""Perplexity×NIA hybrid retrieval engine.

Public surface (re-exported once the submodules land in later tasks):
`Chunk`, `Reranker`, `RetrievalEngine`, `chunk_note`. During the TDD build the
re-exports are added incrementally; importing a not-yet-built name raises the
usual ImportError from its module."""

from __future__ import annotations

__all__ = ["Chunk", "Reranker", "RetrievalEngine", "chunk_note"]
