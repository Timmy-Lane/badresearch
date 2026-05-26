"""Live keyless probes (dossier 13 §8.0). Auto-skipped unless BAD_RUN_LIVE=1.

These confirm the 7 verticals are keyless (no key, polite UA) and the WebResult
mappings survive a real response shape. Network-dependent — never in CI gate."""

from __future__ import annotations

import os

import pytest

from bad_research.web.base import SearchQuery
from bad_research.web.search.verticals import (
    ArxivProvider,
    CrossrefProvider,
    EuropePMCProvider,
    OpenAlexProvider,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("BAD_RUN_LIVE") != "1", reason="set BAD_RUN_LIVE=1 to hit real APIs"
)


@pytest.mark.live
def test_arxiv_live():
    rows = ArxivProvider().search_ex(SearchQuery(query="reciprocal rank fusion", max_results=2))
    assert rows and all(r.metadata["source"] == "arxiv" for r in rows)
    assert all(r.metadata["oa_pdf"] for r in rows)   # arXiv is 100% OA


@pytest.mark.live
def test_openalex_live():
    rows = OpenAlexProvider(mailto="research@bad-research.local").search_ex(
        SearchQuery(query="reciprocal rank fusion", max_results=2))
    assert rows and rows[0].content   # reconstructed abstract is non-empty


@pytest.mark.live
def test_crossref_live():
    rows = CrossrefProvider(mailto="research@bad-research.local").search_ex(
        SearchQuery(query="reciprocal rank fusion", max_results=2))
    assert rows and all(r.metadata["doi"] for r in rows)


@pytest.mark.live
def test_europepmc_live():
    rows = EuropePMCProvider().search_ex(SearchQuery(query="crispr cancer", max_results=2))
    assert rows
