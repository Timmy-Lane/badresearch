"""Tests for Stage-3 cross-source dedup (dossier 07 §3). No network."""

from __future__ import annotations

from bad_research.quality.dedup import dedup


def test_dedup_collapses_near_duplicates(near_dup_pair):
    a, b = near_dup_pair  # ~95% shingle overlap
    kept = dedup([a, b])
    assert len(kept) == 1


def test_dedup_keeps_distinct_docs(distinct_pair):
    a, b = distinct_pair
    kept = dedup([a, b])
    assert len(kept) == 2


def test_dedup_keeps_higher_tier_copy(near_dup_pair):
    a, b = near_dup_pair  # a is tier 'blog' (0.85), b is tier 'forum' (0.80)
    kept = dedup([a, b])
    # the higher-tier (blog > forum) survivor is kept
    assert kept[0].url == "https://a.example/transformer"


def test_dedup_skips_stubs_under_20_words():
    from datetime import UTC, datetime

    from bad_research.web.base import WebResult

    stub_a = WebResult(url="https://a/x", title="t", content="short stub one two",
                       fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    stub_b = WebResult(url="https://b/x", title="t", content="short stub one two",
                       fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    # both < 20 words -> not compared -> both kept (dedup.py:43 rule)
    assert len(dedup([stub_a, stub_b])) == 2


def test_dedup_empty_and_single():
    assert dedup([]) == []
    from datetime import UTC, datetime

    from bad_research.web.base import WebResult

    one = WebResult(url="https://a/x", title="t",
                    content="word " * 30, fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    assert len(dedup([one])) == 1
