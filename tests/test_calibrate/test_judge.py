"""Judge: StubJudge determinism + LLMJudge prompt/parse against a stub provider.

E2 — the judge contract is CATEGORICAL RAILS (pass|borderline|fail per axis), not
0.0-1.0 floats. See test_judge_rails.py for the rail-specific acceptance tests."""

from __future__ import annotations

from bad_research.calibrate.constants import JUDGE_AXES
from bad_research.calibrate.judge import (
    AxisRails,
    JudgeRail,
    JudgeVerdict,
    LLMJudge,
    StubJudge,
)
from tests.test_calibrate.conftest import StubLLM


def test_judge_tier_is_work():
    """D-1: JUDGE_TIER must be 'work' — the code comment endorses Sonnet for categorical rails."""
    from bad_research.calibrate.constants import JUDGE_TIER
    assert JUDGE_TIER == "work", (
        f"JUDGE_TIER is '{JUDGE_TIER}'; change constants.py:23 to 'work' "
        "(Sonnet acceptable per the code comment — saves ~$0.55/run)"
    )


def test_stub_judge_is_deterministic(tiny_report, tiny_corpus):
    j = StubJudge(rails={a: "pass" for a in JUDGE_AXES})
    v1 = j.judge("q", tiny_report, tiny_corpus)
    v2 = j.judge("q", tiny_report, tiny_corpus)
    assert v1.pass_rate == v2.pass_rate
    assert v1.passed is True


def test_verdict_pass_logic():
    high = AxisRails(
        factual=JudgeRail.PASS,
        citation=JudgeRail.PASS,
        completeness=JudgeRail.PASS,
        source_quality=JudgeRail.PASS,
        efficiency=JudgeRail.PASS,
    )
    v = JudgeVerdict.from_rails(high, rationale="ok")
    assert v.passed is True
    assert abs(v.pass_rate - 1.0) < 1e-9

    # a single hard fail on the citation axis sinks the verdict.
    low = AxisRails(
        factual=JudgeRail.PASS,
        citation=JudgeRail.FAIL,
        completeness=JudgeRail.PASS,
        source_quality=JudgeRail.PASS,
        efficiency=JudgeRail.PASS,
    )
    v2 = JudgeVerdict.from_rails(low, rationale="weak cites")
    assert v2.passed is False


def test_llm_judge_single_call_and_parse(stub_llm, tiny_report, tiny_corpus):
    j = LLMJudge(provider=stub_llm)
    v = j.judge("Does X cause Y?", tiny_report, tiny_corpus)
    # exactly one provider call; all five axes present as rails.
    assert stub_llm.call_count == 1
    assert stub_llm.last_messages is not None
    assert set(v.rails.as_dict().keys()) == set(JUDGE_AXES)
    assert 0.0 <= v.pass_rate <= 1.0
    # the corpus + query are in the prompt the judge sent.
    sent = "".join(m.content for m in stub_llm.last_messages if isinstance(m.content, str))
    assert "Does X cause Y?" in sent
    assert "note-1" in sent


def test_llm_judge_coerces_garbage_rail_to_fail(tiny_report, tiny_corpus):
    bad = StubLLM(
        verdict={
            "factual": "amazing",  # not a rail -> FAIL
            "citation": "fail",
            "completeness": "pass",
            "source_quality": "pass",
            "efficiency": "pass",
            "rationale": "x",
        }
    )
    v = LLMJudge(provider=bad).judge("q", tiny_report, tiny_corpus)
    assert v.rails.factual is JudgeRail.FAIL
    assert v.rails.citation is JudgeRail.FAIL
    assert v.passed is False
