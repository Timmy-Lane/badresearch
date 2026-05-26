# Bad Research — Plan 04: Browse/Extract Ladder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `browse/` subsystem — a Tier 0→3 escalation ladder (`fetch_tiered`) that fetches a URL with HTTP first, escalates to JS-render, typed schema-extraction, and finally agentic browse only when a cheaper tier's result trips a quality gate — hooked into `core/fetcher` so the pipeline pays for the expensive tiers per-source only when needed.

**Architecture:** `fetch_tiered(url, *, tier_max, instruction=None, schema=None)` walks tiers in order: **Tier 0** = `builtin` httpx (existing), **Tier 1** = crawl4ai JS render (existing), **Tier 2** = `ExtractProvider` typed extraction (LLM-extract default zero-dep via the Plan-01 LLM seam, AgentQL, Stagehand), **Tier 3** = `BrowseProvider` agentic browse (Browser-Use self-host default, Browserbase opt-in). Escalation is driven by the existing `WebResult.looks_like_junk()` / `looks_like_login_wall()` signals (no new heuristics — reuse hyperresearch's verbatim). A `schema` arg forces Tier 2; an `instruction` arg (or junk/login-wall) routes Tier 3. A `replay_key` action cache skips re-browsing a site already driven. Every optional dependency (crawl4ai lib, AgentQL key, Browserbase key, browser-use lib) degrades gracefully: missing dep/key → the ladder stops at the highest *available* tier and returns the best result it has, never raising.

**Tech Stack:** Python 3.11+, pytest, `unittest.mock` (mock ALL external browsers/APIs — no live network in tests), `httpx` (Tier 0, already a dep), `crawl4ai` (Tier 1, optional extra), `browser-use` (Tier 3, optional extra), Browserbase/Stagehand + AgentQL via HTTP (optional, key-gated). Reuses the Plan-01 `LLMProvider` seam for Tier-2 LLM extraction. Forks/extends `hyperresearch`'s `web/base.py` + `core/fetcher.py`.

---

## Background: what already exists (read before starting)

These are FACTS about the fork base. Do not re-derive them; cite them.

- **`src/bad_research/web/base.py`** (forked from hyperresearch, unchanged shape) defines `WebResult` (dataclass: `url, title, content, fetched_at, raw_html, metadata, media, links, screenshot, raw_bytes, raw_content_type`) with two **escalation-gate methods**:
  - `WebResult.looks_like_junk() -> str | None` — returns a reason string for Cloudflare/captcha/error/empty/binary pages, else `None`. Empty trigger: `len(content.strip()) < 300` → `"Empty or near-empty content"`. Bot trigger → `"Bot detection page: <title>"`.
  - `WebResult.looks_like_login_wall(original_url) -> bool` — true if title/content/URL looks like a login redirect.
  - `WebProvider` Protocol: `name: str`, `fetch(url) -> WebResult`, `search(query, max_results) -> list[WebResult]`.
  - `get_provider(name, profile, magic, headless) -> WebProvider` factory: `"builtin"` (default, httpx+bs4), `"crawl4ai"` (lazy import, raises `ImportError` with `bad-research[crawl4ai]` hint if lib missing), `"exa"`.
- **`src/bad_research/web/builtin.py`** — `BuiltinProvider.fetch()` = httpx GET + bs4 text extract. **This is Tier 0.** Zero deps beyond stdlib (urllib fallback).
- **`src/bad_research/web/crawl4ai_provider.py`** — `Crawl4AIProvider.fetch()` = headless Chromium → `fit_markdown`. **This is Tier 1.** Optional `crawl4ai` lib; also exposes `fetch_many(urls)`.
- **`src/bad_research/core/fetcher.py`** — `fetch_and_save(vault, url, ...)` is the **one call-site**: it calls `prov.fetch(url)`, then aborts on `looks_like_login_wall` / `looks_like_junk`, then writes the note. We hook the ladder in here.
- **Plan 01 (`llm/base.py`) provides the LLM seam** used by `LLMExtractProvider`:
  - `LLMMessage(role, content)` dataclass; `role ∈ {"system","user","assistant","tool"}`.
  - `LLMResponse(text, tool_calls, usage, model)` dataclass.
  - `LLMProvider` Protocol: `complete(messages: list[LLMMessage], *, tier: ModelTier, tools=None, cache=False, max_tokens=4096, temperature=0.1) -> LLMResponse`. `ModelTier = Literal["triage","work","heavy"]`.
  - Plan 04 NEVER instantiates a concrete `LLMProvider`; it accepts one by dependency injection (so tests pass a mock). If `None` is passed and no default is wired, the LLM-extract tier degrades gracefully (returns the Tier-1 result unchanged).

**Verbatim prompts to reuse (do NOT invent new ones):**
- Browser-Use structured-extract system prompt (`teardowns/BROWSER_USE.md:327-336`) — baked into `LLMExtractProvider`.
- Stagehand `EXTRACT_SYSTEM_PROMPT` (`products/BROWSERBASE_PRODUCT_CODE.md:4313-4327`) — referenced by `StagehandExtractProvider`.
- AgentQL `DATA_EXTRACTION_SYSTEM_PROMPT` (`products/AGENTQL_PRODUCT_CODE.md:2080-2107`) — server-side, so `AgentQLExtractProvider` only sends the query; the prompt lives on the AgentQL server.

**Frozen constants this plan uses (from INTERFACES.md / dossier 03):**

| Constant | Value | Source |
|---|---|---|
| Tier 0→1 empty-content trigger | `len(content.strip()) < 300` | `web/base.py` `looks_like_junk` |
| agentic-fast / browse default max_steps (BrowseProvider) | `12` | INTERFACES.md `browse()` default |
| Stagehand agent default maxSteps | `20` | dossier 03 §1.4 |
| Browser-Use typical steps/task | `30–100` | dossier 03 §3.2 |
| LLM-extract chunk size | `100_000` chars | dossier 03 §3.4 (`max_chunk_chars`) |
| AgentQL grounding retries | `1` (`MAX_RETRIES`) | dossier 03 §2.4 |
| ActCache replay key | `SHA-256({instruction, url, variable NAMES})` | dossier 03 §1.5 (never values) |
| EXTRACT_TEMPERATURE | `0.1` | `products/BROWSERBASE_PRODUCT_CODE.md:4270` |
| LLM extract tier | `triage` (cheap `page_extraction_llm`) | dossier 03 §3.4 / §8.8 |
| AXTree token cap | `70_000` tokens / `280_000` chars | dossier 03 §1.3 |

---

## New shared types added (registered here for cross-plan consistency)

This plan adds **two new Protocols** to the frozen interface surface, both already declared in `INTERFACES.md` lines 86-94 (`browse/base.py`). It introduces **no new dataclass** — `BrowseProvider.browse()` and the ladder both return the existing `WebResult`, and `ExtractProvider.extract()` returns a plain `dict`. The only genuinely new public symbols are:

- `BrowseProvider` Protocol (`browse/base.py`) — verbatim from INTERFACES.md.
- `ExtractProvider` Protocol (`browse/base.py`) — verbatim from INTERFACES.md.
- `fetch_tiered(url, *, tier_max, instruction=None, schema=None) -> WebResult` (`browse/ladder.py`) — verbatim from INTERFACES.md.
- `get_browse_provider(name=None) -> BrowseProvider | None` and `get_extract_provider(name=None) -> ExtractProvider | None` factories (`browse/base.py`) — return `None` when the requested impl's dep/key is unavailable (graceful degradation contract). These mirror `web.base.get_provider` but never raise on a missing optional backend.

No edit to `INTERFACES.md` is required — these names match it exactly. The factories returning `None` are an implementation detail consistent with the "all optional deps degrade gracefully" rule in the brief; if a future plan needs them, they are documented here.

---

## File Structure

```
src/bad_research/browse/
├── __init__.py              # re-exports: fetch_tiered, BrowseProvider, ExtractProvider,
│                            #   get_browse_provider, get_extract_provider, replay_key_for
├── base.py                  # BrowseProvider + ExtractProvider Protocols; factories
├── ladder.py                # fetch_tiered() — the Tier 0→3 orchestration + escalation policy
├── extract_llm.py           # LLMExtractProvider (default, zero-dep, uses Plan-01 LLM seam)
├── extract_agentql.py       # AgentQLExtractProvider (HTTP to AgentQL query-data; key-gated)
├── extract_stagehand.py     # StagehandExtractProvider (needs a live Stagehand session)
├── browse_browseruse.py     # BrowserUseProvider (self-host default; optional browser-use lib)
├── browse_browserbase.py    # BrowserbaseProvider (opt-in anti-bot/login; key-gated)
└── cache.py                 # ActCache: replay_key_for() + file-backed get/put

src/bad_research/core/
└── fetcher.py               # MODIFY: fetch_and_save() gains tier/instruction/schema params;
                             #   delegates to browse.fetch_tiered

tests/test_browse/
├── __init__.py
├── conftest.py              # shared fixtures: junk/login/good WebResult builders, fake LLM
├── test_base.py             # Protocol conformance + factory graceful-None behavior
├── test_ladder.py           # escalation decisions (the core of this plan)
├── test_extract_llm.py      # typed-extract returns schema-shaped dict (mock LLM)
├── test_extract_agentql.py  # AgentQL HTTP extract (mock httpx)
├── test_browse_browseruse.py# agentic browse → WebResult (mock browser-use Agent)
├── test_browse_browserbase.py# Browserbase Stagehand agent (mock the session)
├── test_cache.py            # replay_key_for stability + cache hit skips re-browse
└── test_fetcher_hook.py     # core/fetcher delegates to fetch_tiered with right args
```

Build order (each task is self-contained and committable): **base → cache → extract_llm → extract_agentql → extract_stagehand → browse_browseruse → browse_browserbase → ladder → fetcher hook → graceful-degradation sweep**. The ladder is built late because it composes everything below it.

---

## Task 1: Protocols + factories (`browse/base.py`)

Defines the two Protocols verbatim from INTERFACES.md and the `get_*_provider` factories that return `None` (never raise) when an optional backend is unavailable. No backend logic yet — just the contract surface and a stub registry.

**Files:**
- Create: `src/bad_research/browse/__init__.py`
- Create: `src/bad_research/browse/base.py`
- Test: `tests/test_browse/__init__.py`, `tests/test_browse/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_base.py
"""Contract tests for the BrowseProvider / ExtractProvider Protocols and factories."""

from __future__ import annotations

from typing import Any

import pytest

from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)
from bad_research.web.base import WebResult


class _DummyBrowse:
    name = "dummy"

    def browse(self, url, instruction, *, max_steps=12, variables=None, replay_key=None):
        return WebResult(url=url, title="t", content="browsed " + instruction)


class _DummyExtract:
    name = "dummy"

    def extract(self, source, schema, instruction=""):
        return {"ok": True}


def test_browse_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyBrowse(), BrowseProvider)


def test_extract_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyExtract(), ExtractProvider)


def test_browse_signature_accepts_keyword_only_args() -> None:
    p = _DummyBrowse()
    r = p.browse("https://x.test", "load all reviews", max_steps=5,
                 variables={"u": "user"}, replay_key="k")
    assert isinstance(r, WebResult)
    assert r.content == "browsed load all reviews"


def test_get_extract_provider_default_is_llm() -> None:
    """Default extract provider is the zero-dep LLM extractor (always available)."""
    p = get_extract_provider()  # no name → default
    assert p is not None
    assert p.name == "llm"


def test_get_extract_provider_unknown_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown / unavailable extract backend → None (graceful), never raises."""
    assert get_extract_provider("does-not-exist") is None


def test_get_browse_provider_unknown_returns_none() -> None:
    assert get_browse_provider("does-not-exist") is None


def test_get_browse_provider_browseruse_none_when_lib_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser-use not installed → factory returns None, never raises ImportError."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "browser_use" or name.startswith("browser_use."):
            raise ImportError("No module named 'browser_use'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert get_browse_provider("browser-use") is None


def test_get_browse_provider_browserbase_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    assert get_browse_provider("browserbase") is None


def test_get_extract_provider_agentql_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
    assert get_extract_provider("agentql") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/__init__.py
"""Tier 0→3 browse/extract escalation ladder."""

from __future__ import annotations

from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)

__all__ = [
    "BrowseProvider",
    "ExtractProvider",
    "get_browse_provider",
    "get_extract_provider",
]
```

```python
# src/bad_research/browse/base.py
"""BrowseProvider / ExtractProvider Protocols + availability-gated factories.

Both Protocols match ultimate-research/INTERFACES.md verbatim. Factories return None
(never raise) when an optional backend's dependency or API key is unavailable — the
ladder treats None as "this tier is not available" and stops at the highest tier it can.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from bad_research.web.base import WebResult


@runtime_checkable
class BrowseProvider(Protocol):
    """Tier-3: LLM-driven, multi-step browse. Returns a WebResult like any provider,
    but reaches it through an agent loop (login, paginate, click, dismiss modals)."""

    name: str

    def browse(
        self,
        url: str,
        instruction: str,
        *,
        max_steps: int = 12,
        variables: dict | None = None,
        replay_key: str | None = None,
    ) -> WebResult: ...


@runtime_checkable
class ExtractProvider(Protocol):
    """Tier-2: schema-driven typed extraction. Returns a dict conforming to `schema`;
    missing fields are null — never fabricated."""

    name: str

    def extract(
        self,
        source: str | WebResult,
        schema: dict[str, Any] | str,
        instruction: str = "",
    ) -> dict: ...


def get_extract_provider(name: str | None = None) -> ExtractProvider | None:
    """Resolve an ExtractProvider. Default = the zero-dep LLM extractor (always available).
    Returns None for unknown names or unavailable (key-gated) backends.
    """
    if name in (None, "llm"):
        from bad_research.browse.extract_llm import LLMExtractProvider

        return LLMExtractProvider()

    if name == "agentql":
        if not os.environ.get("AGENTQL_API_KEY"):
            return None
        try:
            from bad_research.browse.extract_agentql import AgentQLExtractProvider
        except ImportError:
            return None
        return AgentQLExtractProvider()

    if name == "stagehand":
        # Stagehand-extract needs a live session; only usable mid-Tier-3.
        # Not standalone-resolvable here, so the factory returns None and the
        # ladder constructs it from an active BrowserbaseProvider session instead.
        return None

    return None


def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    """Resolve a BrowseProvider. Default = Browser-Use self-host (if the lib is installed).
    Returns None for unknown names or unavailable backends.
    """
    if name in (None, "browser-use"):
        try:
            from bad_research.browse.browse_browseruse import BrowserUseProvider
        except ImportError:
            return None
        return BrowserUseProvider()

    if name == "browserbase":
        if not os.environ.get("BROWSERBASE_API_KEY"):
            return None
        try:
            from bad_research.browse.browse_browserbase import BrowserbaseProvider
        except ImportError:
            return None
        return BrowserbaseProvider()

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_base.py -v`
Expected: PASS — 9 tests. (`test_get_extract_provider_default_is_llm` needs `extract_llm.py`; if it errors on import, that means Task 3 isn't built yet — temporarily skip it with `@pytest.mark.xfail(reason="extract_llm built in Task 3")` and remove the marker after Task 3. All other 8 pass now.)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/__init__.py src/bad_research/browse/base.py tests/test_browse/__init__.py tests/test_browse/test_base.py
git commit -m "feat(browse): BrowseProvider/ExtractProvider protocols + graceful factories"
```

> Create `tests/test_browse/__init__.py` as an empty file in this task.

---

## Task 2: Shared test fixtures + ActCache (`browse/cache.py`)

The `ActCache` is the cost lever: the first agentic browse of a site produces a replayable script keyed by `SHA-256({instruction, url, variable NAMES})` (never values — secrets must not be cached, per dossier 03 §1.5). A later request with the same key replays at zero LLM cost. We also build the shared `conftest.py` fixtures every later test reuses (junk/login/good `WebResult` builders + a fake LLM).

**Files:**
- Create: `tests/test_browse/conftest.py`
- Create: `src/bad_research/browse/cache.py`
- Test: `tests/test_browse/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/conftest.py
"""Shared fixtures for the browse-ladder tests. Mocks everything external."""

from __future__ import annotations

from typing import Any

import pytest

from bad_research.web.base import WebResult


def make_result(content: str, *, url: str = "https://example.test/page",
                title: str = "Example") -> WebResult:
    return WebResult(url=url, title=title, content=content)


@pytest.fixture
def good_result() -> WebResult:
    # Long, clean content — passes looks_like_junk (>= 300 chars, no bot/error signals).
    body = ("This is a substantial article about a real topic. " * 20)
    return make_result(body, title="A Real Article")


@pytest.fixture
def empty_result() -> WebResult:
    # < 300 chars → looks_like_junk == "Empty or near-empty content" → escalate 0→1.
    return make_result("tiny", title="Stub")


@pytest.fixture
def bot_result() -> WebResult:
    # Cloudflare interstitial → looks_like_junk == "Bot detection page: ..." → escalate to 3b.
    return make_result("Just a moment... Checking your browser. Ray ID: abc123. " * 10,
                       title="Just a moment...")


@pytest.fixture
def login_result() -> WebResult:
    # Short + login signals + /login path → looks_like_login_wall == True → escalate to 3.
    return make_result("Please sign in to continue. Create account.",
                       url="https://example.test/login", title="Sign in")


class FakeLLM:
    """A stand-in LLMProvider: returns a canned text per call. Records calls."""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages, *, tier="triage", tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        self.calls.append({"messages": messages, "tier": tier, "temperature": temperature})
        from bad_research.llm.base import LLMResponse

        text = self._replies.pop(0) if self._replies else "{}"
        return LLMResponse(text=text, tool_calls=[], usage={}, model="fake")


@pytest.fixture
def fake_llm() -> Any:
    return FakeLLM
```

```python
# tests/test_browse/test_cache.py
"""ActCache: stable replay keys (names not values) + hit/miss round-trip."""

from __future__ import annotations

import pytest

from bad_research.browse.cache import ActCache, replay_key_for


def test_replay_key_is_deterministic() -> None:
    k1 = replay_key_for("log in then open billing", "https://x.test/app",
                         variables={"user": "alice", "pw": "secret"})
    k2 = replay_key_for("log in then open billing", "https://x.test/app",
                         variables={"user": "DIFFERENT", "pw": "ALSO-DIFFERENT"})
    # Same instruction+url+variable NAMES → same key, even though VALUES differ.
    assert k1 == k2


def test_replay_key_changes_with_instruction() -> None:
    a = replay_key_for("open billing", "https://x.test", variables=None)
    b = replay_key_for("open settings", "https://x.test", variables=None)
    assert a != b


def test_replay_key_changes_with_variable_names() -> None:
    a = replay_key_for("go", "https://x.test", variables={"user": "x"})
    b = replay_key_for("go", "https://x.test", variables={"token": "x"})
    assert a != b


def test_cache_put_then_get_round_trips(tmp_path) -> None:
    cache = ActCache(root=tmp_path)
    key = replay_key_for("open page", "https://x.test", variables=None)
    assert cache.get(key) is None
    cache.put(key, {"steps": [{"action": "click", "index": 3}], "final_url": "https://x.test/done"})
    got = cache.get(key)
    assert got == {"steps": [{"action": "click", "index": 3}], "final_url": "https://x.test/done"}


def test_cache_get_missing_returns_none(tmp_path) -> None:
    cache = ActCache(root=tmp_path)
    assert cache.get("nonexistent-key") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/cache.py
"""ActCache — replay action scripts without re-paying the agent loop.

Key = SHA-256 over {instruction, url, sorted variable NAMES}. Variable VALUES are NEVER
hashed and never stored — secrets must not leak into the cache (dossier 03 §1.5).
The cached payload is a JSON-serialisable action script the BrowseProvider can replay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def replay_key_for(instruction: str, url: str, *, variables: dict | None = None) -> str:
    """Stable replay key. Uses variable NAMES only (sorted), never values."""
    var_names = sorted((variables or {}).keys())
    payload = json.dumps(
        {"instruction": instruction, "url": url, "variableKeys": var_names},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ActCache:
    """File-backed action-script cache. One JSON file per key under `root`."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, script: dict) -> None:
        self._path(key).write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_cache.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/cache.py tests/test_browse/conftest.py tests/test_browse/test_cache.py
git commit -m "feat(browse): ActCache + replay_key_for (names-not-values) + shared test fixtures"
```

> Add `replay_key_for` to `browse/__init__.py.__all__` and its import block now (it's part of the public surface).

---

## Task 3: LLMExtractProvider (`browse/extract_llm.py`) — Tier 2 default

The zero-dep default extractor. Takes a `WebResult` (or raw markdown string) + a JSON-Schema dict + an instruction, runs the **verbatim Browser-Use structured-output prompt** through the injected `LLMProvider` seam at `triage` tier (cheap `page_extraction_llm`, temperature `0.1`), parses the JSON reply, and returns a schema-shaped dict. Chunks content at `100_000` chars (dossier 03 §3.4). Grounding rule baked into the prompt: **null on missing, never fabricate.** No LLM provider available → returns `{}` (graceful — the ladder keeps the Tier-1 prose result).

**Files:**
- Create: `src/bad_research/browse/extract_llm.py`
- Test: `tests/test_browse/test_extract_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_extract_llm.py
"""LLMExtractProvider: schema-shaped dict from mocked LLM; null-on-missing; chunking."""

from __future__ import annotations

import json

from bad_research.browse.extract_llm import LLMExtractProvider
from bad_research.web.base import WebResult
from tests.test_browse.conftest import FakeLLM, make_result


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "price": {"type": "integer"},
        "in_stock": {"type": "boolean"},
    },
}


