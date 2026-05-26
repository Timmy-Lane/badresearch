# 05 — Deep-Research Loop/Control Patterns: Comparative Best-Of

**Purpose.** Extract the strongest deep-research **loop and control** patterns from the five frontier closed agents we reverse-engineered, comparatively, so we can augment the **hyperresearch** 16-stage fixed pipeline with the best ideas (clarifier, parallel subagents, citation standard, eval loop, budgets, an optional agentic mode).

**Sources (all rounds incl. R2/R3/R4):**
- `teardowns/OPENAI_DEEP_RESEARCH.md` (cited `[ODR §N]`) — 2,098 L, R1+R2.
- `teardowns/GEMINI_DEEP_RESEARCH.md` (cited `[GDR §N]`) — 2,433 L.
- `teardowns/PERPLEXITY_DEEP.md` (cited `[PPLX §N]` / `[PPLX §R3.N]`) — 3,742 L, R1+R2+R3.
- `teardowns/GROK_HEAVY.md` (cited `[GROK §N]`) — 2,153 L.
- `teardowns/CLAUDE_RESEARCH.md` (cited `[CLR §N]` / `[CLR §CE.N]`) — 1,648 L, R1+CE.
- `teardowns/HYPERRESEARCH.md` (cited `[HR Stage N]` / `[HR §N]`) — the base we are augmenting.

**Label key:** **KNOWN** = from leaked prompt / SDK contract / eng blog / verbatim source. **INFERRED** = cross-derived from behaviour/probes. **IDEA** = our engineering proposal for hyperresearch.

**The base we augment (hyperresearch):** a FIXED pipeline of 16 stages — decompose → width-sweep → contradiction-graph → loci → depth → cross-locus → source-tensions → corpus-critic → evidence-digest → triple-draft → synthesize → critics → gap-fetch → patcher → polish → readability. Two tiers: `light` (1→2→10→15→16) and `full` (all 16) `[HR §1 tier table]`. No clarifier, no user-approval gate, no grader-loop, no agentic-ReAct fast path, no test-time-compute dial. It IS already multi-agent (fetcher fan-out, 2 loci analysts, 3 draft orchestrators, 4 critics) and IS already provenance-disciplined (vault + per-sentence cites). The gaps it has are exactly the dimensions below.

---

## 0. The five architectures in one table (loop-control view)

| Dimension | OpenAI DR | Gemini DR | Perplexity DR | Grok Heavy | Claude Research |
|---|---|---|---|---|---|
| Control style | single-agent RL-learned loop | plan-gate → sequential per-step loop | step-bounded ReAct (planner→writer) | N parallel full instances + debate+judge | orchestrator → 1–20 parallel subagents |
| Planning | host clarifier (2-agent) | **user-editable plan + approval gate** | planner system A (no user gate) | orchestrator picks N | LeadResearcher decomposes |
| Parallelism | none (one trajectory) | parallel search *within* a step | parallel queries *within* a step | N=4/8/16/32 instances | 3–5 (≤10/batch, deep 20+) subagents |
| Termination | model-judged (RL "diminishing returns") | per-step coverage + 60-min wall | **`max_steps` hard cap 10** | max_turns ∨ 200s ∨ 1M-ctx ∨ debate-converge | soft 15 calls / 100 sources / 5-min subagent timeout |
| Citation grain | **line-level `【ref†L42-L58】`** | URL-level inline + byte-span grounding | per-sentence `[N]` + `Annotation` char-offsets | paragraph `<grok:render>` `[web:N]`/`[post:N]` | inline `[N]` + dedicated CitationAgent re-ground |
| Eval/grade | RL reward (offline) | RECITATION gate | (none in-loop) | debate-then-judge | **`define_outcome` LLM-judge, ≤20 revisions** |
| TTC dial | **Juice 512/1024, reasoning_effort 4-level** | per-tier query/token caps + Deep Think | citation/reasoning token accounting | N instances | token-budget = 80% of variance |
| Best at | citation discipline + reasoning depth | UX transparency + 1M ctx | cheap step-bounded retrieval | hardest reasoning (HLE 50.7%) | breadth coverage (+90.2%) |

**The thesis of this dossier:** no single product wins every dimension. The ultimate skill should **steal the per-dimension winner** and graft it onto the hyperresearch pipeline as either a new stage, a new mode, or a control knob. The map at the end (`§9`) assigns each winner to a concrete augmentation.

---

## 1. Planning / Clarification

### What each does

**OpenAI — the 2-agent clarifier (the winner for low-friction correctness).** OpenAI splits the system into a **host model** (4o-class, conversational) and a **worker** (o3-deepresearch). The host runs a `research_kickoff_tool` with exactly two methods `[ODR §5, §7]`:

```typescript
namespace research_kickoff_tool {
  type clarify_with_text   = (_: { question: string }) => any;   // ask user for detail
  type start_research_task = (_: { brief: string })   => any;    // kick off the worker
}
```

The host system prompt (verbatim, Feb-4-2025 leak `[ODR §5]`) makes the clarify-vs-go decision explicit and **biases toward research**:

> *"Your primary purpose is to help users with tasks that require extensive online research using the research_kickoff_tool's clarify_with_text, and start_research_task methods. If you require additional information from the user before starting the task, ask them for more detail before starting research using clarify_with_text… If you don't know about a concept / name in the user request, **assume that it is a browsing request and proceed**."* `[ODR §5]`

Model: host is **gpt-4o-mini / 4.1-class**; worker is o3. KNOWN. The clarify gate fires only on genuine ambiguity (acronyms, names, time-periods, unbounded scope `[ODR §18 designed host prompt]`); otherwise it distills a `brief` (1–3 paragraph paraphrase + scope + constraints) and hands off. The worker never sees the raw chat — only the brief `[ODR §15]`. This is a **clean two-stage handoff** and the takeaway #3 in their teardown: *"don't try to merge them"* `[ODR §20]`.

**Gemini — the user-editable plan + approval gate (the winner for steerability/transparency).** Gemini DR does NOT clarify with a question — it emits a **structured multi-step plan** (3–10 steps, each `{title, description, expected_evidence_types}`) rendered as an editable UI artifact, then **waits for explicit approval** `[GDR §5]`. The user can `[Edit plan]` (add/remove/reorder/rewrite steps) or `[Start research]`. Once started, the plan is **locked** — no mid-execution edits `[GDR §5 "can NOT edit mid-execution"]`. Plan is generated via constrained decoding (`response_schema`, INFERRED `[GDR §5]`). The teardown's #1 take-away: *"the plan-gate is the most copyable UX innovation in this space… hidden-plan agents leave users feeling they've lost control"* `[GDR §20]`.

**Perplexity — planner system A, no user gate.** Two-system architecture: a **planner/searcher** (system A) runs the loop, a **writer** (system B) synthesizes `[PPLX §R3.8]`. There is no user-facing plan; `[CORRECTION 2026-05-26: the `plan_approvals`/`collaborative_planning` params do NOT exist in the v0.34.0 SDK — downgraded to SPECULATIVE]` `[PPLX §R3.2]`. Planning is internal CoT, streamed as `reasoning.started{thought}` events.

**Claude — LeadResearcher decomposes, no user gate.** The orchestrator (Opus 4) reads the query, plans in extended-thinking scratchpad, then emits delegation. No clarify, no plan-gate — *"the orchestrator decides delegation autonomously… a UX bet (less friction) trading off transparency"* `[CLR §CE.8]`.

