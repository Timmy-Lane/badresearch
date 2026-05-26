# Bad Research — KR-1: Provider Removal + Dep Slim-Down — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete every paid-API-provider module (Tavily/Sonar/Firecrawl/Exa search + cascade, Browserbase/Browser-Use/AgentQL/Stagehand browse, Cohere embed + Cohere rerank, LanceDB-from-core), slim `pyproject.toml` to the lean keyless base + `[local]`/`[browse]`/`[mcp]` extras, and rewrite the two factories + registry + config to keyless stubs — leaving the full test suite green and the 80% coverage floor intact, on clean ground that KR-2…KR-5 build on.

**Architecture:** This is a *deletion + rewire* pass, not a feature pass. Every task removes one keyed module (or class) plus its tests, fixes the now-broken imports in callers by replacing them with a small **typed keyless stub** (a `NotImplementedError`-raising shim that KR-2/KR-3/KR-4/KR-5 later flesh out), then runs the suite to green and commits. The kept seams (`llm/`, `grounding/`, `quality/`, `core/`, `funnel/` shape, `search/fts.py`, the retrieval fusion math, `calibrate/`) are never rewritten — only called. `anthropic` stays a CORE dependency (the headless `pipeline.run_query` + `calibrate` bridge needs it; the skill path is keyless-to-use because the host supplies inference). The coverage floor is protected by adding the three files whose real coverage moves to a later KR (`web/base.py`, `embed/base.py`, `retrieval/rerank.py` keyless stubs, `retrieval/engine.py` optional-vector branch) to the `[tool.coverage.run] omit` list, exactly as the existing `omit` block already does for not-yet-covered surfaces.

**Tech Stack:** Python 3.11–3.13, `uv` for the venv + test runner (`uv run python -m pytest`), `hatchling` build backend, `pytest` + `pytest-cov` (80% floor, `--strict-markers`), `ruff` + `mypy --strict`, `typer`/`rich` CLI. Removed PyPI packages: `tavily-python`, `exa-py`, `cohere`, `firecrawl-py`, `browser-use`, `agentql`; `lancedb` + `pyarrow` demoted from core to `[local]`. External keyless CLIs (`agent-browser`, `lightpanda`, `yt-dlp`, `git`, optional SearXNG) are NOT pip deps — wired in KR-4/KR-7.

**Bind to the frozen contract:** `docs/INTERFACES_KEYLESS.md` §1 (REMOVED list — exact paths), §3.4 (config knobs), §3.5 (registry), §7 (lean deps). Every label below is **KNOWN** (the code/test exists, verified by reading it), **DESIGNED** (the keyless stub this plan introduces), or **CALIBRATE** (deferred to a later KR — noted, not done here).

**Repo conventions (honor exactly):**
- Always `export PATH="$HOME/.local/bin:$PATH"` before any command (so `uv` resolves).
- Tests run via `uv run python -m pytest` (the sandbox pip is broken; use `uv`).
- The green bar = `uv run python -m pytest -q -p no:cacheprovider` → `501 passed` (the baseline at plan time) minus the tests this plan deletes, **with zero failures/errors and coverage ≥ 80%**.
- Commit on branch `main` after every task. End every commit message with:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- Baseline at plan-write time (verified): `501 passed, 2 skipped`, total coverage **87.81%**.

---

## File Structure

### DELETED — source modules (12 files: 6 web + 4 browse + 1 embed + the providers `__init__`)

| Path | Why | Caller(s) that break |
|---|---|---|
| `src/bad_research/web/providers/tavily_provider.py` | Tavily key | `web/base.py`, `web/providers/__init__.py` |
| `src/bad_research/web/providers/sonar_provider.py` | Perplexity/PPLX key | `web/base.py`, `web/providers/__init__.py` |
| `src/bad_research/web/providers/firecrawl_provider.py` | Firecrawl key | `web/base.py`, `web/providers/__init__.py` |
| `src/bad_research/web/providers/cascade.py` | key-gated cascade | `web/base.py::_build_cascade`, `web/providers/__init__.py` |
| `src/bad_research/web/providers/__init__.py` | dir removed | `web/providers/__init__.py` re-exports |
| `src/bad_research/web/providers/searxng_provider.py` | leaves `providers/` (capability returns keyless in KR-2 under `web/search/`) | `web/base.py`, `web/providers/__init__.py`, `_build_cascade` |
| `src/bad_research/web/exa_provider.py` | Exa key | `web/base.py`, `_build_cascade` |
| `src/bad_research/browse/browse_browserbase.py` | Browserbase key + Stagehand SDK | `browse/base.py`, `browse/ladder.py` |
| `src/bad_research/browse/browse_browseruse.py` | Browser-Use cloud lib | `browse/base.py`, `browse/ladder.py` |
| `src/bad_research/browse/extract_agentql.py` | AgentQL key | `browse/base.py` |
| `src/bad_research/browse/extract_stagehand.py` | Stagehand SDK | `browse/base.py` |
| `src/bad_research/embed/cohere.py` | Cohere key | `embed/base.py`, `cli/research.py::_build_embedder` |

> NOTE: the `web/providers/` directory disappears entirely (6 files). `searxng_provider.py` is in the REMOVED list because its *file* leaves `providers/`; the *capability* is rebuilt keyless in `web/search/` by **KR-2**. KR-1 leaves a `searxng` stub branch in `get_provider`.

### DELETED — tests (12 files)

| Path | Targets removed module |
|---|---|
| `tests/test_web/providers/test_tavily_provider.py` | tavily_provider |
| `tests/test_web/providers/test_sonar_provider.py` | sonar_provider |
| `tests/test_web/providers/test_firecrawl_provider.py` | firecrawl_provider |
| `tests/test_web/providers/test_searxng_provider.py` | searxng_provider |
| `tests/test_web/providers/test_cascade.py` | cascade |
| `tests/test_web/providers/__init__.py` | dir removed |
| `tests/test_web/test_exa_provider.py` | exa_provider |
| `tests/test_browse/test_browse_browserbase.py` | browse_browserbase |
| `tests/test_browse/test_browse_browseruse.py` | browse_browseruse |
| `tests/test_browse/test_extract_agentql.py` | extract_agentql |
| `tests/test_browse/test_extract_stagehand.py` | extract_stagehand |
| `tests/test_embed/test_cohere.py` | cohere embedder |
| `tests/test_retrieval/test_store.py` | LanceChunkStore (moves behind `[local]`; test re-added under a `local` marker in KR-5) |

### MODIFIED — source (11 files + 2 NEW stub files)

| Path | Change |
|---|---|
| `pyproject.toml` | lean core deps (drop `lancedb`/`pyarrow`/`numpy`); delete `[search]` extra; redefine `[browse]`=`["playwright>=1.40"]`; add `[local]`; `[grounding]` folds into `[local]`; redefine `[all]`; extend `[tool.coverage.run] omit`. |
| `src/bad_research/web/base.py` | delete `_build_cascade`; rewrite `get_provider` to keyless registry (default `websearch`; branches `ddgs`/`searxng`/`builtin`/`crawl4ai` → typed stub for the not-yet-built ones); keep `WebResult`/`SearchQuery`/`WebProvider`/`WebSearchProvider`/error classes verbatim. |
| `src/bad_research/web/__init__.py` | unchanged (docstring only) — verify it does not import `providers`. |
| `src/bad_research/browse/base.py` | rewrite `get_browse_provider` (drop browserbase/browser-use key branches → keyless `agent-browser` stub returning `None` until KR-4); rewrite `get_extract_provider` (keep `llm` default; drop `agentql`/`stagehand` branches → `None`). |
| `src/bad_research/browse/ladder.py` | drop `_browseruse`/`_browserbase` injection seams + `_do_browse` keyed branches → keyless `_do_browse` that resolves `get_browse_provider()` (returns `None` until KR-4). Keep `fetch_tiered` signature + Tier 0/1/2 logic verbatim. |
| `src/bad_research/embed/base.py` | rewrite `get_embed_provider` default to `bge-local` (`[local]` stub); delete the `cohere` branch. |
| `src/bad_research/embed/__init__.py` | docstring tweak (no import change). |
| `src/bad_research/retrieval/rerank.py` | delete `CohereReranker` + its import; add a typed `ClaudeCodeReranker` **stub** (KR-5 fills it); rewrite `get_reranker` → `host`/`local`/`none` (default `host`→stub; `local`→`BGEReranker`; `none`→identity). Keep `BGEReranker` + `Scorer` + `_default_bge_scorer`. |
| `src/bad_research/retrieval/engine.py` | make the vector lane optional: `embedder: EmbedProvider \| None = None`, `lance_dir: Path \| None = None`; FTS-only default path; `LanceChunkStore` imported lazily only when `lance_dir` set. Keep fusion + gate + re-retrieve logic verbatim. |
| `src/bad_research/config.py` | drop dead Cohere `embed_model`/`rerank_model` defaults (+ their TOML/env plumbing); add `reranker`/`neural_recall`/`searxng_endpoint`/`browse_engine`/`effort`/`max_tokens` keyless knobs. |
| `src/bad_research/providers.py` | rewrite `PROVIDERS` to keyless rows only (no keyed providers; every `requires_key=False`). |
| `src/bad_research/cli/research.py` | `_build_embedder` → returns `None` (FTS-only default); `_build_reranker` → `ClaudeCodeReranker` stub via `get_reranker(cfg)`; `_build_engine` → passes `embedder=None`, `lance_dir=None`. |

### MODIFIED — tests (8 files)

| Path | Change |
|---|---|
| `tests/test_web/test_provider_factory.py` | rewrite around keyless `get_provider` (default `websearch`; `builtin` real; `ddgs`/`searxng`/`crawl4ai` stub-or-real; unknown raises with keyless list). Delete the cascade/tavily/sonar/firecrawl/providers-reexport tests. |
| `tests/test_providers.py` | rewrite registry assertions to the keyless rows (no keyed names; `requires_key` False everywhere). |
| `tests/test_packaging/test_pyproject.py` | rewrite the extras/lean-base assertions: `[search]` gone, `[local]` present with torch/lancedb, base lean (no lancedb/cohere/torch). |
| `tests/test_packaging/test_doctor.py` | rewrite the `tavily` env-key assertion to a keyless row assertion (e.g. `websearch`/`ddgs` present, `requires_key` False). |
| `tests/test_embed/test_base.py` | rewrite `test_unknown_provider_raises` + add a `get_embed_provider("bge-local")` import-guard test (skip if `[local]` absent). |
| `tests/test_retrieval/test_rerank.py` | delete the Cohere tests; rewrite around `get_reranker` host/local/none + `ClaudeCodeReranker` stub contract + `BGEReranker` (injected scorer). |
| `tests/test_retrieval/test_engine.py` | rewrite `_engine` to construct FTS-only (`embedder=None`, `lance_dir=None`); keep gate/cache/source-weight assertions. |
| `tests/test_pipeline/test_build_real.py` | rewrite the builder tests: `_build_embedder` returns `None`, `_build_reranker` returns `ClaudeCodeReranker`, `_build_engine` works FTS-only; keep the verify-citations LLM-builder test (anthropic stays core). |
| `tests/test_config/test_config.py` | rewrite the default-asserts: drop `embed_model`/`rerank_model`; add `reranker`/`searxng_endpoint`/`browse_engine`/`effort` defaults; fix the TOML test that sets `embed_model`/`rerank_model`. |

