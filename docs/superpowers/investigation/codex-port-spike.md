# Codex-port spike — unverified Codex primitives

**Date:** 2026-06-01
**Author:** Codex-port implementation worker (isolated worktree)
**Status:** pre-on-device. Decisions below are the best-supported assumption
given the docs reachable from this machine; each is marked VERIFIED vs ASSUMED.

The spec (`2026-05-29-codex-port-design.md`) flagged three Codex primitives as
unconfirmed. I cannot reach a live Codex app, so for each I read the superpowers
`codex-tools.md` reference (the canonical tool-mapping doc shipped with
superpowers 5.1.0) plus the spec, picked the best-supported assumption, and
built defensively with the spec's documented fallback.

## Sources consulted

- `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/using-superpowers/references/codex-tools.md`
  — the authoritative Codex tool-name mapping.
- `docs/superpowers/specs/2026-05-29-codex-port-design.md` — design + fallbacks.
- The superpowers Codex-app compatibility spec/plan (same cache,
  `2026-03-23-codex-app-compatibility-*`).

## Verification table

| # | Primitive | Status | Finding / assumption | Defensive build |
|---|-----------|--------|----------------------|-----------------|
| 1 | `spawn_agent` exists and is the Task-tool equivalent | **VERIFIED** (from codex-tools.md) | codex-tools.md maps Claude `Task` -> `spawn_agent`, parallel `Task` -> multiple `spawn_agent`, result-collection -> `wait_agent`, slot-free -> `close_agent`. These are the current names (the doc explicitly notes `wait_agent` superseded the legacy `wait` after rust-v0.115.0). | Router preamble + dispatch-table instruct the orchestrator to use exactly `spawn_agent` / `wait_agent` / `close_agent`. The tool-vocab translator rewrites every `Task(` -> `spawn_agent(` and every `subagent_type: X` -> `agent: references/agents/<X>.md`. |
| 1a | `spawn_agent` accepts a `model` / reasoning-effort param | **ASSUMED (no-op fallback)** | codex-tools.md does NOT document a `model` parameter on `spawn_agent`. Codex is single-model (`gpt-5.5`). | Per spec "Model & tool-lock handling": `model: opus` in the agent frontmatter is treated as a documented **no-op** mapped to "use your highest reasoning effort"; `model: sonnet` = default effort. The agent frontmatter is preserved verbatim in `references/agents/*.md` as an orchestrator hint, and the router preamble explains the effort mapping. No code path depends on a `model` kwarg existing. |
| 1b | `spawn_agent` accepts a `tools` allow-list param | **ASSUMED (prompt-level + CLI-gate fallback)** | codex-tools.md does NOT document a per-spawn tool allow-list. | Per spec: tool-locks (patcher/polish/readability = Read+Edit; fresh-reviewer = Read; synthesizer = Read+Write) are enforced two ways that need no Codex feature: (a) each agent body already carries an explicit prompt-level constraint, preserved verbatim, and the router preamble tells the orchestrator to HONOR the `tools:` frontmatter line; (b) the existing CLI ship-gates (`bad uncited-gate`, `bad recitation-gate`, grounding, patch-log) are platform-neutral and unchanged. If a future Codex build DOES expose `tools`, the frontmatter line is already machine-readable to wire it. |
| 2 | Codex auto-discovers `~/.codex/skills/<name>/SKILL.md` | **ASSUMED (global is the safe default)** | The superpowers Codex-app compatibility work treats `~/.codex/skills/` as the discovery root and SKILL.md frontmatter as `name`+`description`. The spec (D2/D3) chose global `~/.codex/skills/bad-research/` as the safe default and deferred project-local discovery until confirmed. | Installer writes the global path `~/.codex/skills/bad-research/SKILL.md` only. `--codex --project` is NOT implemented as a separate project-local skill tree (deferred per spec open item); `--codex` always targets global `~/.codex/`. Reference files live beside SKILL.md so discovery of the skill dir is sufficient — no second registration needed. |
| 3 | `[features] multi_agent = true` in `~/.codex/config.toml` enables spawn_agent | **VERIFIED** (from codex-tools.md) | codex-tools.md states verbatim: add `[features]` with `multi_agent = true` to `~/.codex/config.toml` to enable `spawn_agent`/`wait_agent`/`close_agent`. | `ensure_multi_agent()` performs an additive, idempotent TOML edit: if `multi_agent = true` already present -> no-op; if `[features]` table exists -> insert the key under it; else append a fresh `[features]` table. Never rewrites or reorders existing config. |

## On-device confirmation still required (Task 5 of the plan / spec open items)

These cannot be settled from this machine and must be checked in a live Codex
session before the install is trusted end-to-end:

1. **`spawn_agent` exact signature** — whether current Codex exposes `model`
   and/or `tools` kwargs. If it does, wire them from the preserved frontmatter;
   if not, the no-op + prompt-level fallback already in place is correct.
2. **Skill auto-discovery** — confirm Codex picks up
   `~/.codex/skills/bad-research/SKILL.md` after restart, and that it reads
   sibling `references/*.md` on demand when the body says "read
   `references/...`".
3. **`agents/openai.yaml`** — confirm the UI-metadata schema
   (`display_name` / `short_description` / `default_prompt`) matches what the
   Codex app actually reads for skill cards. The file is written defensively
   with those three keys.
4. **Project-local skills** — if Codex confirms `.codex/skills/` project
   discovery, extend `--codex --project`. Until then, global-only is correct.
