from tests.test_skills.validate import validate_skill


def test_fresh_review_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-fresh-review.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_fresh_review_is_single_pass_and_read_only(skills_dir):
    body = (skills_dir / "bad-research-fresh-review.md").read_text()
    assert "single pass" in body.lower() or "one pass" in body.lower()
    assert "not a loop" in body.lower()
    assert "fresh" in body.lower()  # fresh-context reviewer
    assert "research/temp/fresh-review.json" in body
