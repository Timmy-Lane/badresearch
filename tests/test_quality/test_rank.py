"""Tests for Stage-5 source-authority ranking (dossier 07 §5)."""

from __future__ import annotations

from datetime import UTC, datetime

from bad_research.quality.rank import authority_rank
from bad_research.web.base import WebResult


def _wr(url: str, score: float) -> WebResult:
    r = WebResult(url=url, title="t", content="body " * 40,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    r.metadata["relevance_score"] = score
    return r


def test_primary_outranks_higher_scored_blog():
    # blog 0.90 * 0.85 = 0.765 ; primary 0.80 * 1.30 = 1.040 -> primary first
    blog = _wr("https://blog.example/post", 0.90)
    primary = _wr("https://www.sec.gov/filing", 0.80)
    ranked = authority_rank([blog, primary])
    assert ranked[0].url == "https://www.sec.gov/filing"


def test_authority_score_stamped_in_metadata():
    primary = _wr("https://www.sec.gov/filing", 0.80)
    ranked = authority_rank([primary])
    assert abs(ranked[0].metadata["authority_score"] - 1.04) < 1e-9


def test_ordering_matches_dossier_chain_on_equal_relevance():
    # all relevance 0.50 -> ordering follows tier multipliers
    urls = [
        "https://forum.example/x",          # blog (default) 0.85 — but make it forum:
        "https://news.ycombinator.com/i",   # forum 0.80
        "https://docs.python.org/3/",       # docs 1.15
        "https://www.reuters.com/x",        # news_tier1 1.00
        "https://arxiv.org/abs/1",          # reference 1.10
        "https://www.sec.gov/x",            # primary 1.30
    ]
    results = [_wr(u, 0.50) for u in urls]
    ranked = authority_rank(results)
    order = [r.url for r in ranked]
    # primary > docs > reference > news > (blog/forum) tail
    assert order[0] == "https://www.sec.gov/x"
    assert order[1] == "https://docs.python.org/3/"
    assert order[2] == "https://arxiv.org/abs/1"
    assert order[3] == "https://www.reuters.com/x"


def test_missing_relevance_score_treated_as_zero():
    r = WebResult(url="https://www.sec.gov/x", title="t", content="b " * 40,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))  # no relevance_score
    ranked = authority_rank([r])
    assert ranked[0].metadata["authority_score"] == 0.0
