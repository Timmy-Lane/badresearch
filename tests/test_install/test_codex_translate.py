"""Unit tests for the Codex translation layer (codex_translate.py)."""

import yaml

from bad_research.core.codex_translate import (
    agentref_path,
    skillref_path,
    strip_frontmatter,
    to_codex_skill_frontmatter,
    translate_tool_vocabulary,
)


def test_skillref_path_strips_prefix_and_adds_references():
    assert skillref_path("bad-research-5-depth-investigation") == "references/5-depth-investigation.md"
    assert skillref_path("bad-research-0.5-clarify") == "references/0.5-clarify.md"
    assert skillref_path("bad-research-query-router") == "references/query-router.md"


def test_agentref_path_strips_prefix_into_agents_dir():
    assert agentref_path("bad-research-fetcher") == "references/agents/fetcher.md"
    assert agentref_path("bad-research-readability-recommender") == "references/agents/readability-recommender.md"


def test_translate_rewrites_skill_calls_to_reference_reads():
    src = 'Run a step: Skill(skill: "bad-research-5-depth-investigation")'
    out = translate_tool_vocabulary(src)
    assert "Skill(" not in out
    assert "references/5-depth-investigation.md" in out


def test_translate_rewrites_subagent_type_to_agent_reference():
    src = "Task(\n  subagent_type: bad-research-fetcher\n  prompt: ...\n)"
    out = translate_tool_vocabulary(src)
    assert "Task(" not in out
    assert "subagent_type" not in out
    assert "spawn_agent(" in out
    assert "agent: references/agents/fetcher.md" in out


def test_translate_rewrites_task_and_todowrite_and_subagent_prose():
    src = "Use the Task tool; seed the TodoWrite list; pass subagent_type."
    out = translate_tool_vocabulary(src)
    assert "Task" not in out.replace("spawn_agent", "")
    assert "TodoWrite" not in out
    assert "subagent_type" not in out
    assert "spawn_agent" in out
    assert "update_plan" in out


def test_translate_rewrites_claude_paths():
    src = "Check .claude/skills/bad-research-1-decompose/SKILL.md and .claude/agents/x.md"
    out = translate_tool_vocabulary(src)
    assert ".claude/" not in out
    assert "references/" in out


def test_translate_routes_claude_skill_path_through_skillref():
    # The `.claude/skills/bad-research-<step>/SKILL.md` install path must land on
    # the REAL rendered reference (`references/<step>.md`), NOT the dangling
    # `references/bad-research-<step>/SKILL.md` the bare literal would yield.
    src = "If `.claude/skills/bad-research-1-decompose/SKILL.md` doesn't exist, run X."
    out = translate_tool_vocabulary(src)
    assert "references/1-decompose.md" in out
    assert "references/bad-research-1-decompose" not in out
    assert "/SKILL.md" not in out  # no leftover dangling dir/file path


def test_translate_entry_self_reinvoke_points_at_skill_md():
    # `Skill(skill: "bad-research")` (no step segment) is the entry skill itself
    # -> this skill's own SKILL.md, never a dangling references/bad-research.md.
    src = 'Re-invoke entirely: Skill(skill: "bad-research").'
    out = translate_tool_vocabulary(src)
    assert "Skill(" not in out
    assert "references/bad-research.md" not in out
    assert "SKILL.md" in out


def test_translate_strips_pretooluse_and_slash_command_and_steps_only():
    src = (
        "ships the entry skill + agents + PreToolUse hook; materialize on first "
        "`/bad-research` invocation, run `bad install --steps-only . --json`."
    )
    out = translate_tool_vocabulary(src)
    assert "PreToolUse" not in out
    assert "/bad-research" not in out
    assert "--steps-only" not in out


def test_translate_no_dangling_bad_research_ref_paths():
    # The exact line that leaked all three before the fix.
    src = (
        "If `.claude/skills/bad-research-1-decompose/SKILL.md` doesn't exist, run "
        "`bad install --steps-only . --json`. Ships entry + agents + PreToolUse "
        "hook; first `/bad-research` invocation. Re-invoke: "
        'Skill(skill: "bad-research").'
    )
    out = translate_tool_vocabulary(src)
    assert "references/bad-research" not in out  # no dangling step or self path
    for tok in ("PreToolUse", "/bad-research", "--steps-only", ".claude/", "Skill("):
        assert tok not in out, tok


def test_translate_is_idempotent():
    src = (
        'Skill(skill: "bad-research-1-decompose"); TodoWrite; the Task tool;\n'
        "subagent_type: bad-research-patcher; .claude/skills/x"
    )
    once = translate_tool_vocabulary(src)
    twice = translate_tool_vocabulary(once)
    assert once == twice


_SRC = """---
name: bad-research
user-invocable: false
description: >
  A multi-line
  description here.
color: green
model: opus
---

# Body

Content.
"""


def test_to_codex_skill_frontmatter_keeps_only_name_and_description():
    out = to_codex_skill_frontmatter(_SRC)
    assert out.startswith("---\n")
    assert "name: bad-research" in out
    assert "description:" in out
    assert "A multi-line description here." in out  # folded to one line
    assert "user-invocable" not in out
    assert "color: green" not in out
    assert "model: opus" not in out
    assert "# Body" in out


def _parse_frontmatter(rendered: str) -> dict:
    block = rendered.split("---\n")[1]
    data = yaml.safe_load(block)
    assert isinstance(data, dict), f"not a YAML mapping: {data!r}"
    return data


def test_to_codex_skill_frontmatter_is_valid_yaml_with_embedded_colon():
    # The real entry-skill description contains `tier-adaptive: a simple ...`;
    # the embedded `: ` made the hand-formatted scalar invalid YAML. The dumped
    # frontmatter must round-trip the colon, quotes, and `#` intact.
    src = (
        "---\nname: bad-research\ndescription: >\n"
        "  Behavior is tier-adaptive: a simple question gets a fast answer.\n"
        '  It uses "quotes" and a # hash and a trailing colon:\n'
        "color: green\n---\n\n# Body\n"
    )
    out = to_codex_skill_frontmatter(src)
    data = _parse_frontmatter(out)  # must not raise
    assert set(data.keys()) <= {"name", "description"}
    assert data["name"] == "bad-research"
    assert "tier-adaptive: a simple" in data["description"]
    assert '"quotes"' in data["description"]
    assert "# hash" in data["description"]


def test_to_codex_skill_frontmatter_only_name_and_description_keys():
    data = _parse_frontmatter(to_codex_skill_frontmatter(_SRC))
    assert set(data.keys()) <= {"name", "description"}


def test_strip_frontmatter_removes_yaml_block():
    out = strip_frontmatter(_SRC)
    assert not out.lstrip().startswith("---")
    assert "name: bad-research" not in out
    assert "# Body" in out


def test_strip_frontmatter_noop_when_absent():
    assert strip_frontmatter("# No frontmatter\n") == "# No frontmatter\n"