**hyperresearch — Stage 1 decompose, no clarifier.** Decompose extracts atomic items in 7 categories, populates `required_section_headings` (*"single highest-leverage field for instruction-following"* `[HR Stage 1]`), classifies tier/format/citation-style, and runs a coverage-matrix self-audit to zero gaps. This is a **decomposition**, not a clarification — it never asks the user anything; the canonical query is GOSPEL.

### Winner + what to adopt

**Adopt OpenAI's clarifier mechanism AND Gemini's plan-gate, layered, both OPTIONAL.** They solve different problems:
- OpenAI's clarifier fixes **ambiguity** (wrong topic → wasted $60 full run). One cheap gpt-4o-mini-class call, fires only on detected ambiguity, default-to-proceed. **This is the higher-ROI of the two for hyperresearch** because a full run costs $60–120 `[HR §1]` and an ambiguous query wastes all of it.
- Gemini's plan-gate fixes **scope/structure** (over/under-scoped plan). hyperresearch already produces a structured plan in Stage 1 (`required_section_headings`, `sub_questions`, tier) — surfacing *that* for approval is nearly free.

**Concrete adoption (IDEA):** insert a **Stage 0.5 — Clarify+Plan-Gate** between bootstrap and Stage 1, controlled by a flag (`--interactive` / `--auto`):
- Run a Haiku-class clarifier on the verbatim query. Use OpenAI's verbatim bias: ambiguous → emit ≤3 clarifying questions; else proceed silently. Verbatim principle to copy: *"If you don't know about a concept/name… assume it is a browsing request and proceed."*
- After Stage 1 decompose, if `--interactive`, render the decomposition JSON (`required_section_headings` + tier + `response_format`) as a Gemini-style editable plan; gate on approval; lock on start. In `--auto` (benchmark/wrapped) mode, skip the gate entirely (the wrapper contract is GOSPEL — matches hyperresearch's existing `research/prompt.txt` GOSPEL rule `[HR bootstrap]`).

**Constants to copy:** clarifier model = gpt-4o-mini / Haiku-class; max clarifying questions = 3; plan steps 3–10 (Gemini) — but hyperresearch's `required_section_headings` (4–7 for narrative `[HR Stage 1]`) already matches this band.

**Reimplementable clarifier prompt (IDEA, structurally derived from `[ODR §5]`):**
```
You are a research-intake assistant. Decide whether the user's query is ready for an
expensive autonomous research run, or whether ONE round of clarification would materially
improve the result.

Clarify (emit 1-3 questions) ONLY if the query has: ambiguous acronyms/names (which "Mercury"?),
unbounded scope ("tell me about X" with no constraint), or an undefined time window.
DEFAULT TO PROCEED: if you don't recognize a concept/name, assume it is a browsing request and
proceed — do NOT ask the user to define it. Never ask more than 3 questions.

Output JSON: {"action": "clarify"|"proceed", "questions": [...], "brief": "<1-3 para distilled
research question with scope + constraints>"}.
Today's date is {date}. Query: {query}
```
The `brief` field is OpenAI's exact handoff payload `[ODR §6 step 3]` — in hyperresearch it becomes the GOSPEL `research/query-<vault_tag>.md` content.

---

## 2. Decomposition + Parallel Subagents

### What each does

**Claude — orchestrator → 1–20 subagents (the winner; the reference design).** This is the most precisely-documented fan-out in the field. Mechanics `[CLR §3–7, §CE.2, §CE.5]`:
- **Depth-1 fan-out:** LeadResearcher (Opus 4) spawns SubAgents (Sonnet 4) that do NOT spawn their own subagents. Flat, one level. The orchestrator does *not* itself browse — its `web_search` is a clarification safety-valve only `[CLR §6]`. This is what makes the fan-out actually parallel.
- **`batch` = `parallel()`:** the orchestrator emits **N `delegate_subagent` tool_use blocks in a single assistant turn** `[CLR §CE.2, §CE.13]`. The harness dispatches all N concurrently, each as a fresh Messages-API conversation with its own context window. Only the final `tool_result` (findings text) crosses back — raw pages never reach the orchestrator `[CLR §CE.13 obs.1]`. Older models (3.5 Sonnet) emit one tool_use/turn; Sonnet 4 / Opus 4 emit many — that capability IS the fan-out.
- **Type-disciplined delegation (4-field contract, KNOWN verbatim):** every subtask must specify `{objective, output_shape (or output_format), tools_allowed, stop_conditions}` `[CLR §CE.2, §6 principle 2]`. Skipping any field is a documented failure mode (vague task → misinterpretation `[CLR §14 #4]`).
- **Effort tiers (the count + budget rule, KNOWN/reconstructed `[CLR §CE.5]`):**

  | Tier | Signal | Sub-agents | Tool-calls/sub-agent | Total token budget |
  |---|---|---|---|---|
  | Simple | single fact | 1 | 3–5 | ~20K |
  | Standard | multi-fact, single domain | 3–5 | 5–10 | ~150K |
  | Complex | multi-domain, comparative | 10–15 | 10–20 | ~1.5M |
  | Deep | open-ended | 20+ (multi-round) | 15–30 | ~5M |

  Default 3, max 20 (max_parallel_subagents=10 per *batch*, multiple batches → 20+ `[CLR §CE.1 rule iv, §CE.10]`).
- **Worker tool-call caps (hard, runtime-enforced):** per-tier hard caps **3 / 10 / 20 / 30** tool calls `[CLR §CE.5, §CE.10]`; soft "<5" for simple lookups. Per-subagent **timeout 300s** → soft-fail with accumulated findings `[CLR §CE.3, §CE.10]`.
- **Synchronous batches:** fan-out is parallel *within* a batch, batches are sequential `[CLR §3]`. The orchestrator synthesizes round 1, decides if gaps remain, spawns round 2. This is a deliberate cost equation, not a bug — async would scale context cubically (O(depth×fanout×ctx)) `[CLR §CE.3]`.
- **The payoff:** +90.2% over single-agent Opus 4; token usage alone explains **80%** of performance variance, tokens+tool-calls+model = **95%** `[CLR §11–12]`.

**Perplexity — planner→writer split (the winner for the synthesis-handoff).** Not subagent fan-out for *search*, but the **clean two-system split**: planner (system A) runs the search→read→reason loop and accumulates `search_results`; writer (system B) receives the *ranked results, NOT the planner's raw CoT*, and produces self-contained cited prose `[PPLX §R3.8]`. Verbatim writer-prompt evidence:

> *"Another system has done the work of planning out the strategy… issuing search queries, math queries, and URL navigations… The user has not seen the other system's work, so your job is to use their findings and write an answer… your answer must be self-contained."* `[PPLX §R3.8]`

This is the same separation hyperresearch already has (Stages 1–9 = planner-equivalent, Stages 10–11 = writer-equivalent) — Perplexity confirms the pattern is correct: **the writer must NOT see the planner's reasoning, only the ranked evidence.**

**Per-locus fan-out idea — where hyperresearch already leads.** hyperresearch's depth stage (Stage 4→5) is *exactly* per-locus fan-out: 2 loci-analysts read the corpus in parallel, the orchestrator merges/clamps-to-6/scores on 4 dims (importance/uncertainty/disagreement/decision_impact, max 40), allocates a **40-source budget proportionally** (composite 30–40 → ≤15 sources; 20–29 → ≤10; 10–19 → ≤5; <10 → skip), then spawns **one depth-investigator per locus with budget>0, capped at 6** `[HR Stage 4]`. This is *Claude's effort-tier budgeting applied per-locus* — hyperresearch invented it independently. The width-sweep (Stage 2) also fans out 10–12 fetchers in one message, zero batch overlap `[HR Stage 2.4]`.

### Winner + what to adopt

**Winner for the general primitive: Claude (the 4-field delegation contract + effort-tier caps + depth-1 batch=parallel). Winner for the synthesis handoff: Perplexity (planner→writer, writer sees evidence not CoT).**

hyperresearch already does fan-out well, but it is missing **two Claude mechanisms**:
1. **Hard, runtime-enforced per-subagent tool-call caps + timeouts.** hyperresearch caps *source counts* (Stage 2 targets) and *investigator counts* (≤6) but does NOT impose a per-subagent tool-call ceiling or a 300s timeout. Add Claude's tier caps (3/10/20/30) and 300s soft-fail to every fetcher/investigator Task. **IDEA.**
2. **The explicit 4-field delegation contract as a validated schema.** hyperresearch's subagent spawn contract (`[HR §subagent spawn contract]`) requires the verbatim query + pipeline-position + inputs, but not Claude's `{objective, output_shape, tools_allowed, stop_conditions}`. Add `stop_conditions` and `output_shape` to every Task — this is the single field that prevents "endless web searching for nonexistent sources" `[CLR §14 #2]`. **IDEA.**

**Adopt Perplexity's writer-isolation explicitly:** hyperresearch's synthesizer is already `[Read, Write]`-locked and told *"do not paste paragraphs from input drafts"* `[HR Stage 11]` — confirm it receives evidence-digest + drafts, NOT the orchestrator's CoT. It does. Keep this.

**Reimplementable delegation contract (IDEA, Claude `[CLR §CE.2]` + hyperresearch spawn rules `[HR §subagent spawn contract]` fused):**
```json
{
  "name": "delegate_subagent",
  "input": {
    "research_query":   "<verbatim block-quoted GOSPEL query>",   // hyperresearch rule
    "pipeline_position":"you are step N; step N-1 produced X; step N+1 will do Y", // hyperresearch
    "objective":        "<single self-contained sub-objective>",   // Claude field 1
    "output_shape":     "<exact return format, e.g. 'JSON array of {claim, note_id, quoted_support}'>", // Claude field 2
    "tools_allowed":    ["web_search","fetch_url","execute_python"], // Claude field 3
    "stop_conditions":  "<when to halt, e.g. 'when 3 primary sources found OR 10 tool calls used'>", // Claude field 4
    "tool_call_cap":    10,        // runtime-enforced (Claude tier cap)
    "timeout_s":        300        // runtime soft-fail (Claude)
  }
}
```
The two missing-from-hyperresearch fields are `stop_conditions` (prevents endless search `[CLR §14 #2]`) and `tool_call_cap`/`timeout_s` (runtime guards, not prompt hopes).

---

## 3. The Browse / Search Loop

### What each does

**OpenAI — WebGPT primitives + RL-learned control (the winner for primitive design).** The web namespace exposes line-level browse primitives `[ODR §7–8]`:

| Primitive | Role |
|---|---|
| `search_query{q, recency, domains}` | web search, ≤30 results (default 10), `recency` in days, `domains` allowlist |
| `open{ref_id, lineno}` | fetch full page text **with line numbers** |
| `find{ref_id, pattern}` | grep within an opened page → matching lines |
| `click{ref_id, id}` | follow an in-page link by its link-id |
| `image_query` | image search (only embed if you actually `open`ed the image `[ODR §5 inner prompt]`) |

The critical RE finding: OpenAI **rejected DAG/graph orchestration in favor of RL-learned control** — the loop terminates "by model judgement, not by a fixed step count" `[ODR §3]`. The model was RL-trained on browse trajectories with a reward that includes a *"diminishing returns"* term so it learns to stop when each additional call adds < threshold of new info `[ODR §App-A Stage 4]`. `open`+`find` give **line-level access**, which is what *enables* the `【ref†L42-L58】` citation grain — the model grounds against specific line ranges, never snippets `[ODR §8]`. Newer (GPT-5.5) browse mandate is *stronger*: *"WHEN IN DOUBT, BROWSE WITH web.run"* `[ODR §R2.4]`.

**Grok — broad tool registry + verbose-streaming DeepSearch (the winner for tool breadth).** 10 tools `[GROK §6]`: `code_execution` (Python 3.12 with scipy/sympy/rdkit/qutip — far broader sci stack than ODR which disables matplotlib), `browse_page{url, instructions}` (note: passes URL to a *summarizer LLM with custom instructions*, not raw text — trades fidelity for focus), `web_search{query, num_results≤30}`, `web_search_with_snippets`, four X tools (`x_keyword_search` with full advanced-operator suite, `x_semantic_search` with `min_score_threshold=0.18`, `x_user_search`, `x_thread_fetch`), `view_image`, `view_x_video`. Each instance fires 5–30 tool calls `[GROK §5 step 5]`.

**Perplexity — `max_steps≤10` ReAct (the winner for cheap step-bounded loops).** The loop is **step-bounded, hard cap 10** (`max_steps … Maximum allowed is 10` `[PPLX §R3.2]`). A "step" = one search→read→reason cycle that can fan out a *list* of queries (`SearchQueriesEvent.queries: List[str]`), so "dozens of searches" = many queries/step × ≤10 steps, NOT 30 sequential steps `[PPLX §R3.2]`. Three in-loop tools (KNOWN from `ReasoningStep` `[PPLX §R3.14]`): `web_search{search_keywords[]}`, `fetch_url_content{contents[]}` (≤`max_urls`/call), **`execute_python{code, result}`** (the "math queries"). Each step persists a `ReasoningStep{thought, web_search|fetch_url_content|execute_python}` — a **fully auditable (thought, action, observation) ReAct trace** `[PPLX §R3.14]`. Two-phase retrieval: recall → rerank with swappable `ranking_model`, scored against `user_original_query` (un-rewritten) so query-expansion doesn't drift relevance `[PPLX §R3.7]`. Three search verticals: `web` / `academic` / `sec` `[PPLX §R3.7]`.

**Claude — subagent-internal loop.** Each subagent runs its own 3–10-turn tool-use loop, emitting 3+ tool calls in parallel per turn `[CLR §7, §CE.6]`. *"Start broad, narrow progressively"* `[CLR §6 principle 6]`.

**hyperresearch — fetcher batches + source-analysts.** No ReAct loop per se; the "loop" is the fixed stage sequence. Width-sweep generates a search plan (4 lenses, 40–100 searches, `[HR Stage 2.1]`), executes via 10–12 parallel fetchers, coverage-checks, runs ≤3 waves. No `execute_python` in the loop; no line-level open/find.

### Winner + what to adopt

**Winner: a hybrid — Perplexity's step-bounded ReAct as the OPTIONAL fast-mode loop (§9 agentic mode), OpenAI's `open`+`find` line primitives for the citation grain, Perplexity's `execute_python` in-loop tool, Grok's broad sci-stack for the code tool.**

For the **fixed hyperresearch pipeline**, the highest-value loop additions are:
1. **Add `execute_python` to the fetcher/depth toolset (IDEA).** Perplexity's RE is explicit: *"A replica MUST implement `execute_python`… web_search+fetch alone will under-perform on any query needing calculation over retrieved numbers"* `[PPLX §R3.14]`. hyperresearch handles `time_periods`/financial figures (`10-Q`/`10-K`) `[HR Stage 1, 2.1 Lens D]` but has no calc tool — a sandboxed Python interpreter (Grok's stack: numpy/scipy/pandas/sympy) closes this.
2. **Line-numbered `open`/`find` for fetched sources (IDEA).** hyperresearch's fetchers store markdown notes with `quoted_support` passages `[HR Stage 2.6]`. Add line numbers to stored notes so the synthesizer/patcher can cite at line grain (feeds §4).
3. **For the OPTIONAL agentic mode (§9):** use Perplexity's exact loop — `max_steps≤10`, per-step query fan-out, persisted ReAct trace, recall→rerank-vs-original-query, terminate when model declares done OR step==max_steps.

