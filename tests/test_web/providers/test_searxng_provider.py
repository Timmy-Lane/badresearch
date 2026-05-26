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
