"""`bad doctor` — active-provider report, no network."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_doctor_runs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "anthropic" in result.output.lower()


def test_doctor_lists_keyless_providers(monkeypatch):
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["websearch"]["requires_key"] is False
    assert by_name["ddgs"]["requires_key"] is False


def test_doctor_searxng_always_keyless(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["searxng"]["requires_key"] is False


def test_doctor_includes_vault_path():
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    assert "vault_root" in data
    assert "model_tiers" in data
