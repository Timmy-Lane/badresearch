# 09 — Speed + Cost + the No-Overkill Curation Matrix

**Role of this dossier.** Dossiers 01–08 each argue *for* a pattern. This one is the
counterweight: it judges every proposed pattern against three axes — **does it make the skill
faster, does it make it cheaper, and does it bloat context or price beyond what it returns** — and
produces the single artifact the design plan executes from: **the ENHANCE / DEFER / CUT matrix**
(Part B) and the **lean v1 feature set** (Part C). The product we are protecting is a *Claude Code
skill* with a Python core, an Anthropic-first LLM seam, and Perplexity×NIA retrieval. Lean means:
**every token sent and every dollar spent has to earn its place.** A research skill that costs
$60–120 and 2.5 h per run (hyperresearch `full` tier, `01§1.1`) is already at the edge of what a
single operator will pay; the augmentations from 02–08 can each *double* that if adopted naively.
This dossier exists to stop that.

**Labels.** **KNOWN** = read from RE'd source / SDK / live probe (cited). **INFERRED** = derived
from those facts. **IDEA** = our design proposal for the skill.

**07 and 08 not yet on disk** (verified: `investigation/` holds only 01–06 at read time). Their
themes — **07 = quality/eval-loop**, **08 = grounding/citation** — are already substantially
specified in **05 §4 (citation standard), §6 (grader loop)** and **06 §A1 (provenance), §A2
(eval)**. Part B judges those proposed patterns under the 07/08 headings; if the on-disk 07/08
introduce a *new* mechanism not covered here, slot it into the matrix using the same three-axis
test stated above.

---

# PART A — Speed + Cost Architecture

The pipeline has exactly four cost/latency levers. Everything in Part A is one of: **(1) caching**
(don't pay twice), **(2) parallelism** (pay at the same time, not in series), **(3) model-tier
routing** (pay the cheap model for cheap work), **(4) budget controls** (cap the total). Each is
mined from the teardowns at reimplementable depth.

## A0 — The cost shape we are optimizing (KNOWN, the baseline)

hyperresearch `full` run = ~$60–120 / 1.5–2.5 h; `light` = ~$5–15 / 30–40 min (`01§1.1`,
`HYPERRESEARCH.md:1470`). Where the money goes (from `06§A4` + `05§7`):

- **Synthesis + critique (stages 10–14)** is the Opus-heavy half: triple-draft (3 Opus drafters)
  → synthesizer (Opus) → **4 parallel Opus critics** → patcher (Opus) → polish (Opus). The four
  critics are "the single most expensive stage (4× Opus)" (`06§A2`).
- **Retrieval (stage 2)** is the token-volume half: 10–12 fetchers/wave × 2–3 waves, 55–80
  sources (`HYPERRESEARCH.md:1483`), each source's full text entering a Sonnet context.
- **NIA's own number for the synthesis tax (KNOWN, `04§3.1`):** synthesis is **~75% of cold-path
  wall time** (10–18 s of a 20 s query); retrieval+rerank are ~1–3 s each. The cache eliminates
  synthesis entirely on a hit. This is the empirical justification for caching being lever #1.
- **Claude's empirical law (KNOWN, `05§7`):** "token usage by itself explains **80%** of the
  variance" in research quality; "upgrading Sonnet 3.7→4 is a larger gain than doubling the token
  budget." Optimization **order**: spend tokens first → optimize tool patterns → upgrade model.
  **Corollary for cutting:** when budget-constrained, cut tokens *last* — cut redundant tool calls
  and over-fetching first.

## A1 — Caching (lever #1 — the biggest single win)

Four distinct caches, each at a different layer. They compose; none substitutes for another.

### A1.1 NIA semantic cache — the query→answer L2 (KNOWN, `04§4`)

The highest-leverage cache. Spec, verbatim from NIA's wire (`04§4.1`, `04§8`):

```
key            = the QUERY EMBEDDING (not a string hash) → 64-bit LSH/SimHash bucket
threshold      = 0.92 cosine (configurable 0.8–1.0; 0.92 default)
embedder       = cache-lane embedder (NIA: Cohere embed-multilingual-v3.0, dim 1024)
speedup        = ~20–25× (warm 0.87–1.3 s vs cold 20–22 s); §15.3 measured 22.19 s → 0.87 s
tiering        = "exact" string-hash L1 in front of the "semantic" L2
write path     = miss → retrieve → rerank → synth → write-back to the LSH bucket
```

On a HIT, NIA echoes `_cached:true, _cache_type:"semantic", _cache_similarity:0.9973,
_original_query:"<seed text>"` (`04§4.2`) — **lift these echo fields verbatim** so the skill can
show the user *why* a query was free.

**The negation guard (KNOWN bug → mandatory fix, `04§1.3`/`04§4.3`).** Cohere v3 is
**negation-blind**: `"how does X wrap source chains"` and `"how does X NOT wrap source chains in
no_std"` hit cosine 0.9305 (above 0.92) and return the *same affirmative* cached answer. NIA never
fixed this. Our replica MUST gate it: a regex `not | n't | without | except | no_std | unlike`
detected in either query forces a **cache miss**. This is ~10 lines and prevents a wrong-answer
class.

**Single-user simplification (IDEA, `04§4`/`04§7.3`).** NIA's key is **cross-tenant** (global, no
tenant component) — that's a *scale* unit-economics play (anyone's query warms everyone's cache)
and a privacy footgun. A single-operator skill **drops the cross-tenant design**: a tiny SQLite
table `query_cache(bucket TEXT PK, query_embedding BLOB, query_text, response_json, created_at)`,
embed-query → LSH-bucket → cosine-compare within the bucket → return on ≥0.92 unless negation.
**Where it pays in *this* product:** the same/paraphrased query fires across hyperresearch stages
that re-search the vault (width-sweep, source-tensions, evidence-digest, critics, gap-fetch) —
~20× on those *intra-run* repeats, not just cross-run. **Verdict preview: ENHANCE, but scoped to
single-user + negation-guarded.** (The two-embedder split that NIA uses to amortize the cache lane
is itself CUT — see B.)

### A1.2 Anthropic prompt caching — the system-prefix L0 (KNOWN, `CLAUDE_CODE.md` §13)

This is the cache that makes a *Claude Code skill* cheap **for free** — it operates below the
semantic cache, on the API request itself. Mechanics, verbatim from Claude Code's own usage
(`CLAUDE_CODE.md:3503-3531`, `:3778`):

- **Up to 4 `cache_control` breakpoints per request** (Anthropic API hard limit).
- Claude Code's breakpoint strategy (directly copyable for our per-worker prompts):
  1. End of **static system-prompt prefix** → `{"type":"ephemeral","ttl":"1h"}` (the expensive
     1-hour write, amortized across the whole run).
  2. End of dynamic suffix (working dir / CLAUDE.md analogue) → `5m`.
  3. End of the **tool-descriptions block** → `5m`.
  4. End of last stable user message in a long conversation → `5m`.
