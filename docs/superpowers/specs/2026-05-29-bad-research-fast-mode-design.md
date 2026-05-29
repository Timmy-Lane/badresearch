# Design Spec — bad-research two-mode consolidation: **Fast** (Perplexity-style) + **Full**

**Date:** 2026-05-29
**Status:** Approved design (awaiting spec review → implementation plan).
**Goal:** Collapse the current three routes (`agentic-fast` / `light` / `full`) into **two operator-facing
modes** — a fast, Perplexity-Deep-Research-style mode that beats Perplexity by stacking the best
keyless patterns from Gemini / OpenAI / Claude / Grok DR, and the existing **Full** deep pipeline,
unchanged. Philosophy (inherited from the super-skill upgrade): **deep core, simple surface. No
rewrite — consolidation + two targeted new builds.**

Companion doc: `2026-05-29-bad-research-fast-mode-RE-gaps.md` — the per-source reverse-engineering
task list (what we still need to capture from Perplexity / Gemini / Claude / Grok / OpenAI DR).

---

## 1. Premise (verified against source)

The 2026-05-29 super-skill upgrade already shipped most of the patterns a fast mode needs. Verified
present in `skills/router.py` + `skills/routing_constants.py`:

- A bounded planner→writer ReAct loop with hard step/call/time caps (`bad-research-agentic-fast.md`,
  `AGENTIC_FAST_MAX_STEPS/CALLS/TIMEOUT_S`) — this **is** Perplexity DR's architecture.
- Parallel query fan-out per step + batched fetch via `bad funnel-gather`.
- A query-**shape** classifier orthogonal to the cost tier (`classify_query_shape` →
  `straightforward` / `breadth_first` / `depth_first`; `SHAPE_FANOUT`).
- Parallel sub-agent fan-out machinery (`SUBAGENT_FANOUT_*`, the `bad-research-fetcher` subagent).
- The OpenAI effort dial (`EFFORT_MAP`), Gemini editable plan-gate (`plan_gate_fires`, step 1.6),
  and Perplexity synthesis-budget reservation (`RESERVE_FOR_SYNTHESIS`, `should_short_circuit`).
- The Perplexity writer contract (per-sentence single-index `[N]`, no `## References`, tables not
  lists) in the agentic-fast writer split.

**Therefore the work is consolidation + two new builds**, not a rebuild:
1. Merge `agentic-fast` + `light` → one **Fast** route, preserving their distinction as an *internal*
   shape/effort knob.
2. **New build #1:** wire the breadth sub-researcher fan-out into the Fast loop.
3. **New build #2:** a slim **citation-grounding pass** for Fast (today only Full grounds claims).

Every change is keyless and Claude-Code-native. Full is untouched.

---

## 2. Mode consolidation (3 routes → 2)

`router.py`:
- `Route = Literal["fast", "full"]` (was `["agentic-fast", "light", "full"]`).
- `classify_route`: the old `agentic-fast` band and `light` band both return `"fast"`. The `full`
  branch (semantic-depth floor, time_periods, argumentative, contradiction, multi-domain,
  breadth-forces-full) is **unchanged**.
- `route_reason`: two-branch rationale (`fast: …` / `full: …`).
- `effort_overrides` / `EFFORT_MAP`: `minimal`→`fast` (ultra-short), `low`→`fast` (richer),
  `medium`/`high`→`full` (today they point at `light`/`full`).

The lost third bucket is **not** lost capability — it becomes the internal Fast scaling:
`query_shape` + effort decide loop depth and whether breadth fan-out fires (see §3).

---

## 3. Mode A — **Fast**: the hybrid bounded loop

One skill: rewrite `bad-research-agentic-fast.md` → `bad-research-fast.md`. Perplexity bounded
planner→writer loop is the spine; a breadth branch adds Claude-style parallel sub-researchers.