def test_extract_returns_schema_shaped_dict() -> None:
    llm = FakeLLM([json.dumps({"title": "iPhone 15 Pro", "price": 999, "in_stock": True})])
    prov = LLMExtractProvider(llm=llm)
    src = make_result("iPhone 15 Pro — $999 — In stock. " * 30)
    out = prov.extract(src, SCHEMA, instruction="extract the product")
    assert out == {"title": "iPhone 15 Pro", "price": 999, "in_stock": True}
    # Used the cheap triage tier + extract temperature 0.1.
    assert llm.calls[0]["tier"] == "triage"
    assert llm.calls[0]["temperature"] == 0.1


def test_extract_null_on_missing_field() -> None:
    """LLM that cannot find a field returns null — provider passes it through, no fabrication."""
    llm = FakeLLM([json.dumps({"title": "Mystery", "price": None, "in_stock": None})])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("Mystery item, details unknown. " * 30), SCHEMA)
    assert out["price"] is None
    assert out["in_stock"] is None


def test_extract_accepts_raw_string_source() -> None:
    llm = FakeLLM([json.dumps({"title": "Doc", "price": 0, "in_stock": False})])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract("raw markdown content here, plenty of it. " * 30, SCHEMA)
    assert out["title"] == "Doc"


def test_extract_strips_markdown_code_fences() -> None:
    """Model wraps JSON in ```json fences — provider must still parse it."""
    fenced = "```json\n" + json.dumps({"title": "Fenced", "price": 1, "in_stock": True}) + "\n```"
    llm = FakeLLM([fenced])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out["title"] == "Fenced"


