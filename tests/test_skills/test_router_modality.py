"""B-5 — Router modality factor: breadth alone must not force `full`.

The benchmark bug: `bad route` up-routed a "best tech stack" survey to `full`
purely because the decomposition had 17 atomic items, then ran the full
contradiction-graph/loci/depth machinery on what is a SURVEY (collect/compare).

These tests assert BOTH directions:
  - broad-but-shallow (many items, low contestedness, collect/compare/survey
    modality) routes `light`/`agentic-fast`, NEVER `full`;
  - genuinely contested/deep queries STILL route `full` (no over-correction).
"""
from __future__ import annotations

from bad_research.skills import routing_constants as R  # noqa: N812
from bad_research.skills.router import (
    classify_route,
    contestedness_score,
    detect_modality,
    route_reason,
)


def _decomp(**kw):
    base = dict(sub_questions=["q1"], entities=[], time_periods=[],
                response_format="structured", contradiction_terms=[], domains=["tech"])
    base.update(kw)
    return base


# ── new constants ─────────────────────────────────────────────────────────

def test_modality_constants_present_and_cited():
    # the broad-curation modalities that, when contestedness is low, defeat the
    # breadth-only full trigger
    assert R.BREADTH_MODALITIES == ("collect", "compare", "survey")
    # contestedness must clear this floor for breadth to escalate to full
    assert 0.0 < R.CONTESTEDNESS_FULL_FLOOR <= 1.0
    # a curation survey can run more atomic items in light before it MUST go full
    assert R.ROUTER_SURVEY_MAX_ATOMIC > R.ROUTER_LIGHT_MAX_ATOMIC


# ── detect_modality ─────────────────────────────────────────────────────────

def test_detect_modality_honours_explicit_field():
    assert detect_modality(_decomp(modality="compare")) == "compare"
    assert detect_modality(_decomp(modality="survey")) == "survey"


def test_detect_modality_infers_survey_from_best_x_phrasing():
    d = _decomp(sub_questions=["what is the best tech stack for a startup",
                               "which database scales best"],
                response_format="structured")
    assert detect_modality(d) in R.BREADTH_MODALITIES


def test_detect_modality_defaults_to_deep_when_no_curation_signal():
    d = _decomp(sub_questions=["analyze whether X caused Y"],
                response_format="argumentative")
    assert detect_modality(d) == "deep"


# ── contestedness_score ───────────────────────────────────────────────────

def test_contestedness_low_for_plain_survey():
    d = _decomp(sub_questions=[f"best option {i}" for i in range(17)],
                response_format="structured", contradiction_terms=[])
    assert contestedness_score(d) < R.CONTESTEDNESS_FULL_FLOOR


def test_contestedness_high_when_contradiction_terms_present():
    d = _decomp(contradiction_terms=["versus", "disputed"],
                response_format="argumentative")
    assert contestedness_score(d) >= R.CONTESTEDNESS_FULL_FLOOR


# ── DIRECTION 1: broad-but-shallow must NOT route full ──────────────────────

def test_broad_shallow_survey_routes_light_not_full():
    # the exact benchmark query class: 17 atomic items, survey modality, no
    # contradiction terms, single domain → must NOT pay for adversarial depth
    d = _decomp(
        sub_questions=[f"best tech for use-case {i}" for i in range(17)],
        entities=[], response_format="structured",
        contradiction_terms=[], domains=["tech"], modality="survey",
    )
    assert classify_route(d) == "light"


def test_broad_shallow_compare_many_items_routes_light():
    d = _decomp(
        sub_questions=[f"compare option {i}" for i in range(12)],
        response_format="structured", contradiction_terms=[],
        domains=["tech"], modality="compare",
    )
    assert classify_route(d) == "light"


# ── DIRECTION 2: contested/deep must STILL route full (no over-correction) ──

def test_contested_deep_still_routes_full_even_if_few_items():
    # few-but-deep + contradiction signals → adversarial dialectics still needed
    d = _decomp(
        sub_questions=["does remote work raise productivity"],
        response_format="argumentative", contradiction_terms=["disputed"],
        domains=["econ"], modality="deep",
    )
    assert classify_route(d) == "full"


def test_survey_modality_does_not_down_route_when_contested():
    # even a survey-shaped query, if it carries contradiction terms, keeps full
    d = _decomp(
        sub_questions=[f"compare framework {i}" for i in range(17)],
        response_format="structured", contradiction_terms=["versus"],
        domains=["tech"], modality="compare",
    )
    assert classify_route(d) == "full"


def test_time_periods_still_force_full_under_survey_modality():
    # Lens-D primaries are non-negotiable regardless of modality
    d = _decomp(
        sub_questions=[f"survey item {i}" for i in range(17)],
        response_format="structured", time_periods=[{"period": "Q3 2024"}],
        modality="survey",
    )
    assert classify_route(d) == "full"


def test_multi_domain_still_forces_full_under_survey_modality():
    d = _decomp(
        sub_questions=[f"survey item {i}" for i in range(17)],
        response_format="structured", domains=["bio", "finance", "law"],
        modality="survey",
    )
    assert classify_route(d) == "full"


def test_argumentative_format_still_forces_full_under_survey_modality():
    # an explicit argumentative format request beats a survey modality guess
    d = _decomp(
        sub_questions=[f"item {i}" for i in range(17)],
        response_format="argumentative", modality="survey",
    )
    assert classify_route(d) == "full"


# ── boundary: breadth WITHOUT a curation modality keeps the old behaviour ──

def test_breadth_without_curation_modality_still_routes_full():
    # no modality signal + many items + deep modality inference → unchanged full
    # (this protects test_effort_can_downgrade_full_to_light's invariant)
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(7)], entities=[],
        domains=["x"], response_format="structured",
    )
    # no "best/compare/list" phrasing, no explicit modality → defaults deep
    assert detect_modality(d) == "deep"
    assert classify_route(d) == "full"


def test_route_reason_mentions_modality_when_down_routed():
    d = _decomp(
        sub_questions=[f"best tool {i}" for i in range(17)],
        response_format="structured", modality="survey",
    )
    reason = route_reason(d).lower()
    assert "light" in reason
    assert "survey" in reason or "modality" in reason or "curation" in reason
