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

**Budget (your pick: ≤8-10 min, slightly richer than Perplexity):** main loop ≤6 steps, fan-out
≤3-4 queries/step, ≤3 parallel sub-researchers (concurrent — little wall-clock cost), cheap models on
filter/rerank, strong model on synthesis. `RESERVE_FOR_SYNTHESIS` already protects the writer budget;
`should_short_circuit` already handles the token-ceiling terminal case.

**Proposed constant changes (`routing_constants.py`)** — final values fixed in the plan:
- Rename `AGENTIC_FAST_*` → `FAST_*`. `FAST_MAX_STEPS = 6` (was 10), `FAST_MAX_CALLS = 14`,
  `FAST_TIMEOUT_S = 600` (was 300 — the 8-10 min budget).
- `FAST_SUBRESEARCHER_K = 3` (breadth branch).
- `FETCHER_TOOLCALL_CAP` keys `{"light","full"}` → `{"fast","full"}` (fast=10, full=20).
- `EFFORT_MAP` route values `light`→`fast`.

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
note and span, drops/flags uncited factual sentences, then the existing `bad uncited-gate` ship-gate
(step 16) blocks delivery on any survivor. Keyless: reuses `LineSpanJudge` / `HostJudgeNLI` (already
built in the super-skill upgrade). No new model, no new key.

**Open RE dependency:** exact citation placement/verification rules — see RE-gaps doc, item OAI-2 /
CLR-2.

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

## 10. Open questions → RE dependencies

The design is buildable today from what we already reverse-engineered, but four points would be
*calibrated better* with fresh captures. These are detailed, per-source, in
`2026-05-29-bad-research-fast-mode-RE-gaps.md`:

1. The loop's **early-stop / coverage heuristic** (every tool leaves it fuzzy) — P0.
2. Perplexity DR **planner** prompt (we have the writer, not the planner) — P1.
3. **Plan → query-batch** mapping + breadth→K mapping — P1.
4. **Citation placement / verification** rules for the slim grounding pass — P1.

None block starting implementation; they sharpen constants and prompts.
