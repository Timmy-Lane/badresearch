"""The quality package public API — the contract other plans import."""

from __future__ import annotations


def test_public_api_surface():
    import bad_research.quality as q

    # Stage 1
    assert callable(q.seo_farm_score)
    assert callable(q.domain_tier)
    assert callable(q.prefetch_filter)
    assert isinstance(q.DOMAIN_TIER, dict)
    assert q.Candidate is not None
    assert q.TierInfo is not None
    # Stage 2
    assert callable(q.postfetch_filter)
    assert callable(q.looks_like_paywall)
    # Stage 3
    assert callable(q.dedup)
    # Stage 4
    assert callable(q.score_and_filter)
    assert q.RelevanceResult is not None
    assert q.RELEVANCE_DROP_THRESHOLD == 0.70
    # Stage 5
    assert callable(q.authority_rank)
    # Injection
    assert isinstance(q.INJECTION_PREAMBLE, str)
    assert callable(q.wrap_untrusted)
    # sources
    assert callable(q.source_id)
    assert callable(q.build_source_row)
    assert callable(q.upsert_source)
