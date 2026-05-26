"""Judge: StubJudge determinism + LLMJudge prompt/parse against a stub provider."""

from __future__ import annotations

from bad_research.calibrate.constants import JUDGE_AXES
from bad_research.calibrate.judge import (
    AxisScores,
    JudgeVerdict,
    LLMJudge,
    StubJudge,
)

from tests.test_calibrate.conftest import StubLLM


def test_stub_judge_is_deterministic(tiny_report, tiny_corpus):
    j = StubJudge(scores={a: 0.9 for a in JUDGE_AXES})
    v1 = j.judge("q", tiny_report, tiny_corpus)
    v2 = j.judge("q", tiny_report, tiny_corpus)
    assert v1.overall == v2.overall
    assert v1.passed is True


def test_verdict_pass_logic():
    high = AxisScores(
        factual=0.9, citation=0.9, completeness=0.9, source_quality=0.9, efficiency=0.9
    )
    v = JudgeVerdict.from_scores(high, rationale="ok")
    assert v.passed is True
    assert abs(v.overall - 0.9) < 1e-9

    low = AxisScores(
        factual=0.9, citation=0.5, completeness=0.9, source_quality=0.9, efficiency=0.9
    )  # citation below per-axis floor
    v2 = JudgeVerdict.from_scores(low, rationale="weak cites")
    assert v2.passed is False


def test_llm_judge_single_call_and_parse(stub_llm, tiny_report, tiny_corpus):
    j = LLMJudge(provider=stub_llm)
    v = j.judge("Does X cause Y?", tiny_report, tiny_corpus)
    # exactly one provider call; all five axes present.
    assert stub_llm.call_count == 1
    assert stub_llm.last_messages is not None
    assert set(v.scores.as_dict().keys()) == set(JUDGE_AXES)
    assert 0.0 <= v.overall <= 1.0
    # the corpus + query are in the prompt the judge sent.
    sent = "".join(m.content for m in stub_llm.last_messages if isinstance(m.content, str))
    assert "Does X cause Y?" in sent
    assert "note-1" in sent


def test_llm_judge_clamps_out_of_range(tiny_report, tiny_corpus):
    bad = StubLLM(
        verdict={
            "factual": 1.4,
            "citation": -0.2,
            "completeness": 0.8,
            "source_quality": 0.8,
            "efficiency": 0.8,
            "rationale": "x",
        }
    )
    v = LLMJudge(provider=bad).judge("q", tiny_report, tiny_corpus)
    assert 0.0 <= v.scores.factual <= 1.0
    assert 0.0 <= v.scores.citation <= 1.0
