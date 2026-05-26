# Bad Research — KR-5: Keyless Retrieval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect `src/bad_research/retrieval/` to a keyless default — FTS5/BM25 recall → host-model `ClaudeCodeReranker` (the verbatim LLM-rerank prompt) → three-tier fusion → 0.70 gate → `<30%`-pass wiki-link re-retrieve → token-set `LexicalCacheBackend` — with the LanceDB vector store and local neural models (`BgeLocalEmbedProvider`, `ms-marco` cross-encoder) demoted behind a `[local]` extra that is use-if-present and auto-activates above 25k chunks. **Zero third-party API keys; no mandatory local model.**

**Architecture:** `RetrievalEngine.__init__` flips to `embedder: EmbedProvider | None = None` (None ⇒ FTS-only recall, the keyless default) and `lance_dir: Path | None = None` (None unless a `[local]` neural lane is on). The fusion math (`hybrid_fuse α=0.7`, `three_tier_fuse 0.75/0.60/0.40` + `0.005` deep penalty, `apply_source_type_weight`, `rrf_merge k=60`) and the FTS chunk lane and chunkers are **kept verbatim** — only the recall source and the reranker swap. `CohereReranker` is deleted; `ClaudeCodeReranker` (one batched host-model call, pointwise 0..1 JSON scorer, the frozen prompt with an injection preamble, graceful `0.0` on parse failure) becomes the default. The semantic cache gains a `LexicalCacheBackend` (token-set overlap-coefficient, threshold `0.85`) selected when `embedder is None`; the existing `0.92`-cosine `SemanticCache` is used only when a `[local]` bi-encoder is resident. LanceDB (`store.py`) and `BgeLocalEmbedProvider` (`embed/bge_local.py`) sit behind import-guards so the default test run and the default install need no `torch`/`lancedb`.

**Tech Stack:** Python 3.11+, SQLite FTS5 (compiled into stdlib `sqlite3`, keyless), pure-Python fusion arithmetic, the host LLM seam (`bad_research.llm.base.LLMProvider`) for the rerank call, pytest with `math.isclose`. A `FakeLLMProvider` test double exercises `ClaudeCodeReranker` (no network, no key). The `[local]` lane (`sentence-transformers` + `torch` + `lancedb` + `pyarrow`) is import-guarded; its tests carry a `local` marker and skip when the deps are absent.

---

## What this plan binds to (read before starting)

- **Frozen contract:** `docs/INTERFACES_KEYLESS.md` — especially §5 (retrieval seams), §5.1 the FTS-default `RetrievalEngine` signature, §5.3 the `ClaudeCodeReranker` default + the frozen LLM-rerank prompt, §5.4 `BgeLocalEmbedProvider` behind `[local]`, §5.5 the `LexicalCacheBackend` (0.85), §5.6 the new constants, §8 the frozen-constants table.
- **Spec dossier:** `docs/investigation/15_KEYLESS_RETRIEVAL.md` — §2 FTS lane, §3 fusion math (kept), §4 the optional local bi-encoder + the 25k threshold, §5 the rerank decision (host-model default, the verbatim §5.3 prompt), §6 the lexical/cosine cache, §7 gate/re-retrieve/`expand_symbols`/cascade, §8 the no-overkill wiring + §8.3 the minimal diff.
- **Outline:** `docs/KEYLESS_REBUILD_PLAN_OUTLINE.md` KR-5 section.
- **KR-1 ordering:** KR-1 is the foundation pass — it deletes `embed/cohere.py` + `retrieval/rerank.py::CohereReranker`, slims `pyproject.toml`, rewrites `config.py` (adds `reranker`/`neural_recall`/`searxng_endpoint`/`browse_engine`/`effort`/`max_tokens`, drops the Cohere `embed_model`/`rerank_model`), rewrites `providers.py`, and rewires `web/base.py::get_provider`. **This plan does NOT assume KR-1 has landed** — every task is written so it works whether or not KR-1 ran first. Where a KR-1 change overlaps this plan's scope (the Cohere deletion, the config knobs, the `get_reranker` factory, the `get_embed_provider` default, the `pyproject` `[local]` extra), this plan performs it idempotently (delete-if-present / add-if-missing) so the two plans converge on the same end state without conflict.

**Labelling convention (per the cross-plan invariant):** every component is tagged **KNOWN** (verbatim from a dossier/source), **DESIGNED** (the keyless reimplementation engineered here), or **CALIBRATE** (needs the KR-7 eval). Inline in the task headers.

---

## Frozen constants (cite verbatim — never re-derive)

```python
# src/bad_research/retrieval/constants.py — KEPT (already in the file, do not touch their values)
ALPHA = 0.7                               # vector:bm25 hybrid weight                  [15 §3.2]  KNOWN
TOP_K_RETRIEVE = 30                       # candidates per query before rerank          [15 §5.4]  KNOWN
RETRIEVAL_WEIGHT = {3: 0.75, 10: 0.60}    # three-tier; default 0.40 for rank>10        [15 §3.3]  KNOWN
RETRIEVAL_WEIGHT_DEFAULT = 0.40           #                                             [15 §3.3]  KNOWN
DEEP_RANK_PENALTY = 0.005                 # ×(rank-10) for rank>10                       [15 §3.3]  KNOWN
SOURCE_TYPE_WEIGHT = {...}                # code/repo 1.2, docs/article 1.0, paper 0.9, dataset 0.85  [15 §3.4]  KNOWN
RELEVANCE_GATE = 0.70                     # drop fused chunks below this                 [15 §7.1]  KNOWN
RERETRIEVE_PASS_FRACTION = 0.30           # <30% pass → re-retrieve                      [15 §7.2]  KNOWN
RERETRIEVE_MAX_ROUNDS = 2                 # ≤2 extra rounds                              [15 §7.2]  KNOWN
SEMANTIC_CACHE_THRESHOLD = 0.92           # cosine; used only when [local] embedder on   [15 §6.1]  KNOWN
RRF_K = 60                                # reciprocal rank fusion constant              [15 §3.1]  KNOWN
BM25_BODY_WEIGHT = 1.0                    # chunk-FTS body weight                        [15 §2.1]  KNOWN

# src/bad_research/retrieval/constants.py — ADDED by this plan (Task 1)
SEMANTIC_CACHE_THRESHOLD_LEXICAL = 0.85   # token-set overlap HIT threshold              [15 §6.2]  KNOWN
NEURAL_RECALL_VAULT_THRESHOLD    = 25_000 # auto-enable the [local] dense lane           [15 §4.3]  KNOWN
LLM_RERANK_TRUNC_CHARS           = 800    # per-chunk truncation for the rerank prompt   [15 §5.3]  KNOWN
LLM_RERANK_BATCH                 = 30     # rerank the full top-30 (top-12 cascade is the budget knob)  [15 §5.3, §7.4]  KNOWN
LLM_RERANK_STOPWORDS = frozenset({"how","does","the","a","in","of","to","is","what","why"})  # lexical-cache token normalize  [15 §6.2]  KNOWN
```

---

## File Structure

`src/bad_research/retrieval/` is reworked, not rebuilt. Kept-verbatim files (`fusion.py`, `fts_chunks.py`, `chunker.py`, `chunker_code.py`, `anchors.py`, `base.py`) are **not modified** — they are the fusion math + FTS lane + chunkers the contract says to keep.

| File | Status | Responsibility after KR-5 |
|---|---|---|
| `retrieval/constants.py` | **Modify** (Task 1) | Add `SEMANTIC_CACHE_THRESHOLD_LEXICAL=0.85`, `NEURAL_RECALL_VAULT_THRESHOLD=25_000`, `LLM_RERANK_TRUNC_CHARS=800`, `LLM_RERANK_BATCH=30`, `LLM_RERANK_STOPWORDS`. Keep every existing value. |
| `retrieval/rerank.py` | **Rewrite** (Task 2, 3) | Delete `CohereReranker`. Add `ClaudeCodeReranker` (the DEFAULT — verbatim LLM-rerank prompt, host LLM seam, pointwise JSON 0..1, temp=0, ~800-char truncate, graceful 0.0). Keep `BGEReranker` import-guarded `[local]`. `get_reranker(config)` → `host`/`local`/`none`. |
| `retrieval/cache.py` | **Modify** (Task 4) | Keep `SemanticCache` (0.92-cosine) + negation guard. Add `LexicalCacheBackend` (token-set overlap-coefficient, 0.85) selected when `embedder is None`. Add `get_cache(...)` selector. |
| `retrieval/engine.py` | **Rewrite** (Task 5, 6, 7) | Constructor `embedder: EmbedProvider | None = None`, `lance_dir: Path | None = None`, `reranker: Reranker`. FTS-only recall when `embedder is None` (initial = min-max BM25); RRF k=60 fuse BM25 + dense when the lane is on. `index()` FTS-always, LanceDB only if embedder set. `expand_symbols` upgraded to wiki-link neighbors (links table). `search(query, *, mode, top_k)` signature unchanged. |
| `embed/base.py` | **Modify** (Task 8) | `get_embed_provider` default → `bge-local` (`[local]`), delete the cohere branch (idempotent). Protocol unchanged. |
| `embed/bge_local.py` | **Create** (Task 8, `[local]`) | `BgeLocalEmbedProvider(name="bge-small-en-v1.5", dim=384)`, query prefix, normalized cosine, `sentence-transformers` import-guarded. |
| `retrieval/store.py` | **Modify** (Task 9) | LanceDB import moved inside the class (lazy) so `import bad_research.retrieval.engine` works with no `lancedb` installed. Logic unchanged. |
| `pyproject.toml` | **Modify** (Task 10) | Add/confirm the `[local]` extra (`torch`, `sentence-transformers`, `lancedb`, `pyarrow`); idempotent removal of `lancedb`/`pyarrow` from core if KR-1 hasn't yet. |
| `embed/cohere.py` | **Delete** (Task 8) | Cohere embedder (key-bearing). Delete if present (KR-1 may already have). |

