# 06 — Cross-Cutting Design Standards & Packaging/Distribution

**Scope.** This dossier does two jobs. **Part A** defines the six cross-cutting
standards that stitch dossiers 01–05 into one coherent skill — citation,
eval, memory/context, cost, streaming, provider abstraction — and for each one
*recommends a single choice* with the reasoning. **Part B** is the
packaging/distribution matrix for "installable via `npx` or `pip`," with
concrete tradeoffs to inform the language/runtime decision. **Part C** is the
packaging recommendation, the open questions for the user, and a first-draft
Synthesis Map across all six dossiers.

**Labels.** `KNOWN` = read from hyperresearch source / a teardown citing
`file:line` / an official doc. `INFERRED` = derived from those facts.
`IDEA` = our design proposal for the ultimate skill (not yet built).

**Primary evidence base.**
- hyperresearch clone: `pyproject.toml`, `cli/install.py`, `core/hooks.py`,
  `mcp/server.py`, `skills/hyperresearch.md`, `models/note.py`, `core/db.py`.
- `teardowns/HYPERRESEARCH.md` (1,575 L), `teardowns/CLAUDE_RESEARCH.md`,
  `teardowns/CLAUDE_CODE.md`, `teardowns/CLAUDE_AGENT_SDK.md`.
- `products/HYPERRESEARCH_PRODUCT_CODE.md` (the standalone-orchestrator design).
- Official docs: Claude Code Skills (`code.claude.com/docs/en/skills`), MCP
  tools spec (`modelcontextprotocol.io/specification/2025-06-18/server/tools`).

---

# PART A — Cross-Cutting Standards

The five other dossiers (01 foundation, 02 retrieval/web, 03 agent loop,
04 synthesis/critique, 05 DR-loop comparisons) each decide *one stage*. These
six standards are the *interfaces between stages*. If they're inconsistent the
pipeline leaks: a citation format that step 2 writes but step 11 can't read; a
budget that step 1 sets but no stage enforces; a memory model that survives
compaction in Claude Code but evaporates in a headless run. Pick one of each,
hard-code the contract, make every stage obey it.

## A1 — Citation / Provenance

**What hyperresearch does (KNOWN).** Provenance lives in *two* places:

1. **On disk, per-source, in YAML frontmatter** (`models/note.py:72-94`,
   `NoteMeta`). Every fetched source becomes one markdown note whose
   frontmatter carries `source` (URL), `source_domain`, `fetched_at`,
   `fetch_provider`, plus epistemic metadata: `tier`
   (`ground_truth|institutional|practitioner|commentary|unknown` —
   `note.py:30-37`) and `content_type`
   (`paper|docs|article|blog|forum|dataset|policy|code|book|transcript|review`
   — `note.py:39-52`). A SQLite `sources` table
   (`core/db.py:101-113`) is the **dedup + provenance index**: `url` PK,
   `note_id` FK, `domain`, `fetched_at`, `provider`, a **16-char SHA-256
   `content_hash`**, and a `status` CHECK `{active,dead,redirected}`.
   *Markdown is truth, SQLite is cache* — delete the DB and `sync` rebuilds it.

2. **In the report, as in-body markers** (`skills/hyperresearch-11-synthesize.md`).
   The citation render mode is a per-run setting `citation_style ∈
   {wikilink, inline, none}`, decided in step 1 and written to
   `prompt-decomposition.json`:
   - `wikilink` (**default**): every citation is a `[[note-id]]` marker
     pointing at the source note in the vault. **No `## Sources` section** —
     the wiki-link *is* the citation and self-resolves against the vault graph
     (synthesize `:188-191`).
   - `inline`: every citation is a `[N]` marker, and the report ends with a
     `## Sources` section listing each cited source as `[N] Title. URL`, read
     from the cited note's YAML frontmatter (synthesize `:193-197`).
   - `none`: no markers, no Sources section.

   A separate readability check (instruction-critic, `core/hooks.py` R2)
   enforces a **citation density floor of 1.5 `[N]` per 1,000 body chars**.

**Compare Anthropic Research (KNOWN, `teardowns/CLAUDE_RESEARCH.md:280-284`).**
A dedicated late-stage **CitationAgent** (inferred Haiku) post-processes the
synthesized report against the fetched corpus and attributes every claim to a
source URL. Citation is a *separate cheap pass*, not inlined during drafting.

**Recommendation (IDEA): adopt hyperresearch's two-layer model verbatim, with
the wiki-link default, and add an OpenAI/Anthropic-DR-style verification pass.**

- *On-disk representation* — every source is one note file:
  `research/notes/<slug>.md` with frontmatter `{source, source_domain,
  fetched_at, fetch_provider, content_hash, tier, content_type}`, mirrored
  into a `sources` table keyed on URL with the SHA-256 content hash for dedup.
  This is the load-bearing decision: **provenance is a first-class on-disk
  artifact, not a string appended to a paragraph.** It is what lets citations
  survive context compaction, lets a later run reuse a prior source, and lets a
  critic search the vault for counter-evidence the draft *should* have cited
  (`teardowns/HYPERRESEARCH.md:439`).
- *In-report representation* — keep all three `citation_style` modes; default
  `wikilink` for vault-internal reports, switch to `inline` (`[N]` + `## Sources`)
  for shipped/standalone reports where the reader has no vault.
