from tests.test_skills.validate import validate_skill


def test_router_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-query-router.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_router_skill_names_two_routes_and_cli(skills_dir):
    body = (skills_dir / "bad-research-query-router.md").read_text()
    for route in ("fast", "full"):
        assert route in body
    assert "bad route" in body  # invokes the deterministic CLI heuristic
    assert "prompt-decomposition.json" in body