**Pipeline (Fast route):**
```
0.5 clarify (cheap, ≤3 Q, default-proceed)
  → 1 decompose  (also emits a one-paragraph SCOPE BRIEF — OpenAI instruction-builder pattern)
  → 1.5 query-router  (route=fast; query_shape=straightforward|breadth|depth)
  → bad-research-fast:
       bounded ReAct loop, cap scaled by shape + effort:
         straightforward → single loop, ~2-3 steps
         depth_first     → single loop, ~4-6 steps, reflect-then-narrow
         breadth_first   → lead spawns K=min(n_subq, 3) parallel bad-research-fetcher
                           sub-researchers (one per sub-question), then gathers
         each step: planner emits ≤3-4 parallel queries (bad funnel-gather)
                    observe = bad retrieve rerank vs the ORIGINAL query
                    reflect / stop  (model-judged AND hard cap)
       writer (1 pass): Perplexity contract — per-sentence [N] (one index/bracket),
                        NO ## References, tables not lists, direct-answer-first, length by format
  → citation-grounding pass (NEW for fast — §5)
  → 12 slim adversarial critic (existing E3 — one dialectic+instruction pass, applied inline)
  → 15 polish
  → 16 readability + uncited-gate (ship-block, all routes)
```

**The stop rule (XSTOP-1, now CLOSED — keyless & evidence-anchored).** The 2026-05-30 RE batch
(`researchfms/teardowns/DEEP_RESEARCH_FAST_MODE_RE.md`) mined five open-source DR clones and
synthesized one auditable keyless stop rule. The Fast loop stops at step `t` when **ANY** of:
1. **Hard cap** — `t >= FAST_MAX_STEPS`.
2. **Coverage complete** — every sub-question has `>= FAST_MIN_SOURCES_PER_SUBQ` distinct supporting
   domains (the per-sub-question checklist is all-green).
3. **Diminishing returns** — this step added `< FAST_MIN_NEW_DOMAINS` *new distinct domains* AND
   `< FAST_MIN_NEW_DOMAINS` new distinct URLs, for `FAST_STALL_PATIENCE` consecutive steps. The
   new-distinct-domains delta is computed from the URL list with **zero model calls** — the
   measurable, auditable form of open_deep_research's "your last 2 searches returned similar
   information."