- *Verification pass (IDEA, borrowed from Research's CitationAgent)* — after
  synthesis, a cheap-model pass walks every claim → confirms a `[[note-id]]`/`[N]`
  exists and the cited note actually supports it (quote-grounding). This catches
  the failure where the model asserts then back-fills a plausible-but-wrong cite.
- *Cross-ref to dossier 05* — 05 should rank DR products on citation fidelity;
  whatever it recommends as the strongest scheme, the on-disk layer above is
  the substrate it renders from. The render mode is swappable; the provenance
  store is not.

## A2 — Eval / Grading Loop

**What hyperresearch does (KNOWN).** There is **no LLM-as-judge that scores a
number**. Grading is *adversarial and structural*, run as four parallel
critics, each Opus, each writing a findings JSON, then a tool-locked patcher
applies the findings as surgical edits (`core/hooks.py`,
`teardowns/HYPERRESEARCH.md:310-314`):

- **dialectic-critic** — counter-evidence the draft ignored/straw-manned
  (searches the vault for on-disk evidence *missing* from the draft).
- **depth-critic** — places the draft hand-waves where an interim note has
  load-bearing quotes/numbers.
- **width-critic** — corpus clusters present in the vault but absent from the
  draft; also a **bloat check** (top reports 45-55 KB, bottom 65-70 KB).
- **instruction-critic** — atomic items from `prompt-decomposition.json`
  missing/under-covered/out-of-order/wrong-format; structural-mirror check
  against `required_section_headings`; a `vague-recommendation` check that
  demands specific thresholds/numbers where the vault supports them.

Each finding has `severity ∈ {critical,major,minor}`, a `location`, an
`issue`, `evidence` (a vault note-id), and a `recommendation`. Critics
**cannot Edit** (`tools: Bash, Read, Write`); the patcher
(`tools: Read, Edit`) applies them with a **≤500-char net-expansion cap per
hunk** (`teardowns/HYPERRESEARCH.md:344`); findings that need restructuring
escalate to the orchestrator. Internally the RACE rubric (Readability,
Accuracy/Argument, Comprehensiveness, Evidence) is the implicit target — the
critics map 1:1 onto its dimensions.

**Compare Research (KNOWN, `CLAUDE_RESEARCH.md:39`).** Anthropic uses an
**LLM-as-judge rubric** — a single judge scores the output on factual accuracy,
citation accuracy, completeness, source quality, tool efficiency. Numeric.

**Recommendation (IDEA): use the adversarial-critic loop as the *in-pipeline*
grader, and add an LLM-as-judge rubric only as the *out-of-pipeline*
calibration harness.** Two different jobs:

- *In-pipeline (improve this report)* — the four-critic + patcher loop. It
  produces *actionable, located, evidence-cited fixes* a patcher can apply.
  A scalar score ("6/10") tells the pipeline nothing it can act on; a finding
  with `location`+`recommendation`+`evidence` does. This is the right grader
  for the loop because it closes — critic → patch → ship.
- *Out-of-pipeline (is the pipeline getting better)* — a separate
  LLM-as-judge with the RACE rubric, run over a frozen eval set, comparing our
  report vs. the original DR product's report on the same query (the
  "CALIBRATE" step from CLAUDE.md). This is the regression harness, not a
  pipeline stage.
- *Where it runs* — critics fire **after the draft, before the polish pass**
  (step 12 of 16). The judge runs **offline**, never in a user-facing run, on
  the example reports.
- *Cost guard* — critics are the single most expensive stage (4× Opus). Gate
  them on tier: `full` runs all four; `light` skips critics entirely
  (`hyperresearch.md:67`). Make the judge cheap-model where possible.

## A3 — Memory / Context Engineering (context-rot defense)

**What hyperresearch does (KNOWN) — this is its central insight.** The V7→V8
rewrite (`skills/hyperresearch.md:235-239`, `teardowns/HYPERRESEARCH.md:641`)
is the load-bearing lesson of the whole product. V7 was **one 1,200-line skill**
loaded once; by Layer 4 of a 3,000-line conversation, Claude Code's context
compaction had **silently evicted the procedure**, and the orchestrator dropped
a stage and produced a flat report — *"in 100% of runs where the orchestrator
didn't re-read the skill file."* The fix is three mechanisms working together:

1. **Skills-as-pipeline-stages.** Each of the 16 stages is its *own* skill
   file, loaded **fresh** into context via the `Skill` tool *at the moment it's
   needed* (`hyperresearch.md:35`). The orchestrator holds only the thin 251-L
   router. Compaction can evict an old stage's procedure — fine, it's never
   needed again because each stage is self-contained and reads its inputs from
   disk. This is the **program-counter-on-a-thin-host** pattern.
2. **TodoWrite as the durable program counter** (`hyperresearch.md:118-123`).
   The 16-step todo list is seeded at bootstrap and "survives context
   compaction; it's your durable memory of where you are in the chain."
3. **State-on-disk between every stage.** Each stage writes one canonical
   artifact (`hyperresearch.md:162-178`): `scaffold.md`,
   `prompt-decomposition.json`, `loci.json`, `comparisons.md`,
   `critic-findings-*.json`, etc. The recovery protocol is literally: *find the
   highest-numbered step whose artifact exists, resume from the next*
   (`:179`). **The model's context is never the source of truth** — disk is.