### UNCHANGED — verify they still import (no edits)

`llm/*`, `grounding/*`, `quality/*`, `core/*`, `funnel/*` (the `sonar`/`exa` strings in `tests/test_funnel/conftest.py` are **FakeProvider names**, not real imports — they stay), `search/fts.py`, `search/filters.py`, `retrieval/{fusion,cache,fts_chunks,chunker,chunker_code,anchors,constants,base}.py`, `retrieval/__init__.py`, `calibrate/*`, `browse/extract_llm.py`, `browse/cache.py`, `web/builtin.py`, `web/crawl4ai_provider.py`.

---

## Temporary stubs this plan leaves (and which KR removes each)

| Stub | File | Behavior in KR-1 | Filled / removed by |
|---|---|---|---|
| `get_provider("websearch"/"ddgs"/"searxng")` branches | `web/base.py` | raise `NotImplementedError("KR-2 …")` (the *named* branch exists so the registry/CLI resolve; `builtin`+`crawl4ai` are real) | **KR-2** (`web/search/`) |
| `get_browse_provider()` default | `browse/base.py` | return `None` (graceful: ladder keeps lower tier) | **KR-4** (`browse/agent_browser.py`) |
| `_do_browse` keyless body | `browse/ladder.py` | resolve `get_browse_provider()`; `None` → keep lower tier | **KR-4** |
| `ClaudeCodeReranker` | `retrieval/rerank.py` | `__init__` ok; `rerank()` raises `NotImplementedError("KR-5 …")` | **KR-5** |
| `get_embed_provider("bge-local")` | `embed/base.py` | import-guarded `BgeLocalEmbedProvider` from `embed.bge_local`; raises `ImportError` w/ install hint until KR-5 creates that module | **KR-5** |
| `_build_embedder` → `None` | `cli/research.py` | FTS-only default | **KR-6** (rewire) — but `None` is the durable default, so this is not removed, only confirmed |

> The stubs are **typed** (real signatures, real return annotations) so `mypy --strict` passes and KR-2…KR-5 drop in bodies without touching callers.

---

## Task 1: Delete the Exa search provider + its test

