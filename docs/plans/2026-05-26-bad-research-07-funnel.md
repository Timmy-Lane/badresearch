# Bad Research — Plan 07: Scraper Funnel — Implementation Plan

> Built for execution by agentic workers via the superpowers `executing-plans` / `subagent-driven-development` flow: each task is a self-contained TDD unit (write failing test → run → see RED → implement → run → see GREEN → commit). No task depends on uncommitted state from another. All code is complete and runnable — no placeholders, no `...`, no "fill this in".

> **⚠ POST-REVIEW RECONCILIATION (2026-05-26) — READ BEFORE CODING THE FAN-OUT (Task ~5) AND READ (Task 6) STAGES.** The cross-plan review found the seams this funnel consumes are **synchronous**: Plan 03's `WebSearchProvider.search_ex(q) -> list[WebResult]` and Plan 04's `fetch_tiered(url, *, tier_max, ...) -> WebResult` are plain `def` (blocking httpx / `asyncio.run`-wrapped browse), **not** `async def`. This funnel runs them concurrently, so it must NOT `await` them directly (the tests below pass only because their `FunnelDeps` fakes are `async def`; against the real sync impls, `await sync_fn()` raises `TypeError`). Add this helper as `funnel/_async.py` and route EVERY seam call through it:
> ```python
> import asyncio, inspect
> async def acall(fn, *args, **kwargs):
>     """Await fn if it's a coroutine function; otherwise run the blocking call in a worker thread."""
>     if inspect.iscoroutinefunction(fn):
>         return await fn(*args, **kwargs)
>     return await asyncio.to_thread(fn, *args, **kwargs)
> ```
> Then in the fan-out and read code, replace `await provider.search_ex(q)` → `await acall(provider.search_ex, q)` and `await fetcher.fetch_tiered(url, tier_max=1, ...)` → `await acall(fetcher.fetch_tiered, url, tier_max=1, ...)`. `acall` handles BOTH this plan's async test fakes AND the real sync Plan-03/04 impls, so every test below stays green and integration (Plan 08 composition) works against the real providers. The `gather()` public entry point itself stays `async`. Add one unit test: `acall` on a sync fn returns its value, and on an async fn awaits it.

## Goal

Build `funnel/` — the **six-stage scraper funnel** that is the engine behind the `width-sweep` skill stage (SPEC §6, dossier `10_SCRAPER_SOURCING.md` §3/§6). It gathers *lots of sources* (fan-out: M queries × P providers, parallel) while keeping the model's context *flat* (the model only ever sees reranked top-`Chunk`s + `[[note-id]]` pointers — never raw page text).

The public entry point:

```python
async def gather(query: str, *, mode: Literal["light", "full"]) -> list[Chunk]: ...
```

`gather` runs the funnel: **(A) FAN-OUT** M queries × P providers via the cascade (async parallel) → raw hits; **(B) DEDUP** (URL-canonical + content-hash, free); **(C) RANK** un-read candidates (URL-utility + RRF k=60) — the cheap→expensive gate; **(D) READ** top-K (≤80 ceiling, batched, via `fetch_tiered`, `browse_page`-style chained-crawl depth 2 / 5 links-per-hub); **(E) FILTER** (quality `postfetch_filter` + >60%-overlap redundancy); **(F) CHUNK + STORE** in the vault (disk/SQLite — NOT the prompt); then **RERANK** the stored chunks via `RetrievalEngine` to the top set.

**The invariant (load-bearing):** callers receive `list[Chunk]` (reranked top chunks) + `[[note-id]]` pointers — NEVER raw page bodies. Sources scale (12→80 notes) while context stays flat (~5–15k tokens). This is proven by a test that asserts no raw page body string leaks into `gather`'s return value.

**Quality is the top priority. No MVP.** Every stage ships at launch with the exact constants from `INTERFACES.md` and dossier 10 §6.2.

## Architecture

```
                          gather(query, mode)
                                  │
   ┌──────────────────────────────┴──────────────────────────────────┐
   │  funnel/orchestrator.py — async, deterministic, NO model in A–E   │
   │                                                                   │
   │  A FAN-OUT   plan_queries(query,mode) → M SearchQuery             │
   │     fan_out(queries, providers)  asyncio.gather  M×P → raw hits   │
   │  B DEDUP     dedup(hits)  URL-canonical + content-hash  → cands   │
   │  C RANK      rank_candidates(cands, query)  utility + RRF k=60    │  ← cheap→expensive GATE
   │              → ordered; take top READ_TOP_K (≤80 ceiling)         │
   │  D READ      read_top_k(ranked, mode)  fetch_tiered batched       │
   │              + chained_crawl(hubs) depth 2 / 5 links              │
   │  E FILTER    postfetch_filter (Plan 05) + redundancy >60% overlap │
   │  E STORE     store_notes(results)  → vault notes (disk/SQLite)    │
   │  F RERANK    RetrievalEngine.index(notes); .search(query, top_k)  │
   │              → list[Chunk]  (the ONLY thing the caller sees)      │
   └───────────────────────────────────────────────────────────────────┘
        composes (all behind seams, all mocked in tests):
   web/providers (WebSearchProvider cascade, Plan 03) · browse/fetch_tiered (Plan 04)
   quality/postfetch_filter (Plan 05) · retrieval/RetrievalEngine + Chunk (Plan 02)
   core/vault + core/fetcher.write_note (hyperresearch base)
```

Stages A–E run at **$0 model cost** (deterministic Python + cheap rank rubric). Only Stage F's reranker (Plan 02, mocked here) and the model downstream touch chunks. The funnel is the mechanism that decouples *source count* from *context size*.

## Tech Stack

- **Python ≥3.11** (matches `pyproject.toml` `requires-python = ">=3.11,<3.14"`), `asyncio` for fan-out/read parallelism.
- **pytest** + `pytest-asyncio` for the async tests (added to `dev` extras).
- Reuses hyperresearch's `core/similarity.py` (shingle/jaccard, `n=3`, Jaccard `0.60`) for the redundancy filter — verbatim, no re-implementation.
- Composes (never re-implements) the Plan 02/03/04/05 seams from `INTERFACES.md`. In tests these seams are **mocked** (fakes implementing the Protocols) so the funnel *logic* is tested in isolation.
- Frozen constants from `INTERFACES.md` + dossier 10 §6.2, used verbatim.

## Frozen constants used by this plan (verbatim from INTERFACES.md + dossier 10 §6.2)

| Constant | `light` | `full` | Source |
|---|---|---|---|
| `M_QUERIES` (planned fan-out) | `12–20` | `40–100` | dossier 10 §6.2 |
| `P_PROVIDERS` (parallel) | `1–2` | `2–4` | dossier 10 §6.2 |
| `K_PER_QUERY` | `5–10` | `10` | dossier 10 §6.2 (Sonar/Exa dflt 10) |
| `CANDIDATE_POOL` post-dedup | `~20` | `~120` | dossier 10 §6.2 |
| `READ_TOP_K` | `12–20` | `60–80` | dossier 10 §6.2 |
| **read-top-K ceiling** | — | **`80`** (degrades past it) | INTERFACES.md frozen constants |
| read concurrency | `3–5` | `10–12` | dossier 10 §6.2 |
| `MAX_CHAIN_DEPTH` / links-per-hub | `0 / 0` | `2 / 5` | dossier 10 §6.2 |
| `RRF_K` | `60` | `60` | INTERFACES.md (Exa/LanceDB) |
| dedup Jaccard / shingle n | `0.60 / 3` | `0.60 / 3` | INTERFACES.md (`similarity.py`) |
| redundancy overlap threshold | `0.60` (>60%) | `0.60` | dossier 10 §3.4 / SPEC §8.3 |
| utility score max composite | `18` (6 dims × 0–3) | `18` | dossier 10 §3.2 |
| `TOP_CHUNKS` to model | `8–15` | `10–30` | dossier 10 §6.2 |
| relevance drop threshold | `0.70` | `0.70` | INTERFACES.md (Perplexity) |

We ship the **upper-bound** of each `full` range as the default `full` value and the **lower-bound** of each `light` range as the default `light` value, so the ceiling is always the binding constraint (this is the load-bearing decision — see Task 2).

---

## File Structure

```
ultimate-research/bad-research/
  src/bad_research/
    funnel/
      __init__.py          # exports gather, FunnelConfig
      config.py            # FunnelConfig dataclass (tiered constants, frozen)
      canonical.py         # canonicalize_url() — strip #hash/www/port/index/slash
      dedup.py             # dedup() — URL-canonical + content-hash (Stage A→B)
      rank.py              # utility_score(), rrf_fuse(), rank_candidates() (Stage C)
      fanout.py            # plan_queries(), fan_out() (Stage A)
      read.py              # read_top_k(), chained_crawl() (Stage D)
      filter.py            # filter_and_store() — postfetch + redundancy (Stage E)
      orchestrator.py      # gather() — wires A→B→C→D→E→F (the public entry)
  tests/
    test_funnel/
      __init__.py
      conftest.py          # fakes: FakeProvider, fake fetch_tiered, fake RetrievalEngine,
                           #        fake postfetch_filter, fake vault/store; WebResult builders
      test_canonical.py
      test_dedup.py
      test_rank.py
      test_fanout.py
      test_read.py
      test_filter.py
      test_orchestrator.py # the integration: fan-out parallel, ≤80 ceiling, no-raw-text invariant
```

All paths below are relative to the repo source root `ultimate-research/bad-research/`. The agent runs every command from that directory (`/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/`).

---

## Task 0 — Bootstrap the `funnel/` package and test harness

**Why:** every later task imports `bad_research.funnel.*` and the test fakes. This task creates the package skeleton, the `pytest-asyncio` wiring, and the shared fakes (mocking Plan 02/03/04/05 seams), so the funnel logic can be tested in isolation.

