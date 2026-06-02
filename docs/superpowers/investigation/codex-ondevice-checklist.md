# Codex install — on-device verification checklist

`bad install --codex` is **statically verified** (below). What it cannot prove from a dev box is
that the OpenAI Codex app actually *discovers, loads, and runs* the rendered skill — three runtime
primitives the design marked ASSUMED (see `codex-port-spike.md`). This is the 10-minute checklist to
close them on a real Codex device. Each item says what to do, what to observe, and the fallback if it
fails.

## Statically verified (no device needed — re-runnable)

Install to a scratch HOME and the render is structurally sound:
```
HOME=$(mktemp -d) bad install --codex
```
- ✅ 21 step references == the live `_BAD_RESEARCH_STEP_SKILLS` roster (incl. `12.5-grader.md`).
- ✅ 17 agent references (incl. the assumption critic).
- ✅ Every `references/*.md` path named in `SKILL.md` resolves to a real file (0 dangling).
- ✅ `SKILL.md` frontmatter is valid YAML (`name` + `description` only) — `yaml.safe_load` passes.
- ✅ `~/.codex/AGENTS.md` has the marker section + the prefer-the-vault / `bad fetch` intent.
- ✅ `~/.codex/config.toml` has `[features] multi_agent = true`.
- ✅ `spawn_agent`/`wait_agent` translation present; **0** `Skill(`/`Task(`/`subagent_type`/`TodoWrite`/`PreToolUse`/`/bad-research` leaks.

## On-device checks (the ASSUMED primitives)

### 1. Skill auto-discovery — does Codex see it?
- **Do:** run `bad install --codex` on the real machine; open Codex; ask a research-shaped question
  (e.g. *"write a cited report comparing PostgreSQL and MySQL on default transaction isolation"*).
- **Observe:** Codex triggers the `bad-research` skill (loads `~/.codex/skills/bad-research/SKILL.md`)
  without being told the skill name.
- **Fallback if not:** invoke it explicitly by name; if even that fails, Codex may not auto-discover
  `~/.codex/skills/<name>/` — file the path it *does* scan and adjust the install target.

### 2. On-demand reference reads — does the orchestrator read `references/<step>.md`?
- **Do:** during a run, watch whether the model reads e.g. `references/1-decompose.md` then
  `references/2-width-sweep.md` as it steps.
- **Observe:** it reads each step reference at the moment that step runs (the compaction-resistance
  design), via the native file-read tool.
- **Fallback if not:** if Codex won't read siblings on demand, inline the step procedures into
  `SKILL.md` (loses compaction-resistance) or prepend a stronger "read the reference for step N before
  running it" instruction in the router preamble.

### 3. `spawn_agent` signature — does it accept `model` / `tools`?
- **Do:** at a fan-out stage (e.g. step 2 fetcher wave or step 12 critics), see whether the
  `spawn_agent` calls the dispatch table emits are accepted, and whether per-agent `model:` /
  `tools:` are honored.
- **Observe:** parallel sub-agents spawn and return; tool-locks (patcher = Read+Edit) hold.
- **Fallback (already designed in):** if `model`/`tools` params don't exist, they degrade to a
  documented no-op — single model (gpt-5.5), tool-locks enforced by the prompt-level constraint in
  each agent body + the CLI gates (`bad uncited-gate`, grounding, recitation). The pipeline still runs.

### 4. End-to-end smoke
- **Do:** run ONE `ultrafast`-shaped query fully in Codex; confirm a final cited report lands and the
  vault populates under `./research/`.
- **Observe:** report written; `bad` CLI calls (fetch/search/verify-citations) work via Codex's shell
  tool (these are platform-neutral and already keyless-degrading).
- **If green:** flip the three primitives from ASSUMED → VERIFIED in `codex-port-spike.md` and the
  Codex port is trustworthy end-to-end.

> Note: the `bad` CLI itself is platform-neutral and unchanged on Codex; only discovery + dispatch are
> Codex-specific, which is exactly what this checklist covers.
