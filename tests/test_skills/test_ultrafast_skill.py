from tests.test_skills.validate import validate_skill


def test_ultrafast_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-ultrafast.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_ultrafast_is_lead_plus_parallel_researchers(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "ULTRAFAST_SUBRESEARCHER_K" in body
    assert "ULTRAFAST_MIN_SOURCES_PER_SUBQ" in body
    assert "bad-research-fetcher" in body            # the parallel sub-researcher
    assert "seven-piece" in body.lower() or "seven-field" in body.lower()
    assert "parallel" in body.lower()
    assert "leader-only" in body.lower() or "only writer" in body.lower()
    assert "[N]" in body                             # per-sentence single-index cites


def test_ultrafast_is_autonomous_and_bounded(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "autonomous" in body.lower()
    assert "ULTRAFAST_TIMEOUT_S" in body             # 15-min wall-clock net
    assert "ultrafast" in body.lower()               # the route gate


def test_ultrafast_runs_slim_grounding_before_gate(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "verify-citations" in body
    assert "uncited" in body.lower()


def test_entry_skill_wires_ultrafast_route(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "bad-research-ultrafast" in body
    assert "--ultrafast" in body          # explicit-only selection documented
    # the fetcher cap prose is updated to include the ultrafast key
    assert '"ultrafast":15' in body or '"ultrafast": 15' in body


def test_query_router_routes_ultrafast(skills_dir):
    body = (skills_dir / "bad-research-query-router.md").read_text()
    assert "--ultrafast" in body
    assert "bad-research-ultrafast" in body