Two more layers: the **vault** is cross-session memory (notes compound across
runs, FTS5+graph indexed); and **per-subagent context isolation** — like
Research's SubAgents (`CLAUDE_RESEARCH.md:276`), a depth-investigator's full
fetched-page context lives only in *its* window; only the interim note crosses
back. This is what lets the system "search more than one context window holds."

**Recommendation (IDEA): port all three mechanisms, and make them
host-agnostic by defining them as a *filesystem state machine*, not a
Claude-Code feature.** The genius of the design is that it depends on almost
nothing host-specific:

- *Stage isolation* → in Claude Code, the `Skill` tool loads a fresh stage
  prompt; in a standalone orchestrator, **each stage is a fresh LLM call with
  exactly that stage's system prompt** and the prior stage's disk artifact as
  input. Same property, no host dependency.
- *Program counter* → in Claude Code, TodoWrite; in a standalone orchestrator,
  a `run-state.json` with `{current_stage, completed_stages, tier}`. The
  recovery rule ("resume from the next artifact") works identically.
- *State on disk* → identical in both. The artifact contract (which file each
  stage writes) is the *interface*; keep it byte-for-byte the same so a run can
  be inspected, resumed, or migrated between hosts.
- *Vault* → the markdown+SQLite store ports verbatim
  (`HYPERRESEARCH_PRODUCT_CODE.md §2`); no LLM, no host coupling.
- *Subagent isolation* → a sub-call gets only its task brief + curated
  note-ids; it returns only a digest. Host-agnostic by construction.

The single rule that makes this portable: **never store pipeline state in the
model's context; the context is a scratchpad, disk is memory.** That holds
whether the host is Claude Code, a Python loop, or an MCP client.

## A4 — Cost / Budget Control

**What hyperresearch does (KNOWN — implicit, tier-gated, not metered).** There
is no token meter and no $ ledger; cost is controlled *structurally* by three
levers:

- **Tier gate** (`hyperresearch.md:61-69`): step 1 classifies `light` vs `full`.
  `light` runs 5 stages (~$5-15, ~30-40 min), `full` runs all 16 (~$60-120,
  ~1.5-2.5 h). The gate is a "binding contract" — the orchestrator is *forbidden*
  to add stages "for thoroughness" or drop them "for budget."
- **Per-stage fan-out caps** (`teardowns/HYPERRESEARCH.md:651`): width sweep
  10-12 fetchers/wave, 8-12 URLs/batch, 45-80 sources total; loci ≤6; total
  depth budget **40 sources** distributed by locus score; source-analyst cap 6;
  gap-fetch ≤5 gaps; patch hunks ≤500 chars; readability ≤50 recs.
- **Model-tier routing** (`teardowns/HYPERRESEARCH.md:652`): orchestrator
  **Opus**; fetcher / loci-analyst / depth-investigator / corpus-critic /
  source-analyst (1M ctx) **Sonnet**; drafter / synthesizer / 4 critics /
  patcher / polish-auditor / readability-recommender **Opus**. Cheap model for
  *fetch/triage/read-heavy* work, strong model for *judgment/synthesis/critique*.

**Compare Research (KNOWN, `CLAUDE_RESEARCH.md`).** Anthropic notes multi-agent
burns ~15× the tokens of a chat and gates the *number* of subagents the lead
spawns (3-5) as the cost lever — same idea, fan-out as budget.

**Recommendation (IDEA): keep the structural levers, and add an explicit
per-run budget meter that the orchestrator checks at stage boundaries.** The
structural caps are correct and should port verbatim. What's missing for a
*shipped* product (where the user pays per run) is a hard ceiling:

- *Per-run budget* — accept `--budget-usd` / `--budget-tokens`. The
  orchestrator tracks spend in `run-state.json` and, at each stage boundary,
  checks the remaining budget against the stage's *expected* cost (a static
  table keyed on stage × tier). If a `full` run would blow the budget, it
  *downgrades the remaining stages* (e.g. skip the second loci-analyst, run 2
  critics instead of 4) rather than aborting mid-report.
- *Per-stage caps* — the existing fan-out caps become the *upper* bound;
  budget pressure tightens them dynamically.
- *Model-tier routing* — keep the cheap=fetch/triage, strong=synthesis/critique
  split. Make the two model IDs *configuration*, not hard-coded, so a budget
  run can route everything to the cheap tier and a premium run can route
  everything to the strong tier. (This is exactly the `ORCH_MODEL` /
  `WORKER_SONNET` / `WORKER_OPUS` env split already in
  `HYPERRESEARCH_PRODUCT_CODE.md §1`.)
- *Report* — emit a `cost-report.json` per run (tokens + $ per stage per
  model) so the user can see where the money went. Cheap to add, essential for
  a paid product.

## A5 — Streaming / Progress Protocol

**What hyperresearch does (KNOWN — none of its own).** As a Claude Code skill,
*progress streaming is the host's job*: Claude Code renders the orchestrator's
tool calls, subagent spawns, and TodoWrite updates in its own TUI. The
TodoWrite list doubles as the user-visible progress bar — the 16 todos tick
from pending→in_progress→completed. The CLI's `serve` command
(`teardowns/HYPERRESEARCH.md:596`) is a read-only markdown→HTML vault viewer,
not a progress stream. There is **no SSE/WebSocket** in the package.

