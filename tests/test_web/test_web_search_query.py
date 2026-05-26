"""SearchQuery dataclass + WebSearchProvider Protocol + cascade error classes."""

from __future__ import annotations

import pytest

from bad_research.web.base import (
    ProviderError,
    QuotaExceeded,
    RateLimited,
    SearchQuery,
    WebProvider,
    WebResult,
    WebSearchProvider,
)


def test_search_query_defaults() -> None:
    q = SearchQuery(query="rust async runtimes")
    assert q.query == "rust async runtimes"
    assert q.intent == "keyword"
    assert q.recency_days is None
    assert q.include_domains is None
    assert q.exclude_domains is None
    assert q.max_results == 10


def test_search_query_full() -> None:
    q = SearchQuery(
        query="latest llm benchmarks",
        intent="neural",
        recency_days=7,
        include_domains=["arxiv.org"],
        exclude_domains=["pinterest.com"],
        max_results=20,
    )
    assert q.intent == "neural"
    assert q.recency_days == 7
    assert q.include_domains == ["arxiv.org"]
    assert q.max_results == 20


def test_intent_literal_values() -> None:
    for intent in ("keyword", "neural", "deep"):
        q = SearchQuery(query="x", intent=intent)  # type: ignore[arg-type]
        assert q.intent == intent


def test_web_search_provider_is_runtime_checkable() -> None:
    """A duck-typed object implementing the surface passes isinstance."""

    class _Stub:
        name = "stub"
        capabilities = {"keyword"}
        cost_per_search = 0.0
        p50_ms = 100

        def fetch(self, url: str) -> WebResult:
            return WebResult(url=url, title="", content="x" * 400)

        def search(self, query: str, max_results: int = 5) -> list[WebResult]:
            return []

        def search_ex(self, q: SearchQuery) -> list[WebResult]:
            return []

    stub = _Stub()
    assert isinstance(stub, WebSearchProvider)
    assert isinstance(stub, WebProvider)  # extends the base Protocol


def test_error_class_hierarchy() -> None:
    """QuotaExceeded and RateLimited are distinct from generic ProviderError."""
    assert issubclass(QuotaExceeded, ProviderError)
    assert issubclass(RateLimited, ProviderError)
    assert not issubclass(QuotaExceeded, RateLimited)
    with pytest.raises(ProviderError):
        raise QuotaExceeded("plan quota exhausted")
