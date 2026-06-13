"""Keyless generic providers: WebSearchToolProvider, DdgsProvider, SearxngProvider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from bad_research.web.base import SearchQuery, WebResult
from bad_research.web.search.base import (
    DdgsProvider,
    KeylessSearchConfig,
    SearxngProvider,
    WebSearchToolProvider,
)


def test_config_frozen_defaults():
    cfg = KeylessSearchConfig()
    assert cfg.rrf_k == 60
    assert cfg.relevance_threshold == 0.70
    assert cfg.min_pass_fraction == 0.30
    assert cfg.max_rounds == 3
    assert cfg.rerank_top_n == 30


def test_websearch_provider_attrs():
    p = WebSearchToolProvider()
    assert p.name == "websearch"
    assert p.cost_per_search == 0.0
    assert "keyword" in p.capabilities


def test_websearch_parses_links_list_of_dicts():
    """Host emits a list[{title,url}] already rank-ordered."""
    links = [
        {"title": "RRF paper", "url": "https://example.com/a"},
        {"title": "RRF blog", "url": "https://example.com/b"},
    ]
    p = WebSearchToolProvider()
    rows = p.parse_links(links)
    assert [r.url for r in rows] == ["https://example.com/a", "https://example.com/b"]
    assert rows[0].metadata == {"rank": 1, "source": "websearch"}
    assert rows[1].metadata == {"rank": 2, "source": "websearch"}
    assert rows[0].content == ""           # content-less SERP row
    assert isinstance(rows[0], WebResult)


def test_websearch_parses_raw_links_string():
    """Host sometimes emits a 'Links: [ ... ]' prefixed string blob."""
    blob = 'Links: ' + json.dumps([{"title": "T", "url": "https://x.com/1"}])
    p = WebSearchToolProvider()
    rows = p.parse_links(blob)
    assert rows[0].url == "https://x.com/1"
    assert rows[0].title == "T"
    assert rows[0].metadata["rank"] == 1


def test_websearch_search_ex_respects_max_results():
    links = [{"title": f"t{i}", "url": f"https://x.com/{i}"} for i in range(20)]
    p = WebSearchToolProvider(links_source=lambda q, **kw: links)
    q = SearchQuery(query="anything", max_results=5)
    rows = p.search_ex(q)
    assert len(rows) == 5
    assert rows[0].metadata["rank"] == 1


def test_ddgs_provider_attrs():
    p = DdgsProvider()
    assert p.name == "ddgs"
    assert p.cost_per_search == 0.0


def test_ddgs_maps_results():
    fake_rows = [
        {"title": "A", "href": "https://a.com", "body": "snippet a"},
        {"title": "B", "href": "https://b.com", "body": "snippet b"},
    ]
    fake_ddgs = MagicMock()
    fake_ddgs.return_value.text.return_value = fake_rows
    with patch("bad_research.web.search.base.DDGS", fake_ddgs):
        rows = DdgsProvider().search_ex(SearchQuery(query="rrf", max_results=10))
    assert [r.url for r in rows] == ["https://a.com", "https://b.com"]
    assert rows[0].content == "snippet a"
    assert rows[0].metadata == {"rank": 1, "source": "ddgs"}
    fake_ddgs.return_value.text.assert_called_once()
    _, kwargs = fake_ddgs.return_value.text.call_args
    assert kwargs.get("max_results") == 10


def test_ddgs_swallows_provider_errors_to_empty():
    """A scraper failure must degrade to [] (the funnel survives one dead lane)."""
    fake_ddgs = MagicMock()
    fake_ddgs.return_value.text.side_effect = RuntimeError("rate limited")
    with patch("bad_research.web.search.base.DDGS", fake_ddgs):
        rows = DdgsProvider().search_ex(SearchQuery(query="rrf"))
    assert rows == []


def test_ddgs_drops_empty_host_redirect_urls():
    # issue #14: Startpage emits click-tracking redirect URLs with an EMPTY host
    # (https:///clev?event=StartpageResultClick&...). They are non-empty strings, so
    # a bare `if not url` skip misses them; they then trip the SSRF "no host" guard
    # downstream. Drop them at parse time so a good result survives alongside.
    fake_rows = [
        {"title": "tracking", "href": "https:///clev?event=StartpageResultClick&sc=x"},
        {"title": "good", "href": "https://real.example.com/page", "body": "ok"},
        {"title": "relative", "href": "/local/path"},
    ]
    fake_ddgs = MagicMock()
    fake_ddgs.return_value.text.return_value = fake_rows
    with patch("bad_research.web.search.base.DDGS", fake_ddgs):
        rows = DdgsProvider().search_ex(SearchQuery(query="rrf", max_results=10))
    assert [r.url for r in rows] == ["https://real.example.com/page"]


def test_searxng_provider_attrs():
    p = SearxngProvider()
    assert p.name == "searxng"
    assert p.cost_per_search == 0.0
    assert p.endpoint == "http://localhost:8080"


@respx.mock
def test_searxng_search_maps_json_and_sends_format_json():
    route = respx.get("http://localhost:8080/search").mock(
        return_value=httpx.Response(200, json={"results": [
            {"url": "https://a.com", "title": "A", "content": "ca",
             "engine": "google", "score": 3.2},
            {"url": "https://b.com", "title": "B", "content": "cb",
             "engine": "bing", "score": 1.1},
        ]})
    )
    rows = SearxngProvider().search_ex(SearchQuery(query="reciprocal rank fusion", max_results=10))
    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["q"] == "reciprocal rank fusion"
    assert sent.url.params["format"] == "json"
    assert [r.url for r in rows] == ["https://a.com", "https://b.com"]
    assert rows[0].content == "ca"
    assert rows[0].metadata["source"] == "searxng"
    assert rows[0].metadata["rank"] == 1
    assert rows[0].metadata["engine"] == "google"
    assert rows[0].metadata["native_score"] == 3.2


@respx.mock
def test_searxng_degrades_to_empty_on_error():
    respx.get("http://localhost:8080/search").mock(return_value=httpx.Response(503))
    rows = SearxngProvider().search_ex(SearchQuery(query="x"))
    assert rows == []


def test_package_public_surface():
    import bad_research.web.search as s
    # every name the frozen contract (INTERFACES_KEYLESS §3.2-§3.3) promises:
    for name in (
        "KeylessSearchConfig", "WebSearchToolProvider", "DdgsProvider", "SearxngProvider",
        "rrf_fuse", "rrf_fuse_with_verticals", "HostModelReranker", "retrieve_until_good",
        "route_query", "VERTICAL_ROUTES", "detect_intent",
        "ArxivProvider", "OpenAlexProvider", "CrossrefProvider", "SemanticScholarProvider",
        "EuropePMCProvider", "PubMedProvider", "WikipediaProvider",
    ):
        assert hasattr(s, name), f"missing public export: {name}"