**Files:**
- Delete: `src/bad_research/web/exa_provider.py`
- Delete: `tests/test_web/test_exa_provider.py`
- Modify: `src/bad_research/web/base.py` (drop the `exa` branch in `get_provider`; drop `_build_cascade`'s Exa lines — full `_build_cascade` removal is Task 4, so here just delete the `exa` `get_provider` branch)

Exa is referenced only by `web/base.py` (`get_provider` branch + `_build_cascade`) and its own test. `_build_cascade` is deleted whole in Task 4, so this task only removes the standalone `exa` branch + the file + test.

- [ ] **Step 1: Delete the module and its test**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm src/bad_research/web/exa_provider.py tests/test_web/test_exa_provider.py
```
Expected: `rm 'src/bad_research/web/exa_provider.py'` and `rm 'tests/test_web/test_exa_provider.py'`.

- [ ] **Step 2: Remove the `exa` branch from `get_provider`**

In `src/bad_research/web/base.py`, delete these lines (currently ~226–229):
```python
    if name == "exa":
        from bad_research.web.exa_provider import ExaProvider

        return ExaProvider()

```
(Leave the rest of `get_provider` and `_build_cascade` intact for now — Task 4 rewrites them.)

- [ ] **Step 3: Run the suite to verify exa is gone and nothing else broke yet**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -5`
Expected: the `exa` factory test is gone; `test_factory_cascade_zero_key` in `test_provider_factory.py` still passes (it only checks SearXNG + `_neural is None`); everything else still passes. (Coverage is deferred to `--no-cov` here; the floor is re-checked at the end of Task 4.)

- [ ] **Step 4: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: remove Exa search provider + its test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Delete the three keyed search providers (Tavily / Sonar / Firecrawl) + their tests

**Files:**
- Delete: `src/bad_research/web/providers/tavily_provider.py`, `src/bad_research/web/providers/sonar_provider.py`, `src/bad_research/web/providers/firecrawl_provider.py`
- Delete: `tests/test_web/providers/test_tavily_provider.py`, `tests/test_web/providers/test_sonar_provider.py`, `tests/test_web/providers/test_firecrawl_provider.py`
- (Do NOT touch `cascade.py`/`searxng_provider.py`/`web/providers/__init__.py` yet — Task 4 removes the whole dir together so imports never dangle mid-task.)

These three are imported by `web/base.py::get_provider` + `_build_cascade` + `web/providers/__init__.py`. Because `web/providers/__init__.py` re-exports them, deleting the files alone breaks `import bad_research.web.providers`. To keep every intermediate state green, this task deletes the three files AND temporarily edits `web/providers/__init__.py` to stop re-exporting them, AND edits `get_provider` to drop their branches. The whole `providers/` dir then disappears in Task 4.

- [ ] **Step 1: Delete the three provider modules + their tests**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm src/bad_research/web/providers/tavily_provider.py \
       src/bad_research/web/providers/sonar_provider.py \
       src/bad_research/web/providers/firecrawl_provider.py \
       tests/test_web/providers/test_tavily_provider.py \
       tests/test_web/providers/test_sonar_provider.py \
       tests/test_web/providers/test_firecrawl_provider.py
```
Expected: six `rm '…'` lines.

- [ ] **Step 2: Stop re-exporting them from `web/providers/__init__.py`**

Replace the entire contents of `src/bad_research/web/providers/__init__.py` with (cascade + searxng survive until Task 4):
```python
"""Web search providers (Plan 03) — keyed providers removed in KR-1; dir removed in KR-1 Task 4."""

from bad_research.web.providers.cascade import CascadeProvider, cascade_search
from bad_research.web.providers.searxng_provider import SearxngProvider

__all__ = ["CascadeProvider", "SearxngProvider", "cascade_search"]
```

- [ ] **Step 3: Drop the tavily/sonar/firecrawl branches from `get_provider`**

In `src/bad_research/web/base.py::get_provider`, delete these three blocks (currently ~231–249):
```python
    if name == "tavily":
        from bad_research.web.providers.tavily_provider import TavilyProvider

        return TavilyProvider()

    if name == "sonar":
        from bad_research.web.providers.sonar_provider import SonarProvider

        return SonarProvider()

```
and
```python
    if name == "firecrawl":
        from bad_research.web.providers.firecrawl_provider import FirecrawlProvider

        return FirecrawlProvider()

```
Then in `_build_cascade`, delete the `if os.environ.get("PERPLEXITY_API_KEY"):`/`SonarProvider`, `if os.environ.get("TAVILY_API_KEY"):`/`TavilyProvider`, and `if os.environ.get("FIRECRAWL_API_KEY"):`/`FirecrawlProvider` blocks (leaving `_build_cascade` to be deleted whole in Task 4). The minimal safe edit: replace the entire `_build_cascade` body's keyed lines so it reads (transitional — deleted next task):
```python
def _build_cascade():
    """Transitional zero-key cascade (SearXNG only). Deleted in KR-1 Task 4."""
    from bad_research.web.providers.cascade import CascadeProvider
    from bad_research.web.providers.searxng_provider import SearxngProvider

    return CascadeProvider(
        keyword_providers=[SearxngProvider()],
        neural_provider=None,
        extractor=None,
        extract_top_n=0,
    )
```

- [ ] **Step 4: Delete the three keyed factory tests in `test_provider_factory.py`**

In `tests/test_web/test_provider_factory.py`, delete `test_factory_tavily`, `test_factory_sonar`, `test_factory_firecrawl`, and update `test_providers_package_reexports` to only import `CascadeProvider`, `SearxngProvider` (drop `FirecrawlProvider`, `SonarProvider`, `TavilyProvider`). Update `test_factory_unknown_raises_with_full_list` will be rewritten in Task 4 — leave it for now (it still passes because the error string is unchanged).

```python
def test_providers_package_reexports() -> None:
    from bad_research.web.providers import CascadeProvider, SearxngProvider

    assert SearxngProvider.name == "searxng"
    assert CascadeProvider.name == "cascade"
```

- [ ] **Step 5: Run the suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: green (the tavily/sonar/firecrawl provider tests + factory tests are gone; cascade-zero-key + searxng factory tests still pass).

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: remove Tavily/Sonar/Firecrawl keyed search providers + tests

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Delete the 4 browse cloud/keyed providers + their tests

**Files:**
- Delete: `src/bad_research/browse/browse_browserbase.py`, `src/bad_research/browse/browse_browseruse.py`, `src/bad_research/browse/extract_agentql.py`, `src/bad_research/browse/extract_stagehand.py`
- Delete: `tests/test_browse/test_browse_browserbase.py`, `tests/test_browse/test_browse_browseruse.py`, `tests/test_browse/test_extract_agentql.py`, `tests/test_browse/test_extract_stagehand.py`
- (Factory + ladder rewrites that reference them are Task 4 — but those references are all *lazy local imports* inside functions, so deleting the files does not break module import. The factory/ladder branches just become dead `return None` paths until Task 4 cleans them.)

> The four modules are imported only lazily inside `browse/base.py` (inside `get_*_provider`) and `browse/ladder.py` (inside `_do_browse`), never at module top level. So the package imports cleanly after deletion; the keyed branches simply hit `ImportError` → `return None`, which `test_graceful_degradation.py` already asserts is fine.

- [ ] **Step 1: Delete the four browse modules + their tests**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm src/bad_research/browse/browse_browserbase.py \
       src/bad_research/browse/browse_browseruse.py \
       src/bad_research/browse/extract_agentql.py \
       src/bad_research/browse/extract_stagehand.py \
       tests/test_browse/test_browse_browserbase.py \
       tests/test_browse/test_browse_browseruse.py \
       tests/test_browse/test_extract_agentql.py \
       tests/test_browse/test_extract_stagehand.py
```
Expected: eight `rm '…'` lines.

- [ ] **Step 2: Run the suite (factories degrade to None gracefully)**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest -q -p no:cacheprovider --no-cov tests/test_browse 2>&1 | tail -8`
Expected: `test_base.py` + `test_graceful_degradation.py` + `test_ladder.py` still pass. The browserbase/browseruse/agentql/stagehand branches in `get_*_provider` now hit `ImportError`→`None` (which the graceful-degradation tests assert). `test_base.py::test_get_browse_provider_browseruse_none_when_lib_missing` and `test_get_browse_provider_browserbase_none_without_key` still pass (lib/key gates short-circuit before the now-missing import).

- [ ] **Step 3: Full suite + commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -4
git add -A
git commit -m "KR-1: remove Browserbase/Browser-Use/AgentQL/Stagehand browse providers + tests

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
Expected: green.

---

## Task 4: Rewrite `web/base.py` to the keyless factory + delete the `providers/` dir

**Files:**
- Modify: `src/bad_research/web/base.py` (delete `_build_cascade`; rewrite `get_provider`)
- Delete: `src/bad_research/web/providers/cascade.py`, `src/bad_research/web/providers/searxng_provider.py`, `src/bad_research/web/providers/__init__.py`
- Delete: `tests/test_web/providers/test_cascade.py`, `tests/test_web/providers/test_searxng_provider.py`, `tests/test_web/providers/__init__.py`
- Modify: `tests/test_web/test_provider_factory.py` (rewrite to the keyless factory)

This is the first factory rewrite. `get_provider` becomes keyless: `builtin` + `crawl4ai` are real (kept), `websearch`/`ddgs`/`searxng` are **typed `NotImplementedError` stubs** (KR-2 fills them), `cascade`/`tavily`/`sonar`/`firecrawl`/`exa` are gone. `_build_cascade` is deleted entirely.

- [ ] **Step 1: Write the failing test (keyless factory contract)**

Replace the entire contents of `tests/test_web/test_provider_factory.py` with:
```python
"""get_provider() is keyless: builtin/crawl4ai real; websearch/ddgs/searxng are
KR-2 stubs; unknown raises ValueError listing only keyless names."""

from __future__ import annotations

import pytest

from bad_research.web.base import get_provider


def test_factory_default_is_websearch_stub() -> None:
    """Default provider is the keyless host WebSearch adapter (a KR-2 stub for now)."""
    prov = get_provider()  # no name -> default
    assert prov.name == "websearch"


def test_factory_builtin_is_real() -> None:
    prov = get_provider("builtin")
    assert prov.name == "builtin"


def test_factory_ddgs_and_searxng_resolve_by_name() -> None:
    assert get_provider("ddgs").name == "ddgs"
    assert get_provider("searxng").name == "searxng"


def test_factory_unknown_raises_keyless_list() -> None:
    with pytest.raises(ValueError) as exc:
        get_provider("not-real")
    msg = str(exc.value)
    for name in ("websearch", "ddgs", "searxng", "builtin", "crawl4ai"):
        assert name in msg
    for gone in ("tavily", "sonar", "exa", "firecrawl", "cascade"):
        assert gone not in msg


def test_no_keyed_providers_package() -> None:
    """The web.providers package is gone."""
    with pytest.raises(ImportError):
        import bad_research.web.providers  # noqa: F401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_web/test_provider_factory.py -q -p no:cacheprovider --no-cov 2>&1 | tail -10`
Expected: FAIL — `get_provider()` still returns `BuiltinProvider` (name `builtin`, not `websearch`); the unknown-list still names tavily/etc.; `web.providers` still imports.

- [ ] **Step 3: Rewrite `get_provider` and delete `_build_cascade`**

In `src/bad_research/web/base.py`, replace the entire `get_provider(...)` function AND the `_build_cascade()` function (everything from `def get_provider(` to end of file) with:
```python
def get_provider(
    name: str | None = None,
    profile: str | None = None,
    magic: bool = False,
    headless: bool = True,
) -> WebProvider:
    """Keyless web provider factory. Default = the host WebSearch tool adapter.

    Every branch is keyless (host tool / local lib / self-host / local render).
    No env var, no API key. `websearch`/`ddgs`/`searxng` are KR-2 stubs until the
    `web/search/` package lands; `builtin` (httpx Tier-0) and `crawl4ai` (local JS
    render) are real today.
    """
    if name in (None, "websearch", "ddgs", "searxng"):
        from bad_research.web.search.base import get_keyless_provider

        return get_keyless_provider(name or "websearch")

    if name == "builtin":
        from bad_research.web.builtin import BuiltinProvider

        return BuiltinProvider()

    if name == "crawl4ai":
        try:
            from bad_research.web.crawl4ai_provider import Crawl4AIProvider

            return Crawl4AIProvider(profile=profile or None, magic=magic, headless=headless)
        except ImportError:
            raise ImportError("crawl4ai provider requires: pip install bad-research[browse]")

    raise ValueError(
        f"Unknown web provider: {name!r}. Available (all keyless): "
        f"websearch, ddgs, searxng, builtin, crawl4ai"
    )
```

- [ ] **Step 4: Create the KR-2 keyless-provider stub module**

The default branch imports `bad_research.web.search.base.get_keyless_provider`. KR-2 owns `web/search/` but KR-1 must leave a typed stub so the factory resolves. Create `src/bad_research/web/search/__init__.py`:
```python
"""Keyless search layer (KR-2). KR-1 ships only the get_keyless_provider stub."""
```
Create `src/bad_research/web/search/base.py`:
```python
"""Keyless web-provider stubs (KR-2 fills the bodies).

KR-1 leaves typed, named stubs so `web/base.py::get_provider` resolves and the
registry/CLI work. Each `search`/`search_ex`/`fetch` raises NotImplementedError
with a 'KR-2' pointer until the real `web/search/` package lands.
"""

from __future__ import annotations

from bad_research.web.base import SearchQuery, WebResult


class _KeylessStub:
    """A typed keyless WebProvider stub. cost_per_search=0.0 (keyless)."""

    capabilities: frozenset[str] = frozenset({"keyword"})
    cost_per_search: float = 0.0
    p50_ms: int = 0

    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        raise NotImplementedError(f"{self.name} search is built in KR-2 (web/search/)")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        raise NotImplementedError(f"{self.name} search_ex is built in KR-2 (web/search/)")

    def fetch(self, url: str) -> WebResult:
        raise NotImplementedError(f"{self.name} fetch is built in KR-3 (web/content/)")


def get_keyless_provider(name: str = "websearch") -> _KeylessStub:
    """Return a keyless provider stub by name (KR-2 replaces the bodies)."""
    if name not in ("websearch", "ddgs", "searxng"):
        raise ValueError(f"Unknown keyless provider: {name!r}")
    return _KeylessStub(name)
```

- [ ] **Step 5: Delete the `providers/` dir (source + tests)**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm src/bad_research/web/providers/cascade.py \
       src/bad_research/web/providers/searxng_provider.py \
       src/bad_research/web/providers/__init__.py \
       tests/test_web/providers/test_cascade.py \
       tests/test_web/providers/test_searxng_provider.py \
       tests/test_web/providers/__init__.py
```
Expected: six `rm '…'` lines. (The empty `tests/test_web/providers/` dir is left or removed by git automatically.)

- [ ] **Step 6: Run the factory test + verify it passes**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_web/test_provider_factory.py -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS (all five tests).

- [ ] **Step 7: Full suite + commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -4
git add -A
git commit -m "KR-1: keyless get_provider factory; drop cascade + providers/ dir

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
Expected: green (no `web.providers` imports anywhere; `_build_cascade` gone).

---

## Task 5: Rewrite `browse/base.py` + `browse/ladder.py` to the keyless seam

**Files:**
- Modify: `src/bad_research/browse/base.py` (`get_browse_provider`, `get_extract_provider`)
- Modify: `src/bad_research/browse/ladder.py` (`fetch_tiered` signature + `_do_browse`)
- Modify: `tests/test_browse/test_base.py` (drop the browserbase/browseruse/agentql key-gate tests; keep the protocol + llm-default + unknown-None tests)
- Modify: `tests/test_browse/test_ladder.py` (drop the `_browseruse`/`_browserbase` injection tests; keep Tier-0/1/2 + the generic browse-via-`_browse` tests)
- Modify: `tests/test_browse/test_graceful_degradation.py` (drop the browser_use/browserbase/agentql refs; keep the Tier-0-only + extract-no-llm tests)

`get_browse_provider` now returns the keyless `AgentBrowserProvider` **if available** — but KR-4 builds that, so KR-1's stub returns `None` (graceful). `get_extract_provider` keeps the `llm` default, drops `agentql`/`stagehand`. The ladder loses the `_browseruse`/`_browserbase` injection seams; `_do_browse` resolves a single keyless browse provider (a `_browse` injection seam stays for tests).

- [ ] **Step 1: Rewrite `get_browse_provider` + `get_extract_provider`**

In `src/bad_research/browse/base.py`, replace `get_extract_provider` and `get_browse_provider` (everything from `def get_extract_provider(` to end of file) with:
```python
def get_extract_provider(name: str | None = None) -> ExtractProvider | None:
    """Resolve an ExtractProvider. Default = the zero-dep LLM extractor (host model,
    always constructible). `aql` is built in KR-4; unknown/unavailable -> None."""
    if name in (None, "llm"):
        from bad_research.browse.extract_llm import LLMExtractProvider

        return LLMExtractProvider()

    if name == "aql":
        # KR-4 ships browse/aql.py::AqlExtractProvider (ported AgentQL parser +
        # host-model resolver). Until then this rung is simply unavailable.
        return None

    return None


def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    """Resolve a keyless BrowseProvider. Default = the local agent-browser CLI
    (built in KR-4: browse/agent_browser.py::AgentBrowserProvider). Until KR-4
    lands, the backend is unavailable -> return None (graceful: the ladder keeps
    the best lower-tier result). No API key, no cloud SDK — keyless only."""
    if name in (None, "agent-browser"):
        try:
            from bad_research.browse.agent_browser import AgentBrowserProvider
        except ImportError:
            return None
        return AgentBrowserProvider()

    return None
```
(Delete the now-unused `import os` at the top of `browse/base.py` if it's no longer referenced — `ruff` will flag it; remove it.)

- [ ] **Step 2: Rewrite `fetch_tiered` + `_do_browse` in `browse/ladder.py`**

In `src/bad_research/browse/ladder.py`:
1. In `fetch_tiered`'s signature, delete the `_browseruse` and `_browserbase` keyword args; add a single `_browse: Any | None = None` injection seam.
2. Update the `_do_browse(...)` call site inside `fetch_tiered` to pass `browse=_browse` (drop `browseruse=`/`browserbase=`).
3. Replace `_do_browse` entirely with:
```python
def _do_browse(url, instruction, *, anti_bot, replay_key, variables, browse) -> WebResult | None:
    """Resolve the single keyless browse provider (agent-browser, KR-4) and run it.
    Returns None if no provider is available (caller keeps the lower-tier result).
    `anti_bot` is accepted for signature stability but no longer routes to a
    separate cloud backend — the keyless agent-browser handles every case."""
    prov = browse
    if prov is None:
        from bad_research.browse.base import get_browse_provider

        prov = get_browse_provider()
    if prov is None:
        return None
    try:
        return prov.browse(url, instruction, replay_key=replay_key, variables=variables)
    except Exception:
        return None
```
Keep the `_is_empty`/`_is_bot_wall`/Tier-0/Tier-1/Tier-2 logic verbatim; the `want_anti_bot`/`want_login`/`want_interactive` decision stays (it just calls the keyless `_do_browse`).

- [ ] **Step 3: Rewrite the three browse tests**

In `tests/test_browse/test_base.py`: delete `test_get_browse_provider_browseruse_none_when_lib_missing`, `test_get_browse_provider_browserbase_none_without_key`, `test_get_extract_provider_agentql_none_without_key`. Add:
```python
def test_get_browse_provider_default_none_until_kr4() -> None:
    """agent-browser CLI wrapper not built yet (KR-4) -> None, never raises."""
    assert get_browse_provider() is None
    assert get_browse_provider("agent-browser") is None


def test_get_extract_provider_aql_none_until_kr4() -> None:
    assert get_extract_provider("aql") is None
```
Keep `test_browse_protocol_is_runtime_checkable`, `test_extract_protocol_is_runtime_checkable`, `test_browse_signature_accepts_keyword_only_args`, `test_get_extract_provider_default_is_llm`, `test_get_extract_provider_unknown_returns_none`, `test_get_browse_provider_unknown_returns_none`.

In `tests/test_browse/test_ladder.py`: in `test_bot_wall_escalates_to_browserbase`, `test_login_wall_escalates_to_agentic_browse`, `test_instruction_triggers_tier3_browse`, `test_no_browse_provider_stays_on_lower_tier`, `test_replay_key_threaded_to_browse`, replace the `_browserbase=bb`/`_browseruse=bu` kwargs with the single `_browse=` seam (e.g. `_browse=bu`, `_browse=bb`, `_browse=None`). Rename `test_bot_wall_escalates_to_browserbase` → `test_bot_wall_escalates_to_keyless_browse`. Example for the bot-wall test:
```python
def test_bot_wall_escalates_to_keyless_browse() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _bot()
    br = MagicMock(); br.browse.return_value = make_result("Recovered behind cloudflare. " * 20)
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1, _browse=br)
    assert "Recovered behind cloudflare" in r.content
    br.browse.assert_called_once()
```

In `tests/test_browse/test_graceful_degradation.py`: rewrite `_no_optional_imports` to drop `browser_use`/`stagehand` (keep `crawl4ai`); rewrite `test_no_keys_no_libs_factories_return_none` to:
```python
def test_no_libs_factories_return_none(monkeypatch):
    _no_optional_imports(monkeypatch)
    assert get_browse_provider() is None          # agent-browser wrapper not built (KR-4)
    assert get_extract_provider("aql") is None
    assert get_extract_provider("llm") is not None  # host-model extractor always constructible
```
Keep `test_ladder_with_only_tier0_returns_result` (drop the `AGENTQL_API_KEY`/`BROWSERBASE_API_KEY` `delenv` lines) and `test_ladder_extract_no_llm_no_crash` verbatim.

- [ ] **Step 4: Run the browse tests + verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_browse -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: PASS (protocols, llm default, keyless None defaults, Tier-0/1/2 ladder, schema-extract, replay-key threading).

- [ ] **Step 5: Full suite + commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -4
git add -A
git commit -m "KR-1: keyless browse seam (agent-browser stub) + single-provider ladder

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
Expected: green.

---

## Task 6: Delete the Cohere embedder + rewire `embed/base.py` to `[local]` stub

**Files:**
- Delete: `src/bad_research/embed/cohere.py`, `tests/test_embed/test_cohere.py`
- Modify: `src/bad_research/embed/base.py` (`get_embed_provider` default → `bge-local`; drop the cohere branch; trim the docstring)
- Modify: `src/bad_research/embed/__init__.py` (docstring only)
- Modify: `tests/test_embed/test_base.py` (rewrite unknown-provider + add a `bge-local` import-guard test)

The `EmbedProvider` Protocol STAYS (it's a kept seam). The default flips to `bge-local`, which lives behind `[local]` — KR-5 creates `embed/bge_local.py`. KR-1's `get_embed_provider("bge-local")` import-guards it and raises a helpful `ImportError` until then.

- [ ] **Step 1: Write the failing test**

Replace the contents of `tests/test_embed/test_base.py` with:
```python
"""EmbedProvider seam: Protocol + keyless factory (default bge-local, [local])."""

from __future__ import annotations

import importlib.util

import pytest

from bad_research.embed.base import EmbedProvider, get_embed_provider


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown embed provider"):
        get_embed_provider("does-not-exist")


def test_protocol_is_runtime_checkable() -> None:
    class _Fake:
        name = "fake"
        dim = 8

        def embed(self, texts, *, input_type):
            return [[0.0] * self.dim for _ in texts]

    assert isinstance(_Fake(), EmbedProvider)


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="[local] extra not installed (sentence-transformers / bge_local)",
)
def test_bge_local_is_default() -> None:
    prov = get_embed_provider()  # default -> bge-local
    assert prov.name.startswith("bge")


