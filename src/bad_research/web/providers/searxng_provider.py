"""SearXNG provider — zero-cost self-hosted metasearch (the zero-key backbone).

GET {endpoint}/search?q=...&format=json. Aggregates Google/Bing/DDG/etc. No API
key, so cost_per_search = 0.0 and it never raises on a missing key — it is the
default search backbone when no premium key is present. Returns <=20 content-less
SERP rows per page; deep-extraction fills full content. (dossier 02 §5, §6.4.)

Configuration:
    export SEARXNG_ENDPOINT="http://localhost:8080"   # default
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import ProviderError, SearchQuery, WebResult

_DEFAULT_ENDPOINT = "http://localhost:8080"
_TIMEOUT_S = 15


class SearxngProvider:
    name = "searxng"
    capabilities = {"keyword"}
    cost_per_search = 0.0
    p50_ms = 800

    def __init__(
        self,
        endpoint: str | None = None,
        engines: list[str] | None = None,
        categories: str = "general",
    ):
        self._url = (
            endpoint or os.environ.get("SEARXNG_ENDPOINT", _DEFAULT_ENDPOINT)
        ).rstrip("/")
        self._engines = engines
        self._categories = categories

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        params: dict[str, str] = {
            "q": q.query,
            "format": "json",
            "categories": self._categories,
        }
        if self._engines:
            params["engines"] = ",".join(self._engines)
        try:
            resp = httpx.get(f"{self._url}/search", params=params, timeout=_TIMEOUT_S)
        except httpx.HTTPError as exc:
            raise ProviderError(f"SearXNG request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"SearXNG error HTTP {resp.status_code}")
        rows = resp.json().get("results", [])[: q.max_results]
        return [_to_web_result(row) for row in rows]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        raise ProviderError(
            "SearXNG does not support fetch — delegate to crawl4ai/builtin in the cascade."
        )


def _to_web_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("engine"):
        metadata["engine"] = row["engine"]
    if row.get("score") is not None:
        metadata["score"] = row["score"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("content", ""),
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
