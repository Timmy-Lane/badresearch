# 11 — Corpus Sweep: Net-New Patterns the 01–10 Dossiers Missed

**Scope.** A deliberate sweep of the *rest* of the corpus — `core/` cross-cutting
research and the `teardowns/` that the prior dossiers never mined — to surface
**genuinely net-new** research-loop / context-engineering / retrieval / grounding /
scraping / orchestration patterns worth folding into the enhanced **hyperresearch**
fork. Every pattern ends in an explicit **ADOPT** (with where it plugs into the
Python core / skill stages / retrieval engine, and v1-vs-v2) or **CUT** (with reason).

## 0. De-duplication ledger — what 01–10 already cover (and I therefore skip)

I read the section maps of all six existing dossiers (01_FOUNDATION, 02_WEB_SEARCH,
03_BROWSE_EXTRACT, 04_NIA_STACK, 05_DR_LOOPS, 06_CROSSCUTTING_PACKAGING — the named
"07–10" topics, quality-filter / grounding / speed-cost / scraper, are subsections of
05 and 06) and grepped them for every candidate pattern below. Already-covered, **skipped**:

| Topic | Covered in | So I do NOT re-derive |
|---|---|---|
| Tavily / Exa / Firecrawl / Perplexity-Sonar search APIs, RRF, progressive rerank ladder, query-biased extraction | 02 §1–6 | provider cascade, fusion math, neural-vs-keyword |
| Browserbase/Stagehand `act/extract/observe`, AgentQL AQL, Browser-Use indexed-DOM, crawl4ai | 03 | agentic browse + typed extraction |
| NIA two-embedder, AST-header-in-chunk, hybrid `alpha`/three-tier fusion, L2 semantic cache, Oracle JSON-ReAct, Dream cycle | 04 | NIA retrieval primitives |
| 5 DR loops (OpenAI/Gemini/Perplexity/Grok/Claude): clarifier, plan-gate, parallel subagents (Claude fan-out, 4-field delegation contract, effort-tier caps 3/10/20/30, 300s timeout), termination, eval/grader, budgets, **CitationAgent re-grounding pass**, Gemini byte-span grounding + RECITATION gate, progressive narrowing | 05 | the entire frontier DR loop comparison |
| Citation/provenance standard, eval/grading loop, **memory/context-rot (TodoWrite-as-program-counter, compaction-evicts-procedure)**, cost/budget, streaming protocol, model-provider abstraction, packaging | 06 | cross-cutting standards |

So the Claude multi-agent fan-out, CitationAgent, progressive narrowing, plan-gate,
effort-tier budgeting, RRF, and TodoWrite-as-PC are **out of scope here** — they're done.
This dossier only reports what those six files do *not* contain.

---

# Research-loop patterns

## R1 — Manus: planner-as-separate-module + dual-level plan (todo.md) — KNOWN

**Source:** `teardowns/MANUS.md` §2.1–2.3, verbatim from `x1xhlol/Manus Agent Tools & Prompt`.
Manus is **not** "LLM + tools." It is LLM + four upstream **modules** (Planner, Knowledge,
Datasource, +todo) that each emit *system-generated events* into one chronological event
stream the inner LLM consumes. Key mechanics:
- **Planner** runs as a separate model/service emitting **numbered pseudocode** plan steps
  with `{current step #, status, reflection}`. The agent LLM never writes the plan — it
  *reads* it. Plan is revised only when the objective changes; the agent is forbidden to
  finish until it reaches the final numbered step.
- **Two-level plan:** coarse external plan (Planner-owned numbered steps) + fine internal
  `todo.md` checklist (agent-owned, on disk, ticked via `file_str_replace`). Rebuild todo.md
  when the planner revises.