def test_bge_local_raises_helpful_without_local_extra() -> None:
    """Without [local] (or before KR-5 builds embed/bge_local.py), the default
    raises ImportError with an install hint — never a bare ModuleNotFoundError."""
    if importlib.util.find_spec("bad_research.embed.bge_local") is not None:
        pytest.skip("embed/bge_local.py exists (KR-5 landed)")
    with pytest.raises(ImportError, match=r"local"):
        get_embed_provider("bge-local")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_embed/test_base.py -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: FAIL — `get_embed_provider()` still defaults to `cohere`; the `bge-local` branch does not exist.

- [ ] **Step 3: Delete the cohere module + rewrite the factory**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm src/bad_research/embed/cohere.py tests/test_embed/test_cohere.py
```
Replace the entire contents of `src/bad_research/embed/base.py` with:
```python
"""Base Protocol + keyless factory for the EmbedProvider seam.

The neural recall lane is OPTIONAL ([local] extra). Default impl:
BgeLocalEmbedProvider (bge-small-en-v1.5, dim 384) — built in KR-5
(embed/bge_local.py). KR-1 leaves the Protocol + an import-guarded factory.
Cohere (the old API embedder) is removed — pure keyless.
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
    """Load an embed provider by name. Default = the local BGE bi-encoder ([local]).

    Keyless: no API embedder. The dense lane is opt-in — installed via
    `pip install bad-research[local]` and built in KR-5 (embed/bge_local.py).
    """
    if name == "bge-local":
        try:
            from bad_research.embed.bge_local import BgeLocalEmbedProvider
        except ImportError as exc:
            raise ImportError(
                'bge-local requires the local neural stack: '
                'pip install "bad-research[local]" (built in KR-5)'
            ) from exc
        return BgeLocalEmbedProvider(**kwargs)

    raise ValueError(f"Unknown embed provider: {name!r}. Available: bge-local")
```
Update `src/bad_research/embed/__init__.py`'s docstring line to:
```python
"""EmbedProvider seam — keyless; the local bi-encoder lane is opt-in ([local])."""
```
(keep the `from bad_research.embed.base import EmbedProvider, get_embed_provider` + `__all__` lines verbatim).

- [ ] **Step 4: Run the embed test + verify it passes**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_embed -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS. `test_bge_local_is_default` SKIPs (sentence-transformers absent), `test_bge_local_raises_helpful_without_local_extra` PASSES (ImportError with "local").

- [ ] **Step 5: Commit (full-suite green check deferred to Task 9 — engine still imports cohere via embedder param; that is fixed in Tasks 7-8)**

> NOTE: at this point `cli/research.py::_build_embedder` still calls `get_embed_provider("cohere", ...)` → now raises `ValueError`. That path is only hit by `tests/test_pipeline/test_build_real.py`, which Task 8 rewrites. To keep the suite green BETWEEN tasks, run the targeted commit but DO NOT run the full no-cov suite as the gate here — Tasks 7→8 restore full green. If you prefer a strictly-green-every-commit discipline, fold Tasks 6+7+8 into one commit; they are split here for review clarity.

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_embed tests/test_retrieval -q -p no:cacheprovider --no-cov 2>&1 | tail -4
git add -A
git commit -m "KR-1: remove Cohere embedder; keyless bge-local default ([local] stub)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
Expected: `test_embed` green; `test_retrieval` still references Cohere reranker + LanceChunkStore (fixed in Tasks 7-8) — `test_rerank.py`/`test_store.py`/`test_engine.py` may fail here; that is expected and resolved next.

---

## Task 7: Delete `CohereReranker`, add the `ClaudeCodeReranker` stub, rewrite `get_reranker`

**Files:**
- Modify: `src/bad_research/retrieval/rerank.py` (delete `CohereReranker`; add `ClaudeCodeReranker` stub; rewrite `get_reranker` → host/local/none)
- Modify: `tests/test_retrieval/test_rerank.py` (rewrite around the keyless reranker)

`BGEReranker` + `Scorer` + `_default_bge_scorer` STAY (they move behind `[local]` but the code is import-guarded already — `_default_bge_scorer` only imports FlagEmbedding/sentence-transformers when constructed without an injected scorer). The new default is `ClaudeCodeReranker` (a host-model stub KR-5 fills).

- [ ] **Step 1: Write the failing test**

Replace the contents of `tests/test_retrieval/test_rerank.py` with:
```python
import pytest

from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import BGEReranker, ClaudeCodeReranker, get_reranker


def test_claude_code_reranker_is_a_reranker() -> None:
    rr = ClaudeCodeReranker()
    assert isinstance(rr, Reranker)


def test_claude_code_reranker_rerank_is_kr5_stub() -> None:
    """KR-1 ships the type; KR-5 fills the host-model body."""
    rr = ClaudeCodeReranker()
    with pytest.raises(NotImplementedError, match="KR-5"):
        rr.rerank("q", ["a", "b"])


def test_get_reranker_default_is_host() -> None:
    class _Cfg:
        reranker = "host"

    rr = get_reranker(_Cfg())
    assert isinstance(rr, ClaudeCodeReranker)


def test_get_reranker_none_is_identity() -> None:
    class _Cfg:
        reranker = "none"

    rr = get_reranker(_Cfg())
    out = rr.rerank("q", ["a", "b", "c"])
    # identity: original order, descending pseudo-scores, stable.
    assert [i for i, _ in out] == [0, 1, 2]
    assert len(out) == 3


def test_get_reranker_local_is_bge_with_injected_scorer() -> None:
    class _Cfg:
        reranker = "local"

    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    assert isinstance(rr, BGEReranker)
    out = rr.rerank("q", ["a", "b", "c"])
    assert [i for i, _ in out] == [0, 1, 2]  # ties -> stable index order
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_retrieval/test_rerank.py -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: FAIL — `ClaudeCodeReranker` does not exist; `get_reranker` still keys off `rerank_model`/`COHERE_API_KEY`.

- [ ] **Step 3: Rewrite `retrieval/rerank.py`**

Replace lines 1–38 (the module docstring through the end of `class CohereReranker`) and the `get_reranker` function at the bottom. Concretely:
1. Delete `import os` (no longer used) and the `class CohereReranker:` block (lines ~23–37).
2. Rewrite the module docstring (lines 1–12) to:
```python
"""Rerankers behind the Reranker Protocol (keyless).

