# RE Handoff — what's still missing to build the Fast mode (per source)

**Date:** 2026-05-29
**Companion to:** `2026-05-29-bad-research-fast-mode-design.md`
**For:** the reverse-engineering effort in `~/Desktop/researchfms` (teardowns/).
**STATUS (2026-05-30): RESOLVED.** The RE was executed — see
`researchfms/teardowns/DEEP_RESEARCH_FAST_MODE_RE.md` (the XSTOP-1 synthesis + a runnable capture
harness, mining five open-source DR clones) and the R5 delta sections on the five DR teardowns.
**XSTOP-1 closed-by-source** (keyless 4-clause stop rule + evidence-anchored `FAST_*` constants);
PPX-1 / OAI-2 / OAI-3 / CLR-1 / CLR-3 / GRK-1/2 closed; **PPX-4 debunked** (T5-XXL / entropy-cutoff
were 3rd-party speculation — do not implement); the remainder (PPX-2/3, GEM-1c/2/3) are non-blocking
live-capture *calibration*. Findings folded into the design spec §3/§5/§10 and plan Tasks 9-11. The
per-source gap list below is retained as the original handoff record.
**Scope discipline:** this lists ONLY what serves the **keyless Fast mode**. Proprietary internals
(indexes, embedders, RL recipes, inference engines) are explicitly out of scope — see §7. Each item
has an **ID**, a **capture target**, **why it matters for Fast**, a **method**, and a **priority**
(P0 blocks calibration / P1 sharpens / P2 nice-to-have).

The existing teardowns are rich — much is already verbatim-captured. For each tool we first state
**what we already have** so you don't re-RE it, then the **delta**.

---

## 0. The single highest-value gap (cross-tool) — the early-stop heuristic

**Every** DR tool deliberately hides *how the loop decides it's done*:
- Perplexity: "reflect on output, assess whether the query is resolved" — no measurable rule (planner
  prompt, PERPLEXITY_DEEP §R4.1).
- OpenAI: stop/backtrack/pivot is **emergent from RL**, not a rule; the reward *shape* is published,
  the coefficients are not (OPENAI_DEEP_RESEARCH §R4.1).
- Gemini: a server-side per-tier compute budget (`budget_exceeded`); no client-visible step counter
  (GEMINI_DEEP_RESEARCH §R3.4).
- Grok: purely turn- and time-bounded (`max_turns` ∧ 200s), no agreement/convergence metric — R1's
  "75% agreement" was **debunked** (GROK_HEAVY §R3.7).