- **Single tool call per iteration** (step #4: "Choose only one tool call per iteration") —
  linear, deterministic, replayable trace.

**ADOPT (v2, partial).** hyperresearch already has a fixed 16-stage pipeline + TodoWrite-as-
program-counter (06 §A3), which is functionally the *coarse* plan. The net-new idea is the
**separating of plan-authorship from execution**: a small dedicated **planner pass** that
emits numbered pseudocode the orchestrator merely *executes and reflects against*, rather than
the orchestrator re-deriving its plan each turn. For an *agentic-mode* hyperresearch run
(05 §9.2 already proposes one), bolt a planner stage that emits `{step_no, action, status,
reflection}` events and a disk `todo.md` distinct from the stage list. The "one tool call per
iteration" discipline is **CUT** — our pipeline benefits from parallel fan-out (05), the
opposite bet, and Manus chose linearity for UI-replay, not quality.

## R2 — Anthropic multi-agent research: artifact system + tool-testing agent + token economics — KNOWN

**Source:** `core/09_FRONTIER_AGENTIC_SYSTEMS.md` §6.1 (Anthropic "Multi-Agent Research System" blog).
Three bits *not* in dossier 05's Claude coverage:
1. **Artifact system.** Subagents do **not** funnel all output through the lead agent. They
   "create outputs that persist independently … store work in external systems, pass
   lightweight references back." The lead synthesizes from references, not raw payloads.
2. **Tool-testing agent.** A specialized agent "attempts to use the tool and then rewrites the
   tool description to avoid failures … found key nuances and bugs." Result: **40% decrease in
   task-completion time**. This is a *self-improving tool description* loop.
3. **Token economics (the load-bearing number):** single-agent = 4× chat tokens; multi-agent =
   **15× chat tokens**; **token usage explains 80% of performance variance** on BrowseComp.
   Resource scaling: simple fact = 1 agent / 3–10 calls; comparison = 2–4 subagents / 10–15
   calls; complex = 10+ subagents.

**ADOPT (v1 for #1, v2 for #2).** #1 the **artifact system** is the single cheapest win and
hyperresearch *already* has the substrate for it: the vault. Today, depth-investigators return
findings text up the chain (05); instead, have each subagent **write its findings as a vault
note and return only the `[[note-id]]`** — the orchestrator synthesizes from note IDs, raw
pages never re-enter the orchestrator context. This is the artifact system expressed as vault
notes; it caps orchestrator context growth at O(num_subagents) references rather than
O(num_subagents × findings_size). **v1.** #2 the tool-testing/description-rewrite loop is
**v2**: at provider-registration time, run each new `WebSearchProvider`/`ExtractProvider`
(02/03) through a 1-shot "call it, read the error, rewrite its description" pass and cache the
improved description. Worth it once we have >5 providers; overkill at launch. #3 the
"80%-of-variance is tokens" insight is **ADOPT as a design axiom** (not code): the budget
controller (06 §A4) should spend its budget on *more subagents/sources*, not bigger models —
this validates hyperresearch's per-locus 40-source budget over a single huge-context call.

## R3 — Cursor / Devin: agentic retrieval as a sub-agent (Deep Search) — KNOWN

**Source:** `teardowns/CURSOR.md` §7.7 (`DeepSearchSubagentParams/ReturnValue`,
`DeepSearchStream`) + `teardowns/DEVIN.md` §14.9 (`<semantic_search>` returns "explanation notes").
Both products do **multi-hop retrieval as its own ReAct sub-agent**, not a one-shot
embed→search→rerank:
- Cursor: `DeepSearchSubagent{query, max_iterations, scope}` runs its own loop
  search→read→search-again→read-again→synthesize, returns `{summary, cited_files, raw_chunks}`,
  streams progress ("looking through 47 files…"). This is why `@codebase` queries take 10+ s.
- Devin: `semantic_search` returns "relevant repos, code files, **and explanation notes**" —
  i.e. retrieval candidates + an LLM pass that explains *how the snippets relate to the query*.
  LLM-augmented retrieval, not raw top-k.

**ADOPT (v2).** hyperresearch's depth stage (per-locus investigators) is *already* multi-hop
fan-out (05 §2). The net-new refinement is the **`{summary, cited_ids, raw_chunks}` return
contract** + **LLM explanation notes** per retrieval: when a depth-investigator queries the
vault/web, return not just chunks but a one-paragraph "why these support the locus" note that
becomes part of the synthesis context. Cheap quality lift, but it's a refinement on an existing
stage → **v2**. The `max_iterations + scope` knob is already covered by Claude's tool-call caps
in 05 (skip).

## R4 — Devin: writer↔reviewer feedback loop ("closing the agent loop") — KNOWN

**Source:** `teardowns/DEVIN.md` §R3.4 (`cognition.ai/blog/closing-the-agent-loop`).
A *second* agent instance reviews the first's output, the writer auto-fixes the reviewer's
comments, loop continues until the reviewer signs off — *before* any human attention is spent.
Devin tracks comment-by-comment state (`done`/`outdated`). Cognition notes this "massively
increased internal token spend" but the quality justified it.

**ADOPT (v1, light).** This is the eval/grader loop (06 §A2, 05 §6) but **as a separate
reviewer agent with its own context, not a self-critique in the same context**. hyperresearch's
polish-auditor (Stage 16) is self-critique; the net-new move is a *fresh-context* reviewer that
reads only `(final_report, source_notes)` and emits structured comments the synthesizer then
addresses, looping until clean. Fresh context = no anchoring to the writer's reasoning. Cap at
2–3 review rounds (cost). Pairs naturally with the CitationAgent (05 §4) which is already a
fresh-context grounding pass — this generalizes it to *quality*, not just citations. **v1.**

---

# Context-engineering patterns

## C1 — Manus KV-cache discipline (the #1 production metric) — KNOWN

**Source:** `core/09_FRONTIER_AGENTIC_SYSTEMS.md` §2.4 (Manus "Context Engineering" blog).
**Not in any dossier.** KV-cache hit rate is "the single most important metric for a production
agent." Numbers (Claude Sonnet): cached input **$0.30/MTok** vs uncached **$3.00/MTok** = **10×**;
average prefill:decode ratio **100:1**. Rules:
1. **Stable prompt prefixes** — a single-token change invalidates all downstream cache.
2. **No second-precision timestamps** in the system prompt (kills cache every request).
3. **Append-only context serialization** (never edit earlier turns in place).
4. **Deterministic JSON** (stable key ordering) for all tool args/results.
5. **Explicit cache breakpoints** when the framework lacks auto incremental prefix caching.
6. **Session-ID routing** for consistent worker affinity (vLLM).

Companion: `core/06_AGENTIC_ARCHITECTURES.md` §14.12 — **sub-agent KV-cache sharing**: forked
subagents inherit the parent's byte-identical prefix → **90% cache discount** on shared context.

**ADOPT (v1 — highest enhance-per-cost).** This is a free 10× cost win that costs *engineering
discipline, not features*. Bake into the Python core's prompt-assembly layer: (a) emit the
system prompt + stage instructions as a frozen prefix per stage, (b) inject the date/run-id
once at a fixed slot, never mid-prompt with second granularity, (c) serialize all vault notes
and tool results with `json.dumps(…, sort_keys=True)`, (d) when fanning out subagents (05),
construct each child request so the **shared system + task preamble is byte-identical** across
siblings to trigger the 90% shared-context discount. Anthropic prompt-caching breakpoints map
directly. **v1.** It's the cheapest item in this whole dossier.

## C2 — Observation masking (JetBrains) — KNOWN

**Source:** `core/06_AGENTIC_ARCHITECTURES.md` §5.3 (JetBrains research). **Not in any dossier.**
Strategy: keep full action+reasoning history, **mask older tool *observations* with
placeholders**, retain the recent ~10 turns of full observations. Result: **52% cost savings
with a +2.6% solve-rate *improvement*** — and it beat LLM summarization in 4 of 5 settings. Why:
old tool outputs are rarely re-read, but old reasoning/actions still inform decisions; masking
the observations removes the biggest token consumer without losing decision context.

**ADOPT (v1).** This is a better compaction primitive than summarization for our agentic-mode
loop and for long width-sweeps. In the context manager: tag every context entry as
`reasoning|action|observation`; when over budget, replace observations older than N=10 turns
with `[observation masked: <tool> on <target>, see vault note [[id]] if needed]` rather than
summarizing the whole window. It's strictly cheaper than an LLM-summary compaction call (no
extra model call) *and* higher quality per the benchmark. Pairs with C1 (masking preserves the
stable prefix). **v1** — drop-in replacement for any naive "summarize old turns" step.

## C3 — ACON: failure-driven context-compression guidelines — KNOWN

**Source:** `core/09_FRONTIER_AGENTIC_SYSTEMS.md` §2.5 (academic, Oct 2025). **Not in dossiers.**
Given paired trajectories where *full* context succeeds but *compressed* context fails, an LLM
analyzes the cause and **updates the compression guidelines** to protect that specific
information type. Result: **26–54% memory reduction at 95%+ preserved accuracy.** Not "summarize
better" — "learn *which* information classes compression keeps losing, then never compress those."

**ADOPT (v2).** A self-tuning layer on top of C2. v1 ships observation-masking with a static
"never mask: numbers, source URLs, contradictions, the active locus" rule. v2 runs the ACON
loop offline against our own calibration traces (where compressed-context answers diverged from
full-context answers) to *learn* the protect-list. Net-new, but only valuable once we have a
trace corpus → **v2**.

## C4 — Manus: file-system-as-memory with restorable compression — KNOWN

**Source:** `core/09` §2.4 + `teardowns/MANUS.md` §5.1–5.2. **Net-new framing.**
Treat the filesystem as unlimited, persistent, directly-operable context. The model
writes/reads files on demand; supports ~50 tool calls/task without context overflow. The key
discipline: **compression must remain *restorable*** — you may drop a web page's *content* from
context but you **must preserve its URL**; you may drop a file's body but **preserve its path**.
On compaction/context-reset, the agent re-reads its own `todo.md` + saved files to reconstruct
state. "Save retrieved data to files instead of outputting intermediate results."

**ADOPT (v1, mostly already there — close the gap).** hyperresearch's vault *is* a file-system-
as-memory (every source = a markdown note), so 80% of this is done. The net-new **discipline**
to enforce: when the context manager evicts a fetched page, it must leave behind a restorable
stub `{url, vault note-id}` so a later stage can re-fetch/re-read rather than re-search. Add a
hard rule to the compaction step: *never drop a source's URL or its vault note-id, even when
dropping its body.* This is the "restorable compression" invariant; it prevents the classic
failure where a compacted run "forgets" it already found a source and re-pays to find it. **v1.**

## C5 — Devin: "context anxiety" bookend prompts (Sonnet 4.5+) — KNOWN

**Source:** `teardowns/DEVIN.md` §R3.12 (`devin-sonnet-4-5-lessons` blog). **Not in dossiers.**
Sonnet 4.5 is "the first model aware of its own context window" — it proactively summarizes as
it nears the limit. Failure mode: **"context anxiety"** — it takes shortcuts / leaves tasks
incomplete when it *believes* it's near the end, even with plenty of room. Fix: **bookend
prompting** — remind the model *both* at the start *and* at the end of the prompt that "the
context window is large; do not take shortcuts; finish thoroughly," plus mid-conversation
reminders. Cognition reports planning +18%, end-to-end +12% from these reminders.

**ADOPT (v1, trivial).** If the enhanced fork runs on Claude (the Anthropic-first seam), add a
two-line bookend to the synthesis/long-running stages: a head reminder and a tail reminder
("budget is ample; complete every locus; do not abbreviate"). Costs ~30 tokens, measurably
lifts thoroughness on multi-hour runs. **v1.** Model-specific (Sonnet 4.5/4.6) — gate behind the
model-provider abstraction (06 §A6).

## C6 — Multi-agent compaction is *mathematically required*, not optional — KNOWN

**Source:** `core/09` §2.7 (Phase Transition paper, Jan 2026). **Not in dossiers.**
Star topologies (one lead, N flat workers) **saturate at ~`N ≈ W/m`** agents (W = context
window, m = per-agent message size). Hierarchical trees bypass this: each aggregation node
enforces `b·m ≤ W` locally → `N = b^L` total agents across depth L. **Compaction at each
aggregation level isn't a nicety — it's the constraint that lets the system scale at all.**

**ADOPT as design axiom (not code).** Validates hyperresearch's *batched, synchronous* fan-out
(05 §2: parallel within a batch, batches sequential, orchestrator synthesizes between) over a
naive "spawn 50 workers into one lead context." If we ever raise the subagent cap past
~`W/m`, we must go hierarchical (lead → 2–3 aggregators → workers) with compaction at the
aggregator. Note in the orchestrator design; no v1 code change (current caps are below
saturation). **Axiom, not feature.**

## C7 — Harness engineering: progress-file + feature-list-with-`passes:false` — KNOWN

**Source:** `core/09` §2.6 (Anthropic "Effective Harnesses for Long-Running Agents").
Two-agent pattern: an **Initializer** creates `init.sh`, `claude-progress.txt`, a git baseline,
and a **feature list as JSON with 200+ items each `{description, steps[], passes: false}`**; the
**Coding agent** reads progress, does *one* feature/session, marks `passes: true` only after
end-to-end verification. The 200+-requirement list is the explicit defense against *premature
completion*; "it is unacceptable to remove or edit tests."

**ADOPT (v2, partial).** Mostly a coding-agent harness, but the **`passes:false` checklist as a
completion gate** transfers: for a deep research run, decompose the question into an explicit
list of *sub-claims to substantiate* `{claim, evidence_found: false}` and refuse to terminate
(05 §5 termination) until every claim is either substantiated-with-citation or explicitly marked
"could not substantiate." This is a stronger termination contract than "coverage heuristic." The
research analogue of "don't mark done until every test passes." **v2** (refines an existing
termination stage).

---

# Retrieval patterns

## RT1 — Glean: 7-signal learned ranker + recency-decay + DSS span extraction — KNOWN

**Source:** `teardowns/GLEAN.md` §3.2, §7, CE.2, CE.3. The richest net-new retrieval material.
Glean's hybrid ranker combines **seven explicitly-weighted signals**, fused by a *learned linear
model* (LambdaMART-class GBDT on click data), with a cross-encoder rerank on only the **top-50**:

| Signal | Mechanism | Per-query tuning |
|---|---|---|
| Semantic | dual-encoder dense, top-256 by cosine | ↑ for conceptual queries |
| Lexical | BM25, exact-phrase + field-restricted | ↑ for entity/code/ID queries |
| Recency | **decay `exp(-t/τ)`, τ per source class** (chat: hours; eng docs: months) | ↑ when query implies "current" |
| Authority | PageRank-like graph centrality over doc→references-doc, weighted by owner seniority | ↑ for policy questions |
| Popularity | rolling-window access count (7/30/90 d) | ↑ for definitional queries |
| Link structure | doc→doc reference graph | ↑ for canonical-source queries |
| Personal affinity | per-user affinity to author/project/channel | always on |

Then **DSS (Document-Span-Selection)** (CE.3, same pattern as Harvey's `gpt_5_dss` flag): after
rerank, a *small extractor LLM* (Gemini Flash / nano-class) returns
`[(chunk_id, char_start, char_end, why_relevant), …]` selecting only spans that *directly*
support an answer. The synthesis LLM then receives **only the extracted spans + offset citation
markers**, not full chunks. Effect: lower token cost, exact byte-range citation traceback, and
prevention of paraphrase-into-hallucination. (Permission-aware retrieval applies the user ACL as
a **hard filter at query time** — relevant only for our private-vault multi-user case.)

**ADOPT — three sub-patterns, ranked.**
1. **DSS span extraction (v1).** This is the strongest net-new retrieval idea. hyperresearch
   retrieves chunks then hands them whole to the synthesizer. Insert a cheap **span-extractor
   pass** between retrieval and synthesis: an LLM returns char-offset spans + `why_relevant`;
   synthesis sees spans + `[[note-id:offset]]` markers. This is the missing piece that makes
   our citations *byte-exact* (today the vault gives `[[note-id]]` granularity, no offsets — 05
   §4 explicitly flags "no line/byte-offset grain"). DSS closes that gap *and* cuts synthesis
   tokens. Pairs with the CitationAgent (05) — DSS is the *pre*-synthesis selection, CitationAgent
   is the *post*-synthesis verification; together they bracket the grounding problem. **v1.**
2. **Recency decay `exp(-t/τ)` with per-source-class τ (v1).** hyperresearch's retrieval (04,
   FTS5 + neural) has no recency signal. Add a recency multiplier `exp(-age/τ)` to the fused
   score, with `τ` keyed on source class (news: days; docs/papers: months; reference: ∞). Trivial
   to implement, materially improves "what's the current state of X" research queries. **v1.**
3. **7-signal learned ranker (CUT for now).** The full LambdaMART-over-click-data ranker needs a
   click-feedback corpus we don't have at launch. Authority/popularity/link-structure are
   enterprise-graph signals irrelevant to a general web+vault research tool. **CUT** the learned
   model; keep semantic + lexical + recency as a hand-weighted fusion (we already have RRF from
   02). Revisit if we ever accumulate usage signals.

## RT2 — Cursor: Merkle-tree incremental indexing — KNOWN

**Source:** `teardowns/CURSOR.md` §7.1–7.4 (`cursor-retrieval` bundle: `MerkleTree`,
`chunk_hash`, `rechunker`). Incremental re-indexing without re-embedding everything: hash every
file (content) and every chunk; build a Merkle tree (chunks=leaves, files/dirs=inner nodes);
on save recompute hashes up the tree; the client sends only **roots** to the server, which walks
down only where hashes differ and re-embeds **only changed chunks** (typically <100 even after a
big refactor). Two ignore files: `.cursorignore` (never send to AI) and `.cursorindexingignore`
(lexically searchable but not semantically embedded). `rechunker` re-processes when the chunking
strategy itself changes.

**ADOPT (v1 for the vault).** hyperresearch's vault re-indexing on every change is wasteful as
the vault grows across sessions. A Merkle-tree diff over vault notes → re-embed only changed
notes/chunks on each run. Concretely: store `chunk_hash = sha256(chunk_text)` per chunk; on
vault rebuild, skip embedding any chunk whose hash is unchanged. This is the cheapest way to make
the neural-vault upgrade (04) actually affordable across long-lived research projects — without
it, every session re-embeds the whole vault. The two-tier ignore (`searchable but not embedded`)
also maps cleanly to large pasted dumps. **v1** for the vault indexer.

## RT3 — Aider repo-map: PageRank-weighted tag index, 10× identifier boost — KNOWN

**Source:** `core/09` §7.7 #2. **Not in dossiers.** Aider builds a tree-sitter tag index
(symbols + references) into a NetworkX dependency graph and ranks files by **PageRank**, with a
**10× boost to identifiers currently mentioned in the conversation**. Produces a compact "repo
map" instead of dumping files.

**CUT.** This is a *code-context* primitive (symbol graphs over a codebase). hyperresearch is a
general web+document research tool, not a code-RAG agent. The "boost tokens already in the
conversation" idea is mildly transferable (boost vault notes containing the active locus's key
terms) but RT1's recency + our existing RRF already cover relevance well enough. **CUT** — wrong
domain, low marginal value.

