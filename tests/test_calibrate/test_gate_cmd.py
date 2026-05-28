"""E1 — `bad calibrate --gate` is the per-step regression gate.

Exits 0 when the golden corpus clears the floor, non-zero when it regresses. The
gate runs OFFLINE (no keys) over the golden corpus through the categorical judge.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_gate_exits_zero_on_the_passing_seed_corpus(tmp_path: Path):
    result = runner.invoke(app, ["calibrate", "--gate", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    # writes a corpus-level report, not the single-query one.
    rep = tmp_path / "golden-eval-report.json"
    assert rep.exists()
    data = json.loads(rep.read_text())
    assert "pass_rate" in data and "components" in data


def test_gate_exits_nonzero_when_corpus_dir_is_deliberately_failing(tmp_path: Path):
    # Point --golden-dir at a dir holding one broken (uncited, overclaiming) case.
    gdir = tmp_path / "broken_golden"
    gdir.mkdir()
    broken = {
        "id": "broken",
        "query": "Does coffee cure cancer?",
        "report": "# Does coffee cure cancer?\n\nCoffee definitively cures all cancers.\n",
        "corpus": [{"note_id": "1", "url": "https://a.edu", "text": "No causal link established."}],
        "expected_behavior": ["does NOT overclaim"],
        "axes_floor": {"citation": "pass", "factual": "pass"},
        "components": {},
    }
    (gdir / "broken.json").write_text(json.dumps(broken))
    result = runner.invoke(
        app, ["calibrate", "--gate", "--golden-dir", str(gdir), "--out", str(tmp_path)]
    )
    assert result.exit_code != 0, result.output


def test_gate_is_keyless(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["calibrate", "--gate", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_gate_json_output_carries_gate_ok_and_floor(tmp_path: Path):
    result = runner.invoke(
        app, ["calibrate", "--gate", "--out", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["gate_ok"] is True
    assert "floor" in payload["data"]
    assert "components" in payload["data"]


def test_gate_baseline_regression_trips_the_gate(tmp_path: Path):
    # A baseline above the seed corpus's pass-rate (1.01 > any rate) is a regression.
    result = runner.invoke(
        app, ["calibrate", "--gate", "--baseline", "1.01", "--out", str(tmp_path)]
    )
    assert result.exit_code != 0, result.output


def test_gate_respects_an_explicit_floor(tmp_path: Path):
    # The --floor exit code is a function of the floor, not hard-coded: a floor the
    # corpus clears -> exit 0; a floor above the corpus's pass-rate -> exit != 0.
    ok = runner.invoke(
        app, ["calibrate", "--gate", "--floor", "0.0", "--out", str(tmp_path)]
    )
    assert ok.exit_code == 0, ok.output
    strict = runner.invoke(
        app, ["calibrate", "--gate", "--floor", "1.01", "--out", str(tmp_path)]
    )
    assert strict.exit_code != 0, strict.output  # unreachable floor trips the gate


def test_gate_llm_flag_routes_to_llm_judge(tmp_path, monkeypatch):
    """E1-1: --llm flag must route evaluate_corpus to LLMJudge, not RubricJudge."""
    calls = []

    class TrackingJudge:
        def judge(self, query, report, corpus):
            calls.append("llm")
            from bad_research.calibrate.judge import AxisRails, JudgeRail, JudgeVerdict

            rails = AxisRails(
                factual=JudgeRail.PASS,
                citation=JudgeRail.PASS,
                completeness=JudgeRail.PASS,
                source_quality=JudgeRail.PASS,
                efficiency=JudgeRail.PASS,
            )
            return JudgeVerdict.from_rails(rails, rationale="tracking")

    monkeypatch.setattr(
        "bad_research.cli.calibrate._make_llm_judge",
        lambda: TrackingJudge(),
    )
    result = runner.invoke(app, ["calibrate", "--gate", "--llm", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(calls) > 0, "--llm flag must invoke LLMJudge path"


def test_gate_default_is_rubric_judge_not_llm(tmp_path, monkeypatch):
    """E1-1: default bad gate (no --llm) must not invoke LLMJudge."""
    monkeypatch.setattr(
        "bad_research.cli.calibrate._make_llm_judge",
        lambda: (_ for _ in ()).throw(
            AssertionError("LLMJudge must not be called without --llm")
        ),
    )
    # patch is a sentinel; if _make_llm_judge is called without --llm the test fails
    result = runner.invoke(app, ["calibrate", "--gate", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