**What a standalone needs (IDEA).** The product-code design
(`HYPERRESEARCH_PRODUCT_CODE.md §1`) exposes `POST /research {query, tier?}`
which runs ~2 h — that *must* stream or the client times out. Two consumers:

- *CLI front-end* — wants a live, human-readable progress feed (which stage,
  which subagent, how many sources fetched, current spend).
- *Server/API front-end* — wants a machine-parseable event stream a UI can
  render.

**Recommendation (IDEA): one event schema, two transports — NDJSON to stdout
for the CLI, SSE for the server — both emitting the same `ProgressEvent`.**

- *Event schema* (the contract): `{ts, run_id, stage, stage_status, event_type,
  detail, cost_so_far_usd, tokens_so_far}` where `event_type ∈ {stage_start,
  stage_done, subagent_spawn, subagent_done, source_fetched, artifact_written,
  budget_warning, error, final_report}`. The stage/artifact names are exactly
  the disk-state-machine artifacts from A3, so the progress stream *is* a live
  view of the program counter.
- *CLI transport* — write `ProgressEvent` as NDJSON to stderr (so stdout stays
  clean for the final report path); a Rich/ora progress UI renders it. Mirrors
  Claude Code's TodoWrite ticker.
- *Server transport* — SSE (`text/event-stream`), one `data:` line per
  `ProgressEvent`. SSE over WebSocket because the stream is server→client only,
  reconnect/resume is trivial (the `run_id` + `run-state.json` lets a
  reconnecting client replay from the last artifact), and it rides plain HTTP.
  This matches how the DR products stream (per dossier 05).
- *Resumability* — because state is on disk (A3), a dropped stream is not a
  dropped run; the client reconnects with `run_id` and the server resumes
  emitting from the current stage.

## A6 — Model-Provider Abstraction

**What hyperresearch does (KNOWN — Anthropic-only, by host inheritance).** The
package contains **zero LLM client** — verified no `anthropic`/`openai`
dependency in `pyproject.toml:24-34`; the only network deps are `httpx`,
`Crawl4AI`, `exa-py` (`teardowns/HYPERRESEARCH.md:17`). The model is *whatever
Claude Code runs*: Opus + Sonnet + Haiku via the subagent roster
(`README.md:159`). Provider abstraction is delegated entirely to the host — and
the Claude Agent SDK's host *does* support 7 API providers internally
(`firstParty`, `bedrock`, `vertex`, `foundry`, `anthropicAws`, `mantle`,
`gateway` — `CLAUDE_AGENT_SDK.md:1965-1980`), but **all are Anthropic-model
endpoints**. There is no path to GPT/Gemini through the Claude Code host.

**The decision.** The moment we ship a **standalone** front-end (Part B option
2/4), we *own* the LLM calls and must choose: stay Anthropic-only (direct
`anthropic` SDK) or go provider-agnostic.

**Tradeoffs (INFERRED).**

| Approach | Pro | Con |
|---|---|---|
| **Anthropic-only (direct SDK)** | Matches the original's exact model behavior (the prompts are *tuned* for Claude — tool-use formatting, the patcher's Edit discipline, RACE-shaped critics); prompt-caching + extended-thinking + Files API available; one auth path; simplest to calibrate against the original | Locked to one vendor's pricing/availability; can't route cheap stages to a cheaper non-Anthropic model; can't offer "bring-your-own-key for OpenAI" |
| **LiteLLM (one wrapper, ~100 providers)** | Single OpenAI-style interface across Anthropic/OpenAI/Gemini/local; per-stage model routing trivial; built-in cost tracking + fallbacks | Lowest-common-denominator API — loses Anthropic-specific features (fine-grained tool-use, prompt cache control) unless special-cased; another dep to maintain; behavioral drift (a prompt tuned for Opus may underperform on GPT-4o) breaks calibration |
| **OpenRouter (hosted gateway)** | Zero client code — one HTTP endpoint, one key, all providers; automatic failover; usage dashboard | A paid middleman in the request path (latency + margin); you don't control routing logic; vendor risk |
| **Thin internal `LLMProvider` Protocol + direct SDKs** | You implement the 2-3 methods you actually use (`complete`, `complete_streaming`, `count_tokens`) per provider; keep Anthropic features on the Anthropic impl; add OpenAI/local later without a heavy dep | More code than LiteLLM; you maintain each adapter |

**Recommendation (IDEA): ship Anthropic-first behind a thin `LLMProvider`
Protocol, with LiteLLM as the optional escape hatch.**

- *Default & calibration target* — direct `anthropic` SDK. The prompts are
  Claude-tuned; the only way to match the original's quality (the whole point
  of "CALIBRATE") is to run on Claude first. Keep prompt-caching and the exact
  model IDs (`ORCH_MODEL`/`WORKER_SONNET`/`WORKER_OPUS`).
- *Abstraction seam* — define `LLMProvider` with the minimal surface the
  pipeline uses: `complete(messages, model, tools, max_tokens, temperature) →
  Message`, `stream(...) → AsyncIterator[Chunk]`, `count_tokens(...)`. Ship one
  impl: `AnthropicProvider`. The orchestrator depends only on the Protocol.