- Usage is tracked split as `ephemeral_1h_input_tokens` vs `ephemeral_5m_input_tokens` because
  "Anthropic charges differently for 1h vs 5m cache writes" (`:3704`).
- The **`splitSysPromptPrefix` marker** (`CLAUDE_CODE.md:5009`, `:2163`): "blocks before the marker
  are eligible for cross-session prompt caching; blocks after it are not." → in our standalone
  orchestrator, put the **ported step-skill prompt + the verbatim research-query GOSPEL block**
  before the marker (stable across the whole pipeline, even across stages that re-spawn the same
  worker type) and the per-stage inputs after it.

**Why this matters for the skill specifically (IDEA).** Every hyperresearch stage re-spawns the
same agent *types* (fetcher, critic, etc.) with the same large system prompt. With a 1h breakpoint
on the agent's system prompt + the GOSPEL query, the 2nd…Nth spawn of that agent type within the
2.5 h run pays ~10% of the input-token cost. This is **the single cheapest speed/cost win in the
whole product** — it's a few `cache_control` stamps, zero new infrastructure, and it stacks with
A1.1. **Verdict preview: ENHANCE (v1, do first).**

### A1.3 Fetch/result caching — the source-content L1 (KNOWN, multiple sources)

- **hyperresearch already has dedup-by-content-hash:** the `sources` table keys on `url` with a
  16-char SHA-256 `content_hash` and a `status ∈ {active,dead,redirected}` (`06§Appendix`,
  `db.py:101`). A URL already fetched in this or a prior run is **not re-fetched** — the vault is a
  persistent cross-session fetch cache. **KEEP verbatim.**
- **Firecrawl's URL-keyed document store (KNOWN, `02§3.4`):** Supabase metadata + GCS HTML,
  default TTL **48 h**, per-domain dynamic via `query_max_age`, 200 ms race timeout; cache-write
  *skipped* for index/tlsclient/fetch engines, actions, custom headers/profile. The reusable rule
  for the skill: **fetch cache TTL ~48 h, keyed on normalized URL** (strip hash/www/port/index.*
  /trailing-slash, `02§3.4`). DEFER the GCS/Supabase tier (overkill at single-user — the vault's
  markdown files already are the cache).
- **Exa `maxAgeHours` (KNOWN, `02§2.1`):** default 168 h, `0`=force-fresh, `-1`=cache-only. When
  we call Exa `/contents`, set `maxAgeHours` per stage (fresh for news queries, cached otherwise).

### A1.4 The disk-state machine as a crash-resume cache (KNOWN, `01§1.1`, `06§A3`)

Not a query cache — a **whole-pipeline cache**. hyperresearch's orchestrator holds **no inter-stage
state in context**; every stage reads inputs from canonical disk artifacts and writes canonical
outputs (`01§1.1`, recovery map `skills/hyperresearch.md:162-179`). Recovery: "find the
highest-numbered step whose artifact exists; resume from the next." **This is a free re-run cache:**
a crashed or budget-aborted run resumes at the last completed stage instead of paying from scratch
— a 2.5 h run that dies at stage 12 doesn't re-pay stages 1–11. **KEEP verbatim** — it is the
single most important durable asset of the base, and it also *is* the streaming resumability
mechanism (`06§A5`: reconnect with `run_id`, replay from last artifact). **This is why 06's
"memento compaction" is CUT** (see B): the disk-state machine already solves what memento bolts on.

**Caching summary (the order to build):** A1.2 prompt-cache (free, do first) → A1.4 disk-state
(already there, keep) → A1.3 fetch dedup (already there, keep + add 48 h TTL) → A1.1 semantic cache
(new, single-user + negation-guarded). All four ENHANCE; none overkill.

## A2 — Parallelism (lever #2 — latency, not cost)

Parallelism cuts **wall-clock**, not dollars (you pay the same tokens, just concurrently). The rule
is: **parallelize independent work; never parallelize a dependency chain.**

### A2.1 Claude parallel tool calls — ~90% speedup (KNOWN, `05§8` principle 8, `CLR §11`)

"Execute multiple searches simultaneously rather than sequentially" cuts research time **up to 90%**
for complex queries (`05§8`). The mechanism: a Sonnet-4/Opus-4 model emits **N tool_use blocks in a
single assistant turn**; the harness dispatches all N concurrently (`05§2`, `CLR §CE.2`). Older
models (3.5) emit one tool_use per turn — the multi-block capability *is* the parallelism.
hyperresearch already exploits this (fetchers/critics/drafters spawned in ONE message,
`HYPERRESEARCH.md` stages 2.4/12/10.3). **KEEP + ensure every fan-out stage emits all spawns in one
turn.** Within an agentic-mode step (B/05§9.2), fan out the step's query list + fetches + python in
one parallel batch. **ENHANCE (free, already mostly present).**

### A2.2 Parallel-subagent fan-out — depth-1, default 3 (KNOWN, `05§2`)

Claude's reference design: **depth-1** fan-out (LeadResearcher spawns SubAgents that do NOT spawn
their own — flat, one level), default **3**, max 20, `max_parallel_subagents=10` per *batch*,
batches sequential (`05§2`, `CLR §CE.1`). Depth-1 is deliberate: async/deep nesting would scale
context **cubically** (O(depth×fanout×ctx), `05§2`). hyperresearch already enforces depth-1 — leaf
agents are denied the `Task` tool to prevent "recursive cost explosion (analysts spawning analysts
spawning analysts)" (`01§1.4`). **KEEP the depth-1 lock.** The default-3 / scale-to-complexity rule
maps onto hyperresearch's existing loci budget (≤6 investigators). **ENHANCE: add the runtime
guards (300 s timeout, per-tier tool-call caps 3/10/20/30) that hyperresearch lacks** (`05§2`,
`05§5`) — a stuck fetcher currently has no kill.

### A2.3 Async multi-provider search fan-out (KNOWN/IDEA, `02§6.3`)

In the cascade (`02§6.3`), Stage-1 search fires the **primary + 2–3 query expansions in ONE batch
call** (Sonar/Tavily batch-query support, `02§4.1`/`02§1.1`) — one round-trip instead of four. When
multiple providers are queried (e.g. Sonar + Exa for a thin result), fire them concurrently and
RRF-fuse. **ENHANCE, but only the batch-query single-round-trip part for v1**; the
multi-provider-concurrent-fan-out is **DEFER** (one good provider per stage is enough for v1; firing
3 providers in parallel triples search cost for marginal recall — see B).

### A2.4 What NOT to parallelize (the discipline)

- **The stage chain itself** — stages are a dependency DAG (synthesis needs the evidence digest
  needs the depth notes…). The disk-state machine is *sequential by contract* (`01§1.1`). Never
  parallelize across stages.
- **The width-sweep into agentic browse** — `03§7.4`: do NOT run Tier-3 agentic browse across many
  URLs in the width wave; it's "too many URLs." Browse is per-source, in depth/gap stages only.
- **Whole-pipeline ensembling** (Grok's N=16–32 instances) — 16–32× cost for marginal gain (`05§11`,
  CUT in B).

