from tests.test_skills.validate import validate_skill


def test_citation_verifier_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-11.5-citation-verifier.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_citation_verifier_names_dispositions_and_cli(skills_dir):
    body = (skills_dir / "bad-research-11.5-citation-verifier.md").read_text()
    for disp in ("supported", "partial", "unsupported", "contradicted"):
        assert disp in body
    assert "bad verify-citations" in body
    assert "claim_anchors" in body
    assert "[Read]" in body  # tool-lock


def test_citation_verifier_has_slim_fast_mode(skills_dir):
    body = (skills_dir / "bad-research-11.5-citation-verifier.md").read_text()
    assert "slim" in body.lower() and "fast" in body.lower()
    assert "Edit" in body  # slim mode applies dispositions inline (no step-14 patcher)
    assert "common knowledge" in body.lower()       # the OpenAI 3-tier cite exemption
    assert "DROP-CITE" in body or "ACCEPT" in body   # the grounding-score thresholds