## RT4 — Supermemory: multi-vector extraction, forgetting, dual-temporal grounding — KNOWN

**Source:** `teardowns/SUPERMEMORY.md` §15, §18. Beats Zep by +14.6pp on LongMemEval-S (81.6%
overall, GPT-4o). Net-new mechanics for a *persistent research vault*:
- **Multi-vector knowledge extraction:** ingestion extracts across **6 vectors** (Personal Info,
  Preferences, Events, Temporal Data, Updates, Assistant Info) — not one flat chunk per source.
- **Memory versioning with forgetting:** every memory has `isForgotten`, `forgetAfter`,
  `forgetReason`; `updateMemory()` creates a new version with `isLatest:false` + `parentMemoryId`
  + `rootMemoryId` for chain traversal. Memories *expire* and *supersede*.
- **Dual-layer temporal grounding:** `documentDate` (when written) + `eventDate[]` (when the
  event occurred) — distinguishes "stated on" from "happened on." Drives Temporal Reasoning
  (76.7% vs Zep 62.4%) and Knowledge-Update (88.5%) wins.
- **Three embedding slots per chunk** (`embedding`/`embeddingNew`/`matryoshkaEmbedding`) for
  **zero-downtime embedding-model migration**.

**ADOPT (v2, selective).**
- **Knowledge-Update / forgetting (v2):** the most valuable bit for multi-session research. When
  a new source *contradicts or supersedes* a vault note (hyperresearch already has contradiction
  detection — 04 §6.2, Stage 3), don't just flag it: mark the old note `superseded_by:[[new-id]]`
  and bias retrieval toward the latest version. This is exactly what beats full-context on
  Knowledge-Update. **v2.**
