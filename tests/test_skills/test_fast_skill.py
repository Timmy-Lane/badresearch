from tests.test_skills.validate import validate_skill


def test_fast_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-fast.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_fast_has_loop_bounds_and_planner_writer(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    assert "max_steps" in body and "10" in body
    assert "300" in body and "15" in body  # Claude guards
    assert "planner" in body.lower() and "writer" in body.lower()
    assert "bad funnel-gather" in body or "funnel" in body.lower()
    assert "[N]" in body  # per-sentence single-index cites
