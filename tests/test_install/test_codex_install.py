"""Codex install tests: layout, frontmatter validity, roster-completeness
(derived from the LIVE source, never hardcoded), translation-leak lint, and
idempotency.

NEVER writes the real ~/.codex — every test monkeypatches HOME to tmp_path or
passes an explicit tmp home.
"""

import re

from bad_research.core import hooks
from bad_research.core.codex_install import (
    AGENT_FILES,
    build_agent_files,
    ensure_multi_agent,
    inject_codex_agents_md,
    install_codex,
    read_codex_asset,
    write_codex_skill,
    write_openai_yaml,
)
from bad_research.core.codex_translate import skillref_path


# --- live roster derivation (NOT hardcoded) ---------------------------------

def _live_step_count() -> int:
    return len(hooks._BAD_RESEARCH_STEP_SKILLS)


def _live_agent_count() -> int:
    """Count the _AGENT prompt constants the Claude installer actually installs.

    Derived from the install loop in hooks.py (the `_install_*_agent(home, ...)`
    calls), so this tracks the real roster rather than a frozen number.
    """
    src = (hooks.__file__,)
    text = open(src[0], encoding="utf-8").read()
    calls = re.findall(r"_install_\w+_agent\(home", text)
    return len(calls)


# --- agent roster -----------------------------------------------------------

def test_agent_files_match_live_constant_count():
    assert len(AGENT_FILES) == _live_agent_count()


def test_agent_files_have_no_leftover_placeholder():
    for name, body in AGENT_FILES.items():
        assert "{hpr_path}" not in body, name
        assert "{scaffold_only_sections}" not in body, name


def test_agent_files_include_assumption_and_recommender():
    # The assumption critic (the spec's stale roster omitted it) and the
    # readability recommender (named differently from the historical
    # "reformatter") must both be present.
    assert "assumption-critic.md" in AGENT_FILES
    assert "readability-recommender.md" in AGENT_FILES
    assert "fetcher.md" in AGENT_FILES
    assert "fresh-reviewer.md" in AGENT_FILES


def test_read_codex_asset_loads_router_preamble():
    text = read_codex_asset("router-preamble.md")
    assert "Execution model on Codex" in text


# --- skill dir layout -------------------------------------------------------

def test_write_codex_skill_lays_out_dir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    assert (root / "SKILL.md").exists()
    # a sample step reference + the fast-route reference
    assert (root / "references" / "5-depth-investigation.md").exists()
    assert (root / "references" / "fast.md").exists()
    # sample agent references
    assert (root / "references" / "agents" / "fetcher.md").exists()
    assert (root / "references" / "agents" / "patcher.md").exists()
    # static asset
    assert (root / "references" / "dispatch-table.md").exists()


def test_all_step_references_present_match_live_count(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    for skill_name in hooks._BAD_RESEARCH_STEP_SKILLS:
        assert (root / skillref_path(skill_name)).exists(), skill_name
    # exactly len(roster) step references (excluding the agents/ subdir + static)
    refs = root / "references"
    step_files = [p for p in refs.glob("*.md") if p.name != "dispatch-table.md"]
    assert len(step_files) == _live_step_count()


def test_all_agent_references_present_match_live_count(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    agents = home / ".codex" / "skills" / "bad-research" / "references" / "agents"
    agent_files = list(agents.glob("*.md"))
    assert len(agent_files) == _live_agent_count()
    for name in build_agent_files("bad"):
        assert (agents / name).exists(), name


def test_skill_md_frontmatter_is_codex_valid(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    fm = (home / ".codex" / "skills" / "bad-research" / "SKILL.md").read_text(encoding="utf-8")
    head = fm.split("---\n")[1]  # first frontmatter block
    keys = [ln.split(":")[0].strip() for ln in head.splitlines() if ":" in ln]
    assert set(keys) <= {"name", "description"}
    assert "Execution model on Codex" in fm  # preamble prepended


def test_step_references_have_no_frontmatter(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    txt = (
        home / ".codex" / "skills" / "bad-research" / "references" / "1-decompose.md"
    ).read_text(encoding="utf-8")
    assert not txt.lstrip().startswith("---")


# --- openai.yaml + AGENTS.md + config ---------------------------------------

def test_write_openai_yaml(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_openai_yaml(home)
    y = (
        home / ".codex" / "skills" / "bad-research" / "agents" / "openai.yaml"
    ).read_text(encoding="utf-8")
    assert "display_name:" in y
    assert "default_prompt:" in y


def test_inject_agents_md_creates_marker_section(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    inject_codex_agents_md(home, hpr_path="bad")
    txt = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    assert "bad-research:start" in txt
    assert "bad-research:end" in txt
    assert "bad fetch" in txt


def test_inject_agents_md_preserves_existing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "AGENTS.md").write_text("# My notes\nkeep me\n", encoding="utf-8")
    inject_codex_agents_md(home, hpr_path="bad")
    txt = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    assert "keep me" in txt
    assert "bad-research:start" in txt


def test_inject_agents_md_no_duplicate_on_rerun(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    inject_codex_agents_md(home, hpr_path="bad")
    second = inject_codex_agents_md(home, hpr_path="bad")
    assert second == []  # nothing changed
    txt = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    assert txt.count("bad-research:start") == 1


def test_ensure_multi_agent_adds_flag(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    ensure_multi_agent(home)
    cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[features]" in cfg
    assert "multi_agent = true" in cfg
    assert 'model = "gpt-5.5"' in cfg  # preserved


def test_ensure_multi_agent_inserts_under_existing_features(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    cfg_path = home / ".codex" / "config.toml"
    cfg_path.write_text("[features]\nother = true\n", encoding="utf-8")
    ensure_multi_agent(home)
    cfg = cfg_path.read_text(encoding="utf-8")
    assert "multi_agent = true" in cfg
    assert "other = true" in cfg
    assert cfg.count("[features]") == 1


def test_ensure_multi_agent_idempotent(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    cfg_path = home / ".codex" / "config.toml"
    cfg_path.write_text("[features]\nmulti_agent = true\n", encoding="utf-8")
    assert ensure_multi_agent(home) is None  # no change


# --- full install + idempotency + leak lint ---------------------------------

def test_install_codex_full(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    actions = install_codex(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    assert (root / "SKILL.md").exists()
    assert (root / "agents" / "openai.yaml").exists()
    assert (home / ".codex" / "AGENTS.md").exists()
    cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "multi_agent = true" in cfg
    assert len(actions) > 0


def test_install_codex_idempotent(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_codex(home, hpr_path="bad")
    second = install_codex(home, hpr_path="bad")
    assert second == []  # nothing changed on second run


def test_install_codex_via_home_default(tmp_path, monkeypatch):
    # Defensive: even the no-arg path must hit the monkeypatched HOME, never the
    # real ~/.codex.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    install_codex(hpr_path="bad")
    assert (home / ".codex" / "skills" / "bad-research" / "SKILL.md").exists()


_FORBIDDEN = ("Skill(", "Task(", "TodoWrite", "subagent_type", ".claude/")


def test_no_claude_tokens_leak_into_codex_render(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_codex(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    offenders = []
    for f in root.rglob("*.md"):
        text = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN:
            if tok in text:
                offenders.append(f"{f.relative_to(root)}: {tok}")
    assert not offenders, "Claude tokens leaked:\n" + "\n".join(offenders)
