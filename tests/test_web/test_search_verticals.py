"""The 7 keyless verticals: param + response mapping (respx-mocked, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from bad_research.web.base import SearchQuery
from bad_research.web.search.verticals import (
    ArxivProvider,
    CrossrefProvider,
    EuropePMCProvider,
    OpenAlexProvider,
    PubMedProvider,
    SemanticScholarProvider,
    WikipediaProvider,
    reconstruct_abstract,
)

FIX = Path(__file__).parent / "fixtures"


def _txt(name):
    return (FIX / name).read_text()


def _json(name):
    return json.loads(_txt(name))


def test_reconstruct_abstract_orders_by_position():
    inv = {"Reciprocal": [0], "rank": [1], "fusion": [2], "works": [3]}
    assert reconstruct_abstract(inv) == "Reciprocal rank fusion works"


@respx.mock
def test_arxiv_maps_atom_to_webresults_with_oa_pdf():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=_txt("arxiv_query.atom")))
    rows = ArxivProvider().search_ex(SearchQuery(query="reciprocal rank fusion", max_results=10))
    assert len(rows) == 2
    r = rows[0]
    assert r.title == "Reciprocal Rank Fusion Revisited"
    assert r.content.startswith("We study RRF")
    assert r.metadata["source"] == "arxiv"
    assert r.metadata["year"] == "2021"
    assert r.metadata["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert r.metadata["oa_pdf"] == "http://arxiv.org/pdf/2101.00001v1"   # arXiv 100% OA
    assert r.metadata["rank"] == 1


@respx.mock
def test_openalex_reconstructs_inverted_abstract_and_sends_mailto():
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json=_json("openalex_works.json")))
    rows = OpenAlexProvider(mailto="me@example.com").search_ex(SearchQuery(query="rrf"))
    assert route.called
    assert route.calls.last.request.url.params["mailto"] == "me@example.com"
    assert route.calls.last.request.url.params["search"] == "rrf"
    r = rows[0]
    assert r.content == "Reciprocal rank fusion works"           # reconstructed
    assert r.metadata["doi"] == "https://doi.org/10.1145/rrf"
    assert r.metadata["citations"] == 1500
    assert r.metadata["oa_pdf"] == "https://example.org/rrf.pdf"
    assert r.metadata["source"] == "openalex"
    assert r.metadata["native_score"] == 3261.0


@respx.mock
def test_crossref_maps_doi_spine():
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json=_json("crossref_works.json")))
    rows = CrossrefProvider(mailto="me@example.com").search_ex(SearchQuery(query="rrf"))
    r = rows[0]
    assert r.url == "https://doi.org/10.1145/rrf"
    assert r.metadata["doi"] == "10.1145/rrf"
    assert r.metadata["year"] == 2009
    assert r.metadata["citations"] == 1500
    assert r.metadata["authors"] == ["Gordon Cormack"]
    assert r.metadata["source"] == "crossref"


@respx.mock
def test_s2_maps_tldr_and_oa_pdf():
    respx.get(url__startswith="https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=_json("s2_search.json")))
    rows = SemanticScholarProvider().search_ex(SearchQuery(query="rrf"))
    r = rows[0]
    assert r.content == "We combine ranked lists with RRF."   # prefers abstract over tldr
    assert r.metadata["doi"] == "10.1145/rrf"
    assert r.metadata["citations"] == 1500
    assert r.metadata["oa_pdf"] == "https://example.org/s2rrf.pdf"
    assert r.metadata["source"] == "s2"


@respx.mock
def test_s2_backs_off_on_429_then_returns_empty():
    respx.get(url__startswith="https://api.semanticscholar.org").mock(
        return_value=httpx.Response(429))
    rows = SemanticScholarProvider(max_retries=2, backoff_base=0.0).search_ex(SearchQuery(query="rrf"))
    assert rows == []      # best-effort: persistent 429 -> empty lane


@respx.mock
def test_europepmc_maps_core_result():
    respx.get(url__startswith="https://www.ebi.ac.uk/europepmc").mock(
        return_value=httpx.Response(200, json=_json("europepmc_search.json")))
    rows = EuropePMCProvider().search_ex(SearchQuery(query="crispr cancer"))
    r = rows[0]
    assert r.metadata["doi"] == "10.1000/epmc"
    assert r.metadata["pmid"] == "12345"
    assert r.metadata["year"] == "2023"
    assert r.content.startswith("We review CRISPR")
    assert r.metadata["source"] == "europepmc"


@respx.mock
def test_pubmed_esearch_then_esummary():
    respx.get(url__startswith="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(200, json=_json("pubmed_esearch.json")))
    respx.get(url__startswith="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
        return_value=httpx.Response(200, json=_json("pubmed_esummary.json")))
    rows = PubMedProvider().search_ex(SearchQuery(query="crispr cancer", max_results=2))
    assert len(rows) == 2
    assert rows[0].title == "CRISPR-Cas9 in tumors"
    assert rows[0].metadata["pmid"] == "38000001"
    assert rows[0].url.endswith("38000001/")
    assert rows[0].metadata["source"] == "pubmed"


@respx.mock
def test_wikipedia_search_then_summary():
    respx.get(url__startswith="https://en.wikipedia.org/w/api.php").mock(
        return_value=httpx.Response(200, json=_json("wikipedia_search.json")))
    respx.get(url__startswith="https://en.wikipedia.org/api/rest_v1/page/summary").mock(
        return_value=httpx.Response(200, json=_json("wikipedia_summary.json")))
    rows = WikipediaProvider().search_ex(SearchQuery(query="CRISPR", max_results=1))
    r = rows[0]
    assert r.content.startswith("CRISPR are DNA sequences")
    assert r.url == "https://en.wikipedia.org/wiki/CRISPR"
    assert r.metadata["wikibase_item"] == "Q412563"
    assert r.metadata["source"] == "wikipedia"
