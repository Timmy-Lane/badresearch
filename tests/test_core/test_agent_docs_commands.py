"""Guard: the installer-written CLAUDE.md blurb may only reference REAL CLI commands.

issue #11/#16 — the published v0.1.0 CLAUDE.md instructed `bad sync`, `bad note
list/update`, `bad tags`, `bad repair`, `bad status`, `bad setup`, and a
`fetch --save-assets` flag, none of which existed, so every agent following the
documented mechanics failed on its first call. This test pins the blurb to the
actual Typer surface so the docs can never silently drift from the CLI again.
"""
from __future__ import annotations

import re

from bad_research.cli import app
from bad_research.core.agent_docs import HYPERRESEARCH_BLURB


def _real_command_map() -> dict[str, set[str]]:
    """{top-level command -> set of its subcommands} for the live Typer app.

    A leaf command maps to an empty set; a group (note/assets) maps to its
    subcommand names."""
    out: dict[str, set[str]] = {}
    for c in app.registered_commands:
        name = c.name or (c.callback.__name__ if c.callback else None)
        if name:
            out[name] = set()
    for g in app.registered_groups:
        subs: set[str] = set()
        ti = g.typer_instance
        if ti is not None:
            for sc in ti.registered_commands:
                sname = sc.name or (sc.callback.__name__ if sc.callback else None)
                if sname:
                    subs.add(sname)
        out[g.name] = subs
    return out


# Every `{hpr} <command> [<subcommand>]` invocation in the blurb. The blurb uses
# the `{hpr}` path placeholder; the first token after it is the command.
_INVOCATION = re.compile(r"\{hpr\}\s+([a-z][a-z-]+)(?:\s+([a-z][a-z-]+))?")

# Tokens that follow a group command but are NOT subcommands (flags / args).
_NON_SUBCOMMAND = {"--help"}


def test_blurb_references_only_real_commands():
    real = _real_command_map()
    groups = {name for name, subs in real.items() if subs}
    bad: list[str] = []
    for cmd, maybe_sub in _INVOCATION.findall(HYPERRESEARCH_BLURB):
        if cmd not in real:
            bad.append(cmd)
            continue
        # For a group command (note/assets), the next token must be a real subcommand.
        if (cmd in groups and maybe_sub and not maybe_sub.startswith("-")
                and maybe_sub not in real[cmd] and maybe_sub not in _NON_SUBCOMMAND):
            bad.append(f"{cmd} {maybe_sub}")
    assert not bad, f"CLAUDE.md blurb references non-existent commands: {sorted(set(bad))}"


def test_blurb_has_no_save_assets_phantom_flag():
    # `fetch --save-assets` was a phantom flag (issue #16): the flag never existed
    # and the fetch CLI does not persist assets.
    assert "--save-assets" not in HYPERRESEARCH_BLURB
