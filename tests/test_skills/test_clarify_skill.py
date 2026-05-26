from tests.test_skills.validate import validate_skill


def test_clarify_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-0.5-clarify.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_clarify_has_default_proceed_and_cap(skills_dir):
    body = (skills_dir / "bad-research-0.5-clarify.md").read_text()
    assert "default" in body.lower() and "proceed" in body.lower()
    assert "3" in body  # max 3 questions
    assert "research/clarify.json" in body
    assert "triage" in body.lower()  # triage-tier model