Tests under `tests/test_retrieval/` and `tests/test_embed/`:

| Test file | Status | Covers |
|---|---|---|
| `tests/test_retrieval/test_rerank.py` | **Rewrite** (Task 2, 3) | `ClaudeCodeReranker` prompt assembly + JSON parse + graceful 0.0 via `FakeLLMProvider`; `get_reranker` host/local/none. |
| `tests/test_retrieval/test_cache.py` | **Extend** (Task 4) | `LexicalCacheBackend` reorder/suffix HIT, paraphrase MISS, negation MISS; keep the cosine `SemanticCache` tests. |
| `tests/test_retrieval/test_engine.py` | **Rewrite** (Task 5, 6, 7) | FTS-only default path (no embedder), 0.70 gate, source-type weight, lexical-cache hit/negation-miss, wiki-link expand; the dense lane via stub embedder. |
| `tests/test_retrieval/test_fusion.py` | **Keep** | Unchanged — the fusion math is untouched; the existing `math.isclose` tests still pass. |
| `tests/test_retrieval/conftest.py` | **Extend** (Task 2) | Add `FakeLLMProvider` + `stub_links_db` fixtures. Keep `StubEmbedder`. |
| `tests/test_embed/test_bge_local.py` | **Create** (Task 8, `local` marker) | `BgeLocalEmbedProvider` shape; skipped when `sentence-transformers` absent. |
| `tests/test_retrieval/test_store.py` | **Mark** (Task 9) | Add `@pytest.mark.local` so it skips without `lancedb`. |
| `tests/test_embed/test_cohere.py` | **Delete** (Task 8) | Cohere test (mirrors the deleted module). |

`pytest.ini`/`pyproject` markers: register a `local` marker (Task 10) so `uv run python -m pytest -m "not local"` is the keyless default test command.

**Repo notes (apply to every `Run:` block):** prepend `export PATH="$HOME/.local/bin:$PATH"` to your shell; run tests with `uv run python -m pytest`; install with `uv`. Commit on the `main` branch.

---

## Task 0: Baseline — confirm the existing surface compiles and tests pass

**Files:** none (read-only baseline).

- [ ] **Step 1: Confirm branch and a green starting point for the kept fusion math**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git branch --show-current
uv run python -m pytest tests/test_retrieval/test_fusion.py -q
```
Expected: branch prints `main`; the fusion tests PASS (this is the math KR-5 keeps untouched — it is the regression anchor).

- [ ] **Step 2: Record the rerank/engine baseline (these WILL change)**

Run:
```bash
uv run python -m pytest tests/test_retrieval/test_rerank.py tests/test_retrieval/test_engine.py -q || true
```
Expected: PASS today (they target `CohereReranker` + the LanceDB engine). After this plan they are rewritten; this step just confirms the starting state so a mid-plan failure is attributable.

- [ ] **Step 3: No commit** — read-only baseline.

---

## Task 1: Add the KR-5 retrieval constants  [KNOWN — INTERFACES_KEYLESS §5.6 / dossier 15 §6.2, §4.3, §5.3]

**Files:**
- Modify: `src/bad_research/retrieval/constants.py`
- Test: `tests/test_retrieval/test_constants.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retrieval/test_constants.py`:
```python
def test_kr5_keyless_constants_present_and_exact():
    from bad_research.retrieval import constants as C
    # dossier 15 §6.2 — token-set lexical cache threshold (looser than the 0.92 cosine).
    assert C.SEMANTIC_CACHE_THRESHOLD_LEXICAL == 0.85
    # dossier 15 §4.3 — auto-enable the [local] dense lane above this chunk count.
    assert C.NEURAL_RECALL_VAULT_THRESHOLD == 25_000
    # dossier 15 §5.3 — per-chunk truncation for the rerank prompt + the full top-30 batch.
    assert C.LLM_RERANK_TRUNC_CHARS == 800
    assert C.LLM_RERANK_BATCH == 30
    # The kept cosine threshold must still be 0.92 (used only under [local]).
    assert C.SEMANTIC_CACHE_THRESHOLD == 0.92
    # Stopwords for lexical-cache token normalization (dossier 15 §6.2).
    assert "how" in C.LLM_RERANK_STOPWORDS and "async" not in C.LLM_RERANK_STOPWORDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_retrieval/test_constants.py::test_kr5_keyless_constants_present_and_exact -v`
Expected: FAIL with `AttributeError: module 'bad_research.retrieval.constants' has no attribute 'SEMANTIC_CACHE_THRESHOLD_LEXICAL'`.

- [ ] **Step 3: Add the constants**

In `src/bad_research/retrieval/constants.py`, after the existing `SEMANTIC_CACHE_THRESHOLD = 0.92` / `NEGATION_PATTERN = ...` block, add:
```python
# ── KR-5 keyless retrieval (INTERFACES_KEYLESS §5.6, dossier 15) ─────────────
SEMANTIC_CACHE_THRESHOLD_LEXICAL = 0.85   # token-set overlap HIT (no embedder)  [15 §6.2]
NEURAL_RECALL_VAULT_THRESHOLD = 25_000    # auto-enable the [local] dense lane    [15 §4.3]
LLM_RERANK_TRUNC_CHARS = 800              # truncate each chunk for the rerank prompt  [15 §5.3]
LLM_RERANK_BATCH = 30                     # rerank the full top-30 (top-12 cascade = budget knob)  [15 §5.3, §7.4]
# Tiny stopword set for the lexical-cache token normalizer (dossier 15 §6.2).
LLM_RERANK_STOPWORDS = frozenset(
    {"how", "does", "the", "a", "in", "of", "to", "is", "what", "why"}
)
```
Do NOT change any existing value.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_retrieval/test_constants.py -v`
Expected: PASS (the new test + the existing constant tests).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/constants.py tests/test_retrieval/test_constants.py
git commit -m "feat(retrieval): add KR-5 keyless constants (lexical cache 0.85, neural-recall 25k, rerank trunc/batch)"
```

---

## Task 2: Test scaffolding — `FakeLLMProvider` + the `ClaudeCodeReranker` prompt/parse contract  [DESIGNED — dossier 15 §5.3]

**Files:**
- Modify: `tests/test_retrieval/conftest.py`
- Test: `tests/test_retrieval/test_rerank.py` (rewrite)

This task installs the test double and the first `ClaudeCodeReranker` behavior (prompt assembly + JSON parse). The implementation lands in Step 3.

- [ ] **Step 1: Add `FakeLLMProvider` to conftest**

Append to `tests/test_retrieval/conftest.py`:
```python
from bad_research.llm.base import LLMMessage, LLMResponse


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
```
(The existing `import pytest` at the top of conftest already covers the `@pytest.fixture` decorator.)

- [ ] **Step 2: Replace `tests/test_retrieval/test_rerank.py` with the keyless contract**

Overwrite `tests/test_retrieval/test_rerank.py` entirely:
```python
import json

import pytest

from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import ClaudeCodeReranker, get_reranker
from tests.test_retrieval.conftest import FakeLLMProvider


def test_claude_code_reranker_is_a_reranker():
    rr = ClaudeCodeReranker(llm=FakeLLMProvider(reply_text="[]"))
    assert isinstance(rr, Reranker)


def test_reranker_returns_empty_for_no_docs():
    rr = ClaudeCodeReranker(llm=FakeLLMProvider(reply_text="[]"))
    assert rr.rerank("q", []) == []


def test_prompt_contains_query_rubric_and_numbered_chunks():
    llm = FakeLLMProvider(reply_text='[{"i":1,"s":0.0},{"i":2,"s":1.0}]')
    rr = ClaudeCodeReranker(llm=llm)
    rr.rerank("why did they pick alpha=0.7", ["irrelevant text", "alpha=0.7 explained here"])
    # One batched call (dossier 15 §5.3 — all candidates in ONE host-model call).
    assert len(llm.calls) == 1
    sysmsg = llm.calls[0]["messages"][0]
    usermsg = llm.calls[0]["messages"][1]
    assert sysmsg.role == "system"
    # The frozen rubric anchors (verbatim from the §5.3 prompt).
    assert "relevance reranker" in sysmsg.content
    assert "0.0–1.0 scale" in sysmsg.content or "0.0-1.0 scale" in sysmsg.content
    assert '[{"i": <chunk number>, "s": <score 0.0-1.0>}, ...]' in sysmsg.content
    # The user message carries the query + 1-based numbered chunks.
    assert "QUERY: why did they pick alpha=0.7" in usermsg.content
    assert "[1]" in usermsg.content and "[2]" in usermsg.content
    # Determinism: temperature=0 (dossier 15 §5.3).
    assert llm.calls[0]["temperature"] == 0


def test_scores_parsed_and_returned_descending():
    # Two chunks; the host says chunk 2 (index 1) is the most relevant.
    llm = FakeLLMProvider(reply_text='[{"i":1,"s":0.10},{"i":2,"s":0.90}]')
    rr = ClaudeCodeReranker(llm=llm)
    out = rr.rerank("q", ["a", "b"])
    assert out[0] == (1, 0.90)
    assert out[1] == (0, 0.10)


