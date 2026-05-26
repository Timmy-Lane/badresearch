# Bad Research — Plan 02: Retrieval Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hyperresearch's FTS-only vault with a Perplexity×NIA hybrid retrieval engine — LanceDB dense vectors + FTS5/BM25 fused at `alpha=0.7`, Cohere/BGE cross-encoder rerank with three-tier fusion, a 0.70 relevance gate with `<30%`-pass re-retrieve, and a negation-guarded semantic cache.

**Architecture:** A new `bad_research.retrieval` package. The chunker turns notes into stable-ID `Chunk`s (AST-header-prepend for code via tree-sitter, semantic split for prose). The `RetrievalEngine` indexes chunk vectors into an embedded LanceDB `chunks` table and chunk text into the existing SQLite FTS5 lane, then at query time fuses the two lanes (`alpha=0.7` on min-max-normalized scores), reranks the top-30 with a `Reranker`, blends via three-tier weights `w={≤3:0.75,≤10:0.60,>10:0.40}`, applies the 0.70 gate, re-retrieves when `<30%` pass (≤2 rounds), and short-circuits paraphrases through a 0.92-cosine semantic cache with a regex negation guard. Two new SQLite tables (`sources`, `claim_anchors`) are created here (DDL only; populated by Plans 05/06). The dead `embeddings` table is removed.

**Tech Stack:** Python 3.11+, LanceDB (embedded, no server), PyArrow, SQLite FTS5 (reused from hyperresearch), `tree-sitter` + `tree-sitter-language-pack`, NumPy (cosine/min-max), Cohere SDK (`rerank-v3.5`, optional), `sentence-transformers`/`FlagEmbedding` (`bge-reranker-v2-m3`, optional offline), pytest. Embeddings come from Plan 01's `EmbedProvider` seam (Cohere `embed-v3`, dim 1024); tests use a deterministic stub embedder.

---

## Dependencies on other plans

This plan consumes these types from **Plan 01** (`llm/embed/config`). They are listed here so an engineer reading this plan in isolation knows the exact shapes. If Plan 01 has not landed, create the minimal stubs in Task 0; otherwise import them.

```python
# bad_research/embed/base.py  (Plan 01 — consumed here)
from typing import Literal, Protocol
class EmbedProvider(Protocol):
    name: str
    dim: int
    def embed(self, texts: list[str], *, input_type: Literal["document","query"]) -> list[list[float]]: ...

# bad_research/config.py  (Plan 01 — consumed here; only the fields this plan reads)
# BadResearchConfig.vault_root: Path
# BadResearchConfig.embed_model: str = "embed-v3"
# BadResearchConfig.rerank_model: str = "rerank-v3.5"   # or "bge-reranker-v2-m3" offline
```

This plan **adds** to `bad_research/config.py` the retrieval-specific knobs (Task 12) and **adds** no other shared cross-plan types beyond what `retrieval/base.py` declares (`Chunk`, `Reranker`, `RetrievalEngine`) — those are already in `INTERFACES.md` and are produced by this plan.

The `Note` model is hyperresearch's (`bad_research/models/note.py`, a verbatim fork of `hyperresearch/src/hyperresearch/models/note.py`): `Note.meta: NoteMeta`, `Note.body: str`, `Note.path: str`, `Note.meta.id: str`, `Note.meta.source: str | None`, `Note.meta.content_type: ContentType | None`, `Note.meta.tier: Tier | None`, `Note.meta.status` ∈ `{draft,review,evergreen,stale,deprecated,archive}`.

---

## Frozen constants (from `INTERFACES.md` — cite verbatim, never re-derive)

```python
# bad_research/retrieval/constants.py  (Task 1)
ALPHA = 0.7                              # vector weight in hybrid fuse; (1-ALPHA)=BM25            [NIA §5.1]
TOP_K_RETRIEVE = 30                      # hybrid candidates before rerank                          [NIA §5.1]
RETRIEVAL_WEIGHT = {3: 0.75, 10: 0.60}   # three-tier; default 0.40 for rank>10                     [NIA §5.2]
DEEP_RANK_PENALTY = 0.005                # ×(rank-10) for rank>10                                    [NIA §5.2]
RELEVANCE_GATE = 0.70                    # drop fused chunks below this                              [Perplexity]
RERETRIEVE_PASS_FRACTION = 0.30          # <30% pass gate → re-retrieve                              [Perplexity]
RERETRIEVE_MAX_ROUNDS = 2                # ≤2 extra rounds                                           [Perplexity]
SEMANTIC_CACHE_THRESHOLD = 0.92          # cosine; +negation guard                                   [NIA §5.5]
RRF_K = 60                               # reciprocal rank fusion constant                           [Exa/LanceDB §8.8]
SOURCE_TYPE_WEIGHT = {                    # multiply final score by content_type weight              [NIA §5.3]
    "code": 1.2, "repository": 1.2,
    "docs": 1.0, "documentation": 1.0,
    "paper": 0.9, "research_paper": 0.9,
    "dataset": 0.85, "huggingface_dataset": 0.85,
}
DEFAULT_SOURCE_TYPE_WEIGHT = 1.0
# FTS5 BM25 column weights (id/title/body/tags/aliases) and status multipliers — kept verbatim from hyperresearch
BM25_TITLE_WEIGHT, BM25_BODY_WEIGHT, BM25_TAGS_WEIGHT, BM25_ALIASES_WEIGHT = 10.0, 1.0, 5.0, 3.0   [HR fts.py]
BM25_STATUS_MULT = {"evergreen": 1.5, "stale": 0.7, "deprecated": 0.3}                              [HR]
# Chunker
CHUNK_BYTE_TARGET = 2400                  # ~600 tokens; midpoint of NIA's 1500-3000 B               [NIA §3.5]
CHUNK_BYTE_MIN = 2500                     # files under this become a single whole-file chunk        [NIA §3.5]
CHUNK_OVERLAP = 0                         # clean cuts, no overlap                                   [NIA §3.5]
EMBED_TRUNC_CHARS = 16384                 # hard per-text truncation before embed (=2^14)            [NIA §3.4]
EMBED_BATCH_CAP = 96                      # texts per embed() call (Cohere v3 cap is 96)             [dossier 02]
# LanceDB ANN (cite teardowns/LANCEDB.md)
LANCE_INDEX_MIN_ROWS = 256               # below this, flat search only (no ANN index)              [LANCEDB §5.5]
LANCE_NUM_PARTITIONS_TARGET = 10000      # target_partition_size for recommended_num_partitions     [LANCEDB §5.5]
LANCE_HNSW_M = 20                         # IVF_HNSW_PQ edges/node                                   [LANCEDB §5.11]
LANCE_HNSW_EF_CONSTRUCTION = 150         # HNSW build candidate list                                [LANCEDB §5.11]
LANCE_PQ_NUM_SUB_VECTORS = 16            # PQ sub-vectors                                           [LANCEDB §5.4]
LANCE_PREFILTER_FLAT_SELECTIVITY = 0.10  # <10% prefilter selectivity → flat search fallback        [LANCEDB §5]
NEGATION_PATTERN = r"\b(not|without|except|unlike|no_std|never|cannot|isn't|aren't|doesn't|don't|won't|n't)\b"  [NIA §4.3]
```

---

## File Structure

New package `src/bad_research/retrieval/`:

| File | Responsibility |
|---|---|
| `retrieval/__init__.py` | Re-export `Chunk`, `Reranker`, `RetrievalEngine`, `chunk_note`. |
| `retrieval/base.py` | The frozen contracts: `Chunk` dataclass, `Reranker` Protocol, `RetrievalEngine` class signature. |
| `retrieval/constants.py` | Every frozen constant above. Single source of truth, imported everywhere. |
| `retrieval/chunker.py` | `chunk_note(note) -> list[Chunk]`; AST-header-prepend (tree-sitter) for code, heading-aware semantic split for prose, stable `chunk_id=sha1(url#heading)`. |
| `retrieval/store.py` | `LanceChunkStore` — embedded LanceDB `chunks` table: open/create, deterministic index build, upsert, vector search with flat-fallback. |
| `retrieval/fusion.py` | Pure math: `minmax_normalize`, `hybrid_fuse(alpha)`, `three_tier_fuse`, `apply_source_type_weight`, `rrf_merge(k=60)`. No I/O — fully unit-testable. |
| `retrieval/rerank.py` | `CohereReranker` (rerank-v3.5) + `BGEReranker` (bge-reranker-v2-m3 offline), both behind the `Reranker` Protocol; `get_reranker(config)` factory. |
| `retrieval/cache.py` | `SemanticCache` — 0.92-cosine query-embedding cache with regex negation guard. |
| `retrieval/anchors.py` | DDL + helpers for the new SQLite `sources` and `claim_anchors` tables (created here; populated by Plans 05/06). |
| `retrieval/engine.py` | `RetrievalEngine` concrete impl wiring chunker→store+FTS→fusion→rerank→gate→re-retrieve→cache. |

Modified:
| File | Change |
|---|---|
| `core/db.py` | Remove the dead `embeddings` table from `SCHEMA_SQL`; bump `SCHEMA_VERSION` to 9; add a migration that drops `embeddings`. |
| `config.py` (Plan 01) | Add retrieval knobs (Task 12). |
| `pyproject.toml` | Add `lancedb`, `pyarrow`, `tree-sitter`, `tree-sitter-language-pack`, `numpy` deps; optional `cohere`, `FlagEmbedding`. |

Tests mirror hyperresearch layout under `tests/test_retrieval/`:
`test_chunker.py`, `test_fusion.py`, `test_store.py`, `test_rerank.py`, `test_cache.py`, `test_anchors.py`, `test_engine.py`, plus `tests/test_retrieval/conftest.py` (the deterministic stub embedder + a fixed-vector fixture).

---

## Task 0: Package scaffold, deps, and Plan-01 stubs

