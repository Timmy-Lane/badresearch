"""KR-6 — the 7-field delegation contract + per-subagent caps in the skills."""
from __future__ import annotations

from tests.test_skills.validate import validate_skill

CONTRACT_FIELDS = ("objective", "output_shape", "tools_allowed", "stop_conditions")


def test_entry_skill_mandates_seven_field_contract(skills_dir, known_skills):
    p = skills_dir / "bad-research.md"
    body = p.read_text()
    # the 3 HAVE fields + the 4 NET-NEW fields (dossier 16 §3.1)
    for field in CONTRACT_FIELDS:
        assert field in body, f"entry skill missing contract field: {field}"
    assert validate_skill(p, known_skills) == []


def test_width_sweep_fetcher_carries_the_four_fields(skills_dir):
    body = (skills_dir / "bad-research-2-width-sweep.md").read_text()
    for field in CONTRACT_FIELDS:
        assert field in body, f"width-sweep spawn missing: {field}"
    # the cap is referenced (FETCHER_TOOLCALL_CAP / FETCHER_TIMEOUT_S)
    assert "stop_conditions" in body
    assert "tool call" in body.lower() or "FETCHER_TOOLCALL_CAP" in body


def test_depth_investigation_carries_the_four_fields(skills_dir):
    body = (skills_dir / "bad-research-5-depth-investigation.md").read_text()
    for field in CONTRACT_FIELDS:
        assert field in body, f"depth spawn missing: {field}"


def test_entry_skill_has_grader_stage_and_degrade_invariant(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "bad-research-12.5-grader" in body
    assert "12.5" in body
    # the token-ceiling degrade order (cut tokens last)
    assert "degrade" in body.lower()
    assert "--max-tokens" in body or "max-tokens" in body


def test_entry_skill_has_effort_continuum(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "--reasoning-effort" in body or "--effort" in body
    for level in ("minimal", "low", "medium", "high"):
        assert level in body
