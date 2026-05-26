import json

from bad_research.core.hooks import install_global_hooks


def test_global_install_drops_entry_skill(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    # entry skill lands at ~/.claude/skills/bad-research/SKILL.md
    entry = home / ".claude" / "skills" / "bad-research" / "SKILL.md"
    assert entry.exists()
    assert "name: bad-research" in entry.read_text(encoding="utf-8")


def test_global_install_drops_agents(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    agents = home / ".claude" / "agents"
    assert (agents / "bad-research-fresh-reviewer.md").exists()
    # the kept critics, renamed
    assert (agents / "bad-research-synthesizer.md").exists()


def test_global_install_skips_step_skills(tmp_path):
    # step skills must NOT install globally (system-reminder bloat) — lazy per-project
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    assert not (home / ".claude" / "skills" / "bad-research-1-decompose").exists()


def test_global_install_writes_pretooluse_hook(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    settings = home / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text(encoding="utf-8"))
    cmds = [h["command"] for entry in data["hooks"]["PreToolUse"] for h in entry["hooks"]]
    assert any("bad-research" in c for c in cmds)


def test_global_install_fresh_reviewer_is_read_locked(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    body = (home / ".claude" / "agents" / "bad-research-fresh-reviewer.md").read_text()
    assert "tools: Read" in body
    assert "name: bad-research-fresh-reviewer" in body
