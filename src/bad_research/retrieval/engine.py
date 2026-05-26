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


class _ChunkMeta:
    __slots__ = ("chunk", "content_type")

    def __init__(self, chunk: Chunk, content_type: str | None):
        self.chunk = chunk
        self.content_type = content_type


class _LexicalShimEmbedder:
    """Keyless deterministic token-hash embedder for the FTS-only cache lane.

    Matches EmbedProvider (name/dim/embed). Same text -> same vector; shared
    tokens stay close (so repeat queries cache-hit and paraphrases stay near).
    NOT a model, no key, no torch. KR-5 swaps the cache to the real
    LexicalCacheBackend; until then this keeps the negation guard alive."""

    name = "lexical-shim"
    dim = 64

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        import hashlib
        import math

        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in t.lower().split():
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "little")
                v[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


class RetrievalEngine:
    def __init__(self, *, cache_db: Path, reranker: Reranker,
                 embedder: EmbedProvider | None = None,
                 lance_dir: Path | None = None,
                 alpha: float = ALPHA, gate: float = RELEVANCE_GATE,
                 top_k_retrieve: int = TOP_K_RETRIEVE):
        self.embedder = embedder
        self.reranker = reranker
        self.alpha = alpha
        self.gate = gate
        self.top_k_retrieve = top_k_retrieve
        # Vector lane is OPTIONAL: only built when a [local] embedder + lance_dir are given.
        self.store = None
        if embedder is not None and lance_dir is not None:
            from bad_research.retrieval.store import LanceChunkStore

            self.store = LanceChunkStore(Path(lance_dir), dim=embedder.dim)
        # Semantic cache needs an embedder to embed the query. When the keyless
        # FTS-only path has no neural embedder, feed it a deterministic lexical
        # token-hash shim (NOT a model, no key) so the negation-guarded cache keeps
        # working. KR-5 replaces this with the real LexicalCacheBackend (0.85 token
        # overlap). The shim matches the EmbedProvider Protocol exactly.
        cache_embedder = embedder if embedder is not None else _LexicalShimEmbedder()
        self.cache = SemanticCache(Path(cache_db), cache_embedder)
        self.conn = sqlite3.connect(str(Path(cache_db).with_name("chunks_meta.db")))
        self.conn.row_factory = sqlite3.Row
        create_chunk_fts(self.conn)
        self._meta: dict[str, _ChunkMeta] = {}
        self.last_cache_hit: bool = False

    # ── INDEX ────────────────────────────────────────────────────────────
    def index(self, notes: Iterable[Note]) -> None:
        pending: list[Chunk] = []
        ct_for: list[str | None] = []
        embed_texts: list[str] = []
        for note in notes:
            ct = getattr(note.meta, "content_type", None)
            for chunk in chunk_note(note):
                et = embed_text_for(chunk, note) if ct == "code" else chunk.text
                embed_texts.append(et[:EMBED_TRUNC_CHARS])
                pending.append(chunk)
                ct_for.append(ct)
        if not pending:
            return
        fts_rows: list[dict[str, Any]] = []
        vectors: list[list[float]] = []
        model_name: str | None = None
        model_dim: int | None = None
        if self.embedder is not None and self.store is not None:
            model_name = self.embedder.name
            model_dim = self.embedder.dim
            for i in range(0, len(embed_texts), EMBED_BATCH_CAP):
                batch = embed_texts[i:i + EMBED_BATCH_CAP]
                vectors.extend(self.embedder.embed(batch, input_type="document"))
        rows: list[dict[str, Any]] = []
        for idx, (chunk, ct) in enumerate(zip(pending, ct_for, strict=True)):
            if vectors:
                rows.append({"chunk_id": chunk.chunk_id, "vector": vectors[idx],
                             "note_id": chunk.note_id, "char_start": chunk.char_start,
                             "char_end": chunk.char_end, "model": model_name,
                             "dim": model_dim})
            fts_rows.append({"chunk_id": chunk.chunk_id, "body": chunk.text, "note_id": chunk.note_id})
            self._meta[chunk.chunk_id] = _ChunkMeta(chunk, ct)
        if rows and self.store is not None:
            self.store.upsert(rows)
            self.store.maybe_build_index()
        index_chunk_fts(self.conn, fts_rows)

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
        bm_hits = search_chunk_fts(self.conn, query, limit=self.top_k_retrieve)
        bm_scores = dict(bm_hits)
        if self.embedder is not None and self.store is not None:
            qv = self.embedder.embed([query], input_type="query")[0]
            from bad_research.retrieval.store import LanceChunkStore

            vec_hits = self.store.search_vector(qv, top_k=self.top_k_retrieve)
            vec_scores = {cid: LanceChunkStore.distance_to_score(d) for cid, d in vec_hits}
            for cid in extra_ids:
                vec_scores.setdefault(cid, 0.0)
            fused_initial = hybrid_fuse(vec_scores, bm_scores, alpha=self.alpha)
        else:
            # FTS-only: min-max(BM25) is the initial score (dossier 15 §3.1).
            for cid in extra_ids:
                bm_scores.setdefault(cid, 0.0)
            if bm_scores:
                lo = min(bm_scores.values())
                hi = max(bm_scores.values())
                rng = hi - lo
                # Degenerate range (single hit / all-equal): every survivor is the
                # top, so map to initial=1.0 (not 0.0) — they are all the best match.
                if rng <= 0.0:
                    fused_initial = dict.fromkeys(bm_scores, 1.0)
                else:
                    fused_initial = {cid: (s - lo) / rng for cid, s in bm_scores.items()}
            else:
                fused_initial = {}
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
