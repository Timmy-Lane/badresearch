"""Frozen retrieval contracts (INTERFACES.md §retrieval/base.py)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from bad_research.models.note import Note


@dataclass
class Chunk:
    chunk_id: str            # sha1(url + "#" + heading)
    note_id: str
    text: str
    char_start: int
    char_end: int
    score: float
    source_id: str


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        """Return [(doc_index, score)] sorted by score descending."""
        ...


class RetrievalEngine:
    """Concrete hybrid engine. Implemented incrementally; see engine.py.

    index(notes)            — chunk + embed + write LanceDB + FTS5.
    search(query, mode, top_k) — hybrid(alpha=0.7) → rerank → three-tier
                                 fusion → 0.70 gate → re-retrieve → cache.
    """

    def index(self, notes: Iterable[Note]) -> None:  # pragma: no cover - replaced in Task 14
        raise NotImplementedError

    def search(self, query: str, *, mode: Literal["light", "full"], top_k: int) -> list[Chunk]:  # pragma: no cover
        raise NotImplementedError