## A3 — Model-tier routing (lever #3 — the cheap-model-for-cheap-work table)

The single highest-ROI cost discipline. hyperresearch already routes (`06§A4`,
`HYPERRESEARCH.md:652`): cheap model for **fetch/triage/read-heavy** work, strong model for
**judgment/synthesis/critique**. The augmentation dossiers add more cheap-able jobs (rerank-L1,
classify, clarify, extract). The table below maps **every job in the augmented pipeline → an
abstract tier → a concrete Anthropic model behind the seam** (`06§A6`: `LLMProvider` Protocol,
`ORCH_MODEL`/`WORKER_SONNET`/`WORKER_OPUS`). Anthropic model IDs are *configuration*, not
hard-coded, so a budget run routes everything cheap and a premium run routes everything strong.

| Job | Tier | Anthropic model (behind seam) | Why this tier | Source |
|---|---|---|---|---|
| Clarifier (≤3 Qs, default-proceed) | **cheap/fast** | **Haiku** | one cheap call, fires only on ambiguity | `05§1` (ODR host = 4o-mini-class) |
| Intent/category classify (people/code/news/sec) | **cheap/fast** | **Haiku** (or local rules first) | binary/enum decision, no synthesis | `02§6.3` Stage-0 |
| Query expansion / reformulation | **cheap/fast** | **Haiku** | short generative, not judgment | `02§4.1` batch |
| Fetcher (fetch URL → markdown note) | **cheap/fast** | **Sonnet** | reading-comprehension, high volume | `01§1.4`, `06§A4` |
| Loci-analyst (score the corpus) | **cheap/fast** | **Sonnet** | judgment but bounded, parallel | `01§1.4` |
| Depth-investigator | **cheap/fast** | **Sonnet** | reading + committed-position notes | `01§1.4` |
| Source-analyst (>5000-word sources) | **cheap/fast (1M ctx)** | **Sonnet (1M)** | long-context read, not synthesis | `01§1.4`, `HR:1483` |
| Corpus-critic | **cheap/fast** | **Sonnet** | gap-finding over the vault | `01§1.4` |
| Rerank **L1** (lexical+embedding cosine) | **no LLM** | — (numpy/SERP scores) | runs on all ~1000 candidates, must be free | `02§5b.2`, `04§3` |
| Rerank **L2** (cross-encoder) | **cheap/fast** | Cohere `rerank-v3.5` API **or** local `bge-reranker-v2-m3` | runs on L1 survivors (top-30) only | `02§5b.2`, `04§3.4` |
| Extract (typed records from a page) | **cheap/fast** | **Haiku/Sonnet** (separate `page_extraction_llm`) | "use a cheaper model than the main loop" | `03§3.4`, `03§8.8` |
| Embed (query + chunks) | **no LLM** | embeddings API (Cohere/Voyage/OpenAI) | not a chat call | `04§7.3` |
| Triple-draft drafters (×3) | **strong** | **Opus** | the core synthesis work | `06§A4` |
| Synthesizer | **strong** | **Opus** | single-voice merge | `06§A4` |
| Grader (5-axis LLM-judge) | **strong** | **Opus** (Sonnet acceptable) | the quality gate; single call | `05§6`, `06§A2` |
| 4 adversarial critics | **strong** | **Opus** | finds load-bearing flaws | `06§A2` |
| Patcher (surgical Edit) | **strong** | **Opus** | precise, tool-locked | `01§1.4` |
| Polish / readability | **strong** | **Opus** (Sonnet acceptable) | hygiene + recs | `06§A4` |
| CitationAgent (re-ground every `[N]`) | **cheap/fast** | **Haiku** | verification pass, not generation | `05§4` (CLR Haiku) |
| Orchestrator (sequencing only) | **strong** | **Opus** | decisions, no research | `01§1.1` |

**The rule a senior engineer needs:** *if the job is read / triage / classify / extract / rerank-L1
/ verify-grounding, route cheap (Haiku for short decisions, Sonnet for long reads). If the job is
synthesize / critique / judge / patch, route strong (Opus).* The seam means a `--cheap` flag can
demote the strong tier (Opus→Sonnet for drafters/critics) for budget runs, accepting a quality dip
the grader will catch. **ENHANCE — this table IS the cost model.**

**One DEFER inside routing:** an *automatic* complexity-classifier that picks model per query
(Perplexity's `enable_search_classifier`, `02§4.1`) is **DEFER v2** — the tier gate (light/full/
oracle, B) already does coarse routing from the stage-1 decomposition for free; a learned
per-query model-router is over-engineering for v1.

## A4 — Budget controls (lever #4 — the cap that downgrades, not aborts)

Three controls, layered. The design principle from `06§A4`: **a per-run budget meter the
orchestrator checks at every stage boundary, and on pressure DOWNGRADES the remaining stages rather
than aborting mid-report.**

### A4.1 reasoning_effort / Juice tiers (KNOWN, `05§7`)

OpenAI's `reasoning_effort` is "the cleanest cost knob in agentic AI" — **4 levels
`minimal/low/medium/high`** (`05§7`, `ODR §R2.11`); "Juice" is the internal dial (128 max for full
DR, 64 default, 16 fast). **Adopt the 4-level enum** as the skill's primary knob, mapped to the
tier system (`05§7`, IDEA):

- `minimal` → light tier, **Haiku** drafters, single draft, no loci, no grader.
- `low` → light tier, **Sonnet** drafters.
- `medium` → full tier, default subagent counts (the default).
- `high` → full tier, max fan-out (loci ≤6, 12 fetchers), extended-thinking on, grader loop on.

This turns hyperresearch's binary light/full into a continuum. **ENHANCE (v1).**

### A4.2 The `--budget-usd` meter that downgrades (IDEA, `06§A4`)

The product-shaping control. Accept `--budget-usd` (and/or `--budget-tokens`). Track cumulative
spend in `run-state.json`; at **each stage boundary**, compare remaining budget to the stage's
*expected* cost (a static table keyed on stage × tier). If a `full` run would blow the budget,
**downgrade the remaining stages** following Claude's optimization order (`05§7`, `06§A4`):

1. **Cut tool-call redundancy first** (fewer fetchers, skip the redundancy/bloat audit).
2. **Drop the most expensive optional stages next** (4 critics → 2; second loci-analyst off;
   skip gap-fetch).