Default: ClaudeCodeReranker (host-model LLM-rerank; the body lands in KR-5 — KR-1
ships the typed stub). Local: BGEReranker (ms-marco-MiniLM / bge-reranker) behind
the [local] extra. None: identity (sort by the engine's initial score).

The old CohereReranker is removed — pure keyless, no COHERE_API_KEY.
"""
```
3. Add the keyless reranker classes (place after the `Scorer` type alias, before `_default_bge_scorer`):
```python
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
```
4. Replace `get_reranker` with:
```python
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
```
(Keep `_default_bge_scorer` and `class BGEReranker` verbatim.)

- [ ] **Step 4: Run the rerank test + verify it passes**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_retrieval/test_rerank.py -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: remove CohereReranker; ClaudeCodeReranker stub + host/local/none factory

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Make the vector lane optional in `RetrievalEngine` (FTS-default) + demote LanceDB to `[local]`

**Files:**
- Modify: `src/bad_research/retrieval/engine.py` (`__init__` takes `embedder: EmbedProvider | None = None`, `lance_dir: Path | None = None`; lazy `LanceChunkStore` import; FTS-only `_one_round`)
- Delete: `tests/test_retrieval/test_store.py` (LanceChunkStore test moves behind a `local` marker in KR-5)
- Modify: `tests/test_retrieval/test_engine.py` (construct FTS-only)
- Keep `src/bad_research/retrieval/store.py` (it still exists, but is only imported lazily when `lance_dir` is set)

The engine becomes FTS-default. When `embedder is None` (the keyless default), `initial_score` = min-max(BM25) and the LanceDB store is never constructed (so `lancedb`/`pyarrow` are not imported). When a `[local]` embedder + `lance_dir` are passed (KR-5), the hybrid lane re-activates verbatim.

- [ ] **Step 1: Write the failing test (FTS-only engine)**

In `tests/test_retrieval/test_engine.py`, replace the `_engine` helper (lines ~21–27) with:
```python
def _engine(tmp_path, _stub_embedder=None):
    # FTS-only keyless default: no embedder, no lance_dir.
    return RetrievalEngine(
        cache_db=tmp_path / "cache.db",
        reranker=_IdentityReranker(),
    )
```
and update every test that calls `_engine(tmp_path, stub_embedder)` to call `_engine(tmp_path)` (the `stub_embedder` fixture is no longer needed for the engine; drop the fixture arg from the five test signatures: `test_index_then_search_returns_relevant_chunk_first`, `test_relevance_gate_drops_low_scoring_chunks`, `test_source_type_weight_boosts_code`, `test_semantic_cache_hit_on_repeat_query`, `test_cache_miss_when_negation_added`).

Also update `_IdentityReranker` to NOT be the KR-5 stub — keep the local fake at the top of the file verbatim (it already returns real scores).

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_retrieval/test_engine.py -q -p no:cacheprovider --no-cov 2>&1 | tail -10`
Expected: FAIL — `RetrievalEngine.__init__` still requires `lance_dir` + `embedder` positionally; `SemanticCache(Path(cache_db), embedder)` passes `None` to a cache that expects an embedder.

- [ ] **Step 3: Rewrite `RetrievalEngine`**

In `src/bad_research/retrieval/engine.py`:
1. Change the top-level `from bad_research.retrieval.store import LanceChunkStore` to a lazy import (delete the top-level line; import inside `__init__`/`_one_round` only when `lance_dir` is set).
2. Replace `__init__` (lines ~46–63) with:
```python
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
```
2a. Add the lexical-shim embedder near the top of `engine.py` (after `_ChunkMeta`, before `class RetrievalEngine`). It is a deterministic, keyless token-hash embedder (dim 64) used ONLY to keep `SemanticCache` functional on the FTS-only path — it is NOT a neural model and pulls no deps:
```python
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
```
3. In `index`, guard the embed + upsert with `if self.embedder is not None and self.store is not None:`; ALWAYS index FTS. Concretely, wrap the vector-embed block so FTS-only indexing still runs:
```python
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
        if self.embedder is not None and self.store is not None:
            for i in range(0, len(embed_texts), EMBED_BATCH_CAP):
                batch = embed_texts[i:i + EMBED_BATCH_CAP]
                vectors.extend(self.embedder.embed(batch, input_type="document"))
        rows: list[dict[str, Any]] = []
        for idx, (chunk, ct) in enumerate(zip(pending, ct_for, strict=True)):
            if vectors:
                rows.append({"chunk_id": chunk.chunk_id, "vector": vectors[idx],
                             "note_id": chunk.note_id, "char_start": chunk.char_start,
                             "char_end": chunk.char_end, "model": self.embedder.name,
                             "dim": self.embedder.dim})
            fts_rows.append({"chunk_id": chunk.chunk_id, "body": chunk.text, "note_id": chunk.note_id})
            self._meta[chunk.chunk_id] = _ChunkMeta(chunk, ct)
        if rows and self.store is not None:
            self.store.upsert(rows)
            self.store.maybe_build_index()
        index_chunk_fts(self.conn, fts_rows)
```
4. In `_one_round`, branch on the embedder. Replace the vector block (lines ~121–130) with:
```python
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
                lo = min(bm_scores.values()); hi = max(bm_scores.values())
                rng = (hi - lo) or 1.0
                fused_initial = {cid: (s - lo) / rng for cid, s in bm_scores.items()}
            else:
                fused_initial = {}
```
(Keep the rest of `_one_round` — the rerank/three-tier/gate/pass-fraction logic — verbatim.)

- [ ] **Step 4: Delete the LanceDB store test**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git rm tests/test_retrieval/test_store.py
```
(KR-5 re-adds it under a `local` marker.)

- [ ] **Step 5: Run the retrieval tests + verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_retrieval -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: PASS. The engine tests now run FTS-only (the IdentityReranker fake gives chunks containing query tokens score 0.95 → clear the 0.70 gate; min-max BM25 + three-tier fusion keeps the relevant note first).

> RISK NOTE: if `test_source_type_weight_boosts_code` or the gate test goes red under FTS-only scoring (different `initial` scale than hybrid), adjust ONLY the test's note bodies so the relevant chunk clears 0.70 — do NOT change `RELEVANCE_GATE` or the fusion math (frozen constants). The three-tier blend leans on rank when `initial` is min-maxed; a single relevant chunk maps to `initial=1.0` (it is both min and max alone or top), so rank-1 × reranker 0.95 clears the gate. Verify empirically; tune note text, never constants.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: RetrievalEngine FTS-default; LanceDB vector lane optional ([local])

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Rewrite `config.py` keyless knobs

**Files:**
- Modify: `src/bad_research/config.py` (drop `embed_model`/`rerank_model` + their TOML/env plumbing; add `reranker`/`neural_recall`/`searxng_endpoint`/`browse_engine`/`effort`/`max_tokens`)
- Modify: `tests/test_config/test_config.py` (rewrite the default + TOML asserts)

- [ ] **Step 1: Write the failing test**

In `tests/test_config/test_config.py`:
- In `test_defaults_match_interfaces`, delete `assert cfg.embed_model == "embed-english-v3.0"` and `assert cfg.rerank_model == "rerank-v3.5"`; add:
```python
    assert cfg.reranker == "host"
    assert cfg.neural_recall is False
    assert cfg.searxng_endpoint == "http://localhost:8080"
    assert cfg.browse_engine == "lightpanda"
    assert cfg.effort == "medium"
    assert cfg.max_tokens is None
```
- In `test_load_returns_defaults_when_no_env_no_toml`, replace `assert cfg.embed_model == "embed-english-v3.0"` with `assert cfg.reranker == "host"`.
- Rewrite `test_toml_overrides_default` so the TOML sets keyless knobs instead of `embed_model`/`rerank_model`:
```python
def test_toml_overrides_default(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        "[bad-research]\n"
        "budget_usd = 7.0\n"
        "cheap = true\n"
        'reranker = "local"\n'
        'browse_engine = "chrome"\n'
        'searxng_endpoint = "http://searx.local:9000"\n'
        'vault_root = "/tmp/custom-vault"\n'
    )
    cfg = BadResearchConfig.load(config_path=toml)
    assert cfg.budget_usd == 7.0
    assert cfg.cheap is True
    assert cfg.reranker == "local"
    assert cfg.browse_engine == "chrome"
    assert cfg.searxng_endpoint == "http://searx.local:9000"
    assert cfg.vault_root == Path("/tmp/custom-vault")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_config -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: FAIL — `cfg.reranker`/`cfg.searxng_endpoint`/etc. don't exist; the default asserts on `embed_model`/`rerank_model`.

- [ ] **Step 3: Rewrite `config.py`**

In `src/bad_research/config.py`:
1. Add `from typing import Literal` to the imports.
2. In the `BadResearchConfig` dataclass, delete the two lines:
```python
    embed_model: str = "embed-english-v3.0"  # Cohere
    rerank_model: str = "rerank-v3.5"      # Cohere; "bge-reranker-v2-m3" offline
```
and add (after `cheap: bool = False`):
```python
    # ── Keyless knobs (KR-1; dossier 13/15/16) ──────────────────────────────
    reranker: Literal["host", "local", "none"] = "host"   # host-model LLM-rerank default
    neural_recall: bool = False                            # opt-in local bi-encoder lane ([local])
    searxng_endpoint: str = "http://localhost:8080"        # self-host T1; no key
    browse_engine: Literal["lightpanda", "chrome"] = "lightpanda"  # rung-2.5 default (dossier 14)
    effort: Literal["minimal", "low", "medium", "high"] = "medium"  # KR-6 effort continuum
    max_tokens: int | None = None                          # KR-6 per-run ceiling (opt-in)
```
3. In `load()`'s TOML layer, delete the two blocks:
```python
            if "embed_model" in section:
                cfg.embed_model = section["embed_model"]
            if "rerank_model" in section:
                cfg.rerank_model = section["rerank_model"]
```
and add:
```python
            if "reranker" in section:
                cfg.reranker = section["reranker"]
            if "neural_recall" in section:
                cfg.neural_recall = bool(section["neural_recall"])
            if "searxng_endpoint" in section:
                cfg.searxng_endpoint = str(section["searxng_endpoint"])
            if "browse_engine" in section:
                cfg.browse_engine = section["browse_engine"]
            if "effort" in section:
                cfg.effort = section["effort"]
            if "max_tokens" in section:
                cfg.max_tokens = int(section["max_tokens"])
```
4. In `load()`'s env layer, delete the two blocks:
```python
        if (v := os.environ.get("BAD_RESEARCH_EMBED_MODEL")) is not None:
            cfg.embed_model = v
        if (v := os.environ.get("BAD_RESEARCH_RERANK_MODEL")) is not None:
            cfg.rerank_model = v
```
and add:
```python
        if (v := os.environ.get("BAD_RESEARCH_RERANKER")) is not None:
            cfg.reranker = v  # type: ignore[assignment]
        if (v := os.environ.get("BAD_RESEARCH_NEURAL_RECALL")) is not None:
            cfg.neural_recall = _parse_bool(v)
        if (v := os.environ.get("BAD_RESEARCH_SEARXNG_ENDPOINT")) is not None:
            cfg.searxng_endpoint = v
        if (v := os.environ.get("BAD_RESEARCH_EFFORT")) is not None:
            cfg.effort = v  # type: ignore[assignment]
        if (v := os.environ.get("BAD_RESEARCH_MAX_TOKENS")) is not None:
            cfg.max_tokens = int(v)
```

- [ ] **Step 4: Run the config test + verify it passes**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_config -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: keyless config knobs (reranker/searxng_endpoint/browse_engine/effort); drop Cohere defaults

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Rewrite the provider registry (`providers.py`) to keyless rows

**Files:**
- Modify: `src/bad_research/providers.py` (`PROVIDERS` → keyless rows only)
- Modify: `tests/test_providers.py` (rewrite assertions)
- Modify: `tests/test_packaging/test_doctor.py` (rewrite the tavily env-key assertion)

The registry powers `bad doctor`. Every keyless row has `env_var=None` so `requires_key` is `False` and `active` reduces to `import_present`. The `Provider`/`ProviderStatus` dataclasses + `provider_status`/`active_providers` logic stay verbatim.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_providers.py` with:
```python
"""Keyless provider registry: every row is keyless (requires_key False)."""

from __future__ import annotations

from bad_research.providers import (
    PROVIDERS,
    ProviderStatus,
    active_providers,
    provider_status,
)


def test_registry_is_keyless_only():
    names = {p.name for p in PROVIDERS}
    # keyless rows present
    assert {"anthropic-host", "websearch", "ddgs", "searxng", "agent-browser"} <= names
    # no keyed provider survives KR-1
    for gone in ("cohere", "tavily", "exa", "firecrawl", "agentql", "browserbase", "browser_use", "sonar"):
        assert gone not in names


def test_every_provider_requires_no_key():
    for s in provider_status():
        assert s.requires_key is False, f"{s.name} still requires a key"
        assert s.key_present is True  # no key required -> always "present"


def test_active_reduces_to_import_present():
    for s in provider_status():
        assert s.active == s.import_present


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")


def test_active_providers_subset():
    active = active_providers()
    assert all(s.active for s in active)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_providers.py -q -p no:cacheprovider --no-cov 2>&1 | tail -8`
Expected: FAIL — the registry still lists cohere/tavily/exa/etc. with `env_var` set.

- [ ] **Step 3: Rewrite `PROVIDERS`**

In `src/bad_research/providers.py`, replace the `PROVIDERS` tuple (lines ~26–38) with:
```python
PROVIDERS: tuple[Provider, ...] = (
    Provider("anthropic-host", None, "anthropic", "(base)", "llm"),    # host supplies inference; no key
    Provider("websearch", None, None, "(base)", "search"),             # host WebSearch tool (KR-2)
    Provider("ddgs", None, "ddgs", "(base)", "search"),                # keyless multi-engine lib (KR-2)
    Provider("searxng", None, None, "(base)", "search"),               # self-host JSON, no key (KR-2)
    Provider("crawl4ai", None, "crawl4ai", "browse", "browse"),        # local JS render
    Provider("agent-browser", None, None, "browse", "browse"),         # local CLI (CDP); KR-4
    Provider("arxiv", None, None, "(base)", "search"),                 # keyless vertical (httpx); KR-2
    Provider("openalex", None, None, "(base)", "search"),
    Provider("crossref", None, None, "(base)", "search"),
    Provider("europepmc", None, None, "(base)", "search"),
    Provider("pubmed", None, None, "(base)", "search"),
    Provider("wikipedia", None, None, "(base)", "search"),
    Provider("bge-local", None, "sentence_transformers", "local", "embed"),     # [local] opt-in; KR-5
    Provider("ms-marco-local", None, "sentence_transformers", "local", "rerank"),
    Provider("nli-deberta", None, "sentence_transformers", "local", "nli"),
)
```
(`anthropic-host` keeps `import_name="anthropic"` so `bad doctor` can report whether the headless/calibration bridge is usable; it requires no key in the skill path.)

- [ ] **Step 4: Rewrite `test_doctor.py`'s key-env assertions**

In `tests/test_packaging/test_doctor.py`:
- Replace `test_doctor_reports_active_from_env` with:
```python
def test_doctor_lists_keyless_providers(monkeypatch):
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["websearch"]["requires_key"] is False
    assert by_name["ddgs"]["requires_key"] is False
```
- Replace `test_doctor_searxng_always_keyless` body's `by_name["searxng"]["requires_key"] is False` assertion (it stays valid — `searxng` is still a row).
- Keep `test_doctor_runs` (assert `"anthropic" in result.output.lower()` — `anthropic-host` contains "anthropic", still passes) and `test_doctor_includes_vault_path` verbatim.

- [ ] **Step 5: Run the registry + doctor tests + verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_providers.py tests/test_packaging/test_doctor.py -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: keyless provider registry (no keyed rows; requires_key=False everywhere)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Rewire the `cli/research.py` builders (FTS-only, keyless reranker) + fix `test_build_real.py`

**Files:**
- Modify: `src/bad_research/cli/research.py` (`_build_embedder` → `None`; `_build_reranker` → `get_reranker(cfg)`; `_build_engine` → FTS-only)
- Modify: `tests/test_pipeline/test_build_real.py` (rewrite the cohere/lance builder tests; keep the anthropic verify-citations test)

`_build_embedder` returns `None` (keyless FTS-only default; KR-5/`[local]` opt-in re-enables the dense lane). `_build_reranker` returns `get_reranker(cfg)` — now reads `cfg.reranker` (default `"host"` → `ClaudeCodeReranker`). `_build_engine` constructs the engine with `embedder=None`, `lance_dir=None`. The verify-citations LLM builder is untouched (anthropic stays core).

- [ ] **Step 1: Write the failing test**

Replace the contents of `tests/test_pipeline/test_build_real.py` with:
```python
"""REAL builder-path integration tests (KR-1 keyless rewire).

The pipeline/CLI tests monkeypatch the stage SEAMS, so the dependency-construction
lines inside cli/research.py never executed. These exercise the ACTUAL builder
helpers to catch wrong import names / broken keyless wiring.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.config import BadResearchConfig
from bad_research.llm.base import LLMProvider
from bad_research.retrieval.rerank import ClaudeCodeReranker


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import anthropic

    client = MagicMock()
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=client))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return client


