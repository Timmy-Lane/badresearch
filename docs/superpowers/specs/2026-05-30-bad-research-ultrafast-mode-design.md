# Design Spec — bad-research third route: **Ultrafast** (commercial-DR-grade middle tier)

**Date:** 2026-05-30
**Status:** Approved design (awaiting spec review → implementation plan).
**Goal:** Add a **third operator-facing mode**, `ultrafast`, between the existing `fast` (≤10 min,
shallow single-loop) and `full` (30–60+ min, adversarial) routes. Ultrafast is the keyless replica of
the "Deep Research" button in Perplexity / Gemini / Grok / OpenAI / Claude DR: a **plan → wide parallel
multi-source browse → long sectioned cited report** experience that lands in **5–15 minutes**, with
**zero API keys** and **zero pauses** (fully autonomous). It stacks the best keyless pattern from each
commercial tool onto the plumbing the `fast`/`full` routes already ship.

Philosophy (inherited from [[super-skill-upgrade]] and [[project-fast-mode]]): **deep core, simple
surface. No rewrite — one new orchestration skill that wires existing keyless parts at a middle budget.**

---

## 1. Premise (verified against source)

The `fast`-mode consolidation (2026-05-30, PR #3) already shipped almost every keyless primitive a
commercial-DR middle tier needs. Verified present in `src/bad_research/skills/`:

- A **route override seam** in the `route` CLI command: `bad route --apply --fast|--full` forces a
  route, bypassing `classify_route` ([research.py:57-62](../../../src/bad_research/cli/research.py)).
- **Parallel sub-researcher fan-out**: the `bad-research-fetcher` subagent + the `breadth_first` branch
  of `bad-research-fast.md` already spawn `K=min(n_subq, FAST_SUBRESEARCHER_K=3)` parallel fetchers,
  each a bounded browse loop, with the seven-piece subagent spawn contract.
- The **XSTOP-1 4-clause auditable stop rule** (hard cap / coverage-checklist ≥N domains per sub-q /
  new-distinct-domains novelty proxy / model-declared `research_complete`) — keyless, loop-counter-based.
- **Leader-only terminal synthesis** (Grok seam): in `fast`, sub-researchers return claims+sources,
  never prose; the lead is the only writer; no fan-out after writing starts.
- The **slim citation-grounding pass** (`bad verify-citations`, the `bad-research-11.5-citation-verifier`
  **Slim mode** section) applied inline via Edit, no patcher.
- The **light-tier slim critic** (one dialectic+instruction pass, `bad-research-12-critics` Light-tier
  section) applied inline, no fan-out.
- **Polish** (`bad-research-15-polish`) and the deterministic **uncited ship-gate** (`bad uncited-gate`,
  step 16) run on every route.

**Therefore the work is one new skill + constants + flag plumbing**, not a rebuild:
1. A new `bad-research-ultrafast.md` orchestration skill: plan → K parallel researchers → leader
   synthesis → slim grounding → slim critic → polish → gate, at middle-tier caps.
2. A `--ultrafast` flag + natural-language "ultrafast mode" trigger that forces `route="ultrafast"`.
3. An `ULTRAFAST_*` constants block (wider caps than `FAST_*`, a 15-min wall-clock net).

Every change is keyless and Claude-Code-native. `fast` and `full` are untouched; `classify_route`
never auto-emits `ultrafast`, so the golden eval corpus and route tests do not move.

---

## 2. Positioning (three operator modes)

| | `fast` | **`ultrafast` (new)** | `full` |
|---|---|---|---|
| Wall-clock | ≤10 min | **5–15 min** | 30–60+ min |
| Browse | 1 serial planner loop, ≤6 steps | **K≤6 parallel researcher subagents** | width-sweep funnel + loci/depth investigators |
| Sub-questions | 3 | **up to 8** | unbounded |
| Sources / sub-q | 3 distinct domains | **≥4 distinct domains** | exhaustive |
| Synthesis | orchestrator, 1 pass, 500–2000w | **orchestrator, 1 pass, sectioned 1500–4000w** | 3-draft ensemble → synthesizer subagent |
| Adversarial | 1 slim critic | **1 slim critic** | 5-critic fan-out + grader loop + fresh-review |
| Grounding | slim `verify-citations` (inline) | **slim `verify-citations` (inline)** | backward citation-verifier + patcher |
| Clarifier / plan-gate | 0.5 runs; 1.6 skipped | **both skipped (autonomous)** | 0.5 + 1.6 (interactive) |
| Selection | auto / `--fast` | **`--ultrafast` / "ultrafast mode"** | auto / `--full` |

Ultrafast's distinct value over `fast` is three-fold and structural: **parallel multi-researcher
browse** (what a single serial loop cannot do), **wider coverage** (8 sub-questions × 4–5 domains vs
3 × 3), and a **long sectioned report**. Its distinct value under `full` is the absence of the
adversarial apparatus (no contradiction graph, loci, depth investigation, triple-draft, 5 critics,
grader loop, fresh-review) — that machinery is what makes `full` slow, and ultrafast omits all of it.

---

## 3. Selection — explicit only, autonomous

**Route name** `ultrafast`; **flag** `--ultrafast`; **skill** `bad-research-ultrafast`.

- `classify_route` is **unchanged** — it still only auto-emits `fast`/`full`. Ultrafast is never
  auto-selected.
- The route is forced two ways, both resolved during bootstrap by the entry skill:
  1. **`--ultrafast` CLI flag** → the orchestrator runs `bad route --apply --ultrafast`, which sets
     `route="ultrafast"` in `research/prompt-decomposition.json` (mutually exclusive with
     `--fast`/`--full`).
  2. **Natural-language request** — the user prompt explicitly asks for "ultrafast mode" / "use
     ultrafast" / "ultra fast research". The orchestrator recognizes this binding intent during
     bootstrap and applies the same `--ultrafast` override. The CLI flag is the canonical signal; the
     NL phrase is a convenience the Opus orchestrator honors. Detection is conservative — only an
     explicit "ultrafast" mention triggers it, never an inferred "make it fast."
- **Autonomous** → ultrafast skips **both** step 0.5 (clarifier) and step 1.6 (plan-gate), exactly as
  an `--auto` run does. It plans internally and runs start-to-finish with no human round-trip — the
  Perplexity / Grok DeepSearch experience. This protects the 5–15 min wall-clock and keeps `-p` /
  scripted runs working.

---

## 4. The pipeline — best-feature steal-list mapped to each stage

**Route sequence:**
```
1 decompose  (cap ULTRAFAST_MAX_SUBQUESTIONS = 8 sub-questions; emits the scope brief)
  → 1.5 query-router  (route=ultrafast via --ultrafast override; query_shape still emitted)
  → bad-research-ultrafast:
       PLAN:    internal, no gate — the decomposition's sub-questions ARE the report sections,
                importance-ordered (Claude breadth-first ordering).
       BROWSE:  spawn K = min(n_subq, ULTRAFAST_SUBRESEARCHER_K = 6) parallel bad-research-fetcher
                sub-researchers, ONE per sub-question. Each runs a bounded agentic browse loop
                (FETCHER_TOOLCALL_CAP["ultrafast"] = 15 calls, ULTRAFAST_FETCHER_TIMEOUT_S = 360s),
                chasing 3–8 primary sources via citation chains, returning claims+sources JSON
                (never prose). Seven-piece spawn contract. Per-wave deadline = the fetcher timeout;
                the lead proceeds with returned results when a wave exceeds it.
                Coverage gate: a sub-question is GREEN at ULTRAFAST_MIN_SOURCES_PER_SUBQ = 4 distinct
                domains. One optional gap-fill wave targets sub-questions still below the gate.
       SYNTH:   leader-only (Grok terminal seam). The orchestrator dedups gathered evidence, reserves
                ULTRAFAST_RESERVE_SYNTH_FRAC = 0.30 of budget, and writes ONE sectioned report inline
                — one section per sub-question, tables-first, per-sentence single-index [N] citations.
                No fan-out after writing starts. 1500–4000 words, scaling with breadth.
  → slim citation-grounding  (bad-research-11.5-citation-verifier Slim mode: verify-citations inline)
  → slim critic              (bad-research-12-critics Light-tier: one dialectic+instruction pass inline)
  → 15 polish
  → 16 uncited-gate (+ readability audit)
```

| Stage | Pattern stolen from | Reuses |
|---|---|---|
| 1. Plan (internal, no gate) | **Gemini** DR plan, run autonomously | step 1 `decompose` |
| 2. Wide parallel browse | **Claude** lead + parallel subagents, importance-ordered | K≤6 `bad-research-fetcher` |
| ↳ each researcher | **Perplexity/OpenAI** agentic browse + coverage stop + reserve-for-synthesis | `funnel-gather`/`retrieve`, XSTOP stop rule, citation-chasing |
| 3. Leader-only synthesis | **Grok** terminal seam + **Gemini/OpenAI** long sectioned report | orchestrator writes inline |
| 4. Slim grounding | — | step 11.5 slim `verify-citations` |
| 5. One slim critic | — | step 12 light critic |
| 6. Polish + ship-gate | — | step 15 + step 16 `uncited-gate` |

**Writer contract** (identical discipline to `fast`): per-sentence single-index `[N]` citations (each
index its own bracket, `[1][2]` never `[1,2]`, ≤3 per sentence); no `## References` section (the host
resolves `[N]` to the vault note out-of-band); ≤25 words verbatim per source, ≤1 quote per source
(Claude copyright cap); partial-answer-better-than-none if a wave stalled (flag the thin sections);
agentic-effort realism (hours-to-days, never weeks/months; no calendar estimates unless asked).

---

## 5. New constants (`ULTRAFAST_*` in `routing_constants.py`)

```python
# ---- Ultrafast-route constants (keyless commercial-DR middle tier) ----
# Sits between FAST_* and the full-tier caps. Parallel fetchers ⇒ wall-clock ≈ one
# wave (~5–6 min) + synthesis/grounding (~4–6 min) = the 5–15 min target.
ULTRAFAST_MAX_SUBQUESTIONS     = 8     # report sections / parallel researcher streams (fast=3)
ULTRAFAST_SUBRESEARCHER_K      = 6     # parallel bad-research-fetcher cap (fast=3)
ULTRAFAST_MIN_SOURCES_PER_SUBQ = 4     # distinct domains to mark a sub-question green (fast=3)
ULTRAFAST_FETCHER_TIMEOUT_S    = 360   # per-researcher soft deadline (fetcher default=300)
ULTRAFAST_RESERVE_SYNTH_FRAC   = 0.30  # budget reserved for the longer synthesis (fast=0.25)
ULTRAFAST_TIMEOUT_S            = 900   # wall-clock safety net (15 min; fast=600)
# FETCHER_TOOLCALL_CAP gains an "ultrafast" key:
FETCHER_TOOLCALL_CAP = {"light": 10, "ultrafast": 15, "full": 20}
```

Values are evidence-aligned ballparks (between the `fast` clone-anchored values and the `full`
caps) and are tunable without touching control flow.

---

## 6. Code / plumbing touchpoints

| File | Change |
|---|---|
| `src/bad_research/skills/router.py` | `Route = Literal["fast", "full", "ultrafast"]`. `classify_route` **unchanged** (never returns ultrafast). |
| `src/bad_research/cli/research.py` (`route_cmd`) | Add `--ultrafast` option; `if ultrafast: route = "ultrafast"`; make `--fast`/`--full`/`--ultrafast` three-way mutually exclusive. |
| `src/bad_research/cli/research.py` (`run`) | Add `--ultrafast` flag; thread to the route step exactly as `--fast`/`--full` are threaded today. |
| `src/bad_research/skills/routing_constants.py` | Add the `ULTRAFAST_*` block + the `"ultrafast"` key in `FETCHER_TOOLCALL_CAP`. |
| `src/bad_research/skills/bad-research.md` | Add an `ultrafast` row to the route table; bootstrap detects `--ultrafast`/NL-intent; skip 0.5 + 1.6; seed the ultrafast todo sequence. |
| `src/bad_research/skills/bad-research-ultrafast.md` | **New** orchestration skill (the §4 pipeline). `user-invocable: false`. |
| `src/bad_research/skills/bad-research-query-router.md` | Pass `--ultrafast` through to `bad route --apply` when the override is set. |
| `tests/` | `route_cmd --ultrafast` → `route=ultrafast`; three-way mutual-exclusivity error; `ULTRAFAST_*` sanity; **golden-corpus regression guard** (asserting `classify_route` output is unchanged for every fixture). |

The `bad install` skill installer globs `src/bad_research/skills/*.md`, so the new skill ships
automatically once the file exists (verify during implementation).

---

## 7. Decisions locked during brainstorming

1. **Positioning** = new middle tier (not a scaled-up `fast`, not a replacement). [user]
2. **Selection** = explicit only: `--ultrafast` flag or NL "ultrafast mode". No auto-routing. [user]
3. **Interactivity** = always autonomous; skips 0.5 clarifier **and** 1.6 plan-gate. [user, extended]
4. **Architecture** = Approach A (lead + parallel researchers), over scaled-loop (B) and stripped-full
   (C). [recommended, approved]
5. **Report** = 1500–4000w, one section per sub-question, tables-first, inline `[N]`. [default, approved]
6. **Keep the one slim critic** (cheap, reuses fast's). [default, approved]
7. **Synthesis = orchestrator writes inline** (literally leader-only), not a new synthesizer subagent.
   [default, approved]
8. **Constant values** ballpark, tunable. [default, approved]

---

## 8. Out of scope (YAGNI)

- Auto-routing ultrafast (the classifier never emits it — explicit only).
- An editable plan-gate for ultrafast (autonomous by decision #3).
- A dedicated synthesizer subagent / triple-draft for ultrafast (orchestrator writes once).
- Any change to `fast` or `full` behavior, to `classify_route`, or to the golden eval corpus.
- A new `--effort` level mapping to ultrafast (effort dial was declined in favor of the flag).

---

## 9. Success criteria

- `bad route --apply --ultrafast --decomposition <f>` writes `route: "ultrafast"`; `--ultrafast`
  with `--fast` or `--full` errors.
- A `--ultrafast` run produces `research/notes/final_report_<tag>.md` (1500–4000w, sectioned, every
  non-trivial sentence carrying a resolvable `[N]`) in 5–15 min wall-clock, with no clarifier or
  plan-gate pause.
- The browse stage spawns ≥2 parallel `bad-research-fetcher` subagents on a multi-sub-question query.
- `bad uncited-gate` passes on the shipped report.
- Full test suite green; `classify_route` output byte-identical for every golden fixture (no route
  regression).
