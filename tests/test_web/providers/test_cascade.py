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


def test_dedup_preserves_original_url() -> None:
    """Canonicalization rewrites r.url but stashes the original in metadata so
    Stage-3 re-fetch can fall back to it."""
    original = "https://www.x.test/a/?utm_source=z"
    merged = _dedup_union({"sonar": [_r(original)]})
    assert len(merged) == 1
    row = merged[0]
    assert row.url == "https://x.test/a"          # canonicalized
    assert row.metadata["original_url"] == original  # original preserved


def test_dedup_no_original_url_when_unchanged() -> None:
    """When canonicalization is a no-op, no original_url is stashed."""
    url = "https://x.test/a"
    merged = _dedup_union({"sonar": [_r(url)]})
    assert merged[0].url == url
    assert "original_url" not in merged[0].metadata


def test_canonical_keeps_ref_param() -> None:
    """?ref=main is a meaningful routing/branch param (GitHub etc.) and must NOT
    be stripped — two distinct ref values stay distinct."""
    assert _canonical_url("https://github.com/a/b?ref=main") == "https://github.com/a/b?ref=main"
    assert _canonical_url("https://github.com/a/b?ref=main") != _canonical_url(
        "https://github.com/a/b?ref=dev"
    )


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


# --- Task 8: CascadeProvider routing -------------------------------------------


from bad_research.web.base import ProviderError, QuotaExceeded, SearchQuery
from bad_research.web.providers.cascade import CascadeProvider, cascade_search


class _StubProvider:
    """A keyword/neural provider stub that returns canned results or raises."""

    def __init__(self, name, results=None, raises=None, capabilities=None):
        self.name = name
        self.capabilities = capabilities or {"keyword"}
        self.cost_per_search = 0.0
        self.p50_ms = 100
        self._results = results or []
        self._raises = raises
        self.calls = 0

    def search_ex(self, q: SearchQuery):
        self.calls += 1
        if self._raises:
            raise self._raises
        return list(self._results)

    def search(self, query, max_results=5):
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url):
        return _r(url)


class _StubExtractor:
    def __init__(self):
        self.name = "extractor"
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return WebResult(url=url, title="fetched", content="Full extracted body. " * 40)


class _StubReranker:
    """Returns docs in reverse order with descending scores, to prove it's used."""

    def __init__(self):
        self.called = False

    def rerank(self, query, docs):
        self.called = True
        n = len(docs)
        return [(i, 1.0 - i / max(n, 1)) for i in reversed(range(n))]


def test_stage1_unions_parallel_providers() -> None:
    p1 = _StubProvider("sonar", [_r("https://a.test", 0.9)])
    p2 = _StubProvider("searxng", [_r("https://b.test", 0.85)])
    cascade = CascadeProvider(keyword_providers=[p1, p2])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert {r.url for r in results} == {"https://a.test", "https://b.test"}
    assert p1.calls == 1 and p2.calls == 1


def test_stage1_skips_failed_provider() -> None:
    good = _StubProvider("searxng", [_r("https://ok.test", 0.9)])
    dead = _StubProvider("tavily", raises=QuotaExceeded("quota"))
    cascade = CascadeProvider(keyword_providers=[good, dead])
    results = cascade.search_ex(SearchQuery(query="x"))
    # Dead provider is skipped, good provider's result survives.
    assert [r.url for r in results] == ["https://ok.test"]


def test_stage2_fires_when_stage1_thin() -> None:
    """All Stage-1 results below the 0.70 bar -> <30% pass -> neural fires."""
    thin = _StubProvider("searxng", [_r("https://lo.test", 0.4), _r("https://lo2.test", 0.5)])
    neural = _StubProvider(
        "exa", [_r("https://neural.test", 0.95)], capabilities={"neural"}
    )
    rer = _StubReranker()
    cascade = CascadeProvider(keyword_providers=[thin], neural_provider=neural, reranker=rer)
    results = cascade.search_ex(SearchQuery(query="concept query"))
    assert neural.calls == 1            # Stage-2 fired
    assert rer.called                   # reranker ran on merged set
    assert any("neural.test" in r.url for r in results)