def test_extract_no_llm_returns_empty_dict() -> None:
    """No LLM provider wired → graceful empty dict, never raises."""
    prov = LLMExtractProvider(llm=None)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out == {}


def test_extract_bad_json_returns_empty_dict() -> None:
    """Model returns non-JSON garbage → {} (never crash the pipeline)."""
    llm = FakeLLM(["I could not extract anything, sorry!"])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out == {}


def test_extract_chunks_long_content_and_merges() -> None:
    """Content > 100k chars → multiple chunks; results merge (list fields concatenate)."""
    schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    chunk1 = json.dumps({"items": ["a", "b"]})
    chunk2 = json.dumps({"items": ["c", "d"]})
    llm = FakeLLM([chunk1, chunk2])
    prov = LLMExtractProvider(llm=llm)
    big = "x" * 150_000  # forces 2 chunks at 100k
    out = prov.extract(make_result(big), schema)
    assert out["items"] == ["a", "b", "c", "d"]
    assert len(llm.calls) == 2  # one LLM call per chunk
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.extract_llm'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/extract_llm.py
"""LLMExtractProvider — Tier-2 default, zero new deps.

Runs Browser-Use's verbatim structured-output prompt (teardowns/BROWSER_USE.md:327-336)
over a page's markdown via the Plan-01 LLMProvider seam, at the cheap `triage` tier
(the `page_extraction_llm` pattern, dossier 03 §3.4). Returns a schema-shaped dict.
Grounding: the prompt forbids fabrication; missing fields come back null. No LLM wired
or unparseable reply → {} (graceful — caller keeps the prose result).
"""

from __future__ import annotations

import json
from typing import Any

from bad_research.web.base import WebResult

MAX_CHUNK_CHARS = 100_000  # dossier 03 §3.4 (browser-use max_chunk_chars)
EXTRACT_TEMPERATURE = 0.1  # products/BROWSERBASE_PRODUCT_CODE.md:4270

# Verbatim Browser-Use structured-output system prompt (teardowns/BROWSER_USE.md:327-336).
STRUCTURED_EXTRACT_SYSTEM_PROMPT = (
    "You are an expert at extracting structured data from the markdown of a webpage.\n"
    "<input>You will be given a query, a JSON Schema, and the markdown of a webpage that "
    "has been filtered to remove noise and advertising content.</input>\n"
    "<instructions>\n"
    "- Extract ONLY information present in the webpage. Do not guess or fabricate values.\n"
    "- Your response MUST conform to the provided JSON Schema exactly.\n"
    "- If a required field's value cannot be found on the page, use null (if the schema "
    "allows it) or an empty string / empty array as appropriate.\n"
    "- If the content was truncated, extract what is available from the visible portion.\n"
    "- If <already_collected> items are provided, skip any items whose name/title/URL "
    "matches those listed — do not include duplicates.\n"
    "</instructions>"
)


def _chunk(text: str, size: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[i:i + size] for i in range(0, len(text), size)]


def _parse_json(text: str) -> dict | None:
    """Tolerant JSON parse: strips ```json fences, finds the first {...} block."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    t = t.strip()
    try:
        val = json.loads(t)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            try:
                val = json.loads(t[start:end + 1])
                return val if isinstance(val, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _merge(acc: dict, new: dict) -> dict:
    """Merge a chunk result into the accumulator: list fields concatenate; scalars
    keep the first non-null value found."""
    for k, v in new.items():
        if isinstance(v, list):
            acc.setdefault(k, [])
            if isinstance(acc[k], list):
                acc[k].extend(v)
            else:
                acc[k] = v
        elif k not in acc or acc.get(k) in (None, "", []):
            acc[k] = v
    return acc


class LLMExtractProvider:
    name = "llm"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def extract(self, source: str | WebResult, schema: dict[str, Any] | str,
                instruction: str = "") -> dict:
        if self._llm is None:
            return {}
        content = source.content if isinstance(source, WebResult) else str(source)
        schema_str = schema if isinstance(schema, str) else json.dumps(schema)

        from bad_research.llm.base import LLMMessage

        merged: dict = {}
        for chunk_text in _chunk(content):
            collected = json.dumps(list(merged.keys())) if merged else "[]"
            user = (
                f"<query>{instruction or 'Extract the data described by the schema.'}</query>\n"
                f"<output_schema>{schema_str}</output_schema>\n"
                f"<content_stats>length={len(chunk_text)} chars</content_stats>\n"
                f"<webpage_content>{chunk_text}</webpage_content>\n"
                f"<already_collected>{collected}</already_collected>"
            )
            messages = [
                LLMMessage(role="system", content=STRUCTURED_EXTRACT_SYSTEM_PROMPT),
                LLMMessage(role="user", content=user),
            ]
            resp = self._llm.complete(messages, tier="triage",
                                      temperature=EXTRACT_TEMPERATURE, max_tokens=4096)
            parsed = _parse_json(resp.text)
            if parsed is not None:
                merged = _merge(merged, parsed)
        return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_llm.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Remove the xfail marker from Task 1**

If you added `@pytest.mark.xfail` to `test_get_extract_provider_default_is_llm` in Task 1, remove it now and re-run `tests/test_browse/test_base.py` — all 9 pass.

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/browse/extract_llm.py tests/test_browse/test_extract_llm.py
git commit -m "feat(browse): LLMExtractProvider — Tier-2 default, verbatim browser-use prompt, null-on-missing"
```

---

## Task 4: AgentQLExtractProvider (`browse/extract_agentql.py`) — Tier 2, key-gated

POSTs `(html_or_url, query)` to the AgentQL REST `/v1/query-data` endpoint and returns the typed dict. The AQL query string IS the schema; if the caller passed a JSON-Schema dict, we translate it to an AQL string (objects → `{}`, arrays → `[]`, leaf + numeric/boolean type → `field(integer|boolean|float)`). The deterministic ref-grounding + 1 corrective retry (dossier 03 §2.4) live **on the AgentQL server**, so this client only sends the query and parses the JSON `data`. Mock httpx — no live API in tests.

**Files:**
- Create: `src/bad_research/browse/extract_agentql.py`
- Test: `tests/test_browse/test_extract_agentql.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_extract_agentql.py
"""AgentQLExtractProvider: JSON-Schema→AQL translation + mocked HTTP query-data."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.browse.extract_agentql import AgentQLExtractProvider, json_schema_to_aql
from bad_research.web.base import WebResult


