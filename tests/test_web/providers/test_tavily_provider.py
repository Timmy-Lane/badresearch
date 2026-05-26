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
