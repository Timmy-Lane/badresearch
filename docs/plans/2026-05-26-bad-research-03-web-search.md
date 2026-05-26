# Bad Research — Plan 03: Web-Search Cascade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `web/providers/` layer — five `WebSearchProvider` implementations (`tavily`, `exa`-extended, `sonar`, `searxng`, `firecrawl`) with verbatim real-API param mapping, plus the three-stage `cascade_search()` (intent route → fast-keyword parallel union+dedup → conditional neural rerank → deep extract) with a zero-key degradation path — all returning hyperresearch's existing `WebResult`.

**Architecture:** Each provider is a thin adapter that mirrors the existing `web/exa_provider.py` shape (lazy SDK/`httpx` import, keyed `RuntimeError` on missing env var, a private `_to_web_result()` normalizer). All providers implement the `WebSearchProvider` Protocol (extends hyperresearch's `WebProvider` with `search_ex(SearchQuery) -> list[WebResult]`, `capabilities`, `cost_per_search`, `p50_ms`). The `CascadeProvider` composes them: Stage-0 intent route (rules) picks lane; Stage-1 fires the fast-keyword providers (tavily+sonar+searxng) in parallel and dedups by canonical URL; Stage-2 (Exa neural + RRF `k=60` + injected `Reranker`) fires **only when <30% of Stage-1 results clear the `0.70` bar**; Stage-3 deep-extracts the selected URLs via Firecrawl/Exa-contents/crawl4ai, gated by `WebResult.looks_like_junk()`/`looks_like_login_wall()`. Cost/quality decisions trace to dossier `investigation/02_WEB_SEARCH.md` and the frozen constants in `INTERFACES.md`.

**Tech Stack:** Python 3.11+, `httpx` (already a hyperresearch dep) for Tavily/Sonar/SearXNG/Firecrawl HTTP; `exa-py` SDK (already optional dep) for Exa; `pytest` + `respx` (httpx mock — new dev dep) for the HTTP-calling providers; `unittest.mock.monkeypatch` for the Exa SDK (matching the existing `test_exa_provider.py` pattern); `concurrent.futures.ThreadPoolExecutor` for Stage-1 parallel fan-out.

---

## Context for the implementer (read before Task 1)

You are working inside the fork repo at `ultimate-research/bad-research/` (source root `src/bad_research/`, a fork of `hyperresearch/src/hyperresearch/`). When this plan says "the package", it means `bad_research`. The reference clone to read while implementing is `/Users/seventyleven/Desktop/researchfms/hyperresearch/` (read-only).

**Already exists in the fork (from the hyperresearch base — do NOT re-create):**
- `src/bad_research/web/base.py` — `WebResult` dataclass (verbatim, see below), `WebProvider` Protocol (`name`, `fetch`, `search`), `get_provider(name, profile, magic, headless)` factory.
- `src/bad_research/web/builtin.py` — `BuiltinProvider` (stdlib fetch, `search()` raises `NotImplementedError`).
- `src/bad_research/web/crawl4ai_provider.py` — `Crawl4AIProvider` (browser fetch).
- `src/bad_research/web/exa_provider.py` — `ExaProvider` (the reference adapter shape; we EXTEND it in Task 5).

**`WebResult` (frozen — `web/base.py`, reuse verbatim, never redefine):**
```python
@dataclass
class WebResult:
    url: str
    title: str
    content: str  # clean markdown or plain text
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw_html: str | None = None
    metadata: dict = field(default_factory=dict)
    media: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    screenshot: bytes | None = None
    raw_bytes: bytes | None = None
    raw_content_type: str | None = None
    # @property domain; def looks_like_login_wall(original_url); def looks_like_junk() -> str | None
```

**`Reranker` Protocol (frozen — from Plan 02, `retrieval/base.py`, INTERFACES.md):** the cascade's Stage-2 takes an *injected* `Reranker` so it does not depend on Plan 02's concrete engine and is unit-testable with a stub:
```python
class Reranker(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...  # (idx, score) desc
```

**Frozen constants used by this plan (cite exactly — INTERFACES.md "Frozen constants" + dossier 02):**

| Constant | Value | Where used |
|---|---|---|
| RRF `k` | `60` | Stage-2 fusion (`_rrf_fuse`) |
| relevance drop threshold | `0.70` | Stage-1 thin-test + Stage-2/3 gate |
| re-retrieve trigger / max rounds | `<30%` pass / `2` | Stage-1→Stage-2 fire condition |
| dedup canonical-URL | exact-URL canonicalization (strip scheme-case/`www.`/fragment/trailing-slash/utm-*) | Stage-1 dedup (free) |
| Sonar `cost_per_search` / `p50_ms` | `0.005` / `358` | provider attrs (PERPLEXITY_DEEP §4) |
| Exa-neural `cost_per_search` / `p50_ms` | `0.005` / `1375` | provider attrs (EXA §8.4) |
| Tavily `cost_per_search` (advanced=2cr) / `p50_ms` | `0.008` / `1342` | provider attrs (TAVILY §3.6) |
| SearXNG `cost_per_search` / `p50_ms` | `0.0` / `800` | provider attrs (zero-key) |
| Tavily quota HTTP codes | `432`/`433` → permanent; `429` → backoff | error classes |
| Exa contents text default | `8000` chars | extend ExaProvider |

**Test mocking decision (read once, applies to every provider task):**
- Providers that call `httpx.post`/`httpx.get` directly (Tavily, Sonar, SearXNG, Firecrawl) → mock the wire with **`respx`** (the canonical httpx mock; it intercepts at the transport layer so we assert the EXACT request payload). Add `respx>=0.21` to `[project.optional-dependencies].dev` in `pyproject.toml`.
- The Exa extension → keep the existing pattern: `monkeypatch.setattr(exa_py, "Exa", MagicMock(...))` (matches `tests/test_web/test_exa_provider.py`).
- The cascade → inject **stub** providers (plain objects implementing the Protocol) + a **stub** `Reranker`; no HTTP at all. This makes routing logic deterministic and fast.

**The `_to_web_result()` discipline (mirror `exa_provider.py:101-135` for every provider):** a private module-level function that takes the provider's raw row dict and returns a `WebResult`, putting the relevance `score` and `snippet` into `metadata`. Content-less SERP rows (Sonar/SearXNG) put the SERP `snippet` into `content`; the deep-extraction stage fills full content later.

---

## File Structure

All new files under `src/bad_research/web/providers/` (new package). Tests mirror under `tests/test_web/providers/`.

```
src/bad_research/web/
  base.py                         # EXISTS — extend with SearchQuery + WebSearchProvider Protocol + cascade error classes (Task 1)
  exa_provider.py                 # EXISTS — extend: search_ex, capabilities, cost_per_search, p50_ms, find_similar (Task 5)
  providers/
    __init__.py                   # new — re-exports the five provider classes + CascadeProvider (Task 9)
    tavily_provider.py            # new — TavilyProvider (Task 2)
    sonar_provider.py             # new — SonarProvider (Task 3)
    searxng_provider.py           # new — SearxngProvider (Task 4)
    firecrawl_provider.py         # new — FirecrawlProvider (Task 6)
    cascade.py                    # new — CascadeProvider + cascade_search + _rrf_fuse + _canonical_url + _dedup_union (Tasks 7,8)

tests/test_web/
  providers/
    __init__.py                   # new — empty
    test_tavily_provider.py       # Task 2
    test_sonar_provider.py        # Task 3
    test_searxng_provider.py      # Task 4
    test_firecrawl_provider.py    # Task 6
    test_cascade.py               # Tasks 7,8
  test_exa_provider.py            # EXISTS — add search_ex/find_similar tests (Task 5)
  test_web_search_query.py        # Task 1 — SearchQuery + WebSearchProvider Protocol + error classes

pyproject.toml                    # MODIFY — add respx dev dep + tavily/firecrawl/searxng have no SDK (httpx only); register provider extras (Task 10)
```

Responsibility split: each provider file owns exactly one upstream API and its `_to_web_result`. `cascade.py` owns ONLY routing/fusion/dedup — it never talks to an upstream directly, it composes provider instances passed to its constructor. `base.py` owns the shared types (`SearchQuery`, `WebSearchProvider`, error classes) so every provider imports them from one place.

---

## Task 1: Shared types — `SearchQuery`, `WebSearchProvider`, cascade error classes

**Files:**
- Modify: `src/bad_research/web/base.py` (append after the existing `WebProvider` Protocol, before `get_provider`)
- Test: `tests/test_web/test_web_search_query.py`

These are the cross-plan contract types from INTERFACES.md §"Seam signatures". They MUST match verbatim so Plans 04–09 can import them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/test_web_search_query.py`:
```python
"""SearchQuery dataclass + WebSearchProvider Protocol + cascade error classes."""

from __future__ import annotations

import pytest

from bad_research.web.base import (
    ProviderError,
    QuotaExceeded,
    RateLimited,
    SearchQuery,
    WebProvider,
    WebResult,
    WebSearchProvider,
)


def test_search_query_defaults() -> None:
    q = SearchQuery(query="rust async runtimes")
    assert q.query == "rust async runtimes"
    assert q.intent == "keyword"
    assert q.recency_days is None
    assert q.include_domains is None
    assert q.exclude_domains is None
    assert q.max_results == 10


def test_search_query_full() -> None:
    q = SearchQuery(
        query="latest llm benchmarks",
        intent="neural",
        recency_days=7,
        include_domains=["arxiv.org"],
        exclude_domains=["pinterest.com"],
        max_results=20,
    )
    assert q.intent == "neural"
    assert q.recency_days == 7
    assert q.include_domains == ["arxiv.org"]
    assert q.max_results == 20


def test_intent_literal_values() -> None:
    for intent in ("keyword", "neural", "deep"):
        q = SearchQuery(query="x", intent=intent)  # type: ignore[arg-type]
        assert q.intent == intent


def test_web_search_provider_is_runtime_checkable() -> None:
    """A duck-typed object implementing the surface passes isinstance."""

    class _Stub:
        name = "stub"
        capabilities = {"keyword"}
        cost_per_search = 0.0
        p50_ms = 100

        def fetch(self, url: str) -> WebResult:
            return WebResult(url=url, title="", content="x" * 400)

        def search(self, query: str, max_results: int = 5) -> list[WebResult]:
            return []

        def search_ex(self, q: SearchQuery) -> list[WebResult]:
            return []

    stub = _Stub()
    assert isinstance(stub, WebSearchProvider)
    assert isinstance(stub, WebProvider)  # extends the base Protocol


def test_error_class_hierarchy() -> None:
    """QuotaExceeded and RateLimited are distinct from generic ProviderError."""
    assert issubclass(QuotaExceeded, ProviderError)
    assert issubclass(RateLimited, ProviderError)
    assert not issubclass(QuotaExceeded, RateLimited)
    with pytest.raises(ProviderError):
        raise QuotaExceeded("plan quota exhausted")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_web_search_query.py -v`
Expected: FAIL — `ImportError: cannot import name 'SearchQuery' from 'bad_research.web.base'`

- [ ] **Step 3: Write minimal implementation**

In `src/bad_research/web/base.py`, change the imports line at top from `from typing import Protocol, runtime_checkable` (leave it) and add `Literal`:
```python
from typing import Literal, Protocol, runtime_checkable
```
Then append after the `WebProvider` Protocol class (before `def get_provider`):
```python
# --- Cascade error classes (Plan 03; cite dossier 02 §6.5) ---------------------


class ProviderError(Exception):
    """A provider failed in a way that should advance the cascade ladder.

    5xx, timeouts, malformed responses. The cascade catches this and tries the
    next provider immediately.
    """


class QuotaExceeded(ProviderError):
    """Plan/pay-as-you-go limit hit — permanent for this run, do NOT retry.

    Tavily 432 (plan quota) / 433 (PAYG limit); Exa x402. The cascade skips this
    provider for the remainder of the run.
    """


class RateLimited(ProviderError):
    """Transient 429 — back off (2s -> x1.5 -> 10s cap) then advance the ladder."""


# --- Rich search surface (Plan 03; INTERFACES.md "Seam signatures") ------------


@dataclass
class SearchQuery:
    """A normalized search request that the rich `search_ex()` path consumes.

    `intent` picks the cascade lane: keyword (fast SERP), neural (semantic),
    deep (full extraction). `recency_days` maps to each provider's recency
    filter (Tavily time_range / Sonar search_recency_filter / Exa published-date).
    """

    query: str
    intent: Literal["keyword", "neural", "deep"] = "keyword"
    recency_days: int | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    max_results: int = 10


@runtime_checkable
class WebSearchProvider(WebProvider, Protocol):
    """Extends WebProvider with the rich, capability-aware search surface.

    `capabilities` advertises what the provider can do so the cascade can route
    (subset of {"keyword","neural","extract","crawl"}). `cost_per_search` and
    `p50_ms` let the cascade order/budget providers.
    """

    name: str
    capabilities: set[str]
    cost_per_search: float
    p50_ms: int

    def fetch(self, url: str) -> WebResult: ...

    def search_ex(self, q: SearchQuery) -> list[WebResult]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_web_search_query.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/base.py tests/test_web/test_web_search_query.py
git commit -m "feat(web): add SearchQuery, WebSearchProvider Protocol, cascade error classes"
```

---

## Task 2: `TavilyProvider` — SERP-fusion + RAG extract

**Files:**
- Create: `src/bad_research/web/providers/__init__.py` (empty for now; re-exports added in Task 9)
- Create: `src/bad_research/web/providers/tavily_provider.py`
- Create: `tests/test_web/providers/__init__.py` (empty)
- Test: `tests/test_web/providers/test_tavily_provider.py`

Maps `SearchQuery` → `POST https://api.tavily.com/search` with the exact dossier-02 §1.5 payload. Auth via `Authorization: Bearer tvly-...` **header** (not body). Strips `None` values. Splits quota codes: 432/433 → `QuotaExceeded`, 429 → `RateLimited`. Cites dossier 02 §1.1, §1.5; constants §1.4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/providers/test_tavily_provider.py`:
```python
"""TavilyProvider — mocks the api.tavily.com HTTP wire via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from bad_research.web.base import (
    QuotaExceeded,
    RateLimited,
    SearchQuery,
    WebResult,
    WebSearchProvider,
)
from bad_research.web.providers.tavily_provider import TavilyProvider

SEARCH_URL = "https://api.tavily.com/search"
EXTRACT_URL = "https://api.tavily.com/extract"


def _sample_results() -> dict:
    return {
        "query": "rust async",
        "results": [
            {
                "title": "Async Rust",
                "url": "https://a.test/async",
                "content": "Short AI snippet about async rust.",
                "raw_content": "# Async Rust\n\nFull markdown body here, long enough to matter.",
                "score": 0.97,
                "published_date": "2026-03-01",
                "favicon": "https://a.test/favicon.ico",
            },
            {
                "title": "Tokio",
                "url": "https://b.test/tokio",
                "content": "Tokio snippet.",
                "score": 0.81,
            },
        ],
        "response_time": 1.2,
        "request_id": "req-1",
    }


def test_provider_attrs() -> None:
    prov = TavilyProvider(api_key="tvly-test")
    assert prov.name == "tavily"
    assert prov.capabilities == {"keyword", "extract"}
    assert prov.cost_per_search == 0.008
    assert prov.p50_ms == 1342
    assert isinstance(prov, WebSearchProvider)


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        TavilyProvider()


@respx.mock
def test_search_ex_builds_exact_payload() -> None:
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_sample_results())
    )
    prov = TavilyProvider(api_key="tvly-test")
    q = SearchQuery(
        query="rust async",
        recency_days=7,
        include_domains=["a.test"],
        exclude_domains=["spam.test"],
        max_results=15,
    )
    results = prov.search_ex(q)

    assert route.called
    sent = route.calls.last.request
    # Auth is a header, NOT in the body (dossier 02 §1.1).
    assert sent.headers["authorization"] == "Bearer tvly-test"
    assert sent.headers["x-client-source"] == "bad-research"
    import json

    body = json.loads(sent.content)
    assert body["query"] == "rust async"
    assert body["search_depth"] == "advanced"          # dossier 02 §1.5
    assert body["include_raw_content"] == "markdown"
    assert body["chunks_per_source"] == 3
    assert body["include_favicon"] is True
    assert body["max_results"] == 15
    assert body["time_range"] == "week"                # recency_days 7 -> "week"
    assert body["include_domains"] == ["a.test"]
    assert body["exclude_domains"] == ["spam.test"]
    # None values are stripped — no `topic` / `country` keys.
    assert "topic" not in body
    assert "country" not in body

    assert len(results) == 2
    assert all(isinstance(r, WebResult) for r in results)
    # raw_content wins over content when present.
    assert results[0].content.startswith("# Async Rust")
    assert results[0].metadata["score"] == 0.97
    assert results[0].metadata["snippet"] == "Short AI snippet about async rust."
    assert results[0].metadata["published_date"] == "2026-03-01"
    assert results[0].metadata["favicon"] == "https://a.test/favicon.ico"
    # row without raw_content falls back to content.
    assert results[1].content == "Tokio snippet."


@respx.mock
def test_recency_days_buckets() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = TavilyProvider(api_key="tvly-test")
    import json

    for days, expected in [(1, "day"), (7, "week"), (30, "month"), (365, "year"), (500, "year")]:
        prov.search_ex(SearchQuery(query="x", recency_days=days))
        body = json.loads(respx.calls.last.request.content)
        assert body["time_range"] == expected, f"{days} -> {expected}"


@respx.mock
def test_max_results_capped_at_20() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = TavilyProvider(api_key="tvly-test")
    prov.search_ex(SearchQuery(query="x", max_results=999))
    import json

    body = json.loads(respx.calls.last.request.content)
    assert body["max_results"] == 20   # MAX_RESULTS_CEILING (dossier 02 §1.5)


@respx.mock
def test_quota_codes_raise_permanent() -> None:
    prov = TavilyProvider(api_key="tvly-test")
    for code in (432, 433):
        respx.post(SEARCH_URL).mock(return_value=httpx.Response(code, json={"error": "quota"}))
        with pytest.raises(QuotaExceeded):
            prov.search_ex(SearchQuery(query="x"))


@respx.mock
def test_429_raises_rate_limited() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(429, json={"error": "slow down"}))
    prov = TavilyProvider(api_key="tvly-test")
    with pytest.raises(RateLimited):
        prov.search_ex(SearchQuery(query="x"))


@respx.mock
def test_5xx_raises_provider_error() -> None:
    from bad_research.web.base import ProviderError

    respx.post(SEARCH_URL).mock(return_value=httpx.Response(502, text="bad gateway"))
    prov = TavilyProvider(api_key="tvly-test")
    with pytest.raises(ProviderError):
        prov.search_ex(SearchQuery(query="x"))


@respx.mock
def test_fetch_uses_extract_endpoint() -> None:
    route = respx.post(EXTRACT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://a.test/page", "raw_content": "Extracted markdown body."}
                ],
                "failed_results": [],
            },
        )
    )
    prov = TavilyProvider(api_key="tvly-test")
    result = prov.fetch("https://a.test/page")

    assert route.called
    import json

    body = json.loads(route.calls.last.request.content)
    assert body["urls"] == ["https://a.test/page"]
    assert body["extract_depth"] == "advanced"
    assert body["format"] == "markdown"
    assert isinstance(result, WebResult)
    assert result.content == "Extracted markdown body."


@respx.mock
def test_search_str_path_delegates_to_search_ex() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json=_sample_results()))
    prov = TavilyProvider(api_key="tvly-test")
    results = prov.search("rust async", max_results=2)
    assert len(results) == 2
    assert results[0].url == "https://a.test/async"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_tavily_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.web.providers'`

- [ ] **Step 3: Write minimal implementation**

Create `src/bad_research/web/providers/__init__.py`:
```python
"""Web search providers + the search cascade (Plan 03)."""
```

Create `tests/test_web/providers/__init__.py` (empty file, zero bytes).

Create `src/bad_research/web/providers/tavily_provider.py`:
```python
"""Tavily web provider — SERP-fusion search built for machines.

POST https://api.tavily.com/search. Auth is a Bearer header (not body).
Maps SearchQuery -> the advanced-depth, raw-markdown, RAG-native payload from
dossier 02 §1.5. Splits Tavily's custom quota codes (432/433 permanent, 429
transient) into the cascade's error classes.

Configuration:
    export TAVILY_API_KEY="tvly-..."
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import (
    ProviderError,
    QuotaExceeded,
    RateLimited,
    SearchQuery,
    WebResult,
)

# Constants (KNOWN — dossier 02 §1.4, §1.5; products/TAVILY_PRODUCT_CODE.md:130-281).
_BASE = "https://api.tavily.com"
_MAX_RESULTS_CEILING = 20
_DEFAULT_CHUNKS_PER_SOURCE = 3
_SEARCH_TIMEOUT_S = 60
_EXTRACT_TIMEOUT_S = 30
_CLIENT_SOURCE = "bad-research"


def _recency_to_time_range(days: int | None) -> str | None:
    """Map recency_days to Tavily's time_range bucket (day/week/month/year)."""
    if days is None:
        return None
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class TavilyProvider:
    name = "tavily"
    capabilities = {"keyword", "extract"}
    cost_per_search = 0.008  # advanced = 2 credits (dossier 02 §1.4)
    p50_ms = 1342            # PERPLEXITY_DEEP §4 measured

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("TAVILY_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Get a key at https://app.tavily.com "
                "and export it."
            )
        self._key = key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "X-Client-Source": _CLIENT_SOURCE,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code in (432, 433):
            raise QuotaExceeded(f"Tavily quota exhausted (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise RateLimited("Tavily rate limited (HTTP 429)")
        if resp.status_code >= 500 or resp.status_code >= 400:
            raise ProviderError(f"Tavily error HTTP {resp.status_code}: {resp.text[:200]}")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "search_depth": "advanced",
            "include_raw_content": "markdown",
            "chunks_per_source": _DEFAULT_CHUNKS_PER_SOURCE,
            "include_favicon": True,
            "max_results": min(q.max_results, _MAX_RESULTS_CEILING),
            "time_range": _recency_to_time_range(q.recency_days),
            "include_domains": q.include_domains,
            "exclude_domains": q.exclude_domains,
        }
        # Strip None values (dossier 02 §1.1 — the SDK does this so undocumented
        # params and unset filters never hit the wire).
        body = {k: v for k, v in body.items() if v is not None}
        try:
            resp = httpx.post(
                f"{_BASE}/search", json=body, headers=self._headers(), timeout=_SEARCH_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Tavily request failed: {exc}") from exc
        self._raise_for_status(resp)
        return [_to_web_result(row) for row in resp.json().get("results", [])]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        body = {"urls": [url], "extract_depth": "advanced", "format": "markdown"}
        try:
            resp = httpx.post(
                f"{_BASE}/extract", json=body, headers=self._headers(), timeout=_EXTRACT_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Tavily extract failed: {exc}") from exc
        self._raise_for_status(resp)
        rows = resp.json().get("results", [])
        if not rows:
            raise ProviderError(f"Tavily returned no content for {url}")
        row = rows[0]
        return WebResult(
            url=row.get("url", url),
            title=row.get("title", ""),
            content=row.get("raw_content") or row.get("content", ""),
            fetched_at=datetime.now(UTC),
            metadata={"favicon": row.get("favicon")} if row.get("favicon") else {},
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    """Normalize a Tavily search row -> WebResult.

    raw_content (full markdown) wins over content (the ~500-char AI snippet);
    the snippet is preserved in metadata.
    """
    metadata: dict[str, Any] = {}
    if row.get("score") is not None:
        metadata["score"] = row["score"]
    if row.get("content"):
        metadata["snippet"] = row["content"]
    if row.get("published_date"):
        metadata["published_date"] = row["published_date"]
    if row.get("favicon"):
        metadata["favicon"] = row["favicon"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("raw_content") or row.get("content", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_tavily_provider.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/__init__.py src/bad_research/web/providers/tavily_provider.py tests/test_web/providers/__init__.py tests/test_web/providers/test_tavily_provider.py
git commit -m "feat(web): TavilyProvider — advanced SERP search + extract, quota-code-aware"
```

---

## Task 3: `SonarProvider` — Perplexity raw `/search` (fast tier, batch + verticals)

**Files:**
- Create: `src/bad_research/web/providers/sonar_provider.py`
- Test: `tests/test_web/providers/test_sonar_provider.py`

Maps `SearchQuery` → `POST https://api.perplexity.ai/search` (raw search, no LLM synthesis). `search_mode` (web/academic/sec) is a provider-construction param. `recency_days` → `search_recency_filter`. Returns content-less SERP rows (snippet → `content`). `fetch()` is not native — raises `ProviderError` so the cascade delegates to firecrawl/builtin. Cites dossier 02 §4.1, §4.5; constants §4.4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/providers/test_sonar_provider.py`:
```python
"""SonarProvider — mocks api.perplexity.ai/search via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from bad_research.web.base import ProviderError, SearchQuery, WebResult, WebSearchProvider
from bad_research.web.providers.sonar_provider import SonarProvider

SEARCH_URL = "https://api.perplexity.ai/search"


def _sample() -> dict:
    return {
        "id": "s-1",
        "results": [
            {
                "title": "Deep Research Survey",
                "url": "https://arxiv.org/abs/1234",
                "snippet": "A survey of deep research agents and their retrieval loops.",
                "date": "2026-02-15",
                "last_updated": "2026-02-20",
            },
            {
                "title": "Sonar API",
                "url": "https://docs.perplexity.ai/sonar",
                "snippet": "The Sonar search endpoint supports batch queries.",
            },
        ],
    }


def test_provider_attrs() -> None:
    prov = SonarProvider(api_key="pplx-test")
    assert prov.name == "sonar"
    assert prov.capabilities == {"keyword", "academic"}
    assert prov.cost_per_search == 0.005
    assert prov.p50_ms == 358
    assert isinstance(prov, WebSearchProvider)


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
        SonarProvider()


@respx.mock
def test_search_ex_builds_payload() -> None:
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json=_sample()))
    prov = SonarProvider(api_key="pplx-test", search_mode="academic")
    q = SearchQuery(
        query="deep research agents",
        recency_days=30,
        include_domains=["arxiv.org"],
        exclude_domains=["medium.com"],
        max_results=15,
    )
    results = prov.search_ex(q)

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer pplx-test"
    body = json.loads(sent.content)
    assert body["query"] == "deep research agents"
    assert body["search_mode"] == "academic"
    assert body["max_results"] == 15
    assert body["max_tokens_per_page"] == 4096        # default (dossier 02 §4.1)
    assert body["search_recency_filter"] == "month"   # 30 days -> month
    # domain filter: deny prefixed with "-" (dossier 02 §4.1).
    assert body["search_domain_filter"] == ["arxiv.org", "-medium.com"]

    assert len(results) == 2
    assert all(isinstance(r, WebResult) for r in results)
    # SERP rows are content-less; snippet goes into content.
    assert results[0].content.startswith("A survey of deep research")
    assert results[0].metadata["date"] == "2026-02-15"
    assert results[0].metadata["last_updated"] == "2026-02-20"


@respx.mock
def test_max_results_capped_at_20() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    prov.search_ex(SearchQuery(query="x", max_results=999))
    body = json.loads(respx.calls.last.request.content)
    assert body["max_results"] == 20


@respx.mock
def test_recency_buckets() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    for days, expected in [(0, "hour"), (1, "day"), (7, "week"), (30, "month"), (365, "year")]:
        prov.search_ex(SearchQuery(query="x", recency_days=days))
        body = json.loads(respx.calls.last.request.content)
        assert body.get("search_recency_filter") == expected, f"{days} -> {expected}"


@respx.mock
def test_no_recency_omits_filter() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    prov.search_ex(SearchQuery(query="x"))
    body = json.loads(respx.calls.last.request.content)
    assert "search_recency_filter" not in body


@respx.mock
def test_5xx_raises_provider_error() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    prov = SonarProvider(api_key="pplx-test")
    with pytest.raises(ProviderError):
        prov.search_ex(SearchQuery(query="x"))


def test_fetch_not_native() -> None:
    prov = SonarProvider(api_key="pplx-test")
    with pytest.raises(ProviderError, match="does not support fetch"):
        prov.fetch("https://x.test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_sonar_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.web.providers.sonar_provider'`

- [ ] **Step 3: Write minimal implementation**

Create `src/bad_research/web/providers/sonar_provider.py`:
```python
"""Perplexity Sonar raw-search provider — fastest + highest-quality keyword tier.

POST https://api.perplexity.ai/search (raw search, no LLM synthesis). Exposes
search_mode (web/academic/sec — three distinct indexes) as a construction param.
Returns content-less SERP rows: the snippet becomes WebResult.content; the deep-
extraction stage fills full content. fetch() is not native (dossier 02 §4.5).

Configuration:
    export PERPLEXITY_API_KEY="pplx-..."
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from bad_research.web.base import ProviderError, SearchQuery, WebResult

# Constants (KNOWN — dossier 02 §4.1, §4.4).
_BASE = "https://api.perplexity.ai"
_MAX_RESULTS_CEILING = 20
_DEFAULT_MAX_TOKENS_PER_PAGE = 4096
_TIMEOUT_S = 30
_MAX_DOMAIN_FILTER = 20


def _recency_to_filter(days: int | None) -> str | None:
    """Map recency_days -> Sonar search_recency_filter (hour/day/week/month/year)."""
    if days is None:
        return None
    if days <= 0:
        return "hour"
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class SonarProvider:
    name = "sonar"
    capabilities = {"keyword", "academic"}
    cost_per_search = 0.005  # flat per-request (dossier 02 §4.4)
    p50_ms = 358             # fastest of all four (PERPLEXITY_DEEP §4)

    def __init__(
        self,
        api_key: str | None = None,
        search_mode: Literal["web", "academic", "sec"] = "web",
        max_tokens_per_page: int = _DEFAULT_MAX_TOKENS_PER_PAGE,
    ):
        key = api_key or os.environ.get("PERPLEXITY_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "PERPLEXITY_API_KEY is not set. Get a key at "
                "https://www.perplexity.ai/settings/api and export it."
            )
        self._key = key
        self._mode = search_mode
        self._mtpp = max_tokens_per_page

    def _build_domain_filter(self, q: SearchQuery) -> list[str] | None:
        allow = q.include_domains or []
        deny = [f"-{d}" for d in (q.exclude_domains or [])]
        combined = (allow + deny)[:_MAX_DOMAIN_FILTER]
        return combined or None

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "max_results": min(q.max_results, _MAX_RESULTS_CEILING),
            "search_mode": self._mode,
            "max_tokens_per_page": self._mtpp,
        }
        recency = _recency_to_filter(q.recency_days)
        if recency is not None:
            body["search_recency_filter"] = recency
        domain_filter = self._build_domain_filter(q)
        if domain_filter is not None:
            body["search_domain_filter"] = domain_filter

        try:
            resp = httpx.post(
                f"{_BASE}/search",
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Sonar request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"Sonar error HTTP {resp.status_code}: {resp.text[:200]}")
        return [_to_web_result(row) for row in resp.json().get("results", [])]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        raise ProviderError(
            "Sonar does not support fetch — delegate to firecrawl/exa/builtin in the cascade."
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("date"):
        metadata["date"] = row["date"]
    if row.get("last_updated"):
        metadata["last_updated"] = row["last_updated"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("snippet", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_sonar_provider.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/sonar_provider.py tests/test_web/providers/test_sonar_provider.py
git commit -m "feat(web): SonarProvider — Perplexity raw /search, academic/sec verticals"
```

---

## Task 4: `SearxngProvider` — zero-key self-host search backbone

**Files:**
- Create: `src/bad_research/web/providers/searxng_provider.py`
- Test: `tests/test_web/providers/test_searxng_provider.py`

`GET {SEARXNG_ENDPOINT}/search?q=...&format=json`. No API key — `cost_per_search = 0.0`. This is the zero-key degradation backbone. Endpoint defaults to `http://localhost:8080` (overridable via env). Returns content-less SERP rows. `fetch()` not native. Cites dossier 02 §5, §6.4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/providers/test_searxng_provider.py`:
```python
"""SearxngProvider — mocks the SearXNG /search JSON endpoint via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from bad_research.web.base import ProviderError, SearchQuery, WebResult, WebSearchProvider
from bad_research.web.providers.searxng_provider import SearxngProvider


def _sample() -> dict:
    return {
        "results": [
            {
                "url": "https://x.test/a",
                "title": "A",
                "content": "Snippet A from a metasearch engine.",
                "engine": "google",
                "score": 1.0,
            },
            {
                "url": "https://x.test/b",
                "title": "B",
                "content": "Snippet B.",
                "engine": "bing",
                "score": 0.9,
            },
            {"url": "https://x.test/c", "title": "C", "content": "C", "engine": "ddg"},
        ]
    }


def test_provider_attrs() -> None:
    prov = SearxngProvider(endpoint="http://localhost:8080")
    assert prov.name == "searxng"
    assert prov.capabilities == {"keyword"}
    assert prov.cost_per_search == 0.0
    assert prov.p50_ms == 800
    assert isinstance(prov, WebSearchProvider)


def test_no_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """SearXNG never raises on missing key — it is the zero-key backbone."""
    monkeypatch.delenv("SEARXNG_ENDPOINT", raising=False)
    prov = SearxngProvider()  # defaults to localhost:8080, no raise
    assert prov.name == "searxng"


@respx.mock
def test_search_ex_builds_params_and_truncates() -> None:
    route = respx.get("http://localhost:8080/search").mock(
        return_value=httpx.Response(200, json=_sample())
    )
    prov = SearxngProvider(endpoint="http://localhost:8080")
    results = prov.search_ex(SearchQuery(query="metasearch", max_results=2))

    req = route.calls.last.request
    assert req.url.params["q"] == "metasearch"
    assert req.url.params["format"] == "json"
    assert req.url.params["categories"] == "general"
    # max_results truncates the returned list.
    assert len(results) == 2
    assert all(isinstance(r, WebResult) for r in results)
    assert results[0].content == "Snippet A from a metasearch engine."
    assert results[0].metadata["engine"] == "google"
    assert results[0].metadata["score"] == 1.0


@respx.mock
def test_engines_param_joined() -> None:
    respx.get("http://localhost:8080/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    prov = SearxngProvider(endpoint="http://localhost:8080", engines=["google", "bing"])
    prov.search_ex(SearchQuery(query="x"))
    req = respx.calls.last.request
    assert req.url.params["engines"] == "google,bing"


@respx.mock
def test_endpoint_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARXNG_ENDPOINT", "http://searx.local:9000")
    route = respx.get("http://searx.local:9000/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    prov = SearxngProvider()
    prov.search_ex(SearchQuery(query="x"))
    assert route.called


@respx.mock
def test_connection_error_raises_provider_error() -> None:
    respx.get("http://localhost:8080/search").mock(side_effect=httpx.ConnectError("refused"))
    prov = SearxngProvider(endpoint="http://localhost:8080")
    with pytest.raises(ProviderError):
        prov.search_ex(SearchQuery(query="x"))


def test_fetch_not_native() -> None:
    prov = SearxngProvider(endpoint="http://localhost:8080")
    with pytest.raises(ProviderError, match="does not support fetch"):
        prov.fetch("https://x.test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_searxng_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.web.providers.searxng_provider'`

- [ ] **Step 3: Write minimal implementation**

Create `src/bad_research/web/providers/searxng_provider.py`:
```python
"""SearXNG provider — zero-cost self-hosted metasearch (the zero-key backbone).

GET {endpoint}/search?q=...&format=json. Aggregates Google/Bing/DDG/etc. No API
key, so cost_per_search = 0.0 and it never raises on a missing key — it is the
default search backbone when no premium key is present. Returns <=20 content-less
SERP rows per page; deep-extraction fills full content. (dossier 02 §5, §6.4.)

Configuration:
    export SEARXNG_ENDPOINT="http://localhost:8080"   # default
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import ProviderError, SearchQuery, WebResult

_DEFAULT_ENDPOINT = "http://localhost:8080"
_TIMEOUT_S = 15


class SearxngProvider:
    name = "searxng"
    capabilities = {"keyword"}
    cost_per_search = 0.0
    p50_ms = 800

    def __init__(
        self,
        endpoint: str | None = None,
        engines: list[str] | None = None,
        categories: str = "general",
    ):
        self._url = (
            endpoint or os.environ.get("SEARXNG_ENDPOINT", _DEFAULT_ENDPOINT)
        ).rstrip("/")
        self._engines = engines
        self._categories = categories

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        params: dict[str, str] = {
            "q": q.query,
            "format": "json",
            "categories": self._categories,
        }
        if self._engines:
            params["engines"] = ",".join(self._engines)
        try:
            resp = httpx.get(f"{self._url}/search", params=params, timeout=_TIMEOUT_S)
        except httpx.HTTPError as exc:
            raise ProviderError(f"SearXNG request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"SearXNG error HTTP {resp.status_code}")
        rows = resp.json().get("results", [])[: q.max_results]
        return [_to_web_result(row) for row in rows]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        raise ProviderError(
            "SearXNG does not support fetch — delegate to crawl4ai/builtin in the cascade."
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("engine"):
        metadata["engine"] = row["engine"]
    if row.get("score") is not None:
        metadata["score"] = row["score"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("content", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_searxng_provider.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/searxng_provider.py tests/test_web/providers/test_searxng_provider.py
git commit -m "feat(web): SearxngProvider — zero-key self-host metasearch backbone"
```

---

## Task 5: Extend `ExaProvider` — `search_ex`, `find_similar`, capability attrs

**Files:**
- Modify: `src/bad_research/web/exa_provider.py` (add attrs + methods, keep existing `search`/`fetch`/`_to_web_result` intact)
- Test: `tests/test_web/test_exa_provider.py` (add tests; keep existing ones passing)

Adds the `WebSearchProvider` surface to the existing Exa adapter without breaking its current `search()`/`fetch()`. `search_ex()` maps `SearchQuery` → the exa-py `search` call (type, category, date filters, contents with highlights+summary). `find_similar(url)` wraps `/findSimilar` for citation expansion. Cites dossier 02 §2.1, §2.6.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web/test_exa_provider.py`:
```python
def test_exa_capability_attrs(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.web.base import WebSearchProvider

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = MagicMock()
    client.headers = {}
    _patch_sdk(monkeypatch, client)

    prov = get_provider("exa")
    assert prov.capabilities == {"neural", "keyword", "extract"}
    assert prov.cost_per_search == 0.005
    assert prov.p50_ms == 1375
    assert isinstance(prov, WebSearchProvider)


def test_exa_search_ex_maps_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.web.base import SearchQuery

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = MagicMock()
    client.headers = {}
    client.search.return_value = _make_response([
        _make_result(url="https://n.test", title="N", text="Neural body"),
    ])
    _patch_sdk(monkeypatch, client)

    prov = get_provider("exa")
    q = SearchQuery(
        query="contrastive link prediction",
        intent="neural",
        recency_days=30,
        include_domains=["arxiv.org"],
        exclude_domains=["x.com"],
        max_results=12,
    )
    results = prov.search_ex(q)

    assert len(results) == 1
    assert results[0].content == "Neural body"
    _args, kwargs = client.search.call_args
    assert kwargs["num_results"] == 12
    assert kwargs["type"] == "neural"        # intent="neural" -> type="neural"
    assert kwargs["include_domains"] == ["arxiv.org"]
    assert kwargs["exclude_domains"] == ["x.com"]
    # recency_days populates start_published_date (ISO, ~30 days ago).
    assert "start_published_date" in kwargs
    assert kwargs["contents"]["highlights"] is True
    assert "summary" in kwargs["contents"]


def test_exa_search_ex_keyword_intent_maps_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.web.base import SearchQuery

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = MagicMock()
    client.headers = {}
    client.search.return_value = _make_response([])
    _patch_sdk(monkeypatch, client)

    prov = get_provider("exa")
    prov.search_ex(SearchQuery(query="x", intent="keyword"))
    _args, kwargs = client.search.call_args
    assert kwargs["type"] == "auto"          # non-neural intent -> auto routing


def test_exa_find_similar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = MagicMock()
    client.headers = {}
    client.find_similar_and_contents.return_value = _make_response([
        _make_result(url="https://sim.test", title="Similar", text="Similar body"),
    ])
    _patch_sdk(monkeypatch, client)

    prov = get_provider("exa")
    results = prov.find_similar("https://seed.test", max_results=3)
    assert len(results) == 1
    assert results[0].url == "https://sim.test"
    args, kwargs = client.find_similar_and_contents.call_args
    assert args[0] == "https://seed.test"
    assert kwargs["num_results"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_exa_provider.py -v`
Expected: FAIL — `AttributeError: 'ExaProvider' object has no attribute 'capabilities'` (and the new tests error on `search_ex`/`find_similar`)

- [ ] **Step 3: Write minimal implementation**

In `src/bad_research/web/exa_provider.py`, add to the top imports:
```python
from datetime import UTC, datetime, timedelta
```
(replace the existing `from datetime import UTC, datetime` line).

Add `SearchQuery` to the base import:
```python
from bad_research.web.base import SearchQuery, WebResult
```

Inside `class ExaProvider`, directly under `name = "exa"`, add the capability attrs:
```python
    name = "exa"
    capabilities = {"neural", "keyword", "extract"}
    cost_per_search = 0.005  # neural 1-25 results (dossier 02 §2.5)
    p50_ms = 1375            # PERPLEXITY_DEEP §4 measured
```

Add these two methods to `ExaProvider` (after the existing `fetch` method):
```python
    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        """Rich search: map SearchQuery -> exa-py search with highlights+summary."""
        kwargs: dict[str, Any] = {
            "num_results": q.max_results,
            "type": "neural" if q.intent == "neural" else self._search_type,
            "contents": {
                "text": {"max_characters": self._text_max_characters},
                "highlights": True,
                "summary": True,
            },
        }
        if self._category:
            kwargs["category"] = self._category
        include = q.include_domains or self._include_domains
        exclude = q.exclude_domains or self._exclude_domains
        if include:
            kwargs["include_domains"] = include
        if exclude:
            kwargs["exclude_domains"] = exclude
        if q.recency_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=q.recency_days)
            kwargs["start_published_date"] = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        response = self._client.search(q.query, **kwargs)
        return [_to_web_result(r) for r in response.results]

    def find_similar(self, url: str, max_results: int = 5) -> list[WebResult]:
        """Find pages similar to a seed URL (citation expansion). dossier 02 §2.6."""
        response = self._client.find_similar_and_contents(
            url,
            num_results=max_results,
            text={"max_characters": self._text_max_characters},
            highlights=True,
        )
        return [_to_web_result(r) for r in response.results]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_exa_provider.py -v`
Expected: PASS (all existing tests + 4 new tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/exa_provider.py tests/test_web/test_exa_provider.py
git commit -m "feat(web): extend ExaProvider with search_ex, find_similar, capability attrs"
```

---

## Task 6: `FirecrawlProvider` — deep-extraction engine + crawl + free DDG search

**Files:**
- Create: `src/bad_research/web/providers/firecrawl_provider.py`
- Test: `tests/test_web/providers/test_firecrawl_provider.py`

`search()` → `POST {base}/v1/search` (with `scrapeOptions` to get markdown inline). `fetch()` → `POST {base}/v1/scrape` (`onlyMainContent=true`, `formats=["markdown","links"]` — runs the 19-step transformer server-side). `capabilities` includes `extract` and `crawl`. Base overridable for self-host (`FIRECRAWL_BASE`). Cites dossier 02 §3.1, §3.6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/providers/test_firecrawl_provider.py`:
```python
"""FirecrawlProvider — mocks api.firecrawl.dev v1 endpoints via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from bad_research.web.base import ProviderError, SearchQuery, WebResult, WebSearchProvider
from bad_research.web.providers.firecrawl_provider import FirecrawlProvider

SEARCH_URL = "https://api.firecrawl.dev/v1/search"
SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"


def _search_resp() -> dict:
    return {
        "success": True,
        "data": [
            {
                "url": "https://a.test/p",
                "title": "Page A",
                "description": "Desc A",
                "markdown": "# Page A\n\nFull markdown body of A.",
                "links": [{"href": "https://a.test/next", "text": "next"}],
                "position": 1,
            },
            {
                "url": "https://b.test/p",
                "title": "Page B",
                "description": "Desc B",
                "position": 2,
            },
        ],
    }


def test_provider_attrs() -> None:
    prov = FirecrawlProvider(api_key="fc-test")
    assert prov.name == "firecrawl"
    assert prov.capabilities == {"keyword", "extract", "crawl"}
    assert prov.p50_ms == 2000
    assert isinstance(prov, WebSearchProvider)


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
        FirecrawlProvider()


@respx.mock
def test_search_ex_builds_payload() -> None:
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json=_search_resp()))
    prov = FirecrawlProvider(api_key="fc-test")
    results = prov.search_ex(SearchQuery(query="firecrawl test", max_results=8))

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer fc-test"
    body = json.loads(sent.content)
    assert body["query"] == "firecrawl test"
    assert body["limit"] == 8
    assert body["scrapeOptions"]["formats"] == ["markdown"]
    assert body["scrapeOptions"]["onlyMainContent"] is True

    assert len(results) == 2
    assert all(isinstance(r, WebResult) for r in results)
    # markdown wins; falls back to description when absent.
    assert results[0].content.startswith("# Page A")
    assert results[0].links == [{"href": "https://a.test/next", "text": "next"}]
    assert results[0].metadata["position"] == 1
    assert results[1].content == "Desc B"   # no markdown -> description


@respx.mock
def test_fetch_uses_scrape_endpoint() -> None:
    route = respx.post(SCRAPE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "url": "https://a.test/page",
                    "metadata": {"title": "Page", "favicon": "https://a.test/fav.ico"},
                    "markdown": "Scraped markdown content.",
                    "links": [{"href": "https://a.test/x"}],
                },
            },
        )
    )
    prov = FirecrawlProvider(api_key="fc-test")
    result = prov.fetch("https://a.test/page")

    body = json.loads(route.calls.last.request.content)
    assert body["url"] == "https://a.test/page"
    assert body["onlyMainContent"] is True
    assert body["formats"] == ["markdown", "links"]
    assert isinstance(result, WebResult)
    assert result.content == "Scraped markdown content."
    assert result.title == "Page"
    assert result.links == [{"href": "https://a.test/x"}]


@respx.mock
def test_base_url_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRECRAWL_BASE", "http://localhost:3002")
    route = respx.post("http://localhost:3002/v1/search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    prov = FirecrawlProvider(api_key="fc-test")
    prov.search_ex(SearchQuery(query="x"))
    assert route.called


@respx.mock
def test_429_raises_rate_limited() -> None:
    from bad_research.web.base import RateLimited

    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(429, json={"success": False, "error": "Rate limit exceeded"})
    )
    prov = FirecrawlProvider(api_key="fc-test")
    with pytest.raises(RateLimited):
        prov.search_ex(SearchQuery(query="x"))


@respx.mock
def test_5xx_raises_provider_error() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(500, text="boom"))
    prov = FirecrawlProvider(api_key="fc-test")
    with pytest.raises(ProviderError):
        prov.search_ex(SearchQuery(query="x"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_firecrawl_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.web.providers.firecrawl_provider'`

- [ ] **Step 3: Write minimal implementation**

Create `src/bad_research/web/providers/firecrawl_provider.py`:
```python
"""Firecrawl provider — deep-extraction engine (the 19-step transformer) + crawl.

search() -> POST /v1/search (scrapeOptions pulls markdown inline). fetch() ->
POST /v1/scrape (onlyMainContent, markdown+links — runs the 19-step transformer
+ injection-defended LLM-clean server-side). Base URL is overridable for the
self-hosted Firecrawl + SearXNG path. (dossier 02 §3.1, §3.3, §3.6.)

Configuration:
    export FIRECRAWL_API_KEY="fc-..."
    export FIRECRAWL_BASE="https://api.firecrawl.dev"   # default; override for self-host
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import ProviderError, RateLimited, SearchQuery, WebResult

_DEFAULT_BASE = "https://api.firecrawl.dev"
_TIMEOUT_S = 60


class FirecrawlProvider:
    name = "firecrawl"
    capabilities = {"keyword", "extract", "crawl"}
    cost_per_search = 0.01  # varies; conservative estimate (dossier 02 §3.5)
    p50_ms = 2000           # search+scrape is the slowest path (INFERRED)

    def __init__(self, api_key: str | None = None, base: str | None = None):
        key = api_key or os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY is not set. Get a key at https://firecrawl.dev "
                "and export it (or run self-hosted and set FIRECRAWL_BASE)."
            )
        self._key = key
        self._base = (base or os.environ.get("FIRECRAWL_BASE", _DEFAULT_BASE)).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimited("Firecrawl rate limited (HTTP 429)")
        if resp.status_code >= 400:
            raise ProviderError(f"Firecrawl error HTTP {resp.status_code}: {resp.text[:200]}")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "limit": q.max_results,
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        }
        try:
            resp = httpx.post(
                f"{self._base}/v1/search", json=body, headers=self._headers(), timeout=_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Firecrawl search failed: {exc}") from exc
        self._raise_for_status(resp)
        return [_to_search_result(row) for row in resp.json().get("data", [])]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        body = {"url": url, "onlyMainContent": True, "formats": ["markdown", "links"]}
        try:
            resp = httpx.post(
                f"{self._base}/v1/scrape", json=body, headers=self._headers(), timeout=_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Firecrawl scrape failed: {exc}") from exc
        self._raise_for_status(resp)
        data = resp.json().get("data", {})
        meta = data.get("metadata", {})
        result_metadata: dict[str, Any] = {}
        if meta.get("favicon"):
            result_metadata["favicon"] = meta["favicon"]
        return WebResult(
            url=data.get("url", url),
            title=meta.get("title", ""),
            content=data.get("markdown", ""),
            fetched_at=datetime.now(UTC),
            links=data.get("links", []),
            metadata=result_metadata,
        )


def _to_search_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("position") is not None:
        metadata["position"] = row["position"]
    if row.get("description"):
        metadata["description"] = row["description"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("markdown") or row.get("description", ""),
        fetched_at=datetime.now(UTC),
        links=row.get("links", []),
        metadata=metadata,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_firecrawl_provider.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/firecrawl_provider.py tests/test_web/providers/test_firecrawl_provider.py
git commit -m "feat(web): FirecrawlProvider — /v1/search + /v1/scrape 19-step extraction"
```

---

## Task 7: Cascade primitives — `_canonical_url`, `_dedup_union`, `_rrf_fuse`

**Files:**
- Create: `src/bad_research/web/providers/cascade.py` (primitives only; `CascadeProvider` added in Task 8)
- Test: `tests/test_web/providers/test_cascade.py` (primitives section)

Pure functions, no HTTP. `_canonical_url` collapses scheme-case, `www.`, fragment, trailing slash, and `utm_*`/`fbclid` tracking params. `_dedup_union` merges multiple provider result lists by canonical URL, keeping the first occurrence and recording which providers found each URL (in `metadata["found_by"]`). `_rrf_fuse` implements Reciprocal Rank Fusion with `k=60` (frozen constant; EXA §6.2 / INTERFACES.md). These are the dedup + fusion building blocks Stage-1 and Stage-2 use.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/providers/test_cascade.py`:
```python
"""Cascade primitives + routing logic — no HTTP, stub providers + stub reranker."""

from __future__ import annotations

from bad_research.web.base import WebResult
from bad_research.web.providers.cascade import (
    RRF_K,
    _canonical_url,
    _dedup_union,
    _rrf_fuse,
)


def _r(url: str, score: float | None = None) -> WebResult:
    meta = {} if score is None else {"score": score}
    return WebResult(url=url, title=url, content="x" * 500, metadata=meta)


def test_canonical_url_collapses_noise() -> None:
    assert _canonical_url("https://www.Example.com/Page/") == _canonical_url(
        "https://example.com/Page"
    )
    assert _canonical_url("http://example.com/p#section") == _canonical_url(
        "http://example.com/p"
    )
    # tracking params stripped; path case preserved.
    assert _canonical_url("https://x.test/a?utm_source=tw&id=5") == "https://x.test/a?id=5"
    assert _canonical_url("https://x.test/a?fbclid=abc") == "https://x.test/a"


def test_canonical_url_preserves_meaningful_query() -> None:
    assert _canonical_url("https://x.test/s?q=rust&page=2") == "https://x.test/s?page=2&q=rust"


def test_dedup_union_merges_by_canonical_url() -> None:
    list_a = [_r("https://www.a.test/x/"), _r("https://b.test/y")]
    list_b = [_r("https://a.test/x"), _r("https://c.test/z")]
    merged = _dedup_union({"sonar": list_a, "tavily": list_b})

    urls = sorted(r.url for r in merged)
    # a.test/x appears once (canonical-collapsed across www + trailing slash).
    assert len(merged) == 3
    assert urls == ["https://a.test/x", "https://b.test/y", "https://c.test/z"]
    a_row = next(r for r in merged if "a.test" in r.url)
    assert set(a_row.metadata["found_by"]) == {"sonar", "tavily"}


def test_rrf_fuse_k_is_60() -> None:
    assert RRF_K == 60


def test_rrf_fuse_ranks_consensus_higher() -> None:
    # X is rank-1 in both lists -> highest RRF; Z only in one list -> lowest.
    list_a = [_r("https://x.test"), _r("https://y.test"), _r("https://z.test")]
    list_b = [_r("https://x.test"), _r("https://y.test")]
    fused = _rrf_fuse([list_a, list_b])

    urls = [r.url for r in fused]
    assert urls[0] == "https://x.test"   # rank-1 in both
    assert urls[-1] == "https://z.test"  # only one list, rank-3
    # rrf_score recorded in metadata, descending.
    scores = [r.metadata["rrf_score"] for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_fuse_formula() -> None:
    # Single list, X at rank-1: rrf = 1/(60+1).
    fused = _rrf_fuse([[_r("https://x.test")]])
    assert abs(fused[0].metadata["rrf_score"] - (1.0 / 61.0)) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_cascade.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.web.providers.cascade'`

- [ ] **Step 3: Write minimal implementation**

Create `src/bad_research/web/providers/cascade.py`:
```python
"""Web-search cascade: intent route -> fast keyword union -> conditional neural
rerank -> deep extract, with zero-key degradation. (SPEC §5, dossier 02 §6.3.)

This module owns ONLY routing/dedup/fusion. It composes provider instances passed
to CascadeProvider's constructor; it never talks to an upstream API directly.
"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bad_research.web.base import WebResult

# Frozen constants (INTERFACES.md "Frozen constants").
RRF_K = 60                       # Reciprocal Rank Fusion k (EXA §6.2)
RELEVANCE_BAR = 0.70             # relevance drop threshold (Perplexity)
THIN_PASS_FRACTION = 0.30        # <30% pass -> Stage-2 fires (Perplexity failsafe)
MAX_RERETRIEVE_ROUNDS = 2        # re-retrieve max rounds

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = frozenset({"fbclid", "gclid", "mc_eid", "mc_cid", "ref"})


def _canonical_url(url: str) -> str:
    """Collapse cosmetic URL variants so dedup catches the same page.

    Lowercases scheme+host, strips a leading 'www.', drops the fragment, removes
    a trailing slash on non-root paths, strips utm_*/fbclid-style tracking params,
    and sorts the remaining query so order doesn't matter.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _TRACKING_PARAM_EXACT
        and not any(k.startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(kept))
    return urlunsplit((scheme, host, path, query, ""))


def _dedup_union(by_provider: dict[str, list[WebResult]]) -> list[WebResult]:
    """Merge per-provider result lists by canonical URL.

    Keeps the first-seen WebResult for each canonical URL and records every
    provider that returned it in metadata['found_by'].
    """
    seen: dict[str, WebResult] = {}
    found_by: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    for provider_name, results in by_provider.items():
        for r in results:
            key = _canonical_url(r.url)
            if key not in seen:
                seen[key] = r
                order.append(key)
            found_by[key].append(provider_name)
    out: list[WebResult] = []
    for key in order:
        r = seen[key]
        r.metadata["found_by"] = found_by[key]
        out.append(r)
    return out


def _rrf_fuse(ranked_lists: list[list[WebResult]]) -> list[WebResult]:
    """Reciprocal Rank Fusion over multiple ranked lists. k = RRF_K (60).

    rrf(doc) = sum over lists L of 1 / (RRF_K + rank_L(doc)), rank is 1-based.
    Returns one WebResult per canonical URL, sorted by rrf_score descending, with
    the score recorded in metadata['rrf_score'].
    """
    scores: dict[str, float] = defaultdict(float)
    repr_result: dict[str, WebResult] = {}
    for ranked in ranked_lists:
        for rank, r in enumerate(ranked, start=1):
            key = _canonical_url(r.url)
            scores[key] += 1.0 / (RRF_K + rank)
            repr_result.setdefault(key, r)
    fused = sorted(repr_result.values(), key=lambda r: scores[_canonical_url(r.url)], reverse=True)
    for r in fused:
        r.metadata["rrf_score"] = scores[_canonical_url(r.url)]
    return fused
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_cascade.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/cascade.py tests/test_web/providers/test_cascade.py
git commit -m "feat(web): cascade primitives — canonical-URL dedup + RRF(k=60) fusion"
```

---

## Task 8: `CascadeProvider` + `cascade_search` — the four-stage router

**Files:**
- Modify: `src/bad_research/web/providers/cascade.py` (add `_route_intent`, `_passes_bar`, `CascadeProvider`, `cascade_search`)
- Test: `tests/test_web/providers/test_cascade.py` (add routing tests)

`CascadeProvider` composes injected providers (keyword providers list, an optional neural `ExaProvider`, an optional extractor for Stage-3, an optional `Reranker`). `cascade_search()`:
- **Stage-0** — `_route_intent` picks the lane from `SearchQuery.intent` + keyword heuristics ("latest"/year tokens → recency; "find sites like"/URL → neural-similar).
- **Stage-1** — fires all keyword providers in parallel (`ThreadPoolExecutor`), unions+dedups. A provider that raises `QuotaExceeded`/`RateLimited`/`ProviderError` is skipped (ladder degradation), not fatal.
- **Stage-2** — fires **only when <30% of Stage-1 results pass the 0.70 bar** (or `intent="neural"`): runs the neural provider, RRF-fuses Stage-1+Stage-2, then optional cross-encoder rerank via the injected `Reranker`.
- **Stage-3** — for the top-N content-less/junk results, calls the extractor's `fetch()`, dropping `looks_like_junk()`/`looks_like_login_wall()` hits.
- Zero-key path: if only SearXNG is present and no neural/extractor, the cascade still returns Stage-1 results.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web/providers/test_cascade.py`:
```python
import pytest

from bad_research.web.base import ProviderError, QuotaExceeded, SearchQuery
from bad_research.web.providers.cascade import CascadeProvider, cascade_search


class _StubProvider:
    """A keyword/neural provider stub that returns canned results or raises."""

    def __init__(self, name, results=None, raises=None, capabilities=None):
        self.name = name
        self.capabilities = capabilities or {"keyword"}
        self.cost_per_search = 0.0
        self.p50_ms = 100
        self._results = results or []
        self._raises = raises
        self.calls = 0

    def search_ex(self, q: SearchQuery):
        self.calls += 1
        if self._raises:
            raise self._raises
        return list(self._results)

    def search(self, query, max_results=5):
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url):
        return _r(url)


class _StubExtractor:
    def __init__(self):
        self.name = "extractor"
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return WebResult(url=url, title="fetched", content="Full extracted body. " * 40)


class _StubReranker:
    """Returns docs in reverse order with descending scores, to prove it's used."""

    def __init__(self):
        self.called = False

    def rerank(self, query, docs):
        self.called = True
        n = len(docs)
        return [(i, 1.0 - i / max(n, 1)) for i in reversed(range(n))]


def test_stage1_unions_parallel_providers() -> None:
    p1 = _StubProvider("sonar", [_r("https://a.test", 0.9)])
    p2 = _StubProvider("searxng", [_r("https://b.test", 0.85)])
    cascade = CascadeProvider(keyword_providers=[p1, p2])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert {r.url for r in results} == {"https://a.test", "https://b.test"}
    assert p1.calls == 1 and p2.calls == 1


def test_stage1_skips_failed_provider() -> None:
    good = _StubProvider("searxng", [_r("https://ok.test", 0.9)])
    dead = _StubProvider("tavily", raises=QuotaExceeded("quota"))
    cascade = CascadeProvider(keyword_providers=[good, dead])
    results = cascade.search_ex(SearchQuery(query="x"))
    # Dead provider is skipped, good provider's result survives.
    assert [r.url for r in results] == ["https://ok.test"]


def test_stage2_fires_when_stage1_thin() -> None:
    """All Stage-1 results below the 0.70 bar -> <30% pass -> neural fires."""
    thin = _StubProvider("searxng", [_r("https://lo.test", 0.4), _r("https://lo2.test", 0.5)])
    neural = _StubProvider(
        "exa", [_r("https://neural.test", 0.95)], capabilities={"neural"}
    )
    rer = _StubReranker()
    cascade = CascadeProvider(keyword_providers=[thin], neural_provider=neural, reranker=rer)
    results = cascade.search_ex(SearchQuery(query="concept query"))
    assert neural.calls == 1            # Stage-2 fired
    assert rer.called                   # reranker ran on merged set
    assert any("neural.test" in r.url for r in results)


def test_stage2_does_not_fire_when_stage1_rich() -> None:
    """Enough Stage-1 results above 0.70 -> neural does NOT fire."""
    rich = _StubProvider(
        "sonar",
        [_r("https://a.test", 0.95), _r("https://b.test", 0.92), _r("https://c.test", 0.88)],
    )
    neural = _StubProvider("exa", [_r("https://n.test", 0.99)], capabilities={"neural"})
    cascade = CascadeProvider(keyword_providers=[rich], neural_provider=neural)
    cascade.search_ex(SearchQuery(query="x"))
    assert neural.calls == 0            # Stage-2 skipped — Stage-1 was rich


def test_neural_intent_forces_stage2() -> None:
    rich = _StubProvider("sonar", [_r("https://a.test", 0.95), _r("https://b.test", 0.95)])
    neural = _StubProvider("exa", [_r("https://n.test", 0.99)], capabilities={"neural"})
    cascade = CascadeProvider(keyword_providers=[rich], neural_provider=neural)
    cascade.search_ex(SearchQuery(query="x", intent="neural"))
    assert neural.calls == 1            # intent=neural always fires Stage-2


def test_stage3_extracts_content_less_top_results() -> None:
    """SERP rows with thin content get deep-extracted; junk hits get dropped."""
    serp = _StubProvider(
        "sonar",
        [
            WebResult(url="https://thin.test", title="t", content="too short"),
            WebResult(url="https://good.test", title="g", content="x" * 600),
        ],
    )
    extractor = _StubExtractor()
    cascade = CascadeProvider(
        keyword_providers=[serp], extractor=extractor, extract_top_n=2
    )
    results = cascade.search_ex(SearchQuery(query="x"))
    # thin.test had <300 chars (junk) -> extracted; good.test already substantial.
    assert "https://thin.test" in extractor.fetched
    thin_row = next(r for r in results if "thin.test" in r.url)
    assert thin_row.content.startswith("Full extracted body")


def test_zero_key_path_searxng_only() -> None:
    """SearXNG-only cascade (no neural, no extractor) still returns Stage-1 results."""
    searxng = _StubProvider("searxng", [_r("https://z.test", 0.8)], capabilities={"keyword"})
    cascade = CascadeProvider(keyword_providers=[searxng])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert [r.url for r in results] == ["https://z.test"]


def test_cascade_search_module_fn() -> None:
    """The cascade_search() free function builds + runs a CascadeProvider."""
    p = _StubProvider("searxng", [_r("https://a.test", 0.9)])
    results = cascade_search(SearchQuery(query="x"), keyword_providers=[p])
    assert [r.url for r in results] == ["https://a.test"]


def test_all_providers_dead_returns_empty() -> None:
    dead = _StubProvider("tavily", raises=ProviderError("boom"))
    cascade = CascadeProvider(keyword_providers=[dead])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert results == []


def test_cascade_is_web_search_provider() -> None:
    from bad_research.web.base import WebSearchProvider

    cascade = CascadeProvider(keyword_providers=[_StubProvider("searxng")])
    assert isinstance(cascade, WebSearchProvider)
    assert cascade.name == "cascade"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_cascade.py -v`
Expected: FAIL — `ImportError: cannot import name 'CascadeProvider' from 'bad_research.web.providers.cascade'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/bad_research/web/providers/cascade.py`:
```python
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from bad_research.web.base import ProviderError, SearchQuery


class _RerankerLike(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...


_MIN_CONTENT_CHARS = 300  # below this a SERP row is content-less -> Stage-3 extract


def _route_intent(q: SearchQuery) -> SearchQuery:
    """Stage 0 — cheap local intent route. Fills recency from query tokens and
    upgrades intent to 'neural' for similarity-style queries.
    """
    lowered = q.query.lower()
    recency = q.recency_days
    if recency is None and any(
        tok in lowered for tok in ("latest", "today", "this week", "right now", "2026")
    ):
        recency = 7
    intent = q.intent
    if intent == "keyword" and (
        lowered.startswith("find sites like")
        or lowered.startswith("similar to")
        or "http://" in lowered
        or "https://" in lowered
    ):
        intent = "neural"
    return SearchQuery(
        query=q.query,
        intent=intent,
        recency_days=recency,
        include_domains=q.include_domains,
        exclude_domains=q.exclude_domains,
        max_results=q.max_results,
    )


def _passes_bar(r: WebResult, bar: float = RELEVANCE_BAR) -> bool:
    """A result clears the bar if its score >= bar. Score-less rows count as
    below the bar (forces Stage-2 when SERP providers return no score)."""
    score = r.metadata.get("score")
    return score is not None and score >= bar


class CascadeProvider:
    """Composes the provider set into the four-stage cascade. name = 'cascade'."""

    name = "cascade"
    capabilities = {"keyword", "neural", "extract"}
    cost_per_search = 0.0  # computed dynamically; placeholder for the Protocol attr
    p50_ms = 600

    def __init__(
        self,
        keyword_providers: list,
        neural_provider=None,
        extractor=None,
        reranker: _RerankerLike | None = None,
        extract_top_n: int = 0,
    ):
        self._keyword = list(keyword_providers)
        self._neural = neural_provider
        self._extractor = extractor
        self._reranker = reranker
        self._extract_top_n = extract_top_n

    # -- Stage 1 ---------------------------------------------------------------
    def _stage1(self, q: SearchQuery) -> list[WebResult]:
        by_provider: dict[str, list[WebResult]] = {}

        def _run(provider) -> tuple[str, list[WebResult]]:
            try:
                return provider.name, provider.search_ex(q)
            except ProviderError:
                return provider.name, []   # ladder degradation — skip dead provider

        if not self._keyword:
            return []
        with ThreadPoolExecutor(max_workers=max(len(self._keyword), 1)) as pool:
            for name, results in pool.map(_run, self._keyword):
                by_provider[name] = results
        return _dedup_union(by_provider)

    # -- Stage 2 ---------------------------------------------------------------
    def _should_fire_neural(self, q: SearchQuery, stage1: list[WebResult]) -> bool:
        if self._neural is None:
            return False
        if q.intent == "neural":
            return True
        if not stage1:
            return True
        passing = sum(1 for r in stage1 if _passes_bar(r))
        return (passing / len(stage1)) < THIN_PASS_FRACTION

    def _stage2(self, q: SearchQuery, stage1: list[WebResult]) -> list[WebResult]:
        try:
            neural_results = self._neural.search_ex(q)
        except ProviderError:
            neural_results = []
        fused = _rrf_fuse([stage1, neural_results])
        if self._reranker is not None and fused:
            order = self._reranker.rerank(q.query, [r.content for r in fused])
            fused = [fused[idx] for idx, _score in order]
        return fused

    # -- Stage 3 ---------------------------------------------------------------
    def _stage3(self, results: list[WebResult]) -> list[WebResult]:
        if self._extractor is None or self._extract_top_n <= 0:
            return results
        out: list[WebResult] = []
        extracted = 0
        for r in results:
            needs_extract = (
                extracted < self._extract_top_n and r.looks_like_junk() is not None
            )
            if needs_extract:
                try:
                    fetched = self._extractor.fetch(r.url)
                except ProviderError:
                    out.append(r)
                    continue
                extracted += 1
                if fetched.looks_like_junk() is not None or fetched.looks_like_login_wall(r.url):
                    continue  # drop junk/login-wall after extraction
                fetched.metadata.update(r.metadata)
                out.append(fetched)
            else:
                out.append(r)
        return out

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        routed = _route_intent(q)
        stage1 = self._stage1(routed)
        results = stage1
        if self._should_fire_neural(routed, stage1):
            results = self._stage2(routed, stage1)
        results = self._stage3(results)
        return results[: q.max_results] if q.max_results else results

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        if self._extractor is not None:
            return self._extractor.fetch(url)
        if self._keyword:
            return self._keyword[0].fetch(url)
        raise ProviderError("Cascade has no provider capable of fetch().")


def cascade_search(
    q: SearchQuery,
    *,
    keyword_providers: list,
    neural_provider=None,
    extractor=None,
    reranker: _RerankerLike | None = None,
    extract_top_n: int = 0,
) -> list[WebResult]:
    """Build a CascadeProvider from the given provider set and run one query."""
    return CascadeProvider(
        keyword_providers=keyword_providers,
        neural_provider=neural_provider,
        extractor=extractor,
        reranker=reranker,
        extract_top_n=extract_top_n,
    ).search_ex(q)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/providers/test_cascade.py -v`
Expected: PASS (all primitive tests + 10 routing tests)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/providers/cascade.py tests/test_web/providers/test_cascade.py
git commit -m "feat(web): CascadeProvider — 4-stage route/union/neural-gate/extract"
```

---

## Task 9: Register providers in `get_provider()` + `providers/__init__.py` re-exports

**Files:**
- Modify: `src/bad_research/web/base.py` (extend `get_provider`)
- Modify: `src/bad_research/web/providers/__init__.py` (re-exports)
- Test: `tests/test_web/test_provider_factory.py`

The factory gains `tavily`, `sonar`, `searxng`, `firecrawl`, `cascade`. Each lazy-imports its module. Unknown names still raise `ValueError` listing all available providers. The `cascade` name auto-assembles the provider set from whatever keys are present (zero-key → SearXNG-only).

- [ ] **Step 1: Write the failing test**

Create `tests/test_web/test_provider_factory.py`:
```python
"""get_provider() routes to the new providers; unknown still raises ValueError."""

from __future__ import annotations

import pytest

from bad_research.web.base import get_provider


def test_factory_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    prov = get_provider("tavily")
    assert prov.name == "tavily"


def test_factory_sonar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
    prov = get_provider("sonar")
    assert prov.name == "sonar"


def test_factory_searxng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARXNG_ENDPOINT", raising=False)
    prov = get_provider("searxng")
    assert prov.name == "searxng"


def test_factory_firecrawl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    prov = get_provider("firecrawl")
    assert prov.name == "firecrawl"


def test_factory_cascade_zero_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No premium keys -> cascade assembles a SearXNG-only keyword set."""
    for k in ("TAVILY_API_KEY", "PERPLEXITY_API_KEY", "EXA_API_KEY", "FIRECRAWL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    prov = get_provider("cascade")
    assert prov.name == "cascade"
    assert any(p.name == "searxng" for p in prov._keyword)
    assert prov._neural is None


def test_factory_unknown_raises_with_full_list() -> None:
    with pytest.raises(ValueError) as exc:
        get_provider("not-real")
    msg = str(exc.value)
    for name in ("builtin", "crawl4ai", "exa", "tavily", "sonar", "searxng", "firecrawl", "cascade"):
        assert name in msg


def test_providers_package_reexports() -> None:
    from bad_research.web.providers import (
        CascadeProvider,
        FirecrawlProvider,
        SearxngProvider,
        SonarProvider,
        TavilyProvider,
    )

    assert TavilyProvider.name == "tavily"
    assert SonarProvider.name == "sonar"
    assert SearxngProvider.name == "searxng"
    assert FirecrawlProvider.name == "firecrawl"
    assert CascadeProvider.name == "cascade"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_provider_factory.py -v`
Expected: FAIL — `ValueError: Unknown web provider: 'tavily'` (factory doesn't know the new names yet)

- [ ] **Step 3: Write minimal implementation**

In `src/bad_research/web/base.py`, replace the `if name == "exa":` block and the final `raise ValueError` in `get_provider` with:
```python
    if name == "exa":
        from bad_research.web.exa_provider import ExaProvider

        return ExaProvider()

    if name == "tavily":
        from bad_research.web.providers.tavily_provider import TavilyProvider

        return TavilyProvider()

    if name == "sonar":
        from bad_research.web.providers.sonar_provider import SonarProvider

        return SonarProvider()

    if name == "searxng":
        from bad_research.web.providers.searxng_provider import SearxngProvider

        return SearxngProvider()

    if name == "firecrawl":
        from bad_research.web.providers.firecrawl_provider import FirecrawlProvider

        return FirecrawlProvider()

    if name == "cascade":
        return _build_cascade()

    raise ValueError(
        f"Unknown web provider: {name!r}. Available: builtin, crawl4ai, exa, "
        f"tavily, sonar, searxng, firecrawl, cascade"
    )


def _build_cascade():
    """Assemble a CascadeProvider from whatever provider keys are present.

    Zero-key -> SearXNG-only keyword set, no neural, no extractor (the floor that
    still beats hyperresearch's NotImplementedError search). (SPEC §5 zero-key path.)
    """
    import os

    from bad_research.web.providers.cascade import CascadeProvider
    from bad_research.web.providers.searxng_provider import SearxngProvider

    keyword: list = []
    if os.environ.get("PERPLEXITY_API_KEY"):
        from bad_research.web.providers.sonar_provider import SonarProvider

        keyword.append(SonarProvider())
    if os.environ.get("TAVILY_API_KEY"):
        from bad_research.web.providers.tavily_provider import TavilyProvider

        keyword.append(TavilyProvider())
    keyword.append(SearxngProvider())  # always available — zero-key backbone

    neural = None
    if os.environ.get("EXA_API_KEY"):
        from bad_research.web.exa_provider import ExaProvider

        neural = ExaProvider()

    extractor = None
    if os.environ.get("FIRECRAWL_API_KEY"):
        from bad_research.web.providers.firecrawl_provider import FirecrawlProvider

        extractor = FirecrawlProvider()
    elif neural is not None:
        extractor = neural  # Exa /contents as the extract fallback

    return CascadeProvider(
        keyword_providers=keyword,
        neural_provider=neural,
        extractor=extractor,
        extract_top_n=8 if extractor is not None else 0,
    )
```

In `src/bad_research/web/providers/__init__.py`:
```python
"""Web search providers + the search cascade (Plan 03)."""

from bad_research.web.providers.cascade import CascadeProvider, cascade_search
from bad_research.web.providers.firecrawl_provider import FirecrawlProvider
from bad_research.web.providers.searxng_provider import SearxngProvider
from bad_research.web.providers.sonar_provider import SonarProvider
from bad_research.web.providers.tavily_provider import TavilyProvider

__all__ = [
    "CascadeProvider",
    "FirecrawlProvider",
    "SearxngProvider",
    "SonarProvider",
    "TavilyProvider",
    "cascade_search",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/test_provider_factory.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/web/base.py src/bad_research/web/providers/__init__.py tests/test_web/test_provider_factory.py
git commit -m "feat(web): register tavily/sonar/searxng/firecrawl/cascade in get_provider"
```

---

## Task 10: Packaging — dev dep `respx`, provider extras, full-suite green

**Files:**
- Modify: `pyproject.toml` (in the fork: `ultimate-research/bad-research/pyproject.toml`)
- Test: full `tests/test_web/` suite

Add `respx` to the dev extra (the httpx mock the provider tests need) and declare provider optional-extras so `pip install "bad-research[web]"` pulls the SDKs. Tavily/Sonar/SearXNG/Firecrawl use only `httpx` (already a core dep) so they need no SDK; Exa keeps `exa-py`.

- [ ] **Step 1: Write the failing test (verification gate)**

There is no new code test here; the gate is the whole web suite passing with respx available. First confirm respx is missing:

Run: `cd ultimate-research/bad-research && python -c "import respx" 2>&1`
Expected: FAIL — `ModuleNotFoundError: No module named 'respx'`

- [ ] **Step 2: Add the dependency and extras**

In `ultimate-research/bad-research/pyproject.toml`, under `[project.optional-dependencies]`, update the `dev` list and add a `web` extra:
```toml
[project.optional-dependencies]
mcp = ["mcp>=1.6"]
exa = ["exa-py>=2.0.0"]
web = ["exa-py>=2.0.0"]            # tavily/sonar/searxng/firecrawl need only httpx (core dep)
all = ["bad-research[mcp,exa,web]"]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "mypy>=1.8",
    "respx>=0.21",
]
```

- [ ] **Step 3: Install the dev extra**

Run: `cd ultimate-research/bad-research && pip install -e ".[dev,web]"`
Expected: installs `respx`, `exa-py`, and the package in editable mode. Verify:

Run: `cd ultimate-research/bad-research && python -c "import respx, exa_py; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full web suite**

Run: `cd ultimate-research/bad-research && pytest tests/test_web/ -v`
Expected: PASS — all tests across `test_web_search_query.py`, `test_provider_factory.py`, `test_exa_provider.py`, and `tests/test_web/providers/*` green. No test makes a real network call (every HTTP path is mocked by respx; the Exa path is monkeypatched).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build(web): add respx dev dep + [web] provider extra; full web suite green"
```

---

## Self-Review

**1. Spec coverage (SPEC §5 + dossier 02 §6):**
- Stage 0 intent route → `_route_intent` (Task 8). ✓
- Stage 1 fast keyword parallel union (tavily+sonar+searxng) + dedup → `_stage1` + `_dedup_union` (Tasks 7,8). ✓
- Stage 2 neural rerank fires only when <30% pass the 0.70 bar; Exa + RRF k=60 + reranker → `_should_fire_neural` + `_stage2` + `_rrf_fuse` (Tasks 7,8). ✓
- Stage 3 deep extract (firecrawl/exa contents) gated by junk/login-wall → `_stage3` (Task 8). ✓
- Zero-key degradation (searxng) → `_build_cascade` + `test_factory_cascade_zero_key` + `test_zero_key_path_searxng_only` (Tasks 8,9). ✓
- Each provider's real API params from dossier 02 → Tasks 2–6 with mocked-HTTP payload asserts. ✓
- Register in `get_provider()` → Task 9. ✓
- Reuse `WebResult` verbatim, add `SearchQuery`/`WebSearchProvider` per INTERFACES.md → Task 1. ✓

**2. Placeholder scan:** No TBD/TODO; every code step is complete and runnable. Every test has real assertions. ✓

**3. Type consistency:** `SearchQuery` fields (`query`, `intent`, `recency_days`, `include_domains`, `exclude_domains`, `max_results`) match INTERFACES.md lines 70–76 verbatim. `WebSearchProvider` surface (`name`, `capabilities: set[str]`, `cost_per_search: float`, `p50_ms: int`, `fetch`, `search_ex`) matches INTERFACES.md lines 78–84 verbatim. `Reranker.rerank(query, docs) -> list[tuple[int,float]]` matches line 107. `WebResult` never redefined — imported from `web/base.py` everywhere. RRF `k=60`, relevance bar `0.70`, thin-pass `<30%` are the frozen constants. ✓

**Cross-plan note:** Plan 02 (retrieval) owns the concrete `Reranker` (Cohere `rerank-v3.5` / local `bge-reranker-v2-m3`); the cascade only consumes the Protocol, so Plans 02 and 03 can be implemented in either order. The orchestrator (skill layer, Plan 08) wires the real reranker into `_build_cascade` once Plan 02 lands; until then the factory builds the cascade with `reranker=None` and Stage-2 still RRF-fuses (rerank is the optional refinement step).

---

## Execution Handoff

**Plan complete and saved to `ultimate-research/plans/2026-05-26-bad-research-03-web-search.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task (10 tasks), review between tasks, fast iteration. REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**2. Inline Execution** — execute tasks in this session using superpowers:executing-plans, batch execution with checkpoints.

**Which approach?**
