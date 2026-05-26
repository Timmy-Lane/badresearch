"""get_provider() is keyless (INTERFACES_KEYLESS §3.1): builtin/crawl4ai real;
websearch/ddgs/searxng + the 7 scholarly verticals resolve to the web/search/
classes; unknown raises ValueError listing only keyless names."""

from __future__ import annotations

import importlib.util

import pytest

from bad_research.web.base import get_provider
from bad_research.web.search.base import (
    DdgsProvider,
    SearxngProvider,
    WebSearchToolProvider,
)
from bad_research.web.search.verticals import ArxivProvider, OpenAlexProvider

_HAS_DDGS = importlib.util.find_spec("ddgs") is not None


def test_factory_default_is_websearch() -> None:
    """Default provider is the keyless host WebSearch adapter."""
    assert isinstance(get_provider(), WebSearchToolProvider)
    assert isinstance(get_provider("websearch"), WebSearchToolProvider)
    assert get_provider().name == "websearch"


def test_factory_builtin_is_real() -> None:
    prov = get_provider("builtin")
    assert prov.name == "builtin"


def test_factory_ddgs_and_searxng_resolve_by_name() -> None:
    assert get_provider("ddgs").name == "ddgs"
    assert get_provider("searxng").name == "searxng"


def test_factory_searxng_branch_is_real_class() -> None:
    assert isinstance(get_provider("searxng"), SearxngProvider)


def test_factory_vertical_branches() -> None:
    assert isinstance(get_provider("arxiv"), ArxivProvider)
    assert isinstance(get_provider("openalex"), OpenAlexProvider)


@pytest.mark.skipif(not _HAS_DDGS, reason="ddgs not installed")
def test_factory_ddgs_branch_is_real_class() -> None:
    assert isinstance(get_provider("ddgs"), DdgsProvider)


def test_factory_keyed_names_raise() -> None:
    with pytest.raises(ValueError):
        get_provider("tavily")     # keyed providers are gone


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