def test_chunks_truncated_to_trunc_chars_in_prompt():
    from bad_research.retrieval.constants import LLM_RERANK_TRUNC_CHARS
    llm = FakeLLMProvider(reply_text='[{"i":1,"s":0.5}]')
    rr = ClaudeCodeReranker(llm=llm)
    long_doc = "x" * (LLM_RERANK_TRUNC_CHARS + 500)
    rr.rerank("q", [long_doc])
    usermsg = llm.calls[0]["messages"][1].content
    # The 500 overflow chars never reach the prompt.
    assert ("x" * (LLM_RERANK_TRUNC_CHARS + 1)) not in usermsg
    assert ("x" * LLM_RERANK_TRUNC_CHARS) in usermsg
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_retrieval/test_rerank.py -v`
Expected: FAIL with `ImportError: cannot import name 'ClaudeCodeReranker' from 'bad_research.retrieval.rerank'` (and `CohereReranker` may still be importable — that's fine, it's deleted in Step 4 of the next task).

- [ ] **Step 4: No commit yet** — the implementation lands in Task 3; commit there with the passing tests.

---

## Task 3: Implement `ClaudeCodeReranker` (the default) + `get_reranker` host/local/none  [KNOWN prompt §5.3 / DESIGNED host-seam wiring]

**Files:**
- Rewrite: `src/bad_research/retrieval/rerank.py`
- Test: `tests/test_retrieval/test_rerank.py` (from Task 2) + add the `get_reranker` cases below.

- [ ] **Step 1: Add the `get_reranker` host/local/none tests**

Append to `tests/test_retrieval/test_rerank.py`:
```python
def test_get_reranker_default_host_returns_claude_code(monkeypatch):
    class _Cfg:
        reranker = "host"
    rr = get_reranker(_Cfg(), llm=FakeLLMProvider(reply_text="[]"))
    assert isinstance(rr, ClaudeCodeReranker)


def test_get_reranker_none_is_identity_sort_by_input_order():
    class _Cfg:
        reranker = "none"
    rr = get_reranker(_Cfg())
    # "none" → identity: every doc scores 1.0, input order preserved (the --no-rerank floor, §5.1).
    out = rr.rerank("q", ["a", "b", "c"])
    assert [i for i, _ in out] == [0, 1, 2]
    assert all(s == 1.0 for _, s in out)


def test_get_reranker_local_lazy_imports_bge(monkeypatch):
    # "local" must NOT import torch at factory time when a scorer is injected (test-only path).
    class _Cfg:
        reranker = "local"
    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    out = rr.rerank("q", ["a", "b"])
    assert len(out) == 2
    # Stable tie-break by ascending index.
    assert [i for i, _ in out] == [0, 1]


def test_malformed_json_degrades_each_missing_chunk_to_zero():
    # Host returns a score only for chunk 1; chunk 2 missing → 0.0 (graceful, §5.3).
    llm = FakeLLMProvider(reply_text='[{"i":1,"s":0.8}]')
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b"]))
    assert out[0] == 0.8
    assert out[1] == 0.0


def test_entire_call_unparseable_returns_all_zero():
    # Whole reply is junk → every chunk 0.0 (engine then leans on `initial`, §5.3).
    llm = FakeLLMProvider(reply_text="sorry, I can't do that")
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b", "c"]))
    assert out == {0: 0.0, 1: 0.0, 2: 0.0}


def test_json_inside_markdown_fence_is_still_parsed():
    # Robustness: the model wraps the array in a ```json fence despite the instruction.
    llm = FakeLLMProvider(reply_text='```json\n[{"i":1,"s":0.4},{"i":2,"s":0.6}]\n```')
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b"]))
    assert out[0] == 0.4 and out[1] == 0.6
