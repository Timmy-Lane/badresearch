"""BrowserUseProvider: agentic browse -> WebResult; replay-cache short-circuit."""

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
