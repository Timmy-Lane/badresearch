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
