from tests.test_skills.validate import validate_skill


def test_decompose_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-1-decompose.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_decompose_emits_scope_brief(skills_dir):
    body = (skills_dir / "bad-research-1-decompose.md").read_text()
    assert "scope_brief" in body  # one-paragraph framing for the fast writer
