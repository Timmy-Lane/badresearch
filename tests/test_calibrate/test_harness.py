"""End-to-end harness on a fixture: mocked runner + mocked judge → CalibrationReport."""

from __future__ import annotations

import json

from bad_research.calibrate.constants import JUDGE_AXES
from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.harness import (
    BadRunOutput,
    CalibrationReport,
    run_calibration,
)
from bad_research.calibrate.judge import StubJudge


def _fake_runner(query: str) -> BadRunOutput:
    meter = CostMeter()
    meter.record(
        stage="synthesize",
        tier="heavy",
        input_tokens=8000,
        output_tokens=4000,
        citation_tokens=200,
        search_queries=15,
    )
    return BadRunOutput(
        report=f"# {query}\n\nA grounded claim [1].\n",
        corpus=[{"note_id": "n1", "url": "https://a.edu", "text": "supporting evidence"}],
        cost=meter,
    )


def test_run_calibration_offline():
    judge = StubJudge(scores={a: 0.88 for a in JUDGE_AXES})
    report = run_calibration(
        "Does X cause Y?",
        runner=_fake_runner,
        baselines=[],  # offline: no external baselines
        judge=judge,
    )
    assert isinstance(report, CalibrationReport)
    assert report.query == "Does X cause Y?"
    assert report.bad.verdict.passed is True
    assert report.bad.cost_usd > 0
    assert report.baselines == []  # none available


def test_calibration_report_json_roundtrip():
    judge = StubJudge(scores={a: 0.8 for a in JUDGE_AXES})
    report = run_calibration("q", runner=_fake_runner, baselines=[], judge=judge)
    blob = report.to_json()
    data = json.loads(blob)
    assert data["query"] == "q"
    assert "bad" in data and "verdict" in data["bad"] and "cost" in data["bad"]
    assert set(data["bad"]["verdict"]["scores"].keys()) == set(JUDGE_AXES)


def test_calibration_report_markdown():
    judge = StubJudge(scores={a: 0.8 for a in JUDGE_AXES})
    md = run_calibration("q", runner=_fake_runner, baselines=[], judge=judge).to_markdown()
    assert "# Calibration Report" in md
    assert "factual" in md
    assert "$" in md  # cost line rendered


def test_baseline_comparison_when_available():
    """A baseline whose .run() succeeds is judged and a delta is computed."""
    from bad_research.calibrate.baselines import BaselineResult

    class FakeBaseline:
        name = "fake"

        def available(self):
            return True

        def run(self, query):
            return BaselineResult(
                name="fake",
                report=f"# {query}\n\nweaker claim.\n",
                corpus=[{"note_id": "b1", "url": "x", "text": "y"}],
            )

    # judge scores the baseline lower than bad-research
    class TieredJudge:
        def judge(self, query, report, corpus):
            score = 0.9 if "grounded" in report or "[1]" in report else 0.6
            from bad_research.calibrate.judge import AxisScores, JudgeVerdict

            return JudgeVerdict.from_scores(
                AxisScores.from_raw({a: score for a in JUDGE_AXES}), rationale="t"
            )

    report = run_calibration(
        "q", runner=_fake_runner, baselines=[FakeBaseline()], judge=TieredJudge()
    )
    assert len(report.baselines) == 1
    b = report.baselines[0]
    assert b.name == "fake"
    # bad-research scored higher → positive delta in its favor.
    assert report.bad.verdict.overall - b.verdict.overall > 0
    assert (
        abs(report.delta_vs("fake") - (report.bad.verdict.overall - b.verdict.overall)) < 1e-9
    )