def test_stage2_does_not_fire_when_stage1_rich() -> None:
    """Enough Stage-1 results above 0.70 -> neural does NOT fire."""
    rich = _StubProvider(
        "sonar",
        [_r("https://a.test", 0.95), _r("https://b.test", 0.92), _r("https://c.test", 0.88)],
    )
    neural = _StubProvider("exa", [_r("https://n.test", 0.99)], capabilities={"neural"})
    cascade = CascadeProvider(keyword_providers=[rich], neural_provider=neural)
    cascade.search_ex(SearchQuery(query="x"))
    assert neural.calls == 0            # Stage-2 skipped — Stage-1 was rich


def test_neural_intent_forces_stage2() -> None:
    rich = _StubProvider("sonar", [_r("https://a.test", 0.95), _r("https://b.test", 0.95)])
    neural = _StubProvider("exa", [_r("https://n.test", 0.99)], capabilities={"neural"})
    cascade = CascadeProvider(keyword_providers=[rich], neural_provider=neural)
    cascade.search_ex(SearchQuery(query="x", intent="neural"))
    assert neural.calls == 1            # intent=neural always fires Stage-2


def test_stage3_extracts_content_less_top_results() -> None:
    """SERP rows with thin content get deep-extracted; junk hits get dropped."""
    serp = _StubProvider(
        "sonar",
        [
            WebResult(url="https://thin.test", title="t", content="too short"),
            WebResult(url="https://good.test", title="g", content="x" * 600),
        ],
    )
    extractor = _StubExtractor()
    cascade = CascadeProvider(
        keyword_providers=[serp], extractor=extractor, extract_top_n=2
    )
    results = cascade.search_ex(SearchQuery(query="x"))
    # thin.test had <300 chars (junk) -> extracted; good.test already substantial.
    assert "https://thin.test" in extractor.fetched
    thin_row = next(r for r in results if "thin.test" in r.url)
    assert thin_row.content.startswith("Full extracted body")


def test_stage3_fetches_original_url_when_present() -> None:
    """Stage-3 re-fetch prefers metadata['original_url'] (set by dedup) over the
    canonical r.url, since the canonical form can 404 on strict hosts."""
    serp = _StubProvider(
        "sonar",
        [WebResult(url="https://www.thin.test/a/", title="t", content="too short")],
    )
    extractor = _StubExtractor()
    cascade = CascadeProvider(
        keyword_providers=[serp], extractor=extractor, extract_top_n=2
    )
    cascade.search_ex(SearchQuery(query="x"))
    # dedup canonicalized to https://thin.test/a and stashed the original;
    # Stage-3 must have fetched the ORIGINAL, not the canonical form.
    assert extractor.fetched == ["https://www.thin.test/a/"]


def test_zero_key_path_searxng_only() -> None:
    """SearXNG-only cascade (no neural, no extractor) still returns Stage-1 results."""
    searxng = _StubProvider("searxng", [_r("https://z.test", 0.8)], capabilities={"keyword"})
    cascade = CascadeProvider(keyword_providers=[searxng])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert [r.url for r in results] == ["https://z.test"]


def test_cascade_search_module_fn() -> None:
    """The cascade_search() free function builds + runs a CascadeProvider."""
    p = _StubProvider("searxng", [_r("https://a.test", 0.9)])
    results = cascade_search(SearchQuery(query="x"), keyword_providers=[p])
    assert [r.url for r in results] == ["https://a.test"]


def test_all_providers_dead_returns_empty() -> None:
    dead = _StubProvider("tavily", raises=ProviderError("boom"))
    cascade = CascadeProvider(keyword_providers=[dead])
    results = cascade.search_ex(SearchQuery(query="x"))
    assert results == []


def test_cascade_is_web_search_provider() -> None:
    from bad_research.web.base import WebSearchProvider

    cascade = CascadeProvider(keyword_providers=[_StubProvider("searxng")])
    assert isinstance(cascade, WebSearchProvider)
    assert cascade.name == "cascade"
