"""`bad calibrate <query>` emits both report files; offline path needs no keys."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_calibrate_offline_emits_both_reports(tmp_path: Path):
    result = runner.invoke(
        app,
        ["calibrate", "Does X cause Y?", "--offline", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "calibration-report.json").exists()
    assert (tmp_path / "calibration-report.md").exists()

    data = json.loads((tmp_path / "calibration-report.json").read_text())
    assert data["query"] == "Does X cause Y?"
    assert "bad" in data and "verdict" in data["bad"]


def test_calibrate_json_stdout(tmp_path: Path):
    result = runner.invoke(
        app,
        ["calibrate", "q", "--offline", "--out", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert "verdict" in payload["data"]["bad"]


def test_offline_calibrate_needs_zero_keys(tmp_path, monkeypatch):
    """The offline path must run with no provider env var set (conftest clears them)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        app, ["calibrate", "keyless?", "--offline", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "calibration-report.json").exists()


def test_available_baselines_is_keyless_clean(monkeypatch):
    """No keyed baseline (Perplexity/Grok) is offered, regardless of env keys."""
    monkeypatch.setenv("PPLX_API_KEY", "pplx-xxx")
    monkeypatch.setenv("XAI_API_KEY", "xai-xxx")
    from bad_research.calibrate import available_baselines

    names = {b.name for b in available_baselines()}
    assert "perplexity" not in names
    assert "grok" not in names
