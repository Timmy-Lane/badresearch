"""Unit tests for the Codex translation layer (codex_translate.py)."""

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


def test_strip_frontmatter_removes_yaml_block():
    out = strip_frontmatter(_SRC)
    assert not out.lstrip().startswith("---")
    assert "name: bad-research" not in out
    assert "# Body" in out


def test_strip_frontmatter_noop_when_absent():
    assert strip_frontmatter("# No frontmatter\n") == "# No frontmatter\n"