### 0.1 — Add `pytest-asyncio` to dev extras

If `pyproject.toml` for `bad-research` does not yet exist (Plan 01 owns it), create the minimal file below; otherwise just add the two `dev` deps. The funnel package only needs the standard library + the seams it composes.

Create/ensure `pyproject.toml` `dev` extras contain:

```toml
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
]
```

Ensure `[tool.pytest.ini_options]` enables asyncio auto mode:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
asyncio_mode = "auto"
```

> If Plan 01 already created `pyproject.toml`, **edit** these two keys rather than overwriting the file.

### 0.2 — Create the package skeleton

Create `src/bad_research/funnel/__init__.py`:

```python
"""funnel/ — the six-stage scraper funnel (SPEC §6, dossier 10).

Public API:
    gather(query, *, mode) -> list[Chunk]   # the ONLY entry point callers use
    FunnelConfig                              # tiered constants

Invariant: callers receive reranked Chunk[] + [[note-id]] pointers,
never raw page bodies. Stages A–E run at $0 model cost.
"""

from __future__ import annotations

from bad_research.funnel.config import FunnelConfig
from bad_research.funnel.orchestrator import gather

__all__ = ["FunnelConfig", "gather"]
```

> This file imports symbols that don't exist yet (`gather`, `FunnelConfig`). That's expected — it will import cleanly once Tasks 1 and 8 land. Do not run a top-level import of the package until then; the per-module tasks import their own module directly.

### 0.3 — Create the test harness with all seam fakes

Create `tests/test_funnel/__init__.py` (empty file).

Create `tests/test_funnel/conftest.py` — the shared fakes. These mock the **Plan 02/03/04/05** seams so the funnel logic is tested without real providers/network/LLM:

```python
"""Fakes for the funnel tests — mock every cross-plan seam (Plan 02/03/04/05).

We do NOT import real providers/retrieval/LLM; the funnel composes them behind
seams, and here we substitute deterministic fakes so funnel *logic* is isolated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest

# ---- WebResult (Plan 03 / hyperresearch web/base.py shape) ----------------
# We mirror the real WebResult fields the funnel touches. The real class lives
# in bad_research.web.base (forked from hyperresearch). For isolation we define
# a structurally identical stand-in; the funnel only uses .url/.title/.content
# and .looks_like_junk()/.looks_like_login_wall().


@dataclass
class FakeWebResult:
    url: str
    title: str = ""
    content: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)
    # SERP-time signals the rank stage uses (set by FakeProvider.search_ex):
    serp_rank: int = 0          # 1-based rank within this provider's list
    serp_provider: str = ""

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.url).netloc

    def looks_like_login_wall(self, original_url: str) -> bool:
        return "login" in (self.title or "").lower()

    def looks_like_junk(self) -> str | None:
        if len((self.content or "").strip()) < 300:
            return "Empty or near-empty content"
        return None


# ---- SearchQuery (Plan 03 dataclass, INTERFACES.md) -----------------------
@dataclass
class FakeSearchQuery:
    query: str
    intent: Literal["keyword", "neural", "deep"] = "keyword"
    recency_days: int | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    max_results: int = 10


# ---- Chunk (Plan 02 dataclass, INTERFACES.md) -----------------------------
@dataclass
class FakeChunk:
    chunk_id: str
    note_id: str
    text: str
    char_start: int
    char_end: int
    score: float
    source_id: str


# ---- WebSearchProvider fake (Plan 03 Protocol) ----------------------------
class FakeProvider:
    """Each provider returns a deterministic, distinct URL list so we can prove
    the union/merge and the parallelism. `calls` records concurrency evidence.
    """

    def __init__(self, name: str, *, latency: float = 0.0,
                 url_template: str = "https://{name}.example/{q}/{i}"):
        self.name = name
        self.capabilities = {"keyword"}
        self.cost_per_search = 0.005
        self.p50_ms = 300
        self._latency = latency
        self._url_template = url_template
        self.calls: list[str] = []        # queries this provider received

    def fetch(self, url: str) -> FakeWebResult:  # not used by the funnel directly
        return FakeWebResult(url=url, title=url, content="x" * 400)

    async def search_ex(self, q) -> list[FakeWebResult]:  # async in the funnel
        import asyncio

        self.calls.append(q.query)
        if self._latency:
            await asyncio.sleep(self._latency)
        out = []
        for i in range(q.max_results):
            url = self._url_template.format(name=self.name, q=q.query.replace(" ", "_"), i=i)
            out.append(FakeWebResult(url=url, title=f"{self.name} {q.query} {i}",
                                     content="body " * 100,
                                     serp_rank=i + 1, serp_provider=self.name))
        return out


# ---- fetch_tiered fake (Plan 04) ------------------------------------------
class FakeFetcher:
    """Records which URLs were read so the ≤80 ceiling can be asserted."""

    def __init__(self, *, junk_urls: set[str] | None = None,
                 hub_links: dict[str, list[str]] | None = None):
        self.read_urls: list[str] = []
        self._junk = junk_urls or set()
        self._hub_links = hub_links or {}

    async def fetch_tiered(self, url: str, *, tier_max: int = 1,
                           instruction=None, schema=None) -> FakeWebResult:
        self.read_urls.append(url)
        if url in self._junk:
            return FakeWebResult(url=url, title="login", content="too short")
        links = [{"href": h, "text": "next"} for h in self._hub_links.get(url, [])]
        return FakeWebResult(url=url, title=f"page {url}", content="real content " * 80,
                             links=links)


# ---- postfetch_filter fake (Plan 05) --------------------------------------
def fake_postfetch_filter(result):
    """Plan 05 contract: returns reason str if junk, None if it passes."""
    return result.looks_like_junk()


# ---- vault / store fake ----------------------------------------------------
class FakeVault:
    """Captures stored notes so we can assert raw text lives on 'disk', not in
    the returned Chunks."""

    def __init__(self):
        self.notes: dict[str, str] = {}   # note_id -> body (the raw page text)
        self._counter = 0

    def store_note(self, *, title: str, body: str, url: str, provider: str) -> str:
        self._counter += 1
        note_id = f"note-{self._counter}"
        self.notes[note_id] = body
        return note_id


# ---- RetrievalEngine fake (Plan 02) ---------------------------------------
class FakeRetrievalEngine:
    """Indexes notes, then 'search' returns Chunks whose text is a short
    excerpt (NOT the full body) with a score; honors top_k and the 0.70 gate."""

    def __init__(self):
        self.indexed: list[tuple[str, str]] = []  # (note_id, body)

    def index(self, notes) -> None:
        for note_id, body in notes:
            self.indexed.append((note_id, body))

    def search(self, query: str, *, mode: str, top_k: int) -> list:
        chunks = []
        for rank, (note_id, body) in enumerate(self.indexed):
            score = max(0.0, 0.95 - rank * 0.05)   # descending, deterministic
            if score < 0.70:
                continue
            excerpt = body[:60]                     # a CHUNK, never the full body
            chunks.append(FakeChunk(
                chunk_id=f"{note_id}#0", note_id=note_id, text=excerpt,
                char_start=0, char_end=len(excerpt), score=score, source_id=note_id))
        return chunks[:top_k]


# ---- fixtures --------------------------------------------------------------
@pytest.fixture
def providers():
    return [FakeProvider("sonar"), FakeProvider("exa"), FakeProvider("searxng")]


@pytest.fixture
def fetcher():
    return FakeFetcher()


@pytest.fixture
def vault():
    return FakeVault()


@pytest.fixture
def retrieval():
    return FakeRetrievalEngine()
```

### 0.4 — Run it (RED → GREEN baseline)

```bash
python -m pytest tests/test_funnel/ -q
```

**Expected output:** `no tests ran` (collected 0 items) — the harness imports cleanly. If you see an `ImportError`, fix the conftest before proceeding.

### 0.5 — Commit

```bash
git add src/bad_research/funnel/__init__.py tests/test_funnel/ pyproject.toml
git commit -m "feat(funnel): bootstrap package + test fakes for Plan 02/03/04/05 seams

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 1 — `FunnelConfig`: tiered constants (the funnel's numeric spine)

**Why:** every stage reads its bounds from one frozen config. The `full` ceiling (`READ_TOP_K=80`) is load-bearing and must come from here, not be scattered.

### 1.1 — Write the failing test

Create `tests/test_funnel/test_config.py`:

```python
from __future__ import annotations

from bad_research.funnel.config import FunnelConfig


def test_full_tier_constants_match_dossier():
    cfg = FunnelConfig.for_mode("full")
    assert cfg.m_queries == 100          # upper bound of 40-100 (dossier 10 §6.2)
    assert cfg.p_providers == 4          # 2-4
    assert cfg.k_per_query == 10
    assert cfg.candidate_pool == 120
    assert cfg.read_top_k == 80          # the ceiling IS the full read budget
    assert cfg.read_concurrency == 12
    assert cfg.max_chain_depth == 2
    assert cfg.max_links_per_hub == 5
    assert cfg.rrf_k == 60
    assert cfg.dedup_jaccard == 0.60
    assert cfg.shingle_n == 3
    assert cfg.redundancy_overlap == 0.60
    assert cfg.utility_max == 18
    assert cfg.top_chunks == 30          # upper bound of 10-30
    assert cfg.relevance_threshold == 0.70


def test_light_tier_constants_match_dossier():
    cfg = FunnelConfig.for_mode("light")
    assert cfg.m_queries == 12           # lower bound of 12-20
    assert cfg.p_providers == 1          # 1-2 → 1 (seed-only)
    assert cfg.k_per_query == 5
    assert cfg.candidate_pool == 20
    assert cfg.read_top_k == 12          # 12-20
    assert cfg.read_concurrency == 3
    assert cfg.max_chain_depth == 0      # no chained crawl on light
    assert cfg.max_links_per_hub == 0
    assert cfg.top_chunks == 8           # lower bound of 8-15


def test_read_top_k_never_exceeds_ceiling():
    # The ceiling is global and load-bearing (degrades past 80, hyperresearch).
    for mode in ("light", "full"):
        assert FunnelConfig.for_mode(mode).read_top_k <= FunnelConfig.READ_CEILING
    assert FunnelConfig.READ_CEILING == 80


def test_unknown_mode_raises():
    import pytest
    with pytest.raises(ValueError, match="mode"):
        FunnelConfig.for_mode("deep")  # 'deep' is full@max-effort, not a 4th mode
```

### 1.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_config.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.config'` (or collection error). RED confirmed.

### 1.3 — Implement

Create `src/bad_research/funnel/config.py`:

```python
"""FunnelConfig — the tiered numeric spine of the scraper funnel.