4. **Model-declared done** — the planner emits a `research_complete` flag (the keyless analogue of
   open_deep_research's `ResearchComplete` tool). Additive early-out; clauses 1-3 guarantee
   termination even if the model never emits it.

After stopping, reserve `FAST_RESERVE_SYNTH_FRAC` of the budget for the writer (never spend it all on
retrieval). The verbatim planner reflect/stop prompt that emits this decision as one JSON object lives
in the RE synthesis PART 2.3 and is lifted into the Fast skill (plan Task 10).

**Evidence-anchored constants (`routing_constants.py`)** — each value cited to a cloned repo in the
RE synthesis PART 2.2; finalized in the plan:
- `FAST_MAX_STEPS = 6`, `FAST_MAX_QUERIES_PER_STEP = 4`, `FAST_MAX_RESULTS_PER_QUERY = 5`,
  `FAST_MIN_NEW_DOMAINS = 2`, `FAST_STALL_PATIENCE = 1`, `FAST_MIN_SOURCES_PER_SUBQ = 3`,
  `FAST_MAX_SUBQUESTIONS = 3`, `FAST_CONTENT_TRIM_CHARS = 25000`, `FAST_TEMPERATURE = 0.4`,
  `FAST_RESERVE_SYNTH_FRAC = 0.25`, `FAST_SUBRESEARCHER_K = 3`, plus a wall-clock safety net
  `FAST_TIMEOUT_S = 600`.
- `EFFORT_MAP` route values `light`→`fast`.
- **Skipped as overkill** (the "no bullshit" rule): `FAST_CONFIDENCE_STOP` (needs a calibrated scorer
  we lack keyless — the domain-novelty proxy is the primary gate), periodic replanning (redundant
  with per-step reflect), and a separate `FAST_MAX_CALLS` (the step×queries budget already bounds
  calls). The PART-3 capture harness stays an RE-folder asset; it is **not** built into the skill.

**Funnel-mode axis stays `{"light","full"}`.** `FETCHER_TOOLCALL_CAP` keys are NOT renamed — `mode`
is an internal fan-out dial, not the route; route `fast` maps to funnel-`light`. (Recorded decision;
keeps the diff focused and every commit green.)

---

## 4. The pattern stack (provenance — all keyless)

| Pattern | Source | Status |
|---|---|---|
| Bounded planner→writer ReAct loop + hard step cap | Perplexity | have (agentic-fast) |
| Parallel query fan-out/step + batched fetch | Perplexity / all | have (funnel) |
| Cheap clarify + **scope-rewrite to brief** | OpenAI | partial — ADD rewrite to step 1 |
| Query-shape classifier (depth/breadth/straight) | Claude | have (`classify_query_shape`) |
| **Parallel sub-researcher fan-out on breadth** | Claude / Grok | NEW build #1 — wire into Fast |
| **Separate citation-grounding pass** | OpenAI / Claude | NEW build #2 — slim version for Fast |
| Source-quality as prompt heuristic, *not a tool* | Claude | verify present in fetcher/funnel prompts |
| Writer contract (per-sentence `[N]`, no refs, tables) | Perplexity | have |
| Reserve budget for synthesis / short-circuit | Perplexity | have (`RESERVE_FOR_SYNTHESIS`) |
| Leader-only synthesis (sub-researchers don't write) | Grok | applies to breadth branch |
| Editable plan-gate | Gemini | have (1.6) — Full-only; opt-in `--plan` for Fast |

---

## 5. New build #2 — slim citation-grounding pass for Fast

**Why:** today only Full binds every claim to a source (step 11.5 citation-verifier +
`bad uncited-gate`). Fast writes per-sentence `[N]` markers but does not *verify* each maps to real
retrieved support — the single biggest correctness lever OpenAI/Claude DR identify. Adding a slim
grounding pass is what makes Fast "better than Perplexity," not just "as fast."

**Design:** reuse step 11.5 machinery in a slim configuration (no triple-draft assumptions): after the
Fast writer produces the report, run a bounded grounding pass that resolves each `[N]` to its vault
note and span, then acts inline (Read+Edit, no step-14 patcher). Keyless: reuses `LineSpanJudge` /
`HostJudgeNLI` (built in the super-skill upgrade). No new model, no new key. The R5 deltas make this
concrete:
- **Why it's the key quality lever:** Anthropic's CitationAgent has *no* faithfulness check
  (`CLAUDE_RESEARCH.md` R5.2) — unsupported claims ship silently uncited; OpenAI's faithfulness is
  RL-internal and un-portable. A keyless replica MUST add this gate; it's the genuinely *additive*
  step, not redundancy.
- **Which sentences (OpenAI 3-tier, §R5.1C):** MUST verify load-bearing facts + anything volatile
  since cutoff (numbers/dates/prices/versions/"latest"); SHOULD verify other web-supportable
  statements; common knowledge + synthesis are EXEMPT (keeps the pass cheap).
- **Disposition thresholds (§R5.3):** ACCEPT ≥0.75 · TIGHTEN ≥0.55 · FLAG ≥0.35 · DROP-CITE <0.35 ·
  DROP-SENTENCE for a MUST-verify claim with no span. Placement lifts Claude `citations_agent.md`
  verbatim (one cite per source per sentence, after the period). The existing `bad uncited-gate`
  (step 16) is the forward ship-block downstream.

**RE status:** the placement/verification rules (OAI-2, CLR-2) are now **closed-by-source** — folded
in above.

---

## 6. New build #1 — breadth sub-researcher fan-out in Fast

**Why:** Perplexity's single loop is narrower than Claude Research's parallel decomposition on
breadth queries (independent sub-questions). For `query_shape == breadth_first`, Fast spawns
K=min(n_subq, `FAST_SUBRESEARCHER_K`) parallel `bad-research-fetcher` sub-researchers, one per
sub-question, each a bounded fetch loop (`FETCHER_TOOLCALL_CAP["fast"]`, `FETCHER_TIMEOUT_S`). The
**lead** (Fast orchestrator) is the only writer (Grok leader-only-render rule) — sub-researchers
return claims+sources, the lead synthesizes. Reuses the existing fetcher subagent and the
seven-piece subagent spawn contract from the entry skill; the only new wiring is the dispatch from
inside the Fast skill on the breadth shape.

---

## 7. Surgical change map

- `skills/router.py` — `Route` literal; `classify_route` (collapse two bands → `fast`);
  `route_reason`; `effort_overrides`.
- `skills/routing_constants.py` — `FAST_*` rename + new caps; `FAST_SUBRESEARCHER_K`;
  `FETCHER_TOOLCALL_CAP` keys; `EFFORT_MAP` routes.
- `skills/bad-research-agentic-fast.md` → `skills/bad-research-fast.md` — hybrid loop + breadth
  fan-out + scope-brief read + grounding-pass call.
- `skills/bad-research.md` (entry) — route table 3→2 rows; bootstrap todo seeding; recovery artifacts;
  per-route sequence text.
- `skills/bad-research-query-router.md` — 3-way → 2-way classification + next-step routing.
- `skills/bad-research-1-decompose.md` — emit the one-paragraph scope brief.
- CLI (`bad route` + wherever `--effort` is wired) — add `--fast` / `--full` override flags.
- Step 11.5 citation-verifier — add a slim/`fast` mode (or a thin `bad-research-fast-cite` wrapper).
- `tests/` + golden-eval corpus — route literals `agentic-fast|light` → `fast`; route-assertion
  fixtures; new tests for the collapse, the breadth fan-out, the slim grounding pass.

**Steps 2 (width-sweep) and 10 (triple-draft) become Full-only** — Fast's loop+writer fully replaces
the old `light` single-draft path (your decision).

---

## 8. What stays unchanged (Full)

The entire Full pipeline (0.5 → 1 → 1.5 → 1.6 → 2 → 4* → 5 → 6* → 8 → 10* → 11 → 11.5 → 12 → 13 →
12.5 → 14 → 14.5 → 15 → 16) is untouched. All Full invariants in the entry skill remain in force.

---

## 9. Out of scope / risks

- **No new models or keys.** Cross-model review remains infeasible keyless (unchanged from V8).
- **Risk: route-name churn breaks the golden eval.** The corpus asserts route strings; updating
  fixtures is mechanical but must be complete (CI gate). Mitigate by a single rename commit + green
  suite before any behavior change.
- **Risk: breadth fan-out inflates Fast latency.** Mitigated by the hard `FAST_TIMEOUT_S` per-wave
  deadline + `FAST_SUBRESEARCHER_K ≤ 3`; sub-researchers run concurrently.
- **Risk: slim grounding pass stalls** (the G5 regrounding-loop failure mode). Mitigated by reusing
  the super-skill's forward-binding fix — the writer emits anchored citations, so the gate sees an
  already-grounded draft.

---

## 10. RE status (the gaps are now answered — 2026-05-30 batch)

The RE handoff's gaps were reverse-engineered and committed to `researchfms`
(`teardowns/DEEP_RESEARCH_FAST_MODE_RE.md` + R5 deltas on all five DR teardowns). Status:

- **XSTOP-1 (the P0) — CLOSED-by-source.** The keyless 4-clause stop rule above is synthesized from
  five open-source DR clones (open_deep_research, gpt-researcher, dzhng, smolagents,
  local-deep-research), each constant cited. The two un-closeable commercial behaviors (OpenAI &
  Anthropic RL/server-side stop judgement — OAI-1, CLR-2) are **substituted** by this explicit
  auditable policy, not chased.
- **PPX-1, OAI-2, OAI-3, CLR-1, CLR-3, GRK-1/2 — CLOSED-by-source.** Notably CLR-3 settled: the lead
  sets only `prompt` on a sub-researcher (no model/tools/cap) — confirms our prompt-level
  `stop_conditions` breadth-fan-out contract. OAI-2 gives the citation-placement discipline for the
  slim grounding pass.
- **PPX-4 — DEBUNKED.** The "T5-XXL 3-5 phrasings / entropy-cutoff 0.85" claims trace to a 3rd-party
  speculation repo; **do not carry them into the replica** (they never were in our design).
- **NEEDS-LIVE-CAPTURE (non-blocking):** PPX-2/3, GEM-1(c)/2/3 — these are *calibration* of the
  numeric thresholds (e.g. fitting `FAST_MIN_NEW_DOMAINS` to real per-step domain-novelty curves)
  via the shipped capture harness. The replica runs correctly on the DESIGNED defaults today; the
  harness is an RE-folder tuning tool, not a build dependency.

**Net effect on this design:** the Fast loop's stop logic moves from "model-judged (RE-dependent)" to
the concrete, evidence-anchored, keyless rule in §3 — no remaining blockers.
