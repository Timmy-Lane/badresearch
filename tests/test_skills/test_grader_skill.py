"""KR-6 — structural validator for the new grader-loop skill (dossier 16 §4.1)."""
from __future__ import annotations

from tests.test_skills.validate import validate_skill


def test_grader_skill_is_structurally_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-12.5-grader.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_grader_skill_runs_the_loop_with_cap_3(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "MAX_GRADER_REVISIONS" in body
    assert "bad grade-report" in body
    assert "full" in body.lower()  # full-tier only
    # the judge->patch->re-judge loop shape
    assert "re-judge" in body.lower() or "re-grade" in body.lower()
    # it does NOT run on light/agentic-fast (anti-overkill, dossier §4.1)
    assert "agentic-fast" in body and "light" in body


def test_grader_skill_feeds_findings_to_patcher(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "critic-findings-grader.json" in body
    assert "bad-research-14-patcher" in body


# ── B-3: grader history failure ledger + round >= 2 escalation clause ──


def test_grader_skill_accumulates_grader_history(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "grader_history" in body
    assert "round" in body.lower()
    assert "failed_axes" in body or "still_failing" in body


def test_grader_skill_injects_escalation_clause_on_round_2(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    low = body.lower()
    # escalation clause injected into patcher spawn on round >= 2
    assert "escalat" in low
    assert "round" in low
    # the "repeat same fix" anti-pattern is explicitly forbidden
    assert "same" in low and ("fix" in low or "patch" in low)
    # structural escalation instruction present
    assert "structural" in low and ("section" in low or "addition" in low)
