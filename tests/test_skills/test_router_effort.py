"""KR-6 — routing_constants loop caps + the effort continuum."""
from __future__ import annotations

from bad_research.skills import routing_constants as R


def test_grader_and_cap_constants_present_and_frozen():
    # dossier 16 §3.2 / §4.1 / INTERFACES_KEYLESS §8 frozen table
    assert R.MAX_GRADER_REVISIONS == 3
    assert R.FETCHER_TOOLCALL_CAP == {"light": 10, "full": 20}
    assert R.FETCHER_TIMEOUT_S == 300
    assert R.INVESTIGATOR_TIMEOUT_S == 900
    assert R.SUBAGENT_SOURCE_KILL == 100


def test_effort_levels_are_the_openai_four():
    assert R.EFFORT_LEVELS == ("minimal", "low", "medium", "high")
    # every level maps to a route + a fetcher fan-out cap (dossier 16 §6.1)
    for lvl in R.EFFORT_LEVELS:
        assert lvl in R.EFFORT_MAP
        row = R.EFFORT_MAP[lvl]
        assert row["route"] in ("light", "full")
        assert isinstance(row["fetchers_max"], int)
        assert isinstance(row["loci_max"], int)
        assert row["tier"] in ("triage", "work", "heavy", "default")


def test_effort_monotonic_fanout():
    # minimal <= low <= medium <= high on fetcher width (the cost knob)
    widths = [R.EFFORT_MAP[l]["fetchers_max"] for l in R.EFFORT_LEVELS]
    assert widths == sorted(widths)


from bad_research.skills.router import classify_route, degrade_order, effort_overrides


def test_effort_overrides_minimal_forces_light_single_draft():
    ov = effort_overrides("minimal")
    assert ov["route"] == "light"
    assert ov["fetchers_max"] == 4
    assert ov["single_draft"] is True


def test_effort_overrides_high_forces_full_opus():
    ov = effort_overrides("high")
    assert ov["route"] == "full"
    assert ov["tier"] == "heavy"
    assert ov["fetchers_max"] == 12
    assert ov["loci_max"] == 6


def test_effort_overrides_unknown_returns_none():
    # an absent/invalid --effort leaves the auto-route untouched
    assert effort_overrides(None) is None
    assert effort_overrides("turbo") is None


def test_effort_can_downgrade_full_to_light():
    # auto-classify would say full (7 atomic items), but --effort minimal pins light
    decomp = {"sub_questions": list(range(7)), "entities": [], "domains": ["x"],
              "response_format": "structured"}
    assert classify_route(decomp) == "full"
    ov = effort_overrides("minimal")
    assert ov["route"] == "light"  # the override is the user's explicit floor/ceiling


def test_degrade_order_is_tokens_last():
    order = degrade_order()
    assert order[0] == "tool-call-redundancy"
    assert order[-1] == "model-tier"  # tokens/synthesis never appear — cut last (never)
    assert "synthesis" not in order and "grounding-tokens" not in order
