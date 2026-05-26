"""get_provider() routes to the new providers; unknown still raises ValueError."""

from __future__ import annotations

import pytest

from bad_research.web.base import get_provider


def test_factory_searxng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARXNG_ENDPOINT", raising=False)
    prov = get_provider("searxng")
    assert prov.name == "searxng"


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
    from bad_research.web.providers import CascadeProvider, SearxngProvider

    assert SearxngProvider.name == "searxng"
    assert CascadeProvider.name == "cascade"