def test_json_schema_to_aql_object_and_types() -> None:
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "integer"},
            "in_stock": {"type": "boolean"},
        },
    }
    aql = json_schema_to_aql(schema)
    assert aql.startswith("{") and aql.endswith("}")
    assert "title" in aql
    assert "price(integer)" in aql
    assert "in_stock(boolean)" in aql


def test_json_schema_to_aql_array_of_objects() -> None:
    schema = {
        "type": "object",
        "properties": {
            "products": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "price": {"type": "integer"}}},
            }
        },
    }
    aql = json_schema_to_aql(schema)
    assert "products[]" in aql
    assert "name" in aql and "price(integer)" in aql


def test_extract_posts_query_and_returns_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"data": {"title": "Hello", "price": 999}}
    resp.raise_for_status.return_value = None
    client.post.return_value = resp
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    src = WebResult(url="https://shop.test/p", title="P", content="...", raw_html="<html>...</html>")
    out = prov.extract(src, "{ title  price(integer) }")
    assert out == {"title": "Hello", "price": 999}
    # Posted to the query-data endpoint with the api key header.
    _, kwargs = client.post.call_args
    assert "X-API-Key" in kwargs["headers"]


def test_extract_string_source_sends_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raw-URL source → AgentQL navigates itself (body carries `url`)."""
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"data": {"x": 1}}
    resp.raise_for_status.return_value = None
    client.post.return_value = resp
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    prov.extract("https://shop.test/p", "{ x(integer) }")
    _, kwargs = client.post.call_args
    assert kwargs["json"]["url"] == "https://shop.test/p"


def test_extract_http_error_returns_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server error → {} (graceful — ladder keeps prose), never raises."""
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    client.post.side_effect = RuntimeError("boom")
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    out = prov.extract(WebResult(url="https://x.test", title="x", content="c"), "{ a }")
    assert out == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_agentql.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.extract_agentql'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/extract_agentql.py
"""AgentQLExtractProvider — Tier-2 typed extraction via AgentQL REST query-data.

The AQL query string IS the schema (dossier 03 §2.1). JSON-Schema dicts are translated to
AQL: object→{}, array→[], numeric/boolean leaf→field(type). Deterministic ref-grounding +
1 corrective retry run server-side (dossier 03 §2.4) — this client only sends the query.
Key-gated by AGENTQL_API_KEY; any HTTP failure degrades to {} (never raises).
"""

from __future__ import annotations

import os
from typing import Any

from bad_research.web.base import WebResult

AGENTQL_ENDPOINT = "https://api.agentql.com/v1/query-data"
_TYPE_HINT = {"integer": "integer", "number": "float", "boolean": "boolean"}


def json_schema_to_aql(schema: dict[str, Any]) -> str:
    """Translate a JSON-Schema object into an AgentQL query string."""

    def render_props(props: dict[str, Any]) -> str:
        fields = []
        for name, spec in props.items():
            spec = spec or {}
            t = spec.get("type")
            if t == "object":
                fields.append(f"{name} {{ {render_props(spec.get('properties', {}))} }}")
            elif t == "array":
                items = spec.get("items", {}) or {}
                if items.get("type") == "object":
                    fields.append(f"{name}[] {{ {render_props(items.get('properties', {}))} }}")
                else:
                    fields.append(f"{name}[]")
            elif t in _TYPE_HINT:
                fields.append(f"{name}({_TYPE_HINT[t]})")
            else:
                fields.append(name)
        return "  ".join(fields)

    return "{ " + render_props(schema.get("properties", {})) + " }"


class AgentQLExtractProvider:
    name = "agentql"

    def __init__(self, endpoint: str = AGENTQL_ENDPOINT) -> None:
        self._endpoint = endpoint
        self._key = os.environ.get("AGENTQL_API_KEY", "")

    def extract(self, source: str | WebResult, schema: dict[str, Any] | str,
                instruction: str = "") -> dict:
        import httpx

        query = schema if isinstance(schema, str) else json_schema_to_aql(schema)
        body: dict[str, Any] = {"query": query,
                                "params": {"mode": "standard", "wait_for": 0}}
        if isinstance(source, WebResult):
            if source.raw_html:
                body["html"] = source.raw_html
            else:
                body["url"] = source.url
        else:
            body["url"] = str(source)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(self._endpoint, json=body,
                                   headers={"X-API-Key": self._key,
                                            "Content-Type": "application/json"})
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_agentql.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/extract_agentql.py tests/test_browse/test_extract_agentql.py
git commit -m "feat(browse): AgentQLExtractProvider — JSON-Schema→AQL + query-data HTTP, graceful"
```

---

## Task 5: StagehandExtractProvider (`browse/extract_stagehand.py`) — Tier 2, session-bound

Only usable when a live Stagehand/Browserbase page object exists (handed in by the `BrowserbaseProvider` mid-Tier-3). Wraps `page.extract({instruction, schema})` (dossier 03 §1.2). It cannot be resolved standalone by the factory (returns `None` there — see Task 1) — it is constructed from an active session. Mock the session/page object.

**Files:**
- Create: `src/bad_research/browse/extract_stagehand.py`
- Test: `tests/test_browse/test_extract_stagehand.py` (add to the existing test file set)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_extract_stagehand.py
"""StagehandExtractProvider: wraps a live page.extract; mock the page."""

from __future__ import annotations

from unittest.mock import MagicMock

from bad_research.browse.extract_stagehand import StagehandExtractProvider


SCHEMA = {"type": "object", "properties": {"headline": {"type": "string"}}}


def test_extract_calls_page_extract_with_instruction_and_schema() -> None:
    page = MagicMock()
    page.extract.return_value = {"headline": "Big News"}
    prov = StagehandExtractProvider(page=page)
    out = prov.extract("ignored-when-session-bound", SCHEMA, instruction="get the headline")
    assert out == {"headline": "Big News"}
    args, kwargs = page.extract.call_args
    payload = args[0] if args else kwargs
    # Stagehand extract takes {instruction, schema}.
    assert payload["instruction"] == "get the headline"
    assert payload["schema"] == SCHEMA


def test_extract_no_page_returns_empty_dict() -> None:
    """No live session → {} (graceful)."""
    prov = StagehandExtractProvider(page=None)
    assert prov.extract("x", SCHEMA) == {}


def test_extract_page_error_returns_empty_dict() -> None:
    page = MagicMock()
    page.extract.side_effect = RuntimeError("session closed")
    prov = StagehandExtractProvider(page=page)
    assert prov.extract("x", SCHEMA) == {}


def test_extract_non_dict_result_coerced_to_empty() -> None:
    page = MagicMock()
    page.extract.return_value = "not a dict"
    prov = StagehandExtractProvider(page=page)
    assert prov.extract("x", SCHEMA) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_stagehand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.extract_stagehand'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/extract_stagehand.py
"""StagehandExtractProvider — Tier-2 extraction against a LIVE Stagehand page.

Used only mid-Tier-3, when a Browserbase/Stagehand session is already open (interactive
widgets / link-ID extraction crawl4ai can't reach — dossier 03 §1.2). Calls
page.extract({instruction, schema}). The verbatim EXTRACT_SYSTEM_PROMPT lives in the
Stagehand server (products/BROWSERBASE_PRODUCT_CODE.md:4313-4327); this is the client call.
No page → {} (graceful).
"""

from __future__ import annotations

from typing import Any

from bad_research.web.base import WebResult


class StagehandExtractProvider:
    name = "stagehand"

    def __init__(self, page: Any | None = None) -> None:
        self._page = page

    def extract(self, source: str | WebResult, schema: dict[str, Any] | str,
                instruction: str = "") -> dict:
        if self._page is None:
            return {}
        try:
            result = self._page.extract({"instruction": instruction, "schema": schema})
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_extract_stagehand.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/extract_stagehand.py tests/test_browse/test_extract_stagehand.py
git commit -m "feat(browse): StagehandExtractProvider — session-bound page.extract wrapper"
```

---

## Task 6: BrowserUseProvider (`browse/browse_browseruse.py`) — Tier 3 self-host default

Wraps a `browser_use.Agent(task=instruction, llm=..., browser_session=...)`. On `done`, dumps the final page → markdown for `WebResult.content`. Integrates the `ActCache`: a `replay_key` hit skips the agent loop entirely (zero LLM cost). Optional `browser_use` lib — missing → the factory returned `None` in Task 1, so this module is never imported when the lib is absent. We mock `browser_use.Agent` in tests (no real browser).

The Browser-Use `Agent.run()` is async; we wrap it with `asyncio.run` exactly as `crawl4ai_provider.py` does for its async crawler.