Every constant traces to INTERFACES.md (frozen constants) and dossier
10_SCRAPER_SOURCING.md §6.2. We ship the upper bound of each `full` range and
the lower bound of each `light` range so the ~80-read CEILING is always the
binding constraint (dossier 10 §3.3: reading past ~80 degrades synthesis).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["light", "full"]


@dataclass(frozen=True)
class FunnelConfig:
    # Stage A — fan-out
    m_queries: int
    p_providers: int
    k_per_query: int
    # Stage B — dedup / pool
    candidate_pool: int
    dedup_jaccard: float
    shingle_n: int
    # Stage C — rank
    rrf_k: int
    utility_max: int
    # Stage D — read
    read_top_k: int
    read_concurrency: int
    max_chain_depth: int
    max_links_per_hub: int
    # Stage E — filter
    redundancy_overlap: float
    # Stage F — rerank/feed
    top_chunks: int
    relevance_threshold: float

    # The load-bearing global ceiling (INTERFACES.md frozen constants).
    READ_CEILING: int = 80

    @classmethod
    def for_mode(cls, mode: str) -> FunnelConfig:
        if mode == "full":
            cfg = cls(
                m_queries=100, p_providers=4, k_per_query=10,
                candidate_pool=120, dedup_jaccard=0.60, shingle_n=3,
                rrf_k=60, utility_max=18,
                read_top_k=80, read_concurrency=12,
                max_chain_depth=2, max_links_per_hub=5,
                redundancy_overlap=0.60,
                top_chunks=30, relevance_threshold=0.70,
            )
        elif mode == "light":
            cfg = cls(
                m_queries=12, p_providers=1, k_per_query=5,
                candidate_pool=20, dedup_jaccard=0.60, shingle_n=3,
                rrf_k=60, utility_max=18,
                read_top_k=12, read_concurrency=3,
                max_chain_depth=0, max_links_per_hub=0,
                redundancy_overlap=0.60,
                top_chunks=8, relevance_threshold=0.70,
            )
        else:
            raise ValueError(
                f"unknown mode {mode!r}; valid modes are 'light' and 'full' "
                "('deep' is full@max-effort, not a 4th mode — see SPEC §6)")
        # Invariant: never read past the ceiling.
        assert cfg.read_top_k <= cls.READ_CEILING
        return cfg
```

### 1.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_config.py -q
```

**Expected:** `4 passed`.

### 1.5 — Commit

```bash
git add src/bad_research/funnel/config.py tests/test_funnel/test_config.py
git commit -m "feat(funnel): FunnelConfig tiered constants — 80-read ceiling load-bearing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — `canonicalize_url`: URL normalization (dedup precondition)

**Why:** Stage A dedup collapses `a.com/p` and `a.com/p/` to one candidate. Firecrawl-style normalization (dossier 10 §3.1 / §28.5): strip `#hash`, `www`, port, `index.*`, trailing slash, normalize scheme.

### 2.1 — Write the failing test

Create `tests/test_funnel/test_canonical.py`:

```python
from __future__ import annotations

from bad_research.funnel.canonical import canonicalize_url


def test_strips_trailing_slash():
    assert canonicalize_url("https://a.com/p") == canonicalize_url("https://a.com/p/")


def test_strips_hash_fragment():
    assert canonicalize_url("https://a.com/p#section") == canonicalize_url("https://a.com/p")


def test_strips_www():
    assert canonicalize_url("https://www.a.com/p") == canonicalize_url("https://a.com/p")


def test_strips_default_port():
    assert canonicalize_url("https://a.com:443/p") == canonicalize_url("https://a.com/p")
    assert canonicalize_url("http://a.com:80/p") == canonicalize_url("http://a.com/p")


def test_strips_index_files():
    assert canonicalize_url("https://a.com/docs/index.html") == canonicalize_url("https://a.com/docs")
    assert canonicalize_url("https://a.com/index.php") == canonicalize_url("https://a.com")


def test_lowercases_scheme_and_host_keeps_path_case():
    assert canonicalize_url("HTTPS://A.COM/Path") == "https://a.com/Path"


def test_preserves_query_string():
    # query is meaningful (e.g. ?id=5); do NOT strip it
    out = canonicalize_url("https://a.com/p?id=5")
    assert "id=5" in out


def test_distinct_paths_stay_distinct():
    assert canonicalize_url("https://a.com/p") != canonicalize_url("https://a.com/q")
```

### 2.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_canonical.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.canonical'`.

### 2.3 — Implement

Create `src/bad_research/funnel/canonical.py`:

```python
"""canonicalize_url — Firecrawl-style URL normalization for dedup (dossier 10
§3.1, FC §28.5). Collapses cosmetic variants so `a.com/p` and `a.com/p/`,
`www.a.com/p`, and `a.com/p#x` all dedup to one candidate.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": "80", "https": "443"}
_INDEX_RE = re.compile(r"/index\.(html?|php|aspx?|jsp|cgi)$", re.IGNORECASE)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower() or "https"

    host = parts.hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]

    # Drop default port; keep non-default ports.
    netloc = host
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    path = parts.path
    # strip index.* files
    path = _INDEX_RE.sub("", path)
    # strip a single trailing slash (but keep root "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # drop fragment; preserve query (it is semantically meaningful)
    return urlunsplit((scheme, netloc, path, parts.query, ""))
```

### 2.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_canonical.py -q
```

**Expected:** `8 passed`.

### 2.5 — Commit

```bash
git add src/bad_research/funnel/canonical.py tests/test_funnel/test_canonical.py
git commit -m "feat(funnel): canonicalize_url — Firecrawl-style normalization for dedup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — `dedup`: Stage A→B (URL-canonical + content-hash, free)

**Why:** the fan-out returns ~400–1200 raw hits with heavy overlap (providers share ~30–50% of URLs). Dedup collapses them to the candidate pool **at $0**: URL-canonical first, then content-hash (`sha256(content)[:16]`, matching `core/fetcher.py:137`) for mirror/syndicated pages with different URLs but identical bodies.

A `Candidate` dataclass is introduced here — it carries the un-read SERP signals (rank, provider) that Stage C ranks on, and accumulates every provider that surfaced the URL (so RRF can fuse across provider rank lists).

### 3.1 — Write the failing test

Create `tests/test_funnel/test_dedup.py`:

```python
from __future__ import annotations

from bad_research.funnel.dedup import Candidate, dedup
from tests.test_funnel.conftest import FakeWebResult


def _hit(url, content="real body " * 50, rank=1, provider="sonar", title=""):
    return FakeWebResult(url=url, title=title or url, content=content,
                         serp_rank=rank, serp_provider=provider)


def test_collapses_url_variants_to_one_candidate():
    hits = [
        _hit("https://a.com/p"),
        _hit("https://a.com/p/"),       # trailing slash → same
        _hit("https://www.a.com/p#x"),  # www + fragment → same
    ]
    cands = dedup(hits)
    assert len(cands) == 1


def test_collapses_identical_content_under_different_urls():
    same = "the exact same syndicated wire story " * 20
    hits = [
        _hit("https://ap.com/story", content=same),
        _hit("https://reuters-mirror.com/story", content=same),  # mirror, diff URL
        _hit("https://other.com/unique", content="totally different text " * 20),
    ]
    cands = dedup(hits)
    # AP + mirror collapse to 1, the unique page stays → 2
    assert len(cands) == 2


def test_candidate_accumulates_all_provider_ranks():
    # Same URL surfaced by sonar@2 and exa@5 → ONE candidate, BOTH rank lists.
    hits = [
        _hit("https://a.com/p", rank=2, provider="sonar"),
        _hit("https://a.com/p", rank=5, provider="exa"),
    ]
    cands = dedup(hits)
    assert len(cands) == 1
    c = cands[0]
    assert c.provider_ranks == {"sonar": 2, "exa": 5}


def test_keeps_first_seen_webresult_as_representative():
    hits = [_hit("https://a.com/p", title="first"),
            _hit("https://a.com/p/", title="second")]
    cands = dedup(hits)
    assert cands[0].result.title == "first"


def test_empty_input_returns_empty():
    assert dedup([]) == []
```

### 3.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_dedup.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.dedup'`.

### 3.3 — Implement

Create `src/bad_research/funnel/dedup.py`:

```python
"""Stage A→B dedup — URL-canonical + content-hash, $0, no model.

URL-canonical collapse uses canonicalize_url (Firecrawl-style). Content-hash
collapse uses sha256(content)[:16] (matches core/fetcher.py:137) to catch
mirror/syndicated pages with different URLs but identical bodies.

Output: list[Candidate] — the un-read candidate pool. Each Candidate carries
the SERP signals (provider_ranks) the rank stage (Stage C) fuses via RRF.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from bad_research.funnel.canonical import canonicalize_url


@dataclass
class Candidate:
    """An un-read search hit. The funnel ranks these BEFORE fetching (Stage C)."""

    canonical_url: str
    result: object                       # the representative WebResult (un-read SERP shape)
    provider_ranks: dict[str, int] = field(default_factory=dict)  # provider -> 1-based rank

    @property
    def url(self) -> str:
        return self.canonical_url


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]


def dedup(hits: list) -> list[Candidate]:
    """Collapse raw fan-out hits into the candidate pool.

    Stage 1: URL-canonical dedup (cosmetic variants → one).
    Stage 2: content-hash dedup (mirrors/syndication → one).
    Provider ranks from every duplicate are merged onto the survivor.
    """
    by_url: dict[str, Candidate] = {}
    for h in hits:
        cu = canonicalize_url(h.url)
        prov = getattr(h, "serp_provider", "") or "unknown"
        rank = getattr(h, "serp_rank", 0) or 0
        if cu in by_url:
            # keep first-seen representative; merge this provider's rank
            existing = by_url[cu]
            if prov not in existing.provider_ranks:
                existing.provider_ranks[prov] = rank
        else:
            by_url[cu] = Candidate(canonical_url=cu, result=h,
                                   provider_ranks={prov: rank} if rank else {prov: 0})

    # Stage 2 — content-hash collapse across distinct URLs.
    by_hash: dict[str, Candidate] = {}
    out: list[Candidate] = []
    for cand in by_url.values():
        body = getattr(cand.result, "content", "") or ""
        # Pages with no body yet (snippet-only) can't be content-deduped; keep them.
        if not body.strip():
            out.append(cand)
            continue
        ch = _content_hash(body)
        if ch in by_hash:
            # merge provider ranks onto the canonical survivor, drop the mirror
            survivor = by_hash[ch]
            for p, r in cand.provider_ranks.items():
                survivor.provider_ranks.setdefault(p, r)
        else:
            by_hash[ch] = cand
            out.append(cand)
    return out
```

### 3.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_dedup.py -q
```

**Expected:** `5 passed`.

### 3.5 — Commit

```bash
git add src/bad_research/funnel/dedup.py tests/test_funnel/test_dedup.py
git commit -m "feat(funnel): Stage A->B dedup — URL-canonical + content-hash, free

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — `rank_candidates`: Stage C (the cheap→expensive gate)

**Why:** **this is the architectural gate that makes breadth cheap.** We gathered ~120 candidates but only fetch the top ~80. Ranking happens on **un-read** candidates using only SERP signals (rank, provider, domain, snippet) — zero fetches. Two mechanisms fuse: (1) **RRF k=60** over the per-provider rank lists (a URL surfaced by sonar@2 and exa@5 scores `1/(60+2)+1/(60+5)`); (2) a **6-dimension utility score** (max composite 18, dossier 10 §3.2). Rank descending; the read stage then takes only `read_top_k`.

### 4.1 — Write the failing test

Create `tests/test_funnel/test_rank.py`:

```python
from __future__ import annotations

from bad_research.funnel.dedup import Candidate
from bad_research.funnel.rank import rank_candidates, rrf_fuse, utility_score
from tests.test_funnel.conftest import FakeWebResult


def _cand(url, ranks, *, domain_title="", content="body " * 80):
    r = FakeWebResult(url=url, title=domain_title or url, content=content)
    return Candidate(canonical_url=url, result=r, provider_ranks=dict(ranks))


def test_rrf_fuses_multi_provider_ranks_k60():
    # surfaced by two providers ranks 2 and 5 → 1/(60+2)+1/(60+5)
    score = rrf_fuse({"sonar": 2, "exa": 5}, k=60)
    assert abs(score - (1 / 62 + 1 / 65)) < 1e-9


def test_rrf_single_provider():
    assert abs(rrf_fuse({"sonar": 1}, k=60) - (1 / 61)) < 1e-9


def test_rrf_ignores_zero_ranks():
    # rank 0 means 'unknown position' — don't let it dominate (would be 1/60)
    assert rrf_fuse({"sonar": 0}, k=60) == 0.0


def test_utility_score_bounded_0_to_18():
    c = _cand("https://sec.gov/filing", {"sonar": 1},
              domain_title="SEC EDGAR 10-Q primary filing")
    s = utility_score(c, query="acme 10-Q revenue")
    assert 0 <= s <= 18


def test_authority_domain_scores_higher_than_blog():
    gov = _cand("https://sec.gov/x", {"sonar": 1}, domain_title="SEC filing")
    blog = _cand("https://randomblog.wordpress.com/x", {"sonar": 1}, domain_title="my hot take")
    assert utility_score(gov, "x") > utility_score(blog, "x")


def test_rank_orders_before_any_read():
    # Higher composite (RRF + utility) must come first; NO fetch happens.
    cands = [
        _cand("https://low.blog/x", {"searxng": 9}, domain_title="opinion"),
        _cand("https://sec.gov/x", {"sonar": 1, "exa": 2}, domain_title="SEC filing data"),
        _cand("https://mid.com/x", {"tavily": 4}, domain_title="news report"),
    ]
    ranked = rank_candidates(cands, query="financial data", rrf_k=60)
    assert ranked[0].url == "https://sec.gov/x"          # best RRF + authority
    assert ranked[-1].url == "https://low.blog/x"
    # the Candidate objects are returned un-mutated (no .content fetched in)
    assert all(isinstance(c, Candidate) for c in ranked)


def test_rank_is_pure_no_network(monkeypatch):
    # Guard: rank must never call fetch_tiered. We patch a sentinel that explodes.
    import bad_research.funnel.rank as rank_mod
    assert not hasattr(rank_mod, "fetch_tiered")  # rank module must not import the reader
```

### 4.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_rank.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.rank'`.

### 4.3 — Implement

Create `src/bad_research/funnel/rank.py`:

```python
"""Stage C — rank un-read candidates (the cheap-search -> expensive-read gate).

Two cheap signals, NO fetch:
  1. RRF k=60 over per-provider rank lists (INTERFACES.md; Exa/LanceDB canon).
  2. 6-dimension utility score, max composite 18 (dossier 10 §3.2,
     hyperresearch width-sweep §2.3): Authority, Novelty, Stance, Coverage,
     Redundancy, Freshness — each 0-3.

This module imports NOTHING from the read/fetch layer: the whole point is that
ranking is free and happens before any expensive read.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Authority by domain class (dossier 10 §3.2 dim 1; quality DOMAIN_TIER spirit).
_PRIMARY = ("sec.gov", "edgar", "europa.eu", "gov.uk", ".gov", "arxiv.org",
            "ncbi.nlm.nih.gov", "doi.org", "semanticscholar.org")
_INSTITUTIONAL = ("reuters.com", "bloomberg.com", "ft.com", "nature.com",
                  "ieee.org", "acm.org", "wsj.com", "economist.com")
_BLOG = ("wordpress.com", "blogspot.com", "medium.com", "substack.com",
         "tumblr.com")


def rrf_fuse(provider_ranks: dict[str, int], *, k: int = 60) -> float:
    """Reciprocal Rank Fusion across provider rank lists. Rank 0 = unknown,
    contributes nothing (don't let an unranked hit score 1/k)."""
    total = 0.0
    for rank in provider_ranks.values():
        if rank and rank > 0:
            total += 1.0 / (k + rank)
    return total


def _authority(domain: str) -> int:
    d = domain.lower()
    if any(p in d for p in _PRIMARY):
        return 3
    if any(p in d for p in _INSTITUTIONAL):
        return 2
    if any(p in d for p in _BLOG):
        return 0
    return 1  # default: quality journalism / unknown


def utility_score(candidate, query: str) -> int:
    """6-dim utility, 0-3 each, max 18 (dossier 10 §3.2). Operates only on
    un-read SERP signals (domain, title/snippet, provider spread, recency)."""
    r = candidate.result
    domain = urlsplit(candidate.canonical_url).netloc.lower()
    title = (getattr(r, "title", "") or "").lower()
    meta = getattr(r, "metadata", {}) or {}
    q_terms = {t for t in query.lower().split() if len(t) > 2}

    authority = _authority(domain)

    # Novelty: how many distinct providers surfaced it (broad surfacing => less novel
    # niche; single-provider niche domains => more novel). Cap 3.
    n_prov = len(candidate.provider_ranks)
    novelty = 3 if n_prov == 1 else (1 if n_prov == 2 else 0)

    # Stance diversity: adversarial/critical signals in the title.
    adversarial = ("criticism", "limitations", "problems with", "against",
                   "debunk", "fails", "wrong")
    stance = 3 if any(a in title for a in adversarial) else 1

    # Coverage: title term overlap with the query (proxy for on-topic-ness).
    overlap = len(q_terms & set(title.split()))
    coverage = min(3, overlap)

    # Redundancy: penalize obvious aggregator/rewrite signals.
    redundancy = 0 if any(s in title for s in ("roundup", "everything you need", "explained")) else 2

    # Freshness: from metadata recency if present, else neutral.
    days = meta.get("age_days")
    if days is None:
        freshness = 1
    elif days <= 365:
        freshness = 3
    elif days <= 365 * 3:
        freshness = 2
    else:
        freshness = 1

    return authority + novelty + stance + coverage + redundancy + freshness


def rank_candidates(candidates: list, query: str, *, rrf_k: int = 60) -> list:
    """Order candidates descending by (RRF + normalized utility). Pure: no read.

    Composite = rrf_fuse(...) + utility/18 * (1/k-scale) so utility breaks RRF
    ties without dominating the parameter-free fusion. We weight RRF as primary
    (it is the multi-provider recall signal) and utility as the quality tiebreak.
    """
    def composite(c) -> float:
        rrf = rrf_fuse(c.provider_ranks, k=rrf_k)
        util = utility_score(c, query) / 18.0
        # RRF dominates; utility scaled into RRF's magnitude (~1/61) as tiebreak.
        return rrf + util * (1.0 / rrf_k)

    return sorted(candidates, key=composite, reverse=True)
```

