"""Zero-key / zero-dep posture: the ladder degrades, never raises."""

from __future__ import annotations

import builtins

import pytest

from bad_research.browse.base import get_browse_provider, get_extract_provider
from bad_research.browse.ladder import fetch_tiered
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
    """Empty Tier-0 + no crawl4ai + no browse + no extract -> returns the Tier-0 result."""
    monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    _no_optional_imports(monkeypatch)

    class _T0:
        def fetch(self, url):
            return make_result("short", url=url)  # < 300 chars -> would want Tier 1

    r = fetch_tiered("https://x.test", tier_max=3,
                     instruction="paginate", schema={"type": "object"},
                     _tier0=_T0())
    # No tier above 0 is available; we still get a WebResult, no exception.
    assert r.content == "short"
    assert "extracted" not in r.metadata  # LLM extractor with no LLM -> {} -> not attached


def test_ladder_extract_no_llm_no_crash(monkeypatch):
    """schema requested, LLM extractor present but no LLM wired -> {} -> result unchanged."""
    class _T0:
        def fetch(self, url):
            return make_result("Substantial content. " * 40, url=url)

    r = fetch_tiered("https://x.test", tier_max=2, schema={"type": "object"}, _tier0=_T0())
    assert r.content.startswith("Substantial content")
    assert "extracted" not in r.metadata