**Files:**
- Create: `src/bad_research/browse/browse_browseruse.py`
- Test: `tests/test_browse/test_browse_browseruse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_browse_browseruse.py
"""BrowserUseProvider: agentic browse → WebResult; replay-cache short-circuit."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from bad_research.web.base import WebResult


@pytest.fixture
def fake_browser_use(monkeypatch: pytest.MonkeyPatch):
    """Install a fake `browser_use` module with an Agent whose run() returns a final page."""
    mod = types.ModuleType("browser_use")

    class FakeHistory:
        def final_result(self):
            return "Final extracted page content, long enough to be real. " * 10

    class FakeAgent:
        last_init = {}

        def __init__(self, *, task, llm=None, browser_session=None, **kw):
            FakeAgent.last_init = {"task": task, "llm": llm, "kw": kw}

        async def run(self, max_steps=12):
            FakeAgent.last_init["max_steps"] = max_steps
            return FakeHistory()

    mod.Agent = FakeAgent
    monkeypatch.setitem(sys.modules, "browser_use", mod)
    return mod


def test_browse_returns_webresult(fake_browser_use) -> None:
    from bad_research.browse.browse_browseruse import BrowserUseProvider

    prov = BrowserUseProvider(llm=MagicMock())
    r = prov.browse("https://app.test", "log in and open billing", max_steps=7)
    assert isinstance(r, WebResult)
    assert "Final extracted page content" in r.content
    assert r.url == "https://app.test"
    assert fake_browser_use.Agent.last_init["max_steps"] == 7


def test_browse_passes_instruction_as_task(fake_browser_use) -> None:
    from bad_research.browse.browse_browseruse import BrowserUseProvider

    prov = BrowserUseProvider(llm=MagicMock())
    prov.browse("https://app.test", "load all reviews")
    assert "load all reviews" in fake_browser_use.Agent.last_init["task"]
    assert "https://app.test" in fake_browser_use.Agent.last_init["task"]


def test_replay_cache_hit_skips_agent(fake_browser_use, tmp_path) -> None:
    """A replay_key with a cached script returns without ever constructing the Agent."""
    from bad_research.browse.browse_browseruse import BrowserUseProvider
    from bad_research.browse.cache import ActCache, replay_key_for

    cache = ActCache(root=tmp_path)
    key = replay_key_for("open billing", "https://app.test", variables=None)
    cache.put(key, {"content": "CACHED page body, replayed at zero cost. " * 5,
                    "final_url": "https://app.test/billing"})

    fake_browser_use.Agent.last_init = {}  # reset spy
    prov = BrowserUseProvider(llm=MagicMock(), cache=cache)
    r = prov.browse("https://app.test", "open billing", replay_key=key)
    assert "CACHED page body" in r.content
    assert r.url == "https://app.test/billing"
    # Agent was never constructed (no task recorded since reset).
    assert fake_browser_use.Agent.last_init == {}


def test_replay_cache_miss_runs_agent_then_stores(fake_browser_use, tmp_path) -> None:
    from bad_research.browse.browse_browseruse import BrowserUseProvider
    from bad_research.browse.cache import ActCache, replay_key_for

    cache = ActCache(root=tmp_path)
    key = replay_key_for("open billing", "https://app.test", variables=None)
    prov = BrowserUseProvider(llm=MagicMock(), cache=cache)
    prov.browse("https://app.test", "open billing", replay_key=key)
    # After a miss, the result is cached for next time.
    assert cache.get(key) is not None
    assert "Final extracted page content" in cache.get(key)["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_browse_browseruse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.browse_browseruse'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/browse_browseruse.py
"""BrowserUseProvider — Tier-3 self-host agentic browse (dossier 03 §3).

Wraps browser_use.Agent (indexed-DOM loop, picks actions by integer index → no selector
hallucination). On `done`, the final result becomes WebResult.content. A replay_key hit
returns a cached page body without running the loop (ActCache, dossier 03 §1.5). The Agent
is async (like crawl4ai's crawler) so we drive it with asyncio.run. Optional browser_use
lib — if absent, the factory never imports this module.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from bad_research.browse.cache import ActCache
from bad_research.web.base import WebResult


class BrowserUseProvider:
    name = "browser-use"

    def __init__(self, llm: Any | None = None, cache: ActCache | None = None) -> None:
        self._llm = llm
        self._cache = cache

    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult:
        # Replay short-circuit: cached script → zero-cost WebResult.
        if replay_key and self._cache is not None:
            cached = self._cache.get(replay_key)
            if cached is not None:
                return WebResult(
                    url=cached.get("final_url", url),
                    title=cached.get("title", ""),
                    content=cached.get("content", ""),
                    fetched_at=datetime.now(UTC),
                    metadata={"replayed": True, "replay_key": replay_key},
                )

        result = asyncio.run(self._run(url, instruction, max_steps, variables))

        if replay_key and self._cache is not None:
            self._cache.put(replay_key, {"content": result.content,
                                         "final_url": result.url, "title": result.title})
        return result

    async def _run(self, url: str, instruction: str, max_steps: int,
                   variables: dict | None) -> WebResult:
        from browser_use import Agent

        task = f"Go to {url}. {instruction}"
        agent_kwargs: dict[str, Any] = {"task": task, "llm": self._llm}
        if variables:
            agent_kwargs["sensitive_data"] = variables  # %var% redaction (dossier 03 §3.3)
        agent = Agent(**agent_kwargs)
        history = await agent.run(max_steps=max_steps)

        content = ""
        if hasattr(history, "final_result"):
            content = history.final_result() or ""
        elif isinstance(history, str):
            content = history
        return WebResult(url=url, title="", content=content or "",
                         fetched_at=datetime.now(UTC), metadata={"tier": 3})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_browse_browseruse.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/browse_browseruse.py tests/test_browse/test_browse_browseruse.py
git commit -m "feat(browse): BrowserUseProvider — Tier-3 self-host agentic browse + replay cache"
```

---

## Task 7: BrowserbaseProvider (`browse/browse_browserbase.py`) — Tier 3b, opt-in anti-bot

The paid escalation for Cloudflare/Datadome walls and logins. Connects over CDP to `connect.browserbase.com` with `verified` stealth + proxy + captcha-solve, then drives a Stagehand `agent.execute(instruction)`. Key-gated by `BROWSERBASE_API_KEY` (factory returns `None` without it, Task 1). Same `ActCache` replay short-circuit as Browser-Use. We mock the whole Stagehand client — no real connection.

**Files:**
- Create: `src/bad_research/browse/browse_browserbase.py`
- Test: `tests/test_browse/test_browse_browserbase.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_browse_browserbase.py
"""BrowserbaseProvider: mocked Stagehand agent → WebResult; verified stealth; replay."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.web.base import WebResult


def _fake_stagehand_factory(final_text: str, final_url: str = "https://site.test/done"):
    """Build a fake Stagehand client whose agent.execute returns a result and whose
    page.extract / page text yields content."""
    stagehand = MagicMock()
    agent = MagicMock()
    agent.execute.return_value = MagicMock(success=True)
    stagehand.agent.return_value = agent
    page = MagicMock()
    page.url = final_url
    page.extract.return_value = {"text": final_text}
    page.content.return_value = f"<html><body>{final_text}</body></html>"
    stagehand.page = page
    return stagehand, agent, page


def test_browse_drives_agent_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    stagehand, agent, page = _fake_stagehand_factory("Recovered content behind Cloudflare. " * 8)

    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", lambda **kw: stagehand)

    prov = mod.BrowserbaseProvider()
    r = prov.browse("https://site.test", "dismiss the wall and read the article", max_steps=10)
    assert isinstance(r, WebResult)
    assert "Recovered content" in r.content
    assert r.url == "https://site.test/done"
    agent.execute.assert_called_once()


def test_browse_uses_verified_stealth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-bot tier must request verified stealth (stealth_level 2)."""
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    captured = {}

    def fake_make(**kw):
        captured.update(kw)
        stagehand, _, _ = _fake_stagehand_factory("content " * 50)
        return stagehand

    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", fake_make)

    mod.BrowserbaseProvider().browse("https://site.test", "read it")
    assert captured.get("verified") is True


def test_browse_replay_cache_hit_skips_connection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    from bad_research.browse import browse_browserbase as mod
    from bad_research.browse.cache import ActCache, replay_key_for

    sentinel = MagicMock(side_effect=AssertionError("should not connect on cache hit"))
    monkeypatch.setattr(mod, "_make_stagehand", sentinel)

    cache = ActCache(root=tmp_path)
    key = replay_key_for("read it", "https://site.test", variables=None)
    cache.put(key, {"content": "CACHED bb body " * 10, "final_url": "https://site.test/a"})

    prov = mod.BrowserbaseProvider(cache=cache)
    r = prov.browse("https://site.test", "read it", replay_key=key)
    assert "CACHED bb body" in r.content


def test_browse_connection_error_returns_junk_webresult(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the remote browser fails, return an empty WebResult (caller sees junk, doesn't crash)."""
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", MagicMock(side_effect=RuntimeError("net down")))

    r = mod.BrowserbaseProvider().browse("https://site.test", "read it")
    assert isinstance(r, WebResult)
    assert r.content == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_browse_browserbase.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.browse_browserbase'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/browse_browserbase.py
"""BrowserbaseProvider — Tier-3b anti-bot/login agentic browse (dossier 03 §1, §3b).

Connects over CDP to connect.browserbase.com with verified stealth + residential proxy +
captcha-solve, then drives a Stagehand agent.execute(instruction). The connection +
Stagehand wiring is isolated in `_make_stagehand` so tests can monkeypatch it (no SDK
needed to test the logic). Key-gated by BROWSERBASE_API_KEY. Same ActCache replay
short-circuit as Browser-Use. Any failure → empty WebResult (graceful; caller treats it
as junk, never crashes).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from bad_research.browse.cache import ActCache
from bad_research.web.base import WebResult


def _make_stagehand(*, api_key: str, verified: bool = True) -> Any:
    """Create a connected Stagehand client over a verified Browserbase session.

    Isolated for testability. Requires the `stagehand` Python SDK at runtime.
    """
    from stagehand import Stagehand  # optional dep, imported lazily

    return Stagehand(
        env="BROWSERBASE",
        api_key=api_key,
        browserbase_session_create_params={
            "browserSettings": {
                "advancedStealth": True,
                "verified": verified,          # stealth_level 2 (dossier 03 §1.1)
                "solveCaptchas": True,
                "proxies": True,
            }
        },
    )


class BrowserbaseProvider:
    name = "browserbase"

    def __init__(self, cache: ActCache | None = None) -> None:
        self._cache = cache
        self._key = os.environ.get("BROWSERBASE_API_KEY", "")

    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult:
        if replay_key and self._cache is not None:
            cached = self._cache.get(replay_key)
            if cached is not None:
                return WebResult(url=cached.get("final_url", url), title=cached.get("title", ""),
                                 content=cached.get("content", ""), fetched_at=datetime.now(UTC),
                                 metadata={"replayed": True, "replay_key": replay_key})

        try:
            stagehand = _make_stagehand(api_key=self._key, verified=True)
        except Exception:
            return WebResult(url=url, title="", content="", fetched_at=datetime.now(UTC),
                             metadata={"tier": "3b", "error": "connect_failed"})

        try:
            page = stagehand.page
            page.goto(url) if hasattr(page, "goto") else None
            agent = stagehand.agent({"maxSteps": max_steps})
            agent.execute(instruction)
            # Read the result with the tree (cheap), not a typed extract (dossier 03 §1.4 rule).
            extracted = {}
            if hasattr(page, "extract"):
                extracted = page.extract({"instruction": instruction,
                                          "schema": {"type": "object",
                                                     "properties": {"text": {"type": "string"}}}}) or {}
            content = extracted.get("text") if isinstance(extracted, dict) else ""
            if not content and hasattr(page, "content"):
                content = page.content() or ""
            final_url = getattr(page, "url", url) or url
            result = WebResult(url=final_url, title="", content=content or "",
                               fetched_at=datetime.now(UTC), metadata={"tier": "3b"})
        except Exception:
            result = WebResult(url=url, title="", content="", fetched_at=datetime.now(UTC),
                               metadata={"tier": "3b", "error": "browse_failed"})
        finally:
            try:
                stagehand.close()
            except Exception:
                pass

        if result.content and replay_key and self._cache is not None:
            self._cache.put(replay_key, {"content": result.content,
                                         "final_url": result.url, "title": result.title})
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_browse_browserbase.py -v`
Expected: PASS — 4 tests.

