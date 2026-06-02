"""Tests for the recency converter + the dedup dating that activates it.

Levers #4: the previously-INERT freshness apparatus is now populated.
`compute_age_days` turns a hit's date signals into an age; `dedup` stamps that
age onto BOTH consumers (metadata['age_days'] for rank.py, published_days_ago
for the prefilter recency gate). All deterministic via an injected `today`.
"""

from __future__ import annotations

from datetime import date, datetime

from bad_research.funnel.dedup import Candidate, dedup
from bad_research.funnel.recency import compute_age_days, stamp_age
from tests.test_funnel.conftest import FakeWebResult

TODAY = date(2026, 6, 2)


# ---- compute_age_days (the converter) -------------------------------------

def test_age_from_year_anchors_to_jan_1():
    # year=2024 -> Jan 1 2024 anchor; today 2026-06-02.
    age = compute_age_days({"year": 2024}, today=TODAY)
    assert age == (TODAY - date(2024, 1, 1)).days


def test_age_from_string_year():
    assert compute_age_days({"year": "2024"}, today=TODAY) == (TODAY - date(2024, 1, 1)).days
    # "2024-03" style still yields the leading year
    assert compute_age_days({"year": "2024-03"}, today=TODAY) == (TODAY - date(2024, 1, 1)).days


def test_iso_published_date_wins_over_year():
    # An exact ISO date is more precise than the Jan-1 year anchor and is used.
    age = compute_age_days({"year": 2024}, today=TODAY, published_date="2024-12-31")
    assert age == (TODAY - date(2024, 12, 31)).days


def test_iso_datetime_with_tz_parses():
    age = compute_age_days({}, today=TODAY, published_date="2025-06-02T08:30:00Z")
    assert age == 365


def test_undatable_returns_none():
    assert compute_age_days({}, today=TODAY) is None
    assert compute_age_days({"year": None}, today=TODAY) is None
    assert compute_age_days({"year": "not-a-year"}, today=TODAY) is None


def test_future_date_clamps_to_zero():
    # A misdated future source never produces a negative age.
    assert compute_age_days({"year": 2099}, today=TODAY) == 0


def test_today_defaults_to_utc_when_omitted():
    # Determinism contract: omitting `today` is allowed (defaults to UTC now);
    # the result is still a sane non-negative int for a past year.
    age = compute_age_days({"year": 2000})
    assert isinstance(age, int) and age > 0


def test_datetime_today_is_accepted():
    age = compute_age_days({"year": 2025}, today=datetime(2026, 1, 1))
    assert age == (date(2026, 1, 1) - date(2025, 1, 1)).days


# ---- stamp_age (in-place, idempotent) -------------------------------------

def test_stamp_writes_age_days_in_place():
    meta: dict = {"year": 2024}
    stamp_age(meta, today=TODAY)
    assert meta["age_days"] == (TODAY - date(2024, 1, 1)).days


def test_stamp_is_idempotent_preserves_precise_value():
    # An already-stamped precise age must not be clobbered by a coarser recompute.
    meta: dict = {"year": 2024, "age_days": 100}
    out = stamp_age(meta, today=TODAY)
    assert out == 100 and meta["age_days"] == 100


# ---- dedup stamps BOTH consumers ------------------------------------------

def _hit(url, *, year=None, content="real body " * 50, provider="sonar"):
    meta = {"source": provider}
    if year is not None:
        meta["year"] = year
    return FakeWebResult(url=url, title=url, content=content,
                         serp_rank=1, serp_provider=provider, metadata=meta)


def test_dedup_stamps_both_age_days_and_published_days_ago():
    cands = dedup([_hit("https://blog.com/p", year=2024)], today=TODAY)
    c = cands[0]
    expected = (TODAY - date(2024, 1, 1)).days
    # rank.py reads result.metadata['age_days']; the gate reads published_days_ago.
    assert c.result.metadata["age_days"] == expected
    assert c.published_days_ago == expected


def test_dedup_undatable_hit_leaves_age_none():
    cands = dedup([_hit("https://blog.com/p")], today=TODAY)  # no year
    c = cands[0]
    assert c.result.metadata["age_days"] is None
    assert c.published_days_ago is None


def test_dedup_default_field_is_none_without_dating():
    # The new field defaults to None on a bare Candidate (no regression for callers
    # that construct Candidates directly).
    c = Candidate(canonical_url="https://x.com", result=FakeWebResult(url="https://x.com"))
    assert c.published_days_ago is None