```

- [ ] **Step 2: Run to verify the new cases fail**

Run: `uv run python -m pytest tests/test_retrieval/test_rerank.py -v`
Expected: FAIL — `ClaudeCodeReranker`/`get_reranker(reranker=...)` not implemented yet.

- [ ] **Step 3: Rewrite `src/bad_research/retrieval/rerank.py`**

Overwrite the whole file:
```python
"""Rerankers behind the Reranker Protocol — KEYLESS.

Default: ClaudeCodeReranker — the host model (no API key) scores each candidate
0..1 with the verbatim LLM-rerank prompt (dossier 15 §5.3). One batched call,
pointwise JSON output, temperature=0, ~800-char truncation, graceful 0.0 on any
parse failure. Drop-in for the Reranker Protocol; feeds three_tier_fuse exactly
as Cohere's score did.

Offline ([local] extra): BGEReranker — local cross-encoder (ms-marco-MiniLM by
default for the keyless `reranker="local"` flag, dossier 15 §5.2). torch is
imported lazily, only when a scorer is constructed.

Floor: the identity reranker (reranker="none") — every doc scores 1.0, input
order preserved (the --no-rerank speed/zero-token fallback, §5.1).

NO Cohere. NO mandatory local model.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from bad_research.llm.base import LLMMessage
from bad_research.retrieval.constants import LLM_RERANK_TRUNC_CHARS

# A local cross-encoder scorer: maps [(query, doc)] -> [relevance_score].
Scorer = Callable[[list[tuple[str, str]]], list[float]]

# ── The frozen LLM-rerank prompt (dossier 15 §5.3, INTERFACES_KEYLESS §5.3) ──
# VERBATIM. Shared with web/search/rerank.py::HostModelReranker (search vs vault
# candidates — same prompt). The injection preamble (quality/injection.py) is
# prepended by the engine wiring; the rubric below is the rerank contract.
LLM_RERANK_SYSTEM = (
    "You are a relevance reranker. Given a research QUERY and a numbered list of\n"
    "candidate text CHUNKS, score each chunk's relevance to the query on a 0.0–1.0\n"
    "scale. Relevance means: does this chunk contain information that directly helps\n"
    "ANSWER or EXPLAIN the query — not merely mention its keywords.\n"
    "\n"
    "Scoring rubric (be calibrated, use the full range):\n"
    "  1.0  = directly and completely answers/explains the query\n"
    "  0.7  = strongly relevant; contains a key part of the answer\n"
    "  0.4  = tangentially relevant; mentions the topic but not the answer\n"
    "  0.1  = same general domain, wrong specific subject\n"
    "  0.0  = unrelated\n"
    "\n"
    "Output ONLY a JSON array of objects, one per chunk, in input order:\n"
    '[{"i": <chunk number>, "s": <score 0.0-1.0>}, ...]\n'
    "No prose, no markdown fence, no explanation."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _build_user_message(query: str, docs: list[str]) -> str:
    lines = [f"QUERY: {query}", "", "CHUNKS:"]
    for n, doc in enumerate(docs, start=1):
        lines.append(f"[{n}] {doc[:LLM_RERANK_TRUNC_CHARS]}")
    return "\n".join(lines)


def _parse_scores(text: str, n_docs: int) -> dict[int, float]:
    """Parse the host reply into {doc_index0 -> score}. Pointwise + graceful:
    any chunk missing or unparseable defaults to 0.0 (dossier 15 §5.3)."""
    out = {i: 0.0 for i in range(n_docs)}
    m = _JSON_ARRAY_RE.search(text or "")
    if not m:
        return out
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return out
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx1 = int(item["i"])
            score = float(item["s"])
        except (KeyError, TypeError, ValueError):
            continue
        idx0 = idx1 - 1  # the prompt numbers chunks 1-based.
        if 0 <= idx0 < n_docs:
            out[idx0] = max(0.0, min(1.0, score))
    return out


class ClaudeCodeReranker:
    """The DEFAULT keyless reranker — the host model scores candidates 0..1.

    `llm` is any LLMProvider (bad_research.llm.base). The skill path supplies the
    host model; the headless/calibration path supplies AnthropicProvider. No key
    is read here — the provider owns that."""

    def __init__(self, *, llm: Any, tier: str = "work",
                 injection_preamble: str = ""):
        self._llm = llm
        self._tier = tier
        self._preamble = injection_preamble

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        system = (self._preamble + "\n\n" + LLM_RERANK_SYSTEM) if self._preamble else LLM_RERANK_SYSTEM
        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=_build_user_message(query, docs)),
        ]
        try:
            resp = self._llm.complete(messages, tier=self._tier, temperature=0,
                                      max_tokens=2048)
            scores = _parse_scores(resp.text, len(docs))
        except Exception:  # noqa: BLE001 — the whole call failing must not crash retrieval (§5.3)
            scores = {i: 0.0 for i in range(len(docs))}
        scored = list(scores.items())
        scored.sort(key=lambda x: (-x[1], x[0]))  # desc by score, stable by index
        return scored


class _IdentityReranker:
    """The --no-rerank floor (dossier 15 §5.1): every doc 1.0, input order kept."""

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        return [(i, 1.0) for i in range(len(docs))]


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
        import math

        from sentence_transformers import CrossEncoder  # type: ignore

        ce = CrossEncoder(repo)
        return lambda pairs: [1.0 / (1.0 + math.exp(-float(s))) for s in ce.predict(pairs)]


class BGEReranker:
    """Local cross-encoder ([local]). Default model is the LIGHT ms-marco MiniLM
    (dossier 15 §5.2 — not the 560 MB m3) for the keyless `reranker="local"`."""

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
                 bge_scorer: Scorer | None = None) -> Any:
    """Keyless reranker factory (INTERFACES_KEYLESS §5.3):
      "host"  → ClaudeCodeReranker (default; host model, no key)
      "local" → BGEReranker(ms-marco-MiniLM-L-6-v2) ([local] extra)
      "none"  → _IdentityReranker (the --no-rerank floor)
    `config.reranker` selects; falls back to "host"."""
    choice = getattr(config, "reranker", "host")
    if choice == "none":
        return _IdentityReranker()
    if choice == "local":
        return BGEReranker(scorer=bge_scorer)
    # "host" (default): ClaudeCodeReranker needs a host LLM provider.
    if llm is None:
        from bad_research.llm.base import get_llm_provider

        llm = get_llm_provider("anthropic", config=config) if hasattr(config, "model_tiers") \
            else get_llm_provider("anthropic")
    return ClaudeCodeReranker(llm=llm)
```

- [ ] **Step 4: Delete `CohereReranker` (already done — the rewrite drops it)**

Confirm no Cohere reference survives:
```bash
grep -n "Cohere\|cohere" src/bad_research/retrieval/rerank.py || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 5: Run the rerank tests**

Run: `uv run python -m pytest tests/test_retrieval/test_rerank.py -v`
Expected: PASS (all Task 2 + Task 3 cases). Note `test_get_reranker_default_host_returns_claude_code` passes because `llm=FakeLLMProvider(...)` is injected — no `anthropic`/key is touched.

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/retrieval/rerank.py tests/test_retrieval/test_rerank.py tests/test_retrieval/conftest.py
git commit -m "feat(retrieval): ClaudeCodeReranker (host-model LLM-rerank, verbatim prompt) replaces Cohere; get_reranker host/local/none"
```

---

## Task 4: `LexicalCacheBackend` (token-set overlap 0.85) + cache selector  [KNOWN math §6.2 / DESIGNED selector]

**Files:**
- Modify: `src/bad_research/retrieval/cache.py`
- Test: `tests/test_retrieval/test_cache.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retrieval/test_cache.py`:
```python
def test_lexical_cache_hit_on_token_reorder(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("python async concurrency patterns", {"answer": "A"})
    # Same token set, reordered → overlap 1.0 → HIT (dossier 15 §6.2, NIA 0.9701 case).
    hit = cache.get("concurrency patterns python async")
    assert hit is not None and hit["payload"] == {"answer": "A"}


def test_lexical_cache_hit_on_suffix_noise(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("binary quantization memory", {"answer": "B"})
    # Superset query (extra tokens) → overlap-coefficient ignores the larger side → HIT
    # (matches NIA's +9-token suffix-noise 0.9242 case).
    hit = cache.get("binary quantization memory reduction sixteen times faster lookup")
    assert hit is not None and hit["payload"] == {"answer": "B"}


def test_lexical_cache_miss_on_paraphrase(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("how to cut vector RAM", {"answer": "C"})
    # Zero content-token overlap → MISS (just re-runs, never a wrong answer; §6.2).
    assert cache.get("binary quantization reduced memory sixteen fold") is None


def test_lexical_cache_miss_when_negation_added(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("does it support async in no_std", {"answer": "yes"})
    # The negation guard forces a miss even if the token overlap clears 0.85 (§6.2 belt-and-suspenders).
    assert cache.get("does it NOT support async in no_std") is None


def test_get_cache_selects_lexical_when_no_embedder(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend, get_cache
    cache = get_cache(tmp_path / "c.db", embedder=None)
    assert isinstance(cache, LexicalCacheBackend)


def test_get_cache_selects_cosine_when_embedder_present(tmp_path, stub_embedder):
    from bad_research.retrieval.cache import SemanticCache, get_cache
    cache = get_cache(tmp_path / "c.db", embedder=stub_embedder)
    assert isinstance(cache, SemanticCache)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_retrieval/test_cache.py -v`
Expected: FAIL — `cannot import name 'LexicalCacheBackend'` / `'get_cache'`.

- [ ] **Step 3: Add `LexicalCacheBackend` + `get_cache` to `cache.py`**

Append to `src/bad_research/retrieval/cache.py` (keep `SemanticCache` and `has_negation` exactly as they are):
```python
from bad_research.retrieval.constants import (  # noqa: E402  (grouped with existing imports at top in practice)
    LLM_RERANK_STOPWORDS,
    SEMANTIC_CACHE_THRESHOLD_LEXICAL,
)
from bad_research.search.fts import preprocess_query  # noqa: E402


_LEX_DDL = """
CREATE TABLE IF NOT EXISTS query_cache_lex (
    query_text   TEXT PRIMARY KEY,
    tokens       TEXT NOT NULL,   -- json sorted list[str]
    has_negation INTEGER NOT NULL,
    payload      TEXT NOT NULL,   -- json
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _normalize_tokens(query: str) -> frozenset[str]:
    """Lowercase, strip FTS markers, drop the tiny stopword set (dossier 15 §6.2)."""
    raw = preprocess_query(query).replace('"', "").replace("*", "")
    toks = (w.lower() for w in raw.split())
    return frozenset(t for t in toks if t and t not in LLM_RERANK_STOPWORDS)


def _token_sim(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap coefficient: |a∩b| / min(|a|,|b|). Recall-biased so suffix noise
    on the larger side still scores high (dossier 15 §6.2)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class LexicalCacheBackend:
    """Keyless token-set semantic cache (dossier 15 §6.2). HIT at overlap ≥ 0.85
    with the negation guard. Catches reorder + suffix-noise; misses true
    paraphrase (which just re-runs — never a wrong answer). Same get/put surface
    as SemanticCache."""

    def __init__(self, db_path: Path,
                 *, threshold: float = SEMANTIC_CACHE_THRESHOLD_LEXICAL):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_LEX_DDL)
        self.conn.commit()

    def get(self, query: str) -> dict[str, Any] | None:
        q_tokens = _normalize_tokens(query)
        q_neg = has_negation(query)
        best = None
        best_sim = -1.0
        for row in self.conn.execute(
            "SELECT query_text, tokens, has_negation, payload FROM query_cache_lex"
        ):
            cached = frozenset(json.loads(row["tokens"]))
            sim = _token_sim(q_tokens, cached)
            if sim > best_sim:
                best_sim, best = sim, row
        if best is None or best_sim < self.threshold:
            return None
        # Negation guard (same as SemanticCache): disagreement on negation → MISS.
        if q_neg != bool(best["has_negation"]):
            return None
        return {"payload": json.loads(best["payload"]),
                "cache_similarity": best_sim,
                "original_query": best["query_text"]}

    def put(self, query: str, payload: dict[str, Any]) -> None:
        tokens = sorted(_normalize_tokens(query))
        self.conn.execute(
            "INSERT OR REPLACE INTO query_cache_lex "
            "(query_text, tokens, has_negation, payload) VALUES (?, ?, ?, ?)",
            (query, json.dumps(tokens), int(has_negation(query)), json.dumps(payload)),
        )
        self.conn.commit()


def get_cache(db_path: Path, *, embedder: Any = None) -> Any:
    """Select the cache backend (INTERFACES_KEYLESS §5.5): token-set lexical when
    no embedder (the keyless default), cosine 0.92 when a [local] bi-encoder is
    resident."""
    if embedder is None:
        return LexicalCacheBackend(Path(db_path))
    return SemanticCache(Path(db_path), embedder)
```
Move the two new `from ... import` lines up into the existing import block at the top of the file (next to `from bad_research.embed.base import EmbedProvider`) to satisfy `ruff` — the `# noqa: E402` markers above are only there to document where they go; placing them at the top makes the noqa unnecessary. Add `from typing import Any` if not already imported (it is, in the existing header).

- [ ] **Step 4: Run to verify the cache tests pass**

Run: `uv run python -m pytest tests/test_retrieval/test_cache.py -v`
Expected: PASS — the new `LexicalCacheBackend`/`get_cache` cases AND the existing `SemanticCache` cosine + negation tests (untouched).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/cache.py tests/test_retrieval/test_cache.py
git commit -m "feat(retrieval): LexicalCacheBackend (token-set overlap 0.85) + get_cache selector; cosine 0.92 stays for [local]"
```

---

## Task 5: `RetrievalEngine` — FTS-only default path (no embedder)  [DESIGNED — INTERFACES_KEYLESS §5.1, §5.2]

**Files:**
- Rewrite: `src/bad_research/retrieval/engine.py`
- Test: `tests/test_retrieval/test_engine.py` (rewrite)

This is the core swap: `embedder=None` ⇒ FTS5/BM25 recall, min-max-normed BM25 as `initial_score`, `ClaudeCodeReranker` over the top-30, three-tier fuse, 0.70 gate, `<30%` re-retrieve, lexical cache. No LanceDB constructed.

- [ ] **Step 1: Rewrite `tests/test_retrieval/test_engine.py` for the keyless default**

Overwrite `tests/test_retrieval/test_engine.py`:
```python
import json

from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.base import Reranker
from bad_research.retrieval.engine import RetrievalEngine
from bad_research.retrieval.rerank import ClaudeCodeReranker
from tests.test_retrieval.conftest import FakeLLMProvider


class _RubricLLM:
    """A FakeLLMProvider-shaped host that scores by query-token overlap so the
    rerank is deterministic without a real model. Returns the §5.3 JSON shape."""
    name = "rubric"

    def __init__(self):
        self.calls = []

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        from bad_research.llm.base import LLMResponse
        self.calls.append(messages)
        user = messages[1].content
        # Parse the "[n] text" chunk lines back out of the user message.
        items = []
        for line in user.splitlines():
            if line.startswith("[") and "]" in line:
                n = int(line[1:line.index("]")])
                body = line[line.index("]") + 1:].strip().lower()
                qtoks = set(messages[1].content.split("QUERY: ")[1].splitlines()[0].lower().split())
                hit = bool(qtoks & set(body.split()))
                items.append({"i": n, "s": 0.95 if hit else 0.10})
        return LLMResponse(text=json.dumps(items), tool_calls=[], usage={}, model="rubric")


def _note(nid, body, ct=None, status="evergreen"):
    return Note(meta=NoteMeta(title=nid, id=nid, source=f"https://ex.com/{nid}",
                              content_type=ct, status=status),
                body=body, path=f"research/{nid}.md")


def _fts_engine(tmp_path, llm=None):
    """The KEYLESS DEFAULT: embedder=None, lance_dir=None → FTS-only recall."""
    rr = ClaudeCodeReranker(llm=llm or _RubricLLM())
    return RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)


