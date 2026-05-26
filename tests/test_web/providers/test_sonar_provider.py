"""SonarProvider — mocks api.perplexity.ai/search via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from bad_research.web.base import ProviderError, SearchQuery, WebResult, WebSearchProvider
from bad_research.web.providers.sonar_provider import SonarProvider

SEARCH_URL = "https://api.perplexity.ai/search"


def _sample() -> dict:
    return {
        "id": "s-1",
        "results": [
            {
                "title": "Deep Research Survey",
                "url": "https://arxiv.org/abs/1234",
                "snippet": "A survey of deep research agents and their retrieval loops.",
                "date": "2026-02-15",
                "last_updated": "2026-02-20",
            },
            {
                "title": "Sonar API",
                "url": "https://docs.perplexity.ai/sonar",
                "snippet": "The Sonar search endpoint supports batch queries.",
            },
        ],
    }


def test_provider_attrs() -> None:
    prov = SonarProvider(api_key="pplx-test")
    assert prov.name == "sonar"
    assert prov.capabilities == {"keyword", "academic"}
    assert prov.cost_per_search == 0.005
    assert prov.p50_ms == 358
    assert isinstance(prov, WebSearchProvider)


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
        SonarProvider()


@respx.mock
def test_search_ex_builds_payload() -> None:
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json=_sample()))
    prov = SonarProvider(api_key="pplx-test", search_mode="academic")
    q = SearchQuery(
        query="deep research agents",
        recency_days=30,
        include_domains=["arxiv.org"],
        exclude_domains=["medium.com"],
        max_results=15,
    )
    results = prov.search_ex(q)

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer pplx-test"
    body = json.loads(sent.content)
    assert body["query"] == "deep research agents"
    assert body["search_mode"] == "academic"
    assert body["max_results"] == 15
    assert body["max_tokens_per_page"] == 4096        # default (dossier 02 §4.1)
    assert body["search_recency_filter"] == "month"   # 30 days -> month
    # domain filter: deny prefixed with "-" (dossier 02 §4.1).
    assert body["search_domain_filter"] == ["arxiv.org", "-medium.com"]

    assert len(results) == 2
    assert all(isinstance(r, WebResult) for r in results)
    # SERP rows are content-less; snippet goes into content.
    assert results[0].content.startswith("A survey of deep research")
    assert results[0].metadata["date"] == "2026-02-15"
    assert results[0].metadata["last_updated"] == "2026-02-20"


@respx.mock
def test_max_results_capped_at_20() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    prov.search_ex(SearchQuery(query="x", max_results=999))
    body = json.loads(respx.calls.last.request.content)
    assert body["max_results"] == 20


@respx.mock
def test_recency_buckets() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    for days, expected in [(0, "hour"), (1, "day"), (7, "week"), (30, "month"), (365, "year")]:
        prov.search_ex(SearchQuery(query="x", recency_days=days))
        body = json.loads(respx.calls.last.request.content)
        assert body.get("search_recency_filter") == expected, f"{days} -> {expected}"


@respx.mock
def test_no_recency_omits_filter() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    prov = SonarProvider(api_key="pplx-test")
    prov.search_ex(SearchQuery(query="x"))
    body = json.loads(respx.calls.last.request.content)
    assert "search_recency_filter" not in body


@respx.mock
def test_5xx_raises_provider_error() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    prov = SonarProvider(api_key="pplx-test")
    with pytest.raises(ProviderError):
        prov.search_ex(SearchQuery(query="x"))


def test_fetch_not_native() -> None:
    prov = SonarProvider(api_key="pplx-test")
    with pytest.raises(ProviderError, match="does not support fetch"):
        prov.fetch("https://x.test")