def test_build_embedder_is_none_keyless_default():
    from bad_research.cli.research import _build_embedder

    cfg = BadResearchConfig()  # default: FTS-only, no neural recall
    assert _build_embedder(cfg) is None


def test_build_reranker_default_is_claude_code():
    from bad_research.cli.research import _build_reranker

    cfg = BadResearchConfig()  # default reranker = "host"
    rr = _build_reranker(cfg)
    assert isinstance(rr, ClaudeCodeReranker)


def test_build_engine_constructs_fts_only_engine(tmp_path):
    from bad_research.cli.research import _build_engine
    from bad_research.retrieval.engine import RetrievalEngine

    cfg = BadResearchConfig()
    vault = SimpleNamespace(root=tmp_path)  # _build_engine only reads .root
    engine = _build_engine(cfg, vault)

    assert isinstance(engine, RetrievalEngine)
    assert engine.embedder is None          # keyless FTS-only
    assert engine.store is None             # no LanceDB constructed
    assert isinstance(engine.reranker, ClaudeCodeReranker)
    assert (tmp_path / ".bad-research").is_dir()


def test_verify_report_builds_real_llm_provider(monkeypatch, tmp_path):
    """anthropic stays a CORE dep: the verify-citations LLM builder runs for real."""
    _patch_anthropic(monkeypatch)

    import bad_research.cli.research as research
    import bad_research.config as config_mod
    import bad_research.core.vault as vault_mod
    import bad_research.grounding.anchors as anchors_mod
    import bad_research.grounding.nli as nli_mod
    import bad_research.grounding.verifier as verifier_mod

    built = {}

    class _FakeNLI:
        def __init__(self, *a, **k):
            pass

    class _FakeVerifier:
        def __init__(self, *, nli, llm):
            built["llm"] = llm

        def verify(self, report_md, store, note_bodies):
            return SimpleNamespace(findings=[])

    monkeypatch.setattr(nli_mod, "CrossEncoderNLI", _FakeNLI)
    monkeypatch.setattr(verifier_mod, "CitationVerifier", _FakeVerifier)
    monkeypatch.setattr(anchors_mod, "AnchorStore", lambda conn: MagicMock())

    vault = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(vault_mod.Vault, "discover", staticmethod(lambda: vault))
    monkeypatch.setattr(config_mod.BadResearchConfig, "load", classmethod(lambda cls: cls()))

    report = tmp_path / "report.md"
    report.write_text("The answer is X [1].", encoding="utf-8")

    out = research._verify_report(str(report), vault_tag="t")
    assert out == []
    assert isinstance(built["llm"], LLMProvider)
    assert built["llm"].name == "anthropic"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_pipeline/test_build_real.py -q -p no:cacheprovider --no-cov 2>&1 | tail -10`
Expected: FAIL — `_build_embedder` still calls `get_embed_provider("cohere", ...)` (now raises `ValueError`); `_build_engine` still passes `lance_dir`/`embedder`.

- [ ] **Step 3: Rewrite the three builders in `cli/research.py`**

In `src/bad_research/cli/research.py`:
1. Replace `_build_engine` (lines ~132–146) with:
```python
def _build_engine(cfg: object, vault: object) -> object:
    """Construct a keyless FTS-only RetrievalEngine bound to the vault's cache dir.

    The dense vector lane (LanceDB + a [local] embedder) is opt-in — None here by
    default. KR-5 turns it on above the 25k-chunk threshold or when neural_recall=1.
    """
    from bad_research.retrieval.engine import RetrievalEngine

    root = Path(getattr(vault, "root", Path.cwd()))
    base = root / ".bad-research"
    base.mkdir(parents=True, exist_ok=True)
    embedder = _build_embedder(cfg)
    lance_dir = (base / "lance") if embedder is not None else None
    return RetrievalEngine(
        cache_db=base / "semantic_cache.db",
        reranker=_build_reranker(cfg),
        embedder=embedder,
        lance_dir=lance_dir,
    )
