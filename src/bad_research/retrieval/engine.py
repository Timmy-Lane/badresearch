"""Concrete RetrievalEngine: chunk→embed→LanceDB+FTS index; hybrid→rerank→
three-tier fusion→0.70 gate→<30%-pass re-retrieve→negation-guarded cache."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from bad_research.embed.base import EmbedProvider
from bad_research.models.note import Note
from bad_research.retrieval.base import Chunk, Reranker
from bad_research.retrieval.cache import SemanticCache
from bad_research.retrieval.chunker import chunk_note
from bad_research.retrieval.chunker_code import embed_text_for
from bad_research.retrieval.constants import (
    ALPHA,
    EMBED_BATCH_CAP,
    EMBED_TRUNC_CHARS,
    RELEVANCE_GATE,
    RERETRIEVE_MAX_ROUNDS,
    RERETRIEVE_PASS_FRACTION,
    TOP_K_RETRIEVE,
)
from bad_research.retrieval.fts_chunks import (
    create_chunk_fts,
    index_chunk_fts,
    search_chunk_fts,
)
from bad_research.retrieval.fusion import (
    apply_source_type_weight,
    hybrid_fuse,
    three_tier_fuse,
)
from bad_research.retrieval.store import LanceChunkStore


class _ChunkMeta:
    __slots__ = ("chunk", "content_type")

    def __init__(self, chunk: Chunk, content_type: str | None):
        self.chunk = chunk
        self.content_type = content_type


class RetrievalEngine:
    def __init__(self, *, lance_dir: Path, cache_db: Path, embedder: EmbedProvider,
                 reranker: Reranker, alpha: float = ALPHA, gate: float = RELEVANCE_GATE,
                 top_k_retrieve: int = TOP_K_RETRIEVE):
        self.store = LanceChunkStore(Path(lance_dir), dim=embedder.dim)
        self.embedder = embedder
        self.reranker = reranker
        self.alpha = alpha
        self.gate = gate
        self.top_k_retrieve = top_k_retrieve
        self.cache = SemanticCache(Path(cache_db), embedder)
        # Chunk metadata DB (FTS lane + chunk_id→meta map), per-vault.
        self.conn = sqlite3.connect(str(Path(cache_db).with_name("chunks_meta.db")))
        self.conn.row_factory = sqlite3.Row
        create_chunk_fts(self.conn)
        self._meta: dict[str, _ChunkMeta] = {}
        self.last_cache_hit: bool = False

    # ── INDEX ────────────────────────────────────────────────────────────
    def index(self, notes: Iterable[Note]) -> None:
        embed_texts: list[str] = []
        pending: list[Chunk] = []
        ct_for: list[str | None] = []
        for note in notes:
            ct = getattr(note.meta, "content_type", None)
            for chunk in chunk_note(note):
                et = embed_text_for(chunk, note) if ct == "code" else chunk.text
                embed_texts.append(et[:EMBED_TRUNC_CHARS])
                pending.append(chunk)
                ct_for.append(ct)
        if not pending:
            return
        # Batch-embed at the provider cap.
        vectors: list[list[float]] = []
        for i in range(0, len(embed_texts), EMBED_BATCH_CAP):
            batch = embed_texts[i:i + EMBED_BATCH_CAP]
            vectors.extend(self.embedder.embed(batch, input_type="document"))
        rows: list[dict[str, Any]] = []
        fts_rows: list[dict[str, Any]] = []
        for chunk, vec, ct in zip(pending, vectors, ct_for, strict=True):
            rows.append({"chunk_id": chunk.chunk_id, "vector": vec, "note_id": chunk.note_id,
                         "char_start": chunk.char_start, "char_end": chunk.char_end,
                         "model": self.embedder.name, "dim": self.embedder.dim})
            fts_rows.append({"chunk_id": chunk.chunk_id, "body": chunk.text, "note_id": chunk.note_id})
            self._meta[chunk.chunk_id] = _ChunkMeta(chunk, ct)
        self.store.upsert(rows)
        index_chunk_fts(self.conn, fts_rows)
        self.store.maybe_build_index()

    # ── SEARCH ───────────────────────────────────────────────────────────
    def search(self, query: str, *, mode: Literal["light", "full"], top_k: int) -> list[Chunk]:
        cached = self.cache.get(query)
        if cached is not None:
            self.last_cache_hit = True
            return [self._meta[cid].chunk for cid in cached["payload"]["chunk_ids"]
                    if cid in self._meta][:top_k]
        self.last_cache_hit = False

        survivors: list[Chunk] = []
        extra_ids: set[str] = set()
        for round_idx in range(1 + RERETRIEVE_MAX_ROUNDS):
            survivors, pass_fraction, top_note = self._one_round(query, extra_ids)
            if pass_fraction >= RERETRIEVE_PASS_FRACTION or round_idx == RERETRIEVE_MAX_ROUNDS:
                break
            # expand_symbols-style widening: pull same-note neighbor chunks.
            if top_note is not None:
                extra_ids |= {cid for cid, m in self._meta.items() if m.chunk.note_id == top_note}

        survivors.sort(key=lambda c: c.score, reverse=True)
        result = survivors[:top_k]
        self.cache.put(query, {"chunk_ids": [c.chunk_id for c in result]})
        return result

    def _one_round(self, query: str,
                   extra_ids: set[str]) -> tuple[list[Chunk], float, str | None]:
        qv = self.embedder.embed([query], input_type="query")[0]
        vec_hits = self.store.search_vector(qv, top_k=self.top_k_retrieve)
        vec_scores = {cid: LanceChunkStore.distance_to_score(d) for cid, d in vec_hits}
        bm_hits = search_chunk_fts(self.conn, query, limit=self.top_k_retrieve)
        bm_scores = dict(bm_hits)
        # widening: ensure neighbor chunks are scored even if ANN missed them.
        for cid in extra_ids:
            vec_scores.setdefault(cid, 0.0)

        fused_initial = hybrid_fuse(vec_scores, bm_scores, alpha=self.alpha)
        if not fused_initial:
            return [], 0.0, None
        # pre-rerank rank (1-based) by initial score desc.
        ranked = sorted(fused_initial.items(), key=lambda kv: kv[1], reverse=True)
        cand_ids = [cid for cid, _ in ranked if cid in self._meta]
        docs = [self._meta[cid].chunk.text for cid in cand_ids]
        rer = dict(self.reranker.rerank(query, docs))  # idx → reranker_score

        survivors: list[Chunk] = []
        for rank0, cid in enumerate(cand_ids):
            rank = rank0 + 1
            initial = fused_initial[cid]
            reranker_score = rer.get(rank0, 0.0)
            fused = three_tier_fuse(initial, reranker_score, rank)
            fused = apply_source_type_weight(fused, self._meta[cid].content_type)
            if fused >= self.gate:
                c = self._meta[cid].chunk
                survivors.append(Chunk(chunk_id=c.chunk_id, note_id=c.note_id, text=c.text,
                                       char_start=c.char_start, char_end=c.char_end,
                                       score=fused, source_id=c.source_id))
        pass_fraction = (len(survivors) / len(cand_ids)) if cand_ids else 0.0
        top_note = self._meta[cand_ids[0]].chunk.note_id if cand_ids else None
        return survivors, pass_fraction, top_note
