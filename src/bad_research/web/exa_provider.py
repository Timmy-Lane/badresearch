"""Exa web provider — AI-native neural search returning ranked URLs with content.

Exa (https://exa.ai) is a search API designed for agents: results are ranked by
semantic relevance to the query and contents (text, highlights, summary) can be
returned in a single request.

Configuration:
    export EXA_API_KEY="your-api-key"     # https://dashboard.exa.ai/api-keys

    # in .hyperresearch/config.toml
    [web]
    provider = "exa"

Optional install:
    pip install "hyperresearch[exa]"
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from bad_research.web.base import SearchQuery, WebResult


class ExaProvider:
    """Web provider backed by the Exa search API.

    Supports both `search` (neural ranking) and `fetch` (URL → contents).
    Content is returned as plain text (Exa's extracted main-page text);
    when text is empty, falls back to highlights, then summary.
    """

    name = "exa"
    capabilities = {"neural", "keyword", "extract"}
    cost_per_search = 0.005  # neural 1-25 results (dossier 02 §2.5)
    p50_ms = 1375            # PERPLEXITY_DEEP §4 measured

    def __init__(
        self,
        api_key: str | None = None,
        search_type: str = "auto",
        text_max_characters: int = 8000,
        category: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ):
        try:
            from exa_py import Exa
        except ImportError as exc:
            raise ImportError(
                'exa provider requires: pip install "bad-research[exa]"'
            ) from exc

        key = api_key or os.environ.get("EXA_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "EXA_API_KEY is not set. Get a free key at "
                "https://dashboard.exa.ai/api-keys and export it."
            )

        self._client = Exa(api_key=key)
        # Tracking header so Exa can attribute traffic to this integration.
        self._client.headers["x-exa-integration"] = "hyperresearch"

        self._search_type = search_type
        self._text_max_characters = text_max_characters
        self._category = category
        self._include_domains = include_domains
        self._exclude_domains = exclude_domains

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        """Search the web via Exa and return ranked results with content."""
        kwargs: dict[str, Any] = {
            "num_results": max_results,
            "type": self._search_type,
            "contents": {
                "text": {"max_characters": self._text_max_characters},
                "highlights": True,
            },
        }
        if self._category:
            kwargs["category"] = self._category
        if self._include_domains:
            kwargs["include_domains"] = self._include_domains
        if self._exclude_domains:
            kwargs["exclude_domains"] = self._exclude_domains

        response = self._client.search(query, **kwargs)
        return [_to_web_result(r) for r in response.results]

    def fetch(self, url: str) -> WebResult:
        """Fetch a single URL via Exa /contents and return clean text."""
        response = self._client.get_contents(
            [url],
            text={"max_characters": self._text_max_characters},
        )
        if not response.results:
            raise RuntimeError(f"Exa returned no contents for {url}")
        return _to_web_result(response.results[0])

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        """Rich search: map SearchQuery -> exa-py search with highlights+summary."""
        kwargs: dict[str, Any] = {
            "num_results": q.max_results,
            "type": "neural" if q.intent == "neural" else self._search_type,
            "contents": {
                "text": {"max_characters": self._text_max_characters},
                "highlights": True,
                "summary": True,
            },
        }
        if self._category:
            kwargs["category"] = self._category
        include = q.include_domains or self._include_domains
        exclude = q.exclude_domains or self._exclude_domains
        if include:
            kwargs["include_domains"] = include
        if exclude:
            kwargs["exclude_domains"] = exclude
        if q.recency_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=q.recency_days)
            kwargs["start_published_date"] = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        response = self._client.search(q.query, **kwargs)
        return [_to_web_result(r) for r in response.results]

    def find_similar(self, url: str, max_results: int = 5) -> list[WebResult]:
        """Find pages similar to a seed URL (citation expansion). dossier 02 §2.6.

        [CORRECTION 2026-05-26] exa-py 2.13 `find_similar_and_contents` overloads
        accept `text`/`summary` but NOT a top-level `highlights` kwarg (it would
        only be honored inside `contents`, and the method is itself deprecated in
        favor of `search()`). Dropped the invalid `highlights=True` arg; `text`
        contents already give us the body. The cascade calls this rarely (citation
        expansion only), so the deprecated method is acceptable here.
        """
        response = self._client.find_similar_and_contents(
            url,
            num_results=max_results,
            text={"max_characters": self._text_max_characters},
        )
        return [_to_web_result(r) for r in response.results]


def _to_web_result(item: Any) -> WebResult:
    """Convert an exa-py Result into a hyperresearch WebResult.

    Cascades through text → highlights → summary so the caller always gets
    something usable in `content`, regardless of which content modes Exa
    populated for this row.
    """
    text = getattr(item, "text", None) or ""
    highlights = getattr(item, "highlights", None) or []
    summary = getattr(item, "summary", None) or ""

    if text.strip():
        content = text
    elif highlights:
        content = "\n\n".join(h for h in highlights if h)
    else:
        content = summary

    metadata: dict[str, Any] = {}
    for field in ("author", "published_date", "score", "favicon", "image"):
        value = getattr(item, field, None)
        if value:
            metadata[field] = value
    if highlights:
        metadata["highlights"] = list(highlights)
    if summary and summary != content:
        metadata["summary"] = summary

    return WebResult(
        url=getattr(item, "url", "") or "",
        title=getattr(item, "title", None) or "",
        content=content,
        fetched_at=datetime.now(UTC),
        metadata=metadata,
    )
