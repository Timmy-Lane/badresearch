"""E2 — categorical-rails judge (Arize: words not numbers).

The offline 5-axis judge must return a categorical RAIL per axis
(`pass | borderline | fail`), NOT a raw float. Rails map to a pass-rate for
reporting. A clearly-good report -> all `pass`; a clearly-bad -> `fail`s. The
offline StubJudge path stays deterministic + keyless.
"""

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


def test_rail_enum_is_categorical_not_numeric():
    # The rail set is the Arize-style categorical vocabulary, not a 0.0-1.0 score.
    assert {r.value for r in JudgeRail} == {"pass", "borderline", "fail"}


def test_verdict_carries_rails_not_floats():
    rails = AxisRails.from_raw({a: "pass" for a in JUDGE_AXES})
    v = JudgeVerdict.from_rails(rails, rationale="ok")
    d = v.to_dict()
    # Each axis value is a categorical rail string, never a float.
    for axis in JUDGE_AXES:
        assert d["rails"][axis] in {"pass", "borderline", "fail"}
        assert not isinstance(d["rails"][axis], float)
    assert v.passed is True


def test_all_pass_rails_pass():
    rails = AxisRails.from_raw({a: "pass" for a in JUDGE_AXES})
    v = JudgeVerdict.from_rails(rails, rationale="clearly good")
    assert v.passed is True
    assert v.pass_rate == 1.0


def test_any_fail_rail_fails_the_verdict():
    raw = {a: "pass" for a in JUDGE_AXES}
    raw["citation"] = "fail"  # one hard fail sinks the verdict
    v = JudgeVerdict.from_rails(AxisRails.from_raw(raw), rationale="bad cite")
    assert v.passed is False
    assert v.pass_rate < 1.0


def test_borderline_band_maps_to_half_credit():
    raw = {a: "borderline" for a in JUDGE_AXES}
    v = JudgeVerdict.from_rails(AxisRails.from_raw(raw), rationale="meh")
    # borderline = 0.5 credit; 5 axes all borderline => pass_rate 0.5
    assert v.pass_rate == 0.5
    # all-borderline is NOT a pass (below the pass-rate floor).
    assert v.passed is False


def test_unknown_rail_token_degrades_to_fail():
    # A hallucinated/garbage rail token must read as fail, never crash.
    rails = AxisRails.from_raw({a: "excellent" for a in JUDGE_AXES})
    assert all(r is JudgeRail.FAIL for r in rails.as_dict().values())


def test_stub_judge_is_deterministic_and_keyless(tiny_report, tiny_corpus):
    j = StubJudge(rails={a: "pass" for a in JUDGE_AXES})
    v1 = j.judge("q", tiny_report, tiny_corpus)
    v2 = j.judge("q", tiny_report, tiny_corpus)
    assert v1.pass_rate == v2.pass_rate
    assert v1.passed is True


def test_llm_judge_returns_rails_from_a_clearly_good_report(tiny_report, tiny_corpus):
    good = StubLLM(verdict={a: "pass" for a in JUDGE_AXES} | {"rationale": "solid"})
    v = LLMJudge(provider=good).judge("Does X cause Y?", tiny_report, tiny_corpus)
    assert good.call_count == 1  # single strong-model call, not an ensemble
    assert v.passed is True
    assert set(v.rails.as_dict().keys()) == set(JUDGE_AXES)


def test_llm_judge_fails_a_clearly_bad_report(tiny_report, tiny_corpus):
    bad = StubLLM(
        verdict={
            "factual": "fail",
            "citation": "fail",
            "completeness": "fail",
            "source_quality": "borderline",
            "efficiency": "pass",
            "rationale": "fabricated, uncited",
        }
    )
    v = LLMJudge(provider=bad).judge("q", tiny_report, tiny_corpus)
    assert v.passed is False


def test_llm_judge_tolerates_garbage_and_does_not_throw(tiny_report, tiny_corpus):
    junk = StubLLM(verdict={"oops": "not the schema"})
    v = LLMJudge(provider=junk).judge("q", tiny_report, tiny_corpus)
    # missing axes default to fail; never a float, never a crash.
    assert v.passed is False
    assert set(v.rails.as_dict().keys()) == set(JUDGE_AXES)
