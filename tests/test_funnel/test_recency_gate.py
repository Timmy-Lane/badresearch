"""Tests for the recency gate now WIRED into the funnel orchestrator (lever #4).

`quality/prefilter.py::passes_recency_gate` was orphaned (zero callers). It is
now called from `funnel/orchestrator.py::recency_gate` (Stage B.5), driven by
the query's `recency_max_age_days` window. These tests prove the gate fires:
stale non-primary candidates are dropped, primaries are exempt, undatable hits
pass, and evergreen (None) is a no-op — end-to-end through `gather`.
"""

from __future__ import annotations

from datetime import date

from bad_research.funnel.dedup import dedup
from bad_research.funnel.orchestrator import FunnelDeps, gather, recency_gate
from bad_research.quality.prefilter import RECENCY_MAX_AGE_DAYS
from tests.test_funnel.conftest import (
    FakeFetcher,
    FakeProvider,
    FakeRetrievalEngine,
    FakeVault,
    FakeWebResult,
    fake_postfetch_filter,
)

TODAY = date(2026, 6, 2)


def _hit(url, *, year=None, provider="sonar"):
    meta = {"source": provider}
    if year is not None:
        meta["year"] = year
    return FakeWebResult(url=url, title=url, content="real body " * 60,
                         serp_rank=1, serp_provider=provider, metadata=meta)


# ---- recency_gate unit (operates on dated funnel Candidates) --------------

def test_gate_drops_stale_nonprimary_under_breaking():
    cands = dedup([_hit("https://blog.com/old", year=2020)], today=TODAY)
    kept = recency_gate(cands, max_age_days=RECENCY_MAX_AGE_DAYS["breaking"])  # 7
    assert kept == []


def test_gate_keeps_fresh_under_breaking():
    cands = dedup([_hit("https://blog.com/new", year=2026)], today=date(2026, 1, 3))
    kept = recency_gate(cands, max_age_days=RECENCY_MAX_AGE_DAYS["breaking"])  # 7 days
    assert len(kept) == 1


def test_gate_exempts_primary_even_when_stale():
    # A 2019 SEC filing is primary -> never recency-dropped (the existing rule).
    cands = dedup([_hit("https://sec.gov/filing", year=2019)], today=TODAY)
    kept = recency_gate(cands, max_age_days=RECENCY_MAX_AGE_DAYS["breaking"])
    assert len(kept) == 1


def test_gate_passes_undatable_hit():
    cands = dedup([_hit("https://blog.com/nodate")], today=TODAY)  # no year -> None age
    kept = recency_gate(cands, max_age_days=RECENCY_MAX_AGE_DAYS["current"])
    assert len(kept) == 1


def test_evergreen_window_is_noop():
    cands = dedup([_hit("https://blog.com/old", year=2000)], today=TODAY)
    kept = recency_gate(cands, max_age_days=RECENCY_MAX_AGE_DAYS["evergreen"])  # None
    assert len(kept) == 1


def test_current_window_drops_older_than_180d_keeps_within():
    old = dedup([_hit("https://blog.com/old", year=2024)], today=TODAY)
    recent = dedup([_hit("https://blog.com/recent", year=2026)], today=date(2026, 3, 1))
    assert recency_gate(old, max_age_days=180) == []
    assert len(recency_gate(recent, max_age_days=180)) == 1


# ---- end-to-end through gather --------------------------------------------

class DatedProvider(FakeProvider):
    """Returns one stale (2019) blog hit and one fresh (2026) blog hit.

    Bodies are DISTINCT so Stage-2 content-hash dedup keeps both (identical
    bodies would collapse to one and mask the gate's effect).
    """

    async def search_ex(self, q):
        self.calls.append(q.query)
        return [
            FakeWebResult(url="https://stale.blog/x", title="old take",
                          content="stale story body " * 80, serp_rank=1,
                          serp_provider=self.name,
                          metadata={"year": 2019, "source": self.name}),
            FakeWebResult(url="https://fresh.blog/y", title="new take",
                          content="fresh story body " * 80, serp_rank=2,
                          serp_provider=self.name,
                          metadata={"year": 2026, "source": self.name}),
        ]


def _deps(provider):
    return FunnelDeps(
        providers=[provider],
        fetcher=FakeFetcher(),
        postfetch_filter=fake_postfetch_filter,
        vault=FakeVault(),
        retrieval=FakeRetrievalEngine(),
    )


async def test_gather_breaking_window_drops_stale_blog_only_fresh_read():
    fetcher = FakeFetcher()
    deps = FunnelDeps(providers=[DatedProvider("sonar")], fetcher=fetcher,
                      postfetch_filter=fake_postfetch_filter, vault=FakeVault(),
                      retrieval=FakeRetrievalEngine())
    await gather("topic", mode="full", deps=deps,
                 recency_max_age_days=RECENCY_MAX_AGE_DAYS["breaking"],
                 today=date(2026, 1, 3))
    # the 2019 blog is stale-dropped before the read; the 2026 one survives.
    assert "https://stale.blog/x" not in fetcher.read_urls
    assert "https://fresh.blog/y" in fetcher.read_urls


async def test_gather_no_window_reads_both_stale_and_fresh():
    fetcher = FakeFetcher()
    deps = FunnelDeps(providers=[DatedProvider("sonar")], fetcher=fetcher,
                      postfetch_filter=fake_postfetch_filter, vault=FakeVault(),
                      retrieval=FakeRetrievalEngine())
    # No recency window (evergreen default): the gate is a no-op, both are read.
    await gather("topic", mode="full", deps=deps, today=TODAY)
    assert "https://stale.blog/x" in fetcher.read_urls
    assert "https://fresh.blog/y" in fetcher.read_urls
