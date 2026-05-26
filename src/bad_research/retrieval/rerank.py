"""Rerankers behind the Reranker Protocol.

Default: CohereReranker (rerank-v3.5, reranks the FULL candidate set — NIA §5.4).
Offline: BGEReranker (bge-reranker-v2-m3) via FlagEmbedding, with a graceful
sentence-transformers CrossEncoder fallback when FlagEmbedding isn't installed.

[VERIFIED 2026-05-26] against cohere==7.0.0 (the brief said ~v5/v7.x):
  ClientV2.rerank(model=, query=, documents=, top_n=) -> V2RerankResponse with
  `.results[i].index` and `.results[i].relevance_score`. Maps cleanly to
  Reranker.rerank(query, docs) -> [(idx, score)] desc. `rerank-v3.5` is a valid
  model id. No [CORRECTION] needed.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

# A local cross-encoder scorer: maps [(query, doc)] -> [relevance_score].
Scorer = Callable[[list[tuple[str, str]]], list[float]]


class CohereReranker:
    def __init__(self, *, model: str = "rerank-v3.5", api_key: str | None = None,
                 client: Any = None):
        self.model = model
        if client is not None:
            self._client = client
        else:
            import cohere  # lazy
            self._client = cohere.ClientV2(api_key or os.environ["COHERE_API_KEY"])

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        resp = self._client.rerank(model=self.model, query=query, documents=docs, top_n=len(docs))
        return [(r.index, float(r.relevance_score)) for r in resp.results]


def _default_bge_scorer(model: str) -> Scorer:
    """Build a local cross-encoder scorer. Prefer FlagEmbedding.FlagReranker;
    fall back to sentence-transformers CrossEncoder. Import-guarded so the
    module imports cleanly even with neither installed (the scorer is only
    materialized when BGEReranker is constructed WITHOUT an injected scorer)."""
    repo = f"BAAI/{model}" if not model.startswith("BAAI/") else model
    try:
        from FlagEmbedding import FlagReranker  # type: ignore

        fr = FlagReranker(repo, use_fp16=True)
        return lambda pairs: fr.compute_score(pairs, normalize=True)
    except ImportError:
        from sentence_transformers import CrossEncoder  # type: ignore

        ce = CrossEncoder(repo)
        # CrossEncoder.predict returns raw logits; apply sigmoid for [0,1] parity.
        import math

        return lambda pairs: [1.0 / (1.0 + math.exp(-float(s))) for s in ce.predict(pairs)]


class BGEReranker:
    """Local cross-encoder. `scorer(pairs)` maps [(query, doc)] -> [score].
    In production, scorer wraps FlagEmbedding.FlagReranker('BAAI/bge-reranker-v2-m3')
    (or a sentence-transformers CrossEncoder fallback)."""

    def __init__(self, *, model: str = "bge-reranker-v2-m3", scorer: Scorer | None = None):
        self.model = model
        self._scorer = scorer if scorer is not None else _default_bge_scorer(model)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        scores = self._scorer([(query, d) for d in docs])
        scored = list(enumerate(float(s) for s in scores))
        # Sort desc by score; ties broken by ascending index (stable).
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored


def get_reranker(config: Any, *, client: Any = None,
                 bge_scorer: Scorer | None = None) -> CohereReranker | BGEReranker:
    """Cohere when rerank_model is a 'rerank*' id AND a COHERE_API_KEY exists
    (or a client is injected); else the offline BGE reranker."""
    model = getattr(config, "rerank_model", "rerank-v3.5")
    if model.startswith("rerank") and (client is not None or os.environ.get("COHERE_API_KEY")):
        return CohereReranker(model=model, client=client)
    return BGEReranker(model=model, scorer=bge_scorer)
