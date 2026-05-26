"""Perplexity Sonar raw-search provider — fastest + highest-quality keyword tier.

POST https://api.perplexity.ai/search (raw search, no LLM synthesis). Exposes
search_mode (web/academic/sec — three distinct indexes) as a construction param.
Returns content-less SERP rows: the snippet becomes WebResult.content; the deep-
extraction stage fills full content. fetch() is not native (dossier 02 §4.5).

Configuration:
    export PERPLEXITY_API_KEY="pplx-..."
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from bad_research.web.base import ProviderError, SearchQuery, WebResult

# Constants (KNOWN — dossier 02 §4.1, §4.4).
_BASE = "https://api.perplexity.ai"
_MAX_RESULTS_CEILING = 20
_DEFAULT_MAX_TOKENS_PER_PAGE = 4096
_TIMEOUT_S = 30
_MAX_DOMAIN_FILTER = 20


def _recency_to_filter(days: int | None) -> str | None:
    """Map recency_days -> Sonar search_recency_filter (hour/day/week/month/year)."""
    if days is None:
        return None
    if days <= 0:
        return "hour"
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class SonarProvider:
    name = "sonar"
    capabilities = {"keyword", "academic"}
    cost_per_search = 0.005  # flat per-request (dossier 02 §4.4)
    p50_ms = 358             # fastest of all four (PERPLEXITY_DEEP §4)

    def __init__(
        self,
        api_key: str | None = None,
        search_mode: Literal["web", "academic", "sec"] = "web",
        max_tokens_per_page: int = _DEFAULT_MAX_TOKENS_PER_PAGE,
    ):
        key = api_key or os.environ.get("PERPLEXITY_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "PERPLEXITY_API_KEY is not set. Get a key at "
                "https://www.perplexity.ai/settings/api and export it."
            )
        self._key = key
        self._mode = search_mode
        self._mtpp = max_tokens_per_page

    def _build_domain_filter(self, q: SearchQuery) -> list[str] | None:
        allow = q.include_domains or []
        deny = [f"-{d}" for d in (q.exclude_domains or [])]
        combined = (allow + deny)[:_MAX_DOMAIN_FILTER]
        return combined or None

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "max_results": min(q.max_results, _MAX_RESULTS_CEILING),
            "search_mode": self._mode,
            "max_tokens_per_page": self._mtpp,
        }
        recency = _recency_to_filter(q.recency_days)
        if recency is not None:
            body["search_recency_filter"] = recency
        domain_filter = self._build_domain_filter(q)
        if domain_filter is not None:
            body["search_domain_filter"] = domain_filter

        try:
            resp = httpx.post(
                f"{_BASE}/search",
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Sonar request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"Sonar error HTTP {resp.status_code}: {resp.text[:200]}")
        return [_to_web_result(row) for row in resp.json().get("results", [])]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        raise ProviderError(
            "Sonar does not support fetch — delegate to firecrawl/exa/builtin in the cascade."
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("date"):
        metadata["date"] = row["date"]
    if row.get("last_updated"):
        metadata["last_updated"] = row["last_updated"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("snippet", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
