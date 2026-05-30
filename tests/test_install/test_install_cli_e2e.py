from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_bad_install_default_is_global(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    res = runner.invoke(app, ["install", "--json"])
    assert res.exit_code == 0, res.output
    assert (home / ".claude" / "skills" / "bad-research" / "SKILL.md").exists()
    # step skills NOT global
    assert not (home / ".claude" / "skills" / "bad-research-1-decompose").exists()


def test_bad_install_steps_only(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    res = runner.invoke(app, ["install", str(proj), "--steps-only", "--json"])
    assert res.exit_code == 0, res.output
    assert (proj / ".claude" / "skills" / "bad-research-1-decompose" / "SKILL.md").exists()


def test_bad_install_project(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / ".bad-research").mkdir(parents=True)
    res = runner.invoke(app, ["install", str(proj), "--project", "--json"])
    assert res.exit_code == 0, res.output
    assert (proj / ".claude" / "skills" / "bad-research" / "SKILL.md").exists()
    assert (proj / ".claude" / "skills" / "bad-research-fast" / "SKILL.md").exists()
