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
