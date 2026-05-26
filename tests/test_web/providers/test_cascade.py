"""Cascade primitives + routing logic — no HTTP, stub providers + stub reranker."""

from __future__ import annotations

from bad_research.web.base import WebResult
from bad_research.web.providers.cascade import (
    RRF_K,
    _canonical_url,
    _dedup_union,
    _rrf_fuse,
)


def _r(url: str, score: float | None = None) -> WebResult:
    meta = {} if score is None else {"score": score}
    return WebResult(url=url, title=url, content="x" * 500, metadata=meta)


def test_canonical_url_collapses_noise() -> None:
    assert _canonical_url("https://www.Example.com/Page/") == _canonical_url(
        "https://example.com/Page"
    )
    assert _canonical_url("http://example.com/p#section") == _canonical_url(
        "http://example.com/p"
    )
    # tracking params stripped; path case preserved.
    assert _canonical_url("https://x.test/a?utm_source=tw&id=5") == "https://x.test/a?id=5"
    assert _canonical_url("https://x.test/a?fbclid=abc") == "https://x.test/a"


def test_canonical_url_preserves_meaningful_query() -> None:
    assert _canonical_url("https://x.test/s?q=rust&page=2") == "https://x.test/s?page=2&q=rust"


def test_dedup_union_merges_by_canonical_url() -> None:
    list_a = [_r("https://www.a.test/x/"), _r("https://b.test/y")]
    list_b = [_r("https://a.test/x"), _r("https://c.test/z")]
    merged = _dedup_union({"sonar": list_a, "tavily": list_b})

    urls = sorted(r.url for r in merged)
    # a.test/x appears once (canonical-collapsed across www + trailing slash).
    assert len(merged) == 3
    assert urls == ["https://a.test/x", "https://b.test/y", "https://c.test/z"]
    a_row = next(r for r in merged if "a.test" in r.url)
    assert set(a_row.metadata["found_by"]) == {"sonar", "tavily"}


def test_rrf_fuse_k_is_60() -> None:
    assert RRF_K == 60


def test_rrf_fuse_ranks_consensus_higher() -> None:
    # X is rank-1 in both lists -> highest RRF; Z only in one list -> lowest.
    list_a = [_r("https://x.test"), _r("https://y.test"), _r("https://z.test")]
    list_b = [_r("https://x.test"), _r("https://y.test")]
    fused = _rrf_fuse([list_a, list_b])

    urls = [r.url for r in fused]
    assert urls[0] == "https://x.test"   # rank-1 in both
    assert urls[-1] == "https://z.test"  # only one list, rank-3
    # rrf_score recorded in metadata, descending.
    scores = [r.metadata["rrf_score"] for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_fuse_formula() -> None:
    # Single list, X at rank-1: rrf = 1/(60+1).
    fused = _rrf_fuse([[_r("https://x.test")]])
    assert abs(fused[0].metadata["rrf_score"] - (1.0 / 61.0)) < 1e-9
