"""Tavily web provider — SERP-fusion search built for machines.

POST https://api.tavily.com/search. Auth is a Bearer header (not body).
Maps SearchQuery -> the advanced-depth, raw-markdown, RAG-native payload from
dossier 02 §1.5. Splits Tavily's custom quota codes (432/433 permanent, 429
transient) into the cascade's error classes.

Configuration:
    export TAVILY_API_KEY="tvly-..."
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import (
    ProviderError,
    QuotaExceeded,
    RateLimited,
    SearchQuery,
    WebResult,
)

# Constants (KNOWN — dossier 02 §1.4, §1.5; products/TAVILY_PRODUCT_CODE.md:130-281).
_BASE = "https://api.tavily.com"
_MAX_RESULTS_CEILING = 20
_DEFAULT_CHUNKS_PER_SOURCE = 3
_SEARCH_TIMEOUT_S = 60
_EXTRACT_TIMEOUT_S = 30
_CLIENT_SOURCE = "bad-research"


def _recency_to_time_range(days: int | None) -> str | None:
    """Map recency_days to Tavily's time_range bucket (day/week/month/year)."""
    if days is None:
        return None
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class TavilyProvider:
    name = "tavily"
    capabilities = {"keyword", "extract"}
    cost_per_search = 0.008  # advanced = 2 credits (dossier 02 §1.4)
    p50_ms = 1342            # PERPLEXITY_DEEP §4 measured

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("TAVILY_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Get a key at https://app.tavily.com "
                "and export it."
            )
        self._key = key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "X-Client-Source": _CLIENT_SOURCE,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code in (432, 433):
            raise QuotaExceeded(f"Tavily quota exhausted (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise RateLimited("Tavily rate limited (HTTP 429)")
        if resp.status_code >= 500 or resp.status_code >= 400:
            raise ProviderError(f"Tavily error HTTP {resp.status_code}: {resp.text[:200]}")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "search_depth": "advanced",
            "include_raw_content": "markdown",
            "chunks_per_source": _DEFAULT_CHUNKS_PER_SOURCE,
            "include_favicon": True,
            "max_results": min(q.max_results, _MAX_RESULTS_CEILING),
            "time_range": _recency_to_time_range(q.recency_days),
            "include_domains": q.include_domains,
            "exclude_domains": q.exclude_domains,
        }
        # Strip None values (dossier 02 §1.1 — the SDK does this so undocumented
        # params and unset filters never hit the wire).
        body = {k: v for k, v in body.items() if v is not None}
        try:
            resp = httpx.post(
                f"{_BASE}/search", json=body, headers=self._headers(), timeout=_SEARCH_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Tavily request failed: {exc}") from exc
        self._raise_for_status(resp)
        return [_to_web_result(row) for row in resp.json().get("results", [])]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        body = {"urls": [url], "extract_depth": "advanced", "format": "markdown"}
        try:
            resp = httpx.post(
                f"{_BASE}/extract", json=body, headers=self._headers(), timeout=_EXTRACT_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Tavily extract failed: {exc}") from exc
        self._raise_for_status(resp)
        rows = resp.json().get("results", [])
        if not rows:
            raise ProviderError(f"Tavily returned no content for {url}")
        row = rows[0]
        return WebResult(
            url=row.get("url", url),
            title=row.get("title", ""),
            content=row.get("raw_content") or row.get("content", ""),
            fetched_at=datetime.now(UTC),
            metadata={"favicon": row.get("favicon")} if row.get("favicon") else {},
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    """Normalize a Tavily search row -> WebResult.

    raw_content (full markdown) wins over content (the ~500-char AI snippet);
    the snippet is preserved in metadata.
    """
    metadata: dict[str, Any] = {}
    if row.get("score") is not None:
        metadata["score"] = row["score"]
    if row.get("content"):
        metadata["snippet"] = row["content"]
    if row.get("published_date"):
        metadata["published_date"] = row["published_date"]
    if row.get("favicon"):
        metadata["favicon"] = row["favicon"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("raw_content") or row.get("content", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
