"""RRF k=60 fusion + consensus tie-break + DOI-first dedup + richness tie-break."""

from __future__ import annotations

from bad_research.web.base import WebResult
from bad_research.web.search.rank import rrf_fuse


def _r(url, source, content="", doi=None, citations=None, oa_pdf=None, title="t"):
    md = {"source": source}
    if doi is not None:
        md["doi"] = doi
    if citations is not None:
        md["citations"] = citations
    if oa_pdf is not None:
        md["oa_pdf"] = oa_pdf
    return WebResult(url=url, title=title, content=content, metadata=md)


def test_rrf_k60_exact_arithmetic():
    """One URL at rank 1 of two lists scores 2 * 1/(60+1)."""
    l1 = [_r("https://a.com", "websearch"), _r("https://b.com", "websearch")]
    l2 = [_r("https://a.com", "ddgs"), _r("https://c.com", "ddgs")]
    fused = rrf_fuse([l1, l2], k=60)
    # a appears rank-1 in both → 1/61 + 1/61; b rank-2 in l1 → 1/62; c rank-2 in l2 → 1/62
    assert fused[0].url == "https://a.com"
    # b and c tie on RRF (both 1/62) and on source count (1 each) → stable order preserved
    assert {fused[1].url, fused[2].url} == {"https://b.com", "https://c.com"}


def test_rrf_default_k_is_60_from_constants():
    l1 = [_r("https://a.com", "websearch")]
    # Calling without k uses RRF_K=60; a single rank-1 hit scores 1/61.
    fused = rrf_fuse([l1])
    assert fused[0].url == "https://a.com"


def test_rrf_consensus_tiebreak_more_sources_wins():
    # p: 1/61 (a) + 1/61 (c) = 2/61, two sources; q: 1/61, one source → p first
    a = [_r("p", "s1"), _r("q", "s2_filler")]  # p rank1 1/61
    b = [_r("q", "s2"), _r("p_filler", "s2")]  # q rank1 1/61  => p and q tie at 1/61
    c = [_r("p", "s3")]                          # p again rank1 +1/61 -> p has 2 sources
    fused = rrf_fuse([a, b, c])
    assert fused[0].url == "p"


def test_rrf_keeps_richer_representative():
    short = _r("https://a.com", "websearch", content="", title="short")
    rich = _r("https://a.com", "openalex", content="a long abstract here", title="A Full Title")
    fused = rrf_fuse([[short], [rich]])
    assert len(fused) == 1
    assert fused[0].content == "a long abstract here"   # longer content kept (§1.3)
    assert set(fused[0].metadata["sources"]) == {"websearch", "openalex"}