```
2. Replace `_build_embedder` (lines ~149–154) with:
```python
def _build_embedder(cfg: object) -> object | None:
    """Keyless default = no neural embedder (FTS-only). The local bi-encoder lane
    ([local]) is opt-in via config.neural_recall — built in KR-5. Returns None
    unless neural recall is explicitly enabled AND the [local] stack imports."""
    if not getattr(cfg, "neural_recall", False):
        return None
    try:
        from bad_research.embed.base import get_embed_provider

        return get_embed_provider("bge-local")
    except ImportError:
        return None  # [local] not installed -> degrade to FTS-only (graceful)
```
3. Replace `_build_reranker` (lines ~157–162) with:
```python
def _build_reranker(cfg: object) -> object:
    """Keyless reranker: get_reranker reads cfg.reranker (default "host" ->
    ClaudeCodeReranker, the host-model LLM-rerank). "local"/"none" also keyless."""
    from bad_research.retrieval.rerank import get_reranker

    return get_reranker(cfg)
```

- [ ] **Step 4: Run the builder test + verify it passes**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_pipeline/test_build_real.py -q -p no:cacheprovider --no-cov 2>&1 | tail -6`
Expected: PASS (4 tests).

- [ ] **Step 5: Full suite (no-cov) — first all-green checkpoint since Task 5**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest -q -p no:cacheprovider --no-cov 2>&1 | tail -5`
Expected: all green (0 failed, 0 errors). Note the passed count (should be ~470 after deletions). If anything is red, fix it before committing (most likely a missed `_build_providers` reference — see RISK below).

> RISK NOTE: `cli/research.py::_build_providers` still calls `get_provider("builtin")` (real, kept). It does NOT need changing in KR-1 (KR-6 rewires it to the keyless search providers). Leave it. `_build_tiered_fetcher` references `TieredFetcher` (which never existed — it's wrapped in `try/except` returning `None`); leave it (KR-4/KR-6 build the real tiered fetcher).

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: keyless cli/research builders (FTS-only engine, ClaudeCodeReranker default)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Slim `pyproject.toml` to the lean keyless base + extras + coverage omit

**Files:**
- Modify: `pyproject.toml` (core deps; delete `[search]`; redefine `[browse]`/`[local]`/`[all]`; extend `[tool.coverage.run] omit`)
- Modify: `tests/test_packaging/test_pyproject.py` (rewrite the extras/lean-base assertions)

The lean core drops `lancedb`/`pyarrow` (vector store → `[local]`) but **KEEPS `numpy`** — `grounding/nli.py` (a kept core module) imports `numpy` directly in `predict()` and `tests/test_grounding/test_nli.py` injects a stub CrossEncoder so that path runs WITHOUT sentence-transformers (so numpy is hit on the non-`[local]` test path). The contract §7 lean set omits numpy; that is an oversight — keeping it is the correct, verified call. Core also adds the keyless content/search deps (`crawl4ai`, `ddgs`, `pymupdf4llm`, `trafilatura`, `beautifulsoup4`, `lxml`, `rank-bm25`, `snowballstemmer`, `dateparser`, `feedparser`). `anthropic` STAYS core. `[search]` is deleted. `[browse]` = `["playwright>=1.40"]`. `[local]` = torch/sentence-transformers/lancedb/pyarrow. `[grounding]` folds into `[local]` (the NLI model lives there). The coverage `omit` gains the KR-2/KR-5 stub files so the floor reflects only tested keyless surface.

> Per the resolved decisions: `crawl4ai` moves INTO core (the keyless content pipeline KR-3 needs its PruningContentFilter/JS render). This is heavier than a pure-stdlib base but is keyless and is what the dossiers require. `test_pyproject.py`'s `HEAVY_FORBIDDEN_IN_BASE` set is updated to drop `crawl4ai` from the forbidden list (it is now an intentional keyless core dep) while keeping torch/cohere/tavily/etc. forbidden.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_packaging/test_pyproject.py`'s Task-2 section (everything from `HEAVY_FORBIDDEN_IN_BASE = {` to end of file) with:
```python
# Keyed / paid SDKs + the GPU stack that MUST NOT be in the keyless base.
HEAVY_FORBIDDEN_IN_BASE = {
    "cohere",
    "tavily-python",
    "exa-py",
    "browser-use",
    "agentql",
    "stagehand",
    "firecrawl-py",
    "sentence-transformers",
    "torch",
    "lancedb",
    "pyarrow",
    "playwright",
    "FlagEmbedding",
}


def _names(dep_list: list[str]) -> set[str]:
    out = set()
    for d in dep_list:
        name = d.split(";")[0].strip()
        for sep in (">=", "==", "~=", "<", ">", "[", " "):
            name = name.split(sep)[0]
        out.add(name.strip())
    return out


def test_base_install_is_lean(pp):
    base = _names(pp["project"]["dependencies"])
    leaked = (base & {n.lower() for n in HEAVY_FORBIDDEN_IN_BASE}) | (base & HEAVY_FORBIDDEN_IN_BASE)
    assert not leaked, f"keyed/heavy deps leaked into base: {leaked}"
    # base carries the keyless essentials (numpy stays: grounding/nli.py imports it directly)
    assert {"anthropic", "httpx", "typer", "pymupdf", "crawl4ai", "ddgs", "trafilatura", "numpy"} <= base


def test_base_has_no_torch_lancedb_or_keyed_sdk(pp):
    base = pp["project"]["dependencies"]
    for forbidden in ("torch", "lancedb", "pyarrow", "cohere", "tavily", "exa-py", "playwright"):
        assert all(forbidden not in d for d in base), f"{forbidden} leaked into base"


def test_search_extra_is_gone(pp):
    extras = pp["project"]["optional-dependencies"]
    assert "search" not in extras, "the [search] extra must be deleted (pure keyless)"


def test_extras_groups_exist(pp):
    extras = pp["project"]["optional-dependencies"]
    for group in ("browse", "local", "mcp", "all", "dev"):
        assert group in extras, f"missing extras group: {group}"


def test_browse_extra_is_playwright_only(pp):
    browse = _names(pp["project"]["optional-dependencies"]["browse"])
    assert "playwright" in browse
    for gone in ("browser-use", "agentql", "crawl4ai"):
        assert gone not in {n.lower() for n in browse}


def test_local_extra_holds_the_neural_stack(pp):
    local = _names(pp["project"]["optional-dependencies"]["local"])
    assert {"torch", "sentence-transformers", "lancedb", "pyarrow"} <= local


def test_all_composes_extras(pp):
    all_dep = pp["project"]["optional-dependencies"]["all"]
    assert any("bad-research[" in d for d in all_dep)
```
(Keep the Task-1 metadata tests `test_project_name_and_python`, `test_entry_points`, `test_wheel_packages` verbatim.)

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest tests/test_packaging/test_pyproject.py -q -p no:cacheprovider --no-cov 2>&1 | tail -10`
Expected: FAIL — `lancedb`/`pyarrow` still in base; `[search]` still present; `[local]` missing; `[browse]` still has crawl4ai/browser-use.

- [ ] **Step 3: Rewrite `pyproject.toml`'s deps + extras**

Replace the `dependencies = [ … ]` block (lines ~27–44) with:
```toml
# Lean, zero-key keyless base: deterministic content pipeline + keyless search libs
# + the LLM seam. Heavy/optional stacks (Playwright, neural rerank/recall, LanceDB)
# live behind named extras. anthropic STAYS core (headless/calibration bridge).
dependencies = [
    "anthropic>=0.40",
    "httpx>=0.27",
    "numpy>=1.26",
    "crawl4ai>=0.4",
    "ddgs>=9.14",
    "pymupdf>=1.24",
    "pymupdf4llm>=0.0.17",
    "trafilatura>=1.8",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "rank-bm25>=0.2",
    "snowballstemmer>=2.2",
    "dateparser>=1.2",
    "feedparser>=6.0",
    "typer>=0.9.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "jinja2>=3.1",
    "platformdirs>=4.0",
    "tree-sitter>=0.23",
    "tree-sitter-language-pack>=0.7",
    "rapidfuzz>=3.0",
    "langdetect>=1.0.9",
]
```
Replace the entire `[project.optional-dependencies]` block (lines ~46–79) with:
```toml
[project.optional-dependencies]
# Optional Playwright path (crawl4ai pulls its own Chromium otherwise). agent-browser
# + lightpanda + yt-dlp + git are EXTERNAL keyless CLIs the skill drives — NOT pip deps.
browse = ["playwright>=1.40"]
# Offline neural stack — opt-in, lazy-downloaded. The ONLY place torch/lancedb live.
# Holds the NLI verifier (nli-deberta-v3-base) + bge bi-encoder + ms-marco reranker.
local = [
    "torch>=2.0",
    "sentence-transformers>=3.0",
    "lancedb>=0.13",
    "pyarrow>=15.0",
]
mcp = ["mcp>=1.6"]
all = ["bad-research[browse,local,mcp]"]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
    "respx>=0.21",
    "mcp>=1.6",
]
```

- [ ] **Step 4: Extend the coverage `omit` list so the floor reflects tested keyless surface**

In `pyproject.toml`'s `[tool.coverage.run] omit = [ … ]`, the deleted files (`web/exa_provider.py`, `web/providers/*`, `embed/cohere.py`, `retrieval/store.py` test) no longer exist, so their lines vanish. Remove the now-dead omit entries `"*/web/builtin.py"` and `"*/web/crawl4ai_provider.py"` ONLY if they were there for the providers (they were inherited-provider omits — leave them, they are still real files). ADD these KR-2/KR-5 stub files (whose real coverage lands in a later KR):
```toml
    # KR-1 keyless stubs (real coverage lands in KR-2/KR-5)
    "*/web/search/base.py",
    "*/embed/base.py",
    "*/retrieval/store.py",
```
Insert these three lines inside the existing `omit = [ … ]` list (before the closing `]`). Do NOT omit `retrieval/rerank.py` or `retrieval/engine.py` — they ARE covered by the rewritten tests (the `ClaudeCodeReranker` stub + FTS-only engine). `embed/base.py` is omitted because its only-exercised path (the ImportError branch) is environment-dependent.