- *Escape hatch* — a `LiteLLMProvider` impl behind an optional extra
  (`pip install ultimate-research[litellm]` / npm peer dep) for users who want
  OpenAI/Gemini/local. Document loudly that **non-Anthropic models are
  uncalibrated** — the critics/patcher prompts may need re-tuning.
- *Do NOT* hard-require LiteLLM/OpenRouter in the core. Provider-agnosticism is
  a feature for power users, not the default, because it trades away the exact
  thing that makes the replica good (Claude-tuned prompts).

---

# PART B — Packaging / Distribution Matrix

Four shipping models for "installable via `npx` or `pip`." For each: the
install command, the runtime, the host/model dependency, and who the user is.

## B1 — Option 1: Claude Code / Agent-SDK Skill (what hyperresearch IS)

**KNOWN — this is the reverse-engineered baseline.**

- **Install:** `pip install hyperresearch` then `hyperresearch install --global`
  (drops the entry skill + 14 agents into `~/.claude/`) or
  `hyperresearch install .` (per-project: vault + CLAUDE.md + PreToolUse hook +
  16 step skills + agents). On first `/hyperresearch` in a project the entry
  skill lazily bootstraps the vault and step skills
  (`cli/install.py:43-94`, `skills/hyperresearch.md:77-81`).
- **Runtime:** the Python CLI is a **deterministic vault manager** (SQLite-FTS5,
  web fetchers) that **never calls an LLM**. The *agent loop runs inside Claude
  Code* — the host model (Opus) reads the entry skill, sequences stages via the
  `Skill` tool, and spawns subagents via the `Task` tool.
- **Host/model dependency:** *hard* dependency on Claude Code (or the Agent SDK
  host). No Claude Code → the skill does nothing; the CLI alone can fetch+store
  but won't run the pipeline. Model is Anthropic-only (A6).
- **Who the user is:** a Claude Code user who types `/hyperresearch <topic>`.

**The SKILL.md frontmatter format (KNOWN — `code.claude.com/docs/en/skills`).**
A skill is a directory `<name>/SKILL.md` with YAML frontmatter + markdown body.
Disk locations and command names:

| Location | Command |
|---|---|
| `~/.claude/skills/<name>/SKILL.md` (personal) | `/<name>` everywhere |
| `<project>/.claude/skills/<name>/SKILL.md` (project) | `/<name>` in that project |
| `<plugin>/skills/<name>/SKILL.md` | `/<plugin>:<name>` |
| Plugin-root `SKILL.md` | `/<plugin>:<frontmatter-name>` |

Frontmatter fields:

| Field | Req | Meaning |
|---|---|---|
| `name` | No | Display label; defaults to directory name |
| `description` | Rec | What it does + when to use. **Claude reads this to auto-trigger.** `description`+`when_to_use` truncated at **1,536 chars** in the listing |
| `when_to_use` | No | Trigger phrases / example requests; counts toward the 1,536-char cap |
| `allowed-tools` | No | Tools usable without permission prompt while active (space-separated or YAML list) — **this is the tool-lock mechanism** |
| `model` | No | Model while skill active (`sonnet`/`opus`/`haiku`/`inherit`); reverts next turn |
| `effort` | No | `low`/`medium`/`high`/`xhigh`/`max` while active |
| `context` | No | `fork` → run in a forked **subagent** context |
| `agent` | No | Which subagent type when `context: fork` |
| `disable-model-invocation` | No | `true` → only the user can `/invoke`; also blocks subagent preload |
| `user-invocable` | No | `false` → hide from `/` menu (background knowledge) |
| `argument-hint` / `arguments` | No | Autocomplete hint / named positional args (`$name` substitution) |
| `hooks` | No | Hooks scoped to this skill's lifecycle |
| `paths` | No | Glob patterns; auto-activate only on matching files |

String substitutions in the body: `$ARGUMENTS`, `$ARGUMENTS[N]`/`$N`, `$name`,
`${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`.
**Progressive disclosure / supporting files:** `SKILL.md` is required;
sibling `scripts/`, `references/`, `templates/` load *only when the body
references them* — "long reference material costs almost nothing until you need
it." (This is the same trick hyperresearch's 16-skill split exploits.)

**The skills-as-pipeline pattern (KNOWN — the reusable architecture).** One
thin **router** skill (`hyperresearch.md`, 251 L) that *contains no procedures*
— it bootstraps canonical inputs, seeds the TodoWrite program counter, then
invokes `Skill(skill: "hyperresearch-N-stepname")` for each stage in tier order.
Each stage skill loads fresh, executes, writes a disk artifact, returns. Tool
discipline is enforced by `allowed-tools` per agent (critics get
`Bash,Read,Write`; the patcher gets `Read,Edit` only — *cannot regenerate*).
Subagents are `.claude/agents/<name>.md` files with their own `model:` and
`tools:` frontmatter, invoked by the `Task` built-in. A PreToolUse hook
(`matcher: "Glob|Grep|WebSearch|WebFetch"`, `core/hooks.py:3113-3119`) reminds
the host to check the vault before raw web search.

## B2 — Option 2: Standalone CLI with its own LLM client

**IDEA — the headless orchestrator in `products/HYPERRESEARCH_PRODUCT_CODE.md`.**

