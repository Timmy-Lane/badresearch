from tests.test_skills.validate import validate_skill


def test_every_skill_validates(skills_dir, known_skills):
    errors = []
    for p in sorted(skills_dir.glob("bad-research*.md")):
        errors += validate_skill(p, known_skills)
    assert errors == [], "\n".join(errors)


def test_every_step_skill_in_roster_has_a_file(skills_dir):
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS

    for name in _BAD_RESEARCH_STEP_SKILLS:
        assert (skills_dir / f"{name}.md").exists(), f"missing skill file for {name}"


def test_step_skill_roster_is_exactly_18_full_tier_stages():
    """Post-merge (C-1/C-2/C-3): the full-tier stage roster must contain exactly 18
    invocable stages (excludes bad-research-fast, which is its own route, not
    a full-tier step). The real roster is 19 entries; 19 - fast = 18.

    NOTE: the C-6 plan asserted 17, but the actual `_BAD_RESEARCH_STEP_SKILLS` roster
    (counting the half-steps 0.5 / 1.5 / 1.6 / 11.5 that the plan's arithmetic omitted)
    is 18 after the three merges. 18 is the verified count.
    """
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS

    full_tier_steps = [s for s in _BAD_RESEARCH_STEP_SKILLS
                       if s != "bad-research-fast"]
    removed = {
        "bad-research-3-contradiction-graph",
        "bad-research-7-source-tensions",
        "bad-research-9-evidence-digest",
    }
    for name in removed:
        assert name not in full_tier_steps, f"{name} must be removed (C-1/C-2/C-3)"
    assert len(full_tier_steps) == 18, \
        f"Expected 18 full-tier stages, got {len(full_tier_steps)}: {full_tier_steps}"