- **Dual-temporal `{documentDate, eventDate}` on every note (v1, cheap).** Add both fields to
  vault frontmatter; lets the recency decay (RT1) and temporal queries distinguish publish-time
  from event-time. Trivial schema add, real quality lift on "what was true as of <date>." **v1.**
- **Three-slot embeddings for zero-downtime migration (v2).** Only matters once we swap embedding
  models on a live vault; nice-to-have, not launch. **v2.**
- **6-vector extraction (CUT).** Their vectors (Preferences, Personal Info, Assistant Info) are
  *personal-assistant* memory categories, not research-document categories. **CUT** — wrong
  taxonomy; our extraction should be claim/entity/contradiction-oriented (already in 04/Stage 3).

## RT5 — Supermemory ASMR: multi-variant answer ensemble — KNOWN

**Source:** `teardowns/SUPERMEMORY.md` §15 (ASMR — explicitly a research "parody," NOT production).
**8-Variant Ensemble:** 8 distinct reasoning paths, marked correct if *any* reaches ground truth
→ 98.6% (this is a *ceiling* metric, not a usable selector). **12-Variant Decision Forest:** 12
GPT-4o-mini agents answer independently; an Aggregator LLM does **majority voting + domain-trust
weighting + conflict resolution** → 97.2% (this *is* a usable selector).

