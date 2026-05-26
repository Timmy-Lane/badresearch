from bad_research.core.hooks import install_hooks


def test_project_install_drops_all_step_skills(tmp_path):
    root = tmp_path / "proj"
    (root / ".bad-research").mkdir(parents=True)  # vault marker
    install_hooks(root, hpr_path="bad")
    skills = root / ".claude" / "skills"
    assert (skills / "bad-research-1-decompose" / "SKILL.md").exists()
    assert (skills / "bad-research-agentic-fast" / "SKILL.md").exists()
    assert (skills / "bad-research" / "SKILL.md").exists()  # entry skill too


def test_project_install_includes_new_step_skills(tmp_path):
    root = tmp_path / "proj"
    (root / ".bad-research").mkdir(parents=True)
    install_hooks(root, hpr_path="bad")
    skills = root / ".claude" / "skills"
    for name in (
        "bad-research-0.5-clarify",
        "bad-research-query-router",
        "bad-research-11.5-citation-verifier",
        "bad-research-fresh-review",
    ):
        assert (skills / name / "SKILL.md").exists(), name


def test_project_install_writes_fresh_reviewer_agent(tmp_path):
    root = tmp_path / "proj"
    (root / ".bad-research").mkdir(parents=True)
    install_hooks(root, hpr_path="bad")
    assert (root / ".claude" / "agents" / "bad-research-fresh-reviewer.md").exists()
