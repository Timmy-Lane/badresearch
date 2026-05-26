"""Rerankers behind the Reranker Protocol (keyless).

Default: ClaudeCodeReranker (host-model LLM-rerank; the body lands in KR-5 — KR-1
ships the typed stub). Local: BGEReranker (ms-marco-MiniLM / bge-reranker) behind
the [local] extra. None: identity (sort by the engine's initial score).

The old API reranker is removed — pure keyless, no third-party key.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bad_research.retrieval.base import Reranker

# A local cross-encoder scorer: maps [(query, doc)] -> [relevance_score].
Scorer = Callable[[list[tuple[str, str]]], list[float]]


class ClaudeCodeReranker:
    """Host-model LLM-reranker (the keyless DEFAULT). KR-5 fills `rerank` with the
    verbatim LLM-rerank prompt (pointwise 0..1, temp=0, ~800-char truncate, JSON
    out, injection preamble). KR-1 ships the typed stub so callers wire cleanly."""

    name = "claude-code"

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        raise NotImplementedError(
            "ClaudeCodeReranker.rerank is the host-model LLM-rerank, built in KR-5"
        )


class IdentityReranker:
    """The `--no-rerank` floor: keep the engine's initial order, descending
    pseudo-scores, stable by index. Keyless, deterministic, $0."""

    name = "identity"

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        n = len(docs)
        return [(i, float(n - i)) for i in range(n)]


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
                 bge_scorer: Scorer | None = None) -> Reranker:
    """Keyless reranker factory keyed on config.reranker:
      "host"  -> ClaudeCodeReranker (host-model LLM-rerank; the default; KR-5 body)
      "local" -> BGEReranker (ms-marco-MiniLM / bge-reranker-v2-m3; [local])
      "none"  -> IdentityReranker (the --no-rerank floor)
    Unknown -> "host". The `client` kwarg is accepted for KR-5 test injection."""
    choice = getattr(config, "reranker", "host")
    if choice == "none":
        return IdentityReranker()
    if choice == "local":
        return BGEReranker(scorer=bge_scorer)
    return ClaudeCodeReranker()
