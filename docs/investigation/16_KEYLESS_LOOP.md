# 16 — The Keyless Deep-Research Loop: Patterns the Host Runs (No API Keys)

**Theme.** Bad Research is a **keyless** Claude Code skill: the Claude Code host
*is* the orchestrator + the subagents. There is no service to call — the
deep-research loop, the anti-bullshit gates, and the grounding contract are all
**prompt-level / orchestration-level / deterministic-Python** techniques the host
itself runs. This dossier mines the frontier DR teardowns for the *loop + quality +
grounding* patterns that are **inherently keyless** (a prompt is keyless; a
threshold is keyless; a fan-out rule run via the Task tool is keyless) and maps
each to **the exact skill stage / orchestrator rule / deterministic gate** that
reimplements it — with a sharp focus on **what we have NOT yet built or could
strengthen**.

**Why this is different from 05/07/08.** Dossiers 05 (DR-loops), 07 (quality
filter), 08 (grounding) were *first-pass* and full of `IDEA` proposals. Most of
those IDEAs are now **shipped code**: the clarifier (`bad-research-0.5-clarify`),
the router (`skills/router.py` + `bad-research-query-router`), the agentic-fast
ReAct loop (`bad-research-agentic-fast`), the 3-tier CitationVerifier
(`grounding/verifier.py` + `bad-research-11.5-citation-verifier`), the fresh-review
(`bad-research-fresh-review`), the deterministic no-uncited gate
(`grounding/gate.py`), and the whole prefilter/dedup/relevance/rank stack
(`quality/*.py`). This dossier **re-baselines against the code as built**, then
isolates the residual gaps. Where 05/07/08 said "ADOPT (IDEA)," this file says
**HAVE** (cite the file) or **NET-NEW** (cite the gap + the keyless plan).

**The keyless constraint, stated once.** Every pattern below is reimplementable
with ONLY: (a) the Claude Code host as orchestrator (the entry skill +
`Skill`/`Task`/`TodoWrite` + tool-allowlists), (b) the host spawning subagents via
the `Task` tool, (c) deterministic Python gates in `bad_research/*` run via `Bash`,
and (d) a local NLI model (`nli-deberta-v3-base`, $0). No frontier DR *service* is
ever called; we steal their *techniques*, not their APIs. Each pattern ends with
**Keyless reimplementation:** naming the stage/rule/gate.

**Label key:** **KNOWN** = verbatim from a teardown / read from our source.
**INFERRED** = cross-derived. **HAVE** = already shipped (file cited).
**NET-NEW** = the gap this dossier flags + the keyless plan to close it.

**Sources.** `teardowns/{OPENAI_DEEP_RESEARCH,GEMINI_DEEP_RESEARCH,PERPLEXITY_DEEP,
GROK_HEAVY,CLAUDE_RESEARCH}.md` (cited `[ODR]/[GDR]/[PPLX]/[GROK]/[CLR]`); our
code under `src/bad_research/`; dossiers 05/07/08 (cited `[05]/[07]/[08]`).

---

## 0. The keyless map — every frontier mechanism → where it lives in our host

| Frontier mechanism | Keyless because… | Our reimplementation | Status |
|---|---|---|---|
| OpenAI 2-agent clarifier `[ODR §5]` | a prompt-level intake decision | `bad-research-0.5-clarify` (Haiku-tier, default-proceed, ≤3 Q) | **HAVE** |
| Gemini plan-gate `[GDR §5]` | rendering a plan + waiting = host UI | decomposition surfaced via `--interactive`; locked-on-start | **HAVE (partial)** |
| Query-complexity router `[05 §9.2]` | a deterministic decision tree over decomposition | `skills/router.py` `classify_route()` | **HAVE** |
| Claude depth-1 parallel fan-out `[CLR §CE.2]` | N `Task` calls in one assistant turn | `bad-research-2-width-sweep` 10–12 fetchers in one msg | **HAVE (counts only)** |
| Claude 4-field delegation contract `[CLR §CE.2]` | a prompt schema | only 3-piece (query/position/inputs) in spawn contract | **NET-NEW** |
| Per-subagent caps (300s / 3·10·20·30 / 100-src) `[CLR §CE.5]` | a runtime guard the host enforces | only agentic-fast has prose bounds; full-pipeline Tasks unbounded | **NET-NEW** |
| Perplexity step-bounded ReAct `max_steps≤10` `[PPLX §R3.2]` | a loop counter the host runs | `bad-research-agentic-fast` (10/15/300s) | **HAVE** |
| Perplexity planner→writer split `[PPLX §R3.8]` | two prompts, writer sees evidence not CoT | agentic-fast + Stage-11 synthesizer `[Read,Write]`-lock | **HAVE** |
| `execute_python` in-loop `[PPLX §R3.14]` | host runs `python -c` via Bash | agentic-fast ACT phase | **HAVE (fast only)** |
| Per-sentence single-index `[N]` citation `[PPLX §R3.6]` | a prompt rule + a render | `grounding/render.py` + every writer prompt | **HAVE** |
| OpenAI line-range grain `【ref†L42-L58】` `[ODR §9]` | char offsets computed deterministically | `grounding/extract.py` (`char_start/end` + `quote_sha`) | **HAVE** |
| Claude CitationAgent re-ground `[CLR §8]` | a verification pass the host runs | `grounding/verifier.py` 3-tier cascade | **HAVE** |
| Claude `define_outcome` 5-axis judge `[CLR §13]` | a single LLM call with a rubric | `calibrate/judge.py` (but **offline only**) | **HAVE (offline)** |
| Claude grader **revision loop** (judge→revise→re-judge) `[CLR §13]` | a host loop | no in-pipeline grader loop exists | **NET-NEW** |
| Gemini RECITATION verbatim-block `[GDR §R3.9]` | an n-gram overlap check (no decoder needed) | absent | **NET-NEW** |
| OpenAI reasoning_effort 4-level `[ODR §R2.11]` | a tier→model/fan-out continuum | `--reasoning-effort` flag declared but **ignored** (`research.py:118`); binary tier in practice | **NET-NEW (stub)** |
| Perplexity per-component metering `[PPLX §R3.5]` | token accounting the host tracks | none; no per-run ceiling | **NET-NEW** |
| Gemini confidenceScores → hedge `[GDR §879]` | a band → a hedge word | `verify_score` computed, not propagated to hedging | **NET-NEW (partial)** |
| SEO-farm / source-authority gate `[07 §1]` | regex + a static tier table | `quality/prefilter.py` | **HAVE** |
| Shingle-Jaccard dedup 0.60 `[07 §3]` | a hash pass | `core/similarity.py` + `funnel/dedup.py` | **HAVE** |
| 0.70 relevance drop / <30% re-retrieve `[07 §4]` | thresholds on a local rerank | `quality/relevance.py` + funnel | **HAVE** |
| Untrusted-content injection preamble `[07 §2.4]` | a verbatim prompt constant | shared preamble on page-touching prompts | **HAVE** |