def test_engine_default_has_no_embedder_and_no_lance(tmp_path):
    eng = _fts_engine(tmp_path)
    assert eng.embedder is None
    assert eng.store is None  # no LanceDB constructed on the keyless path.


def test_reranker_protocol_satisfied(tmp_path):
    eng = _fts_engine(tmp_path)
    assert isinstance(eng.reranker, Reranker)


def test_fts_only_index_then_search_returns_relevant_chunk_first(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([
        _note("a", "# A\n\npython async await concurrency patterns explained\n"),
        _note("b", "# B\n\nrust ownership borrow checker lifetimes memory\n"),
    ])
    hits = eng.search("python async", mode="light", top_k=2)
    assert len(hits) >= 1
    assert hits[0].note_id == "a"
    assert hits[0].char_end > hits[0].char_start


def test_relevance_gate_drops_low_scoring_chunks(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await\n"),
               _note("z", "# Z\n\ntotally unrelated zebra xylophone\n")])
    hits = eng.search("python async", mode="light", top_k=10)
    assert all(h.score >= 0.70 for h in hits)


def test_source_type_weight_boosts_code(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("code", "def parse_async(): return async_io_loop()\n" * 80, ct="code"),
               _note("docs", "parse async io loop documentation prose\n" * 80, ct="docs")])
    hits = eng.search("parse async", mode="full", top_k=2)
    by_note = {h.note_id: h.score for h in hits}
    if "code" in by_note and "docs" in by_note:
        assert by_note["code"] >= by_note["docs"]


