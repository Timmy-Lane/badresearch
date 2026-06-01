"""Translate Claude Code skill/agent sources into Codex equivalents.

Pure functions only — no filesystem side effects. The Codex installer
(``codex_install.py``) composes these to render the skill directory.

The translation is a deterministic substitution layer, NOT free-form prose
rewriting:

1. ``Skill(skill: "bad-research-N-...")`` -> "read ``references/N-....md``"
2. ``Task(`` -> ``spawn_agent(`` and ``subagent_type: bad-research-X`` ->
   ``agent: references/agents/X.md`` (the inline-prompt source for that agent)
3. ``TodoWrite`` -> ``update_plan``
4. Claude install-surface paths (``.claude/skills/...`` etc.) -> Codex paths
5. ``to_codex_skill_frontmatter`` strips a Claude skill's frontmatter down to
   ``name`` + ``description`` (Codex SKILL.md rule); ``strip_frontmatter``
   removes it entirely (reference docs need no frontmatter).

Every public function is idempotent: running it on already-translated text is a
no-op, because the output contains none of the source tokens.
"""

from __future__ import annotations

import re

_SKILL_PREFIX = "bad-research-"


def skillref_path(skill_name: str) -> str:
    """``bad-research-5-depth-investigation`` -> ``references/5-depth-investigation.md``.

    Strips the ``bad-research-`` prefix and places the remainder under
    ``references/``. Used for both step procedures and (via ``agentref_path``)
    subagent prompts.
    """
    rest = skill_name[len(_SKILL_PREFIX):] if skill_name.startswith(_SKILL_PREFIX) else skill_name
    return f"references/{rest}.md"


def agentref_path(agent_name: str) -> str:
    """``bad-research-fetcher`` -> ``references/agents/fetcher.md``.

    The Codex filename for a subagent is its Claude frontmatter ``name:`` with
    the ``bad-research-`` prefix stripped. Deriving it this way (rather than a
    hardcoded table) guarantees ``subagent_type: bad-research-X`` and the file
    written for that agent always agree, even for the readability-recommender
    (whose name differs from the historical "reformatter" label).
    """
    rest = agent_name[len(_SKILL_PREFIX):] if agent_name.startswith(_SKILL_PREFIX) else agent_name
    return f"references/agents/{rest}.md"


# --- tool-vocabulary substitution ------------------------------------------

# Run FIRST: the structured Skill(...) call. Tolerates `skill:` / `skill =`
# spacing and single/double quotes. Consumes the whole call into a file-read
# instruction.
_SKILL_CALL_RE = re.compile(r'Skill\(\s*skill\s*[:=]\s*["\']([^"\']+)["\']\s*\)')

# Run SECOND: a `subagent_type: bad-research-X` line (the multi-line Task(...)
# form the skills use). Rewrites to `agent: references/agents/X.md`. Tolerates
# `:` or `=` and surrounding whitespace; captures the agent slug.
_SUBAGENT_TYPE_RE = re.compile(r'subagent_type\s*[:=]\s*(' + re.escape(_SKILL_PREFIX) + r'[\w.-]+)')

# Literal substitutions applied after the regexes. Order matters — longer /
# more-specific forms first so a later short form can't pre-empt them.
_LITERAL_SUBS: tuple[tuple[str, str], ...] = (
    # Claude install-surface paths -> Codex layout. Specific dirs before the
    # bare `.claude/` catch-all.
    (".claude/skills/", "references/"),
    (".claude/agents/", "references/agents/"),
    (".claude/settings.json", ".codex/config.toml"),
    (".claude/", ".codex/"),
    # The lazy step-skill bootstrap does not exist on Codex (procedures are
    # bundled). Neutralise the command so the orchestrator doesn't try it.
    ("bad install --steps-only . --json", "(no-op on Codex — step procedures are bundled here)"),
    ("bad install --steps-only .", "(no-op on Codex — step procedures are bundled here)"),
    ("bad install --steps-only", "(no-op on Codex — step procedures are bundled here)"),
    # Subagent dispatch tool.
    ("the Task tool", "the spawn_agent tool"),
    ("Task tool", "spawn_agent tool"),
    ("Task call", "spawn_agent call"),
    ("Task(", "spawn_agent("),
    # Any residual bare `subagent_type` token (e.g. in prose) -> `agent`.
    ("subagent_type", "agent"),
    # Task tracking.
    ("TodoWrite", "update_plan"),
    # Skill-loader phrasing.
    ("the Skill tool", "the file-read tool"),
    ("Skill tool", "file-read tool"),
    # Model phrasing (the orchestrator-as-Opus framing).
    ("orchestrator (Opus)", "orchestrator"),
    ("(Opus)", ""),
)


def translate_tool_vocabulary(text: str) -> str:
    """Rewrite Claude Code tool references into Codex equivalents.

    Idempotent: the output contains none of the source tokens, so a second
    pass is a no-op.
    """
    # Skill(skill: "bad-research-N-...") -> read `references/N-....md`
    text = _SKILL_CALL_RE.sub(lambda m: f"read `{skillref_path(m.group(1))}`", text)
    # subagent_type: bad-research-X -> agent: references/agents/X.md
    text = _SUBAGENT_TYPE_RE.sub(lambda m: f"agent: {agentref_path(m.group(1))}", text)
    # Literal token substitutions.
    for old, new in _LITERAL_SUBS:
        text = text.replace(old, new)
    return text


# --- frontmatter handling ---------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return ``(frontmatter_block_without_fences, body)``.

    ``frontmatter`` is ``None`` if the text has no leading ``---`` block.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def _extract_field(fm: str, field: str) -> str | None:
    """Extract a scalar or folded (``>``) YAML field from a frontmatter block.

    Handles both ``field: value`` and the folded/literal block form::

        field: >
          line one
          line two

    Returns the value folded to a single space-joined line, or ``None`` if the
    field is absent.
    """
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith(f"{field}:"):
            continue
        rest = line[len(field) + 1:].strip()
        if rest and rest not in (">", "|", ">-", "|-", ">+", "|+"):
            return rest
        # Folded/literal block: collect subsequent more-indented lines.
        collected: list[str] = []
        for cont in lines[i + 1:]:
            if cont.strip() == "":
                continue
            if not cont.startswith((" ", "\t")):
                break
            collected.append(cont.strip())
        return " ".join(collected) if collected else None
    return None


def to_codex_skill_frontmatter(text: str) -> str:
    """Rewrite a Claude skill's frontmatter to Codex-valid (``name`` + ``description``).

    Strips every other field (``user-invocable``, ``color``, ``model``,
    ``tools``, ...). If the text has no frontmatter, it is returned unchanged.
    """
    fm, body = _split_frontmatter(text)
    if fm is None:
        return text
    name = _extract_field(fm, "name") or "bad-research"
    description = _extract_field(fm, "description") or ""
    new_fm = f"---\nname: {name}\ndescription: {description}\n---\n"
    return new_fm + body


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block entirely (for reference docs)."""
    _, body = _split_frontmatter(text)
    return body