**The thesis of this dossier:** everything above is keyless. We have ~80% of it.
The residual five (`NET-NEW`) are the in-pipeline grader loop, the 4-field
delegation contract + runtime caps, the RECITATION-equivalent overlap gate, the
reasoning_effort continuum + token ceiling, and confidence-band hedging. §§3–7
spec each at reimplementable depth and name the exact stage it lands in.

---

## 1. The Loop — what we have, stated against the frontier

The host runs three loop shapes, routed by `skills/router.py`:

**Route `agentic-fast` (the Perplexity engine, keyless).** `bad-research-agentic-fast`
is a verbatim port of the Perplexity DR loop `[PPLX §R3.2,§R3.14]`:

```
step=0; calls=0; deadline=now+300s          # AGENTIC_FAST_TIMEOUT_S
while step<10 and now<deadline:              # AGENTIC_FAST_MAX_STEPS (Perplexity max_steps)
    THINK  → one paragraph to react-trace.md (the auditable (thought,action,obs))
    if coverage complete: break              # model-judged stop (OpenAI diminishing-returns)
    ACT    → bad funnel-gather "<q>" (a LIST of queries, fanned out — not one search)
    OBSERVE→ bad retrieve "<ORIGINAL verbatim query>"   # rerank vs un-rewritten query [PPLX §R3.7]
    if calls>=15: break                      # AGENTIC_FAST_MAX_CALLS (Claude guard)
WRITER (system B): sees RANKED chunks, NOT the planner trace → single-pass [N]-cited answer
```
The bounds live frozen in `routing_constants.py` (`AGENTIC_FAST_MAX_STEPS=10`,
`MAX_CALLS=15`, `TIMEOUT_S=300`). This is **keyless**: the loop counter, the
model-judged break, the `python -c` math tool, and the writer split are all things
the host *does*, not services it *calls*. **HAVE.**

**Route `light` / `full` (the fixed 16-stage pipeline).** The loop here is the
*stage graph* — the host invokes `Skill(bad-research-N-…)` in sequence; each stage
loads fresh, defeating context-rot (the V8 design, the one thing every frontier
product lacks — they all run one long trajectory + `memento`-style self-summary
`[ODR §R2.3]`, `[CLR §CE.6]`). Termination is **structural** (stage 16 completes),
not budget-based. **HAVE — and superior to the frontier on this axis.**

**Parallel subagent fan-out (Claude depth-1, keyless via Task).** `bad-research-2-
width-sweep` partitions the search queue into **10–12 non-overlapping batches of
8–12 URLs** and spawns **10–12 `bad-research-fetcher` subagents in ONE message** —
the host's `Task`-tool equivalent of Claude's `batch = parallel()` (`N` tool_use
blocks in one assistant turn `[CLR §CE.2]`). Depth-1 is enforced structurally:
fetchers do not spawn fetchers. Cap of 6 source-analysts. This *is* Claude's
fan-out, keyless. **HAVE — but missing the delegation contract + runtime caps (§3).**

**What the loop does NOT yet have (the two loop gaps, both NET-NEW):**
1. The **4-field delegation contract** on the full-pipeline `Task` spawns (§3.1).
2. **Runtime per-subagent caps** (timeout / tool-call ceiling / source kill) on the
   full-pipeline fetchers/investigators/critics — only `agentic-fast` is bounded (§3.2).

---

## 2. Grounding — what we have, stated against the frontier

