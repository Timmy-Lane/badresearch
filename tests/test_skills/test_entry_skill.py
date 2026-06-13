from tests.test_skills.validate import validate_skill


def test_entry_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_entry_skill_has_two_route_sequences(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    for route in ("fast", "full"):
        assert route in body
    assert "bad-research-0.5-clarify" in body
    assert "bad-research-query-router" in body
    assert "bad-research-fast" in body
    assert "bad-research-11.5-citation-verifier" in body
    assert "bad-research-fresh-review" in body
    # lazy step-skill install on first invocation
    assert "bad install --steps-only" in body
    # the deterministic ship gate
    assert "uncited" in body.lower()


def test_entry_skill_bootstrap_uses_bad_not_bare_hyperresearch(skills_dir):
    # issue #12: the bootstrap called bare `hyperresearch archive-run` / `vault-tag`,
    # which exits 127 on a uv-tool install where only `bad` is on PATH. The whole
    # skill must invoke the CLI as `bad …` consistently (the installer also documents
    # the absolute path in CLAUDE.md for the not-on-PATH case).
    import re
    body = (skills_dir / "bad-research.md").read_text()
    bare = re.findall(r"hyperresearch [a-z][a-z-]+", body)
    assert bare == [], f"entry skill invokes bare `hyperresearch <cmd>` (use `bad`): {bare}"
    # the bootstrap names the real commands via `bad`
    assert "bad archive-run" in body
    assert "bad vault-tag" in body
