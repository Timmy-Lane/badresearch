"""Recency-biased planning (lever #5): SearchQuery.recency_days now reaches the
providers as a real date filter.

  - host WebSearch / ddgs / SearXNG  -> `after:YYYY-MM-DD` Google-style operator
  - OpenAlex                         -> filter=from_publication_date:YYYY-MM-DD
  - Crossref                         -> filter=from-pub-date:YYYY-MM-DD
  - arXiv                            -> search_query ... AND submittedDate:[lo TO hi]

The cutoff date is computed by `recency_cutoff_date` (today - recency_days), so
the tests assert against that helper rather than hard-coding a wall-clock date.
A None / unset recency window is a clean no-op (no filter param, query unchanged).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import respx

from bad_research.web.base import SearchQuery, recency_cutoff_date
from bad_research.web.search.base import (
    DdgsProvider,
    SearxngProvider,
    WebSearchToolProvider,
    with_after_operator,
)
from bad_research.web.search.verticals import (
    ArxivProvider,
    CrossrefProvider,
    OpenAlexProvider,
)

RECENCY = 365
CUTOFF = recency_cutoff_date(RECENCY)


# ---- recency_cutoff_date helper -------------------------------------------

def test_cutoff_is_today_minus_window():
    assert recency_cutoff_date(30, today=date(2026, 6, 2)) == date(2026, 5, 3)


def test_cutoff_none_for_unset_or_nonpositive_window():
    assert recency_cutoff_date(None) is None
    assert recency_cutoff_date(0) is None
    assert recency_cutoff_date(-5) is None


# ---- with_after_operator (host / ddgs / searxng share this) ---------------

def test_after_operator_injected_when_window_set():
    out = with_after_operator("rust async", 30)
    assert out == f"rust async after:{recency_cutoff_date(30).isoformat()}"


def test_after_operator_noop_without_window():
    assert with_after_operator("rust async", None) == "rust async"


def test_after_operator_idempotent():
    once = with_after_operator("q", 30)
    assert with_after_operator(once, 30) == once  # not appended twice


# ---- generic providers thread recency_days through ------------------------

def test_websearch_search_ex_injects_after_into_query():
    captured: dict = {}

    def links_source(q, **kw):
        captured["q"] = q
        return []

    WebSearchToolProvider(links_source=links_source).search_ex(
        SearchQuery(query="latest ai news", recency_days=RECENCY))
    assert captured["q"] == f"latest ai news after:{CUTOFF.isoformat()}"


def test_websearch_no_recency_leaves_query_unchanged():
    captured: dict = {}
    WebSearchToolProvider(links_source=lambda q, **kw: captured.update(q=q) or []).search_ex(
        SearchQuery(query="timeless topic"))
    assert captured["q"] == "timeless topic"


def test_ddgs_search_ex_injects_after_into_query():
    fake_ddgs = MagicMock()
    fake_ddgs.return_value.text.return_value = []
    with patch("bad_research.web.search.base.DDGS", fake_ddgs):
        DdgsProvider().search_ex(SearchQuery(query="breaking story", recency_days=RECENCY))
    args, _ = fake_ddgs.return_value.text.call_args
    assert args[0] == f"breaking story after:{CUTOFF.isoformat()}"


@respx.mock
def test_searxng_search_ex_injects_after_into_query():
    route = respx.get("http://localhost:8080/search").mock(
        return_value=httpx.Response(200, json={"results": []}))
    SearxngProvider().search_ex(SearchQuery(query="recent dev", recency_days=RECENCY))
    assert route.calls.last.request.url.params["q"] == f"recent dev after:{CUTOFF.isoformat()}"


# ---- scholarly verticals get keyless date filters -------------------------

@respx.mock
def test_openalex_adds_from_publication_date_filter():
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={"results": []}))
    OpenAlexProvider().search_ex(SearchQuery(query="llm", recency_days=RECENCY))
    assert route.calls.last.request.url.params["filter"] == f"from_publication_date:{CUTOFF.isoformat()}"


@respx.mock
def test_openalex_no_filter_without_window():
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={"results": []}))
    OpenAlexProvider().search_ex(SearchQuery(query="llm"))
    assert "filter" not in route.calls.last.request.url.params


@respx.mock
def test_crossref_adds_from_pub_date_filter():
    route = respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}}))
    CrossrefProvider().search_ex(SearchQuery(query="llm", recency_days=RECENCY))
    assert route.calls.last.request.url.params["filter"] == f"from-pub-date:{CUTOFF.isoformat()}"


@respx.mock
def test_arxiv_adds_submitted_date_range():
    route = respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(
            200, text="<feed xmlns='http://www.w3.org/2005/Atom'></feed>"))
    ArxivProvider().search_ex(SearchQuery(query="llm", recency_days=RECENCY))
    sq = route.calls.last.request.url.params["search_query"]
    lo = CUTOFF.strftime("%Y%m%d") + "0000"
    assert f"submittedDate:[{lo} TO 99991231235959]" in sq
    assert sq.startswith("all:llm")


@respx.mock
def test_arxiv_no_date_range_without_window():
    route = respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(
            200, text="<feed xmlns='http://www.w3.org/2005/Atom'></feed>"))
    ArxivProvider().search_ex(SearchQuery(query="llm"))
    assert "submittedDate" not in route.calls.last.request.url.params["search_query"]