### 4.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_rank.py -q
```

**Expected:** `7 passed`.

### 4.5 — Commit

```bash
git add src/bad_research/funnel/rank.py tests/test_funnel/test_rank.py
git commit -m "feat(funnel): Stage C rank — RRF k=60 + 6-dim utility, the cheap->expensive gate

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 — `plan_queries` + `fan_out`: Stage A (parallel multi-provider fan-out)

**Why:** breadth = `M queries × P providers × K results`, gathered **in parallel** (`asyncio.gather`). `plan_queries` expands one user query into M `SearchQuery` objects (the Perplexity `queries: List[str]` shape). `fan_out` fires them across the active providers concurrently and flattens. **The decisive test:** providers run in parallel (total wall time ≈ max single latency, not sum) and their distinct URL lists are merged.

> Real query expansion (3-lens A/B/C/D, dossier 10 §1.2) lives in the `width-sweep` skill prompt (Plan 08) — the orchestrator (Claude) authors the lens-driven queries. The funnel's `plan_queries` is the deterministic fallback/cap that turns a query into ≤M `SearchQuery` seeds when called programmatically; the skill can pass its own list in.

### 5.1 — Write the failing test

Create `tests/test_funnel/test_fanout.py`:

```python
from __future__ import annotations

import asyncio
import time

import pytest

from bad_research.funnel.fanout import fan_out, plan_queries
from tests.test_funnel.conftest import FakeProvider


def test_plan_queries_caps_at_m():
    qs = plan_queries("impact of AI on jobs", m_queries=12, k_per_query=5)
    assert len(qs) <= 12
    assert all(q.max_results == 5 for q in qs)
    # the verbatim user query is always present as the first seed
    assert qs[0].query == "impact of AI on jobs"


def test_plan_queries_distinct():
    qs = plan_queries("quantum computing error correction", m_queries=8, k_per_query=10)
    texts = [q.query for q in qs]
    assert len(texts) == len(set(texts))  # no duplicate seeds


async def test_fan_out_merges_provider_lists():
    providers = [FakeProvider("sonar"), FakeProvider("exa"), FakeProvider("searxng")]
    queries = plan_queries("topic", m_queries=2, k_per_query=4)
    hits = await fan_out(queries, providers)
    # 2 queries × 3 providers × 4 results = 24 raw hits (distinct URLs per provider)
    assert len(hits) == 24
    domains = {h.serp_provider for h in hits}
    assert domains == {"sonar", "exa", "searxng"}


async def test_fan_out_runs_providers_in_parallel():
    # Each provider sleeps 0.2s. Serial would be 2 queries × 3 providers × 0.2 = 1.2s.
    # Parallel must be ~0.2s (one round). Assert well under the serial floor.
    providers = [FakeProvider(n, latency=0.2) for n in ("sonar", "exa", "searxng")]
    queries = plan_queries("topic", m_queries=2, k_per_query=2)
    start = time.perf_counter()
    await fan_out(queries, providers)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.6, f"fan-out not parallel: took {elapsed:.2f}s (serial would be 1.2s)"


async def test_fan_out_survives_one_provider_failure():
    class Boom(FakeProvider):
        async def search_ex(self, q):
            raise RuntimeError("provider down")

    providers = [FakeProvider("sonar"), Boom("exa")]
    queries = plan_queries("topic", m_queries=1, k_per_query=3)
    hits = await fan_out(queries, providers)
    # sonar's 3 results survive; exa's failure is swallowed (degrade, not abort)
    assert len(hits) == 3
    assert all(h.serp_provider == "sonar" for h in hits)


async def test_fan_out_empty_providers_returns_empty():
    hits = await fan_out(plan_queries("topic", m_queries=2, k_per_query=2), [])
    assert hits == []
```

### 5.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_fanout.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.fanout'`.

### 5.3 — Implement

Create `src/bad_research/funnel/fanout.py`:

```python
"""Stage A — fan-out. Many queries per step (Perplexity queries: List[str]),
fired across P providers in parallel (asyncio.gather), then flattened.

Breadth = M_QUERIES × P_PROVIDERS × K_PER_QUERY, gathered concurrently so
latency ≈ max single search, not the sum (dossier 10 §1.3, §5.1).

A dead provider degrades to the survivors (SPEC §13 provider failover) — one
provider's exception never aborts the fan-out.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal


@dataclass
class SearchQuery:
    """Mirror of the Plan 03 SearchQuery (INTERFACES.md web/base.py). Redeclared
    here as the funnel's input contract; the real one is structurally identical.
    """

    query: str
    intent: Literal["keyword", "neural", "deep"] = "keyword"
    recency_days: int | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    max_results: int = 10


# Deterministic lens suffixes — the programmatic fallback expansion when the
# skill doesn't supply its own lens plan (dossier 10 §1.2 lenses A/B/C).
_LENS_SUFFIXES = (
    "",                              # Lens A — core fact (verbatim query first)
    "latest developments",          # Lens A — state-of-the-art
    "original study foundational paper",   # Lens B — citation-chain depth
    "criticism limitations",        # Lens C — adversarial
    "alternative explanation",      # Lens C — dissent
    "primary data analysis",        # Lens B — upstream sources
)


def plan_queries(query: str, *, m_queries: int, k_per_query: int) -> list[SearchQuery]:
    """Expand one user query into ≤ m_queries SearchQuery seeds. Verbatim query
    is always the first seed. Cheap deterministic fallback for programmatic
    callers; the width-sweep skill (Plan 08) may pass a richer lens plan in."""
    seen: set[str] = set()
    out: list[SearchQuery] = []
    for suffix in _LENS_SUFFIXES:
        text = query if not suffix else f"{query} {suffix}"
        if text in seen:
            continue
        seen.add(text)
        out.append(SearchQuery(query=text, max_results=k_per_query))
        if len(out) >= m_queries:
            break
    return out[:m_queries]


async def fan_out(queries: list, providers: list) -> list:
    """Fire every (query × provider) concurrently; flatten survivors.

    Returns the raw hit pool (with duplicates — Stage B dedups). Stamps the
    representative WebResults with serp_rank/serp_provider if the provider
    didn't already (fakes do; real providers set them in search_ex).
    """
    if not providers or not queries:
        return []

    async def _one(provider, q) -> list:
        try:
            results = await provider.search_ex(q)
        except Exception:
            return []  # degrade: a dead provider drops out, never aborts the run
        for i, r in enumerate(results):
            if not getattr(r, "serp_provider", ""):
                r.serp_provider = provider.name
            if not getattr(r, "serp_rank", 0):
                r.serp_rank = i + 1
        return results

    tasks = [_one(p, q) for q in queries for p in providers]
    batches = await asyncio.gather(*tasks)
    hits: list = []
    for b in batches:
        hits.extend(b)
    return hits
```

### 5.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_fanout.py -q
```

**Expected:** `6 passed`.

### 5.5 — Commit

```bash
git add src/bad_research/funnel/fanout.py tests/test_funnel/test_fanout.py
git commit -m "feat(funnel): Stage A fan-out — parallel M-query x P-provider, degrade-not-abort

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — `read_top_k` + `chained_crawl`: Stage D (≤80 ceiling, batched, chained-crawl)

**Why:** Stage D is where the cheap→expensive gate pays off: we **read only the top `read_top_k`** ranked candidates (never the full pool), batched at `read_concurrency` via `fetch_tiered` (Plan 04, mocked). **The ≤80 ceiling is enforced here and is load-bearing** — the 81st candidate is never read. Hub pages (Wikipedia/surveys with many outbound links) trigger a **bounded chained crawl** (`browse_page` pattern, dossier 10 §2.2): rank the outbound links, queue the top `max_links_per_hub`, depth ≤ `max_chain_depth`; queued links re-enter the dedup gate so they don't double-read.

### 6.1 — Write the failing test

Create `tests/test_funnel/test_read.py`:

```python
from __future__ import annotations

import pytest

from bad_research.funnel.dedup import Candidate
from bad_research.funnel.read import read_top_k
from tests.test_funnel.conftest import FakeFetcher, FakeWebResult


def _ranked(n):
    out = []
    for i in range(n):
        url = f"https://src{i}.com/p"
        out.append(Candidate(canonical_url=url,
                             result=FakeWebResult(url=url, content="snippet"),
                             provider_ranks={"sonar": i + 1}))
    return out


async def test_reads_only_top_k_not_full_pool():
    ranked = _ranked(120)              # post-dedup candidate pool ~120
    fetcher = FakeFetcher()
    results = await read_top_k(ranked, fetcher=fetcher, read_top_k=80,
                               concurrency=12, max_chain_depth=0, max_links_per_hub=0)
    assert len(fetcher.read_urls) == 80          # only 80 fetched
    assert len(results) == 80


async def test_81st_candidate_is_never_read():
    ranked = _ranked(120)
    # mark the 81st (index 80) with a sentinel URL; assert it's absent from reads
    sentinel = "https://NEVER-READ.com/p"
    ranked[80] = Candidate(canonical_url=sentinel,
                           result=FakeWebResult(url=sentinel, content="x"),
                           provider_ranks={"sonar": 81})
    fetcher = FakeFetcher()
    await read_top_k(ranked, fetcher=fetcher, read_top_k=80, concurrency=12,
                     max_chain_depth=0, max_links_per_hub=0)
    assert sentinel not in fetcher.read_urls


async def test_ceiling_caps_even_if_top_k_misconfigured():
    # Defense in depth: even if a caller passes read_top_k > ceiling, never read >80.
    ranked = _ranked(200)
    fetcher = FakeFetcher()
    await read_top_k(ranked, fetcher=fetcher, read_top_k=999, concurrency=12,
                     max_chain_depth=0, max_links_per_hub=0, ceiling=80)
    assert len(fetcher.read_urls) == 80


async def test_batched_read_concurrency_bounded():
    # The semaphore bounds in-flight reads; we assert it completes and reads all.
    ranked = _ranked(20)
    fetcher = FakeFetcher()
    results = await read_top_k(ranked, fetcher=fetcher, read_top_k=20, concurrency=5,
                               max_chain_depth=0, max_links_per_hub=0)
    assert len(results) == 20


async def test_chained_crawl_follows_top_hub_links_bounded():
    # src0 is a hub linking 8 outbound URLs; with max_links_per_hub=5 we follow 5.
    hub = "https://hub.com/p"
    extra = [f"https://child{i}.com/a" for i in range(8)]
    ranked = [Candidate(canonical_url=hub,
                        result=FakeWebResult(url=hub, content="hub"),
                        provider_ranks={"sonar": 1})]
    fetcher = FakeFetcher(hub_links={hub: extra})
    results = await read_top_k(ranked, fetcher=fetcher, read_top_k=80, concurrency=12,
                               max_chain_depth=2, max_links_per_hub=5,
                               query="topic")
    read = set(fetcher.read_urls)
    assert hub in read
    followed = [c for c in extra if c in read]
    assert len(followed) == 5            # exactly max_links_per_hub, not all 8


async def test_chain_depth_zero_follows_nothing():
    hub = "https://hub.com/p"
    ranked = [Candidate(canonical_url=hub,
                        result=FakeWebResult(url=hub, content="hub"),
                        provider_ranks={"sonar": 1})]
    fetcher = FakeFetcher(hub_links={hub: ["https://child.com/a"]})
    await read_top_k(ranked, fetcher=fetcher, read_top_k=80, concurrency=12,
                     max_chain_depth=0, max_links_per_hub=0, query="topic")
    assert fetcher.read_urls == [hub]    # no link-following on light tier


async def test_chained_links_reenter_dedup_no_double_read():
    # A hub links to a URL already in the read set → it is NOT read twice.
    hub = "https://hub.com/p"
    dup = "https://src1.com/p"
    ranked = [
        Candidate(canonical_url=hub, result=FakeWebResult(url=hub, content="hub"),
                  provider_ranks={"sonar": 1}),
        Candidate(canonical_url=dup, result=FakeWebResult(url=dup, content="x"),
                  provider_ranks={"sonar": 2}),
    ]
    fetcher = FakeFetcher(hub_links={hub: [dup]})
    await read_top_k(ranked, fetcher=fetcher, read_top_k=80, concurrency=12,
                     max_chain_depth=2, max_links_per_hub=5, query="topic")
    assert fetcher.read_urls.count(dup) == 1   # read once, not twice
```

### 6.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_read.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.read'`.

### 6.3 — Implement

Create `src/bad_research/funnel/read.py`:

```python
"""Stage D — read ONLY the top-K ranked candidates (≤80 ceiling), batched.

The cheap-search -> expensive-read gate pays off here: we fetch the Stage-C
winners and NEVER the full pool. The ~80-read ceiling is load-bearing
(dossier 10 §3.3: reading past it degrades synthesis) and enforced even if a
caller misconfigures read_top_k.

Reads run through fetch_tiered (Plan 04, the Tier 0->3 escalation ladder),
bounded by an asyncio.Semaphore (read_concurrency 10-12 full / 3-5 light).

Chained crawl (browse_page pattern, dossier 10 §2.2): a hub page's outbound
links are ranked by a free JS-cosine score against the query and the top
max_links_per_hub are queued, depth <= max_chain_depth; queued links re-enter
the seen-set so they are never double-read.
"""

from __future__ import annotations

import asyncio
import math
import re

_DEFAULT_CEILING = 80
_HUB_LINK_FLOOR = 10   # a page with >=10 outbound links is treated as a hub


def _js_cosine(query: str, text: str) -> float:
    """Firecrawl-style pure-JS bag-of-words cosine (dossier 10 §2.2 / FC §28.6).
    No embedding model — tokenize on \\W+, count, dot/magnitudes. Dirt cheap."""
    qt = [t for t in re.split(r"\W+", query.lower()) if t]
    dt = [t for t in re.split(r"\W+", text.lower()) if t]
    if not qt or not dt:
        return 0.0
    from collections import Counter
    qc, dc = Counter(qt), Counter(dt)
    common = set(qc) & set(dc)
    dot = sum(qc[t] * dc[t] for t in common)
    qmag = math.sqrt(sum(v * v for v in qc.values()))
    dmag = math.sqrt(sum(v * v for v in dc.values()))
    return dot / (qmag * dmag) if qmag and dmag else 0.0


def _rank_hub_links(query: str, links: list[dict], limit: int) -> list[str]:
    """Rank a hub's outbound links by JS-cosine of (anchor text) vs query, keep top `limit`."""
    scored = []
    for ln in links:
        href = ln.get("href") or ""
        if not href.startswith("http"):
            continue
        text = (ln.get("text") or "") + " " + href
        scored.append((_js_cosine(query, text), href))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [href for _, href in scored[:limit]]


async def read_top_k(
    ranked: list,
    *,
    fetcher,
    read_top_k: int,
    concurrency: int,
    max_chain_depth: int,
    max_links_per_hub: int,
    query: str = "",
    ceiling: int = _DEFAULT_CEILING,
) -> list:
    """Read the top candidates via fetch_tiered, batched + chained.

    Returns the list of read WebResults (junk not yet filtered — Stage E does
    that). Never reads more than min(read_top_k, ceiling) primary candidates;
    chained-crawl children also count against the same read budget.
    """
    budget = min(read_top_k, ceiling)
    sem = asyncio.Semaphore(max(1, concurrency))
    seen: set[str] = set()
    results: list = []
    reads_done = 0
    lock = asyncio.Lock()

    async def _fetch(url: str):
        async with sem:
            return await fetcher.fetch_tiered(url, tier_max=1)

    async def _try_read(url: str) -> object | None:
        nonlocal reads_done
        async with lock:
            if url in seen or reads_done >= budget:
                return None
            seen.add(url)
            reads_done += 1
        return await _fetch(url)

    # Primary wave: the top-budget ranked candidates, batched.
    primaries = ranked[:budget]
    primary_results = await asyncio.gather(*[_try_read(c.canonical_url) for c in primaries])
    results.extend(r for r in primary_results if r is not None)

    # Chained crawl: follow the best outbound links of hub pages, bounded.
    if max_chain_depth > 0 and max_links_per_hub > 0:
        frontier = list(results)
        depth = 1
        while frontier and depth <= max_chain_depth:
            next_frontier: list = []
            queued: list[str] = []
            for page in frontier:
                links = getattr(page, "links", []) or []
                if len(links) < _HUB_LINK_FLOOR and len(links) < max_links_per_hub * 2:
                    # not hub-like enough; still allow following if it has links
                    if not links:
                        continue
                for href in _rank_hub_links(query, links, max_links_per_hub):
                    if href not in seen:
                        queued.append(href)
            # read queued links under the SAME budget; re-dedup via seen-set
            child_results = await asyncio.gather(*[_try_read(u) for u in queued])
            for cr in child_results:
                if cr is not None:
                    results.append(cr)
                    next_frontier.append(cr)
            frontier = next_frontier
            depth += 1

    return results
```

### 6.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_read.py -q
```

**Expected:** `7 passed`.

> Note on `test_chained_crawl_follows_top_hub_links_bounded`: the hub has 8 links (≥ floor heuristic is bypassed when `links` present), `max_links_per_hub=5` caps the follow to 5. If the hub-floor heuristic blocks following when a page has fewer than 10 links but you intend to follow anyway, the `len(links) < max_links_per_hub * 2` clause permits small-but-linky pages. Verify both chained tests pass; if `test_chain_depth_zero_follows_nothing` and the bounded test conflict, the depth gate (`max_chain_depth > 0`) is the authority.

### 6.5 — Commit

```bash
git add src/bad_research/funnel/read.py tests/test_funnel/test_read.py
git commit -m "feat(funnel): Stage D read — ≤80 ceiling enforced, batched, bounded chained-crawl

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 — `filter_and_store`: Stage E (junk + >60% redundancy, then store to vault)

**Why:** Stage E removes *fake* breadth and persists the corpus to disk (NOT the prompt). First the Plan 05 `postfetch_filter` (junk/login-wall/paywall/language) drops garbage pages. Then the **redundancy filter** clusters pages sharing **>60% of shingled content** (Jaccard `0.60`, `n=3`, reusing hyperresearch `core/similarity.py` verbatim) — "N sources are really 1 source in N outfits" — keeping the canonical and discounting derivatives. Survivors are written to the vault (mocked `FakeVault`), returning `(note_id, body)` pairs. **The raw body lives on disk; it is what `RetrievalEngine.index` reads, NOT what the caller sees.**

### 7.1 — Write the failing test

Create `tests/test_funnel/test_filter.py`:

```python
from __future__ import annotations

from bad_research.funnel.filter import filter_and_store
from tests.test_funnel.conftest import FakeVault, FakeWebResult, fake_postfetch_filter


def _page(url, content, title=""):
    return FakeWebResult(url=url, title=title or url, content=content)


def test_drops_junk_via_postfetch_filter():
    pages = [
        _page("https://good.com/a", "real substantive content " * 40),
        _page("https://junk.com/b", "tiny"),          # < 300 chars → junk
    ]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    urls = [vault.notes[nid] for nid, _ in stored]
    assert len(stored) == 1                            # junk dropped


def test_drops_redundant_over_60pct_overlap():
    base = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10
    pages = [
        _page("https://orig.com/a", base),
        _page("https://copy.com/b", base),             # identical → >60% overlap → drop
        _page("https://uniq.com/c", "completely orthogonal vocabulary here " * 20),
    ]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    assert len(stored) == 2                             # orig + uniq; copy discounted


def test_keeps_near_but_under_threshold():
    # ~40% overlap should NOT be dropped (only >60%).
    a = "word_a " * 30 + "shared shared shared "
    b = "word_b " * 30 + "shared shared shared "
    pages = [_page("https://a.com/a", a), _page("https://b.com/b", b)]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    assert len(stored) == 2


def test_stores_raw_body_to_vault_returns_note_ids():
    pages = [_page("https://good.com/a", "substantive content body " * 40)]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    note_id, body = stored[0]
    assert note_id in vault.notes                       # the raw body lives on disk
    assert "substantive content" in vault.notes[note_id]
    assert "substantive content" in body                # passed to RetrievalEngine.index


def test_empty_input_returns_empty():
    assert filter_and_store([], vault=FakeVault(), postfetch_filter=fake_postfetch_filter,
                            redundancy_overlap=0.60, shingle_n=3) == []
```

### 7.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_filter.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.filter'`.

### 7.3 — Implement

Create `src/bad_research/funnel/filter.py`:

```python
"""Stage E — filter junk + redundancy, then STORE survivors to the vault.

1. Plan 05 postfetch_filter: junk/login-wall/paywall/language → drop (returns
   a reason str if junk, None if it passes).
2. Redundancy clustering: pages sharing > redundancy_overlap of their shingled
   content (Jaccard, n=3) are derivative — keep the first (canonical), discount
   the rest (dossier 10 §3.4: "N sources are really 1 source in N outfits").
   Reuses hyperresearch core/similarity.py (shingle/jaccard) verbatim.
3. Store survivors to the vault (disk/SQLite). The raw body lives ON DISK; it
   is what RetrievalEngine.index reads, never what the caller sees.

Returns list[(note_id, body)] for Stage F to index.
"""

from __future__ import annotations

from bad_research.core.similarity import jaccard, shingle


def filter_and_store(
    pages: list,
    *,
    vault,
    postfetch_filter,
    redundancy_overlap: float,
    shingle_n: int,
) -> list[tuple[str, str]]:
    # 1. Junk filter (Plan 05).
    clean = [p for p in pages if postfetch_filter(p) is None]

    # 2. Redundancy clustering (brute Jaccard over shingles, n=3).
    kept: list = []
    kept_shingles: list[set] = []
    for p in clean:
        body = getattr(p, "content", "") or ""
        sh = shingle(body, n=shingle_n)
        is_derivative = any(
            jaccard(sh, prev) > redundancy_overlap for prev in kept_shingles
        )
        if is_derivative:
            continue   # discount the derivative; the canonical is already kept
        kept.append(p)
        kept_shingles.append(sh)

    # 3. Store survivors to the vault (raw body -> disk).
    stored: list[tuple[str, str]] = []
    for p in kept:
        body = getattr(p, "content", "") or ""
        note_id = vault.store_note(
            title=getattr(p, "title", "") or p.url,
            body=body,
            url=p.url,
            provider=getattr(p, "serp_provider", "") or "fetch",
        )
        stored.append((note_id, body))
    return stored
```

### 7.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_filter.py -q
```

**Expected:** `5 passed`.

> If `core.similarity` is not importable in the bad-research fork yet, the agent must confirm it was carried over from hyperresearch (`src/bad_research/core/similarity.py`). It is part of the hyperresearch base (Plan 01's fork step). If absent, copy it verbatim from `hyperresearch/src/hyperresearch/core/similarity.py` — do NOT re-implement.

### 7.5 — Commit

```bash
git add src/bad_research/funnel/filter.py tests/test_funnel/test_filter.py
git commit -m "feat(funnel): Stage E filter+store — postfetch junk + >60% redundancy, vault store

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8 — `gather`: the orchestrator (wire A→B→C→D→E→F, enforce the invariant)

**Why:** this is the public entry point and the proof of the whole design. It composes all stages and the cross-plan seams (providers, `fetch_tiered`, `postfetch_filter`, `RetrievalEngine`, vault), returning **only** `list[Chunk]`. **The load-bearing test asserts no raw page body string leaks into the return value** — the model sees reranked chunks + `[[note-id]]` pointers, never raw pages.

`gather` takes the seams via a small `FunnelDeps` bundle (dependency injection) so it's testable in isolation; the real wiring (Plan 03 cascade, Plan 04 `fetch_tiered`, Plan 02 `RetrievalEngine`, Plan 05 `postfetch_filter`, real vault) is assembled by the caller (the `width-sweep` skill backend, Plan 08) — production wiring is out of scope for this plan's tests but the signature is exact.

### 8.1 — Write the failing test

Create `tests/test_funnel/test_orchestrator.py`:

```python
from __future__ import annotations

import time

import pytest

from bad_research.funnel.orchestrator import FunnelDeps, gather
from tests.test_funnel.conftest import (
    FakeFetcher,
    FakeProvider,
    FakeRetrievalEngine,
    FakeVault,
    fake_postfetch_filter,
)


def _deps(providers=None, fetcher=None, vault=None, retrieval=None):
    return FunnelDeps(
        providers=providers or [FakeProvider("sonar"), FakeProvider("exa"),
                                FakeProvider("searxng")],
        fetcher=fetcher or FakeFetcher(),
        postfetch_filter=fake_postfetch_filter,
        vault=vault or FakeVault(),
        retrieval=retrieval or FakeRetrievalEngine(),
    )


async def test_gather_returns_only_chunks():
    deps = _deps()
    chunks = await gather("impact of AI on jobs", mode="full", deps=deps)
    assert isinstance(chunks, list)
    assert all(hasattr(c, "chunk_id") and hasattr(c, "text") and hasattr(c, "note_id")
               for c in chunks)


async def test_no_raw_page_body_leaks_into_return():
    # THE invariant: the corpus body lives on disk; the caller never sees it.
    vault = FakeVault()
    deps = _deps(vault=vault)
    chunks = await gather("topic", mode="full", deps=deps)
    # every stored note body is the full raw page; assert NO chunk text equals
    # (or contains the full of) any stored body — chunks are excerpts only.
    full_bodies = list(vault.notes.values())
    assert full_bodies, "precondition: something was stored"
    for c in chunks:
        for body in full_bodies:
            assert c.text != body, "raw page body leaked into a Chunk"
            assert len(c.text) < len(body), "Chunk text is not an excerpt"


async def test_gather_returns_note_id_pointers():
    deps = _deps()
    chunks = await gather("topic", mode="full", deps=deps)
    # every chunk points back to a note_id (the [[note-id]] pointer the model resolves)
    assert all(c.note_id for c in chunks)


async def test_read_ceiling_enforced_end_to_end():
    # Wide fan-out → many candidates → only ≤80 are ever fetched.
    fetcher = FakeFetcher()
    deps = _deps(fetcher=fetcher)
    await gather("topic with lots of sources", mode="full", deps=deps)
    assert len(fetcher.read_urls) <= 80


async def test_rank_runs_before_read():
    # Instrument: the fetcher records read order. The first URLs read must be the
    # top-ranked ones (highest RRF). We seed one clearly-authoritative URL and
    # assert it is read (i.e. survived the rank gate), while a low-utility one is
    # only read if budget remains.
    class TaggedProvider(FakeProvider):
        async def search_ex(self, q):
            from tests.test_funnel.conftest import FakeWebResult
            self.calls.append(q.query)
            # one gov authority hit at rank 1, plus filler
            out = [FakeWebResult(url="https://sec.gov/top", title="SEC filing data",
                                 content="body " * 100, serp_rank=1, serp_provider=self.name)]
            for i in range(q.max_results - 1):
                out.append(FakeWebResult(url=f"https://{self.name}.f/{q.query}/{i}",
                                         title="blog", content="body " * 100,
                                         serp_rank=i + 2, serp_provider=self.name))
            return out

    fetcher = FakeFetcher()
    deps = _deps(providers=[TaggedProvider("sonar")], fetcher=fetcher)
    await gather("financial data", mode="full", deps=deps)
    # The authority URL (surfaced by every query at rank 1, multi-RRF) is read.
    assert "https://sec.gov/top" in fetcher.read_urls


async def test_light_mode_smaller_pool_and_no_chain():
    fetcher = FakeFetcher(hub_links={"x": ["y"]})
    deps = _deps(fetcher=fetcher)
    chunks = await gather("simple question", mode="light", deps=deps)
    assert len(fetcher.read_urls) <= 20      # light READ_TOP_K is 12, ceiling 20-ish
    assert isinstance(chunks, list)


async def test_dedup_collapses_duplicate_providers_end_to_end():
    # All three providers return the SAME url template → heavy URL overlap →
    # candidate pool collapses; far fewer reads than M×P×K raw hits.
    same_tpl = "https://shared.example/{q}/{i}"
    providers = [FakeProvider(n, url_template=same_tpl) for n in ("a", "b", "c")]
    fetcher = FakeFetcher()
    deps = _deps(providers=providers, fetcher=fetcher)
    await gather("topic", mode="full", deps=deps)
    # 3 providers returned identical URLs per query → dedup to 1 per (q,i) slot.
    # raw = M×P×K; deduped reads must be roughly M×K (a third), well under raw.
    assert len(fetcher.read_urls) <= 80


async def test_empty_corpus_returns_empty_not_error():
    # Every page is junk → nothing stored → gather returns [] (honest gap, SPEC §13).
    class AllJunk(FakeFetcher):
        async def fetch_tiered(self, url, *, tier_max=1, instruction=None, schema=None):
            from tests.test_funnel.conftest import FakeWebResult
            self.read_urls.append(url)
            return FakeWebResult(url=url, title="x", content="short")  # junk
    deps = _deps(fetcher=AllJunk())
    chunks = await gather("topic", mode="full", deps=deps)
    assert chunks == []
```