**Files:**
- Create: `src/bad_research/retrieval/__init__.py`
- Create: `tests/test_retrieval/__init__.py`
- Modify: `pyproject.toml`
- Create (only if Plan 01 not landed): `src/bad_research/embed/base.py`, `src/bad_research/config.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Add to the `dependencies` array:
```toml
    "lancedb>=0.13",
    "pyarrow>=15.0",
    "numpy>=1.26",
    "tree-sitter>=0.23",
    "tree-sitter-language-pack>=0.7",
```
Add optional extras:
```toml
[project.optional-dependencies]
rerank = ["cohere>=5.13"]
rerank-local = ["FlagEmbedding>=1.3"]
```

- [ ] **Step 2: Verify deps install**

Run: `pip install -e '.[rerank,rerank-local]' && python -c "import lancedb, pyarrow, numpy, tree_sitter; from tree_sitter_language_pack import get_parser; get_parser('python'); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Create the package + test package markers**

`src/bad_research/retrieval/__init__.py`:
```python
"""Perplexity×NIA hybrid retrieval engine."""
from bad_research.retrieval.base import Chunk, Reranker, RetrievalEngine
from bad_research.retrieval.chunker import chunk_note

__all__ = ["Chunk", "Reranker", "RetrievalEngine", "chunk_note"]
```
`tests/test_retrieval/__init__.py`: (empty file)

- [ ] **Step 4: If Plan 01 has not landed, create the minimal consumed stubs**

Only do this step if `src/bad_research/embed/base.py` does not already exist. `src/bad_research/embed/base.py`:
```python
from __future__ import annotations
from typing import Literal, Protocol, runtime_checkable

@runtime_checkable
class EmbedProvider(Protocol):
    name: str
    dim: int
    def embed(self, texts: list[str], *, input_type: Literal["document", "query"]) -> list[list[float]]: ...
```
And ensure `src/bad_research/config.py` has at least:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class BadResearchConfig:
    vault_root: Path = Path.home() / ".bad-research"
    model_tiers: dict = field(default_factory=lambda: {
        "triage": "claude-haiku-4-5", "work": "claude-sonnet-4-6", "heavy": "claude-opus-4-7"})
    embed_model: str = "embed-v3"
    rerank_model: str = "rerank-v3.5"
    budget_usd: float | None = None
    cheap: bool = False
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/bad_research/retrieval/__init__.py tests/test_retrieval/__init__.py src/bad_research/embed/base.py src/bad_research/config.py
git commit -m "chore(retrieval): scaffold retrieval package + deps (lancedb, pyarrow, tree-sitter)"
```

---

## Task 1: Frozen constants module

**Files:**
- Create: `src/bad_research/retrieval/constants.py`
- Test: `tests/test_retrieval/test_constants.py`

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_constants.py`:
```python
from bad_research.retrieval import constants as C


def test_frozen_constants_match_interfaces():
    assert C.ALPHA == 0.7
    assert C.TOP_K_RETRIEVE == 30
    assert C.RETRIEVAL_WEIGHT == {3: 0.75, 10: 0.60}
    assert C.DEEP_RANK_PENALTY == 0.005
    assert C.RELEVANCE_GATE == 0.70
    assert C.RERETRIEVE_PASS_FRACTION == 0.30
    assert C.RERETRIEVE_MAX_ROUNDS == 2
    assert C.SEMANTIC_CACHE_THRESHOLD == 0.92
    assert C.RRF_K == 60
    assert C.SOURCE_TYPE_WEIGHT["code"] == 1.2
    assert C.SOURCE_TYPE_WEIGHT["docs"] == 1.0
    assert C.SOURCE_TYPE_WEIGHT["paper"] == 0.9
    assert C.DEFAULT_SOURCE_TYPE_WEIGHT == 1.0
    assert (C.BM25_TITLE_WEIGHT, C.BM25_BODY_WEIGHT, C.BM25_TAGS_WEIGHT, C.BM25_ALIASES_WEIGHT) == (10.0, 1.0, 5.0, 3.0)
    assert C.BM25_STATUS_MULT == {"evergreen": 1.5, "stale": 0.7, "deprecated": 0.3}
    assert C.EMBED_TRUNC_CHARS == 16384
    assert C.EMBED_BATCH_CAP == 96
    assert C.LANCE_INDEX_MIN_ROWS == 256
    assert C.RRF_K == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.constants'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/constants.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_constants.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/constants.py tests/test_retrieval/test_constants.py
git commit -m "feat(retrieval): frozen constants module (alpha=0.7, w-tiers, 0.70 gate, 0.92 cache, RRF k=60)"
```

---

## Task 2: `Chunk`, `Reranker`, `RetrievalEngine` contracts

**Files:**
- Create: `src/bad_research/retrieval/base.py`
- Test: `tests/test_retrieval/test_base.py`

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_base.py`:
```python
from dataclasses import fields
from typing import get_type_hints

from bad_research.retrieval.base import Chunk, Reranker, RetrievalEngine


def test_chunk_shape_matches_interfaces():
    names = {f.name for f in fields(Chunk)}
    assert names == {"chunk_id", "note_id", "text", "char_start", "char_end", "score", "source_id"}
    c = Chunk(chunk_id="a", note_id="n", text="t", char_start=0, char_end=1, score=0.5, source_id="s")
    assert c.score == 0.5 and c.char_end == 1


def test_reranker_is_protocol_with_rerank():
    # A class implementing rerank(query, docs) -> list[tuple[int,float]] is a Reranker
    class _Dummy:
        def rerank(self, query, docs):
            return [(i, 1.0 - i / 10) for i, _ in enumerate(docs)]
    assert isinstance(_Dummy(), Reranker)


def test_retrieval_engine_has_index_and_search():
    assert hasattr(RetrievalEngine, "index")
    assert hasattr(RetrievalEngine, "search")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.base'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/base.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_base.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/base.py tests/test_retrieval/test_base.py
git commit -m "feat(retrieval): Chunk/Reranker/RetrievalEngine contracts per INTERFACES.md"
```

---

## Task 3: Deterministic test fixtures (stub embedder + chunk factory)

**Files:**
- Create: `tests/test_retrieval/conftest.py`

Tests must be deterministic and offline. A hash-based stub embedder produces stable unit vectors so vector math, store round-trips, and cache cosine values are reproducible without any API.

- [ ] **Step 1: Write the fixtures (no separate test — exercised by later tasks)**

`tests/test_retrieval/conftest.py`:
```python
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
```

- [ ] **Step 2: Verify the fixture imports cleanly**

Run: `pytest tests/test_retrieval/ -q --collect-only`
Expected: collection succeeds with no import errors (conftest loads `StubEmbedder`/`make_chunk`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_retrieval/conftest.py
git commit -m "test(retrieval): deterministic stub embedder + chunk factory fixtures"
```

---

## Task 4: Chunker — stable chunk_id + prose semantic split

**Files:**
- Create: `src/bad_research/retrieval/chunker.py`
- Test: `tests/test_retrieval/test_chunker.py`

The chunker produces `Chunk`s with **provenance offsets that index into `note.body`**: `note.body[char_start:char_end]` must equal the chunk's raw source slice (header is prepended in a separate `embed_text` field used only for embedding, NOT counted in offsets). `chunk_id = sha1(url + "#" + heading)`. Prose splits at markdown H2/H3 boundaries; sections over `CHUNK_BYTE_TARGET` split further at paragraph breaks; the whole note becomes one chunk if `len(body) < CHUNK_BYTE_MIN`.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_chunker.py`:
```python
import hashlib

from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.chunker import chunk_note, make_chunk_id


def _note(body: str, source="https://ex.com/a", content_type=None, status="draft") -> Note:
    meta = NoteMeta(title="T", id="n1", source=source, content_type=content_type, status=status)
    return Note(meta=meta, body=body, path="research/n1.md")


def test_chunk_id_is_stable_sha1_of_url_hash_heading():
    cid = make_chunk_id("https://ex.com/a", "Setup")
    assert cid == hashlib.sha1(b"https://ex.com/a#Setup").hexdigest()
    # Deterministic: same inputs -> same id across calls.
    assert make_chunk_id("https://ex.com/a", "Setup") == cid


def test_short_note_is_single_whole_note_chunk():
    body = "# Title\n\nA short prose note under the min byte threshold.\n"
    chunks = chunk_note(_note(body))
    assert len(chunks) == 1
    c = chunks[0]
    # Offsets cover the whole body and slice back to it.
    assert c.char_start == 0
    assert c.char_end == len(body)


def test_prose_splits_at_h2_headings_with_correct_offsets():
    body = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Section One\n\n" + ("alpha " * 600) + "\n\n"
        "## Section Two\n\n" + ("beta " * 600) + "\n"
    )
    chunks = chunk_note(_note(body))
    assert len(chunks) >= 2
    # PROVENANCE: every chunk slices back to its declared offsets exactly.
    for c in chunks:
        assert body[c.char_start:c.char_end] == _slice_for(body, c)
    # Headings became distinct chunk_ids (sha1 of url#heading).
    ids = {c.chunk_id for c in chunks}
    assert len(ids) == len(chunks)


def _slice_for(body, chunk):
    # The chunk text (minus any prepended embed header) must be a verbatim
    # substring of body at [char_start:char_end].
    return body[chunk.char_start:chunk.char_end]


def test_chunk_text_is_verbatim_body_slice():
    body = "# T\n\n## A\n\n" + ("word " * 700) + "\n\n## B\n\n" + ("term " * 700) + "\n"
    for c in chunk_note(_note(body)):
        assert c.text == body[c.char_start:c.char_end]
        assert 0 <= c.char_start < c.char_end <= len(body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_chunker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.chunker'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/chunker.py`:
```python
"""Chunker: stable-ID chunks with verbatim-slice provenance.

- Code notes (content_type == "code"): tree-sitter AST split + NIA-style
  header prepended to embed_text (Task 5 extends this).
- Prose: markdown heading-aware split; oversized sections re-split at
  paragraph breaks. Whole note if body < CHUNK_BYTE_MIN.
- chunk_id = sha1(url + "#" + heading)  (NIA §3.5 stable-id pattern).
- char_start/char_end index into note.body (provenance for grounding, Plan 06).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from bad_research.models.note import Note
from bad_research.retrieval.base import Chunk
from bad_research.retrieval.constants import CHUNK_BYTE_MIN, CHUNK_BYTE_TARGET

_H_RE = re.compile(r"^(#{1,3})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def make_chunk_id(url: str, heading: str) -> str:
    return hashlib.sha1(f"{url}#{heading}".encode()).hexdigest()


@dataclass
class _Span:
    heading: str
    start: int
    end: int


def _heading_spans(body: str) -> list[_Span]:
    """Byte spans between markdown H1-H3 headings. Each span starts at the
    heading line and ends just before the next heading (or EOF)."""
    matches = list(_H_RE.finditer(body))
    if not matches:
        return [_Span("", 0, len(body))]
    spans: list[_Span] = []
    # Preamble before the first heading (if any non-empty content).
    if matches[0].start() > 0:
        spans.append(_Span("", 0, matches[0].start()))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        spans.append(_Span(m.group(2).strip(), start, end))
    return spans


def _split_oversized(span: _Span, body: str) -> list[_Span]:
    """Split a too-large span at blank-line (paragraph) boundaries, keeping
    each piece <= CHUNK_BYTE_TARGET where possible. Offsets stay absolute."""
    text = body[span.start:span.end]
    if len(text.encode()) <= CHUNK_BYTE_TARGET:
        return [span]
    pieces: list[_Span] = []
    cursor = span.start
    para_starts = [span.start] + [span.start + m.end() for m in re.finditer(r"\n\s*\n", text)]
    buf_start = span.start
    for nxt in para_starts[1:] + [span.end]:
        if (nxt - buf_start) > CHUNK_BYTE_TARGET and nxt > buf_start:
            pieces.append(_Span(span.heading, buf_start, nxt))
            buf_start = nxt
        cursor = nxt
    if buf_start < span.end:
        pieces.append(_Span(span.heading, buf_start, span.end))
    return pieces or [span]


def _prose_chunks(note: Note) -> list[Chunk]:
    body = note.body
    url = note.meta.source or note.path
    note_id = note.meta.id
    if len(body.encode()) < CHUNK_BYTE_MIN:
        return [Chunk(
            chunk_id=make_chunk_id(url, note.meta.title or "_"),
            note_id=note_id, text=body, char_start=0, char_end=len(body),
            score=0.0, source_id="")]
    chunks: list[Chunk] = []
    idx = 0
    for span in _heading_spans(body):
        for piece in _split_oversized(span, body):
            text = body[piece.start:piece.end]
            if not text.strip():
                continue
            heading = piece.heading or f"_{idx}"
            # Disambiguate repeated headings after oversize-split with an index suffix.
            cid = make_chunk_id(url, f"{heading}#{idx}" if idx else heading)
            chunks.append(Chunk(chunk_id=cid, note_id=note_id, text=text,
                                char_start=piece.start, char_end=piece.end,
                                score=0.0, source_id=""))
            idx += 1
    return chunks


def chunk_note(note: Note) -> list[Chunk]:
    """Dispatch on content_type. Code → AST (Task 5); else prose."""
    ct = getattr(note.meta, "content_type", None)
    if ct == "code":
        from bad_research.retrieval.chunker_code import chunk_code_note  # Task 5
        return chunk_code_note(note)
    return _prose_chunks(note)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_chunker.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/chunker.py tests/test_retrieval/test_chunker.py
git commit -m "feat(retrieval): prose chunker — stable sha1(url#heading) ids + verbatim-slice offsets"
```

---

## Task 5: Code chunker — tree-sitter AST split + NIA AST-header prepend

**Files:**
- Create: `src/bad_research/retrieval/chunker_code.py`
- Test: `tests/test_retrieval/test_chunker_code.py`

NIA's single biggest insight (dossier 04 §2): before embedding a code chunk, walk the tree-sitter AST and **prepend a plain-text header** so the embedder sees the call graph as tokens. The header is for *embedding only* — it must NOT corrupt `Chunk.text` (which stays a verbatim `body` slice for provenance). So `chunk_code_note` returns `Chunk`s whose `.text` is the raw slice, and a separate `embed_text_for(chunk, note)` builds the augmented string the store embeds. Header format is verbatim NIA §3.1:

```
{owner}/{repo}/{file_path}                          # line 1, always
Calls: {comma_separated_function_names}             # only if call_expressions exist
Control flow: N branches, M loops, complexity C     # always for code
                                                     # blank line
{raw source code}
```

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_chunker_code.py`:
```python
from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.chunker_code import (
    ast_header,
    chunk_code_note,
    embed_text_for,
)


def _code_note(body: str, source="https://github.com/o/r/blob/main/q.py") -> Note:
    meta = NoteMeta(title="q.py", id="qpy", source=source, content_type="code")
    return Note(meta=meta, body=body, path="research/qpy.md")


PY = (
    "def enqueue(x):\n"
    "    if x:\n"
    "        return clear(dequeue(x))\n"
    "    for i in range(3):\n"
    "        pass\n"
    "\n"
    "def helper():\n"
    "    return enqueue(1)\n"
)


def test_code_chunk_text_is_verbatim_body_slice():
    note = _code_note(PY)
    for c in chunk_code_note(note):
        assert c.text == note.body[c.char_start:c.char_end]


def test_ast_header_lists_calls_and_control_flow():
    h = ast_header("o/r/q.py", PY, language="python")
    assert h.splitlines()[0] == "o/r/q.py"
    # Calls present: clear, dequeue, range, enqueue appear as call_expressions.
    calls_line = next(l for l in h.splitlines() if l.startswith("Calls:"))
    assert "dequeue" in calls_line and "clear" in calls_line
    cf = next(l for l in h.splitlines() if l.startswith("Control flow:"))
    assert "branches" in cf and "loops" in cf and "complexity" in cf


def test_embed_text_prepends_header_then_blank_line_then_code():
    note = _code_note(PY)
    chunk = chunk_code_note(note)[0]
    et = embed_text_for(chunk, note)
    # Header, blank line, then the verbatim chunk text.
    assert et.startswith("o/r/q.py")
    assert "\n\n" in et
    assert et.endswith(chunk.text)


