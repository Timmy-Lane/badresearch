"""`bad doctor` — keyless capability report, no network, no key checks."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_doctor_runs_keyless():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "keyless" in out  # the keyless-by-default banner
    assert "anthropic-host" in out  # the host-model row


def test_doctor_reports_external_clis():
    result = runner.invoke(app, ["doctor"])
    out = result.output.lower()
    # The 4 driven CLIs appear by name.
    for cli in ("agent-browser", "lightpanda", "yt-dlp", "git"):
        assert cli in out, f"doctor did not report external CLI: {cli}"


def test_doctor_silent_on_searxng():
    result = runner.invoke(app, ["doctor"])
    assert "searxng" not in result.output.lower()


def test_doctor_shows_install_hint_for_absent_cli(monkeypatch):
    # Force every external CLI to look absent so the hint must render.
    import bad_research.providers as prov

    monkeypatch.setattr(prov.shutil, "which", lambda _name: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "agent-browser install" in result.output  # the hint string


def test_doctor_json_is_keyless_surface():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["keyless"] is True
    # Every provider row is keyless.
    assert all(p["requires_key"] is False for p in data["providers"])
    # The external-CLI block is present and SearXNG-free.
    names = {c["name"] for c in data["external_clis"]}
    assert {"agent-browser", "lightpanda", "yt-dlp", "git"} <= names
    assert "searxng" not in {n.lower() for n in names}


def test_doctor_includes_vault_and_local_lines():
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    assert "vault_root" in data
    assert "model_tiers" in data
    assert "local_installed" in data  # the [local] neural-stack presence flag
