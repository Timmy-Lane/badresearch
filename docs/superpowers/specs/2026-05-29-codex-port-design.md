# Codex port of the bad-research pipeline — design

**Date:** 2026-05-29
**Status:** approved design, pre-implementation
**Author:** brainstorming session (Claude Code orchestrator + user)

## Problem

`bad-research` ships its deep-research pipeline as a Claude Code harness: a
`bad install` command writes an entry skill + 22 step skills + 16 subagents +
a PreToolUse hook + a CLAUDE.md blurb into `~/.claude/`. The orchestration
relies on two Claude Code primitives:

1. The `Skill` tool — the orchestrator loads each step procedure on demand,
   exactly when that step runs.
2. The `Task` tool with registered `subagent_type`s — parallel subagents with
   per-agent model pinning (opus/sonnet) and tool-locks (e.g. patcher =
   Read+Edit only).

We want the same pipeline available in **OpenAI Codex** (the desktop app,
model `gpt-5.5`), with the same logic, skills, and pipeline stages.

## Key scope insight

~90% of `bad-research` is already platform-neutral. The entire `bad` CLI
(vault, `fetch`, `search`, grounding / recitation / uncited gates, calibration)
is Python that Codex invokes through its native shell tool with **zero
changes**. Only two things are Claude-specific and need porting:

1. The `~/.claude/` **install surface** (skills, agents, hook, CLAUDE.md).
2. The **tool vocabulary** embedded in skill/agent prompt text (`Skill`,
   `Task`, `TodoWrite`, `subagent_type`, "Opus orchestrator").

This spec covers only those two.

## Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Subagent fidelity | **Full parity** — enable `multi_agent`, port all 16 subagents to `spawn_agent` with inline prompts. Models collapse to gpt-5.5; tool-locks become prompt-level + gate-enforced where Codex can't restrict tools. |
| D2 | Step-chain architecture | **One skill + `references/step-N.md`** — Codex auto-triggers skills by description and has no explicit `Skill(...)` loader, so the 16+ step procedures live as reference files the orchestrator reads on demand. |
| D3 | Distribution | **`bad install --codex`** — extend the existing CLI to write into `~/.codex/skills/`, mirroring the current `~/.claude/` installer. Keyless, same machinery. |
| D4 | Content single-sourcing | **Transform-at-install** — one source of truth (the existing step-skill `.md` files + agent prompt constants), translated to Codex at install time via a substitution table + frontmatter rewriter. A Codex-specific override exists only for the router section of SKILL.md, where the mechanics differ most. |

## Goals

- `bad install --codex` materializes the full pipeline as a single auto-discovered
  Codex skill.
- A Codex session can run the same agentic-fast / light / full tiers with the
  same stage sequence and the same grounding guarantees.
- One source of truth for prompt content; no parallel `skills_codex/` tree.

## Non-goals

- Changing any `bad` CLI behavior, vault format, or gate logic.
- Publishing a Codex marketplace plugin (possible later; D3 chose the CLI path).
- Bit-for-bit model parity — Codex is single-model; opus/sonnet distinctions
  degrade gracefully (see "Model & tool-lock handling").

## Target layout

`bad install --codex` writes one skill directory (global by default):

```
~/.codex/skills/bad-research/
├── SKILL.md                       # router/orchestrator (from skills/bad-research.md), Codex vocabulary
├── agents/
│   └── openai.yaml                # Codex UI metadata: display_name, short_description, default_prompt
└── references/
    ├── step-00.5-clarify.md        # 22 step procedures (from skills/bad-research-*.md),
    ├── step-01-decompose.md        #   read on demand via the native file-read tool (D2)
    ├── …
    ├── step-16-readability-audit.md
    ├── dispatch-table.md           # stage -> agent prompt file, parallel count, intended model/tool-lock
    └── agents/
        ├── fetcher.md              # 16 subagent prompts (from hooks.py constants),
        ├── loci-analyst.md         #   passed inline to spawn_agent (D1)
        ├── depth-investigator.md
        ├── source-analyst.md
        ├── dialectic-critic.md
        ├── depth-critic.md
        ├── width-critic.md
        ├── instruction-critic.md
        ├── light-critic.md
        ├── corpus-critic.md
        ├── draft-orchestrator.md
        ├── synthesizer.md
        ├── patcher.md
        ├── polish-auditor.md
        ├── readability-reformatter.md
        └── fresh-reviewer.md
```

Codex skill frontmatter is restricted to `name` + `description` (+ optional
`metadata.short-description`). The reference files have no frontmatter
requirements (they are plain context documents).

### Step-skill roster (source → reference file)

The 22 source files in `src/bad_research/skills/bad-research-*.md` map to
`references/step-*.md`, preserving order:

`0.5-clarify, 1-decompose, query-router, 1.6-plan-gate, 2-width-sweep,
3-contradiction-graph, 4-loci-analysis, 5-depth-investigation,
6-cross-locus-reconcile, 7-source-tensions, 8-corpus-critic, 9-evidence-digest,
10-triple-draft, 11-synthesize, 11.5-citation-verifier, 12-critics, 13-gap-fetch,
14-patcher, fresh-review, 15-polish, 16-readability-audit, agentic-fast`

## Tool-vocabulary translation

A deterministic substitution layer rewrites Claude Code tool references into
Codex equivalents (source of mapping: superpowers `codex-tools.md`):

