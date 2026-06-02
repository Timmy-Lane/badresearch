"""Tests for grounding.recall_harness — the honest, keyless, LLM-free recall harness.

These assert the HONEST contract: number/negation/antonym/unsupported-append are
AFFIRMATIVELY caught keyless; the paraphrase-contradiction band is NOT (it is
escalate-only, disclosed, and excluded from the regression floor). No LLM is used.
"""

from __future__ import annotations

from bad_research.grounding.recall_harness import (
    DETERMINISTIC_CATCHABLE,
    REGRESSION_FLOOR,
    GroundedClaim,
    Mutation,
    affirmatively_caught,
    build_cases,
    builtin_fixtures,
    escalated_only,
    format_report_text,
    run_recall,
)


def test_builtin_fixtures_are_grounded_and_accepted():
    # Each unmutated grounded pair should be ACCEPTED keyless: neither affirmatively
    # caught nor escalated (no false-positive on genuine near-verbatim support).
    for gc in builtin_fixtures():
        assert not affirmatively_caught(gc.claim, gc.quote)
        assert not escalated_only(gc.claim, gc.quote)


def test_deterministic_bands_have_full_affirmative_catch():
    report = run_recall(builtin_fixtures())
    for r in report.per_mutation:
        if r.deterministic_band:
            assert r.n_applied > 0
            assert r.n_affirmed == r.n_applied, f"{r.mutation} not fully caught"
            assert r.affirmed_rate == 1.0


def test_paraphrase_band_is_disclosed_uncaught_and_escalate_only():
    report = run_recall(builtin_fixtures())
    para = next(r for r in report.per_mutation if r.mutation == Mutation.PARAPHRASE_CONTRADICTION)
    # The honest core: affirmative catch is 0, the band is escalate-only.
    assert para.deterministic_band is False
    assert para.n_affirmed == 0
    assert para.affirmed_rate == 0.0
    assert para.n_escalated == para.n_applied
    assert Mutation.PARAPHRASE_CONTRADICTION not in DETERMINISTIC_CATCHABLE


def test_regression_floor_holds_on_deterministic_bands_only():
    report = run_recall(builtin_fixtures())
    # The floor is over the deterministic bands; the paraphrase band can't drag it down.
    assert report.deterministic_catch_rate() >= REGRESSION_FLOOR


def test_number_flip_is_caught_by_numeric_mismatch():
    gc = GroundedClaim("Sales grew 10 percent.", "Sales grew 10 percent last year.")
    cases = [c for c in build_cases([gc]) if c.mutation == Mutation.NUMBER_FLIP and c.applied]
    assert cases, "number flip should apply"
    assert affirmatively_caught(cases[0].mutated_claim, gc.quote)


def test_to_dict_reports_disclosure_and_split_columns():
    d = run_recall(builtin_fixtures()).to_dict()
    assert "DISCLOSED UNCAUGHT BAND" in d["disclosure"]
    assert d["deterministic_catch_rate"] == 1.0
    rows = {r["mutation"]: r for r in d["per_mutation"]}
    assert rows["paraphrase_contradiction"]["affirmed_catch_rate"] == 0.0
    assert rows["paraphrase_contradiction"]["escalated_only_rate"] == 1.0
    assert rows["number_flip"]["affirmed_catch_rate"] == 1.0


def test_format_report_text_mentions_disclosure_and_pass():
    txt = format_report_text(run_recall(builtin_fixtures()))
    assert "DISCLOSED uncaught band" in txt
    assert "PASS" in txt
    assert "paraphrase_contradiction" in txt


def test_harness_uses_no_llm():
    # The harness signatures take no provider; run_recall must work with no LLM wired.
    report = run_recall(builtin_fixtures())
    assert report.n_grounded_total == len(builtin_fixtures())
