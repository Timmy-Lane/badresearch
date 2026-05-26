"""Frozen retrieval constants. Every value cites INTERFACES.md / a dossier.

DO NOT re-derive any of these. They are calibration-verified."""
from __future__ import annotations

# ── Hybrid fusion (NIA §5.1-§5.3) ───────────────────────────────────────────
ALPHA = 0.7                               # vector weight; (1-ALPHA) = BM25
TOP_K_RETRIEVE = 30                       # candidates per query before rerank
# three-tier fusion weight keyed on pre-rerank rank (1-based). Default 0.40 for rank>10.
RETRIEVAL_WEIGHT = {3: 0.75, 10: 0.60}
RETRIEVAL_WEIGHT_DEFAULT = 0.40
DEEP_RANK_PENALTY = 0.005                 # subtract 0.005*(rank-10) for rank>10
SOURCE_TYPE_WEIGHT = {
    "code": 1.2, "repository": 1.2,
    "docs": 1.0, "documentation": 1.0, "article": 1.0, "blog": 1.0,
    "paper": 0.9, "research_paper": 0.9,
    "dataset": 0.85, "huggingface_dataset": 0.85,
}
DEFAULT_SOURCE_TYPE_WEIGHT = 1.0

# ── Relevance gate + re-retrieve (Perplexity) ───────────────────────────────
RELEVANCE_GATE = 0.70
RERETRIEVE_PASS_FRACTION = 0.30
RERETRIEVE_MAX_ROUNDS = 2

# ── Semantic cache (NIA §5.5, §4.3) ─────────────────────────────────────────
SEMANTIC_CACHE_THRESHOLD = 0.92
NEGATION_PATTERN = r"\b(not|without|except|unlike|no_std|never|cannot|isn't|aren't|doesn't|don't|won't|n't)\b"

# ── RRF (Exa / LanceDB §8.8) ────────────────────────────────────────────────
RRF_K = 60

# ── FTS5/BM25 lexical lane (hyperresearch fts.py — kept verbatim) ────────────
BM25_TITLE_WEIGHT = 10.0
BM25_BODY_WEIGHT = 1.0
BM25_TAGS_WEIGHT = 5.0
BM25_ALIASES_WEIGHT = 3.0
BM25_STATUS_MULT = {"evergreen": 1.5, "stale": 0.7, "deprecated": 0.3}

# ── Chunker (NIA §3.4-§3.5) ─────────────────────────────────────────────────
CHUNK_BYTE_TARGET = 2400
CHUNK_BYTE_MIN = 2500
CHUNK_OVERLAP = 0
EMBED_TRUNC_CHARS = 16384
EMBED_BATCH_CAP = 96

# ── LanceDB ANN (teardowns/LANCEDB.md) ──────────────────────────────────────
LANCE_INDEX_MIN_ROWS = 256
LANCE_NUM_PARTITIONS_TARGET = 10000
LANCE_HNSW_M = 20
LANCE_HNSW_EF_CONSTRUCTION = 150
LANCE_PQ_NUM_SUB_VECTORS = 16
LANCE_PREFILTER_FLAT_SELECTIVITY = 0.10
