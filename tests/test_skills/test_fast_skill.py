from tests.test_skills.validate import validate_skill


def test_fast_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-fast.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_fast_has_loop_bounds_and_planner_writer(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    assert "FAST_MAX_STEPS" in body and "6" in body
    assert "600" in body                            # FAST_TIMEOUT_S wall-clock guard
    assert "planner" in body.lower() and "writer" in body.lower()
    assert "bad funnel-gather" in body or "funnel" in body.lower()
    assert "[N]" in body                            # per-sentence single-index cites
    assert "breadth" in body.lower()                # shape-aware fan-out
    assert "bad-research-fetcher" in body           # the parallel sub-researcher


def test_fast_has_auditable_stop_rule(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    assert "research_complete" in body              # keyless convergence flag
    assert "distinct domain" in body.lower()        # the new-domains novelty proxy
    assert "FAST_MIN_NEW_DOMAINS" in body and "FAST_MIN_SOURCES_PER_SUBQ" in body
    assert "checklist" in body.lower()              # per-sub-question coverage