| Source (Claude Code) | Codex render |
|----------------------|--------------|
| `Skill(skill: "bad-research-N-…")` | "read `references/step-N-….md`" |
| `Task(subagent_type=X, prompt=…)` | `spawn_agent(...)` with the inline prompt from `references/agents/X.md` |
| Multiple parallel `Task` calls | multiple `spawn_agent` calls, collected via `wait_agent`, freed via `close_agent` |
| `TodoWrite` | `update_plan` |
| `Read` / `Write` / `Edit` / `Bash` | native file/shell tools (names kept) |
| `WebFetch` of a source page | already `bad fetch` in the prompts — platform-neutral, untouched |

The translation is implemented as an explicit mapping table plus a frontmatter
rewriter, NOT free-form prose rewriting. The router section of `SKILL.md` —
"how the chain works" — is the one place the mechanics diverge enough that a
**Codex-specific override** is maintained rather than auto-translated (D4).

## Subagent dispatch — full parity (D1)

- Each of the 16 subagents becomes an inline `spawn_agent` prompt. The
  orchestrator reads `references/agents/<name>.md`, appends the per-call inputs
  (verbatim `research_query`, pipeline position, paths), and dispatches.
- Parallel fan-outs (fetcher waves, two loci-analysts, per-locus
  depth-investigators, the four step-12 critics) → multiple `spawn_agent`
  calls, gathered with `wait_agent`, released with `close_agent`.
- `~/.codex/config.toml` must contain `[features] multi_agent = true`. The
  installer adds this idempotently (additive edit) and reports it in the
  install actions. If the user's config can't be edited, the installer warns
  and prints the two lines to add.

### Model & tool-lock handling

Codex is single-model (`gpt-5.5`). Parity degrades gracefully:

- **Model pinning:** if `spawn_agent` exposes a model / reasoning-effort
  parameter, map `model: opus` → high effort and `model: sonnet` →
  default/medium effort. If it does not, all subagents run on the session model
  and the `model:` frontmatter becomes a documented no-op.
- **Tool-locks** (patcher / polish-auditor / readability-reformatter =
  Read+Edit only; fresh-reviewer = Read only): if `spawn_agent` exposes a tool
  allow-list, apply it. Otherwise enforce via (a) an explicit prompt-level
  constraint already present in each agent body ("you may ONLY Read and Edit")
  and (b) the existing pipeline gates (`patch-log`, grounding, uncited,
  recitation) which are CLI-based and unchanged.

> **Open implementation item:** confirm the exact `spawn_agent` signature
> (whether it accepts `model` / `tools` parameters) against current Codex docs
> during implementation. This does not change the architecture — the design
> already specifies a fallback for both cases.

## Install machinery — `bad install --codex`

Mirrors `core.hooks` for the Codex target:

- **Target:** `~/.codex/skills/bad-research/` (global). Research artifacts
  (`research/`) stay project-local exactly as today. Project-local Codex skills
  are written only if confirmed supported; otherwise global-only.
- **Frontmatter transform:** emit only `name` + `description`; strip
  `user-invocable: false` and any Claude-only fields.
- **AGENTS.md injection** replaces CLAUDE.md injection: a marker-delimited
  "Research Base (bad-research)" section is written into `~/.codex/AGENTS.md`
  (and/or project `AGENTS.md`), using Codex tool vocabulary. This section also
  carries the intent of the Claude-only PreToolUse hook — "prefer the vault and
  `bad fetch` over raw web search/fetch" — since Codex has no PreToolUse hook
  equivalent. Existing user AGENTS.md content is preserved (marker-section
  replace, never clobber).
- **Idempotency:** re-running `bad install --codex` is a cheap no-op when files
  and config are already current, matching the existing installer contract.

The existing `bad install` (Claude Code, `~/.claude/`) is untouched; `--codex`
is an additive flag. (`--codex` + `--project` semantics: global skill +
project AGENTS.md, pending project-skill support confirmation.)

## Single-sourcing (D4)

Implementation reads the same source content used by the Claude Code installer:

- step procedures: `src/bad_research/skills/bad-research-*.md`
- subagent prompts: the `*_AGENT` string constants in `core/hooks.py`

A translation module (substitution table + frontmatter rewriter) produces the
Codex layout at install time. This guarantees the two targets cannot drift in
substance. Only the router-section override is Codex-specific and lives in its
own small source file.

## Testing

- `tests/test_install` (Codex path): asserts files land at
  `~/.codex/skills/bad-research/…`; SKILL.md frontmatter is Codex-valid (only
  `name` + `description`); `references/step-*.md` and `references/agents/*.md`
  rosters are complete (22 + 16); `multi_agent = true` is present in config;
  AGENTS.md gets the marker section.
- A lint test asserting **no** `Skill(`, `Task(`, `subagent_type`, or
  `TodoWrite` tokens leak into any Codex-rendered file (translation completeness).
- Idempotency test: second `--codex` run produces no changes.

## Rollout

1. Translation module + router override (single-source transform).
2. `bad install --codex` writer (skill dir, references, agents, openai.yaml).
3. AGENTS.md injector + config `multi_agent` setter.
4. Tests (install layout, translation-leak lint, idempotency).
5. Manual smoke: run a light-tier query end to end in Codex.

## Open items

- Confirm `spawn_agent` signature (model / tools params) — see "Model &
  tool-lock handling".
- Confirm whether Codex discovers project-local `.codex/skills/` — affects
  `--codex --project`.