---

## 4. Citation / Provenance

### What each does (most-to-least strict)

**OpenAI — line-level `【ref†L42-L58】` (the winner for verifiability).** Format: `【{cursor}†L{line_start}(-L{line_end})?】` where cursor = source ref-id (`turn3search4`) and the L-range is the supporting span in the opened page `[ODR §5 inner prompt, §9]`. Rules (verbatim-derived): never write a URL directly, always use ref-id; never cite a ref-id you didn't open; place at END of paragraphs; multi-source `citeturn3search4turn1news0`. Hallucination defenses: line-level grounding (post-hoc verifiable), image-only-if-opened, no URL extrapolation `[ODR §9]`. The teardown's #2 take-away: *"line-level citations are not optional… any replica that cites at paragraph/article level will hallucinate at the rate of pre-2025 browse models"* `[ODR §20]`.

**Gemini — byte-span grounding (`GroundingSupport`/`confidence_scores`) (the winner for machine-verifiable confidence).** Report prose uses URL-level inline markdown links `([Title](url))` — human-readable but coarse `[GDR §8]`. BUT under the hood, Search Grounding emits `groundingMetadata` with `groundingChunks` linking **each output sentence to specific source snippets** with confidence scores `[GDR §8 grounding verification]`. There is also a **RECITATION gate** (Google's verbatim-copyright filter) that blocks output reproducing source text too closely (see §6). So Gemini has *two* grain levels: coarse prose links + fine byte-span grounding metadata the UI uses.

**Perplexity — typed per-sentence `[N]` + `Annotation` char-offsets (the winner for the prose+structured dual view).** Prose: per-sentence single-index brackets — *"Ice is less dense than water[1][2]"*, **each index in its own bracket, never `[1,2]`**, ≤3 per sentence, no space before bracket, **no References section** (client renders sources out-of-band) `[PPLX §R3.6]`. The `[N]` maps to `SearchResult.id: int`. Structured: `Annotation{start_index, end_index, title, type, url}` marks a char span in the report and binds it to a source — *"the prose bracket is human-facing, the Annotation is the structured offset→URL map the UI uses to make [N] clickable"* `[PPLX §R3.7]`.

**Grok — `<grok:render type="render_inline_citation">` with typed `[web:N]`/`[post:N]`.** Render-component (not markdown): placed inline directly after final punctuation; only from web/browse/X results; `[web:N]` for web, `[post:N]` for X posts; one per sentence/bullet/cell; no other citation method; no fabricated ids `[GROK §8]`. Paragraph-grain, verifiable. X posts render as embedded cards.

**Claude — inline `[N]` → dedicated CitationAgent re-grounding (the winner for the post-hoc verification pass).** The orchestrator writes `[SOURCE:N]` markers during synthesis; a **separate late-stage CitationAgent** (Haiku-class, INFERRED) reads `(draft_report, all_subagent_findings)` and **re-grounds every claim against the actual source text**, rewriting claims that fail grounding and surfacing low-confidence notes `[CLR §8, §CE.13 obs.2]`. Runs AFTER `finish_research`, purely a grounding/verification pass. *"A dedicated CitationAgent is non-negotiable; citation hallucination is the single largest correctness risk"* `[CLR §24 #6]`.

**hyperresearch — wikilink `[[note-id]]` / inline `[N]` / none, per-sentence.** Citation style chosen in Stage 1; wikilinks `[[<source-note-id>]]` are the default and are PRESERVED through polish (they're the citation system, not a leak) `[HR Stage 11, 15]`; inline `[N]` + `## Sources` for benchmarks/external. Per-sentence cites directly after each sentence `[HR Stage 11]`. The provenance backbone is the **vault** — every source is a markdown note with frontmatter, so `[[note-id]]` is a hard reference to a stored artifact. No line/byte-offset grain, no separate re-grounding agent.

### RECOMMENDED ONE standard for the ultimate skill

**Adopt a layered standard: Perplexity's per-sentence single-index `[N]` brackets as the PROSE format + OpenAI's line-range grain as the GROUNDING anchor + a Claude-style CitationAgent re-grounding pass. Concretely:**

```
Prose (human-facing):   per-sentence, single-index-per-bracket, ≤3/sentence, no space before
                        e.g. "Single-atom Pt achieves 90% FE[12][27]."
Anchor (structured):    each [N] resolves to {note_id, url, title, line_start, line_end, char_span}
                        — OpenAI's L-range grain stored in the vault note, Perplexity's
                          Annotation{start_index,end_index,url} for the report text.
Sources rendering:      OUT OF BAND from the report body (Perplexity rule) — the client/CLI
                        renders the source list from vault frontmatter; NO "## References"
                        section inside the prose (unless citation_style=inline for benchmarks).
Verification:           a dedicated CitationAgent (Haiku/Sonnet) re-grounds every [N] against
                        the cited note's line-range BEFORE the report is finalized.
```

**Why this combination:** hyperresearch already has the per-sentence discipline and the vault (the hard provenance anchor) — it just needs (a) the **line/char-offset grain** stored per citation (steal OpenAI's L-range + Perplexity's Annotation), and (b) a **re-grounding pass** (steal Claude's CitationAgent). The single-index-per-bracket rule is Perplexity's and is the cleanest for rendering. Avoid Gemini's prose-URL-only grain (too coarse for verification) but **steal its confidence-score idea** for the CitationAgent's output (emit per-claim confidence high/med/low).

**Constants to copy:** ≤3 sources/sentence (Perplexity); cite directly after final punctuation, no space (Perplexity/Grok); embed-image-only-if-opened (OpenAI); no References section in prose body (Perplexity); CitationAgent model = Haiku-class (Claude).

---

## 5. Termination

### What each does

| Product | Termination rule | KNOWN? |
|---|---|---|
| **Perplexity** | **`max_steps` hard cap = 10** (model-declares-done OR step==max_steps); preset carries default, param overrides but can't exceed 10 `[PPLX §R3.2]` | KNOWN (SDK contract) |
| **Grok** | `max_turns` ∨ **200s wall** ∨ **1M-context** ∨ debate converges (≥75% instances agree) ∨ debate round cap 3–5 — **no convergence metric for the search loop itself** `[GROK §3 note 3, §7 step 6]` | KNOWN/INFERRED |
| **Claude** | soft: **15 calls / 100 sources** per subagent; per-subagent **300s timeout** → soft-fail; orchestrator decides "more research?" between batches `[CLR §14, §CE.3]` | KNOWN |
| **OpenAI** | **model-judged** ("comprehensive coverage; further searches return diminishing returns"), RL-learned, no fixed count; soft 5–30 min wall `[ODR §3, §App-A]` | KNOWN (mechanism) / INFERRED (threshold) |
| **Gemini** | per-step coverage self-decision + ~60-min wall ceiling `[GDR §R2 compare table]` | INFERRED |
| **hyperresearch** | **stage-based** — the pipeline terminates when stage 16 completes. Per-stage internal caps: ≤3 fetch waves, ≤6 investigators, ≤5 gap-fetches, coverage-matrix zero-gaps `[HR Stages 2,4,13]` | KNOWN |

### Winner + what to adopt

**hyperresearch's stage-based termination is actually the most robust for a fixed pipeline** — it doesn't need a convergence metric because the stage graph IS the termination contract. But it lacks **per-stage hard wall-clock and tool-call ceilings**, which every frontier system has as a safety net.

**Adopt (IDEA): belt-and-suspenders termination per stage.**
1. **Perplexity's `max_steps≤10`** applies to the OPTIONAL agentic mode (§9) — that's the right ceiling for a ReAct loop (verified: most Perplexity DR tasks finish <3 min within ≤10 steps `[PPLX §R3.9]`).
2. **Claude's per-subagent caps** (300s timeout, tier tool-call caps 3/10/20/30, 100-source hard kill) on every hyperresearch fetcher/investigator/critic Task. hyperresearch has source-count targets but no per-agent timeout — a stuck fetcher currently has no kill.
3. **Grok's wall-clock ceiling** (200s/instance) as a per-stage timeout, scaled to stage cost (fetch waves 300s, depth investigation 900s, drafting 900s).

**Key insight (KNOWN):** none of the five uses a semantic "convergence detector" for the search loop — they all use **budget exhaustion (steps/time/sources/context) OR a coverage self-check**. hyperresearch's coverage-matrix (Stage 1 zero-gaps) + coverage-check (Stage 2.5 well/adequate/thin/uncovered) is the *best* coverage self-check of the five — keep it, add the budget ceilings as the safety net.

**Grok's exact ceilings (KNOWN/INFERRED `[GROK §3,§7]`):** the *search* loop inside each instance has no convergence metric — it just runs 5–30 tool calls then emits a candidate. Termination lives at the *ensemble* layer: debate runs **3–5 rounds**, converging when **≥75% of instances agree** on the core answer; if no convergence by the round cap, the **judge picks** the best-grounded answer `[GROK §7 step 6]`. Wall-clock ceiling ~200s/instance (instances run in parallel → 2–3 min median wall despite 16–32× total compute `[GROK §10]`). This is the one termination idea hyperresearch could borrow at the *draft* layer: hyperresearch already produces 3 angle-drafts (Stage 10) — the synthesizer (Stage 11) is effectively the "judge" picking/merging. The ≥75%-agreement→assert-confidently rule maps onto hyperresearch's `consensus-claims.json` (3+ independent sources agree = "settled ground, assert without hedging" `[HR Stage 3]`).

---

## 6. Eval / Grading

### What each does

**Claude — `define_outcome` LLM-as-judge + the 5-axis rubric (the winner; the reference grader).** The eval methodology is KNOWN verbatim `[CLR §13]`:
- **5-axis rubric:** (1) **factual accuracy** — "do claims match sources?"; (2) **citation accuracy** — "do cited sources match the claims?"; (3) **completeness** — "are all requested aspects covered?"; (4) **source quality** — "primary over secondary?"; (5) **tool efficiency** — "right tools, reasonable number of times?"
- **Implementation that won:** *"Single LLM call with a single prompt outputting scores from 0.0–1.0 and a pass-fail grade was the most consistent"* — tested against multi-call ensemble judges, single call was MORE consistent (less variant-prompt noise) `[CLR §13]`.
- **Scale:** start with **~20 queries** representing real usage for fast regression detection, then scale to **hundreds** before committing `[CLR §13]`. Human-in-loop catches edge cases (hallucinations on unusual queries, source-selection bias) `[CLR §13]`.
- **`define_outcome` / max 20 revisions, client-supplied rubric:** the managed-agent pattern lets a client supply a grading rubric; the agent revises its output up to a cap (max ~20 revisions) until the LLM-judge passes `[CLR managed-agent / define_outcome]`. This is the **grader-LOOP** (not just one-shot grading) — judge → revise → re-judge until pass or revision cap.

**Gemini — RECITATION gate (the winner for the copyright/verbatim safety check).** A hard filter that blocks output reproducing source text too closely (verbatim-copyright protection). It's a *negative* grader — it doesn't score quality, it rejects outputs that copy. hyperresearch's polish-auditor already strips "copyrighted material verbatim" implicitly via the synthesizer's *"do not paste paragraphs… synthesize in your own voice"* rule `[HR Stage 11]` — RECITATION formalizes this as a gate.

**Grok — debate-then-judge (the winner for ensemble grading).** N instances debate (3–5 rounds, converge at ≥75% agreement), then a **separate Grok-4 judge instance** with a judge-specific prompt picks the best-grounded answer and flags disagreements `[GROK §7 steps 6–7]`. This is grading-as-aggregation, not grading-as-revision.

**OpenAI / Perplexity — offline only.** OpenAI grades via RL reward during *training*, not at inference `[ODR §App-A]`. Perplexity has no in-loop grader.

**hyperresearch — adversarial critics, but NO grader loop.** Stage 12 spawns **4 critics in parallel** (dialectic/depth/width/instruction), each emitting a findings JSON `[HR Stage 12]`. These are *adversarial reviewers*, not a scoring rubric — they find specific flaws, the patcher (Stage 14) applies surgical fixes. There is NO numeric rubric, NO pass/fail gate, NO judge→revise→re-judge loop, NO max-revisions cap. The pipeline runs critics ONCE → patches ONCE → done.

### Winner + how to add a grader loop to hyperresearch

**Winner: Claude's `define_outcome` 5-axis LLM-judge revision loop. Add it as a new gated stage.**

hyperresearch's critics are *complementary* to a grader, not a substitute: critics find specific issues (qualitative, per-finding); a grader scores the whole report on fixed axes (quantitative, pass/fail). **Add both layers.**

**IDEA — Stage 11.5 "Grader Loop" (insert between Synthesize and Critics, gated):**
```
1. Run a single-LLM-call judge (Opus/Sonnet) with the 5-axis rubric, adapted to hyperresearch:
   - factual accuracy        (claims match vault notes?)
   - citation accuracy       (every [N]/[[note-id]] resolves & supports its sentence?)
   - completeness            (every required_section_heading + atomic item from decomposition covered?)
   - source quality          (primary/academic/gov over blog — reuse Stage 2.3 utility scoring)
   - tool/process efficiency  (no over-fetch, no derivative-source padding)
   Output: 5 scores 0.0–1.0 + overall PASS/FAIL + a findings list (feed to patcher).
2. If FAIL and revisions < MAX_REVISIONS (cap 5, NOT 20 — hyperresearch patches are surgical,
   not regenerations, so fewer iterations needed): the judge's findings join the critic findings,
   the patcher (Stage 14) applies them, re-grade. Loop.
3. If PASS or revisions == cap: proceed.
```
Why cap=5 not 20: Claude's 20-revision cap assumes full regeneration each round; hyperresearch's patch-never-regenerate invariant `[HR Stage 14]` means each revision is a small Edit, converging faster — 5 is sufficient and respects the cost ceiling.

**Reimplementable grader prompt (IDEA, Claude's "single LLM call, 0.0–1.0 + pass/fail" `[CLR §13]`):**
```
You are a research-report grader. Score the report on 5 axes (0.0–1.0 each) and emit an
overall PASS/FAIL plus a findings list. Single response, no tool calls.

  factual_accuracy:   every non-trivial claim is supported by a cited vault note. (sample 8 claims)
  citation_accuracy:  every [N]/[[note-id]] resolves AND the cited note actually supports the sentence.
  completeness:       every required_section_heading present in order; every atomic item from
                      prompt-decomposition.json covered (no false-negatives — the expensive miss).
  source_quality:     primary/gov/academic > journalism > blog (reuse Stage 2.3 6-dim utility scoring).
  process_efficiency: no derivative-source padding (Stage 2.6 redundancy), no missing time_periods figures.

PASS if all axes ≥ 0.8 AND no critical finding. Output JSON:
{"scores":{...}, "overall":"PASS"|"FAIL", "findings":[{"axis","severity":"critical|major|minor",
 "failure_mode":"missing|under-covered|miscited|misordered","fix_hint":"...","atomic_item":"..."}]}
```
Findings with `severity ∈ {critical,major}` join the Stage-12 critic findings and flow to the patcher (Stage 14); the report is re-graded after patching. Note the alignment: hyperresearch's **instruction-critic** `[HR Stage 12]` already measures `completeness` qualitatively — the grader adds the quantitative gate and the pass/fail loop the critics lack.

**Also adopt the eval-set discipline (IDEA):** ship a **20-query benchmark set** (Claude's number) for offline regression testing of the whole skill, scored by the same 5-axis judge. This is how you calibrate the skill against the real frontier DR products (run both, score both, close the gap).

**Adopt RECITATION as a polish gate (IDEA):** in Stage 15/16, add an explicit verbatim-overlap check (n-gram overlap > threshold vs cited source) → flag for rewrite. Cheap, prevents copyright incidents.

---

## 7. Budgets / Test-Time-Compute

### What each does

**OpenAI — Juice + reasoning_effort (the winner; the cleanest cost dial).** "Juice" is OpenAI's internal reasoning-effort dial `[ODR §4]`:
- **Juice: 128** = max, used by full Deep Research (o3-deepresearch); Juice 64 = o3-default; Juice 16 = fast modes `[ODR §4, §20 #7]`.
- The CONTEXT brief specifies **Juice 512 (API) / 1024 (app)** — these are the higher-tier values in the GPT-5 era; the `deep_research/o3` SKU has a **1024-token max-output chunk** (worker streams synthesis in 1024-token chunks the host stitches `[ODR §R2.6]`).
- API `reasoning_effort` parameter: **4 levels `minimal`/`low`/`medium`/`high`** (o3 → inherited by GPT-5.5) `[ODR §R2.11]`. DR runs at `high` by default; lightweight (o4-mini) at medium/low.
- The teardown's #7 take-away: *"the reasoning-effort dial is the cleanest cost knob in agentic AI… if you build a reasoning model expose this dial; if you consume one tune it per use-case"* `[ODR §20]`.
- Token economics: ~200K–500K tokens/run, ~$20–60 at API rates, bundled to ~$0.80 effective `[ODR §10]`.

**Gemini — per-tier query/token caps + 60-min wall (the winner for hard tiering).** Plan steps 3–10, each gets a **search budget of 3–15 tool calls** `[GDR §5]`; tier caps (AI Premium ~5–10 runs/day) `[GDR §10]`; ~60-min wall ceiling `[GDR §R2]`. 1M context = no summarization needed (the budget IS the context window) `[GDR §15]`. Cost ~$1–3/run `[GDR §10]`.

**Perplexity — citation/reasoning token accounting (the winner for granular metering).** Five cost components per `sonar-deep-research` call `[PPLX §R3.5, §2146]`: **input + output + reasoning_tokens + citation_tokens + (search_queries × per-query) + flat request_cost**. Pricing: $2/M citation, $3/M reasoning, $5/1K searches, $2 in / $8 out `[PPLX §2146]`. `citation_tokens` = *"Perplexity bills you for the tokens of cited source material it pulled into context"* `[PPLX §R3.5]`. `num_search_queries` = the canonical "how many searches" integer. `search_context_size: low/medium/high` dial trades cost for recall `[PPLX §R3.7]`. Client timeout `DEFAULT_TIMEOUT = 900s` `[PPLX §R3.1]`.

**Claude — token budget = 80% of variance (the winner for the empirical law).** *"Token usage by itself explains 80% of the variance… upgrading Sonnet 3.7→Sonnet 4 is a larger gain than doubling the token budget"* `[CLR §11–12]`. Per-tier total token budgets: 20K/150K/1.5M/5M `[CLR §CE.5]`. Multi-agent = ~15× single chat `[CLR §11]`. The optimization order is KNOWN: **spend more tokens first, then optimize tool patterns, then upgrade model** `[CLR §12]`.

**Grok — N instances as the dial.** TTC = N parallel instances (4/8/16/32 by complexity) `[GROK §3 note 1, §10]`; ~$10–60/run for N=16–32.

**hyperresearch — tier as the only dial.** `light` (~$5–15, ~30–40 min) vs `full` (~$60–120, ~1.5–2.5h) `[HR §1]`. Within a tier, budgets are fixed per stage (40-source loci budget, ≤6 investigators, source-count targets). No reasoning-effort dial, no per-run token cap, no metering.

### Winner + what to adopt

**Winner: OpenAI's reasoning_effort dial (4-level) as the primary knob + Claude's empirical "tokens=80% variance" optimization order + Perplexity's per-component metering for cost transparency.**

**IDEA — add three budget controls to hyperresearch:**
1. **A reasoning-effort dial mapped to model + iteration count.** OpenAI's lesson: expose `minimal/low/medium/high`. For hyperresearch (which consumes Anthropic models), map:
   - `minimal` → light tier, Haiku drafters, single draft, no loci.
   - `low` → light tier, Sonnet drafters.
   - `medium` → full tier, default subagent counts.
   - `high` → full tier, max subagent counts (loci ≤6, fetchers 12, deep investigators), extended-thinking on.
   This makes the existing tier system a *continuum* rather than a binary.
2. **Per-run token/cost ceiling with the Claude optimization order.** Track cumulative tokens; if approaching a user-set cap, the orchestrator degrades gracefully (fewer fetchers, skip redundancy audit) — and the order of cuts follows Claude's law: cut tokens last (they're 80% of quality), cut tool-call redundancy first.
3. **Perplexity-style per-component metering surfaced to the user.** Report `{input, output, reasoning, citation (source-text ingested), search_queries}` token/cost breakdown — hyperresearch already tracks source counts; add token accounting so the user sees *why* a full run costs $60–120.

**Constant to copy:** the 4-level effort enum (`minimal/low/medium/high`); 1024-token output chunking for streaming (OpenAI); `search_context_size` low/medium/high recall dial (Perplexity) → map to hyperresearch's `num_search_results`.

---

## 8. Prompt-Engineering Principles (Claude eng blog, verbatim)

The 8 principles from the Anthropic engineering blog are the single most reusable verbatim prompt-engineering corpus in the field `[CLR §15, §6]`. All KNOWN.

1. **Think like your agents.** *"You must understand their effects."* When debugging, read the agent's actual context window, don't guess `[CLR §15 #1]`. → hyperresearch's "subagent spawn contract" (verbatim query + pipeline-position) is exactly this — the subagent gets the full mental model.
2. **Scale effort to complexity.** Embed explicit scaling guidelines: *"simple queries use 1 agent with 3–10 tool calls; complex research uses 10+ subagents"* `[CLR §6 principle 3, §15 #3]`. → hyperresearch's tier gate + loci source-budget allocation already does this; the reasoning-effort dial (§7) extends it.
3. **Detailed delegation.** Delegation must include *"an objective, an output format, guidance on the tools and sources to use, and clear task boundaries"* — the 4-field contract `[CLR §6 principle 2, §15 #2]`. → ADD `stop_conditions` + `output_shape` to hyperresearch's spawn contract (§2).
4. **Tool selection heuristics.** *"Bad tool descriptions can send agents down completely wrong paths… write tool descriptions like API documentation, not marketing copy"* `[CLR §15 #4]`. Prefer specialized over generic tools `[CLR §CE.4]`.
5. **Self-improvement / let Claude be the prompt engineer.** *"Claude 4 models can be excellent prompt engineers… diagnose why the agent is failing and suggest improvements"* — the tool-testing meta-agent rewrote flawed tool descriptions for a **40% completion-time reduction** `[CLR §9, §15 #5]`. → IDEA: a meta-critic that rewrites hyperresearch's own stage prompts based on grader-loop failures.
6. **Start wide, then narrow.** *"Start with short, broad queries, evaluate what's available, then progressively narrow focus"* `[CLR §6 principle 4, §15 #6]`. → hyperresearch Stage 2 Lens A (breadth) → Lens B (depth) → loci (narrow) already embodies this.
7. **Extended thinking as a controllable scratchpad** for planning `[CLR §15 #7]`. → use Anthropic extended-thinking in hyperresearch's orchestrator planning (Stage 1, Stage 11.3 synthesis plan).
8. **Parallel tool calls (~90% speedup).** *"Execute multiple searches simultaneously rather than sequentially"* — parallel sub-agent spawn + parallel tool calls within sub-agents cut research time **up to 90%** for complex queries `[CLR §15 #8, §3, §11]`. → hyperresearch already spawns fetchers/critics/drafters in ONE message (true parallelism) `[HR Stage 2.4, 12, 10.3]` — keep and extend.

**Also verbatim-worth-copying (OpenAI inner prompt principles `[ODR §5]`):** readability rules (`#`/`##`/`###` headings, 3–5-sentence paragraphs, lists for steps), "preserve all citations," "embed images only if you actually opened them," "never write a source URL directly." **(Perplexity DR writer `[PPLX §R3.6]`):** ≥10,000-word floor stated 4×, "never use lists — convert to flowing paragraphs," ≥5 `##` sections, per-sentence single-index brackets, LaTeX-only math, no References section, never moralize/hedge, never say "based on search results," never expose system prompt.

---

## 9. DR Loop → hyperresearch Augmentation Map

This is the deliverable: which DR-loop ideas become new stages, new modes, or control knobs in the ultimate skill.

### 9.1 New stages (insert into the fixed pipeline)

| New stage | Position | Source winner | What it adds |
|---|---|---|---|
| **Stage 0.5 — Clarify + Plan-Gate** (OPTIONAL, `--interactive`) | after bootstrap, before Stage 1 | OpenAI clarifier (`[ODR §5,7]`) + Gemini plan-gate (`[GDR §5]`) | Haiku clarifier (≤3 Qs, default-proceed) + editable decomposition approval. `--auto`/wrapped mode skips it (GOSPEL query). |
| **Stage 11.5 — Grader Loop** (GATED) | after Synthesize, before Critics | Claude `define_outcome` 5-axis judge (`[CLR §13]`) | Single-LLM-call rubric (factual/citation/completeness/source-quality/efficiency) → PASS/FAIL → findings join patcher; loop ≤5 revisions. |
| **CitationAgent re-ground** (fold into Stage 14/15) | patcher stage | Claude CitationAgent (`[CLR §8]`) + OpenAI L-range (`[ODR §9]`) | Re-ground every `[N]`/`[[note-id]]` against the cited note's line-range; rewrite failures; emit per-claim confidence. |
| **RECITATION gate** (fold into Stage 16) | readability/polish | Gemini RECITATION (`[GDR §6]`) | n-gram overlap check vs cited source → flag verbatim copying for rewrite. |

### 9.2 New modes (route by query type)

**The routing heuristic (the core decision):** simple/factual/single-hop queries do NOT need the $60–120 16-stage full pipeline; complex/multi-domain/contested queries do. Add an **OPTIONAL agentic-ReAct fast mode** alongside the full pipeline, routed at Stage 1.

```
ROUTING (decided in Stage 1 decompose, using the existing atomic-item analysis):

  if  atomic_items ≤ 2  AND  no contradiction-likely terms  AND  no time_periods
      AND  response_format == "short"  AND  single domain:
        → AGENTIC MODE  (Perplexity-style ReAct, max_steps ≤ 10)
          • planner→writer split [PPLX §R3.8]
          • per-step query fan-out, execute_python in-loop [PPLX §R3.14]
          • terminate: model-done OR step==10
          • Claude per-call caps (300s, ≤15 calls) as safety net
          • single-pass writer, per-sentence [N] cites
          • cost ~$1–5, time <3 min  [PPLX §R3.9]

  elif response_format in {structured} OR atomic_items 3–6 OR mild tensions:
        → LIGHT TIER  (existing: 1→2→10→15→16) + grader-loop  [HR §1]
          cost ~$5–15

  else  (multi-domain, contested, argumentative, time_periods, ≥7 atomic items):
        → FULL PIPELINE  (existing 16 stages) + clarifier + grader-loop  [HR §1]
          cost ~$60–120
```

**Why this heuristic:** it mirrors OpenAI's lightweight-vs-full fallback `[ODR §12]` and Claude's effort-tier rule `[CLR §CE.5]` — both gate compute on complexity. The signal is hyperresearch's OWN Stage-1 decomposition output (`atomic_items`, `response_format`, `time_periods`, contradiction-likely terms) — no new classifier needed. The agentic mode IS Perplexity DR (cheapest, step-bounded); the full pipeline IS hyperresearch (deepest); light is the middle.

**Reimplementable agentic-mode loop (IDEA, Perplexity `[PPLX §R3.2,§R3.14,§R3.17]` + Claude guards `[CLR §CE.5]`):**
```python
def agentic_research(query, max_steps=10, max_calls=15, timeout_s=300):
    ctx, step = [planner_system_prompt(query)], 0       # planner = system A
    deadline = now() + timeout_s
    while step < max_steps and now() < deadline:        # termination: steps OR wall
        step += 1
        plan = reason(ctx)                              # emit thought (ReAct), pick action
        if plan.declares_done: break                    # model-judged stop (OpenAI-style)
        # one step = a LIST of queries / fetches / code, fanned out in parallel:
        results = parallel(                             # Claude "batch=parallel()" within a step
            [web_search(q) for q in plan.search_queries],     # recall
            [fetch_url(u) for u in plan.fetch_urls[:max_urls]],
            [execute_python(c) for c in plan.code],           # the "math queries" [PPLX §R3.14]
        )
        ranked = rerank(results, score_against=query)   # rerank vs ORIGINAL query [PPLX §R3.7]
        ctx.append(ReasoningStep(plan.thought, action, ranked))  # persist auditable trace
        if total_tool_calls(ctx) >= max_calls: break    # Claude hard cap safety net
    # writer = system B: gets RANKED RESULTS, not the planner CoT [PPLX §R3.8]
    return writer(query, evidence=collect_cited(ctx))   # single-pass, per-sentence [N] cites
```
This is the entire Perplexity DR engine. In hyperresearch it slots in as the `agentic` mode branch of Stage 1's router; it reuses hyperresearch's vault (each `fetch_url` result becomes a note) and its citation renderer.

### 9.3 New control knobs

| Knob | Source winner | Mapping in hyperresearch |
|---|---|---|
| **`reasoning_effort` 4-level** (`minimal/low/medium/high`) | OpenAI Juice (`[ODR §4,§R2.11]`) | minimal→light+Haiku+single-draft; low→light+Sonnet; medium→full default; high→full+max-fan-out+extended-thinking |
| **Per-subagent caps** (300s timeout, tool-call caps 3/10/20/30, 100-source kill) | Claude (`[CLR §CE.5,§CE.10]`) | applied to every fetcher/investigator/critic Task as runtime guards |
| **`max_steps ≤ 10`** | Perplexity (`[PPLX §R3.2]`) | the agentic-mode loop ceiling |
| **`search_context_size` low/med/high** | Perplexity (`[PPLX §R3.7]`) | maps to Stage 2 `num_search_results` + source-count targets |
| **Per-run token/cost ceiling** | Perplexity metering (`[PPLX §R3.5]`) + Claude order (`[CLR §12]`) | track cumulative tokens; degrade gracefully (cut redundancy audit first, tokens last) |
| **4-field delegation `+stop_conditions+output_shape`** | Claude (`[CLR §CE.2]`) | added to hyperresearch's subagent spawn contract |
| **`execute_python` in-loop tool** | Perplexity (`[PPLX §R3.14]`) + Grok sci-stack (`[GROK §6]`) | added to fetcher/depth toolset for quantitative queries (numpy/scipy/pandas/sympy) |

### 9.4 The recommended citation standard (restated)

**Per-sentence single-index `[N]` brackets (Perplexity) + line/char-offset anchor (OpenAI L-range + Perplexity Annotation) stored in the vault + a Claude-style CitationAgent re-grounding pass + no References section in prose (Perplexity) + per-claim confidence (Gemini grounding scores).** hyperresearch's vault already provides the hard provenance anchor (`[[note-id]]` → stored markdown note); the augmentation adds line-grain + re-grounding + structured offsets.

### 9.5 What hyperresearch already does BETTER (don't change)

- **Context-rot defeat** via skill-as-stage decomposition — frontier products all run one long trajectory and rely on `memento`/external-memory to survive context pressure (`[ODR §R2.3]`, `[CLR §CE.6]`); hyperresearch never holds the procedure in context (loads each stage fresh) `[HR §1]`. Superior.
- **Patch-never-regenerate** — no frontier DR product has this; they all regenerate. hyperresearch's `[Read, Edit]` tool-lock + 500-char hunk cap `[HR Stage 14]` is a genuine correctness moat. Keep.
- **Coverage self-check** (zero-gap matrix + well/adequate/thin/uncovered) is the best of the five — better than budget-only termination. Keep.
- **Triple-draft ensemble** (strongest-thesis / steelman-contrarian / synthesis-reconciler) `[HR Stage 10]` is closest to Grok's debate but cheaper (3 drafts, not N instances) and feeds a synthesizer rather than a judge. Keep; the grader-loop (§9.1) complements it.
- **Persistent rebuildable vault** that compounds across sessions — every frontier DR product is stateless per-run (`[ODR §15]`, `[GDR §15]`, `[CLR §CE.11]`); hyperresearch's cross-session vault is unique. Keep.

---

## 10. Per-Dimension Winners (one-line summary + constant)

| # | Dimension | Winner | Load-bearing constant/mechanism |
|---|---|---|---|
| 1 | Planning/clarification | **OpenAI** (clarifier) + **Gemini** (plan-gate) | 2-method `research_kickoff_tool`; default-to-proceed bias; gpt-4o-mini host; Gemini plan locked-on-start, 3–10 steps |
| 2 | Decomposition+parallel | **Claude** (fan-out) + **Perplexity** (planner→writer) | depth-1, batch=parallel() (N tool_use/turn); 4-field contract; default 3/max 20; caps 3/10/20/30; 300s timeout; writer sees evidence NOT CoT |
| 3 | Browse/search loop | hybrid: **Perplexity** ReAct + **OpenAI** line-primitives + **Grok** sci-stack | `max_steps≤10`, query fan-out/step; `execute_python` in-loop; `open`+`find` line access; recall→rerank-vs-original-query |
| 4 | Citation/provenance | **OpenAI** (line-grain) + **Perplexity** (per-sentence `[N]`+Annotation) + **Claude** (re-ground) | `【ref†L42-L58】`; single-index-per-bracket, ≤3/sentence, no References section; CitationAgent (Haiku) re-grounds before final |
| 5 | Termination | **hyperresearch** (stage/coverage) + safety nets from Claude/Perplexity/Grok | stage graph + zero-gap matrix; +`max_steps≤10`, 300s/agent, 200s wall, 100-source kill |
| 6 | Eval/grading | **Claude** `define_outcome` 5-axis LLM-judge | single-call rubric, 0.0–1.0 + pass/fail; 20-query eval set→hundreds; revision loop (hyperresearch cap 5, not 20) |
| 7 | Budgets/TTC | **OpenAI** reasoning_effort + **Claude** law + **Perplexity** metering | Juice 128/512/1024; 4-level effort enum; tokens=80% variance, cut tokens last; 5-component metering |
| 8 | Prompt principles | **Claude** eng blog (8 verbatim) | think-like-agents; scale-effort; detailed-delegation; parallel-tool-calls ~90% speedup; start-wide-narrow |

---

## 11. What NOT to copy (anti-patterns the RE surfaced)

- **OpenAI's single long trajectory + `memento` self-summarization** `[ODR §R2.3]` — a band-aid for context rot that hyperresearch *structurally avoids* by loading each stage fresh from disk. Don't adopt `memento`; the skill-as-stage design is strictly better for a long pipeline.
- **Gemini's locked-on-start plan** `[GDR §5]` — the user can't edit mid-execution. For hyperresearch, the plan-gate should be approve-or-edit *before* Stage 1, then the pipeline runs (matching Gemini's lock). Fine. But don't promise mid-run editing — that requires checkpointing the orchestrator's context, which hyperresearch deliberately keeps thin.
- **Grok's N=16–32 parallel full instances** `[GROK §10]` — 16–32× cost for the "wisdom of crowds" gain. hyperresearch's 3-draft ensemble + critics + grader achieves most of the reliability benefit at ~⅒ the cost. Don't ensemble whole pipelines.
- **Perplexity's `chat/completions` coarse 3-event stream** `[PPLX §R3 contrast]` — superseded by the 14-event `/v1/responses` taxonomy. If streaming, copy the fine-grained per-step reasoning events, not the legacy shape.
- **Citation at paragraph/article grain** (Gemini prose-URL-only) — *"will hallucinate at the rate of pre-2025 browse models"* `[ODR §20]`. Always go line/sentence grain.
- **OpenAI's "always full effort" default** — DR over-browses simple queries, burning quota on "capital of France"-class questions `[ODR §App-B #8]`. The routing heuristic (§9.2) is precisely the fix: route trivial queries to agentic-fast mode, never to the 16-stage pipeline.

## 12. Honest gaps in this comparison

- **Verbatim planner prompts** are not public for any product except OpenAI's host clarifier `[ODR §5]` and Perplexity's *writer* (the planner-A prompt itself has not leaked `[PPLX §R3.12 #1]`). The §9 grader/clarifier/delegation prompts are IDEA reconstructions from the RE, not lifted strings.
- **Per-preset `max_steps` defaults** (Perplexity) are unpublished — only the hard cap 10 is KNOWN `[PPLX §R3.12 #2]`.
- **Grok's exact N-selection mechanism and debate/judge prompts** are INFERRED `[GROK §3 note 1]`.
- **Claude's CitationAgent model + exact rubric weights** are INFERRED (Haiku-class, uniform weights assumed) `[CLR §20, §22]`.
- **Gemini's RECITATION threshold and Deep-Think internals** are not disclosed `[GDR §19]`.
These gaps affect *exact-parity* replication, not the architectural augmentation map — every §9 item is implementable at the mechanism level from KNOWN sources.

---

*End of dossier. Cross-refs: `teardowns/{OPENAI,GEMINI,PERPLEXITY,GROK_HEAVY,CLAUDE}_*.md`, `teardowns/HYPERRESEARCH.md`, `core/06_AGENTIC_ARCHITECTURES.md`. Next: encode §9 augmentations as new hyperresearch skill files + the routing heuristic in Stage 1.*