**CUT (with a v2 footnote).** The 8-variant "any path correct" is a benchmark-gaming ceiling, not
deployable (you don't know ground truth at inference) — **CUT**. The 12-variant decision-forest is
real but expensive (12× inference) and overlaps Grok-Heavy's debate-then-judge already analyzed in
05. Our budget axiom (R2 #3) says spend tokens on *sources*, not *N redundant answers*. **CUT for
v1.** Footnote: if a calibration run shows synthesis is the weak link (not retrieval), a 3-variant
majority-vote on the *final synthesis only* is a cheap v2 experiment — but don't build it
speculatively.

---

# Grounding patterns

## G1 — DeepWiki: per-sentence mandatory citation with empty-tag fallback — KNOWN

**Source:** `teardowns/DEEPWIKI.md` §D.5 (verbatim 63-line system prompt) + §D.5.1–D.5.2.
The strictest citation contract in the corpus — *stricter than dossier 05's recommended
standard*. Verbatim rules:
- **"Output a `<cite/>` tag after EVERY SINGLE SENTENCE and claim … Every sentence and claim MUST
  END IN A CITATION."**
- **"If you decide a citation is unnecessary, you must still output a `<cite/>` tag with nothing
  inside."** (the empty-tag fallback — no sentence escapes the contract).
- Format: `<cite repo="…" path="…" start="…" end="…" />`. **"Citations should span at most 5
  lines."** "DON'T CITE ENTIRE FUNCTIONS … use the MINIMUM number of lines needed."
- **Anti-speculation clause:** "Do not make any guesses or speculations … If you are unsure …
  say so, and indicate the information you would need." + "DO NOT MAKE UP ANSWERS."
- Output structure: `Answer` then a **`Notes` section** that disambiguates and explicitly
  mentions retrieved snippets that were *surface-similar but not used* (negative provenance).
- `<budget:token_budget>200000</budget:token_budget>` — explicit per-call token cap in-prompt.
- The rendering layer **mechanically enforces** that every sentence has a citation; un-cited
  sentences are rejected/low-confidence. That mechanical check, not just the prompt, is the moat.

**ADOPT (v1 — the citation upgrade).** hyperresearch's current standard is per-sentence wikilinks
(05 §4, 06 §A1) but with **no mechanical enforcement** and **no empty-tag-required rule**. Adopt
three concrete things: (1) **empty-tag-required fallback** — the synthesizer must emit a citation
marker after *every* sentence, an explicit `[[—]]` (no-source) marker if none applies, so a
post-pass can *count* and verify 100% coverage; (2) a **mechanical citation-coverage gate** in
the polish stage that rejects any report with un-cited declarative sentences (regex over the
rendered output, not an LLM call — cheap and deterministic); (3) the **5-line-max / minimum-span
rule** to stop "cite the whole note" laziness — pairs perfectly with RT1's DSS span extraction
(DSS *produces* the ≤5-line spans the citation rule *demands*). Also adopt the **Notes section
with negative provenance** ("similar but unused sources") — directly useful in research to show
what was considered and rejected. **v1** — this is the single biggest grounding upgrade available.

## G2 — DeepWiki: templated structure generator (TOC-from-corpus) — KNOWN

**Source:** `teardowns/DEEPWIKI.md` §D.2.4. A "table-of-contents generator" prompt takes the
repo summary + file tree and emits a **stable hierarchical structure** (Overview → Architecture →
Implementation → API → Testing → …) *customized to the content*, then a second pass fills each
section with cited prose + inline Mermaid (no colors, double-quoted labels — rendering invariants).

**ADOPT (v2).** This is hyperresearch's "Dream" / report-structuring analogue. The net-new bit is
**a dedicated structure-first pass** that emits the section skeleton from the gathered corpus
*before* writing prose, so the report has a stable, content-derived outline rather than a
free-form synthesis. hyperresearch likely already structures reports; if the calibration shows
structure drift, adopt the explicit two-pass (structure → fill). The Mermaid-diagram inline
generation (diagrams in the same LLM call as prose, with hard rendering rules) is a nice optional
output enhancement. **v2** — refinement, not a gap.

## G3 — Mintlify: `llms.txt` / `llms-full.txt` as a first-class research *input* surface — KNOWN

**Source:** `teardowns/MINTLIFY.md` §5.4, §6. Every Mintlify-rendered docs site serves
`/llms.txt` (curated index: title + `[Title](url.md): description` list), `/llms-full.txt` (entire
docs corpus concatenated as one markdown file), and per-page `.md` twins. This is the *de-facto AI
consumption standard* spreading across docs sites. Mintlify even sells an **"agent-readiness
grader"** (`leaves.mintlify.com/api/cli/score`) that checks a site for exactly this surface.

**ADOPT (v1 — scraper/sourcing enhancement).** The browse/scrape layer (03) should **probe for
`/llms.txt` and `/llms-full.txt` before falling back to HTML scraping** of any docs-like domain.
If present, `/llms-full.txt` is a *single clean-markdown fetch of the entire corpus* — zero
scraping, zero HTML cleanup, zero JS rendering, already chunked by heading. This is dramatically
cheaper and higher-quality than crawling. Add as the *first* tier of the fetch-routing waterfall
(02 §5b.5 / 03 §6): `llms-full.txt → llms.txt-indexed .md pages → Firecrawl → browser`. **v1** —
pure win for any documentation source, which research touches constantly.

## G4 — Mintlify: stable chunk IDs `sha1(path#heading-slug)` — KNOWN

**Source:** `teardowns/MINTLIFY.md` §9.6.4, §9.7.1. Chunks are keyed `id = sha1(path + '#' +
slug(heading))` so **citation deeplinks survive rebuilds** (`preserveAutoGeneratedMetadata`).
Chunking is **per-MDX-heading-section**, not fixed-token windows, with secondary paragraph split
only if a section exceeds ~1200 tokens.

**ADOPT (v1, cheap).** Combine with RT2's Merkle re-indexing: stable, content-addressed chunk IDs
(`sha1(source_url#heading)`) mean (a) re-indexing skips unchanged chunks by ID, and (b) citations
`[[note-id]]` stay valid across re-fetches of the same source. hyperresearch's vault note-ids
should be **content-derived and heading-anchored**, not sequential. Also adopt **heading-section
chunking** (which NIA already does for code via AST, 04 §2 — this extends it to prose/docs).
**v1** — small, foundational, makes RT2 + G1 both work.

---

# Scraping / sourcing patterns

## SC1 — Mintlify scraper: vendor-fingerprint → render-strategy routing — KNOWN

**Source:** `teardowns/MINTLIFY.md` §9.6.3 (`detectFramework.js`). Before scraping a docs site,
fingerprint the source vendor from HTML markers and route the fetch strategy accordingly:
- GitBook (`<link rel=preconnect href=api.gitbook.com>` / `<meta generator=gitbook>`) → **needs a
  real browser (Puppeteer)** because it's client-rendered.
- ReadMe (`<meta name="readme-deploy">`), Docusaurus (`<meta generator=docusaurus>`, version
  parsed; v1 rejected) → **SSR/static, scrape from raw HTML** (no browser needed).
- No vendor detected → hard fail (their migration is vendor-gated).

The principle: **detect render strategy from cheap HTML markers, escalate to browser only when the
vendor requires it.**

**ADOPT (v1).** The fetch-routing waterfall (02/03) already escalates fast→neural→browser, but
*reactively* (try cheap, fall through on failure). Mintlify's trick is **proactive routing from a
fingerprint** — saves a wasted cheap-fetch attempt on known-client-rendered platforms. Add a
lightweight `detect_render_strategy(html_head)` that checks for known SPA/CSR markers (GitBook,
Notion-hosted, heavy-JS-framework generator tags) and jumps straight to the browser provider,
skipping the doomed static fetch. Combine with G3 (`llms.txt` probe first). **v1** — modest
latency/cost win on the long tail of docs sites.

## SC2 — DeepWiki: repo-ingestion bounds + depth-1 clone — KNOWN

**Source:** `teardowns/DEEPWIKI.md` §D.2.1. `git clone --depth=1` (history not needed for docs),
plus explicit ingestion bounds: max repo size (~5–10 GB), max file count (~100k), skip large
binaries/lockfiles/generated artifacts, standard ignore patterns (`.git`, `node_modules`, `dist`,
`build`, `target`, `vendor`, `.next`).

**ADOPT (v1, when ingesting repos/large sources).** If the enhanced fork ever ingests a code repo
or a large doc tree as a research source (NIA-style — 04 already does this), the depth-1 +
size/count bounds + ignore-pattern filter is the obvious cost guard. Mostly already implied by
NIA's chunker; the explicit **bounds** (max size/count, skip generated/binary) are the net-new
guardrail to copy verbatim. **v1** for any repo-ingestion path; **N/A** if we never ingest repos.

---

# Orchestration patterns

## O1 — Devin: four-layer persistence (Knowledge / Playbooks / Skills / Notes) + Knowledge Suggestions — KNOWN

**Source:** `teardowns/DEVIN.md` §R3.3. Devin has **no single memory primitive** — four
overlapping stores at different granularities:
1. **Knowledge** — atomic key-value facts ("when deploying to staging, set `STAGING_ENV=true`"),
   read at session start, folder-organized, scoped org/enterprise.
2. **Playbooks** — natural-language multi-step *recipes*, triggered by `!playbook_name`.
3. **Skills** — *executable* code/scripts in `.agents/skills/` (version-controlled with the repo).
4. **Cross-session notes** — inter-run scratch notes (Schedule/Auto-Triage); "each run builds on
   the prior one rather than starting from scratch."
Critically: **Knowledge Suggestions** — at *session end* Devin **proposes new Knowledge entries**
for things it observed worth persisting (the auto-memory-write loop).

**ADOPT (v2, selective).** hyperresearch's vault is the document store; this is *procedural*
memory, a different axis. Two net-new ideas worth taking:
- **Knowledge Suggestions / end-of-run memory write (v2).** After a research run, a cheap pass
  proposes durable facts ("source X is authoritative for topic Y," "this claim was contested by
  A and B") to persist into a project-level `KNOWLEDGE.md` the next run reads at bootstrap. This
  is how cross-session research compounds. (NIA's Dream cycle (04 §6) is the document-enrichment
  analogue; this is the *fact/procedure* analogue.) **v2.**
- **Playbooks as `!name` research templates (v2).** Named reusable research recipes ("competitive
  teardown," "literature review") the user triggers — distinct from the prompt. Nice, not core.
- **Skills (CUT for research).** Executable per-repo scripts are a coding-agent concern. **CUT.**

## O2 — Devin: recursive single-agent ("agents-as-tools, not peers") — KNOWN

**Source:** `teardowns/DEVIN.md` §R3.10 (Walden Yan "Don't Build Multi-Agents"). The principles:
**"Share context, and share full agent traces, not just individual messages"** and **"Actions
carry implicit decisions, and conflicting decisions carry bad results."** Devin's "manage Devins"
reconciles this: the coordinator is a *single* coherent decision-maker with full visibility into
each managed-Devin's *full trajectory* (`read_child_trajectory`); managed-Devins are
narrow-scoped workers on clean-slate VMs — **heavyweight tool calls that happen to be agents, not
peers**. No peer-to-peer coordination.

**ADOPT as design axiom (validates the existing design).** This is the *opposite* governance
stance to Anthropic's parallel subagent fan-out (05) — and it explains *why* hyperresearch's
synchronous-batch fan-out (orchestrator synthesizes between batches, workers don't talk to each
other) is correct: workers are tools, the orchestrator is the single decision-maker. The one
*actionable* net-new bit: **"share full traces, not just messages"** — when a subagent fails or
returns thin results, the orchestrator should see the worker's *trajectory* (what it searched,
what it read), not just its final summary, so the next batch doesn't repeat the same dead-end.
Today (05) only the final `tool_result` crosses back. Adding an optional *failed-trajectory
digest* on worker soft-fail (the 300s-timeout path) prevents re-searching dead ends. **v2**
refinement; the core stance is an **axiom** confirming current design.

## O3 — Mintlify: conversation bucketing for gap detection (the research-feedback loop) — KNOWN

**Source:** `teardowns/MINTLIFY.md` §9.5.2. A nightly job embeds every past query, **clusters**
them (HDBSCAN/agglomerative, cosine), and for each cluster an LLM emits a canonical
`questionSummary` + rolls up `size`, thumbs feedback, and an LLM-judged `resolutionStatus` ("did
the answer actually resolve the query given its sources?"). Output: *which questions the corpus
answers badly* — a documentation-gap detector.

**ADOPT (v2).** For a long-lived research project, this becomes a **research-gap detector**:
cluster the sub-questions a project has asked across sessions, judge which were
well-substantiated vs thinly-sourced, and surface "topics this project keeps asking about but
never resolved well" → drives the next research run's priorities. The LLM-judge `resolutionStatus`
("answer actually supported by sources?") is the same cheap temp-0 grader pattern as 05/06 and
G1's coverage gate. Genuinely net-new as a *meta-loop* over multiple runs, but needs a
multi-session usage history → **v2**.

## O4 — Sourcegraph Amp: script-tool toolbox (simpler than MCP) + AGENT.md self-extension — KNOWN

**Source:** `teardowns/SOURCEGRAPH_AMP.md` §7, §6, §12. Two bits:
- **Script-tool toolbox:** an executable that prints its JSON manifest when called with no args,
  then takes args as JSON-on-stdin and returns JSON-on-stdout. **No JSON-RPC handshake, no stdio
  framing** — one-shot exec per call. Strictly simpler than MCP for adding a tool.
- **AGENT.md self-extension loop:** the system prompt instructs the agent, when it *discovers* a
  useful command (e.g., the test command), to **proactively write it to AGENTS.md so it knows
  next time**. The agent improves its own context file.

**ADOPT (v2 for the toolbox; v1-axiom for self-extension).** The Anthropic-first fork already has
MCP (01 §1.6); the **script-tool pattern is a lighter alternative for user-added research tools**
(a one-file scraper, a custom API client) without MCP ceremony — worth it for the skill's
extensibility story, **v2**. The **AGENT.md self-extension** maps onto O1's Knowledge Suggestions
(same idea: agent writes durable context for its future self) — adopt the *principle* into the
end-of-run memory write (O1, v2). Don't build it twice.

---

# Net-new ADOPT shortlist (ranked by enhance-per-cost)

The handful genuinely worth adding. Ranked: cheapest-with-highest-impact first.

| # | Pattern | Source | Plugs into | v | Why it wins |
|---|---|---|---|---|---|
| 1 | **KV-cache discipline** (stable prefix, no s-precision timestamps, append-only, deterministic JSON, byte-identical subagent prefixes → 90% shared discount) | C1 (Manus / `core/09` §2.4, `core/06` §14.12) | Python core prompt-assembly + subagent dispatch | v1 | ~10× input-token cost cut for *engineering discipline, zero new features*. Cheapest item here. |
| 2 | **DSS span extraction** (extractor LLM returns char-offset spans + `why_relevant`; synthesis sees spans not full chunks) | RT1 (`GLEAN.md` CE.3) | new stage between retrieval and synthesis | v1 | Byte-exact citations (closes 05's "no offset grain" gap) + lower synthesis tokens. Feeds G1's 5-line rule. |
| 3 | **Per-sentence mandatory citation + empty-tag fallback + mechanical coverage gate + Notes/negative-provenance** | G1 (`DEEPWIKI.md` §D.5) | synthesis prompt + deterministic polish-stage check | v1 | Strongest grounding upgrade; the *mechanical* gate (regex, no LLM) is the moat, not the prompt. |
| 4 | **Observation masking** (mask tool observations >10 turns old, keep reasoning/actions) | C2 (`core/06` §5.3) | context manager / compaction | v1 | 52% cost cut **+2.6% solve-rate**; beats LLM-summary compaction, and no extra model call. |
| 5 | **`llms.txt` / `llms-full.txt` probe-first fetch tier** | G3 (`MINTLIFY.md` §5.4) | top of fetch-routing waterfall (02/03) | v1 | One clean-markdown fetch of an entire docs corpus; skips scraping/HTML/JS entirely. |
| 6 | **Recency decay `exp(-t/τ)` per source class** + **dual-temporal `{documentDate, eventDate}`** | RT1 #2 / RT4 (`GLEAN.md` §CE.2, `SUPERMEMORY.md` §15) | fusion scorer + vault frontmatter | v1 | Trivial add; real lift on "current state of X" and "true as of <date>" queries. |
| 7 | **Merkle-tree incremental re-indexing + stable `sha1(url#heading)` chunk IDs + heading-section chunking** | RT2/G4 (`CURSOR.md` §7, `MINTLIFY.md` §9.6.4) | vault indexer | v1 | Makes the neural-vault (04) affordable across long-lived projects; keeps citations valid across re-fetch. |
| 8 | **Artifact system** (subagents write findings to vault, return only `[[note-id]]`) | R2 #1 (`core/09` §6.1) | subagent return contract (05) | v1 | Caps orchestrator context at O(refs) not O(findings); near-free given the vault exists. |
| 9 | **Restorable-compression invariant** (never drop a source's URL / note-id even when dropping its body) | C4 (`MANUS.md` §5.2) | compaction rule | v1 | Prevents the "forgot we already found it → re-pay to re-search" failure. |
| 10 | **Bookend "context anxiety" prompts** (Claude only) | C5 (`DEVIN.md` §R3.12) | long-running stage prompts | v1 | ~30 tokens; measurable +12–18% thoroughness on Sonnet 4.5/4.6. |
| — | **v2 tier (build after v1 + calibration):** fresh-context reviewer loop (R4), knowledge-update/forgetting + supersede (RT4), ACON learned protect-list (C3), `passes:false` claim-substantiation gate (C7), end-of-run Knowledge Suggestions (O1), conversation/research-gap bucketing (O3), agentic-retrieval `{summary,cited_ids,notes}` contract (R3), planner-as-module for agentic mode (R1). | various | — | v2 | All net-new, all worth it, none needed at launch. |

**Deliberately CUT (net-new but overkill/wrong-domain):**
- **Glean 7-signal LambdaMART ranker** (RT1 #3) — needs a click-feedback corpus + enterprise-graph
  signals we don't have; keep semantic+lexical+recency hand-weighted.
- **Aider PageRank repo-map** (RT3) — code-RAG primitive, wrong domain.
- **Supermemory 8/12-variant answer ensembles** (RT5) — benchmark-gaming ceiling (8-var) or 12×
  redundant inference (12-var); our budget axiom spends tokens on sources, not N answers.
- **6-vector personal-memory extraction** (RT4) — personal-assistant taxonomy, not research.
- **Devin Skills / Manus one-tool-per-iteration / Devin VM-otterlink-blockdiff** — coding-agent /
  infra concerns, not a research-skill enhancement.

**Cross-cutting axioms (no code, but they validate / constrain the design):** R2 #3 (token usage
explains 80% of variance → spend budget on sources, not bigger models), C6 (multi-agent compaction
is mathematically required above `N≈W/m` → go hierarchical only if we raise caps), O2 (agents-as-
tools-not-peers + share-full-traces → confirms hyperresearch's synchronous-batch fan-out is right).
