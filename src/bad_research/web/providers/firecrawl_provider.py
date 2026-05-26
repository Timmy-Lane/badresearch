"""Firecrawl provider — deep-extraction engine (the 19-step transformer) + crawl.

search() -> POST /v1/search (scrapeOptions pulls markdown inline). fetch() ->
POST /v1/scrape (onlyMainContent, markdown+links — runs the 19-step transformer
+ injection-defended LLM-clean server-side). Base URL is overridable for the
self-hosted Firecrawl + SearXNG path. (dossier 02 §3.1, §3.3, §3.6.)

[CORRECTION 2026-05-26] Firecrawl's current public API is /v2/search returning
`{success, data: {web: [...]}}`; the /v1/search this provider targets returns a
FLAT `{success, data: [...]}` array. v1 is still live (v2 docs say "v1 remains
available"). We keep the /v1 path (the plan's contract + the simpler flat shape)
but `_extract_rows()` tolerates BOTH the flat-list (v1) and the {web:[...]} (v2)
response shapes so a live v1 OR v2-proxied response both parse.

Configuration:
    export FIRECRAWL_API_KEY="fc-..."
    export FIRECRAWL_BASE="https://api.firecrawl.dev"   # default; override for self-host
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from bad_research.web.base import ProviderError, RateLimited, SearchQuery, WebResult

_DEFAULT_BASE = "https://api.firecrawl.dev"
_TIMEOUT_S = 60


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the result rows out of either response shape.

    v1: {"success": true, "data": [ {row}, ... ]}
    v2: {"success": true, "data": {"web": [ {row}, ... ], "news": ..., ...}}
    """
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("web", []) or []
    return []


class FirecrawlProvider:
    name = "firecrawl"
    capabilities = {"keyword", "extract", "crawl"}
    cost_per_search = 0.01  # varies; conservative estimate (dossier 02 §3.5)
    p50_ms = 2000           # search+scrape is the slowest path (INFERRED)

    def __init__(self, api_key: str | None = None, base: str | None = None):
        key = api_key or os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY is not set. Get a key at https://firecrawl.dev "
                "and export it (or run self-hosted and set FIRECRAWL_BASE)."
            )
        self._key = key
        self._base = (base or os.environ.get("FIRECRAWL_BASE", _DEFAULT_BASE)).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimited("Firecrawl rate limited (HTTP 429)")
        if resp.status_code >= 400:
            raise ProviderError(f"Firecrawl error HTTP {resp.status_code}: {resp.text[:200]}")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": q.query,
            "limit": q.max_results,
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        }
        try:
            resp = httpx.post(
                f"{self._base}/v1/search", json=body, headers=self._headers(), timeout=_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Firecrawl search failed: {exc}") from exc
        self._raise_for_status(resp)
        return [_to_search_result(row) for row in _extract_rows(resp.json())]

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        body = {"url": url, "onlyMainContent": True, "formats": ["markdown", "links"]}
        try:
            resp = httpx.post(
                f"{self._base}/v1/scrape", json=body, headers=self._headers(), timeout=_TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Firecrawl scrape failed: {exc}") from exc
        self._raise_for_status(resp)
        data = resp.json().get("data", {})
        meta = data.get("metadata", {})
        result_metadata: dict[str, Any] = {}
        if meta.get("favicon"):
            result_metadata["favicon"] = meta["favicon"]
        return WebResult(
            url=data.get("url", url),
            title=meta.get("title", ""),
            content=data.get("markdown", ""),
            fetched_at=datetime.now(UTC),
            links=data.get("links", []),
            metadata=result_metadata,
        )


def _to_search_result(row: dict[str, Any]) -> WebResult:
    metadata: dict[str, Any] = {}
    if row.get("position") is not None:
        metadata["position"] = row["position"]
    if row.get("description"):
        metadata["description"] = row["description"]
    return WebResult(
        url=row.get("url", ""),
        title=row.get("title", ""),
        content=row.get("markdown") or row.get("description", ""),
        fetched_at=datetime.now(UTC),
        links=row.get("links", []),
        metadata=metadata,
    )