- **Install:** `pipx install ultimate-research` (Python) or
  `npx ultimate-research` / `npm i -g` (Node/TS). One binary.
- **Runtime:** bundles its *own* agent loop, the `LLMProvider` abstraction
  (A6), the vault, the web providers, and the disk-state-machine. The
  product-code file already designs this: a Python orchestrator that *replaces
  the Claude Code host*, calling the Anthropic Messages API directly (Opus
  orchestrator + Sonnet/Opus workers), "preserving the exact prompts,
  tool-locks (enforced by which tools we expose per worker), disk-state-machine,
  and constants" (`HYPERRESEARCH_PRODUCT_CODE.md` intro). The per-stage runner
  loads a step-skill prompt and spawns a worker with the right tool-allowlist
  (`§15`).
- **Host/model dependency:** *no Claude Code*. Needs `ANTHROPIC_API_KEY` (or
  any provider key via the abstraction). The user/agency runs the LLM calls and
  pays for them directly.
- **Who the user is:** anyone with a terminal and an API key — including
  servers, cron jobs, CI, other agents shelling out. The agency use-case
  (headless report generation) lives here.

## B3 — Option 3: MCP Server

**KNOWN baseline + IDEA extension.** hyperresearch already ships an MCP server
(`mcp/server.py`, `pip install hyperresearch[mcp]`) exposing the **vault** as
read-mostly tools: `search_notes`, `read_note`, `read_many`, `list_notes`,
`get_backlinks`, `get_hubs`, `vault_status`, `lint_vault`, `check_source`,
`list_sources`, `fetch_url`, `create_note`, `update_note`. It's "a thin
protocol layer over existing functions; read-only by design — agents create
notes via file ops, hyperresearch auto-syncs" (`mcp/server.py:1-6`). It does
**not** expose *the research pipeline* as a tool — only the vault primitives.

- **Install:** `pip install ultimate-research[mcp]`; register the stdio command
  in any MCP client's config (`claude_desktop_config.json`, Cursor, etc.).
- **Runtime:** the MCP server process. Per the MCP spec, it declares the
  `tools` capability, answers `tools/list` (each tool: `name`, `title`,
  `description`, `inputSchema` JSON-Schema, optional `outputSchema`), and
  handles `tools/call` returning `content[]` + optional `structuredContent`.
  Transports: **stdio** (default, what hyperresearch uses), or streamable HTTP.
- **Host/model dependency:** the **MCP client** runs the model. The server runs
  *no LLM* if it only exposes vault primitives (like today). **IDEA:** to expose
  the *pipeline* as one tool (`deep_research(query, tier) → report`), the server
  must own an LLM client internally (collapses into Option 2's orchestrator
  behind an MCP face).
- **Who the user is:** any MCP client (Claude Desktop, Cursor, another agent).
  The vault becomes a *shared research substrate* multiple agents can query.

## B4 — Option 4: Hybrid (one core, three front-ends)

**IDEA — the recommended target.** A single core library (orchestrator +
vault + provider abstraction + disk-state-machine + the 16 stage prompts) with
three thin front-ends:

1. **Claude-Code skill front-end** — `install --global` drops the router +
   stage skills + agents into `~/.claude/`; on a Claude Code host, the host
   model drives the loop (Option 1, zero API key needed — the user's Claude
   Code subscription pays).
2. **Standalone CLI/server front-end** — `npx`/`pipx` runs the *same* core with
   its *own* `LLMProvider` (Option 2), no host needed, BYO API key.
3. **MCP-server front-end** — exposes both the vault primitives (today) and the
   full pipeline as MCP tools (Option 3).

The core is identical across all three; only the *driver* differs (host model
vs. own client vs. MCP client). The disk-state-machine + artifact contract (A3)
is exactly what makes this possible — the pipeline doesn't care who's calling
the model, only that artifacts appear on disk in order.

- **Install:** `pip install ultimate-research[all]` →
  `ultimate-research install --global` (skill) **and/or** `ultimate-research
  serve` (CLI/server) **and/or** `ultimate-research mcp` (MCP). Pick a face.
- **Host/model dependency:** *configurable* — skill face = Claude Code host;
  CLI/MCP-pipeline face = own client.
- **Who the user is:** all three audiences, from one package.

---

# PART C — Packaging Recommendation, Open Questions, Synthesis Map

## C1 — Matrix

| | Install | Runtime | Who runs the LLM | Host dep | Cross-platform | User |
|---|---|---|---|---|---|---|
| **1. CC Skill** | `pip install` + `install --global` | Deterministic CLI; loop in Claude Code | **Claude Code host** (Anthropic-only) | **Hard: Claude Code** | Wherever CC runs | Claude Code user typing `/...` |
| **2. Standalone** | `npx` / `pipx` | Own agent loop + LLM client + vault | **Us / the user's key** | **None** | Node or Python everywhere | Terminal/server/CI/agent |
| **3. MCP** | `pip install[mcp]` + client config | MCP server; (LLM only if pipeline-as-tool) | **MCP client** (or us, if pipeline tool) | MCP client | stdio/HTTP everywhere | Any MCP client/agent |
| **4. Hybrid** | `pip/npm install[all]` + pick a face | Shared core, 3 drivers | Configurable per face | Configurable | Both | All three |

## C2 — Recommended path (and why)

