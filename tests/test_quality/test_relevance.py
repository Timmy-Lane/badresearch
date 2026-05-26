"""Tests for Stage-4 relevance thresholding + re-retrieve signal (dossier 07 §4)."""

from __future__ import annotations

from datetime import UTC, datetime

from bad_research.quality.relevance import (
    RELEVANCE_DROP_THRESHOLD,
    RERETRIEVE_PASS_FRACTION,
    RelevanceResult,
    score_and_filter,
)
from bad_research.web.base import WebResult


def _docs(n: int) -> list[WebResult]:
    return [WebResult(url=f"https://x/{i}", title=f"t{i}", content=f"body {i} " * 50,
                      fetched_at=datetime(2026, 5, 26, tzinfo=UTC)) for i in range(n)]


def test_constants_frozen():
    assert RELEVANCE_DROP_THRESHOLD == 0.70
    assert RERETRIEVE_PASS_FRACTION == 0.30


def test_drops_below_070_keeps_above(fake_reranker_factory):
    docs = _docs(4)
    rr = fake_reranker_factory([0.95, 0.80, 0.50, 0.10])  # 2 pass, 2 fail
    res = score_and_filter("q", docs, rr, rounds_remaining=2)
    assert isinstance(res, RelevanceResult)
    assert len(res.kept) == 2
    assert res.pass_fraction == 0.5
    assert res.should_reretrieve is False  # 50% >= 30%


def test_reretrieve_signal_when_under_30pct(fake_reranker_factory):
    docs = _docs(5)
    rr = fake_reranker_factory([0.90, 0.10, 0.10, 0.10, 0.10])  # 1/5 = 20% pass
    res = score_and_filter("q", docs, rr, rounds_remaining=2)
    assert len(res.kept) == 1
    assert res.pass_fraction == 0.2
    assert res.should_reretrieve is True


def test_no_reretrieve_when_rounds_exhausted(fake_reranker_factory):
    docs = _docs(5)
    rr = fake_reranker_factory([0.90, 0.10, 0.10, 0.10, 0.10])  # 20% pass
    res = score_and_filter("q", docs, rr, rounds_remaining=0)
    assert res.should_reretrieve is False  # no rounds left


def test_kept_are_score_sorted_desc(fake_reranker_factory):
    docs = _docs(3)
    rr = fake_reranker_factory([0.72, 0.99, 0.85])
    res = score_and_filter("q", docs, rr, rounds_remaining=2)
    scores = [r.metadata["relevance_score"] for r in res.kept]
    assert scores == sorted(scores, reverse=True)


def test_empty_input_signals_reretrieve(fake_reranker_factory):
    rr = fake_reranker_factory([])
    res = score_and_filter("q", [], rr, rounds_remaining=2)
    assert res.kept == []
    assert res.pass_fraction == 0.0
    assert res.should_reretrieve is True