### 8.2 — Run it (RED)

```bash
python -m pytest tests/test_funnel/test_orchestrator.py -q
```

**Expected:** `ModuleNotFoundError: No module named 'bad_research.funnel.orchestrator'`.

### 8.3 — Implement

Create `src/bad_research/funnel/orchestrator.py`:

```python
"""gather() — the public funnel entry point. Wires Stage A→B→C→D→E→F.

INVARIANT: callers receive list[Chunk] (reranked top chunks) + [[note-id]]
pointers — NEVER raw page bodies. Sources scale (12→80 notes); context stays
flat (~5-15k tokens) because only Stage-F chunks ever cross into the prompt.

Stages A-E run at $0 model cost. The seams (providers/fetch_tiered/postfetch_
filter/RetrievalEngine/vault) are injected via FunnelDeps so the funnel logic
is testable in isolation; the width-sweep skill backend (Plan 08) assembles the
real wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bad_research.funnel.config import FunnelConfig
from bad_research.funnel.dedup import dedup
from bad_research.funnel.fanout import fan_out, plan_queries
from bad_research.funnel.filter import filter_and_store
from bad_research.funnel.rank import rank_candidates
from bad_research.funnel.read import read_top_k


@dataclass
class FunnelDeps:
    """The cross-plan seams the funnel composes (all behind Protocols).

    providers:        list[WebSearchProvider]  (Plan 03 cascade survivors)
    fetcher:          obj with async fetch_tiered(url, *, tier_max, ...) (Plan 04)
    postfetch_filter: callable(WebResult) -> str | None  (Plan 05)
    vault:            obj with store_note(*, title, body, url, provider) -> note_id
    retrieval:        RetrievalEngine (Plan 02) — .index(notes), .search(q, mode, top_k)
    """

    providers: list
    fetcher: object
    postfetch_filter: object
    vault: object
    retrieval: object


async def gather(
    query: str,
    *,
    mode: Literal["light", "full"],
    deps: FunnelDeps,
    queries: list | None = None,
) -> list:
    """Run the six-stage funnel and return reranked Chunk[] (never raw pages).

    `queries` (optional): a caller-supplied lens-driven SearchQuery plan
    (the width-sweep skill passes its 3-lens A/B/C/D plan). When omitted we fall
    back to plan_queries (deterministic expansion).
    """
    cfg = FunnelConfig.for_mode(mode)

    # ── Stage A — FAN-OUT (parallel, cheap, never near the model) ──────────
    if queries is None:
        queries = plan_queries(query, m_queries=cfg.m_queries, k_per_query=cfg.k_per_query)
    active_providers = deps.providers[: cfg.p_providers]
    raw_hits = await fan_out(queries, active_providers)

    # ── Stage B — DEDUP (URL-canonical + content-hash, free) ───────────────
    candidates = dedup(raw_hits)
    candidates = candidates[: cfg.candidate_pool]   # cap the pool

    # ── Stage C — RANK un-read candidates (RRF k=60 + utility) ─────────────
    ranked = rank_candidates(candidates, query, rrf_k=cfg.rrf_k)

    # ── Stage D — READ top-K (≤80 ceiling, batched, chained-crawl) ─────────
    pages = await read_top_k(
        ranked,
        fetcher=deps.fetcher,
        read_top_k=cfg.read_top_k,
        concurrency=cfg.read_concurrency,
        max_chain_depth=cfg.max_chain_depth,
        max_links_per_hub=cfg.max_links_per_hub,
        query=query,
        ceiling=FunnelConfig.READ_CEILING,
    )

    # ── Stage E — FILTER (junk + >60% redundancy) + STORE to vault ─────────
    stored = filter_and_store(
        pages,
        vault=deps.vault,
        postfetch_filter=deps.postfetch_filter,
        redundancy_overlap=cfg.redundancy_overlap,
        shingle_n=cfg.shingle_n,
    )
    if not stored:
        return []   # honest gap, never hallucinate (SPEC §13)

    # ── Stage F — RERANK chunks via RetrievalEngine → top set ──────────────
    # The vault holds the breadth (raw bodies on disk); the engine indexes them
    # and returns only the reranked top chunks the model will see.
    deps.retrieval.index(stored)
    chunks = deps.retrieval.search(query, mode=mode, top_k=cfg.top_chunks)
    return chunks
```

### 8.4 — Run it (GREEN)

```bash
python -m pytest tests/test_funnel/test_orchestrator.py -q
```

**Expected:** `8 passed`.

> If `test_light_mode_smaller_pool_and_no_chain` reads more than 20 URLs, check that `FunnelConfig.for_mode("light").read_top_k == 12` and `candidate_pool == 20` so the pool itself caps reads. If `test_no_raw_page_body_leaks_into_return` fails because a chunk equals a body, the `FakeRetrievalEngine.search` excerpt slice (`body[:60]`) must be shorter than every fake body (each is `"real content " * 80` ≈ 1040 chars) — confirm the fetcher's content is long enough.

### 8.5 — Run the full funnel suite

```bash
python -m pytest tests/test_funnel/ -q
```

**Expected:** all tests pass (≈ 8 + 4 + 8 + 7 + 6 + 7 + 5 + 8 across the modules — `48 passed`). Confirm the count.

### 8.6 — Commit

```bash
git add src/bad_research/funnel/orchestrator.py tests/test_funnel/test_orchestrator.py
git commit -m "feat(funnel): gather() orchestrator — A->F wired, no-raw-text invariant enforced

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9 — Type-check, lint, and finalize the public API

**Why:** the funnel composes typed seams; mypy must confirm signature consistency with `INTERFACES.md`. Ruff enforces the repo style.

### 9.1 — Type-check

```bash
python -m mypy src/bad_research/funnel/
```

**Expected:** `Success: no issues found`. If mypy complains about the injected seam types (they're `object` in `FunnelDeps`), that is intentional for isolation — the production wiring (Plan 08) substitutes the concrete Protocol types. If strict mode flags the `object` attribute access in `orchestrator.gather`, add `# type: ignore[attr-defined]` only on the `deps.*` seam calls (they are duck-typed Protocols resolved at wiring time), with a comment citing this.

### 9.2 — Lint

```bash
python -m ruff check src/bad_research/funnel/ tests/test_funnel/
```

**Expected:** `All checks passed!`. Fix any issues (ruff config: line-length 100, but `E501` is ignored).

### 9.3 — Confirm the public surface

```bash
python -c "from bad_research.funnel import gather, FunnelConfig; import inspect; print(inspect.signature(gather))"
```

**Expected:** `(query: str, *, mode: Literal['light', 'full'], deps: bad_research.funnel.orchestrator.FunnelDeps, queries: list | None = None) -> list`

### 9.4 — Final commit

```bash
git add -A
git commit -m "chore(funnel): mypy + ruff clean; finalize public API

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## New shared type added to INTERFACES.md

This plan introduces **one** new shared type that other plans (08 — the width-sweep skill backend that calls `gather`) must reference. Add it to `INTERFACES.md` under "Seam signatures":

```python
# funnel/orchestrator.py  (Plan 07)
@dataclass
class FunnelDeps:
    providers: list            # list[WebSearchProvider]  (Plan 03 cascade survivors)
    fetcher: object            # has: async fetch_tiered(url, *, tier_max, instruction, schema)  (Plan 04)
    postfetch_filter: object   # callable(WebResult) -> str | None  (Plan 05)
    vault: object              # has: store_note(*, title, body, url, provider) -> note_id
    retrieval: object          # RetrievalEngine (Plan 02): .index(notes), .search(query, *, mode, top_k)

async def gather(query: str, *, mode: Literal["light","full"],
                 deps: FunnelDeps, queries: list[SearchQuery] | None = None) -> list[Chunk]: ...
# Runs the 6-stage funnel (SPEC §6). Returns reranked top Chunk[] + [[note-id]]
# pointers — NEVER raw page bodies. Stages A-E are $0 model cost.
```

Also note: this plan assumes the hyperresearch base provides `bad_research.core.similarity` (`shingle`, `jaccard`) carried over by Plan 01's fork — the redundancy filter reuses it verbatim. And it assumes the vault exposes a `store_note(*, title, body, url, provider) -> note_id` helper (thin wrapper over `core/fetcher.write_note` + the `sources` row); if Plan 01 hasn't surfaced that exact signature, add it as a small adapter (`funnel/store.py`) — but the contract above is what `gather` calls.

---

## Done criteria

- [ ] `python -m pytest tests/test_funnel/ -q` → all pass (~48 tests).
- [ ] `gather(query, *, mode, deps) -> list[Chunk]` returns only `Chunk`s; the no-raw-text invariant test passes.
- [ ] The ≤80 read ceiling is enforced end-to-end (the 81st candidate is never read).
- [ ] Fan-out runs providers in parallel (wall time < serial floor) and merges/dedups.
- [ ] Redundancy filter drops >60%-overlap derivatives.
- [ ] mypy + ruff clean on `funnel/`.
- [ ] `FunnelDeps` + `gather` added to `INTERFACES.md`.