> Note: `test_browse_uses_verified_stealth` and `test_browse_drives_agent_execute` rely on `_make_stagehand` being monkeypatchable at module scope. The `page.content()` fallback in the fake returns HTML, but `page.extract` returns `{"text": ...}` first, so `content` comes from the extract path. The connection-error test patches `_make_stagehand` to raise before any page work.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/browse/browse_browserbase.py tests/test_browse/test_browse_browserbase.py
git commit -m "feat(browse): BrowserbaseProvider — Tier-3b verified-stealth agentic browse, graceful"
```

---

## Task 8: `fetch_tiered` — the Tier 0→3 ladder (`browse/ladder.py`)

The centerpiece. `fetch_tiered(url, *, tier_max, instruction=None, schema=None) -> WebResult` runs tiers in order, escalating only when a cheaper tier's result fails a gate. The escalation policy (dossier 03 §6, all signals from `web/base.py` verbatim):

- **Tier 0 (HTTP)** via `get_provider("builtin")`. → escalate to Tier 1 if `looks_like_junk()` returns `"Empty or near-empty content"` (i.e. `len(content.strip()) < 300` — likely a JS app) **and** `tier_max >= 1`.
- **Tier 1 (crawl4ai JS render)** via `get_provider("crawl4ai")`. Skipped (graceful) if the lib is missing → stay on the best lower-tier result. → if `looks_like_junk()` == a `"Bot detection page: ..."` reason **and** `tier_max >= 3` → escalate to **Tier 3b** (Browserbase, anti-bot). → if `looks_like_login_wall(url)` **and** `tier_max >= 3` → escalate to **Tier 3** (agentic login).
- **Tier 2 (typed extract)** fires when the caller passed a `schema` (not on junk — it's an *output-shape* request). It runs over the best content we have so far, attaching the typed dict to `WebResult.metadata["extracted"]`. The prose `content` is preserved. If extraction returns `{}` (no provider / failure), the result is unchanged (graceful).
- **Tier 3 (agentic browse)** fires when the caller passed an `instruction` (multi-step goal) OR the escalation triggers above fired, **and** `tier_max >= 3`. Uses `get_browse_provider()` (Browser-Use default; Browserbase for the anti-bot case). If no browse provider is available → stay on the best lower-tier result (graceful).

`tier_max` caps how far the ladder may climb (e.g. width-sweep passes `tier_max=1` to stay cheap; depth/gap-fetch pass `tier_max=3`). The ladder always returns the **best** `WebResult` it reached, even if every escalation was unavailable.

The ladder accepts injected providers/LLM so tests never touch the network. Production wiring (real `get_provider`, an `LLMProvider` from Plan 01) is the default when nothing is injected.

**Files:**
- Create: `src/bad_research/browse/ladder.py`
- Test: `tests/test_browse/test_ladder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_ladder.py
"""fetch_tiered escalation decisions — the heart of Plan 04. All providers mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.browse.ladder import fetch_tiered
from bad_research.web.base import WebResult
from tests.test_browse.conftest import make_result


def _good(url="https://x.test"):
    return make_result("Substantial real article content. " * 30, url=url, title="Real")


def _empty(url="https://x.test"):
    return make_result("tiny", url=url, title="Stub")


def _bot(url="https://x.test"):
    return make_result("Just a moment... checking your browser ray id " * 10,
                       url=url, title="Just a moment...")


def _login(url="https://x.test/login"):
    return make_result("Please sign in. create account.", url=url, title="Sign in")


def test_tier0_good_result_no_escalation() -> None:
    """Tier 0 returns clean content → ladder stops at Tier 0, never builds Tier 1."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    t1 = MagicMock()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t0.fetch.assert_called_once()
    t1.fetch.assert_not_called()


def test_tier0_empty_escalates_to_tier1() -> None:
    """Empty Tier-0 (< 300 chars) → escalate to crawl4ai Tier 1."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t1.fetch.assert_called_once()


def test_tier1_unavailable_returns_best_lower_tier() -> None:
    """crawl4ai missing → ladder keeps the (empty) Tier-0 result, never raises."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: None)  # None = unavailable
    assert r.content == "tiny"


def test_tier_max_caps_escalation() -> None:
    """tier_max=0 forbids leaving Tier 0 even on an empty result."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=0,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content == "tiny"
    t1.fetch.assert_not_called()


def test_bot_wall_escalates_to_browserbase() -> None:
    """Tier-1 bot-detection page + tier_max>=3 → Tier-3b Browserbase browse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _bot()
    bb = MagicMock(); bb.browse.return_value = make_result("Recovered behind cloudflare. " * 20)
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1,
                     _browserbase=bb, _browseruse=None)
    assert "Recovered behind cloudflare" in r.content
    bb.browse.assert_called_once()


def test_login_wall_escalates_to_agentic_browse() -> None:
    """Tier-1 login wall + tier_max>=3 → Tier-3 agentic (Browser-Use) browse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    bu = MagicMock(); bu.browse.return_value = make_result("Logged-in dashboard content. " * 20)
    r = fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                     _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    assert "Logged-in dashboard" in r.content
    bu.browse.assert_called_once()


def test_schema_triggers_tier2_extract_attaches_dict() -> None:
    """A schema arg → Tier-2 extract; typed dict attaches to metadata['extracted']."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    extractor = MagicMock(); extractor.extract.return_value = {"title": "Real", "n": 3}
    r = fetch_tiered("https://x.test", tier_max=2,
                     schema={"type": "object", "properties": {"title": {"type": "string"}}},
                     _tier0=t0, _tier1_factory=lambda: MagicMock(),
                     _extractor=extractor)
    assert r.metadata["extracted"] == {"title": "Real", "n": 3}
    assert r.content.startswith("Substantial real")  # prose preserved
    extractor.extract.assert_called_once()