- Claude: per-subagent tool-call budgets (5/5/10/15, hard-kill 20/100) + a bounded grade→revise loop;
  the *rubric text* that judges "done" is only paraphrased (CLAUDE_RESEARCH §R3.16 #5).

**Capture target (XSTOP-1, P0):** for Perplexity DR and OpenAI DR, run 10-20 real queries spanning
trivial→broad→contested. For each, log **per step**: number of new distinct domains, number of new
distinct URLs, and whether the step changed the eventual answer. Plot marginal-new-evidence vs step
index. **Goal:** fit a concrete keyless stop rule for our loop, e.g. *"stop when a step adds < N new
distinct domains OR the coverage checklist (one item per sub-question) is all-green OR step == cap."*
This replaces the RL/server-budget magic with an auditable heuristic and is what sets our `FAST_*`
caps and the reflect/stop prompt.

**Method:** mitmproxy (or browser devtools → Network → the SSE/`text/event-stream` response) on a paid
session; parse the per-step event bursts (see PPX-1 for the exact Perplexity event names). For OpenAI,
the ChatGPT DR activity feed exposes each `search`/`open_page` action — log the action sequence.

---

## 1. Perplexity Deep Research (the BASE)

**What we already have (don't re-RE):**
- The **verbatim DR writer prompt** (PERPLEXITY_DEEP §R3.6, lines 3138-3184): ≥N words, no lists →
  tables, ≥5 `##` sections, per-sentence single-index `[N]` (one index per bracket, ≤3/sentence, no
  space before bracket), no `## References` (sources rendered out-of-band), LaTeX `\( \)`/`\[ \]`,
  anti-hedging impersonal voice, never ask clarifying Qs.
- The **loop contract**: ≤10 steps for DR (hard ceiling, §R3.2), ≤3 queries per `search_web` call
  (§R4.2), batched `fetch_url` never sequential, "never repeat identical tool calls", "all tools then
  write, no interleaving" (§R4.1).
- The SSE event sequence per step (§R3.3/§R3.17): `reasoning.started{thought}` →
  `reasoning.search_queries{queries[]}` → `reasoning.search_results{results,usage}` →
  optional `reasoning.fetch_url_queries/results` → `reasoning.stopped{thought}`.
- The preset table (§4): deep-research = 10 steps / 10K max / 4K per page / ~3,267 prompt tokens;
  fast-search = 1 step; pro-search = 3 steps. `search_context_size: low|medium|high`.

**Delta — what's missing:**

- **PPX-1 (P1) — the planner / "system A" prompt body, current snapshot.** We have the *writer*
  prompt; the planner's query-decomposition + per-step reflect/stop wording is only partially leaked
  (Oct-2025 fragment, §R4.1). *Capture:* the full system prompt on the planner turn of a live
  `sonar-deep-research` / `/v1/responses` call. *Why for Fast:* it's the literal text our Fast
  planner step should adapt (decompose-for-parallelization + reflect rules). *Method:* mitmproxy on
  api.perplexity.ai during a Pro DR run, or prompt-extraction against `sonar-deep-research`.

- **PPX-2 (P1) — query-selection / fan-out logic.** We know each step issues ≤3 queries by
  decomposition, but not *how* the planner picks them, nor the query-expansion model/prompt (the
  "T5-XXL 3-5 phrasings" claim at line 1208 is unverified). *Capture:* `reasoning.search_queries[]`
  per step across 10 runs; correlate query phrasing to the sub-task. *Why for Fast:* tunes our
  `bad funnel-gather --max-queries` and the planner's query-generation instruction.

- **PPX-3 (P2) — typical step count in practice.** The cap is 10; we don't know if DR usually runs
  3, 5, or 10. *Capture:* count `reasoning.started` bursts per run across complexity tiers. *Why:*
  sets `FAST_MAX_STEPS` precisely (we proposed 6).

- **PPX-4 (P2) — writer context payload.** What exactly the writer receives — full snippets, full
  fetched pages, or reranked top-K, and the top-K cutoff (the "entropy cutoff 0.85" at line 1257 is
  unverified). *Why:* informs how much we hand our writer vs. the `RESERVE_FOR_SYNTHESIS` budget.

*Out of scope here:* the Vespa index, pplx-embed, the default reranker (L2 cross-encoder / L3
XGBoost), ROSE/MoE/speculative-decoding — all proprietary infra, replaced by host web-search +
client-side chunking + our keyless LLM reranker. (PERPLEXITY_DEEP §R4.4, §9, §10.)

---

## 2. OpenAI Deep Research

**What we already have:**
- The **clarify front-end prompts** (OPENAI_DEEP_RESEARCH §R3.4): triage → clarifying agent (asks
  2-3 Qs, waits) → **instruction-builder** ("rewrite the query into a fully-scoped brief, fill
  unstated dimensions as open-ended, output ONLY the instructions"). Verbatim-captured.
- The **browse triad** `search` / `open_page` / `find_in_page` (WebGPT lineage), text-browse only.
- Line-level citation scheme `【turnXsearchY†L42-L58】` (ref-ID + line range) and the API
  `url_citation{url,title,start_index,end_index}` (char offsets) (§R3.3, §5, §9).
- `--QDF=0..5` freshness operator + `+`entity boost (§R4.6); `max_tool_calls` cap; reasoning-effort
  ("Juice") dial; "prefer batching" rule.
- Numbers: 30-150 tool calls/run, lightweight `o4-mini-deep-research` = 1-5 min variant.

**Delta — what's missing:**

- **OAI-1 (P0, feeds XSTOP-1) — empirical stop behavior.** The RL stop policy can't be copied; we
  approximate it. *Capture:* per-run action sequence (search/open_page counts) and the point of
  diminishing returns. *Why for Fast:* the keyless stop heuristic (XSTOP-1).

- **OAI-2 (P1) — exact citation placement + verification rules.** We have the *format*; we need the
  *discipline*: which sentences get cited (key facts/conclusions vs. every sentence), line-span
  granularity, and how the post-processor resolves ref-IDs→URLs and line-ranges→char-offsets.
  *Why for Fast:* this is the spec for our slim grounding pass (design §5). *Method:* inspect the DR
  output + the API `url_citation` annotations on the same run; compare cited vs. uncited sentences.

- **OAI-3 (P2) — instruction-builder currency.** Our captured prompt is the May-2025 worker era; the
  GPT-5.5 worker prompt hasn't leaked. *Capture:* re-extract the current instruction-builder +
  clarifying-agent prompt. *Why:* our scope-brief step (design §3) adapts it; worth confirming it
  hasn't changed materially.

*Out of scope:* the RL-trained browsing *policy* (the un-closeable 51.5% vs 9.9% BrowseComp delta —
prompt-only replicas can't match it), OpenAI's search backend + reranker, the container sandbox.

---

## 3. Claude Research (Anthropic multi-agent)

**What we already have (the most directly liftable artifact in any teardown):**
- The three verbatim cookbook prompts — `research_lead_agent.md` (155L), `research_subagent.md`
  (47L), `citations_agent.md` (22L) — drop straight into system-prompt slots (CLAUDE_RESEARCH CE3.15,
  CE3.20).
- The **query-type classifier** (depth-first / breadth-first / straightforward, CE3.2) — already
  mirrored in our `classify_query_shape`.
- The **type-disciplined delegation contract** (objective / output format / context / key questions /
  source guidance / allowed tools / scope boundaries, CE3.4) — mirrored in our seven-piece subagent
  spawn contract.
- Per-subagent budget caps (5/5/10/15, soft-stop ~15 calls/~100 sources, hard-kill 20/100, CE3.5) —
  mirrored in `FETCHER_TOOLCALL_CAP` / `SUBAGENT_SOURCE_KILL`.
- The **separate CitationAgent with byte-identical gate** (CE3.7) and the placement rules (cite key
  facts only, end-of-sentence, one cite per source per sentence, no fragment-level).
- The **source-quality-as-prompt-heuristic** lesson (CE3.10-11: their `evaluate_source_quality` tool
  was broken and patched out; the working mechanism is a verbatim negative-signal list).

**Delta — what's missing:**

- **CLR-1 (P1) — the production 5-axis research rubric TEXT** (factual accuracy, citation accuracy,
  completeness, source quality, tool efficiency) and any axis weights. We have the *mechanism* (the
  grader loop), only the blog's *paraphrase* of the rubric. *Why for Fast:* our slim adversarial
  critic (step 12 E3) and the grounding pass would be sharper with the real rubric text. *Method:*
  prompt-extraction against claude.ai Research, or capture the `define_outcome` grader payload.

- **CLR-2 (P1, pairs with OAI-2) — CitationAgent verification behavior.** The byte-identical gate is
  known; the exact decision for *borderline* support (paraphrase that drifts) is not. *Why for Fast:*
  directly specs our slim grounding pass's accept/flag/drop thresholds.

- **CLR-3 (P2) — `run_blocking_subagent` full schema.** Prose documents `prompt: str`; whether the
  lead also sets per-subagent `model`/`tools`/`max_tool_calls` is unknown (CE3.14 #1). *Why for Fast:*
  confirms whether our breadth fan-out should pass per-sub-researcher caps or rely on prompt-level
  `stop_conditions` (we currently do the latter).

*Out of scope:* the server-side `managed_agents` session/coordinator graph, memory-file mounts,
`encrypted_content` search results, the RL tool-use training.

---

## 4. Gemini Deep Research

**What we already have:**
- The control flow: planner → **user-editable plan gate** (`collaborative_planning`, the
  `requires_action` state) → executor loop → single-large-context synthesis (GEMINI_DEEP_RESEARCH
  §R3.4, §R4.6). The plan gate is mirrored in our step 1.6.
- The 5-step API loop (decompose → search-plan → retrieve → iterative refine → synthesize, §R2.4).
- Two-layer parallelism (N queries per call + N concurrent calls), the `{success/error/paywall/
  unsafe}` fetch-status enum (§R3.6), the dynamic-retrieval "should I search?" gate (§R3.10).
- URL-level inline citations `[claim](url)` backed by byte-span `GroundingSupport` +
  `confidenceScores` (§R3.10).
- Numbers: 3-8 min median, hard cap 60 min; ~80 queries / $1-3 standard, ~160 / $3-7 Max.

**Delta — what's missing:**

- **GEM-1 (P1) — the plan-generation prompt + plan JSON schema.** The verbatim DR planner/synthesizer
  prompt has **never leaked** (open across all 4 rounds); tool schemas/citation rules are inferred
  from *sibling* prompts. *Why for Fast:* our optional `--plan` opt-in (design §3/§4) and the
  scope-brief would benefit from Gemini's actual plan structure (it's the best editable-plan UX in
  the set). *Method:* mitmproxy on a paid Gemini Advanced DR call with `collaborative_planning:true`;
  capture the plan turn's request/response.

- **GEM-2 (P2) — plan-step → search-batch mapping.** "Each plan step gets a 3-15 tool-call budget" is
  *inferred*, never sourced. *Capture:* log which `queries[]`/`urls[]` fire under each plan step in a
  multi-step run. *Why for Fast:* informs how our breadth branch maps sub-questions → sub-researchers.

- **GEM-3 (P2) — the `{paywall/unsafe}` routing behavior.** We know the enum exists; the *action* the
  agent takes on each outcome (skip / retry / substitute) is not captured. *Why for Fast:* cheap
  quality/speed win for our funnel — route around dead/paywalled URLs instead of burning a read.

*Out of scope:* Google Search Grounding + `groundingMetadata` pipeline, Nano Banana charts,
NotebookLM audio, file-search stores, the 1M-context economics (we don't have it keyless).

---

## 5. Grok Heavy

**What we already have:**
- The corrected architecture: a **symmetric N-agent ensemble** (`agent_count ∈ {4,16}`), agent #1 =
  leader (only one with render/citation components), peers get the same prompt/tools/query
  (GROK_HEAVY §R2.4). The **leader-only-render rule** (§R2.2) is what we adopt for the breadth branch
  (lead is the only writer).
- Coordination = a continuous `chatroom_send`/`wait` message bus, not a final reduce (CE.3).
- Termination = turn-bounded + 200s global / 120s per-wait timeout, **no convergence metric** (§R3.7).
- Character-span citations `InlineCitation{id,start_index,end_index, web|x|collections}` (§R3.4);
  median wall-clock 2-3 min even at N=16 (parallel).

**Delta — what's missing:**

- **GRK-1 (P2) — the leader's delegation wording.** The `chatroom_send` *transport* is known; the
  *assignment text* (how the leader splits the query among peers) is left to the model and not
  captured (CE.3). *Why for Fast:* our breadth branch's lead→sub-researcher task text could borrow
  it; but we already have Claude's superior typed delegation contract, so this is low priority.

- **GRK-2 (P2) — how the leader weights conflicting peer findings at synthesis.** With no agreement
  metric, the leader just synthesizes whatever exists at timeout — *how* it reconciles disagreement
  is unknown. *Why for Fast:* our lead synthesis on breadth must reconcile sub-researcher conflicts;
  worth one capture, but our slim critic + Full's dialectic machinery already cover contested cases.

*Out of scope:* the native X firehose integration (the moat), `agent_count=16` roster internals,
prefix-cache economics, the RL tool-use training. Grok contributes essentially **one** pattern we
need (leader-only synthesis), which we already have from the design — so Grok is the **lowest-yield**
source for the Fast build. Don't spend much RE budget here.

---

## 6. Priority-ordered capture plan (minimal sessions)

The whole delta collapses to **~3 capture sessions**:

1. **Session A (P0) — Perplexity DR + OpenAI DR stop behavior** (XSTOP-1, OAI-1, PPX-2, PPX-3).
   10-20 queries each, mitmproxy/devtools, log per-step new-domains/URLs + step counts. *Output:* the
   numeric stop rule + `FAST_MAX_STEPS`/`--max-queries` calibration.
2. **Session B (P1) — planner & citation prompts.** Perplexity planner prompt (PPX-1), OpenAI
   citation placement (OAI-2), Claude rubric + CitationAgent borderline behavior (CLR-1, CLR-2),
   Gemini plan prompt+schema (GEM-1). Prompt-extraction + one traced run each. *Output:* the Fast
   planner/reflect prompt + the slim grounding-pass spec.
3. **Session C (P2) — mapping & routing nice-to-haves.** Plan→batch mapping (GEM-2), paywall routing
   (GEM-3), subagent schema (CLR-3), Grok delegation/synthesis (GRK-1/2). Only if time allows.

**Tooling reminder:** all of this needs paid tiers (Perplexity Pro, ChatGPT Plus/Pro, Gemini
Advanced, Claude with Research, SuperGrok Heavy) and a TLS-intercepting proxy (mitmproxy/Burp) or
browser devtools to read the `text/event-stream` SSE responses. Respect each ToS; this is for
interoperability/competitive analysis of observable behavior, not redistribution of prompts.

---

## 7. Explicitly OUT of scope (do NOT spend RE budget)

These are proprietary and irrelevant to a keyless host-LLM Fast mode — substitute, don't replicate:
- Search **indexes/crawlers** (Perplexity Vespa 200B URLs; Google Search Grounding) → host web-search.
- **Embedders / rerankers** (pplx-embed, cross-encoder/XGBoost, semantic-ranker-512) → our keyless
  LLM reranker + FTS5/BM25.
- **Inference engines** (ROSE, MoE kernels, speculative decoding, prefill/decode disaggregation).
- **RL tool-use training** (OpenAI o3-DR policy, Grok's RL sandbox) — the un-closeable quality delta;
  we accept it and compensate with prompt discipline + the grounding pass + the slim critic.
- Server-side orchestration graphs (`managed_agents`, Gemini state machine internals), sandboxes,
  OAuth connector proxies, X firehose, NotebookLM/Nano-Banana media.