**Recommendation: build the Hybrid (Option 4) with the standalone core as the
foundation, shipped Anthropic-first behind a thin provider seam.**

Reasoning:
1. **The standalone core is the irreducible asset.** Whether the front-end is a
   skill, a CLI, or an MCP tool, the value is the *16-stage disk-state-machine +
   the 16 tuned prompts + the vault*. Build that once, host-agnostic (A3 proves
   it's portable), and the three front-ends are thin shims. Building the skill
   *first* (Option 1) would couple us to Claude Code and make the standalone a
   painful retrofit; building standalone-first makes the skill a trivial
   wrapper (the skill *is* the prompts the standalone already runs).
2. **It de-risks the host dependency.** A pure skill (Option 1) is dead without
   Claude Code; a pure standalone (Option 2) gives up the zero-API-key
   distribution that Claude Code's subscriber base enjoys. Hybrid keeps both.
3. **It matches the existing teardown→product split.** `HYPERRESEARCH.md` (the
   skill) and `HYPERRESEARCH_PRODUCT_CODE.md` (the standalone orchestrator) are
   *already* the two halves of a hybrid — we'd be productizing what the RE
   already separated.
4. **MCP is nearly free once standalone exists** — wrap the same core in
   `tools/list`/`tools/call`. Ship it for the agent-to-agent audience.

Sequencing: **(1)** standalone core + CLI (the engine, calibrate against the
original via the example reports); **(2)** Claude-Code skill front-end (port the
router + stage skills, which are just the prompts the engine already runs);
**(3)** MCP front-end (thin wrapper). Anthropic-only at GA; LiteLLM escape hatch
behind an optional extra.

## C3 — Open questions for the user (frame as options, do NOT decide)

1. **Language: Python vs Node/TS vs both?**
   - *Python* — matches the base (hyperresearch is Python; the vault, Crawl4AI,
     pymupdf, the `anthropic` SDK all Python-native); `pip`/`pipx` install.
     Heavier deps (Crawl4AI pulls Playwright/Chromium).
   - *Node/TS* — `npx` zero-install UX is best-in-class for distribution; the
     Claude **Agent SDK** is TS-first; lighter for a thin orchestrator. But the
     vault + web-fetch stack would need a rewrite or a Python sidecar.
   - *Both* — TS front-end (`npx`) calling a Python core (sidecar/PyOxidizer),
     or two implementations. Most reach, most maintenance.
   - **Lean (mine, not a decision):** Python core (reuses the entire vault +
     fetch stack verbatim, fastest to a calibrated replica); optionally a thin
     `npx` shim later if `npx` distribution proves to matter for the audience.

2. **Standalone vs skill vs hybrid?** Recommended hybrid above — but if the
   *only* audience is Claude Code users, a pure skill is far less code; if the
   *only* audience is the headless agency pipeline, a pure standalone is
   simpler. The hybrid is right *only if* you want both audiences.

3. **Provider-agnostic vs Anthropic-only?** Anthropic-only matches the tuned
   prompts and is the calibration target; provider-agnostic (LiteLLM/OpenRouter)
   widens the audience but the critics/patcher prompts are uncalibrated on
   non-Claude models. Recommended: Anthropic-first, LiteLLM as optional extra.

4. **Self-hosted embeddings vs API?** hyperresearch's retrieval is **SQLite
   FTS5 (lexical) + a wiki-link graph — no vector embeddings in the default
   path** (`core/db.py` has an `embeddings` table but the default search is
   FTS5 with porter stemming + 7 ranking weights). If the ultimate skill adds
   semantic retrieval (dossier 02's call), the choice is: a local model
   (e.g. a sentence-transformer / GTE / bge, no API cost, needs CPU/GPU + the
   torch dep) vs. an embeddings API (Voyage/OpenAI/Cohere, per-call cost, zero
   infra). For a `docker-compose up` product, self-hosted keeps it
   dependency-closed; for a thin `npx` tool, an API keeps it light. **Open:
   does dossier 02 even require embeddings, or does FTS5+graph suffice?**

5. **(Secondary) Budget metering — opt-in or always-on?** A paid/agency product
   wants always-on `cost-report.json` + `--budget-usd` (A4); a personal skill
   running on a CC subscription doesn't see per-token cost and may not need it.

## C4 — First-Draft Synthesis Map (stitching dossiers 01–05)

A single architecture sketch showing where each dossier's decision lands and
how A1-A6 thread through. Stage names are the disk-state-machine artifacts.

```
                          ULTIMATE RESEARCH SKILL — one core, N front-ends
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ FRONT-ENDS (Part B / C2):  [CC skill] · [standalone CLI/server] · [MCP server] │
  │   skill→host model · CLI→own LLMProvider (A6) · MCP→client model               │
  └──────────────────────────────────────────────────────────────────────────────┘
                                       │  drives
                                       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ ORCHESTRATOR  (01_FOUNDATION.md: thin router + program counter)                │
  │   · TodoWrite / run-state.json  = durable program counter (A3)                 │
  │   · loads each stage FRESH, stage writes a disk artifact, returns (A3)         │
  │   · budget meter checked at every stage boundary (A4)                          │
  │   · emits ProgressEvent → NDJSON(CLI) / SSE(server) (A5)                        │
  └──────────────────────────────────────────────────────────────────────────────┘
        │ stage 1 decompose            (01_FOUNDATION.md — tier gate, atomic items,
        │   → prompt-decomposition.json   required_section_headings, citation_style)
        ▼
  ┌─────────────────────────────────────────┐
  │ RETRIEVE  (02_RETRIEVAL.md)              │  cheap-model fetch/triage (A4)
  │   width sweep → fetchers → VAULT         │  every source → note w/ provenance
  │   web providers (Exa/crawl4ai/builtin)   │  frontmatter + sources table (A1)
  │   FTS5 + graph (embeddings? = C3 Q4)     │  context-isolated subagents (A3)
  └─────────────────────────────────────────┘
        │ contradiction-graph, loci.json, interim notes
        ▼
  ┌─────────────────────────────────────────┐
  │ AGENT LOOP / DEPTH  (03_AGENT_LOOP.md)   │  ReAct/plan-execute per locus;
  │   depth-investigators (committed position)│  per-stage fan-out caps (A4);
  │   corpus-critic + gap-fetch              │  tool-lock per worker (allowed-tools)
  └─────────────────────────────────────────┘
        │ evidence-digest.md, comparisons.md
        ▼
  ┌─────────────────────────────────────────┐
  │ SYNTHESIS + CRITIQUE  (04_SYNTHESIS.md)  │  strong model (A4)
  │   triple-draft → fresh-context synthesizer│  citation render = citation_style (A1)
  │   → final_report.md                      │
  │   4 adversarial critics → patcher (≤500c)│  in-pipeline grader (A2)
  │   polish + readability audit             │
  └─────────────────────────────────────────┘
        │ final_report_<tag>.md  + critic-findings-*.json + patch-log.json
        ▼
  ┌─────────────────────────────────────────┐
  │ OUTPUT + EVAL                            │  citation-verification pass (A1)
  │   ship report; cost-report.json (A4)     │  OUT-OF-PIPELINE LLM-as-judge vs.
  │                                          │  the DR products (05_DR_LOOPS.md) (A2)
  └─────────────────────────────────────────┘

  05_DR_LOOPS.md feeds the whole sketch: it benchmarks our loop against
  Anthropic Research / OpenAI DR / Gemini DR — its findings on citation
  fidelity (→A1), judge rubric (→A2), parallelism/cost (→A4), and streaming
  (→A5) are the calibration targets every box above is tuned toward.
```

**How the standards thread the dossiers (one line each):**
- **A1 Citation** — set in 01 (`citation_style`), written in 02 (provenance
  frontmatter), rendered in 04 (synthesizer), verified at output; 05 sets the
  fidelity bar.
- **A2 Eval** — the 04 critic-loop is the in-pipeline grader; the 05 comparison
  defines the out-of-pipeline judge rubric.
- **A3 Memory** — the 01 program-counter + disk-state-machine is the spine all
  of 02/03/04 hang their artifacts on; the 02 vault is cross-session memory.
- **A4 Cost** — 01 tier gate + per-stage caps; cheap model in 02/03, strong in
  04; budget meter spans all stages.
- **A5 Streaming** — orchestrator-level, surfaces every 02/03/04 stage
  transition as a ProgressEvent.
- **A6 Provider** — front-end-level (Part B); the seam that lets the same
  01-04 core run on a CC host, our own client, or an MCP client.

---

## Appendix — Load-bearing constants & contracts (quick reference)

- **Tiers:** `light` = stages {1,2,10,15,16}, ~$5-15, ~30-40 min; `full` = all
  16, ~$60-120, ~1.5-2.5 h (`hyperresearch.md:66-67`).
- **Model routing:** orchestrator Opus; fetcher/loci/depth/corpus-critic/
  source-analyst Sonnet (source-analyst 1M ctx); drafter/synth/4 critics/
  patcher/polish/readability Opus (`HYPERRESEARCH.md:652`).
- **Fan-out caps:** 10-12 fetchers/wave, 8-12 URLs/batch, 45-80 sources; loci
  ≤6; depth budget 40 sources; source-analyst ≤6; gap-fetch ≤5; patch hunk
  ≤500 chars net; readability ≤50 recs (`HYPERRESEARCH.md:651`).
- **Critic caps:** dialectic/depth ≤12 findings, width ≤10 (8 gap+2 bloat),
  instruction ≤15 (12 IF + 3 readability); severity {critical,major,minor}.
- **Citation density floor:** 1.5 `[N]` / 1,000 body chars (instruction-critic R2).
- **Report size target:** 45-55 KB good, 65-70 KB bloated (width-critic bloat
  check).
- **SKILL.md description cap:** 1,536 chars (`description`+`when_to_use`).
- **content_hash:** 16-char SHA-256 truncation for URL/source dedup
  (`builtin.py:137`, `db.py:107`).
- **sources table:** `url` PK, `note_id` FK, `domain`, `fetched_at`,
  `provider`, `content_hash`, `status ∈ {active,dead,redirected}` (`db.py:101`).
- **Provider keys/envs (standalone, `HYPERRESEARCH_PRODUCT_CODE.md §1`):**
  `ANTHROPIC_API_KEY`, `EXA_API_KEY`, `ORCH_MODEL`, `WORKER_SONNET`,
  `WORKER_OPUS`, `HPR_VAULT_API`, `HPR_VAULT_ROOT`.