The grounding contract is the **most-built** part of the system. The full no-
hallucination spine from `[08 §6]` is shipped:

**Forward defense 1 — binding at fetch (keyless, $0).** `grounding/extract.py`
`extract_spans()` turns each `quoted_support` into `(char_start, char_end)` by
exact `body.find()` → rapidfuzz partial-ratio ≥ 95 fallback → **drop the claim if
neither locates it** ("a quote that isn't in the body is a hallucinated quote").
This is OpenAI's line-grain `[ODR §9]` + Gemini's `Segment{startIndex,endIndex}`
`[GDR §836]` reimplemented as a deterministic post-step on the fetcher output. The
`anchor_id = quote_sha = sha256(quoted_support)[:8]` is the byte-identity key.
**HAVE.**

**Forward defense 2 — writer-sees-evidence (keyless prompt-lock).** Stage-11
synthesizer is a fresh Opus session tool-locked to `[Read, Write]`; its inputs are
a closed set (3 drafts + evidence-digest + tensions), never the orchestrator's CoT.
This is Perplexity's planner→writer isolation `[PPLX §R3.8]` enforced by the host's
tool-allowlist. **HAVE.**

**Backward defense 1 — the 3-tier CitationVerifier (keyless cascade).**
`grounding/verifier.py` `CitationVerifier.verify()`, cheapest-first per cited
sentence:
- **Tier A — byte-identity ($0):** `tier_a_byte_identity()` re-`find`s the quote at
  `[char_start:char_end]` + SHA-matches `anchor_id`. Fail → `UNSUPPORTED` (a
  fabricated quote, the most dangerous hallucination, killed at zero cost). This is
  the executable form of OpenAI's *"never cite a ref you didn't open"* `[ODR §9]`.
- **Tier B — local NLI ($0):** `nli.py` `CrossEncoderNLI` runs
  `nli-deberta-v3-base` with `premise=quoted_support`, `hypothesis=report sentence
  AS WRITTEN` (citation tokens stripped — this catches a synthesizer sentence that
  *drifted* from the claim it cites). `classify_nli()` checks contradiction
  (≥0.50) **before** entailment (≥0.70) so a quote that says the opposite is never
  silently passed. Label resolution is by **name not position** (`_label_index`) —
  the anti-silent-inversion fix so a checkpoint that orders logits differently
  can't flip every verdict.
- **Tier C — triage-LLM judge (cents):** only the NLI-*neutral* band escalates,
  batched 20 pairs/call, verbatim `JUDGE_SYSTEM` prompt. This is the cost-correct
  split — 90%+ resolve free, ~10% pay a Haiku-class call.

Dispositions persist to `claim_anchors` (`set_verified`): `supported→verified=1`;
everything else `verified=0`. **HAVE — this is Claude's CitationAgent `[CLR §8]`
reimplemented keyless, with two free tiers the frontier doesn't have.**

**Backward defense 2 — the deterministic no-uncited gate (keyless, $0).**
`grounding/gate.py` `no_uncited_claim_gate()`: for every non-trivial factual
sentence (`is_factual_claim()` = has a number / named entity / comparative /
causal-temporal, and is not a question / meta-stem / hedge-opener), require a
**verified** citation. Three failure modes: `uncited-claim` (critical),
`dangling-cite` (critical, `[N]` → no anchor), `unverified-cite` (major, anchor
exists but `verified≠1`). `gate_blocks_ship()` hard-blocks ship on any critical.
**No LLM — pure string + table.** This is the belt to R2-density's suspenders, and
it runs for **ALL routes** (the entry skill: "ship-block for ALL routes"). **HAVE.**

