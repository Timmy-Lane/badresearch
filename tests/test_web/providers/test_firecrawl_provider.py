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
def test_search_ex_handles_v2_web_shape() -> None:
    """Tolerant parsing: a v2-style {data:{web:[...]}} response also works."""
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://v2.test/p",
                            "title": "V2",
                            "description": "Desc V2",
                            "markdown": "# V2 body",
                        }
                    ]
                },
            },
        )
    )
    prov = FirecrawlProvider(api_key="fc-test")
    results = prov.search_ex(SearchQuery(query="x"))
    assert route.called
    assert len(results) == 1
    assert results[0].url == "https://v2.test/p"
    assert results[0].content.startswith("# V2 body")


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