- [ ] **Step 5: Run the pyproject test + the FULL coverage-gated suite**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_pyproject.py -q -p no:cacheprovider --no-cov 2>&1 | tail -6
uv run python -m pytest -q -p no:cacheprovider 2>&1 | tail -8
```
Expected: pyproject tests PASS; the full suite PASSES with `Required test coverage of 80% reached`. If coverage is < 80%, the offender is almost certainly a now-uncovered branch in a kept file — add it to `omit` ONLY if it is a genuine KR-2/KR-5 stub; otherwise add a small unit test. Do NOT lower the 80% floor.

> NOTE on the dep change vs. the installed venv: `uv run` uses the project's locked env. After editing `pyproject.toml`, the installed packages don't auto-change, but the TESTS only parse `pyproject.toml` as TOML (`test_pyproject.py`) — they don't import the removed packages. The runtime stubs raise `NotImplementedError`/`ImportError`, never import cohere/tavily/etc. So `uv run python -m pytest` passes WITHOUT re-syncing the env. (KR-7 handles the real `uv sync`/lock refresh + `pipx` install verification.)

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "KR-1: lean keyless pyproject (drop [search], lancedb/pyarrow→[local], crawl4ai→core)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Final guards — keyless grep, ruff, mypy, full green

**Files:** none (verification only)

- [ ] **Step 1: The keyless grep guard (the cross-plan invariant)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
grep -rIn -E "import cohere|import tavily|import exa_py|import firecrawl|import browser_use|import agentql|import stagehand|import browserbase|from cohere|from tavily|from exa_py|from firecrawl|CohereReranker|CohereEmbedProvider|ExaProvider|TavilyProvider|SonarProvider|FirecrawlProvider|CascadeProvider|BrowserbaseProvider|BrowserUseProvider|AgentQLExtractProvider|StagehandExtractProvider" src/bad_research --include="*.py" | grep -v "__pycache__"
```
Expected: **zero output** (no keyed import or class survives in `src/`). Docstring mentions of "Firecrawl-style" / "Tavily" in `funnel/`/`quality/` are KEPT (they describe keyless ports, not imports) — they are not matched by this grep (it targets `import`/class names). If any line prints, it is a missed reference; fix it before proceeding.

- [ ] **Step 2: lancedb/pyarrow not imported at module-load in core**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
grep -rIn -E "^import lancedb|^import pyarrow|^from lancedb|^from pyarrow|^import lancedb|^    import lancedb" src/bad_research --include="*.py" | grep -v "__pycache__" | grep -v "retrieval/store.py"
```
Expected: **zero output** (lancedb/pyarrow are imported only inside `retrieval/store.py`, which is itself only imported lazily when `lance_dir` is set).

- [ ] **Step 3: Import-smoke — every core module imports with no keyed/heavy dep**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run python -c "
import importlib
for m in ['bad_research.web.base','bad_research.web.search.base','bad_research.browse.base',
          'bad_research.browse.ladder','bad_research.embed.base','bad_research.retrieval.engine',
          'bad_research.retrieval.rerank','bad_research.providers','bad_research.config',
          'bad_research.cli.research','bad_research.cli']:
    importlib.import_module(m)
    print('OK', m)
print('ALL CORE MODULES IMPORT KEYLESS')
"
```
Expected: `OK …` for every module + `ALL CORE MODULES IMPORT KEYLESS`. (Importing `web.base`/`browse.base` must NOT import cohere/tavily/lancedb — the imports inside the stubs are lazy.)

- [ ] **Step 4: ruff + mypy clean**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
uv run ruff check src/bad_research tests 2>&1 | tail -15
uv run mypy src/bad_research 2>&1 | tail -15
```
Expected: ruff `All checks passed!` (fix any unused-import `F401` left by the deletions — e.g. a stray `import os` in `browse/base.py` or `retrieval/rerank.py`). mypy: no NEW errors vs. the baseline (the stubs are fully typed; if mypy was clean before, it stays clean). If a pre-existing mypy error exists on a kept file, do not fix it here — note it; KR-1 must not introduce a NEW one.

- [ ] **Step 5: The full coverage-gated suite — the KR-1 done bar**

Run: `export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch && uv run python -m pytest -q -p no:cacheprovider 2>&1 | tail -8`
Expected: `N passed, 2 skipped` with **zero failed / zero errors** and `Required test coverage of 80% reached`. (N ≈ 470 after the ~30 deleted tests; the exact number is whatever remains green.)

- [ ] **Step 6: Final commit (verification artifacts only — usually nothing to commit)**

```bash
export PATH="$HOME/.local/bin:$PATH"; cd /Users/seventyleven/Desktop/badresearch
git status --short
# If ruff/mypy fixes were needed:
git add -A
git commit -m "KR-1: final keyless guards green (grep clean, ruff/mypy clean, suite green)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" || echo "nothing to commit — already green"
```

---

## Self-Review (run after the plan, before execution)

**Spec coverage (INTERFACES_KEYLESS §1 REMOVED list):**
- §1.1 web API providers + cascade → Tasks 1, 2, 4 ✓ (tavily/sonar/firecrawl/exa/cascade/searxng-file/`providers/` dir all deleted; `get_provider` keyless; `_build_cascade` gone).
- §1.1 browse cloud/keyed providers → Tasks 3, 5 ✓ (browserbase/browseruse/agentql/stagehand deleted; `get_browse_provider`/`get_extract_provider`/`ladder` keyless).
- §1.1 Cohere embedder + reranker → Tasks 6, 7 ✓ (`embed/cohere.py` + `CohereReranker` deleted; `bge-local`/`ClaudeCodeReranker` stubs).
- §1.1 LanceDB out of core → Task 8 ✓ (engine FTS-default; `store.py` lazy-only; `[local]`).
- §1.2 tests to delete/rewrite → Tasks 1–12 ✓ (12 test files deleted; 9 rewritten).
- §1.3 deps to remove → Task 12 ✓ (`[search]` gone; browser-use/agentql out; lancedb/pyarrow→`[local]`).
- §3.4 config knobs → Task 9 ✓. §3.5 registry → Task 10 ✓. §7 lean deps → Task 12 ✓.

**Resolved-decision honoring:** anthropic = CORE ✓ (Task 12 keeps it; Task 11 keeps the verify-citations LLM builder). agent-browser/yt-dlp/lightpanda/SearXNG = external CLIs, not pip ✓ (Task 12 `[browse]`=playwright only; comment documents the CLIs). `[local]` = use-if-present ✓ (Task 11 `_build_embedder` returns None unless `neural_recall`; Task 6 `get_embed_provider` import-guards, never auto-installs).

**Placeholder scan:** every code step shows the full code; every command shows the expected output; no "TBD"/"add error handling"/"similar to Task N". ✓

**Type consistency:** `ClaudeCodeReranker` (Task 7) is the same name used in Tasks 11 + the build test. `get_keyless_provider` (Task 4) matches the `web/base.py` import. `_LexicalShimEmbedder` (Task 8) matches its construction line. `reranker`/`searxng_endpoint`/`browse_engine`/`effort` config fields (Task 9) match the Task-9 test asserts. ✓

**Stub→KR mapping** (the "leave a typed stub" rule): table in the "Temporary stubs" section above maps every stub to the KR that fills it. ✓

---

## KNOWN / DESIGNED / CALIBRATE labels

- **KNOWN** (verified by reading the code at plan time): the full DELETE list + every caller; the baseline `501 passed / 87.81%`; `SemanticCache` needs an embedder (hence the shim); `builtin`/`crawl4ai` only import `WebResult`; the four browse modules are lazily imported; the funnel `sonar`/`exa` strings are FakeProvider names, not imports; `cli/research.py::_build_providers` uses `builtin` (kept).
- **DESIGNED** (this plan's keyless engineering): the `_KeylessStub`/`get_keyless_provider` (KR-2 seam point), `ClaudeCodeReranker`/`IdentityReranker` stubs, the FTS-only `RetrievalEngine` branch + `_LexicalShimEmbedder`, the keyless `get_browse_provider`/`_do_browse`, the keyless registry rows, the lean dep set.
- **CALIBRATE** (deferred — NOT done in KR-1): the real `web/search/` providers + RRF (KR-2); `fetch_clean` content pipeline (KR-3); `agent_browser.py` + `aql.py` (KR-4); the `ClaudeCodeReranker` host-model body + `LexicalCacheBackend` + `BgeLocalEmbedProvider` + 25k auto-enable (KR-5); the funnel/skill rewire + loop levers (KR-6); `uv sync`/lock + pipx + `bad doctor`/`bad install` keyless bootstrap + calibration harness (KR-7).