def test_lexical_cache_hit_on_repeat_query(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    first = eng.search("python async concurrency", mode="light", top_k=3)
    eng.search("python async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is True
    second = eng.search("concurrency async python", mode="light", top_k=3)  # reorder → lexical HIT
    assert eng.last_cache_hit is True
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_lexical_cache_miss_when_negation_added(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    eng.search("python async concurrency", mode="light", top_k=3)
    eng.search("python NOT async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_retrieval/test_engine.py -v`
Expected: FAIL — the current `RetrievalEngine.__init__` still requires `lance_dir` + `embedder` (no `embedder=None` default, no `.store is None` path).

- [ ] **Step 3: Rewrite `src/bad_research/retrieval/engine.py`**

Overwrite the whole file:
```python
"""Keyless RetrievalEngine (INTERFACES_KEYLESS §5).

Default path (embedder is None): FTS5/BM25 recall → min-max-normed BM25 as
initial_score → ClaudeCodeReranker over top-30 → three_tier_fuse → 0.70 gate →
<30%-pass wiki-link re-retrieve → token-set LexicalCacheBackend. Zero API key,
zero local model.

Optional dense lane ([local] extra, embedder set): also embeds chunks into
LanceDB; recall = RRF k=60 over (BM25 ranks, bi-encoder ranks); cache = cosine
0.92 reusing the resident bi-encoder. Auto-enabled above NEURAL_RECALL_VAULT_
THRESHOLD chunks by the CLI builder (this engine just honors whatever embedder
it is handed).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from bad_research.embed.base import EmbedProvider
from bad_research.models.note import Note
from bad_research.retrieval.base import Chunk, Reranker
from bad_research.retrieval.cache import get_cache
from bad_research.retrieval.chunker import chunk_note
from bad_research.retrieval.chunker_code import embed_text_for
from bad_research.retrieval.constants import (
    ALPHA,
    EMBED_BATCH_CAP,
    EMBED_TRUNC_CHARS,
    RELEVANCE_GATE,
    RERETRIEVE_MAX_ROUNDS,
    RERETRIEVE_PASS_FRACTION,
    RRF_K,
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
    minmax_normalize,
    rrf_merge,
    three_tier_fuse,
)


class _ChunkMeta:
    __slots__ = ("chunk", "content_type")

    def __init__(self, chunk: Chunk, content_type: str | None):
        self.chunk = chunk
        self.content_type = content_type


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
        # Vector store: ONLY when a [local] embedder is supplied. Lazy import so
        # the keyless default never touches lancedb.
        self.store: Any | None = None
        if embedder is not None:
            from bad_research.retrieval.store import LanceChunkStore

            store_dir = Path(lance_dir) if lance_dir is not None \
                else Path(cache_db).with_name("lance")
            self.store = LanceChunkStore(store_dir, dim=embedder.dim)
        # Cache backend: lexical (no embedder) | cosine 0.92 (embedder resident).
        self.cache = get_cache(Path(cache_db), embedder=embedder)
        # Chunk metadata DB (FTS lane + chunk_id→meta map), per-vault — ALWAYS on.
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
                pending.append(chunk)
                ct_for.append(ct)
                if self.embedder is not None:
                    et = embed_text_for(chunk, note) if ct == "code" else chunk.text
                    embed_texts.append(et[:EMBED_TRUNC_CHARS])
        if not pending:
            return
        fts_rows: list[dict[str, Any]] = []
        for chunk, ct in zip(pending, ct_for, strict=True):
            fts_rows.append({"chunk_id": chunk.chunk_id, "body": chunk.text,
                             "note_id": chunk.note_id})
            self._meta[chunk.chunk_id] = _ChunkMeta(chunk, ct)
        index_chunk_fts(self.conn, fts_rows)
        # Dense lane ([local] only): embed + upsert into LanceDB.
        if self.embedder is not None and self.store is not None:
            vectors: list[list[float]] = []
            for i in range(0, len(embed_texts), EMBED_BATCH_CAP):
                batch = embed_texts[i:i + EMBED_BATCH_CAP]
                vectors.extend(self.embedder.embed(batch, input_type="document"))
            rows: list[dict[str, Any]] = []
            for chunk, vec in zip(pending, vectors, strict=True):
                rows.append({"chunk_id": chunk.chunk_id, "vector": vec,
                             "note_id": chunk.note_id, "char_start": chunk.char_start,
                             "char_end": chunk.char_end, "model": self.embedder.name,
                             "dim": self.embedder.dim})
            self.store.upsert(rows)
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
            extra_ids |= self._expand_symbols(top_note)

        survivors.sort(key=lambda c: c.score, reverse=True)
        result = survivors[:top_k]
        self.cache.put(query, {"chunk_ids": [c.chunk_id for c in result]})
        return result

    def _expand_symbols(self, top_note: str | None) -> set[str]:
        """Wiki-link neighbor widening (dossier 15 §7.3): pull chunks of notes the
        top note links to / that link to it (the `links` table), plus same-note
        neighbor chunks. Pure SQL + set union — keyless. Overridden/extended in
        Task 7 to read the links table; here it is the same-note fallback so the
        FTS-only default has a widening lever even with no links DB wired."""
        if top_note is None:
            return set()
        return {cid for cid, m in self._meta.items() if m.chunk.note_id == top_note}

    def _one_round(self, query: str,
                   extra_ids: set[str]) -> tuple[list[Chunk], float, str | None]:
        bm_hits = search_chunk_fts(self.conn, query, limit=self.top_k_retrieve)
        bm_scores = dict(bm_hits)

        if self.embedder is None:
            # KEYLESS DEFAULT: initial = min-max-normed BM25, no fusion lane.
            for cid in extra_ids:
                bm_scores.setdefault(cid, 0.0)
            ids = [cid for cid in bm_scores if cid in self._meta]
            if not ids:
                return [], 0.0, None
            norm = dict(zip(ids, minmax_normalize([bm_scores[c] for c in ids]), strict=True))
            fused_initial = norm
        else:
            # DENSE LANE ([local]): RRF k=60 over BM25 ranks + bi-encoder ranks (§3.1).
            qv = self.embedder.embed([query], input_type="query")[0]
            vec_hits = self.store.search_vector(qv, top_k=self.top_k_retrieve)
            from bad_research.retrieval.store import LanceChunkStore
            vec_scores = {cid: LanceChunkStore.distance_to_score(d) for cid, d in vec_hits}
            for cid in extra_ids:
                vec_scores.setdefault(cid, 0.0)
            bm_rank = [cid for cid, _ in sorted(bm_scores.items(), key=lambda kv: kv[1], reverse=True)]
            vec_rank = [cid for cid, _ in sorted(vec_scores.items(), key=lambda kv: kv[1], reverse=True)]
            fused_initial = dict(rrf_merge(bm_rank, vec_rank, k=RRF_K))
            fused_initial = {c: s for c, s in fused_initial.items() if c in self._meta}
            if not fused_initial:
                return [], 0.0, None
            # Renormalize RRF scores into [0,1] so three_tier_fuse's blend is calibrated.
            ids = list(fused_initial)
            fused_initial = dict(zip(ids, minmax_normalize([fused_initial[c] for c in ids]), strict=True))

        ranked = sorted(fused_initial.items(), key=lambda kv: kv[1], reverse=True)
        cand_ids = [cid for cid, _ in ranked]
        docs = [self._meta[cid].chunk.text for cid in cand_ids]
        rer = dict(self.reranker.rerank(query, docs))  # idx0 → reranker_score

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


# `hybrid_fuse` (α=0.7) and `ALPHA` are imported and retained for the calibrated
# fuser path / parity tests; the default recall path uses min-max BM25 or RRF.
_ = (hybrid_fuse, ALPHA)
```

- [ ] **Step 4: Run the engine tests**

Run: `uv run python -m pytest tests/test_retrieval/test_engine.py -v`
Expected: PASS. The default path constructs no LanceDB (`eng.store is None`), uses the lexical cache (`get_cache(embedder=None)`), and reranks via the injected `_RubricLLM`.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/engine.py tests/test_retrieval/test_engine.py
git commit -m "feat(retrieval): RetrievalEngine FTS-default (embedder=None), lexical cache, host-model rerank; dense lane optional"
```

---

## Task 6: Update the engine `__init__.py` re-export + smoke-import with no `[local]` deps  [DESIGNED]

**Files:**
- Modify: `src/bad_research/retrieval/__init__.py` (only if needed)
- Test: `tests/test_retrieval/test_import_keyless.py` (create)

- [ ] **Step 1: Write the failing import-smoke test**

Create `tests/test_retrieval/test_import_keyless.py`:
```python
"""The keyless default must import with NO torch / lancedb / sentence-transformers
installed. This test asserts the retrieval package + engine + reranker + cache
import without touching any [local] dependency."""
import builtins
import importlib

import pytest


def test_retrieval_imports_without_local_deps(monkeypatch):
    blocked = {"lancedb", "pyarrow", "torch", "sentence_transformers", "FlagEmbedding"}
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        root = name.split(".")[0]
        if root in blocked:
            raise ImportError(f"blocked in keyless test: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    # Force fresh import of the package + the three reworked modules.
    for mod in ("bad_research.retrieval",
                "bad_research.retrieval.engine",
                "bad_research.retrieval.rerank",
                "bad_research.retrieval.cache"):
        importlib.reload(importlib.import_module(mod))
    from bad_research.retrieval import RetrievalEngine  # noqa: F401
    from bad_research.retrieval.rerank import ClaudeCodeReranker, get_reranker  # noqa: F401
    from bad_research.retrieval.cache import LexicalCacheBackend  # noqa: F401


def test_constructing_default_engine_needs_no_local_dep(tmp_path, monkeypatch):
    blocked = {"lancedb", "pyarrow", "torch", "sentence_transformers", "FlagEmbedding"}
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name.split(".")[0] in blocked:
            raise ImportError(f"blocked: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from bad_research.retrieval.engine import RetrievalEngine
    from bad_research.retrieval.rerank import get_reranker

    class _Cfg:
        reranker = "none"
    eng = RetrievalEngine(cache_db=tmp_path / "c.db", reranker=get_reranker(_Cfg()))
    assert eng.store is None and eng.embedder is None
```

- [ ] **Step 2: Run to verify the current state**

Run: `uv run python -m pytest tests/test_retrieval/test_import_keyless.py -v`
Expected: PASS already IF Task 5's lazy `from bad_research.retrieval.store import LanceChunkStore` (inside `__init__`/`_one_round`) is correct. If it FAILS with a blocked-import error, the engine is importing `store` at module top-level — move that import inside the `if embedder is not None:` block (it already is in the Task 5 code). The `__init__.py` re-export (`from bad_research.retrieval.engine import RetrievalEngine`) must not pull `store`.

- [ ] **Step 3: Confirm `__init__.py` is clean (no change expected)**

Read `src/bad_research/retrieval/__init__.py`; it re-exports `Chunk, Reranker, RetrievalEngine, chunk_note`. No edit needed — `engine.py` no longer imports `store` at top level after Task 5. If a stray top-level `store` import remains anywhere on the import chain, remove it.

- [ ] **Step 4: Run the full retrieval suite (keyless only)**

Run: `uv run python -m pytest tests/test_retrieval/ -v -m "not local"`
Expected: PASS (fusion, rerank, cache, engine, constants, import-keyless). `test_store.py` is gated by the `local` marker in Task 9 — it will be deselected here once Task 9 lands; until then it may error on a missing `lancedb` and that is expected to be fixed by Task 9.

- [ ] **Step 5: Commit**

```bash
git add tests/test_retrieval/test_import_keyless.py src/bad_research/retrieval/__init__.py
git commit -m "test(retrieval): keyless import-smoke — engine/reranker/cache import with no torch/lancedb"
```

---

## Task 7: `expand_symbols` upgrade — wiki-link neighbors via the `links` table  [KNOWN §7.3 / DESIGNED links-SQL]

**Files:**
- Modify: `src/bad_research/retrieval/engine.py` (the `_expand_symbols` method + constructor accepts an optional links DB)
- Modify: `tests/test_retrieval/conftest.py` (add `stub_links_db`)
- Test: `tests/test_retrieval/test_engine.py` (add the wiki-link case)

- [ ] **Step 1: Add a links-DB fixture to conftest**

Append to `tests/test_retrieval/conftest.py`:
```python
import sqlite3 as _sqlite3


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
```

- [ ] **Step 2: Add the wiki-link expand test**

Append to `tests/test_retrieval/test_engine.py`:
```python
def test_expand_symbols_pulls_wiki_link_neighbors(tmp_path, stub_links_db):
    # Note "a" links to note "b"; a low-pass first round should widen to b's chunks.
    links_path = stub_links_db([("a", "b")])

    class _LowPassLLM:
        name = "lowpass"
        def complete(self, messages, *, tier, tools=None, cache=False,
                     max_tokens=4096, temperature=0.1):
            from bad_research.llm.base import LLMResponse
            # Score everything 0.0 on round 1 so <30% pass → forces a widen.
            import json as _json
            user = messages[1].content
            ns = [int(l[1:l.index("]")]) for l in user.splitlines()
                  if l.startswith("[") and "]" in l]
            return LLMResponse(text=_json.dumps([{"i": n, "s": 0.0} for n in ns]),
                               tool_calls=[], usage={}, model="lowpass")

    from bad_research.retrieval.rerank import ClaudeCodeReranker
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db",
                          reranker=ClaudeCodeReranker(llm=_LowPassLLM()),
                          links_db=links_path)
    eng.index([_note("a", "# A\n\nquery seed token alpha\n"),
               _note("b", "# B\n\nneighbor body unrelated tokens\n")])
    neighbors = eng._expand_symbols("a")
    # b's chunk ids are pulled in as widening candidates (outlink a→b).
    assert any(eng._meta[cid].chunk.note_id == "b" for cid in neighbors)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run python -m pytest tests/test_retrieval/test_engine.py::test_expand_symbols_pulls_wiki_link_neighbors -v`
Expected: FAIL — `RetrievalEngine.__init__` has no `links_db` param; `_expand_symbols` only does same-note neighbors.

- [ ] **Step 4: Implement the links-DB read in the engine**

In `src/bad_research/retrieval/engine.py`, add `links_db: Path | None = None` to `__init__` (after `lance_dir`) and store it:
```python
                 lance_dir: Path | None = None,
                 links_db: Path | None = None,
                 alpha: float = ALPHA, gate: float = RELEVANCE_GATE,
```
and inside `__init__`, after `self.store` setup:
```python
        self.links_db = Path(links_db) if links_db is not None else None
```
Replace `_expand_symbols` with:
```python
    def _expand_symbols(self, top_note: str | None) -> set[str]:
        """Wiki-link neighbor widening (dossier 15 §7.3). Pull chunks of the top
        note's graph neighbors (outlinks it makes + backlinks to it) from the
        `links` table, unioned with same-note neighbor chunks. Pure SQL + set
        union — keyless, only runs on the rare <30%-pass path."""
        if top_note is None:
            return set()
        neighbor_notes: set[str] = {top_note}
        if self.links_db is not None and self.links_db.exists():
            conn = sqlite3.connect(str(self.links_db))
            try:
                # outlinks: notes top_note links TO (resolved target_id).
                for (tid,) in conn.execute(
                    "SELECT DISTINCT target_id FROM links "
                    "WHERE source_id = ? AND target_id IS NOT NULL", (top_note,)):
                    neighbor_notes.add(tid)
                # backlinks: notes that link TO top_note.
                for (sid,) in conn.execute(
                    "SELECT DISTINCT source_id FROM links WHERE target_id = ?", (top_note,)):
                    neighbor_notes.add(sid)
            finally:
                conn.close()
        return {cid for cid, m in self._meta.items()
                if m.chunk.note_id in neighbor_notes}
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run python -m pytest tests/test_retrieval/test_engine.py -v`
Expected: PASS (the wiki-link case + every earlier engine case; the same-note fallback still works when `links_db is None`).

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/retrieval/engine.py tests/test_retrieval/test_engine.py tests/test_retrieval/conftest.py
git commit -m "feat(retrieval): expand_symbols widens to wiki-link neighbors (links table) on <30%-pass re-retrieve"
```

---

## Task 8: `BgeLocalEmbedProvider` ([local]) + keyless `get_embed_provider` default; delete Cohere embedder  [KNOWN §4.1 / DESIGNED guard]

**Files:**
- Create: `src/bad_research/embed/bge_local.py`
- Modify: `src/bad_research/embed/base.py`
- Delete: `src/bad_research/embed/cohere.py` (if present)
- Delete: `tests/test_embed/test_cohere.py` (if present)
- Test: `tests/test_embed/test_bge_local.py` (create, `local` marker) + `tests/test_embed/test_base.py` (extend)

- [ ] **Step 1: Write the `get_embed_provider` keyless test**

Overwrite `tests/test_embed/test_base.py` (keep any existing Protocol test, add the keyless default):
```python
import pytest

from bad_research.embed.base import EmbedProvider, get_embed_provider


def test_default_embed_provider_is_bge_local_not_cohere():
    # The keyless default selects the [local] bge bi-encoder, NOT cohere.
    # sentence-transformers is a [local] dep; if absent, the factory raises a
    # helpful ImportError — never a key error, never a cohere import.
    with pytest.raises((ImportError, ModuleNotFoundError)):
        get_embed_provider("bge-local")  # will fail to import sentence_transformers in keyless CI


def test_unknown_provider_rejected_and_no_cohere_branch():
    with pytest.raises(ValueError) as ei:
        get_embed_provider("cohere")
    assert "cohere" in str(ei.value).lower()  # cohere is no longer a known provider
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_embed/test_base.py -v`
Expected: FAIL — `get_embed_provider("cohere")` currently SUCCEEDS (returns CohereEmbedProvider), so `test_unknown_provider_rejected_and_no_cohere_branch` fails.

- [ ] **Step 3: Rewrite `src/bad_research/embed/base.py`**

Overwrite the factory (keep the Protocol verbatim):
```python
"""Base Protocol and factory for the EmbedProvider seam — KEYLESS, OPTIONAL.

The default keyless retrieval path uses NO embedder (FTS5/BM25 recall). When a
user opts into the [local] dense lane (`pip install bad-research[local]`,
`neural_recall=True`, or vault > 25k chunks), the factory returns the local
bge-small bi-encoder. There is NO API embedder — Cohere is removed.

Asymmetric input_type: documents embedded at index time, queries at retrieval
time (the bge query prefix is applied for input_type="query").
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class EmbedProvider(Protocol):
    name: str
    dim: int

    def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"],
    ) -> list[list[float]]: ...


def get_embed_provider(name: str = "bge-local", **kwargs) -> EmbedProvider:
    """Load a keyless embed provider by name. Default = the local bge bi-encoder
    ([local] extra). Cohere is removed — there is no API embedder."""
    if name == "bge-local":
        from bad_research.embed.bge_local import BgeLocalEmbedProvider

        return BgeLocalEmbedProvider(**kwargs)

    raise ValueError(
        f"Unknown embed provider: {name!r}. Available: bge-local "
        f"(install with: pip install bad-research[local]). "
        f"Note: cohere and all API embedders were removed in the keyless rebuild."
    )
```

- [ ] **Step 4: Create `src/bad_research/embed/bge_local.py`**

```python
"""BgeLocalEmbedProvider — local bge-small bi-encoder ([local] extra).

Keyless: sentence-transformers runs on CPU, no network at inference once the
~130 MB model is downloaded. dim 384. Asymmetric: the query prefix
"Represent this sentence for searching relevant passages: " is applied for
input_type="query" (dossier 15 §4.1, §4.3); documents get no prefix.
torch/sentence-transformers are imported lazily so this module only loads when
the provider is actually constructed.
"""
from __future__ import annotations

from typing import Literal

_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class BgeLocalEmbedProvider:
    name: str = "bge-small-en-v1.5"
    dim: int = 384

    def __init__(self, *, model: str = "BAAI/bge-small-en-v1.5",
                 device: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy ([local])

        self.name = model.split("/")[-1]
        self._model = SentenceTransformer(model, device=device)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str], *,
              input_type: Literal["document", "query"]) -> list[list[float]]:
        if not texts:
            return []
        payload = [(_QUERY_PREFIX + t) for t in texts] if input_type == "query" else list(texts)
        vecs = self._model.encode(payload, normalize_embeddings=True,
                                  convert_to_numpy=True)
        return [v.tolist() for v in vecs]
```

- [ ] **Step 5: Create the `[local]`-marked provider test**

Create `tests/test_embed/test_bge_local.py`:
```python
import pytest

pytest.importorskip("sentence_transformers")  # [local] extra; skip in keyless CI

from bad_research.embed.base import EmbedProvider
from bad_research.embed.bge_local import BgeLocalEmbedProvider


@pytest.mark.local
def test_bge_local_is_an_embed_provider_with_dim_384():
    p = BgeLocalEmbedProvider()
    assert isinstance(p, EmbedProvider)
    assert p.dim == 384


@pytest.mark.local
def test_bge_local_query_prefix_changes_the_vector():
    p = BgeLocalEmbedProvider()
    [d] = p.embed(["async runtime"], input_type="document")
    [q] = p.embed(["async runtime"], input_type="query")
    assert len(d) == 384 and len(q) == 384
    # The query prefix perturbs the embedding (asymmetric encoding).
    assert d != q
```

- [ ] **Step 6: Delete the Cohere embedder + its test (idempotent)**

Run:
```bash
git rm -f src/bad_research/embed/cohere.py 2>/dev/null || rm -f src/bad_research/embed/cohere.py
git rm -f tests/test_embed/test_cohere.py 2>/dev/null || rm -f tests/test_embed/test_cohere.py
grep -rn "cohere\|Cohere" src/bad_research/embed/ || echo "EMBED CLEAN"
```
Expected: `EMBED CLEAN`.

- [ ] **Step 7: Run the embed tests (keyless)**

Run: `uv run python -m pytest tests/test_embed/ -v -m "not local"`
Expected: PASS — `test_base.py` passes; `test_bge_local.py` is SKIPPED (no `sentence_transformers` in keyless CI).

- [ ] **Step 8: Commit**

```bash
git add -A src/bad_research/embed/ tests/test_embed/
git commit -m "feat(embed): BgeLocalEmbedProvider ([local], dim 384, query prefix); get_embed_provider keyless default; delete Cohere"
```

---

## Task 9: Make `store.py` import-guarded + mark `test_store.py` `[local]`  [DESIGNED — INTERFACES_KEYLESS §1.1]

**Files:**
- Modify: `src/bad_research/retrieval/store.py`
- Modify: `tests/test_retrieval/test_store.py`

- [ ] **Step 1: Move the lancedb/pyarrow imports inside the class (lazy)**

In `src/bad_research/retrieval/store.py`, delete the top-level:
```python
import lancedb  # type: ignore[import-untyped]
import pyarrow as pa
```
and move them into `__init__` + the methods that use them. Replace the top of `LanceChunkStore.__init__`:
```python
    def __init__(self, lance_dir: Path, *, dim: int):
        import lancedb  # type: ignore[import-untyped]  ([local] extra)

        self.dir = Path(lance_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.db = lancedb.connect(str(self.dir))
        self._table = self._open_or_create()
```
and add `import pyarrow as pa` as the first line of `_schema` and of `upsert` (the two methods that reference `pa`). Everything else in the file is unchanged. The result: `import bad_research.retrieval.store` no longer crashes without `lancedb` installed; only *constructing* `LanceChunkStore` requires it (which the keyless engine never does).

- [ ] **Step 2: Mark the store test `[local]`**

At the top of `tests/test_retrieval/test_store.py`, add:
```python
import pytest

pytest.importorskip("lancedb")  # [local] extra
pytestmark = pytest.mark.local
```
(Keep the rest of the test file unchanged.)

- [ ] **Step 3: Run the keyless suite — store is now deselected**

Run: `uv run python -m pytest tests/test_retrieval/ -v -m "not local"`
Expected: PASS, with `test_store.py` SKIPPED/deselected (no `lancedb`).

- [ ] **Step 4: Verify the module still imports without lancedb**

Run: `uv run python -m pytest tests/test_retrieval/test_import_keyless.py -v`
Expected: PASS — importing `bad_research.retrieval.store` is no longer blocked (only constructing it would be).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/retrieval/store.py tests/test_retrieval/test_store.py
git commit -m "refactor(retrieval): lazy-import lancedb/pyarrow in store ([local]); mark test_store local"
```

---

## Task 10: `pyproject.toml` — `[local]` extra + the `local` pytest marker  [KNOWN — INTERFACES_KEYLESS §7]

**Files:**
- Modify: `pyproject.toml`

This is idempotent w.r.t. KR-1: it adds the `[local]` extra and registers the marker; if KR-1 already slimmed core, this is a no-op on the core list.

- [ ] **Step 1: Add/confirm the `[local]` extra**

In `pyproject.toml` under `[project.optional-dependencies]`, add (or confirm) the `local` extra exactly:
```toml
# Offline neural stack — opt-in, lazy-downloaded. The ONLY place torch/lancedb live.
local = [
    "torch>=2.0",
    "sentence-transformers>=3.0",        # bge-small bi-encoder + ms-marco/bge-reranker + nli-deberta
    "lancedb>=0.13",                     # vector store (only when neural_recall is on)
    "pyarrow>=15.0",                     # lancedb dep
]
```
If KR-1 has NOT yet run and `lancedb`/`pyarrow` are still in the core `dependencies` array, leave them for KR-1 to remove (this plan owns `retrieval/`, KR-1 owns the core-dep slim); do not duplicate or fight it. The `[local]` extra above is additive and conflict-free.

- [ ] **Step 2: Register the `local` pytest marker**

Add (or confirm) under `[tool.pytest.ini_options]` in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "local: requires the [local] extra (torch/sentence-transformers/lancedb) — skipped in keyless CI",
    "live: hits a real keyless API/CLI — skipped by default",
]
```
(If `[tool.pytest.ini_options]` already exists, merge the `markers` list — do not duplicate the table header.)

- [ ] **Step 3: Verify the marker is recognized (no unknown-marker warnings)**

Run: `uv run python -m pytest tests/test_retrieval/ tests/test_embed/ -q -m "not local" -W error::pytest.PytestUnknownMarkWarning`
Expected: PASS with no `PytestUnknownMarkWarning` (the `local` marker is registered).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(retrieval): [local] extra (torch/sentence-transformers/lancedb) + register local/live pytest markers"
```

---

## Task 11: Full keyless suite green + the no-key / no-mandatory-model guard  [verification]

**Files:** none (verification + the guard test).

- [ ] **Step 1: Add the keyless-invariant guard test**

Create `tests/test_retrieval/test_no_keys_invariant.py`:
```python
"""Cross-plan invariant (KEYLESS_REBUILD_PLAN_OUTLINE §1): zero third-party key,
no mandatory local model in the retrieval surface."""
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "bad_research"


def test_no_cohere_or_api_embedder_in_retrieval_or_embed():
    banned = ("cohere", "tavily", "exa_provider", "firecrawl", "voyage")
    for pkg in ("retrieval", "embed"):
        for py in (SRC / pkg).rglob("*.py"):
            text = py.read_text().lower()
            for token in banned:
                assert token not in text, f"{py}: banned token {token!r} survives"


def test_default_engine_constructs_with_no_local_dep_and_no_env_key(tmp_path, monkeypatch):
    # No ANTHROPIC_API_KEY, no COHERE_API_KEY — the FTS-default + none-reranker
    # engine must still construct (the host model is only called at rerank time,
    # and "none" avoids even that).
    for k in ("ANTHROPIC_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    from bad_research.retrieval.engine import RetrievalEngine
    from bad_research.retrieval.rerank import get_reranker

    class _Cfg:
        reranker = "none"
    eng = RetrievalEngine(cache_db=tmp_path / "c.db", reranker=get_reranker(_Cfg()))
    assert eng.embedder is None and eng.store is None
```

- [ ] **Step 2: Run the guard**

Run: `uv run python -m pytest tests/test_retrieval/test_no_keys_invariant.py -v`
Expected: PASS — no banned import survives `retrieval/`+`embed/`; the default engine constructs with no env key and no `[local]` dep.

- [ ] **Step 3: Run the entire keyless retrieval + embed surface**

Run:
```bash
uv run python -m pytest tests/test_retrieval/ tests/test_embed/ -v -m "not local"
```
Expected: PASS across `test_constants`, `test_fusion` (untouched), `test_rerank`, `test_cache`, `test_engine`, `test_import_keyless`, `test_no_keys_invariant`, `test_base`; `test_store` and `test_bge_local` SKIPPED (deselected by `-m "not local"`).

- [ ] **Step 4: Lint + type-check the reworked files**

Run:
```bash
uv run ruff check src/bad_research/retrieval/ src/bad_research/embed/
uv run mypy src/bad_research/retrieval/engine.py src/bad_research/retrieval/rerank.py src/bad_research/retrieval/cache.py src/bad_research/embed/base.py 2>/dev/null || true
```
Expected: `ruff` clean; `mypy` may report pre-existing repo-wide issues — fix only ones introduced by this plan (the `Any`-typed `llm`/`store`/`scorer` seams are intentional).

- [ ] **Step 5: Commit**

```bash
git add tests/test_retrieval/test_no_keys_invariant.py
git commit -m "test(retrieval): keyless invariant — no Cohere/API embedder, default engine needs no key or [local] dep"
```

---

## Task 12: Optional `[local]` lane regression (run only where the deps are installed)  [CALIBRATE — dossier 15 §8.4]

**Files:** none new — this is the gated run of the `local`-marked tests.

- [ ] **Step 1: Run the `[local]` lane on a machine with the extra installed**

Run:
```bash
uv pip install -e ".[local]"
uv run python -m pytest tests/test_retrieval/ tests/test_embed/ -v -m "local"
```
Expected: `test_store.py` and `test_bge_local.py` PASS (LanceDB upsert/search; bge dim 384 + asymmetric query prefix). If the machine has no `[local]` deps, this task is documented-and-skipped — it is NOT part of the keyless CI gate.

- [ ] **Step 2: Spot-check the dense-lane engine path with a real embedder**

Run this ad-hoc check (only with `[local]` installed):
```bash
uv run python - <<'PY'
from pathlib import Path
import tempfile
from bad_research.embed.bge_local import BgeLocalEmbedProvider
from bad_research.retrieval.engine import RetrievalEngine
from bad_research.retrieval.rerank import get_reranker
from bad_research.models.note import Note, NoteMeta

class _Cfg: reranker = "none"
d = Path(tempfile.mkdtemp())
eng = RetrievalEngine(cache_db=d/"c.db", reranker=get_reranker(_Cfg()),
                      embedder=BgeLocalEmbedProvider())
assert eng.store is not None and eng.embedder is not None  # dense lane on
eng.index([Note(meta=NoteMeta(title="a", id="a", source="https://x/a"),
                body="# A\n\nbinary quantization cuts vector RAM sixteen fold\n",
                path="research/a.md")])
hits = eng.search("how to reduce embedding memory", mode="full", top_k=3)
print("dense-lane hits:", [(h.note_id, round(h.score,3)) for h in hits])
PY
```
Expected: prints at least one hit for note `a` — the bge dense lane surfaces the paraphrase ("reduce embedding memory" ↔ "cuts vector RAM") that BM25-only would miss (dossier 15 §2.2/§4.3). This validates the RRF-fused dense path end-to-end. CALIBRATE: nDCG A/B (none vs local-cross-encoder vs host) is the KR-7 eval (§8.4).

- [ ] **Step 3: No commit** — verification only.

---

## Self-Review — spec coverage check

| INTERFACES_KEYLESS / dossier 15 requirement | Task |
|---|---|
| §5.1 `RetrievalEngine(embedder=None default, lance_dir=None, reranker, alpha, gate, top_k_retrieve)` | Task 5 (+ `links_db` Task 7) |
| §5.1 `search(query, *, mode, top_k)` signature unchanged | Task 5 |
| §5.1 `index()` FTS-always, LanceDB only if embedder | Task 5 |
| §5.2 fusion math kept verbatim (`hybrid_fuse`, `three_tier_fuse`, `apply_source_type_weight`, `rrf_merge`) | untouched (`fusion.py`); Task 0 regression-anchors it |
| §5.2 FTS-only initial = min-max BM25; RRF k=60 when dense on | Task 5 (`_one_round` branch) |
| §5.3 `ClaudeCodeReranker` default, verbatim LLM-rerank prompt, pointwise 0..1, temp=0, ~800 trunc, JSON, graceful 0.0, injection preamble | Task 2, 3 |
| §5.3 prompt shared shape with `HostModelReranker` (search) | Task 3 (constant `LLM_RERANK_SYSTEM`, documented shared) |
| §5.3 `get_reranker` host/local/none; `BGEReranker` ms-marco default behind `[local]` | Task 3 |
| §5.4 `BgeLocalEmbedProvider(dim 384, query prefix)` `[local]`; `get_embed_provider` keyless default; cohere branch deleted | Task 8 |
| §5.4 25k auto-enable threshold constant | Task 1 (the CLI wires the auto-enable in KR-6; the engine honors whatever embedder it gets) |
| §5.5 `LexicalCacheBackend` (token-set overlap 0.85), selected when `embedder is None`; cosine 0.92 under `[local]` | Task 4 |
| §5.6 constants `SEMANTIC_CACHE_THRESHOLD_LEXICAL/NEURAL_RECALL_VAULT_THRESHOLD/LLM_RERANK_TRUNC_CHARS/LLM_RERANK_BATCH` | Task 1 |
| §7.1 0.70 gate / §7.2 <30% re-retrieve ≤rounds | Task 5 (kept loop) |
| §7.3 `expand_symbols` → wiki-link neighbors (links table) | Task 7 |
| §7.4 progressive cascade (top-12) is a budget knob, not default | Default ships full top-30 (Task 3 `LLM_RERANK_BATCH=30`); top-12 cascade is a documented KR-6 budget lever, out of KR-5 scope |
| §1.1 LanceDB leaves the default path; `store.py` `[local]` import-guard | Task 5 (no construction), Task 9 (lazy import) |
| Outline §1 invariant: zero key, no mandatory local model | Task 6 + Task 11 (import-smoke + guard tests) |
| `[local]` use-if-present, skipped-when-absent / used-when-present | Task 6, 9 (skip), Task 12 (used) |

**Cascade-knob note (intentional non-implementation):** dossier 15 §7.4's top-12 progressive cascade is explicitly "the budget knob for token-constrained runs," with "default ships L2 = full top-30." KR-5 ships the default (full top-30, `LLM_RERANK_BATCH=30`). The cascade is wired to `effort`/`max_tokens` in KR-6 (the loop-lever plan that owns the effort continuum), so implementing it here would duplicate KR-6's degrade-order logic. Recorded here so it is a deliberate scope boundary, not a gap.

**Placeholder scan:** no `TBD`/`TODO`/"add error handling"/"similar to Task N" — every code step shows full code; every test step shows the assertions; every run step shows the command + expected output.

**Type consistency:** `Reranker.rerank(query, docs) -> list[tuple[int, float]]` (base.py, unchanged) is the return shape of `ClaudeCodeReranker`, `BGEReranker`, `_IdentityReranker` (Task 3). `EmbedProvider.embed(texts, *, input_type)` (base.py) matches `BgeLocalEmbedProvider.embed` (Task 8) and the engine's `input_type="document"/"query"` calls (Task 5). `get_cache(db_path, *, embedder)` (Task 4) is called by the engine constructor (Task 5). `RetrievalEngine.__init__(*, cache_db, reranker, embedder=None, lance_dir=None, links_db=None, alpha, gate, top_k_retrieve)` is the single constructor used across Tasks 5/6/7/11/12. The `FakeLLMProvider.complete(...)` signature (Task 2) matches `LLMProvider.complete` (llm/base.py) and is what `ClaudeCodeReranker.rerank` calls (Task 3).

---

## Execution Handoff

**Plan complete and saved to `docs/plans/2026-05-27-bad-research-KR-5-retrieval.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