**Contradiction surfacing (keyless, the strongest axis).** Stages 3/7/8
(contradiction-graph + consensus-claims + source-tensions + corpus-critic "what
would overturn this?") are intact — the best contradiction machinery of all five
products and unique to us. **HAVE.**

**The one grounding gap (NET-NEW, partial):** `verify_score` is computed and stored
but the **`final_confidence` band** (fetcher-confidence × verify_score ×
n_independent_sources → high/medium/low → a *hedge word in the prose*) from
`[08 §4]` is not propagated into the patcher. The verifier knows a claim is
"partial," but the patcher isn't yet told to soften it to "the evidence suggests…"
(§7).

---

## 3. NET-NEW: the delegation contract + runtime caps (loop hardening)

**The gap.** The entry skill's "Subagent spawn contract" requires three pieces:
verbatim `research_query`, a pipeline-position sentence, and the subagent's inputs.
That is **half** of Claude's contract. Claude's 4-field delegation `[CLR §CE.2,
§6 principle 2]` (KNOWN verbatim) requires **`{objective, output_shape,
tools_allowed, stop_conditions}`**, and the single field whose absence is a
documented failure mode is `stop_conditions` — *"endless web searching for
nonexistent sources"* `[CLR §14 #2]`. None of the full-pipeline skill spawn
templates (`bad-research-2-width-sweep`, `-5-depth-investigation`, `-12-critics`,
`-fresh-review`) carry `stop_conditions`, `output_shape`, or a runtime cap.
Only `agentic-fast` is bounded, and only in prose. Confirmed: `grep -rEl
"stop_conditions|output_shape|tool_call_cap" skills/*.md` → **zero hits**.

### 3.1 The 4-field delegation contract (keyless — it's a prompt schema)

Extend the entry-skill spawn contract from 3 pieces to **3 + 4** for every `Task`:

```
SUBAGENT SPAWN CONTRACT (every Task prompt, near the top):
  research_query     : <verbatim block-quoted GOSPEL query>      # HAVE
  pipeline_position  : "you are step N; N-1 produced X; N+1 does Y"  # HAVE
  inputs             : {vault_tag, output_path, locus, ...}      # HAVE
  ── add: ───────────────────────────────────────────────────────
  objective          : "<single self-contained sub-objective>"   # NET-NEW (Claude field 1)
  output_shape       : "<exact return format, e.g. 'JSON array of
                        {claim, note_id, quoted_support, char_start, char_end}'>"  # field 2
  tools_allowed      : ["web_search","fetch_url","execute_python"]  # field 3
  stop_conditions    : "halt when 3 primary sources found OR 10 tool calls used"  # field 4
```

`output_shape` is more than cosmetics: pinning the fetcher's return to the exact
`claims-*.json` schema (incl. `char_start/end`) is what makes the §2 binding
deterministic downstream. **Keyless reimplementation:** edit the "Subagent spawn
contract" section of `skills/bad-research.md` to mandate the 7-field shape, and add
the four fields to each step skill's spawn template. Zero new infra — it's a prompt
schema the host fills in.

### 3.2 Runtime per-subagent caps (keyless — the host enforces them)

Claude's caps are runtime guards, not prompt hopes `[CLR §CE.5,§CE.10]`:

| Tier | sub-agents | tool-calls/agent | total-token budget |
|---|---|---|---|
| Simple | 1 | 3–5 | ~20K |
| Standard | 3–5 | 5–10 | ~150K |
| Complex | 10–15 | 10–20 | ~1.5M |
| Deep | 20+ | 15–30 | ~5M |

Per-subagent **timeout 300s** → soft-fail with accumulated findings; **100-source**
hard kill. Map these onto our routes and freeze them beside the agentic-fast bounds
in `routing_constants.py`:

```python
# NET-NEW — full-pipeline per-subagent caps (Claude CE.5), keyless host guards.
FETCHER_TOOLCALL_CAP   = {"light": 10, "full": 20}   # tool calls per fetcher
FETCHER_TIMEOUT_S      = 300                          # soft-fail, return partial
INVESTIGATOR_TIMEOUT_S = 900                          # depth stage scaled (Grok 200s × cost)
SUBAGENT_SOURCE_KILL   = 100                          # hard stop (Claude)
```

The host enforces a timeout by wrapping each `Task` with a wall-clock budget in the
spawn prompt's `stop_conditions` ("if 300s elapse, stop and return what you have")
AND by the orchestrator checking elapsed time between batch waves. The tool-call
cap is stated in `stop_conditions` ("≤20 tool calls") and is a soft prompt-level
contract — the host has no hard interrupt on a subagent mid-flight, so this is a
*prompt guard + an orchestrator-side timeout on the batch*, not a kernel kill.
**Keyless reimplementation:** `stop_conditions` text (prompt) + an
orchestrator-side per-wave deadline (`bad-research-2-width-sweep` step 2.4: "if a
fetcher wave exceeds FETCHER_TIMEOUT_S, proceed with returned results"). The
constant table lives in `routing_constants.py`. **No service call.**

**Why this matters and is not overkill:** without `stop_conditions`, a fetcher
handed a thin sub-topic burns its whole budget "searching for nonexistent sources"
— the exact `[CLR §14 #2]` failure. The fix is four lines of prompt schema + four
frozen constants. Cheap insurance.

---

## 4. NET-NEW: the in-pipeline grader LOOP (judge → patch → re-judge)

**What we have vs. the gap.** `calibrate/judge.py` `LLMJudge` is the **exact**
Claude `define_outcome` 5-axis judge `[CLR §13]` — a **single** strong-model call
(NOT an ensemble; ensemble tested worse, `[CLR §13]`), scoring `factual / citation
/ completeness / source_quality / efficiency` 0.0–1.0, PASS iff every axis ≥ 0.70
AND mean ≥ 0.75 (`calibrate/constants.py`). The verbatim `JUDGE_SYSTEM` rubric is
shipped. **But** it is wired **offline only** — `cli/calibrate.py` /
`calibrate/harness.py` call `judge.judge()` to score our replica against frontier
baselines on the 20-query eval set. There is **no per-run, in-pipeline grader
loop**: the file's own docstring says *"OFFLINE calibration only — never a per-run
gate."*

Claude's `define_outcome` is more than one-shot grading — it is a **grader LOOP**:
the agent revises its output up to ~20 times until the LLM-judge passes `[CLR §13,
managed-agent]`. We run critics **once** → patch **once** → ship. We have the judge
*and* the patcher; we have never connected them into a loop.

### 4.1 The keyless grader loop (Stage 12.5, gated, full-tier only)

Insert a host-run loop **after the critics (12) + gap-fetch (13), inside the patch
phase**, so the judge sees a report that has *already* had its citations verified
(11.5) and its critic findings patched — the judge's `citation` axis then mostly
passes, isolating the other four. (Note: 11.6 is **already taken** — the synthesizer
spawn is `bad-research-11-synthesize` Step 11.6 — so the grader loop slots at **12.5**,
between critics/gap-fetch and the patcher's final convergence.)

```
GRADER LOOP (full tier only; host-run; keyless):
  revisions = 0
  while revisions < MAX_GRADER_REVISIONS:        # cap = 3, NOT 20 (see below)
      verdict = bad grade-report --report <path> --corpus <evidence-digest> --json
      #  → LLMJudge.judge(): 5 axes 0.0-1.0 + PASS/FAIL + a findings list
      if verdict.passed: break
      # the FAILING axes' findings join the critic + verifier findings:
      append verdict.findings → research/critic-findings-grader.json
      run patcher (step 14) over the combined finding set   # surgical Edits only
      revisions += 1
  # PASS or cap reached → proceed to fresh-review (14.5) → polish (15) → gate (16)
```

**Why cap = 3, not Claude's 20.** Claude's 20-revision cap assumes *full
regeneration* each round. Our **PATCH-NEVER-REGENERATE** invariant means each
revision is a small surgical Edit — convergence is far faster; 3 is sufficient and
respects the cost ceiling `[05 §6]`. Freeze it: `MAX_GRADER_REVISIONS = 3`.

**The judge findings must be patcher-shaped.** Today `LLMJudge` returns scalar axis
scores + a 2-sentence rationale — not actionable findings. The keyless change to
`calibrate/judge.py` (or a thin wrapper `quality/grader.py`): when invoked
in-pipeline, extend the rubric to also emit a `findings` array in the existing
`Finding{failure_mode, severity, location, recommendation}` shape the patcher
already consumes (the same shape the critics and the gate use). The judge prompt
gets one appended clause:

```
Also output "findings": a JSON array of the SPECIFIC defects behind any axis < 0.8,
each {axis, severity:"critical|major|minor", failure_mode:"missing|under-covered|
miscited|misordered", location:"<H2 or sentence>", recommendation:"<surgical fix>"}.
A critical finding is one that, left unfixed, makes an axis fail. Map completeness
misses to the decomposition's required_section_headings + atomic items.
```

**Keyless reimplementation:** a new gated stage `bad-research-12.5-grader` invoked
by the entry skill for `full` only, after critics (12)/gap-fetch (13), folded into
the patcher (14) convergence loop. It calls `bad grade-report` (the in-pipeline mode
of `LLMJudge`), feeds failing-axis findings to the existing patcher, and re-grades.
The loop counter is a host `TodoWrite`/orchestrator-note variable. The judge is a
single LLM call — no service, no key. This is the single largest **NET-NEW** quality
lever: we built the judge and never let it gate a run.

**Anti-overkill guard:** this is `full`-tier only and capped at 3. It does NOT run
on `light`/`agentic-fast` (their quality contract is the forward binding + the
deterministic gate). A grader loop on a $1 fast query is the overkill we explicitly
reject `[07 §6]`.

---

## 5. NET-NEW: the RECITATION-equivalent verbatim-overlap gate

**The gap.** Gemini's RECITATION `[GDR §R3.9]` is a decode-time tripwire that blocks
output reproducing source text too closely. We **CUT** the decoder-level mechanism
(`[08 §1.4]` — we can't control a hosted model's logits), but the *output
guarantee* (no verbatim copying of a source span into the report) is achievable
keyless with an **n-gram overlap check** — and we never built it. Confirmed:
`grep -rEil "recitation|verbatim.overlap|ngram"` → **zero hits**. Today the only
protection is the synthesizer's *"paraphrase, don't paste"* prompt rule + the
≤2-sentence/≤50-word `quoted_support` cap — prompt hopes, not a gate.

### 5.1 The keyless overlap gate (deterministic, $0, folded into Stage 16)

For each report sentence, check its longest verbatim run against every cited note's
body; flag if it copies too much:

```python
# NET-NEW quality/recitation.py — deterministic, $0, no LLM. Folds into the
# Stage-16 readability/polish gate beside no_uncited_claim_gate.
RECITATION_MAX_NGRAM   = 12     # a verbatim run > 12 words from a source = copying
RECITATION_MAX_OVERLAP = 0.50   # >50% of a sentence's tokens are a contiguous source run

def recitation_findings(report_md, note_bodies) -> list[Finding]:
    findings = []
    for sent in split_sentences(strip_sources_section(report_md)):
        toks = words(sent)
        for body in note_bodies.values():
            run = longest_common_contiguous_run(toks, words(body))   # word-level LCS-run
            if len(run) > RECITATION_MAX_NGRAM or len(run)/max(1,len(toks)) > RECITATION_MAX_OVERLAP:
                findings.append(Finding("recitation", "major", sent,
                    "Sentence reproduces a source span verbatim — paraphrase and cite [N]."))
                break
    return findings
```

The check is cheap (word-level contiguous-run match over the small per-run corpus,
not character suffix-arrays). A `major` finding routes to the patcher to paraphrase;
it does not block ship (unlike the no-uncited critical gate) — copying is a quality/
legal smell, not a correctness failure. Public-domain / direct-quote-with-attribution
exceptions mirror Gemini's carve-outs (`[GDR §R3.9]`: public-domain, user-input
transcription, common phrases) — exempt a sentence whose verbatim run is itself
inside an explicit `"…"` quotation with an adjacent `[N]`.

**Keyless reimplementation:** `quality/recitation.py` run in
`bad-research-16-readability-audit` (the same stage as the no-uncited gate), feeding
the patcher. Pure string ops, $0. This gives RECITATION's *output* guarantee without
RECITATION's *decoder* machinery — exactly the `[08 §1.4]` CUT/ADOPT split, now built.

---

## 6. NET-NEW: the reasoning_effort continuum + per-run token ceiling

**The gap.** We have a **binary** tier (`light` / `full`) plus the `agentic-fast`
route. OpenAI's lesson `[ODR §20 #7]` is that the reasoning-effort dial is *"the
cleanest cost knob in agentic AI"* — a **4-level** continuum (`minimal/low/medium/
high`, `[ODR §R2.11]`). Claude's empirical law `[CLR §11–12]` is that **token usage
alone explains 80% of quality variance**, with the optimization order **spend tokens
first → optimize tool patterns → upgrade model**. We expose neither the continuum
nor a per-run token/cost ceiling. (There **is** a `--reasoning-effort` flag declared
in `cli/research.py:118`, but it is **defined-and-ignored** — it appears exactly once,
the option declaration, never plumbed to the router, tier, or provider. The dial is a
stub, not a continuum.) Perplexity's per-component metering
(`input + output + reasoning + citation + searches`, `[PPLX §R3.5]`) gives the user
a cost breakdown we don't surface.

### 6.1 The keyless effort continuum (a tier→model/fan-out mapping)

Map a single `--effort` knob onto the existing tier + model + fan-out levers — no
new model behavior, just a host-side configuration the router consumes:

| `--effort` | route | drafters | subagent fan-out | extended-thinking |
|---|---|---|---|---|
| `minimal` | light, single draft, no loci | Haiku-tier | fetchers ≤4 | off |
| `low` | light | Sonnet-tier | fetchers ≤8 | off |
| `medium` | full, default | default | fetchers 10–12, loci ≤4 | on (orchestrator) |
| `high` | full, max | Opus-tier | fetchers 12, loci ≤6, deep investigators | on (all planning) |

This makes the binary tier a **continuum** — OpenAI's exact 4-level enum, keyless,
expressed as a router config. **Keyless reimplementation:** **wire the existing
stub `--reasoning-effort` flag** (`cli/research.py:118`) through to the bootstrap and
`skills/router.py`, which consumes it to nudge the route + the per-stage fan-out
constants. The model tiers are the existing `triage/light/heavy` LLM tiers. (A
`--effort` alias maps to the same 4-level enum.) The flag is declared today but
ignored — this is plumbing, not a new surface.

### 6.2 The keyless per-run token ceiling + graceful degradation

Track cumulative tokens in an orchestrator-note running total; if approaching a
user-set `--max-tokens` cap, degrade in **Claude's order** (`[CLR §12]`: cut tokens
**last**):

```
DEGRADE ORDER when approaching the token ceiling (Claude optimization order):
  1. cut tool-call redundancy first  (skip the redundancy-audit sub-step)
  2. then cut fan-out width           (fewer fetchers / fewer loci)
  3. then cut model tier              (heavy → light on non-critical stages)
  4. NEVER cut the synthesis/grounding token budget — that's the 80%-variance core
```

Surface the Perplexity-style breakdown at the end: `{input, output, reasoning,
citation_tokens (source text ingested), num_search_queries}` — we already track
source counts; add token accounting so the user sees *why* a full run costs
$60–120. **Keyless reimplementation:** a host-side counter in
`research/temp/orchestrator-notes.md` (or a `bad meter` CLI summing the run's LLM
calls), plus the degrade-order rule in the entry skill's invariants. No service —
the host already sees every token it spends.

**Anti-overkill:** the ceiling is opt-in (`--max-tokens`); the default is the
existing per-tier budget. We do not build a billing system — we surface a count.

---

## 7. NET-NEW (partial): confidence-band hedging into the patcher

**The gap.** `verifier.py` computes `verify_score` and stores it on `claim_anchors`,
but nothing turns it into a **hedge word in the prose**. `[08 §4]` specified
`final_confidence(claim) = f(fetcher_confidence, verify_score, n_independent_sources)`
→ band → hedge:

```
high   : fetcher=high AND verify_score≥0.70 AND n_sources≥2  → assert plainly, no hedge
medium : verify_score 0.40-0.70 OR n_sources==1              → "the evidence suggests / one source reports"
low    : verify_score<0.40 OR fetcher=low                    → "preliminary / a single commentary claims"
```

The verifier already knows `verify_score`; the fetcher already wrote
`confidence: high|medium|low`; Stage 3 already wrote `consensus-claims.json` (the
`n_independent_sources ≥ 3` set). Combining them is deterministic. The missing wire:
the CitationVerifier (11.5) should emit, per cited sentence, a `confidence_band`
into `citation-verify-actions.json`, and the **patcher must add a hedge to any
medium/low claim the synthesizer asserted too confidently**. This turns "the
synthesizer over-asserted" from a vibe into a concrete, evidence-driven patcher
finding.

**Keep the number off-band.** Gemini keeps `confidenceScores` in metadata, not prose
`[GDR §879]` — follow that. The prose carries the *hedge word*; the raw 0.0–1.0 score
lives on `claim_anchors.verify_score` for the CLI/audit only. Surfacing raw scores
in the body is the CUT `[08 §4.2]`.

**Keyless reimplementation:** extend `verifier.py` to compute `confidence_band`
(it has `verify_score`; pass it the fetcher-confidence + consensus count from the
claims JSON), write it into the disposition JSON, and add a hedging clause to the
patcher's instruction set (`bad-research-14-patcher`): *"for any claim with
`confidence_band ∈ {medium, low}` asserted without a hedge, add the band-appropriate
hedge frame; do not change the citation."* Deterministic band + a patcher prompt
rule. No service.

---

## 8. The honest "don't build this" list (keyless ≠ build-everything)

The keyless constraint does not mean we port every frontier mechanism. These remain
**CUT** because they are either not keyless or are overkill (per `[05 §11]`, `[07 §7.3]`,
`[08 §7]`):

- **Gemini RECITATION decode-time tripwire** — needs decoder/logit control we don't
  have. We build the *output guarantee* (§5 overlap gate), not the mechanism.
- **Grok N=16–32 parallel full instances + debate** `[GROK §10]` — 16–32× cost for a
  "wisdom of crowds" gain our 3-draft ensemble + critics + (now) grader loop achieves
  at ~⅒ the cost. We do **not** ensemble whole pipelines. Keyless ≠ free; spawning 32
  full subagent trees would blow the host's budget.
- **OpenAI `memento` self-summarization** `[ODR §R2.3]` — a band-aid for context rot we
  *structurally* avoid via skill-as-stage fresh-loading. Building it would be a
  regression.
- **Perplexity learned engagement click-stream decay** `[07 §1.5]` — no user click
  stream in a stateless CLI skill.
- **Perplexity 3-model L1/L2/L3 rerank ladder + XGBoost + DeBERTa 3-model voting**
  `[07 §4.1]` — we keep the *thresholds* (0.18 recall floor, 0.70 drop, <30%
  re-retrieve) but run ONE local rerank, not the ladder. The voting ensemble triples
  cost for a guarantee the §2 byte-identity + local NLI already provide.
- **Grader loop with cap=20** — capped at 3 because we patch, not regenerate (§4.1).
- **Raw confidence scores in prose** — number stays off-band (§7).

The discipline: a pattern earns a slot only if it is (a) keyless AND (b) buys
quality-per-cost the cheaper layers don't already buy. The five NET-NEW items pass
both tests; this list fails the second.

---

## 9. The complete keyless pipeline, with every stage's source mechanism

```
ROUTE ──── skills/router.py classify_route()  ........... [05 §9.2]  HAVE
  │
  ├─ agentic-fast ── bad-research-agentic-fast (ReAct ≤10 steps) .. [PPLX §R3.2]  HAVE
  │      writer-split (sees ranked chunks, not CoT) ............... [PPLX §R3.8]  HAVE
  │      → 15 polish → 16 gate
  │
  ├─ light ── 0.5 clarify → 1 decompose → 1.5 route → 2 funnel
  │      → 10 single draft → 15 polish → 16 gate(+uncited) ........ HAVE
  │
  └─ full ── 0.5 clarify(default-proceed) ........................ [ODR §5]  HAVE
         1 decompose → 1.5 route
         2 width-sweep: 10-12 fetchers in ONE Task message ....... [CLR §CE.2]  HAVE
              ★ add 4-field delegation contract ................. [CLR §CE.2]  NET-NEW §3.1
              ★ add per-subagent caps (300s/cap/100-src) ........ [CLR §CE.5]  NET-NEW §3.2
              forward-binding: char_start/end + quote_sha ........ [ODR §9]    HAVE §2
         3 contradiction-graph + consensus-claims ............... [08 §3]     HAVE
         4 loci → 5 depth → 6 reconcile → 7 source-tensions ...... HAVE
         8 corpus-critic ("what would overturn this?") .......... [08 §3]     HAVE
         9 evidence-digest (writer's ground truth) .............. [PPLX §R3.8] HAVE
         10 triple-draft → 11 synthesize ([Read,Write]-lock) .... HAVE §2
         11.5 CitationVerifier: A byte-id → B local NLI → C judge  [CLR §8]    HAVE §2
              ★ emit confidence_band per claim .................. [GDR §879]  NET-NEW §7
         12 critics ×4 → 13 gap-fetch ........................... HAVE
         ★ 12.5 GRADER LOOP: judge → patch → re-judge (≤3) ...... [CLR §13]   NET-NEW §4
         14 patcher ............................................. HAVE
              ★ patcher adds hedges to medium/low bands ......... [GDR §879]  NET-NEW §7
         14.5 fresh-review (single pass, [Read]-lock) ........... [CLR]       HAVE
         15 polish (negative net-char-delta) .................... HAVE
         16 readability + ★ recitation overlap gate ............ [GDR §R3.9]  NET-NEW §5
              + no-uncited-claim gate (hard ship-block, $0) ..... [08 §5]     HAVE

CROSS-CUTTING (all routes, all keyless):
  untrusted-content preamble on every page-touching prompt ...... [07 §2.4]  HAVE
  SEO-farm score / domain-tier / blocklist (prefilter.py) ....... [07 §1]    HAVE
  shingle-Jaccard 0.60 dedup (similarity.py) .................... [07 §3]    HAVE
  0.18 recall floor / 0.70 drop / <30% re-retrieve .............. [07 §4]    HAVE
  ★ --effort continuum (minimal/low/medium/high) ................ [ODR §R2.11] NET-NEW §6.1
  ★ --max-tokens ceiling + Claude degrade-order ................. [CLR §12]   NET-NEW §6.2
```

---

## 10. The NET-NEW ledger — five keyless additions, ranked by leverage

| # | Addition | Frontier source | Keyless because | Lands in | Effort |
|---|---|---|---|---|---|
| 1 | **In-pipeline grader LOOP** (judge→patch→re-judge ≤3) | Claude `define_outcome` 5-axis `[CLR §13]` | single LLM call + a host loop counter; the judge already exists offline | new `bad-research-12.5-grader` (full only; 11.6 is taken by the synthesizer spawn); `quality/grader.py` wrapping `LLMJudge` to emit patcher-shaped findings | M |
| 2 | **4-field delegation contract** + runtime caps | Claude `[CLR §CE.2,§CE.5]` | a prompt schema + an orchestrator-side per-wave deadline | entry-skill spawn contract + every step skill's spawn template + `routing_constants.py` caps | S |
| 3 | **RECITATION-equivalent overlap gate** | Gemini RECITATION `[GDR §R3.9]` | word-level contiguous-run match, deterministic, $0 | new `quality/recitation.py` in Stage 16 | S |
| 4 | **reasoning_effort continuum + token ceiling** | OpenAI `[ODR §R2.11]` + Claude law `[CLR §12]` | a tier→model/fan-out config + a host token counter | **wire the stub `--reasoning-effort`** (`research.py:118`) + add `--max-tokens`; router config; entry-skill degrade-order invariant | M |
| 5 | **confidence-band hedging** | Gemini confidenceScores `[GDR §879]` | a deterministic band + a patcher prompt rule | `verifier.py` emits `confidence_band`; `bad-research-14-patcher` hedges | S |

**The one-line takeaway:** the keyless deep-research loop, the anti-bullshit gates,
and the no-hallucination grounding contract are ~80% shipped — the cheap
deterministic layers (binding, dedup, prefilter, uncited gate) and the cheap LLM
layers (clarifier, router, agentic-fast, citation-verifier, fresh-review) are all
built and keyless. The five residual levers are themselves all keyless: a host-run
**grader loop** (we built the judge but never let it gate a run — #1, the highest
leverage), a **delegation contract + caps** that stop runaway fetchers (#2), a
**verbatim-overlap gate** that delivers RECITATION's output guarantee without its
decoder (#3), an **effort continuum + token ceiling** that turns the binary tier
into OpenAI's 4-level dial (#4), and **confidence-band hedging** that turns the
already-computed `verify_score` into a hedge word (#5). None requires a key; all
are stage-prompt edits, frozen constants, or deterministic Python the host runs.

---

## 11. Honest gaps in this analysis

- **The grader-loop's findings-extraction prompt (§4.1) is an IDEA reconstruction.**
  Claude's `define_outcome` rubric is KNOWN; the *findings-array* extension that makes
  it patcher-compatible is our design. It should be calibrated against the offline
  judge's existing rationales before committing the `<0.8` finding threshold.
- **The recitation thresholds (§5) are starting points.** `RECITATION_MAX_NGRAM=12`
  and `MAX_OVERLAP=0.50` are IDEA defaults; Gemini's actual threshold is undisclosed
  `[GDR §19]`. Tune on real reports — too strict false-flags a correctly-attributed
  block quote; too loose misses paraphrase-by-find-replace copying.
- **The per-subagent tool-call cap (§3.2) is a soft prompt guard, not a hard kill.**
  The host can deadline a *wave* but cannot interrupt a single in-flight subagent's
  tool loop. This is a genuine limitation of the keyless model vs. Claude's
  runtime-enforced caps — we approximate with `stop_conditions` text + wave deadlines.
- **The effort→model mapping (§6.1) assumes the host's `triage/light/heavy` LLM tiers
  map cleanly to minimal/low/medium/high.** The exact model per tier is a config
  detail, not a frontier-derived constant.
- **Dossiers 05/07/08 now contain stale `IDEA` labels** for things since shipped
  (clarifier, router, agentic-fast, citation-verifier, gate, prefilters). This file
  supersedes their *status* (not their *analysis*) — read 05/07/08 for the frontier
  evidence, read this for what's built vs. net-new.

*End of dossier. Cross-refs: `05_DR_LOOPS.md` (loop comparison), `07_QUALITY_FILTER.md`
(filter constants), `08_GROUNDING.md` (binding/verifier spec); code under
`src/bad_research/{skills,grounding,quality,funnel,calibrate}/`. Next: implement the
five NET-NEW levers — start with #1 (grader loop) and #2 (delegation contract), the
highest-leverage and lowest-effort respectively.*
