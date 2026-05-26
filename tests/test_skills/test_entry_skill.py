from tests.test_skills.validate import validate_skill


def test_entry_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_entry_skill_has_three_route_sequences(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    for route in ("agentic-fast", "light", "full"):
        assert route in body
    assert "bad-research-0.5-clarify" in body
    assert "bad-research-query-router" in body
    assert "bad-research-agentic-fast" in body
    assert "bad-research-11.5-citation-verifier" in body
    assert "bad-research-fresh-review" in body
    # lazy step-skill install on first invocation
    assert "bad install --steps-only" in body
    # the deterministic ship gate
    assert "uncited" in body.lower()