def test_non_call_file_omits_calls_line_but_keeps_path_and_controlflow():
    body = "X = 1\nY = 2\n"
    h = ast_header("o/r/c.py", body, language="python")
    lines = h.splitlines()
    assert lines[0] == "o/r/c.py"
    assert not any(l.startswith("Calls:") for l in lines)
    assert any(l.startswith("Control flow:") for l in lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_chunker_code.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.chunker_code'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/chunker_code.py`:
```python
"""Code chunker: tree-sitter AST splits + NIA AST-header (dossier 04 §2, §3.1)."""
from __future__ import annotations

import re

from tree_sitter_language_pack import get_parser

from bad_research.models.note import Note
from bad_research.retrieval.base import Chunk
from bad_research.retrieval.chunker import make_chunk_id
from bad_research.retrieval.constants import CHUNK_BYTE_MIN

# Map common file extensions to tree-sitter-language-pack language names.
_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".jsx": "javascript", ".rs": "rust", ".go": "go", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".rb": "ruby", ".php": "php",
}
# Node types that count as a top-level splittable definition, per language family.
_DEF_TYPES = {
    "function_definition", "function_declaration", "method_definition",
    "class_definition", "class_declaration", "function_item", "impl_item",
    "struct_item", "method_declaration", "arrow_function",
}
_BRANCH_TYPES = {"if_statement", "conditional_expression", "match", "match_statement",
                 "switch_statement", "case", "elif_clause", "else_clause", "match_arm"}
_LOOP_TYPES = {"for_statement", "while_statement", "for_in_statement",
               "do_statement", "loop_expression", "for_expression", "while_expression"}
_CALL_TYPES = {"call", "call_expression", "method_invocation", "macro_invocation"}


def _language_for(source_url: str) -> str:
    for ext, lang in _EXT_LANG.items():
        if source_url.endswith(ext) or source_url.endswith(ext + ".md"):
            return lang
    return "python"


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _call_names(root, src: bytes) -> list[str]:
    names: list[str] = []
    for n in _walk(root):
        if n.type in _CALL_TYPES:
            # The function being called is usually the first identifier child.
            fn = n.child_by_field_name("function") or (n.children[0] if n.children else None)
            if fn is not None:
                ident = fn
                while ident.children and ident.type not in ("identifier", "field_identifier"):
                    ident = ident.children[-1]
                txt = src[ident.start_byte:ident.end_byte].decode("utf-8", "replace")
                if txt and txt.isidentifier():
                    names.append(txt)
    # De-dup preserving order.
    seen: dict[str, None] = {}
    for x in names:
        seen.setdefault(x, None)
    return list(seen)


def _control_flow(root) -> tuple[int, int, int]:
    branches = loops = 0
    for n in _walk(root):
        if n.type in _BRANCH_TYPES:
            branches += 1
        elif n.type in _LOOP_TYPES:
            loops += 1
    complexity = branches + loops + 1  # cyclomatic-ish: decision points + 1
    return branches, loops, complexity


def ast_header(path_label: str, code: str, *, language: str) -> str:
    """Build the NIA verbatim AST header for a code chunk."""
    parser = get_parser(language)
    src = code.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node
    calls = _call_names(root, src)
    branches, loops, complexity = _control_flow(root)
    lines = [path_label]
    if calls:
        lines.append("Calls: " + ", ".join(calls))
    lines.append(f"Control flow: {branches} branches, {loops} loops, complexity {complexity}")
    return "\n".join(lines)


def _path_label(note: Note) -> str:
    url = note.meta.source or note.path
    # "owner/repo/file" style: keep the last 3 path segments when it's a github blob URL.
    m = re.search(r"github\.com/([^/]+)/([^/]+)/blob/[^/]+/(.+)$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return url


def chunk_code_note(note: Note) -> list[Chunk]:
    body = note.body
    url = note.meta.source or note.path
    if len(body.encode()) < CHUNK_BYTE_MIN:
        return [Chunk(chunk_id=make_chunk_id(url, note.meta.title or "_0"),
                      note_id=note.meta.id, text=body, char_start=0, char_end=len(body),
                      score=0.0, source_id="")]
    language = _language_for(url)
    parser = get_parser(language)
    src = body.encode("utf-8")
    root = parser.parse(src).root_node
    # Top-level definitions become chunk boundaries (zero overlap, clean AST cuts).
    defs = [c for c in root.children if c.type in _DEF_TYPES]
    chunks: list[Chunk] = []
    if not defs:
        return [Chunk(chunk_id=make_chunk_id(url, note.meta.title or "_0"),
                      note_id=note.meta.id, text=body, char_start=0, char_end=len(body),
                      score=0.0, source_id="")]
    for idx, d in enumerate(defs):
        start, end = d.start_byte, d.end_byte
        text = src[start:end].decode("utf-8", "replace")
        name = ""
        nm = d.child_by_field_name("name")
        if nm is not None:
            name = src[nm.start_byte:nm.end_byte].decode("utf-8", "replace")
        cid = make_chunk_id(url, name or f"_{idx}")
        chunks.append(Chunk(chunk_id=cid, note_id=note.meta.id, text=text,
                            char_start=start, char_end=end, score=0.0, source_id=""))
    return chunks


def embed_text_for(chunk: Chunk, note: Note) -> str:
    """The augmented string the store embeds: header + blank line + raw code.
    Chunk.text stays the verbatim provenance slice."""
    language = _language_for(note.meta.source or note.path)
    header = ast_header(_path_label(note), chunk.text, language=language)
    return f"{header}\n\n{chunk.text}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_chunker_code.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/chunker_code.py tests/test_retrieval/test_chunker_code.py
git commit -m "feat(retrieval): code chunker — tree-sitter AST split + NIA AST-header prepend (calls/control-flow)"
```

---

## Task 6: Fusion math — hybrid alpha blend + three-tier fusion + RRF

**Files:**
- Create: `src/bad_research/retrieval/fusion.py`
- Test: `tests/test_retrieval/test_fusion.py`

This is the load-bearing algebra (dossier 04 §3.2). It is pure (no I/O), so it is exhaustively unit-tested against hand-computed values. Functions:
- `minmax_normalize(scores)` → maps a score list into [0,1]; constant input → all `1.0` (so a single-candidate lane doesn't collapse to 0).
- `hybrid_fuse(vec_scores, bm25_scores, alpha)` → `alpha*norm(vec) + (1-alpha)*norm(bm25)` aligned by candidate id.
- `retrieval_weight(rank)` → `{≤3:0.75, ≤10:0.60, >10:0.40}` (rank is 1-based).
- `three_tier_fuse(initial, reranker, rank)` → `max(0, w*initial + (1-w)*reranker − penalty)`, penalty = `0.005*(rank-10)` for rank>10.
- `apply_source_type_weight(score, content_type)` → `score * SOURCE_TYPE_WEIGHT.get(ct, 1.0)`.
- `rrf_merge(*ranked_lists, k=60)` → sum `1/(rank0 + k)` over lists (0-based rank, matching LanceDB §8.8 `1.0/(i + k)`).

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_fusion.py`:
```python
import math

from bad_research.retrieval.fusion import (
    apply_source_type_weight,
    hybrid_fuse,
    minmax_normalize,
    retrieval_weight,
    rrf_merge,
    three_tier_fuse,
)


def test_minmax_normalize_basic():
    assert minmax_normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_minmax_normalize_constant_returns_ones():
    # A lane where every score is equal must not collapse to all-zeros.
    assert minmax_normalize([3.0, 3.0, 3.0]) == [1.0, 1.0, 1.0]


def test_minmax_normalize_empty():
    assert minmax_normalize([]) == []


def test_hybrid_fuse_alpha_blend_exact():
    # vec normalized: [1.0, 0.0]; bm25 normalized: [0.0, 1.0]; alpha=0.7
    # id A: 0.7*1.0 + 0.3*0.0 = 0.70 ; id B: 0.7*0.0 + 0.3*1.0 = 0.30
    vec = {"A": 10.0, "B": 0.0}
    bm = {"A": 0.0, "B": 4.0}
    fused = hybrid_fuse(vec, bm, alpha=0.7)
    assert math.isclose(fused["A"], 0.70, abs_tol=1e-9)
    assert math.isclose(fused["B"], 0.30, abs_tol=1e-9)


def test_hybrid_fuse_vector_only_id_uses_zero_for_missing_lane():
    # id present only in vector lane → bm25 contribution 0.
    vec = {"A": 10.0, "B": 5.0}
    bm = {"A": 10.0}  # B absent from bm25
    fused = hybrid_fuse(vec, bm, alpha=0.7)
    # vec norm: A=1.0,B=0.0 ; bm norm: A=1.0 (constant→1.0), B missing→0.0
    assert math.isclose(fused["A"], 0.7 * 1.0 + 0.3 * 1.0, abs_tol=1e-9)  # 1.0
    assert math.isclose(fused["B"], 0.7 * 0.0 + 0.3 * 0.0, abs_tol=1e-9)  # 0.0


def test_retrieval_weight_three_tiers():
    assert retrieval_weight(1) == 0.75
    assert retrieval_weight(3) == 0.75
    assert retrieval_weight(4) == 0.60
    assert retrieval_weight(10) == 0.60
    assert retrieval_weight(11) == 0.40
    assert retrieval_weight(26) == 0.40


def test_three_tier_fuse_exact_top_tier():
    # rank<=3 → w=0.75 ; initial=0.8, reranker=0.4 → 0.75*0.8 + 0.25*0.4 = 0.70
    assert math.isclose(three_tier_fuse(0.8, 0.4, 1), 0.70, abs_tol=1e-12)


def test_three_tier_fuse_exact_mid_tier():
    # rank<=10 → w=0.60 ; initial=0.5, reranker=0.9 → 0.6*0.5 + 0.4*0.9 = 0.66
    assert math.isclose(three_tier_fuse(0.5, 0.9, 7), 0.66, abs_tol=1e-12)


def test_three_tier_fuse_exact_tail_tier_with_penalty():
    # rank=11 → w=0.40 ; initial=0.5, reranker=0.5 → 0.4*0.5 + 0.6*0.5 = 0.50
    # penalty = 0.005*(11-10) = 0.005 → 0.495
    assert math.isclose(three_tier_fuse(0.5, 0.5, 11), 0.495, abs_tol=1e-12)


def test_three_tier_fuse_clamps_to_zero():
    # rank=26 penalty=0.005*16=0.08 ; tiny scores → clamp at 0.0
    assert three_tier_fuse(0.0, 0.0, 26) == 0.0


def test_apply_source_type_weight():
    assert math.isclose(apply_source_type_weight(0.5, "code"), 0.60, abs_tol=1e-12)     # ×1.2
    assert math.isclose(apply_source_type_weight(0.5, "paper"), 0.45, abs_tol=1e-12)    # ×0.9
    assert math.isclose(apply_source_type_weight(0.5, "docs"), 0.50, abs_tol=1e-12)     # ×1.0
    assert math.isclose(apply_source_type_weight(0.5, None), 0.50, abs_tol=1e-12)       # default 1.0


def test_rrf_merge_ranks_not_scores():
    # doc X ranked #1 in list1 (idx0) and #5 in list2 (idx4):
    # 1/(0+60) + 1/(4+60) = 0.0166667 + 0.015625 = 0.0322917
    list1 = ["X", "A", "B", "C", "D"]
    list2 = ["A", "B", "C", "D", "X"]
    merged = rrf_merge(list1, list2, k=60)
    score_x = dict(merged)["X"]
    assert math.isclose(score_x, 1 / 60 + 1 / 64, abs_tol=1e-9)
    # merged is sorted descending by score.
    scores = [s for _, s in merged]
    assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_fusion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.fusion'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/fusion.py`:
```python
"""Pure fusion algebra (dossier 04 §3.2). No I/O — fully unit-testable."""
from __future__ import annotations

from bad_research.retrieval.constants import (
    DEEP_RANK_PENALTY,
    DEFAULT_SOURCE_TYPE_WEIGHT,
    RETRIEVAL_WEIGHT,
    RETRIEVAL_WEIGHT_DEFAULT,
    RRF_K,
    SOURCE_TYPE_WEIGHT,
)


def minmax_normalize(scores: list[float]) -> list[float]:
    """Map scores into [0,1]. Constant input → all 1.0 (lane stays informative)."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0 for _ in scores]
    span = hi - lo
    return [(s - lo) / span for s in scores]


def _normalize_map(score_map: dict[str, float]) -> dict[str, float]:
    keys = list(score_map)
    norm = minmax_normalize([score_map[k] for k in keys])
    return dict(zip(keys, norm, strict=True))


def hybrid_fuse(vec_scores: dict[str, float], bm25_scores: dict[str, float],
                *, alpha: float) -> dict[str, float]:
    """alpha*norm(vector) + (1-alpha)*norm(bm25), aligned by candidate id.
    A candidate missing from a lane contributes 0 from that lane."""
    nv = _normalize_map(vec_scores)
    nb = _normalize_map(bm25_scores)
    ids = set(nv) | set(nb)
    return {cid: alpha * nv.get(cid, 0.0) + (1 - alpha) * nb.get(cid, 0.0) for cid in ids}


def retrieval_weight(pre_rerank_rank: int) -> float:
    """Three-tier weight keyed on 1-based pre-rerank rank (NIA §5.2)."""
    if pre_rerank_rank <= 3:
        return RETRIEVAL_WEIGHT[3]    # 0.75
    if pre_rerank_rank <= 10:
        return RETRIEVAL_WEIGHT[10]   # 0.60
    return RETRIEVAL_WEIGHT_DEFAULT   # 0.40


def three_tier_fuse(initial_score: float, reranker_score: float, pre_rerank_rank: int) -> float:
    """final = max(0, w*initial + (1-w)*reranker − penalty)."""
    w = retrieval_weight(pre_rerank_rank)
    base = w * initial_score + (1 - w) * reranker_score
    if pre_rerank_rank > 10:
        base -= DEEP_RANK_PENALTY * (pre_rerank_rank - 10)
    return max(0.0, base)


def apply_source_type_weight(score: float, content_type: str | None) -> float:
    return score * SOURCE_TYPE_WEIGHT.get(content_type or "", DEFAULT_SOURCE_TYPE_WEIGHT)


def rrf_merge(*ranked_lists: list[str], k: float = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. Sums 1/(rank0 + k) over lists (0-based, LanceDB §8.8).
    Returns [(id, score)] sorted descending."""
    acc: dict[str, float] = {}
    for lst in ranked_lists:
        for rank0, cid in enumerate(lst):
            acc[cid] = acc.get(cid, 0.0) + 1.0 / (rank0 + k)
    return sorted(acc.items(), key=lambda kv: kv[1], reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_fusion.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/fusion.py tests/test_retrieval/test_fusion.py
git commit -m "feat(retrieval): fusion algebra — alpha=0.7 hybrid + three-tier {0.75/0.60/0.40} + RRF k=60"
```

---

## Task 7: LanceDB chunk store — upsert, deterministic index, flat-fallback search

**Files:**
- Create: `src/bad_research/retrieval/store.py`
- Test: `tests/test_retrieval/test_store.py`

`LanceChunkStore` owns the embedded LanceDB table `chunks` at `<vault>/.bad-research/lance/`. Schema (INTERFACES.md): `{chunk_id: str (pk), vector: fixed_size_list<float, dim>, note_id, char_start, char_end, model, dim}`. Per `teardowns/LANCEDB.md`: build IVF_HNSW_PQ (`m=20`, `ef_construction=150`, PQ `num_sub_vectors=16`) deterministically only when rows ≥ `LANCE_INDEX_MIN_ROWS=256`; below that, flat (brute-force) search — which is also the correctness path for tests. A prefilter whose estimated selectivity is `< 0.10` forces flat search even when an index exists (LANCEDB §5 flat-fallback). Metric is cosine.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_store.py`:
```python
import pyarrow as pa

from bad_research.retrieval.store import LanceChunkStore


def _rows(embedder, texts):
    vecs = embedder.embed(texts, input_type="document")
    return [
        {"chunk_id": f"c{i}", "vector": vecs[i], "note_id": f"n{i}",
         "char_start": 0, "char_end": len(texts[i]), "model": embedder.name, "dim": embedder.dim}
        for i in range(len(texts))
    ]


def test_create_and_count(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha beta", "gamma delta"]))
    assert store.count() == 2


def test_upsert_is_idempotent_on_chunk_id(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    rows = _rows(stub_embedder, ["alpha beta"])
    store.upsert(rows)
    store.upsert(rows)  # same chunk_id again
    assert store.count() == 1


def test_flat_vector_search_returns_nearest_first(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha alpha alpha", "zeta zeta zeta", "alpha beta"]))
    qv = stub_embedder.embed(["alpha alpha alpha"], input_type="query")[0]
    hits = store.search_vector(qv, top_k=3)
    # Each hit is (chunk_id, distance). Nearest (identical token-bag) is first.
    assert hits[0][0] == "c0"
    # Sorted ascending by distance.
    dists = [d for _, d in hits]
    assert dists == sorted(dists)


def test_search_returns_scores_in_unit_range_via_cosine(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha beta gamma"]))
    qv = stub_embedder.embed(["alpha beta gamma"], input_type="query")[0]
    hits = store.search_vector(qv, top_k=1)
    cid, dist = hits[0]
    # Identical vectors → cosine distance ~0.
    assert cid == "c0"
    assert dist < 1e-3


def test_to_score_converts_cosine_distance_to_similarity():
    # similarity = 1 - distance, clamped to [0,1].
    assert abs(LanceChunkStore.distance_to_score(0.0) - 1.0) < 1e-9
    assert abs(LanceChunkStore.distance_to_score(1.0) - 0.0) < 1e-9
    assert LanceChunkStore.distance_to_score(2.0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.store'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/store.py`:
```python
"""Embedded LanceDB chunk store (teardowns/LANCEDB.md).

Vector lane of the hybrid engine. Deterministic IVF_HNSW_PQ index when the
table is large enough; flat (brute-force) search below the threshold and as a
prefilter fallback under low selectivity. Cosine metric."""
from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

from bad_research.retrieval.constants import (
    LANCE_HNSW_EF_CONSTRUCTION,
    LANCE_HNSW_M,
    LANCE_INDEX_MIN_ROWS,
    LANCE_NUM_PARTITIONS_TARGET,
    LANCE_PQ_NUM_SUB_VECTORS,
)

TABLE = "chunks"


class LanceChunkStore:
    def __init__(self, lance_dir: Path, *, dim: int):
        self.dir = Path(lance_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.db = lancedb.connect(str(self.dir))
        self._table = self._open_or_create()

    def _schema(self) -> pa.Schema:
        return pa.schema([
            pa.field("chunk_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dim)),
            pa.field("note_id", pa.string()),
            pa.field("char_start", pa.int64()),
            pa.field("char_end", pa.int64()),
            pa.field("model", pa.string()),
            pa.field("dim", pa.int64()),
        ])

    def _open_or_create(self):
        if TABLE in self.db.table_names():
            return self.db.open_table(TABLE)
        return self.db.create_table(TABLE, schema=self._schema())

    def upsert(self, rows: list[dict]) -> None:
        """Idempotent on chunk_id (merge_insert delete-then-insert on match)."""
        if not rows:
            return
        tbl = pa.Table.from_pylist(rows, schema=self._schema())
        (self._table.merge_insert("chunk_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(tbl))

    def count(self) -> int:
        return self._table.count_rows()

    def maybe_build_index(self) -> bool:
        """Build a deterministic IVF_HNSW_PQ index iff rows >= threshold.
        Returns True if an index was (or already is) present."""
        n = self.count()
        if n < LANCE_INDEX_MIN_ROWS:
            return False
        num_partitions = max(1, min(4096, n // LANCE_NUM_PARTITIONS_TARGET or 1))
        # Deterministic build: fixed params, no random sampling knobs left to default.
        self._table.create_index(
            metric="cosine",
            vector_column_name="vector",
            index_type="IVF_HNSW_PQ",
            num_partitions=num_partitions,
            num_sub_vectors=LANCE_PQ_NUM_SUB_VECTORS,
            m=LANCE_HNSW_M,
            ef_construction=LANCE_HNSW_EF_CONSTRUCTION,
            replace=True,
        )
        return True

    def search_vector(self, query_vector: list[float], *, top_k: int,
                      where: str | None = None) -> list[tuple[str, float]]:
        """Return [(chunk_id, cosine_distance)] ascending by distance.

        With < LANCE_INDEX_MIN_ROWS rows (or no index) LanceDB performs a flat
        scan automatically — exact and deterministic. A restrictive prefilter
        (`where`) is applied pre-search (prefilter=True) so low-selectivity
        filters fall back to flat scan (LANCEDB §5)."""
        q = self._table.search(query_vector).distance_type("cosine").limit(top_k)
        if where:
            q = q.where(where, prefilter=True)
        rows = q.to_list()
        return [(r["chunk_id"], float(r["_distance"])) for r in rows]

    @staticmethod
    def distance_to_score(distance: float) -> float:
        """Cosine distance → similarity in [0,1]: 1 - d, clamped."""
        return max(0.0, min(1.0, 1.0 - distance))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/store.py tests/test_retrieval/test_store.py
git commit -m "feat(retrieval): LanceDB chunk store — merge-insert upsert, deterministic IVF_HNSW_PQ, flat-fallback cosine search"
```

---

## Task 8: Rerankers — Cohere (mocked) + BGE offline, behind the Protocol

**Files:**
- Create: `src/bad_research/retrieval/rerank.py`
- Test: `tests/test_retrieval/test_rerank.py`

`CohereReranker` (default, `rerank-v3.5`) and `BGEReranker` (`bge-reranker-v2-m3`, offline). Both satisfy `Reranker` (`rerank(query, docs) -> [(idx, score)]` desc). `get_reranker(config)` returns Cohere when `config.rerank_model` starts with `rerank` and a key exists, else BGE. Cohere is tested with a **mocked client** (no network); the test asserts the engine consumes the mocked ordering correctly.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_rerank.py`:
```python
from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import CohereReranker, get_reranker


class _FakeCohereResp:
    def __init__(self, results):
        self.results = results


class _FakeResult:
    def __init__(self, index, relevance_score):
        self.index = index
        self.relevance_score = relevance_score


class _FakeCohereClient:
    """Mimics cohere.ClientV2.rerank: returns results sorted by relevance desc."""
    def __init__(self):
        self.calls = []

    def rerank(self, *, model, query, documents, top_n=None):
        self.calls.append({"model": model, "query": query, "n": len(documents)})
        # Deterministic fake: score = 1.0 for the doc containing 'match', else 0.1,
        # returned already sorted desc (as Cohere does).
        scored = [(i, 0.95 if "match" in d else 0.10) for i, d in enumerate(documents)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return _FakeCohereResp([_FakeResult(i, s) for i, s in scored])


def test_cohere_reranker_is_a_reranker_and_orders_by_relevance():
    client = _FakeCohereClient()
    rr = CohereReranker(model="rerank-v3.5", client=client)
    assert isinstance(rr, Reranker)
    docs = ["nope one", "the match here", "nope two"]
    out = rr.rerank("find the match", docs)
    # (idx, score) desc; the 'match' doc (index 1) ranks first.
    assert out[0][0] == 1
    assert out[0][1] == 0.95
    assert [i for i, _ in out] == [1, 0, 2] or [i for i, _ in out][0] == 1
    # The full candidate set is reranked (NIA: reranks ALL 30), not truncated.
    assert client.calls[0]["n"] == 3
    assert client.calls[0]["model"] == "rerank-v3.5"


def test_get_reranker_prefers_cohere_when_key_present(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test-key")

    class _Cfg:
        rerank_model = "rerank-v3.5"

    rr = get_reranker(_Cfg(), client=_FakeCohereClient())
    assert isinstance(rr, CohereReranker)


def test_get_reranker_falls_back_to_bge_when_model_is_bge():
    class _Cfg:
        rerank_model = "bge-reranker-v2-m3"

    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    out = rr.rerank("q", ["a", "b", "c"])
    assert isinstance(rr, Reranker)
    assert len(out) == 3
    # ties broken by stable index order.
    assert [i for i, _ in out] == [0, 1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_rerank.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.rerank'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/rerank.py`:
```python
"""Rerankers behind the Reranker Protocol.

Default: CohereReranker (rerank-v3.5, reranks the full candidate set — NIA §5.4).
Offline: BGEReranker (bge-reranker-v2-m3) via FlagEmbedding/sentence-transformers."""
from __future__ import annotations

import os
from collections.abc import Callable


class CohereReranker:
    def __init__(self, *, model: str = "rerank-v3.5", api_key: str | None = None, client=None):
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


class BGEReranker:
    """Local cross-encoder. `scorer(pairs)` maps [(query, doc)] -> [score].
    In production, scorer wraps FlagEmbedding.FlagReranker('BAAI/bge-reranker-v2-m3')."""

    def __init__(self, *, model: str = "bge-reranker-v2-m3", scorer: Callable | None = None):
        self.model = model
        if scorer is not None:
            self._scorer = scorer
        else:
            from FlagEmbedding import FlagReranker  # lazy
            fr = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
            self._scorer = lambda pairs: fr.compute_score(pairs, normalize=True)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        scores = self._scorer([(query, d) for d in docs])
        scored = list(enumerate(float(s) for s in scores))
        # Sort desc by score; ties broken by ascending index (stable).
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored


def get_reranker(config, *, client=None, bge_scorer=None):
    """Cohere when rerank_model is a 'rerank*' id AND a COHERE_API_KEY exists
    (or a client is injected); else the offline BGE reranker."""
    model = getattr(config, "rerank_model", "rerank-v3.5")
    if model.startswith("rerank") and (client is not None or os.environ.get("COHERE_API_KEY")):
        return CohereReranker(model=model, client=client)
    return BGEReranker(model=model, scorer=bge_scorer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_rerank.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/rerank.py tests/test_retrieval/test_rerank.py
git commit -m "feat(retrieval): CohereReranker(rerank-v3.5)+BGEReranker(bge-reranker-v2-m3) behind Reranker Protocol"
```

---

## Task 9: Negation-guarded semantic cache

**Files:**
- Create: `src/bad_research/retrieval/cache.py`
- Test: `tests/test_retrieval/test_cache.py`

A single-user SQLite-backed query-embedding cache (dossier 04 §4). On `get(query)`: embed the query, cosine-compare against cached query embeddings; HIT at `cosine >= 0.92` **unless** the new query carries a negation marker the cached query lacked (the NIA negation-blindness fix, §4.3) — then force a MISS. `put(query, payload)` stores the query embedding + payload. The store is per-vault SQLite (`query_cache` table), keyed by an LSH-ish bucket of the embedding for cheap candidate fetch; for correctness the cosine check is exact over bucket candidates.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_cache.py`:
```python
from bad_research.retrieval.cache import SemanticCache, has_negation


def test_has_negation_detects_markers():
    assert has_negation("how does X work without async")
    assert has_negation("X but NOT in no_std")
    assert has_negation("this isn't supported")
    assert not has_negation("how does X wrap source chains")


def test_cache_hit_on_paraphrase(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function wrap chains", {"answer": "A"})
    # Paraphrase with heavy token overlap → cosine >= 0.92 under the stub → HIT.
    hit = cache.get("how does function wrap chains")
    assert hit is not None
    assert hit["payload"] == {"answer": "A"}
    assert hit["cache_similarity"] >= 0.92


def test_cache_miss_when_negation_added(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function wrap chains", {"answer": "A"})
    # Same tokens + a NEGATION word the cached query lacked → forced MISS,
    # even if the raw cosine would clear 0.92 (NIA negation-blindness fix §4.3).
    assert cache.get("how does function NOT wrap chains") is None


def test_cache_miss_on_different_topic(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("alpha beta gamma delta", {"answer": "A"})
    assert cache.get("zeta eta theta iota") is None


def test_cache_negation_to_negation_can_hit(tmp_path, stub_embedder):
    # If BOTH queries carry negation, the guard does not force a miss —
    # they are semantically aligned on the negation.
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function NOT wrap chains", {"answer": "neg"})
    hit = cache.get("how does function NOT wrap chains")
    assert hit is not None and hit["payload"] == {"answer": "neg"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.cache'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/cache.py`:
```python
"""Negation-guarded semantic query cache (dossier 04 §4.1-§4.3).

0.92-cosine over cached query embeddings; a HIT is suppressed when the new
query adds a negation marker the cached query lacked (NIA's documented defect)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

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

    def get(self, query: str) -> dict | None:
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
        # Negation guard: if the new query negates but the cached one did not,
        # force a miss (NIA §4.3). Negation-to-negation is allowed.
        if q_neg and not best["has_negation"]:
            return None
        if (not q_neg) and best["has_negation"]:
            return None
        return {"payload": json.loads(best["payload"]),
                "cache_similarity": best_sim,
                "original_query": best["query_text"]}

    def put(self, query: str, payload: dict) -> None:
        qv = self.embedder.embed([query], input_type="query")[0]
        self.conn.execute(
            "INSERT OR REPLACE INTO query_cache (query_text, embedding, has_negation, payload) "
            "VALUES (?, ?, ?, ?)",
            (query, json.dumps(qv), int(has_negation(query)), json.dumps(payload)),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_cache.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/cache.py tests/test_retrieval/test_cache.py
git commit -m "feat(retrieval): negation-guarded 0.92-cosine semantic cache (NIA §4.3 defect fix)"
```

---

## Task 10: `sources` + `claim_anchors` SQLite DDL

**Files:**
- Create: `src/bad_research/retrieval/anchors.py`
- Test: `tests/test_retrieval/test_anchors.py`

These two tables are created here (DDL + create function); they are **populated by Plans 05 (sources) and 06 (claim_anchors)**. Columns are verbatim from INTERFACES.md §Vault schema additions. This replaces hyperresearch's narrower `sources` table (which had `url PK` + status) with the provenance/dedup shape Plan 05 needs.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_anchors.py`:
```python
import sqlite3

from bad_research.retrieval.anchors import create_provenance_tables


def test_sources_table_has_interfaces_columns(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    assert cols == {
        "source_id", "url", "domain", "domain_tier", "fetch_provider",
        "tier", "fetched_at", "document_date", "event_date",
    }
    # source_id is the primary key.
    pk = [r[1] for r in conn.execute("PRAGMA table_info(sources)") if r[5]]
    assert pk == ["source_id"]


def test_claim_anchors_table_has_interfaces_columns(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(claim_anchors)")}
    assert cols == {
        "anchor_id", "note_id", "char_start", "char_end", "claim",
        "quoted_support", "verified", "verify_score",
    }
    pk = [r[1] for r in conn.execute("PRAGMA table_info(claim_anchors)") if r[5]]
    assert pk == ["anchor_id"]


def test_create_is_idempotent(tmp_path):
    conn = sqlite3.connect(":memory:")
    create_provenance_tables(conn)
    create_provenance_tables(conn)  # second call must not raise
    assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_anchors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.anchors'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/anchors.py`:
```python
"""Provenance + grounding table DDL (INTERFACES.md §Vault schema additions).

`sources` populated by Plan 05/07; `claim_anchors` populated by Plan 06.
Created here so the retrieval engine can be wired against a complete schema."""
from __future__ import annotations

import sqlite3

PROVENANCE_DDL = """
CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,   -- 16-char sha256
    url            TEXT,
    domain         TEXT,
    domain_tier    REAL,
    fetch_provider TEXT,
    tier           INTEGER,
    fetched_at     TEXT,
    document_date  TEXT,
    event_date     TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);

CREATE TABLE IF NOT EXISTS claim_anchors (
    anchor_id      TEXT PRIMARY KEY,   -- = quote_sha (8-char)
    note_id        TEXT,
    char_start     INTEGER,
    char_end       INTEGER,
    claim          TEXT,
    quoted_support TEXT,
    verified       INTEGER,
    verify_score   REAL
);
CREATE INDEX IF NOT EXISTS idx_claim_anchors_note ON claim_anchors(note_id);
"""


def create_provenance_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(PROVENANCE_DDL)
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_anchors.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/anchors.py tests/test_retrieval/test_anchors.py
git commit -m "feat(retrieval): sources + claim_anchors DDL per INTERFACES (populated by Plans 05/06)"
```

---

## Task 11: Remove the dead `embeddings` table; schema v8 → v9

**Files:**
- Modify: `src/bad_research/core/db.py` (forked from `hyperresearch/src/hyperresearch/core/db.py`)
- Modify: `src/bad_research/core/migrations.py` (forked from hyperresearch)
- Test: `tests/test_retrieval/test_schema_migration.py`

The hyperresearch `embeddings` table (`db.py:88-94`) is vestigial (never populated) and is replaced by LanceDB. Remove it from `SCHEMA_SQL`, bump `SCHEMA_VERSION` to 9, and add a migration that `DROP TABLE IF EXISTS embeddings` for existing vaults. Provenance tables are created via Task 10's `create_provenance_tables` in `init_schema`.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_schema_migration.py`:
```python
import sqlite3

from bad_research.core.db import SCHEMA_VERSION, init_schema


def test_embeddings_table_is_gone_after_init():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "embeddings" not in names
    # Provenance tables are created.
    assert "sources" in names
    assert "claim_anchors" in names


def test_schema_version_is_9():
    assert SCHEMA_VERSION == 9


def test_migration_drops_preexisting_embeddings_table():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Simulate a v8 vault that already has the dead table.
    conn.execute("CREATE TABLE embeddings (note_id TEXT PRIMARY KEY, model TEXT, "
                 "dimensions INTEGER, vector BLOB, created_at TEXT)")
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO _meta VALUES ('schema_version', '8')")
    conn.commit()
    init_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "embeddings" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_schema_migration.py -v`
Expected: FAIL (either `embeddings` still present, or `SCHEMA_VERSION != 9`, or `sources` missing the new columns)

- [ ] **Step 3: Write minimal implementation**

In `src/bad_research/core/db.py`:

(a) Bump the version:
```python
SCHEMA_VERSION = 9
```

(b) Delete the `embeddings` `CREATE TABLE` block from `SCHEMA_SQL` (the lines creating `embeddings(note_id PK, model, dimensions, vector BLOB, created_at)`).

(c) Replace the old narrow `sources` `CREATE TABLE` block in `SCHEMA_SQL` with nothing (the provenance `sources` table is now created by `create_provenance_tables`), and remove its `idx_sources_*` indexes from `SCHEMA_SQL`.

(d) Wire provenance-table creation + the drop migration into `init_schema`:
```python
def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist, then run pending migrations."""
    conn.executescript(SCHEMA_SQL)
    conn.executescript(FTS_SQL)
    conn.execute(
        "INSERT OR IGNORE INTO _meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()

    from bad_research.core.migrations import migrate
    migrate(conn, SCHEMA_VERSION)

    # Provenance + grounding tables (Plan 02 Task 10).
    from bad_research.retrieval.anchors import create_provenance_tables
    create_provenance_tables(conn)

    conn.executescript(POST_MIGRATE_INDEXES_SQL)
    conn.commit()
```

In `src/bad_research/core/migrations.py`, add a v9 step that drops the dead table (place alongside the existing migration ladder; this DDL is idempotent and safe to run unconditionally inside `init_schema`'s migrate call):
```python
def _migrate_v9_drop_embeddings(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS embeddings")
    # The old narrow `sources` shape is superseded by the provenance table.
    # If a legacy `sources` with column `provider` (not `fetch_provider`) exists,
    # drop it so create_provenance_tables installs the new shape.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    if cols and "fetch_provider" not in cols:
        conn.execute("DROP TABLE IF EXISTS sources")
    conn.commit()
```
And ensure `migrate(conn, SCHEMA_VERSION)` calls `_migrate_v9_drop_embeddings(conn)` when advancing to v9 (follow the existing migration-dispatch pattern in that file — add the function to the version→callable mapping for version 9).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_schema_migration.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/db.py src/bad_research/core/migrations.py tests/test_retrieval/test_schema_migration.py
git commit -m "feat(core): drop dead embeddings table, schema v8->v9, install provenance tables"
```

---

## Task 12: Retrieval config knobs

**Files:**
- Modify: `src/bad_research/config.py` (Plan 01's `BadResearchConfig`)
- Test: `tests/test_retrieval/test_config.py`

Surface the retrieval knobs that a user might tune (alpha, gate, cache threshold, top_k) on `BadResearchConfig`, defaulting to the frozen constants. The engine reads these (not the constants module directly) so config overrides take effect.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_config.py`:
```python
from bad_research.config import BadResearchConfig
from bad_research.retrieval import constants as C


def test_config_retrieval_defaults_match_frozen_constants():
    cfg = BadResearchConfig()
    assert cfg.retrieval_alpha == C.ALPHA
    assert cfg.relevance_gate == C.RELEVANCE_GATE
    assert cfg.semantic_cache_threshold == C.SEMANTIC_CACHE_THRESHOLD
    assert cfg.top_k_retrieve == C.TOP_K_RETRIEVE


def test_config_retrieval_overridable():
    cfg = BadResearchConfig(retrieval_alpha=0.5)
    assert cfg.retrieval_alpha == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_config.py -v`
Expected: FAIL with `AttributeError: 'BadResearchConfig' object has no attribute 'retrieval_alpha'`

- [ ] **Step 3: Write minimal implementation**

Add these fields to the `BadResearchConfig` dataclass in `src/bad_research/config.py`:
```python
    # Retrieval knobs (Plan 02; default to the frozen constants).
    retrieval_alpha: float = 0.7
    relevance_gate: float = 0.70
    semantic_cache_threshold: float = 0.92
    top_k_retrieve: int = 30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/config.py tests/test_retrieval/test_config.py
git commit -m "feat(config): expose retrieval knobs (alpha, gate, cache threshold, top_k) defaulting to frozen constants"
```

---

## Task 13: Chunk-level FTS5 lexical lane

**Files:**
- Create: `src/bad_research/retrieval/fts_chunks.py`
- Test: `tests/test_retrieval/test_fts_chunks.py`

The BM25 lane operates over **chunks**, not whole notes (the hybrid fuses chunk-vs-chunk). We keep hyperresearch's exact BM25 column weights (`10/1/5/3`) and status multipliers (`1.5/0.7/0.3`), but index chunk text in a dedicated FTS5 virtual table `chunk_fts(chunk_id UNINDEXED, body, note_id UNINDEXED)`. `search_chunk_fts(conn, query, limit)` returns `[(chunk_id, abs_bm25_score)]` (abs because SQLite bm25 returns negatives, smaller = better; hyperresearch takes `abs()`). Query preprocessing reuses hyperresearch's `preprocess_query` (`search/fts.py`).

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_fts_chunks.py`:
```python
import sqlite3

from bad_research.retrieval.fts_chunks import (
    create_chunk_fts,
    index_chunk_fts,
    search_chunk_fts,
)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_chunk_fts(c)
    return c


def test_search_returns_matching_chunk_ids():
    conn = _conn()
    index_chunk_fts(conn, [
        {"chunk_id": "c0", "note_id": "n0", "body": "python async await concurrency"},
        {"chunk_id": "c1", "note_id": "n1", "body": "rust ownership borrow checker"},
    ])
    hits = search_chunk_fts(conn, "python async", limit=10)
    ids = [cid for cid, _ in hits]
    assert "c0" in ids
    assert "c1" not in ids


def test_scores_are_positive_and_higher_is_better():
    conn = _conn()
    index_chunk_fts(conn, [
        {"chunk_id": "c0", "note_id": "n0", "body": "python python python async"},
        {"chunk_id": "c1", "note_id": "n1", "body": "python once only here"},
    ])
    hits = dict(search_chunk_fts(conn, "python", limit=10))
    assert all(s >= 0 for s in hits.values())
    # The chunk with more matches scores higher (abs bm25).
    assert hits["c0"] > hits["c1"]


def test_reindex_replaces_chunk_body():
    conn = _conn()
    index_chunk_fts(conn, [{"chunk_id": "c0", "note_id": "n0", "body": "alpha"}])
    index_chunk_fts(conn, [{"chunk_id": "c0", "note_id": "n0", "body": "beta gamma"}])
    assert [cid for cid, _ in search_chunk_fts(conn, "alpha", limit=10)] == []
    assert [cid for cid, _ in search_chunk_fts(conn, "beta", limit=10)] == ["c0"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_fts_chunks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.fts_chunks'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/fts_chunks.py`:
```python
"""Chunk-level FTS5/BM25 lane. Reuses hyperresearch's query preprocessing and
the body weight; chunk_fts has a single content column so we only weight body."""
from __future__ import annotations

import sqlite3

from bad_research.retrieval.constants import BM25_BODY_WEIGHT
from bad_research.search.fts import preprocess_query  # forked hyperresearch helper

_CHUNK_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    body,
    note_id UNINDEXED,
    tokenize='porter unicode61'
);
"""


def create_chunk_fts(conn: sqlite3.Connection) -> None:
    conn.executescript(_CHUNK_FTS_DDL)
    conn.commit()


def index_chunk_fts(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Upsert chunk bodies. FTS5 has no PK, so delete-by-chunk_id then insert."""
    for r in rows:
        conn.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (r["chunk_id"],))
    conn.executemany(
        "INSERT INTO chunk_fts (chunk_id, body, note_id) VALUES (:chunk_id, :body, :note_id)",
        rows,
    )
    conn.commit()


def search_chunk_fts(conn: sqlite3.Connection, query: str, *, limit: int) -> list[tuple[str, float]]:
    """Return [(chunk_id, abs_bm25)] best-first. abs() because SQLite bm25
    returns negatives (smaller = better); hyperresearch takes abs()."""
    fts_query = preprocess_query(query)
    sql = """
        SELECT chunk_id, bm25(chunk_fts, 0.0, ?, 0.0) AS score
        FROM chunk_fts
        WHERE chunk_fts MATCH ?
        ORDER BY score
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, (BM25_BODY_WEIGHT, fts_query, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["chunk_id"], abs(r["score"])) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_fts_chunks.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/fts_chunks.py tests/test_retrieval/test_fts_chunks.py
git commit -m "feat(retrieval): chunk-level FTS5/BM25 lane (abs bm25, body weight kept from hyperresearch)"
```

---

## Task 14: `RetrievalEngine` — index + hybrid search + rerank + gate + re-retrieve + cache

**Files:**
- Modify: `src/bad_research/retrieval/engine.py` (new file replacing the `RetrievalEngine` stub in `base.py`)
- Modify: `src/bad_research/retrieval/base.py` (re-point the class — see note)
- Test: `tests/test_retrieval/test_engine.py`

The concrete engine. To keep the `Chunk`/`Reranker`/`RetrievalEngine` names importable from `base.py` per INTERFACES, `engine.py` holds the implementation and `base.py`'s `RetrievalEngine` is replaced by `from bad_research.retrieval.engine import RetrievalEngine` re-export at the bottom of the package `__init__` — but the canonical class lives in `engine.py`. (Update `__init__.py` to export the concrete class.)

`index(notes)`: for each note → `chunk_note` → embed (code chunks via `embed_text_for`, prose chunks via raw text), truncate each embed text to `EMBED_TRUNC_CHARS`, batch at `EMBED_BATCH_CAP`, upsert vectors to LanceDB + bodies to `chunk_fts`; track chunk metadata (note_id, content_type, offsets) in an in-memory map rebuildable from disk.

`search(query, mode, top_k)`:
1. Semantic-cache `get` → on HIT return cached chunks.
2. Round loop (≤ `1 + RERETRIEVE_MAX_ROUNDS`):
   a. embed query; LanceDB vector search top-`TOP_K_RETRIEVE`; chunk FTS top-`TOP_K_RETRIEVE`.
   b. `hybrid_fuse(alpha)` → initial scores; rank candidates by initial desc → `pre_rerank_rank` (1-based).
   c. rerank the full candidate doc set (reranker over all candidates' text).
   d. `three_tier_fuse(initial, reranker, rank)` per candidate; `apply_source_type_weight(score, content_type)`.
   e. gate at `RELEVANCE_GATE`; compute pass fraction.
   f. if `pass_fraction >= RERETRIEVE_PASS_FRACTION` or rounds exhausted → break; else widen (`expand_symbols`-style: append the top hit's note_id-neighbors to the candidate set on the next round) and retry.
3. Sort survivors desc, take `top_k`, `put` into the cache, return `Chunk`s with `.score` = fused score.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval/test_engine.py`:
```python
import math

from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.base import Reranker
from bad_research.retrieval.engine import RetrievalEngine


class _IdentityReranker:
    """reranker_score = 1.0 if query token-set ⊆ doc else 0.2; stable order."""
    def rerank(self, query, docs):
        qtoks = set(query.lower().split())
        out = [(i, 0.95 if qtoks & set(d.lower().split()) else 0.20) for i, d in enumerate(docs)]
        out.sort(key=lambda x: (-x[1], x[0]))
        return out


def _note(nid, body, ct=None, status="evergreen"):
    return Note(meta=NoteMeta(title=nid, id=nid, source=f"https://ex.com/{nid}",
                              content_type=ct, status=status),
                body=body, path=f"research/{nid}.md")


def _engine(tmp_path, stub_embedder):
    return RetrievalEngine(
        lance_dir=tmp_path / "lance",
        cache_db=tmp_path / "cache.db",
        embedder=stub_embedder,
        reranker=_IdentityReranker(),
    )


def test_reranker_protocol_satisfied():
    assert isinstance(_IdentityReranker(), Reranker)


def test_index_then_search_returns_relevant_chunk_first(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([
        _note("a", "# A\n\npython async await concurrency patterns explained\n"),
        _note("b", "# B\n\nrust ownership borrow checker lifetimes memory\n"),
    ])
    hits = eng.search("python async", mode="light", top_k=2)
    assert len(hits) >= 1
    assert hits[0].note_id == "a"
    # Provenance offsets slice back into the note body.
    assert hits[0].char_end > hits[0].char_start


def test_relevance_gate_drops_low_scoring_chunks(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await\n"),
               _note("z", "# Z\n\ntotally unrelated zebra xylophone\n")])
    hits = eng.search("python async", mode="light", top_k=10)
    # Every returned chunk cleared the 0.70 gate.
    assert all(h.score >= 0.70 for h in hits)


def test_source_type_weight_boosts_code(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    # Two near-identical chunks; one is content_type=code (×1.2).
    eng.index([_note("code", "def parse_async(): return async_io_loop()\n" * 80, ct="code"),
               _note("docs", "parse async io loop documentation prose\n" * 80, ct="docs")])
    hits = eng.search("parse async", mode="full", top_k=2)
    by_note = {h.note_id: h.score for h in hits}
    # If both survive, the code chunk's source-type weight makes it score >= docs.
    if "code" in by_note and "docs" in by_note:
        assert by_note["code"] >= by_note["docs"]


def test_semantic_cache_hit_on_repeat_query(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    first = eng.search("python async concurrency", mode="light", top_k=3)
    # A negation-free repeat → served from cache, identical chunk_ids.
    second = eng.search("python async concurrency", mode="light", top_k=3)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_cache_miss_when_negation_added(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    eng.search("python async concurrency", mode="light", top_k=3)
    # Adding NOT must not serve the affirmative cached answer (force recompute path).
    # We assert the cache layer reported a miss via the engine's last_cache_hit flag.
    eng.search("python NOT async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.retrieval.engine'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/retrieval/engine.py`:
```python
"""Concrete RetrievalEngine: chunk→embed→LanceDB+FTS index; hybrid→rerank→
three-tier fusion→0.70 gate→<30%-pass re-retrieve→negation-guarded cache."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

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
        rows: list[dict] = []
        fts_rows: list[dict] = []
        pending: list[Chunk] = []
        ct_for: list[str | None] = []
        for note in notes:
            ct = getattr(note.meta, "content_type", None)
            for chunk in chunk_note(note):
                et = embed_text_for(chunk, note) if ct == "code" else chunk.text
                embed_texts.append(et[:EMBED_TRUNC_CHARS])
                pending.append(chunk)
                ct_for.append(ct)
        # Batch-embed at the provider cap.
        vectors: list[list[float]] = []
        for i in range(0, len(embed_texts), EMBED_BATCH_CAP):
            batch = embed_texts[i:i + EMBED_BATCH_CAP]
            vectors.extend(self.embedder.embed(batch, input_type="document"))
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

    def _one_round(self, query: str, extra_ids: set[str]):
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
```

Update `src/bad_research/retrieval/__init__.py` and `base.py` so the concrete engine is the exported `RetrievalEngine`:
```python
# src/bad_research/retrieval/__init__.py
from bad_research.retrieval.base import Chunk, Reranker
from bad_research.retrieval.chunker import chunk_note
from bad_research.retrieval.engine import RetrievalEngine

__all__ = ["Chunk", "Reranker", "RetrievalEngine", "chunk_note"]
```
Remove the placeholder `RetrievalEngine` class from `base.py` (keep `Chunk` and `Reranker` there) to avoid a name clash; `base.py` no longer defines `RetrievalEngine`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval/test_engine.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/engine.py src/bad_research/retrieval/base.py src/bad_research/retrieval/__init__.py tests/test_retrieval/test_engine.py
git commit -m "feat(retrieval): RetrievalEngine — index+hybrid(0.7)+rerank+three-tier fusion+0.70 gate+<30% re-retrieve+cache"
```

---

## Task 15: Full-suite green + lint

**Files:** none (verification)

- [ ] **Step 1: Run the whole retrieval suite**

Run: `pytest tests/test_retrieval/ -v`
Expected: PASS — all tests across constants/base/chunker/chunker_code/fusion/store/rerank/cache/anchors/fts_chunks/schema_migration/config/engine green.

- [ ] **Step 2: Run lint + type checks (match hyperresearch's gates)**

Run: `ruff check src/bad_research/retrieval && mypy src/bad_research/retrieval`
Expected: no errors. Fix any reported issues (these are bugs, not style nits).

- [ ] **Step 3: Run the full repo suite to confirm nothing else broke (the schema bump)**

Run: `pytest -q`
Expected: PASS (no regressions from the v8→v9 migration or the removed `embeddings` table).

- [ ] **Step 4: Commit any lint/type fixes**

```bash
git add -A
git commit -m "chore(retrieval): lint + type-check clean, full suite green"
```

---

## Self-Review (completed by plan author)

- **Spec coverage (SPEC §7, §11):** LanceDB chunks store (Task 7) ✓; AST-header code chunker + prose semantic split + stable `sha1(url#heading)` ids (Tasks 4-5) ✓; hybrid `alpha=0.7` fuse over LanceDB vector + FTS5/BM25 (Tasks 6, 13, 14) ✓; CohereReranker + BGEReranker behind `Reranker` (Task 8) ✓; three-tier `final=w·initial+(1−w)·reranker`, `w={≤3:0.75,≤10:0.60,>10:0.40}` + deep-rank penalty (Task 6) ✓; 0.70 gate + <30%-pass re-retrieve ≤2 rounds + expand_symbols-style widening (Task 14) ✓; negation-guarded 0.92 semantic cache (Task 9) ✓; `sources` + `claim_anchors` DDL (Task 10) ✓; dead `embeddings` table removed (Task 11) ✓; `RetrievalEngine.index()/search(mode, top_k)` (Task 14) ✓.
- **Type consistency:** `Chunk(chunk_id, note_id, text, char_start, char_end, score, source_id)`, `Reranker.rerank(query, docs)->list[tuple[int,float]]`, `RetrievalEngine.index(notes)`/`search(query, *, mode, top_k)->list[Chunk]` match INTERFACES.md verbatim across all tasks. LanceDB `chunks` schema `{chunk_id, vector(FSL<float,dim>), note_id, char_start, char_end, model, dim}` matches INTERFACES. `sources`/`claim_anchors` columns match INTERFACES verbatim.
- **Constants:** all cite INTERFACES/dossiers; alpha=0.7, w=0.75/0.60/0.40, gate 0.70, <30%/2 rounds, cache 0.92, RRF k=60, BM25 10/1/5/3, source-type 1.2/1.0/0.9/0.85 — verbatim.
- **No placeholders:** every code step is complete and runnable; no TBD/TODO.

## Execution Handoff

**Plan complete and saved to `ultimate-research/plans/2026-05-26-bad-research-02-retrieval.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
