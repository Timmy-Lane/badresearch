"""E3 — Light-route adversarial critic (ENHANCEMENT_PLAN E3, P2).

Separate-agent adversarial review beats in-context self-critique (Palantir/YC).
Today the 4 critics (`bad-research-12-critics.md`) run ONLY on `full`; the `light`
and `agentic-fast` routes skip straight to polish with NO adversarial pass.

E3 adds a SLIM single-critic variant for light/agentic-fast: one dialectic+instruction
critic over the final report (no 4-critic fan-out, NO patcher loop) whose findings the
light path applies inline / surfaces. The full-tier 4-critic path is UNCHANGED.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "src" / "bad_research" / "skills"


def _critics_skill() -> str:
    return (SKILLS_DIR / "bad-research-12-critics.md").read_text(encoding="utf-8")


# ── The light-critic agent is defined + registered for install ───────────────


def test_light_critic_agent_constant_defined():
    from bad_research.core import hooks

    assert hasattr(hooks, "LIGHT_CRITIC_AGENT")
    body = hooks.LIGHT_CRITIC_AGENT
    assert "bad-research-light-critic" in body
    # single critic over BOTH dimensions (dialectic counter-evidence + instruction
    # adherence) — the SLIM merge, not a 4-critic fan-out.
    low = body.lower()
    assert "dialectic" in low and "instruction" in low


def test_light_critic_installed_in_project_and_global(tmp_path, monkeypatch):
    from bad_research.core import hooks

    proj = tmp_path / "proj"
    proj.mkdir()
    hooks.install_hooks(proj, hpr_path="bad")
    assert (proj / ".claude" / "agents" / "bad-research-light-critic.md").exists()

    home = tmp_path / "home"
    home.mkdir()
    hooks.install_global_hooks(home, hpr_path="bad")
    assert (home / ".claude" / "agents" / "bad-research-light-critic.md").exists()


# ── The 12-critics skill gates a slim section to light/agentic-fast ──────────


def test_critics_skill_has_light_tier_slim_critic_section():
    body = _critics_skill()
    low = body.lower()
    # a section gated to the fast route (the slim single-critic path)
    assert "fast" in low
    # names the slim single critic agent
    assert "bad-research-light-critic" in body
    # ONE critic, not four — explicitly a single adversarial pass
    assert "single" in low or "one adversarial" in low or "slim" in low


def test_critics_skill_keeps_full_tier_four_critic_path():
    body = _critics_skill()
    # the full-tier critic fan-out must remain intact — now FIVE critics (B-1/B-2
    # added the assumption critic alongside the original four).
    for critic in (
        "bad-research-dialectic-critic",
        "bad-research-depth-critic",
        "bad-research-width-critic",
        "bad-research-instruction-critic",
        "bad-research-assumption-critic",
    ):
        assert critic in body
    # still spawns all 5 in parallel for full
    assert "5 critics" in body or "all 5" in body.lower()


# ── Critic-count guard: no shipped agent string says "four critic" ───────────
# Re-audit 2026-06: the full tier runs FIVE critics (dialectic/depth/width/
# instruction/assumption). Stale "four critic"/"four separate"/"4 critic" prose
# in the SHIPPED agent-prompt constants (the strings install_hooks writes into
# .claude/agents/) silently misrepresents the fan-out to the spawned critics.


def _shipped_agent_strings() -> dict[str, str]:
    """Every `*_AGENT` string constant in hooks — the prompts that ship to disk."""
    from bad_research.core import hooks

    return {
        name: getattr(hooks, name)
        for name in dir(hooks)
        if name.endswith("_AGENT") and isinstance(getattr(hooks, name), str)
    }


@pytest.mark.parametrize("banned", ["four critic", "4 critic", "four separate"])
def test_no_shipped_agent_string_says_four_critic(banned):
    offenders = [
        name
        for name, body in _shipped_agent_strings().items()
        if banned.lower() in body.lower()
    ]
    assert not offenders, (
        f"shipped agent constant(s) {offenders} contain stale '{banned}' — the full "
        "tier runs FIVE critics (dialectic/depth/width/instruction/assumption)"
    )


def test_hooks_module_docstring_says_five_critics():
    from bad_research.core import hooks

    doc = (hooks.__doc__ or "").lower()
    assert "four critic" not in doc and "four separate" not in doc
    assert "five critic" in doc


# ── The light/agentic-fast routes are wired through the critic before polish ──


@pytest.mark.parametrize(
    "skill_file",
    ["bad-research-10-triple-draft.md", "bad-research-fast.md"],
)
def test_light_and_fast_routes_reference_the_light_critic_before_polish(skill_file):
    # The full path (step 10 single-draft) and the fast route must invoke
    # the light critic (step 12 slim section) before handing off to polish (step 15).
    body = (SKILLS_DIR / skill_file).read_text(encoding="utf-8")
    assert "bad-research-12-critics" in body


def test_entry_skill_light_sequence_includes_critic():
    body = (SKILLS_DIR / "bad-research.md").read_text(encoding="utf-8")
    # The light route sequence in the entry skill now threads the slim critic (12)
    # between the draft (10) and polish (15).
    low = body.lower()
    assert "light-critic" in low or "slim critic" in low or "single adversarial critic" in low


# ── B-1: the 5th assumption critic agent is defined + registered for install ──


def test_assumption_critic_agent_constant_defined():
    from bad_research.core import hooks

    assert hasattr(hooks, "ASSUMPTION_CRITIC_AGENT")
    body = hooks.ASSUMPTION_CRITIC_AGENT
    assert "bad-research-assumption-critic" in body
    assert "model: opus" in body
    assert "assumption" in body.lower()
    assert "sub-assumption" in body.lower() or "constituent" in body.lower()


def test_assumption_critic_installed_in_project_and_global(tmp_path, monkeypatch):
    from bad_research.core import hooks

    proj = tmp_path / "proj"
    proj.mkdir()
    hooks.install_hooks(proj, hpr_path="bad")
    assert (proj / ".claude" / "agents" / "bad-research-assumption-critic.md").exists()

    home = tmp_path / "home"
    home.mkdir()
    hooks.install_global_hooks(home, hpr_path="bad")
    assert (home / ".claude" / "agents" / "bad-research-assumption-critic.md").exists()


# ── B-2: the 12-critics skill spawns the 5th critic; patcher consumes it ──────


def test_critics_skill_spawns_assumption_critic(skills_dir):
    body = (skills_dir / "bad-research-12-critics.md").read_text()
    assert "bad-research-assumption-critic" in body
    assert "critic-findings-assumption.json" in body
    # spawned in parallel with the other four (not a separate section)
    assert "assumption" in body.lower()


def test_critics_skill_exit_criterion_updated_for_five_critics(skills_dir):
    body = (skills_dir / "bad-research-12-critics.md").read_text()
    # exit criterion must reflect 5 findings files
    low = body.lower()
    assert "assumption" in low
    assert "5 critic" in low or "five critic" in low or "critic-findings-assumption" in low


def test_patcher_agent_reads_assumption_findings():
    from bad_research.core import hooks

    body = hooks.PATCHER_AGENT
    # patcher agent procedure must read assumption findings alongside the other four
    assert "assumption" in body.lower() or "critic-findings-assumption" in body
