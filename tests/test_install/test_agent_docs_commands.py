"""Regression guard for issue #16: every CLI command the installer-written
CLAUDE.md block (`HYPERRESEARCH_BLURB`) tells the agent to run MUST actually
exist in the shipped CLI. The original bug shipped a doc block citing phantom
commands (`bad repair`, `bad status`, `bad setup`, `bad note list/update`,
`bad tags`) that the binary never registered — every fetcher subagent following
the documented mechanics failed on first call. This test fails the moment the
docs drift from the real command surface again.
"""

from __future__ import annotations

import re

from typer.main import get_command

from bad_research.cli import app
from bad_research.core.agent_docs import HYPERRESEARCH_BLURB


def _command_surface() -> tuple[set[str], dict[str, set[str]]]:
    """(top-level command names, {group: {subcommand names}}) for the live app."""
    root = get_command(app)
    top: set[str] = set(getattr(root, "commands", {}).keys())
    groups: dict[str, set[str]] = {}
    for name, cmd in getattr(root, "commands", {}).items():
        subs = getattr(cmd, "commands", None)
        if subs:
            groups[name] = set(subs.keys())
    return top, groups


# `{hpr} <cmd>` or `{hpr} <group> <sub>` — args/options (`<id>`, `"q"`, `--flag`)
# don't match `[a-z][a-z-]*`, so the second group is only ever a real subcommand.
_REF = re.compile(r"\{hpr\}\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")


def test_claude_md_blurb_references_only_real_commands():
    top, groups = _command_surface()
    refs = set(_REF.findall(HYPERRESEARCH_BLURB))
    assert refs, "expected the blurb to reference {hpr} commands"
    for cmd, sub in refs:
        assert cmd in top, f"CLAUDE.md docs reference unknown command: bad {cmd}"
        if sub and cmd in groups:
            assert sub in groups[cmd], (
                f"CLAUDE.md docs reference unknown subcommand: bad {cmd} {sub}"
            )


def test_phantom_commands_are_gone_from_blurb():
    # The specific phantom commands issue #16 named must not reappear.
    for phantom in ("{hpr} repair", "{hpr} status", "{hpr} setup", "bad setup"):
        assert phantom not in HYPERRESEARCH_BLURB, f"phantom command back in docs: {phantom}"