3. **Demote the model tier** (Opus drafters → Sonnet).
4. **Cut tokens LAST** (they're 80% of quality, `05§7`).

Never abort mid-report — a downgraded report beats no report at the same spend. Emit a
`cost-report.json` per run (`{input, output, reasoning, citation, search_queries}` per stage per
model — Perplexity's 5-component metering, `05§7`) so the user sees where the money went.
**ENHANCE (v1) — this is the difference between a toy and a sellable tool.**

### A4.3 Per-stage token caps + the existing fan-out caps (KNOWN, `06§A4`)

hyperresearch's structural caps ARE the cost model and port verbatim (`06§Appendix`): 10–12
fetchers/wave, 8–12 URLs/batch, 45–80 sources, loci ≤6, depth budget 40 sources, source-analyst ≤6,
gap-fetch ≤5, patch hunk ≤500 chars, readability ≤50 recs, critic finding caps (dialectic/depth ≤12,
width ≤10, instruction ≤15). Under A4.2 budget pressure these caps **tighten dynamically** (become
the *upper* bound, not the target). **KEEP + make budget-pressure-tightenable.**

### A4.4 The cascade "fire-only-when-thin" gating (KNOWN/IDEA, `02§6.3`)

The retrieval-side budget control. The default search cascade fires expensive stages **only on thin
results** (`02§6.3`):

- **Stage 1** (fast keyword/SERP, p50 <600 ms) always runs.
- **Stage 2** (neural/semantic rerank) fires **only if** result count < `max_results×0.6`, OR top
  score < 0.7, OR mode∈{neural,hybrid}, OR the query is a concept not a keyword.
- **Stage 3** (deep extraction — Firecrawl/Exa-contents) runs **only for the top-N URLs we'll
  actually cite**, not every result.
- **Failsafe (Perplexity, `02§5b.2`):** if <30% of candidates clear the 0.7 threshold, discard +
  re-retrieve once with a reformulated query.

This is the same "spend only when the cheap tier is insufficient" logic as the agentic-browse
escalation ladder (`03§6`: httpx → crawl4ai → typed-extract → agentic browse, each tier escalates
only on a quality-gate fail using the existing `looks_like_junk()`/`looks_like_login_wall()`).
**ENHANCE — the gating IS the cost discipline; without it the cascade is just "call every provider
every time."**

### A4.5 The light-vs-full tier gate + agentic-fast-mode routing (KNOWN, `01§1.1` + IDEA `05§9.2`)

The coarsest, highest-leverage budget control: **route the query to the cheapest pipeline that can
answer it.** hyperresearch's tier gate (binding contract, `HYPERRESEARCH.md:56`/`:1470`) already
splits light ($5–15) vs full ($60–120). Dossier 05 adds a **third, cheaper tier** routed from the
*same* stage-1 decomposition output (no new classifier, `05§9.2`):

```
if atomic_items ≤ 2 AND no contradiction-likely terms AND no time_periods
   AND response_format == "short" AND single domain:
     → AGENTIC MODE (Perplexity-style ReAct, max_steps ≤ 10)   cost ~$1–5, <3 min
elif response_format == structured OR atomic_items 3–6 OR mild tensions:
     → LIGHT TIER (1→2→10→15→16) + grader-loop                  cost ~$5–15
else (multi-domain / contested / time_periods / ≥7 items):
     → FULL PIPELINE (16 stages) + clarifier + grader-loop      cost ~$60–120
```

This is the biggest cost lever of all: it stops a "capital of France"-class query from triggering a
$60 16-stage run (OpenAI's documented over-browse failure, `05§11`). **ENHANCE the routing
heuristic (free — reuses existing decompose output).** The agentic-mode *implementation* (the ReAct
loop) is a v1 ENHANCE because it's the cheap path the routing needs; see B.

---

# PART B — THE NO-OVERKILL CURATION MATRIX

**How to read this.** Every pattern proposed across dossiers 01–08 and the augmentation map is
rated:

- **ENHANCE (v1)** — materially improves quality / speed / grounding at acceptable context+price
  cost. Build it.
- **DEFER (v2)** — genuinely good, but not essential to a working v1, or it depends on a v1 piece
  shipping first. Postpone.
- **CUT (overkill)** — bloats context or price, or the gain is marginal, or a base mechanism
  already solves it. Drop, with the reason.

**Context cost** = what it adds to the token bill / context window per run. **Price cost** = new
infra, GPU, or per-call vendor spend. The test for every row: *does this earn its tokens/dollars,
and does it keep us a lean Claude Code skill?*

## B1 — Foundation (dossier 01)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Skills-as-stages / fresh-procedure-per-stage (V7→V8 lesson) | **ENHANCE** | low (saves context — that's the point) | The crown jewel; the only thing that keeps a 2.5 h run from context-rotting. Non-negotiable. |
| Disk-state machine + recovery map | **ENHANCE** | ~0 (disk, not context) | Free crash-resume cache + streaming resumability; replaces "memento" entirely. |
| Light vs full tier gate (binding contract) | **ENHANCE** | ~0 | The coarsest cost lever; route cheap when possible. |
| `[Read,Edit]` / `[Read,Write]` tool-locks | **ENHANCE** | ~0 | Mechanical "patch-never-regenerate"; the single best integrity primitive. |
| FTS5/BM25 vault + provenance tables + dedup | **ENHANCE** | low | The substrate everything renders from; fetch dedup is a free cache. |
| `WebProvider` Protocol + `WebResult` (junk/login-wall gates) | **ENHANCE** | ~0 | Cleanest extension seam; the gates are reused by every escalation ladder. |
| MCP server (vault primitives) | **DEFER** | low | Useful agent-to-agent surface but not needed for a v1 Claude-Code skill; ship after core. |
| Standalone headless orchestrator (replace Claude-Code host) | **DEFER** | n/a | The brief scopes us to a *Claude Code skill*; the host already exists. Build the standalone only when a headless audience appears. |
| Provider-agnostic LLM backend (the EP-D socket) | **DEFER** | low | Anthropic-first behind a thin seam is v1; the socket can stay empty until a non-Anthropic user shows up. |
| Neural-retrieval socket (activate dead `embeddings` table) | **ENHANCE** | medium (embed API spend) | This is where 04's hybrid lane attaches; see B4. |
| HTTP serve / read-only web UI | **CUT** | n/a | Frontend chrome; a Claude Code skill renders in the host. Not product architecture. |

## B2 — Web Search + Neural Retrieval Providers (dossier 02)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Perplexity-Sonar `/search` as Stage-1 primary (358 ms, batch query) | **ENHANCE** | low ($0.005/search) | Fastest + highest SimpleQA (0.930); batch = query-expansion in one round-trip. The default fast tier. |
| Exa `type=auto` neural search as Stage-2 (RRF k=60) | **ENHANCE** | low ($0.005/search) | The semantic lane; fires only when Stage-1 is thin. hyperresearch already wires Exa. |
| Exa Highlights (500-char query-biased passages, 16× fewer tokens) | **ENHANCE** | saves tokens | The single biggest downstream-LLM cost lever ($75 → $10, `02§5b.3`). Pure win. |
| Firecrawl `/scrape` + 19-step transformer + injection-defended clean | **ENHANCE (extract only)** | per-page | The canonical HTML→clean-markdown path; lift the injection-defense prompt verbatim. |
| Firecrawl 3-tier SERP fallback (fire-engine → SearXNG → DDG) | **DEFER** | 0 (self-host) | Good zero-key floor, but one premium provider + builtin covers v1; add SearXNG self-host in v2. |
| RRF k=60 fusion (merge keyword + neural lists) | **ENHANCE** | ~0 | Parameter-free, scale-invariant; the correct merge for the cascade. ~15 lines. |
| Progressive rerank ladder L1→L2→L3 (0.7 threshold, <30% re-retrieve) | **ENHANCE (L1+L2 only)** | L2 = cheap | L1 (free, all candidates) + L2 (cross-encoder, top-30). **L3 XGBoost CUT** — overkill at single-user; the grader is the final quality gate. |
| Tavily SERP-fusion + RAG `/extract` | **DEFER** | $0.008/search | A solid Stage-1 fallback, but Sonar+Exa already cover fast+neural; add as a fallback tier in v2. |
| SearXNG zero-cost self-host search backbone | **DEFER** | 0 (needs a host) | The right v2 "no-premium-key" floor; v1 assumes the operator has one search key. |
| Serper / Brave keyword tier | **DEFER** | low | Optional keyword tier; not needed when Sonar is the primary. |
| Self-hosted Qwen3-Embedding-0.6B/4B + FAISS-IVF + binary-quant index | **CUT** | GPU-hour fixed cost | **Doesn't amortize at single-user scale** — a 4B GPU sits idle 95% of the time; API embeddings are $0-idle and cheaper at hundreds-of-notes/run (`04§7.3`). |
| Exa's full IVF-100k / binary-doc-fp32-query ADC index recipe | **CUT** | GPU + eng | Reproducing Exa's vector DB is a multi-week project for a single-user tool that needs `sqlite-vec` over a few hundred vectors. Massive overkill. |
| pplx-embed self-host (Qwen3-base + Matryoshka + INT8 QAT training) | **CUT** | GPU training cost | Training/hosting an embedder is absurd at this scale; use an embeddings API. |
| `WebSearchProvider` rich interface (`SearchQuery`, capabilities, cost_per_search) | **ENHANCE** | ~0 | The clean way to add providers + drive the cascade budget; backward-compatible with `WebProvider`. |
| The full default cascade (Stage 0 intent → 1 keyword → 2 neural → 3 extract) | **ENHANCE (gated)** | controlled by gating | Adopt the cascade *with* the fire-only-when-thin gating (A4.4) — that gating is what stops it being "call everything every time." |

## B3 — Agentic Browse + Structured Extraction (dossier 03)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Escalation ladder Tier 0→1→2→3 (httpx → crawl4ai → typed → agentic) | **ENHANCE** | controlled | The cost-disciplined fetch policy; each tier escalates only on a quality-gate fail. crawl4ai already present. |
| "Read with the tree, extract only for typed output" (Stagehand rule) | **ENHANCE** | saves tokens | The single biggest browse cost lever — never burn an extract LLM call to merely read. |
| Never let the LLM emit a selector; ground refs against the captured tree | **ENHANCE** | ~0 | The durable anti-hallucination lesson all 3 systems converge on. Free quality. |
| Null-on-missing, never fabricate (in the system prompt) | **ENHANCE** | ~0 | Free grounding; one prompt line. |
| Serialize DOM to indented text, prune aggressively, cap tokens | **ENHANCE** | saves tokens | The cheapest token is the one you don't send; crawl4ai's `fit_markdown` already does most of this. |
| `LLMExtractProvider` (Browser-Use prompt over crawl4ai markdown, cheap model) | **ENHANCE** | cheap LLM | Zero new deps, uses markdown already in hand; the default typed-extraction path. |
| ActCache / replay action scripts (SHA-256 of {instruction,url,var-names}) | **DEFER** | saves $ on repeat browse | Real win *if* agentic browse is used often; v1 browse is rare (depth/gap only), so the replay cache is a v2 optimization. |
| `BrowserUseProvider` (self-host agentic browse, Tier 3) | **DEFER** | N LLM calls | Needed for login/paywall/multi-step; rare in research. Ship the *interface* in v1, the impl in v2. |
| `BrowserbaseProvider` (paid anti-bot: stealth + proxy + CAPTCHA) | **CUT (v1)** | browser-min + proxy + LLM | Premium anti-bot infra is overkill for a research skill; most sources aren't Cloudflare-walled. Add only if a real paywall need emerges. |
| `AgentQLExtractProvider` (AQL DSL, deterministic ref-grounding) | **DEFER** | 1 LLM call + tree | Elegant for repeatable typed scrapes, but LLM-extract over markdown covers v1; AQL is v2 for known-shape pages. |
| `StagehandExtractProvider` (live AXTree extraction) | **CUT (v1)** | Browserbase session | Only when a live Browserbase session exists (Tier 3) — couples to paid infra we've cut for v1. |
| crawl4ai persisted profiles for login | **ENHANCE** | ~0 | Already in the base; the cheap login mechanism. Keep. |

## B4 — NIA Retrieval Stack (dossier 04)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Hybrid dense+BM25 fusion at `alpha=0.7` + rerank + three-tier weights {0.75/0.60/0.40} | **ENHANCE** | embed + rerank | The reimplementable core; turns FTS-only vault into hybrid neural+keyword. ~80 lines; BM25 lane already exists. |
| L2 semantic cache, 0.92 cosine, ~20×, negation-guarded, single-user | **ENHANCE** | one SQLite table + embed/query | The biggest latency/cost win on repeat+intra-run queries (A1.1). Drop cross-tenant, add negation guard. |
| Single API embedder for BOTH lanes (collapse NIA's two-embedder split) | **ENHANCE** | embed API spend | NIA's two-embedder split is a *scale* amortization that doesn't pay single-user (`04§7.3`). Use one API embedder. |
| Asymmetric `input_type` (document at index, query at retrieval) | **ENHANCE** | ~0 | Free quality; required by Qwen3/Cohere/Voyage alike. |
| AST-header-in-chunk indexing (prepend call-graph/control-flow before embed) | **DEFER** | low | NIA's best idea, but it only helps *code* corpora; a general research skill indexes mostly prose. Add for code-notes in v2. |
| Markdown structural header before embedding (H2 sections + tier/content_type) | **DEFER** | low | The prose analogue of AST headers; modest recall gain, add in v2 alongside chunking. |
| Chunk long notes at H2 boundaries (`note_chunks` table) | **DEFER** | low | Helps recall on long sources, but whole-note embedding is fine for v1's hundreds-of-notes scale. |
| `expand_symbols` cAST second-pass over call-graph neighbors | **DEFER** | extra retrieval round | Maps onto hyperresearch's link graph for free, but it's a recall refinement, not core. v2. |
| Source-type/tier weights composed with status multipliers | **ENHANCE** | ~0 | One dict + one multiply; hyperresearch already has status multipliers — compose with tier weights. |
| Self-host Qwen3-Embedding-4B (dim 2560, fp16, A100/H100, vLLM) | **CUT** | GPU-hour fixed cost | **Single-user index volume is tens-hundreds of notes/run; the GPU idles 95% of the time and its fixed cost dwarfs API embedding spend** (`04§7.3`). API embeddings win. |
| TurboPuffer ANN backend | **CUT** | hosted vector DB | Overkill at single-node single-user; `sqlite-vec` or in-process numpy over the BLOBs is enough (`04§3.6`). |
| Oracle JSON-action ReAct agentic mode (alongside fixed pipeline) | **ENHANCE** | bounded | This IS the cheap agentic-fast tier the routing (A4.5) needs; map its tool registry onto the existing CLI. |
| Oracle's Daytona micro-sandbox (per-job, 1800 s TTL, --no-builtin-tools) | **CUT (v1)** | sandbox infra | A `[Read, Bash-allowlisted]` subagent with no shell achieves the same isolation for local tools; full Daytona sandboxing is v2+. |
| Dream-cycle auto-entity-page enrichment (Temporal cron, 5 phases) | **DEFER** | LLM calls off-pipeline | Nice compounding-knowledge feature; run as off-pipeline `hpr dream`, not in the research loop. v2. |
| Dream-cycle's destructive vault-delete-on-cap bug | **CUT** | n/a | Explicitly do NOT replicate (`04§6.1`). |
| Intra-page (prose-vs-code) contradiction detection | **DEFER** | one LLM call | hyperresearch's inter-note contradiction is already better; intra-page is a nice add for the critic stage. v2. |

## B5 — Deep-Research Loop/Control (dossier 05)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| OpenAI 2-agent clarifier (≤3 Qs, default-to-proceed, Haiku) | **ENHANCE** | one Haiku call | One cheap call prevents an ambiguous $60 run going to the wrong topic. Highest ROI of the planning patterns. |
| Gemini editable plan-gate (approve/edit decomposition before run) | **DEFER** | ~0 | Great UX/steerability, but interactive-only; v1 ships `--auto` (GOSPEL query). Add the gate in v2 for `--interactive`. |
| Claude 4-field delegation contract (+`stop_conditions`+`output_shape`) | **ENHANCE** | ~0 | `stop_conditions` is the field that prevents "endless search for nonexistent sources." Two fields added to the spawn contract. |
| Depth-1 fan-out, default 3, batch=parallel() | **ENHANCE** | ~0 | Already in the base; keep the depth-1 lock (prevents cubic context blowup). |
| Per-subagent runtime guards (300 s timeout, tool-call caps 3/10/20/30, 100-source kill) | **ENHANCE** | ~0 | The base caps *counts* but has no per-agent timeout/tool-cap; a stuck fetcher has no kill. Add as runtime guards. |
| Perplexity planner→writer isolation (writer sees evidence, not CoT) | **ENHANCE** | saves tokens | Already how the synthesizer works; confirm it. Reduces synthesis context. |
| Perplexity `execute_python` in-loop tool (numpy/scipy/pandas/sympy) | **DEFER** | sandbox | Closes the quantitative-query gap (10-Q math), but most research queries don't need it; add to depth toolset in v2. |
| OpenAI `open`+`find` line-level primitives + line-numbered notes | **DEFER** | ~0 | Enables line-grain citations; valuable for the grounding standard but a v2 refinement over the vault's `[[note-id]]` anchor. |
| Agentic-ReAct fast mode (`max_steps≤10`, planner→writer) | **ENHANCE** | bounded ($1–5) | The cheap tier the routing (A4.5) routes simple queries to. Same engine as NIA Oracle. |
| Stage 11.5 grader loop (5-axis LLM-judge, ≤5 revisions) | **ENHANCE** | 1 strong call + re-grades | The quality gate the base lacks; cap 5 (not 20 — patches are surgical). Gate on full tier only. |
| CitationAgent re-grounding pass (Haiku) | **ENHANCE** | cheap pass | "Non-negotiable; citation hallucination is the single largest correctness risk" (`05§4`). One Haiku pass. |
| RECITATION gate (n-gram verbatim-overlap check) | **DEFER** | ~0 | Cheap copyright safety; fold into polish in v2. Synthesizer's "don't paste paragraphs" rule covers v1. |
| 20-query offline eval set + RACE-style judge (calibration harness) | **ENHANCE** | offline only | The CALIBRATE step from CLAUDE.md; out-of-pipeline, never in a user run. How we close the gap vs frontier DR. |
| reasoning_effort 4-level dial + per-component metering | **ENHANCE** | ~0 | The primary cost knob (A4.1) + cost transparency (A4.2). |
| Grok N=16–32 parallel full-pipeline instances + debate | **CUT** | 16–32× cost | **Whole-pipeline ensembling: 3× (or 16×) cost for a small gain.** The triple-draft+critics+grader gets most of the reliability at ~1/10 the cost (`05§11`). |
| OpenAI single-long-trajectory + `memento` self-summarization | **CUT** | n/a | A band-aid for context rot the disk-state machine *structurally* avoids. Skills-as-stages is strictly better (`05§11`). |
| Gemini locked-on-start plan with mid-run editing | **CUT** | requires ctx checkpointing | Mid-run editing requires checkpointing the orchestrator context, which the thin-host design deliberately avoids. Approve-before-run only. |
| Citation at paragraph/article grain | **CUT** | n/a | "Will hallucinate at the rate of pre-2025 browse models" (`05§11`). Always sentence/line grain. |
| OpenAI "always full effort" default | **CUT** | wasted $ | Over-browses trivial queries; the routing heuristic (A4.5) is the fix. |

## B6 — Cross-Cutting Standards (dossier 06)

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Two-layer citation: on-disk provenance frontmatter + in-report markers | **ENHANCE** | ~0 | Already in the base; provenance as a first-class on-disk artifact survives compaction. |
| `citation_style ∈ {wikilink, inline, none}` (wikilink default) | **ENHANCE** | ~0 | Swappable render mode; wikilink for vault, inline for shipped reports. |
| Adversarial-critic loop as in-pipeline grader | **ENHANCE** | 4× Opus (gate on full) | Produces *located, actionable, evidence-cited* fixes a patcher applies — better than a scalar score for closing the loop. |
| LLM-as-judge rubric as out-of-pipeline calibration harness | **ENHANCE** | offline | Same as 05's eval set; the regression/calibration harness. |
| Disk-state machine memory model (host-agnostic) | **ENHANCE** | ~0 | The portable spine; "context is scratchpad, disk is memory." |
| Per-subagent context isolation (only the digest crosses back) | **ENHANCE** | saves tokens | Lets the system "search more than one context window holds." Already in the base. |
| Per-run `--budget-usd` meter + graceful downgrade + `cost-report.json` | **ENHANCE** | ~0 | The cap that downgrades not aborts (A4.2); essential for a sellable tool. |
| Model-tier routing as configuration (env-keyed model IDs) | **ENHANCE** | ~0 | The seam that lets a `--cheap` run demote Opus→Sonnet. |
| ProgressEvent schema → NDJSON(CLI) / SSE(server) dual transport | **DEFER** | ~0 | Streaming matters for the *standalone server* face; a Claude Code skill streams via the host's TUI (TodoWrite ticker). v1 needs no SSE. |
| Anthropic-first behind thin `LLMProvider` Protocol | **ENHANCE** | ~0 | Matches the Claude-tuned prompts (the calibration target); the seam is ~3 methods. |
| LiteLLM as optional escape hatch (`[litellm]` extra) | **DEFER** | dep | Provider-agnosticism is a power-user feature, not v1; "non-Anthropic models are uncalibrated." Optional extra later. |
| OpenRouter hosted gateway | **CUT** | paid middleman + latency | A paid middleman in the request path with margin + latency + vendor risk; the thin seam + direct SDK is better. |
| Hybrid packaging (one core, 3 front-ends: skill / CLI / MCP) | **DEFER** | n/a | The right *long-term* shape, but v1 is a Claude Code skill. Build the core skill-first; standalone/MCP faces in v2. |
| Standalone-first sequencing (build headless core, skill as wrapper) | **CUT (for this scope)** | n/a | The brief scopes v1 to a *Claude Code skill*; standalone-first inverts that. Build skill-first; the disk-state contract keeps standalone viable later. |

## B7 — Quality / Eval (dossier 07 theme — not yet on disk)

Judged from the 07 theme as specified in `05§6` and `06§A2`:

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Single-call 5-axis LLM-judge (0.0–1.0 + PASS/FAIL) | **ENHANCE** | 1 strong call | "Single LLM call was MORE consistent than ensemble judges" (`05§6`). Cheap, gated on full tier. |
| Grader→patch→re-grade revision loop (cap 5) | **ENHANCE** | ≤5 re-grades | Closes the quality loop the base lacks; cap 5 because patches are surgical not regenerations. |
| Multi-call ensemble judge | **CUT** | N× judge cost | Tested *worse* than single-call (more variant-prompt noise, `05§6`). Don't ensemble the judge. |
| `define_outcome` managed-agent 20-revision cap | **CUT (the 20)** | wasted revisions | 20 assumes full regeneration; surgical patches converge in ≤5. Cap at 5. |
| 20-query eval set → scale to hundreds | **ENHANCE** | offline | Start at 20 for fast regression, scale before committing (`05§6`). Out-of-pipeline. |

## B8 — Grounding / Citation (dossier 08 theme — not yet on disk)

Judged from the 08 theme as specified in `05§4`/`05§9.4` and `06§A1`:

| Pattern | Verdict | Context/price cost | One-line reason |
|---|---|---|---|
| Per-sentence single-index `[N]` brackets (≤3/sentence, no space, no `## References`) | **ENHANCE** | ~0 | The cleanest prose render; Perplexity's rule. Already close to the base's per-sentence discipline. |
| Vault `[[note-id]]` as the hard provenance anchor | **ENHANCE** | ~0 | Already the base default; a citation is a reference to a stored artifact, not a string. |
| CitationAgent re-grounds every `[N]` before finalize (Haiku) | **ENHANCE** | cheap pass | The single largest correctness risk is citation hallucination; one cheap pass. |
| Citation density floor (1.5 `[N]` / 1000 chars) | **ENHANCE** | ~0 | Already enforced by the instruction-critic; keep. |
| Line/char-offset grain stored per citation (OpenAI L-range + Perplexity Annotation) | **DEFER** | ~0 | Finer verifiability, but the `[[note-id]]` anchor is enough for v1; add line-grain in v2. |
| Per-claim confidence scores (Gemini grounding) | **DEFER** | ~0 | A nice CitationAgent output; v2 polish. |
| Gemini byte-span `groundingMetadata` pipeline | **CUT** | eng | Reproducing Gemini's grounding-metadata machinery is overkill; the re-grounding pass + vault anchor achieves the goal. |

---

# PART C — Curation Summary + the Lean v1 Feature Set

## C1 — The verdict tally

**99 patterns rated across dossiers 01–08 + the augmentation map: 54 ENHANCE / 25 DEFER / 20 CUT.**

| Bucket | Count | What it means |
|---|---|---|
| **ENHANCE (v1)** | **54** | Build these. Note ~half are *KEEP the base does it already* (disk-state machine, tool-locks, fan-out, FTS lane, provenance) — the genuinely *new* v1 build is far smaller (see C3). |
| **DEFER (v2)** | **25** | Good, postponed: SearXNG/Tavily/Brave fallback tiers, AST/markdown chunking + headers, `expand_symbols`, Dream enrichment, ActCache replay, BrowserUse/AgentQL impls, plan-gate, `execute_python`, line-grain citations, ProgressEvent/SSE, MCP face, LiteLLM, hybrid packaging. |
| **CUT (overkill)** | **20** | Dropped — they bloat price (GPU/hosted infra), bloat context (ensembling), or a base mechanism already solves it. |

## C2 — The headline CUTs (the bloat we are refusing, grouped by why)

**Price-bloat — self-hosted GPU / hosted infra that doesn't amortize single-user:**
- **Self-host Qwen3-Embedding-4B (and the 0.6B variant)** — a 4B fp16 embedder on an A100/H100
  amortizes only at high index volume; a single-user run indexes hundreds of notes and the GPU
  idles 95% of the time. **API embeddings are $0-idle and cheaper here** (`04§7.3`).
- **Exa's IVF-100k + binary-doc/fp32-query ADC vector DB recipe** — reproducing a billion-scale
  neural index for a few-hundred-vector vault is multi-week eng for zero benefit; `sqlite-vec` or
  in-process numpy is enough.
- **pplx-embed self-host (Qwen3-base + Matryoshka + INT8 QAT training)** — training/hosting your
  own embedder is absurd at this scale.
- **TurboPuffer ANN backend** — hosted vector DB; overkill single-node.
- **Oracle's Daytona micro-sandbox** — a `[Read, Bash-allowlisted]` no-shell subagent gives the
  same isolation without sandbox infra.
- **Browserbase verified anti-bot + StagehandExtract live-AXTree** — paid stealth/proxy/CAPTCHA
  infra; most research sources aren't Cloudflare-walled.
- **OpenRouter hosted gateway** — a paid middleman (margin + latency + vendor risk) in the request
  path; the thin `LLMProvider` seam + direct SDK is leaner.

**Context/price-bloat — ensembling and band-aids the base structurally avoids:**
- **Grok N=16–32 parallel full-pipeline instances + debate** — *whole-pipeline ensembling: 16×
  cost for a small gain.* The triple-draft + 4 critics + grader gets most of the reliability at
  ~1/10 the cost (`05§11`).
- **Multi-call ensemble judge** — tested *worse* than a single-call judge (variant-prompt noise,
  `05§6`).
- **OpenAI `memento` self-summarization** — a band-aid for the exact context rot the disk-state
  machine *structurally* prevents; skills-as-stages is strictly better.
- **`define_outcome` 20-revision cap** — assumes full regeneration; surgical patches converge in
  ≤5, so 20 is wasted spend.

**Marginal / wrong-grain:**
- **Citation at paragraph/article grain** — "hallucinates at the rate of pre-2025 browse models"
  (`05§11`); always sentence/line grain.
- **OpenAI "always full effort" default** — over-browses trivial queries; the routing heuristic is
  the fix.
- **Gemini mid-run plan editing** — needs orchestrator-context checkpointing the thin-host design
  deliberately avoids.
- **Gemini byte-span `groundingMetadata` machinery** — the re-grounding pass + vault anchor reaches
  the same goal without the pipeline.
- **Standalone-first sequencing / HTTP serve UI** — out of scope for a v1 *Claude Code skill*
  (frontend chrome / wrong-order build).

**The unifying rule behind every CUT:** *at single-operator scale, fixed-cost infra (GPU, hosted
DB, sandbox, gateway) never amortizes, and N× ensembling never returns N× quality. The base's
disk-state machine + tool-locks already solve the context-rot problems the frontier products bolt
extra machinery onto.*

## C3 — The Lean v1 Feature Set (ordered — what the design plan builds)

Scoped to **stay a Claude Code skill, not bloat context, not bloat price.** "KEEP" = inherit from
the base unchanged; "NEW" = the actual build. The genuinely new v1 surface is small — that is the
point.

**Tier 0 — Free wins, do first (cost↓ at ~0 eng):**
1. **NEW — Anthropic prompt-caching breakpoints (A1.2).** Stamp `cache_control` on every worker's
   static system-prompt prefix (1h) + tool-block/dynamic-suffix (5m), 4 breakpoints max. Put the
   step-skill prompt + GOSPEL query before the `splitSysPromptPrefix` marker. *The single cheapest
   win; it makes the whole skill ~10× cheaper on repeated worker spawns.*
2. **KEEP — disk-state machine + recovery map (A1.4)**, tool-locks, depth-1 fan-out, FTS5 lane,
   provenance frontmatter + `sources` dedup cache, `WebProvider`/`WebResult` gates, light/full tier
   gate. *The durable spine; change nothing.*

**Tier 1 — The model + budget cost model (cost↓, the sellable-tool layer):**
3. **NEW — model-tier routing table behind the `LLMProvider` seam (A3).** Anthropic-first; env-keyed
   model IDs so `--cheap` demotes Opus→Sonnet. Haiku for clarify/classify/extract/cite-verify,
   Sonnet for fetch/read, Opus for synth/critique/judge/patch.
4. **NEW — `reasoning_effort` 4-level dial (A4.1)** mapped onto the tier continuum
   (minimal/low/medium/high → Haiku-light … max-fan-out-full).
5. **NEW — `--budget-usd` meter that downgrades, not aborts (A4.2)** + `cost-report.json`
   (5-component metering). Cut order: redundant tool calls → optional stages → model tier → tokens
   last.
6. **NEW — per-subagent runtime guards (A2.2):** 300 s timeout, tool-call caps 3/10/20/30,
   100-source kill. Add `stop_conditions` + `output_shape` to the spawn contract.

**Tier 2 — The query-routing + agentic-fast tier (cost↓ + speed↑, the biggest lever):**
7. **NEW — three-way query routing from the existing decompose output (A4.5):** agentic-fast
   ($1–5) / light ($5–15) / full ($60–120). Free — reuses stage-1 atomic-items/format/time_periods.
8. **NEW — agentic-ReAct fast mode (NIA Oracle / Perplexity loop):** `max_steps≤10`, planner→writer,
   per-step parallel query fan-out, JSON-action `{action,args,reason}`, terminate on done-or-cap.
   This IS the cheap path #7 routes to.

**Tier 3 — The retrieval upgrade (quality↑ at controlled cost):**
9. **NEW — single API-embedder neural lane (A1, B4):** wire the dead `embeddings` table; one API
   embedder (Cohere v3 / Voyage / OpenAI-3-large) for both retrieval + cache lanes; asymmetric
   `input_type`; `sqlite-vec`/numpy cosine. *No GPU, no TurboPuffer.*
10. **NEW — hybrid scoring (B4):** fuse BM25 + dense at `alpha=0.7`, top-30, **L1+L2 rerank**
    (Cohere `rerank-v3.5` or local `bge-reranker-v2-m3`), three-tier weights {0.75/0.60/0.40},
    compose status × tier weights. *No L3 XGBoost.*
11. **NEW — negation-guarded single-user semantic cache (A1.1):** SQLite `query_cache`, 0.92 cosine,
    LSH bucket, regex negation→miss, echo `_cache_*` fields. *No cross-tenant key.*
12. **NEW — default search cascade with fire-only-when-thin gating (A4.4):** Sonar Stage-1 (batch
    query) → Exa Stage-2 *only if thin* → Firecrawl/Exa-contents extraction *only for cited URLs* +
    Exa Highlights for >8k-char pages. *One premium provider per tier; fallback tiers are v2.*

**Tier 4 — The quality + grounding loop (quality↑, gated on cost):**
13. **NEW — Haiku clarifier (≤3 Qs, default-proceed)** before stage 1; skipped in `--auto`.
14. **NEW — Stage 11.5 single-call 5-axis grader loop (≤5 revisions)**, gated to full tier; findings
    join the critic findings → patcher → re-grade. *No ensemble judge, no 20-cap.*
15. **NEW — CitationAgent re-grounding pass (Haiku):** verify every `[N]`/`[[note-id]]` resolves +
    supports its sentence, before finalize. Per-sentence single-index `[N]` render, no `## References`.
16. **KEEP — adversarial 4-critic + patcher loop** (full tier), the readability/polish stages, the
    citation-density floor.

**Tier 5 — Out-of-pipeline (not a user-run cost):**
17. **NEW — 20-query calibration harness + RACE 5-axis judge:** run our replica vs the frontier DR
    products' APIs, score both, close the gap. The CLAUDE.md CALIBRATE step.

**Everything else is v2** (DEFER list, C1): SearXNG/Tavily/Brave fallback tiers, AST/markdown
chunking + structural headers, `expand_symbols`, Dream entity enrichment, ActCache replay, BrowserUse
/AgentQL/Browserbase impls, the editable plan-gate, `execute_python`, line/char-offset citation grain
+ per-claim confidence, RECITATION gate, ProgressEvent/SSE streaming, the MCP + standalone faces,
LiteLLM escape hatch, hybrid packaging.

**The lean guarantee.** v1 adds **one new SQLite table** (`query_cache`), **one activated table**
(`embeddings`), **a handful of `cache_control` stamps**, **one model-routing config table**, **one
budget meter**, **one query router + one agentic-loop branch**, and **three gated LLM passes**
(clarifier, grader, citation-agent) — all behind the existing Claude-Code-skill shape. No GPU, no
hosted vector DB, no sandbox infra, no gateway, no ensembling. Every ENHANCE earns its tokens; every
CUT is infra that doesn't amortize or quality that doesn't return its cost at single-operator scale.

---

*End of 09_SPEED_COST_CURATION.md. Reads 01–06 (on disk) + 07/08 themes (via 05§4/§6, 06§A1/§A2)
+ teardowns HYPERRESEARCH / NIA / CLAUDE_CODE / PERPLEXITY_DEEP / CLAUDE_RESEARCH / EXA / TAVILY /
FIRECRAWL / BROWSERBASE / BROWSER_USE / AGENTQL / LITELLM. Curation matrix: 99 patterns →
54 ENHANCE / 25 DEFER / 20 CUT. The lean v1 feature set (C3) is the build order for the design plan.*
