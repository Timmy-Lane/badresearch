"""Rerankers behind the Reranker Protocol — KEYLESS.

Default: ClaudeCodeReranker — the host model (no API key) scores each candidate
0..1 with the SINGLE frozen LLM-rerank prompt (dossier 15 §5.3 / 13 §4.1). There
is exactly ONE rerank prompt in the codebase: KR-2 froze it as
``web/search/rerank.py::LLM_RERANK_PROMPT_SYSTEM`` (with the injection preamble
baked in) and froze a hardened ``_parse_scores`` that degrades malformed host
output to original order. This module REUSES both verbatim (imported, not
re-authored) so the search reranker (HostModelReranker) and the vault reranker
(ClaudeCodeReranker) speak the identical contract — search vs. vault candidates,
same prompt, same parser.

One batched call, pointwise JSON output, temperature=0, ~800-char truncation,
graceful 0.0 on any parse/call failure (the three-tier blend then leans on the
`initial` score so no candidate is silently dropped).

Offline ([local] extra): BGEReranker — local cross-encoder (ms-marco-MiniLM by
default for the keyless ``reranker="local"`` flag, dossier 15 §5.2). torch is
imported lazily, only when a scorer is constructed.

Floor: the identity reranker (``reranker="none"``) — input order preserved (the
--no-rerank speed/zero-token fallback, §5.1).

NO Cohere. NO mandatory local model.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from bad_research.llm.base import LLMMessage
from bad_research.retrieval.base import Reranker

# ── The ONE frozen rerank prompt + parser (single source of truth) ───────────
# KR-2 created and froze these in web/search/rerank.py (dossier 13 §4.1, shared
# with dossier 15 §5.3). We import — never duplicate — so a future edit to the
# rubric/parser changes BOTH call sites at once.
from bad_research.web.search.rerank import (
    LLM_RERANK_PROMPT_SYSTEM as LLM_RERANK_SYSTEM,
)
from bad_research.web.search.rerank import (
    LLM_RERANK_TRUNC_CHARS,
    _parse_scores,
    _truncate,
)

__all__ = [
    "LLM_RERANK_SYSTEM",
    "BGEReranker",
    "ClaudeCodeReranker",
    "IdentityReranker",
    "Scorer",
    "get_reranker",
]

# A local cross-encoder scorer: maps [(query, doc)] -> [relevance_score].
Scorer = Callable[[list[tuple[str, str]]], list[float]]


def _build_user_message(query: str, docs: list[str]) -> str:
    """Assemble the user message: the query + 0-based numbered, truncated chunks.
    0-based numbering matches the shared KR-2 prompt + parser exactly."""
    passages = "\n".join(
        f"[{i}] {_truncate(d, LLM_RERANK_TRUNC_CHARS)}" for i, d in enumerate(docs)
    )
    return f"QUERY: {query}\nPASSAGES:\n{passages}"


class ClaudeCodeReranker:
    """The DEFAULT keyless reranker — the host model scores candidates 0..1 with
    the ONE frozen prompt + parser (shared with web/search HostModelReranker).

    ``llm`` is any LLMProvider (bad_research.llm.base). The skill path supplies
    the host model; the headless/calibration path supplies AnthropicProvider. No
    key is read here — the provider owns that. The frozen prompt already carries
    the injection preamble, so no extra preamble plumbing is needed."""

    name = "claude-code"

    def __init__(self, *, llm: Any = None, tier: str = "work"):
        # llm may be None at construction: the host provider is resolved LAZILY on
        # the first rerank() call (the skill path supplies the host model only when
        # an actual rerank happens — no key is read at build time, keyless-correct).
        self._llm = llm
        self._tier = tier

    def _provider(self) -> Any:
        """Resolve the host LLM provider lazily (cached). Only touched when a real
        rerank is performed — never at construction, so the keyless build path
        (get_reranker → _build_reranker) never reads ANTHROPIC_API_KEY."""
        if self._llm is None:
            from bad_research.llm.base import get_llm_provider

            self._llm = get_llm_provider("anthropic")
        return self._llm

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        messages = [
            LLMMessage(role="system", content=LLM_RERANK_SYSTEM),
            LLMMessage(role="user", content=_build_user_message(query, docs)),
        ]
        try:
            resp = self._provider().complete(messages, tier=self._tier, temperature=0,
                                             max_tokens=2048)
            # The shared KR-2 parser returns a list[float] (0-based, all-0.0 on a
            # fully-unparseable reply, per-item 0.0 on a missing/malformed item).
            scores = _parse_scores(resp.text, n=len(docs))
        except Exception:  # a failed host call must not crash retrieval (§5.3)
            scores = [0.0] * len(docs)
        # Clamp to [0,1] (defensive; the parser already keeps the model's raw float).
        scored = [(i, max(0.0, min(1.0, float(s)))) for i, s in enumerate(scores)]
        scored.sort(key=lambda x: (-x[1], x[0]))  # desc by score, stable by index
        return scored


class IdentityReranker:
    """The --no-rerank floor (dossier 15 §5.1): input order preserved, descending
    pseudo-scores, stable by index. Keyless, deterministic, $0."""

    name = "identity"

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        n = len(docs)
        return [(i, float(n - i)) for i in range(n)]


def _default_bge_scorer(model: str) -> Scorer:
    """Build a local cross-encoder scorer ([local] extra). Lazy import so the
    module imports cleanly with no torch installed. Prefer FlagEmbedding; fall
    back to sentence-transformers CrossEncoder (sigmoid-normalized to [0,1])."""
    repo = model if model.startswith(("BAAI/", "cross-encoder/")) else f"cross-encoder/{model}"
    try:
        from FlagEmbedding import FlagReranker  # type: ignore

        fr = FlagReranker(repo, use_fp16=True)
        return lambda pairs: fr.compute_score(pairs, normalize=True)
    except ImportError:
        from sentence_transformers import CrossEncoder  # type: ignore

        ce = CrossEncoder(repo)
        return lambda pairs: [1.0 / (1.0 + math.exp(-float(s))) for s in ce.predict(pairs)]


class BGEReranker:
    """Local cross-encoder ([local]). Default model is the LIGHT ms-marco MiniLM
    (dossier 15 §5.2 — not the 560 MB m3) for the keyless ``reranker="local"``."""

    def __init__(self, *, model: str = "ms-marco-MiniLM-L-6-v2",
                 scorer: Scorer | None = None):
        self.model = model
        self._scorer = scorer if scorer is not None else _default_bge_scorer(model)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        scores = self._scorer([(query, d) for d in docs])
        scored = list(enumerate(float(s) for s in scores))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored


def get_reranker(config: Any, *, llm: Any = None,
                 bge_scorer: Scorer | None = None) -> Reranker:
    """Keyless reranker factory (INTERFACES_KEYLESS §5.3):
      "host"  → ClaudeCodeReranker (default; host model, no key)
      "local" → BGEReranker(ms-marco-MiniLM-L-6-v2) ([local] extra)
      "none"  → IdentityReranker (the --no-rerank floor)
    ``config.reranker`` selects; falls back to "host". The ``llm`` kwarg injects a
    host provider for tests/headless; if absent on the "host" path the provider is
    resolved LAZILY on first rerank() (no key is read at factory time for any
    branch — the keyless build path never touches ANTHROPIC_API_KEY)."""
    choice = getattr(config, "reranker", "host")
    if choice == "none":
        return IdentityReranker()
    if choice == "local":
        return BGEReranker(scorer=bge_scorer)
    # "host" (default): ClaudeCodeReranker resolves the host LLM lazily (llm may be None).
    return ClaudeCodeReranker(llm=llm)
