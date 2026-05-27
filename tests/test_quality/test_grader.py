"""KR-6 — the in-pipeline grader. Wraps LLMJudge to emit patcher-shaped Findings
and provides the judge->findings translation the 12.5 loop runs. dossier 16 §4."""
from __future__ import annotations

import json

from bad_research.llm.base import LLMResponse
from bad_research.quality.grader import GRADER_FINDINGS_CLAUSE, Grader


class FakeLLM:
    """Returns a scripted judge JSON (axes + findings); records messages + calls."""

    name = "fake-llm"

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls = 0
        self.last_messages = None

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1) -> LLMResponse:
        self.calls += 1
        self.last_messages = messages
        return LLMResponse(text=json.dumps(self._payload), usage={}, model="fake")


CORPUS = [{"note_id": "n1", "url": "https://a.edu", "text": "X correlates with Y."}]
REPORT = "# Q\n\nX correlates with Y [1].\n"


def test_grader_passing_verdict_has_no_findings():
    payload = {"factual": "pass", "citation": "pass", "completeness": "pass",
               "source_quality": "pass", "efficiency": "pass", "rationale": "good",
               "findings": []}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is True
    assert verdict.findings == []


def test_grader_failing_verdict_emits_patcher_shaped_findings():
    payload = {
        "factual": "fail", "citation": "pass", "completeness": "fail",
        "source_quality": "pass", "efficiency": "pass", "rationale": "thin coverage",
        "findings": [
            {"axis": "completeness", "severity": "critical", "failure_mode": "missing",
             "location": "## Limitations", "recommendation": "Add the funding-bias angle."},
            {"axis": "factual", "severity": "major", "failure_mode": "miscited",
             "location": "X correlates with Y [1].", "recommendation": "Soften to 'suggests'."},
        ],
    }
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is False
    assert len(verdict.findings) == 2
    f0 = verdict.findings[0]
    # patcher-shaped: failure_mode / severity / location / recommendation
    assert f0.failure_mode == "missing"
    assert f0.severity == "critical"
    assert f0.location == "## Limitations"
    assert f0.recommendation.startswith("Add")


def test_grade_prompt_appends_the_findings_clause():
    g = Grader(provider=FakeLLM({"factual": "pass", "citation": "pass",
                                 "completeness": "pass", "source_quality": "pass",
                                 "efficiency": "pass", "findings": []}))
    g.grade("Q", REPORT, CORPUS)
    sys_msg = next(m for m in g.provider.last_messages if m.role == "system")
    assert GRADER_FINDINGS_CLAUSE in sys_msg.content


def test_malformed_findings_degrade_to_empty_not_crash():
    payload = {"factual": "borderline", "citation": "borderline", "completeness": "borderline",
               "source_quality": "borderline", "efficiency": "borderline",
               "findings": "oops-not-a-list"}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is False  # all-borderline is below the pass-rate floor
    assert verdict.findings == []   # bad findings -> empty, no exception


def test_findings_as_dicts_round_trip_to_json():
    payload = {"factual": "fail", "citation": "pass", "completeness": "pass",
               "source_quality": "pass", "efficiency": "pass",
               "findings": [{"axis": "factual", "severity": "major",
                             "failure_mode": "miscited", "location": "s", "recommendation": "r"}]}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    d = verdict.to_dict()
    assert d["passed"] is False
    assert d["findings"][0]["failure_mode"] == "miscited"
    json.dumps(d)  # serializable for the CLI envelope
