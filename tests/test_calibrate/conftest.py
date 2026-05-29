"""Calibration test fixtures: stub judge, stub LLM, a tiny report fixture."""

from __future__ import annotations

import json

import pytest

from bad_research.llm.base import LLMResponse


@pytest.fixture
def tiny_report() -> str:
    return (
        "# Does X cause Y?\n\n"
        "Evidence indicates X correlates with Y [1]. A controlled study found a 23% "
        "increase [2]. However, confounders remain unaddressed [1].\n"
    )


@pytest.fixture
def tiny_corpus() -> list[dict]:
    return [
        {"note_id": "note-1", "url": "https://a.edu/x", "text": "X correlates with Y in cohort data."},
        {"note_id": "note-2", "url": "https://b.org/y", "text": "A controlled study found a 23% increase."},
    ]


class StubLLM:
    """Returns a canned 5-axis JSON verdict; records the prompt for assertions.

    E2 — the verdict is categorical RAILS (pass|borderline|fail per axis), not
    0.0-1.0 floats."""

    name = "stub-llm"

    def __init__(self, verdict: dict | None = None):
        self.last_messages = None
        self.call_count = 0
        self._verdict = verdict or {
            "factual": "pass",
            "citation": "pass",
            "completeness": "pass",
            "source_quality": "borderline",
            "efficiency": "pass",
            "rationale": "well grounded",
        }

    def complete(
        self, messages, *, tier, tools=None, cache=False, max_tokens=4096, temperature=0.1
    ) -> LLMResponse:
        self.last_messages = messages
        self.call_count += 1
        return LLMResponse(
            text=json.dumps(self._verdict),
            tool_calls=[],
            usage={"input_tokens": 1200, "output_tokens": 180},
            model="stub",
        )


@pytest.fixture
def stub_llm() -> StubLLM:
    return StubLLM()


# ── E1-3: deterministic LLMJudge stubs for the two adversarial fixtures ────────
# These make the LLMJudge side of the gap-proof tests deterministic WITHOUT a live
# model: a StubLLM whose canned JSON verdict fails exactly the axis the real host
# model would fail on each adversarial fixture. LLMJudge.judge() calls
# provider.complete(...) -> StubLLM returns json.dumps(verdict) -> _extract_json
# parses it -> AxisRails.from_raw coerces the rails. No keys, no network.
@pytest.fixture
def stub_llm_fail_factual() -> StubLLM:
    """StubLLM that returns factual=fail (all others pass) — models LLMJudge
    correctly identifying a cited-but-contradicting claim (fixture 09)."""
    return StubLLM(
        verdict={
            "factual": "fail",
            "citation": "pass",
            "completeness": "pass",
            "source_quality": "pass",
            "efficiency": "pass",
            "rationale": "report inverts the causal direction of its cited sources",
        }
    )


@pytest.fixture
def stub_llm_fail_completeness() -> StubLLM:
    """StubLLM that returns completeness=fail — models LLMJudge detecting the
    over-hedged evasion (fixture 10)."""
    return StubLLM(
        verdict={
            "factual": "pass",
            "citation": "pass",
            "completeness": "fail",
            "source_quality": "pass",
            "efficiency": "pass",
            "rationale": "answer technically present but buried in hedge; corpus provides clear enumeration",
        }
    )