def test_schema_extract_empty_leaves_result_unchanged() -> None:
    """Extractor returns {} (no provider) → result unchanged, no metadata['extracted']."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    extractor = MagicMock(); extractor.extract.return_value = {}
    r = fetch_tiered("https://x.test", tier_max=2,
                     schema={"type": "object"}, _tier0=t0,
                     _tier1_factory=lambda: MagicMock(), _extractor=extractor)
    assert "extracted" not in r.metadata


def test_instruction_triggers_tier3_browse() -> None:
    """An instruction (multi-step goal) → Tier-3 browse even when Tier-0 looked OK-ish empty."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()  # JS render works...
    bu = MagicMock(); bu.browse.return_value = make_result("Paginated, all 50 reviews loaded. " * 10)
    r = fetch_tiered("https://x.test", tier_max=3, instruction="load all reviews",
                     _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    assert "all 50 reviews" in r.content
    bu.browse.assert_called_once()


def test_no_browse_provider_stays_on_lower_tier() -> None:
    """instruction set but no browse provider available → keep best lower-tier result."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3, instruction="paginate",
                     _tier0=t0, _tier1_factory=lambda: MagicMock(),
                     _browseruse=None, _browserbase=None)
    assert r.content.startswith("Substantial real")


def test_replay_key_threaded_to_browse() -> None:
    """A replay_key is forwarded to the browse provider for cache reuse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    bu = MagicMock(); bu.browse.return_value = make_result("dashboard " * 60)
    fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                 replay_key="rk-123",
                 _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    _, kwargs = bu.browse.call_args
    assert kwargs["replay_key"] == "rk-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_ladder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bad_research.browse.ladder'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/browse/ladder.py
"""fetch_tiered — the Tier 0→3 escalation ladder (dossier 03 §6).

Walk tiers in order; escalate only when a cheaper tier's WebResult trips a gate
(looks_like_junk / looks_like_login_wall — both verbatim from web/base.py). The caller
controls the ceiling with tier_max, and opts into typed output (schema) or interaction
(instruction). Every optional tier degrades gracefully: a missing provider/lib/key means
that rung is skipped and the best lower-tier result is returned. Providers are injectable
for testing (the `_tier0` / `_tier1_factory` / `_extractor` / `_browseruse` / `_browserbase`
keyword args); production uses the real factories by default.
"""

from __future__ import annotations

from typing import Any, Callable

from bad_research.web.base import WebResult


def _is_empty(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Empty or near-empty")


def _is_bot_wall(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Bot detection page")


def fetch_tiered(
    url: str,
    *,
    tier_max: int,
    instruction: str | None = None,
    schema: dict | str | None = None,
    replay_key: str | None = None,
    variables: dict | None = None,
    # ---- injection seams (tests pass mocks; production gets real defaults) ----
    _tier0: Any | None = None,
    _tier1_factory: Callable[[], Any | None] | None = None,
    _extractor: Any | None = None,
    _browseruse: Any | None = None,
    _browserbase: Any | None = None,
    _llm: Any | None = None,
) -> WebResult:
    # ---------- Tier 0: HTTP ----------
    if _tier0 is None:
        from bad_research.web.base import get_provider

        _tier0 = get_provider("builtin")
    result = _tier0.fetch(url)

    # ---------- Tier 1: crawl4ai JS render ----------
    if tier_max >= 1 and _is_empty(result):
        if _tier1_factory is None:
            def _tier1_factory():
                try:
                    from bad_research.web.base import get_provider
                    return get_provider("crawl4ai")
                except ImportError:
                    return None
        t1 = _tier1_factory()
        if t1 is not None:
            try:
                t1_result = t1.fetch(url)
                if len(t1_result.content.strip()) >= len(result.content.strip()):
                    result = t1_result
            except Exception:
                pass  # keep Tier-0 result

    # ---------- Decide on Tier-3 escalation triggers ----------
    want_anti_bot = tier_max >= 3 and _is_bot_wall(result)
    want_login = tier_max >= 3 and result.looks_like_login_wall(url)
    want_interactive = tier_max >= 3 and bool(instruction)

    if want_anti_bot or want_login or want_interactive:
        browse_result = _do_browse(
            url, instruction or "Read the main content of this page.",
            anti_bot=want_anti_bot, replay_key=replay_key, variables=variables,
            browseruse=_browseruse, browserbase=_browserbase,
        )
        if browse_result is not None and browse_result.content.strip():
            result = browse_result

    # ---------- Tier 2: typed extraction (output-shape request) ----------
    if schema is not None and tier_max >= 2:
        extractor = _extractor
        if extractor is None:
            from bad_research.browse.base import get_extract_provider

            extractor = get_extract_provider("llm")
            if extractor is not None and _llm is not None and hasattr(extractor, "_llm"):
                extractor._llm = _llm
        if extractor is not None:
            try:
                data = extractor.extract(result, schema, instruction or "")
            except Exception:
                data = {}
            if data:  # non-empty → attach; {} leaves result untouched (graceful)
                result.metadata["extracted"] = data

    return result


def _do_browse(url, instruction, *, anti_bot, replay_key, variables,
               browseruse, browserbase) -> WebResult | None:
    """Pick a browse provider. Anti-bot → Browserbase first; else Browser-Use first.
    Returns None if no provider is available (caller keeps the lower-tier result)."""
    primary, secondary = (browserbase, browseruse) if anti_bot else (browseruse, browserbase)

    if primary is None and secondary is None:
        # Lazy-resolve from real factories.
        from bad_research.browse.base import get_browse_provider

        if anti_bot:
            primary = get_browse_provider("browserbase") or get_browse_provider("browser-use")
        else:
            primary = get_browse_provider("browser-use") or get_browse_provider("browserbase")

    for prov in (primary, secondary):
        if prov is None:
            continue
        try:
            return prov.browse(url, instruction, replay_key=replay_key, variables=variables)
        except Exception:
            continue
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_ladder.py -v`
Expected: PASS — 11 tests.

- [ ] **Step 5: Wire `fetch_tiered` + `replay_key_for` into `browse/__init__.py`**

```python
# src/bad_research/browse/__init__.py  (replace the file)
"""Tier 0→3 browse/extract escalation ladder."""

from __future__ import annotations

from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)
from bad_research.browse.cache import ActCache, replay_key_for
from bad_research.browse.ladder import fetch_tiered

__all__ = [
    "fetch_tiered",
    "BrowseProvider",
    "ExtractProvider",
    "get_browse_provider",
    "get_extract_provider",
    "ActCache",
    "replay_key_for",
]
```

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/browse/ladder.py src/bad_research/browse/__init__.py tests/test_browse/test_ladder.py
git commit -m "feat(browse): fetch_tiered — Tier 0→3 escalation ladder with junk/login gates"
```

---

## Task 9: Hook the ladder into `core/fetcher.fetch_and_save`

The single change to the existing pipeline. `fetch_and_save` gains three optional params — `tier_max`, `instruction`, `schema` — and, when any is set, sources its `WebResult` from `browse.fetch_tiered(...)` instead of a bare `prov.fetch(url)`. With none set (the default), behaviour is byte-for-byte unchanged (Tier 0/1 as today), so existing tests and the width-sweep stay cheap. A returned `metadata["extracted"]` dict is persisted into the note frontmatter.

**Files:**
- Modify: `src/bad_research/core/fetcher.py` (the `fetch_and_save` signature + the fetch line + extracted-dict persistence)
- Test: `tests/test_browse/test_fetcher_hook.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_fetcher_hook.py
"""core/fetcher delegates to fetch_tiered with the right args when tiers are requested."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.web.base import WebResult


@pytest.fixture
def fake_vault(tmp_path):
    """Minimal vault stub: a config with web_provider/profile, an in-memory sqlite, dirs."""
    import sqlite3

    vault = MagicMock()
    vault.root = tmp_path
    vault.notes_dir = tmp_path / "research" / "notes"
    vault.notes_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sources (url TEXT, note_id TEXT, domain TEXT, "
                 "fetched_at TEXT, provider TEXT, content_hash TEXT)")
    vault.db = conn
    cfg = MagicMock()
    cfg.web_provider = "builtin"
    cfg.web_profile = None
    cfg.web_magic = False
    vault.config = cfg
    return vault


def test_no_tier_args_uses_plain_provider_fetch(monkeypatch, fake_vault):
    """Default call → fetch_tiered NOT used; behaviour unchanged (existing get_provider path)."""
    from bad_research.core import fetcher

    called = {"tiered": 0}
    monkeypatch.setattr(fetcher, "fetch_tiered",
                        lambda *a, **k: called.__setitem__("tiered", called["tiered"] + 1) or
                        WebResult(url="x", title="t", content="c"))

    prov = MagicMock()
    prov.name = "builtin"
    prov.fetch.return_value = WebResult(url="https://x.test", title="Real",
                                        content="Substantial article content. " * 30)
    monkeypatch.setattr("bad_research.web.base.get_provider", lambda *a, **k: prov)
    # Avoid touching real sync machinery.
    monkeypatch.setattr(fetcher, "_persist_note", lambda *a, **k: "note-1", raising=False)

    fetcher.fetch_and_save(fake_vault, "https://x.test")
    assert called["tiered"] == 0
    prov.fetch.assert_called_once()


def test_tier_args_route_through_fetch_tiered(monkeypatch, fake_vault):
    """tier_max/instruction/schema set → fetch_tiered is called with them."""
    from bad_research.core import fetcher

    captured = {}

    def fake_tiered(url, *, tier_max, instruction=None, schema=None, **kw):
        captured.update(url=url, tier_max=tier_max, instruction=instruction, schema=schema)
        return WebResult(url=url, title="Browsed", content="Recovered content. " * 40,
                         metadata={"extracted": {"k": "v"}})

    monkeypatch.setattr(fetcher, "fetch_tiered", fake_tiered)
    monkeypatch.setattr(fetcher, "_persist_note", lambda *a, **k: "note-1", raising=False)

    fetcher.fetch_and_save(fake_vault, "https://x.test", tier_max=3,
                           instruction="log in and read", schema={"type": "object"})
    assert captured["url"] == "https://x.test"
    assert captured["tier_max"] == 3
    assert captured["instruction"] == "log in and read"
    assert captured["schema"] == {"type": "object"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_fetcher_hook.py -v`
Expected: FAIL — `AttributeError: module 'bad_research.core.fetcher' has no attribute 'fetch_tiered'` (and the signature doesn't accept `tier_max`).

- [ ] **Step 3: Write minimal implementation**

Modify `src/bad_research/core/fetcher.py`. (1) Add the import + signature params. (2) Replace the single fetch line. (3) Persist `metadata["extracted"]`. Extract the note-writing block into a small `_persist_note` helper so the test can stub it without dragging in the full sync machinery — this is a pure refactor of code that already exists in `fetch_and_save`.

Add near the top of the module (after the existing `import hashlib` / `from urllib.parse import urlparse`):

```python
from bad_research.browse import fetch_tiered  # Tier 0→3 ladder hook
```

Change the signature of `fetch_and_save` (lines 9-18 today) to add three keyword params at the end:

```python
def fetch_and_save(
    vault,
    url: str,
    tags: list[str] | None = None,
    title: str | None = None,
    parent: str | None = None,
    provider_name: str | None = None,
    save_assets: bool = False,
    visible: bool = False,
    *,
    tier_max: int | None = None,
    instruction: str | None = None,
    schema: dict | str | None = None,
) -> dict:
```

Replace the fetch block (today lines ~50-57, the `prov = get_provider(...)` + `result = prov.fetch(url)`) with:

```python
    use_ladder = tier_max is not None or instruction is not None or schema is not None
    if use_ladder:
        result = fetch_tiered(
            url,
            tier_max=tier_max if tier_max is not None else 3,
            instruction=instruction,
            schema=schema,
        )
        # The ladder already chose a provider; record a synthetic name.
        prov_name = result.metadata.get("fetch_provider") \
            or ("browse" if instruction else "tiered")

        class _ProvShim:
            name = prov_name
        prov = _ProvShim()
    else:
        prov = get_provider(
            provider_name or vault.config.web_provider,
            profile=vault.config.web_profile,
            magic=vault.config.web_magic,
            headless=not visible,
        )
        result = prov.fetch(url)
```

After the note is written and the source recorded (just before the final `return {...}`), persist any extracted dict into the note frontmatter:

```python
    extracted = result.metadata.get("extracted")
    if extracted:
        note_text = note_path.read_text(encoding="utf-8")
        if note_text.startswith("---") and "extracted:" not in note_text:
            import json as _json
            end = note_text.find("---", 3)
            if end != -1:
                note_text = (
                    note_text[:end]
                    + "extracted: " + _json.dumps(extracted, ensure_ascii=False) + "\n"
                    + note_text[end:]
                )
                note_path.write_text(note_text, encoding="utf-8")
```

Finally, wrap the existing note-writing + sync + source-insert region of `fetch_and_save` in a module-level helper `_persist_note(vault, url, result, prov, tags, title, parent)` that returns `note_id` and is called from `fetch_and_save`. This is mechanical — move the existing lines (the `write_note(...)` through `conn.commit()` block) into the helper verbatim, returning `note_id` and the `note_path`. Keep the original logic identical; the only purpose is a stubbable seam for the test. If you prefer not to refactor, the test stubs `_persist_note`; provide it as a thin wrapper that the production path calls.

> Minimal acceptable change if the refactor feels risky: keep the inline note-writing, and in the test, instead of stubbing `_persist_note`, stub `bad_research.core.note.write_note` + `bad_research.core.sync.compute_sync_plan`/`execute_sync` to no-ops. Either approach satisfies the test contract: *the tier args route through `fetch_tiered`, and the default path does not.* Pick the lower-risk one for the actual codebase state.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest ../tests/test_browse/test_fetcher_hook.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Run the FULL existing fetcher/core suite to prove no regression**

Run: `cd src && python -m pytest ../tests/test_core -v`
Expected: PASS — all existing core tests still green (the default path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/core/fetcher.py tests/test_browse/test_fetcher_hook.py
git commit -m "feat(core): hook fetch_tiered into fetch_and_save (opt-in tier_max/instruction/schema)"
```

---

## Task 10: Graceful-degradation integration sweep

A final end-to-end test that proves the headline invariant: **with zero optional deps/keys, the ladder still works and never raises** — it just stops at the highest available tier. This is the "no key/lib → stop at the highest available tier" contract from the brief, exercised through the real (un-mocked-where-possible) code paths with only the *external* browsers/APIs mocked.

**Files:**
- Test: `tests/test_browse/test_graceful_degradation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_graceful_degradation.py
"""Zero-key / zero-dep posture: the ladder degrades, never raises."""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from bad_research.browse.ladder import fetch_tiered
from bad_research.browse.base import get_browse_provider, get_extract_provider
from tests.test_browse.conftest import make_result


def _no_optional_imports(monkeypatch):
    """Force crawl4ai / browser_use / stagehand to look uninstalled."""
    real = builtins.__import__

    def fake(name, *a, **k):
        if name in ("crawl4ai", "browser_use", "stagehand") or \
           name.startswith(("crawl4ai.", "browser_use.", "stagehand.")):
            raise ImportError(f"No module named {name!r}")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_no_keys_no_libs_factories_return_none(monkeypatch):
    monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    _no_optional_imports(monkeypatch)
    assert get_browse_provider("browser-use") is None
    assert get_browse_provider("browserbase") is None
    assert get_extract_provider("agentql") is None
    # LLM extractor is always constructible (it just no-ops without an LLM).
    assert get_extract_provider("llm") is not None


def test_ladder_with_only_tier0_returns_result(monkeypatch):
    """Empty Tier-0 + no crawl4ai + no browse + no extract → returns the Tier-0 result."""
    monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    _no_optional_imports(monkeypatch)

    class _T0:
        def fetch(self, url):
            return make_result("short", url=url)  # < 300 chars → would want Tier 1

    r = fetch_tiered("https://x.test", tier_max=3,
                     instruction="paginate", schema={"type": "object"},
                     _tier0=_T0())
    # No tier above 0 is available; we still get a WebResult, no exception.
    assert r.content == "short"
    assert "extracted" not in r.metadata  # LLM extractor with no LLM → {} → not attached


def test_ladder_extract_no_llm_no_crash(monkeypatch):
    """schema requested, LLM extractor present but no LLM wired → {} → result unchanged."""
    class _T0:
        def fetch(self, url):
            return make_result("Substantial content. " * 40, url=url)

    r = fetch_tiered("https://x.test", tier_max=2, schema={"type": "object"}, _tier0=_T0())
    assert r.content.startswith("Substantial content")
    assert "extracted" not in r.metadata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/test_browse/test_graceful_degradation.py -v`
Expected: It may already mostly pass (the code was built graceful), but run it to confirm. If `test_ladder_extract_no_llm_no_crash` fails because the real `get_extract_provider("llm")` returns a provider that attaches `{}`, that's the bug to confirm is absent — the ladder only attaches when `data` is truthy (Task 8 Step 3). Expected after the code from Tasks 1-8: PASS.

- [ ] **Step 3: No new implementation needed**

These behaviours were built into Tasks 1, 3, and 8. If any test fails, fix the corresponding provider/ladder code to honour the graceful contract (never raise on a missing dep/key; never attach an empty extract dict; always return the best lower-tier `WebResult`).

- [ ] **Step 4: Run the whole browse suite**

Run: `cd src && python -m pytest ../tests/test_browse -v`
Expected: PASS — all tests across all 10 task files (≈ 50 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_browse/test_graceful_degradation.py
git commit -m "test(browse): graceful-degradation sweep — zero-dep/zero-key ladder never raises"
```

---

## Packaging note (do this once, alongside any task)

Add the optional extras to `pyproject.toml` so `pipx install bad-research[browse]` pulls the agentic stack, while the base install stays lean (Tier 0/1 only):

```toml
[project.optional-dependencies]
crawl4ai = ["crawl4ai>=0.4"]            # Tier 1 (already present in hyperresearch fork)
browser-use = ["browser-use>=0.1"]      # Tier 3 self-host
browserbase = ["stagehand-py>=0.1"]     # Tier 3b anti-bot (paid)
browse = ["crawl4ai>=0.4", "browser-use>=0.1"]   # the self-host ladder, no paid keys
```

No code depends on these at import time (every optional import is lazy and guarded), so the base package imports and the full test suite run with none of them installed.

---

## Self-Review

**1. Spec coverage** (SPEC.md §3 browse + §6 the Tier ladder, INTERFACES.md, dossier 03 §6-7):

| Requirement | Task |
|---|---|
| `fetch_tiered(url, *, tier_max, instruction=None, schema=None) -> WebResult` verbatim | Task 8 |
| `BrowseProvider` / `ExtractProvider` Protocols verbatim from INTERFACES.md | Task 1 |
| Tier 0 HTTP (builtin) → Tier 1 crawl4ai (JS) | Task 8 (reuses existing providers) |
| Tier 2 typed extract: `LLMExtractProvider` (default/zero-dep via LLM seam) | Task 3 |
| Tier 2: `AgentQLExtractProvider` | Task 4 |
| Tier 2: `StagehandExtractProvider` | Task 5 |
| Tier 3: `BrowserUseProvider` (self-host default) | Task 6 |
| Tier 3: `BrowserbaseProvider` (opt-in anti-bot/login) | Task 7 |
| Escalation via `looks_like_junk()` / `looks_like_login_wall()` | Task 8 (verbatim gates) |
| `replay_key` action cache | Task 2 (cache) + Tasks 6/7 (use) + Task 8 (thread) |
| Hook into `core/fetcher.fetch()` so escalation is per-source/opt-in | Task 9 |
| All optional deps degrade gracefully | Tasks 1, 3, 6, 7, 8, 10 |
| Mock all external browsers/APIs | Every test task |

**2. Placeholder scan:** No TBD/TODO/"add error handling" — every step has complete code and exact commands. All prompts are verbatim from cited sources, not summarized.

**3. Type consistency:**
- `WebResult` used everywhere matches the existing `web/base.py` dataclass (no new fields; `metadata["extracted"]` is a dict key, not a schema change).
- `BrowseProvider.browse(...)` signature (kwargs `max_steps=12, variables, replay_key`) matches INTERFACES.md line 88-90 exactly. **Default `max_steps=12`** (INTERFACES.md), not 20 (the dossier's Stagehand default is noted but the frozen interface value wins).
- `ExtractProvider.extract(source, schema, instruction="")` matches INTERFACES.md line 92-93 exactly (`instruction` is a positional-with-default `str`, not keyword-only — matches the frozen contract).
- `fetch_tiered` keyword names (`tier_max`, `instruction`, `schema`) match INTERFACES.md line 94 exactly; the extra `_*` injection params are underscore-prefixed and keyword-only so they never collide with the public contract.
- `replay_key_for(instruction, url, *, variables)` is consistent across cache (Task 2), both browse providers (Tasks 6/7), and the ladder (Task 8).
- `LLMProvider.complete(...)` call shape (`tier="triage", temperature=0.1, max_tokens=4096`) matches Plan 01's `llm/base.py` signature.

**Decision recorded:** `BrowseProvider.browse` default `max_steps` is **12** (the INTERFACES.md frozen value). The ladder never overrides it unless a caller passes one. Browser-Use's own loop may internally allow 30-100 steps; that is an impl detail of the provider, not the contract.

---

## Execution Handoff

**Plan complete and saved to `ultimate-research/plans/2026-05-26-bad-research-04-browse.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**2. Inline Execution** — execute tasks in this session using superpowers:executing-plans, batch execution with checkpoints.

**Which approach?**
