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
