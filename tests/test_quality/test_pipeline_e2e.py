"""End-to-end Stage 1-5 composition (dossier 07 §7.1). No network."""

from __future__ import annotations

from datetime import UTC, datetime

import bad_research.quality as q
from bad_research.web.base import WebResult

from .conftest import FakeReranker


def _fetch(candidate: q.Candidate) -> WebResult:
    """Stand-in fetcher: produces a substantive WebResult from a candidate."""
    body = f"In-depth content for {candidate.url}. " * 60
    return WebResult(url=candidate.url, title=candidate.title or "Doc", content=body,
                     fetched_at=datetime(2026, 5, 26, tzinfo=UTC))


def test_full_pipeline_drops_farm_keeps_primary_and_orders_by_authority():
    candidates = [
        q.Candidate(url="https://deals.example/best-vpns-2026-review",
                    snippet="The 15 best VPNs in 2026 — top deals", title="best vpns"),
        q.Candidate(url="https://www.sec.gov/edgar/aapl-10k",
                    snippet="Annual report under the Securities Exchange Act", title="10-K"),
        q.Candidate(url="https://docs.python.org/3/library/asyncio.html",
                    snippet="asyncio documentation", title="asyncio docs"),
    ]

    # STAGE 1 — pre-fetch
    kept = q.prefetch_filter(candidates, query="vpn", max_age_days=None)
    assert not any("best-vpns" in c.url for c in kept)   # farm dropped
    assert kept[0].url == "https://www.sec.gov/edgar/aapl-10k"  # primary first

    # STAGE 2 — fetch + content filter
    fetched = [q.postfetch_filter(_fetch(c)) for c in kept]
    fetched = [r for r in fetched if r is not None]
    assert len(fetched) == 2

    # STAGE 3 — dedup (these two are distinct -> both survive)
    deduped = q.dedup(fetched)
    assert len(deduped) == 2

    # STAGE 4 — relevance (both score high)
    rr = FakeReranker([0.92, 0.88])
    rel = q.score_and_filter("apple 10-k asyncio", deduped, rr, rounds_remaining=2)
    assert rel.should_reretrieve is False
    assert len(rel.kept) == 2

    # STAGE 5 — authority rank: primary (1.30) outranks docs (1.15) on close scores
    ranked = q.authority_rank(rel.kept)
    assert ranked[0].url == "https://www.sec.gov/edgar/aapl-10k"

    # INJECTION — wrap any survivor before it touches an LLM
    wrapped = q.wrap_untrusted(ranked[0].content, source_url=ranked[0].url)
    assert wrapped.startswith(q.INJECTION_PREAMBLE)


def test_thin_corpus_triggers_reretrieve():
    candidates = [q.Candidate(url=f"https://blog.example/post-{i}", snippet="x")
                  for i in range(5)]
    fetched = [q.postfetch_filter(_fetch(c)) for c in candidates]
    fetched = [r for r in fetched if r is not None]
    rr = FakeReranker([0.9] + [0.1] * 4)  # only 1/5 passes -> <30% -> re-retrieve
    rel = q.score_and_filter("q", fetched, rr, rounds_remaining=2)
    assert rel.should_reretrieve is True
