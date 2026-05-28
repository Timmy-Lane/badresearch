# Design Spec — bad-research "Super Skill" Upgrade (A+B+C+D)

**Date:** 2026-05-29
**Status:** Approved scope (A+B+C+D+E1). E2 (cross-run meta-review) deferred.
**Goal:** Make `bad-research` (HYPERRESEARCH V8) measurably better than Perplexity DR, OpenAI DR,
Gemini DR, Grok DR, Claude/Anthropic DR, Nia Oracle, and HyperResearch — while keeping a simple,
one-command operator surface. Philosophy: **deep core, simple surface. No rewrite, no overkill —
surgical changes only.**

Research backing this spec lives in `docs/superpowers/research/` (SYNTHESIS.md + round1/2/3 files),
all cited to source.

---

## 1. Premise (verified against source, not planning docs)

V8 is already the only tool in the comparison set that combines parallel breadth+depth fan-out, a
contradiction graph → scored loci, a triple-draft ensemble, four non-overlapping critics, a
convergence-gated grader loop, a zero-context fresh reviewer, byte-identity citation verification,
and two deterministic ship-gates. Verified already-present (planning docs were stale): golden eval
corpus, categorical grader rails, keyless LLM reranker, 14-day content cache, reflections-only
context, 6-axis URL utility scorer, evidence-redundancy audit, Wikipedia-as-hub rule, period-pinned
primary-source preflight.

**Therefore the work is a focused upgrade set, not a rebuild.** Four workstreams below. Every change
is keyless and Claude-Code-native (no external API keys, no hosted cross-encoders, no new paid
models). Cross-model adversarial review is **infeasible keyless** and is replaced by an in-family
proxy (B③).

---

## 2. Workstream A — Line-anchored, support-checked citations (correctness)

**Why:** absorbs OpenAI DR's line-level grounding (`【ref†L42-L58】`) and Perplexity's per-sentence
citation discipline. Fixes a genuine correctness hole and two stall/false-positive bugs:
- **G4 bug** (`grounding/verifier.py:31-41`): on the keyless path `CitationPresentNLI.predict`
  returns `{"entailment": 1.0}` unconditionally — a paraphrased claim that drifts from its cited
  span is marked SUPPORTED.
- **G1** (`grounding/gate.py:96`): `split_sentences` can tokenize bold-span sub-fragments → phantom
  "factual sentences" → false ship-blocks.
- **G5**: grounding is checked POST-synthesis, so an unanchored draft hits the gate as a wall of
  critical findings → regrounding stall loop.

**Design (four layers):**

1. **Source-side line anchors.** Add `body_to_lines()` + `char_span_to_line_range()` to
   `grounding/extract.py`. Store a `body_lines TEXT` (JSON) column on `note_content`
   (`core/db.py`, SCHEMA_VERSION bump; populated in `core/note.py:write_note`, lazily backfilled on
   read for old notes). Add a keyless `note_find(note_id, pattern, context_lines)` MCP tool
   (`mcp/server.py`) — the analogue of OpenAI `web.find`: regex grep within a note body returning
   `(line_start, line_end, text, char_start, char_end)`. No LLM, ~$0.
2. **Citation token format.** Canonical anchor becomes `[[note-id:L42-L58]]` — a backward-compatible
   extension of the existing `[[wikilink]]` grammar (one regex extension in
   `grounding/render.py:extract_citations`). `ClaimAnchor` (`grounding/anchors.py`) gains nullable
   `line_start`/`line_end`; `anchor_id = quote_sha(quoted_support)` is **unchanged** (Tier-A
   byte-identity untouched).
3. **Synthesis-side emission.** `synthesis-evidence.md` (built at step 11.4b) gains `line_start`/
   `line_end` per chunk, converted from existing `char_start`/`char_end` via
   `char_span_to_line_range`. The synthesizer spawn instruction
   (`bad-research-11-synthesize.md:240-255`) requires the line-anchored token and says: *copy the
   line numbers from the evidence file; do not invent them.* This is the **G5 forward-binding fix** —
   the draft arrives at the gate already grounded; no regrounding pass is added.
4. **Verify-side support check.** Add `LineSpanJudge` to `grounding/verifier.py` (~30 lines),
   replacing `CitationPresentNLI` on the keyless path with the **same interface** (zero caller
   change). It reuses the existing `HostJudgeNLI` lexical pre-filter (near-verbatim → accept without
   a call; genuine paraphrase → batched Tier-C judge). The key change: Tier-B/C premise becomes the
   **specific cited lines** re-read from the note body, not the opaque stored `quoted_support`. The
   Tier-C judge prompt (`verifier.py:123-136`, "does the QUOTE support the CLAIM?") is unchanged — it
   now sees the exact span. Closes G4.
5. **Gate-side.** No structural change; add a 3-line rule: when `verify_score < PARTIAL_LOW`
   (span explicitly does not support the claim) promote to `critical` (blocks ship). Belt-and-
   suspenders: add `_BOLD_SPAN_ONLY` to `_is_formatting_line` to close the residual G1 path.

**Diff surface:** ~144 lines across `grounding/{extract,verifier,gate,render,anchors}.py`,
`core/{db,note}.py`, `retrieval/anchors.py`, `mcp/server.py` + prose edits to
`bad-research-11-synthesize.md` and `bad-research-11.5-citation-verifier.md`. `CitationPresentNLI`
stays as a last-resort fallback. Old bare `[[note-id]]` anchors stay valid (`line_start` NULL →
`LineSpanJudge` falls back to full `quoted_support`, i.e. today's behavior).

---

## 3. Workstream B — Verification edge (cheap, high-value adds)

**① Assumption-decomposition critic** (absorbs AI Co-Scientist deep-verification). The one
verification mode entirely absent today. Add a fifth parallel critic
(`bad-research-assumption-critic` / `bad-research-12-critics.md`) that takes the ~5 highest-stakes
causal/quantitative claims, decontextualizes each into sub-assumptions, and verifies each against the
corpus. Output `critic-findings-assumption.json` — the patcher (step 14) already globs
`critic-findings-*.json`, so **zero patcher integration code**. Parallel add → ~0 added wall-clock,
~$0.50.

**② Grader re-plan memory** (absorbs Magentic-One dual-ledger; reinforces the G5 fix). Today the
grader patch loop carries no failure history between rounds. Accumulate a `grader_history` block in
the findings JSON; on round ≥2 inject one escalation clause into the patcher spawn prompt ("round 1
tried X at sentence level and failed; escalate to Y"). Two artifacts, no new module.
(`bad-research-12.5-grader.md`)

**③ Prior-generation proxy for cross-model review** (keyless substitute for P14, which is
infeasible without a non-Anthropic key — no weight-level diversity inside one model family). Add one
sentence to the fresh-review spawn (`bad-research-fresh-review.md`): *write your own 3-sentence
answer to the research query BEFORE reading the report, then flag where the report diverges.*
Zero-cost approximation of independent-prior review.

**④ Two prompt-only retrieval gaps** (parity verified PARTIAL/GAP in round3-parity.md):
- **Query expansion / multi-phrasing** (Perplexity): one bullet in `bad-research-2-width-sweep.md`
  Step 2.1 — generate 3–5 synonym/paraphrase alternatives per sub-question before searching. (We
  already have programmatic lens expansion in `funnel/fanout.py`; this adds the human-paraphrase
  instruction.)
- **Strategic direction-switch** (Perplexity): a "search-line pivot rule" block in
  `bad-research-5-depth-investigation.md` (and/or width-sweep): when a search line shows no progress,
  explicitly state the pivot to a different hypothesis. (Loop auto-reformulates silently today; this
  makes the pivot a first-class agent instruction.)

**Diff surface:** prose-only except `grader_history` JSON plumbing. No new pipeline stage except the
5th critic (which is a parallel sibling of an existing fan-out).

---

## 4. Workstream C — Simplification (deep core, simple surface)

The four adversarial passes are **verified genuinely distinct** (corpus-critic = pre-draft "what
would overturn this"; 4→5-critic fan-out = non-overlapping failure classes; grader = quantified
convergence loop; fresh-review = sole zero-context reader) — none are cut. We cut only **mechanical
bookkeeping stages** by folding them into their sole consumers:

- **MERGE 3 → 4:** contradiction-graph (no subagent; pure claim-pairing bookkeeping) becomes
  "Step 4.0 preamble" inside `bad-research-4-loci-analysis.md`. All claim-pairing / fight-cluster /
  consensus logic preserved.
- **MERGE 7 → 6:** source-tensions orphan-scan becomes "Step 6.5" inside
  `bad-research-6-cross-locus-reconcile.md`; `comparisons.md` + `source-tensions.json` collapse to
  one richer `tensions.md`. Every tension still surfaced.
- **CUT 9 → 10:** evidence-digest built inline in step 10.0b (it's the pre-digested form of what
  10.0b re-injects anyway). **Reconciliation with A:** the `line_start`/`line_end` evidence fields
  (A-layer 3) are produced wherever this distilled-evidence layer is built — after the merge that is
  step 10.0b / the 11.4b injection. Keep `reflections.md` as the lighter recovery checkpoint.
- **SURFACE-SIMPLIFY grader round-1 (P3):** round-1 judge aggregates the existing
  `critic-findings-*.json` instead of a fresh full-corpus axis-scan; rounds 2–3 remain full scans.
  Cuts the 80%-of-runs round-1 cost from ~$3–5 to ~$0.50. Convergence loop + 0.70 axis floor +
  patch-not-regenerate discipline all preserved; fresh-review (14.5) is the backstop for critic
  blind-spots. Composes with B② (grader_history).

**Operator surface:** one command + one meaningful dial (`--effort`). Confirm `--interactive`
auto-defaults from CLI context (already does via `plan_gate_fires()`); merge the `--reasoning-effort`
alias into the single canonical `--effort`. No new flags.

**Net:** 21 → 17 full-tier stages (−4 `Skill()` calls), **zero adversarial capability lost**.
Preserved: parallel breadth+depth, contradiction handling, all adversarial verification, citation
verification, deterministic ship-gates.

---

## 5. Workstream D — Efficiency (surgical)

- **SIMPLE-WIN:** `calibrate/constants.py:23` `JUDGE_TIER "heavy" → "work"` — a 1-line change the
  code's own comment endorses ("Sonnet acceptable"). Saves ~$0.55/full run.
- **MEDIUM:** delegate step 1 (decompose, JSON extraction) to a work-tier (Sonnet) subagent instead
  of Opus-inline. After C's merges, run the former-step-7 orphan tension-scan (now step 6.5) as a
  Sonnet subagent too. Establishes the "orchestrator delegates structured extraction" pattern.
- **MINOR:** overlap step 8 (corpus-critic) with the evidence-digest work (former step 9, now in 10
  build) where the artifact dependency allows — ~2–3 wall-clock min on a 90-min run.
- **SKIP (overkill):** programmatic-tool-orchestration (no orchestrator-level code sandbox; funnel
  already does this for retrieval); adding a bi-encoder to the keyless default (BM25 + LLM rerank is
  correct at 30-candidate scale).

**Post-merge model-tier table** (the authoritative mapping the plan implements): triage=Haiku,
work=Sonnet for decompose / search-planning / merged-tension-scan / evidence-digest / calibration
judge; heavy=Opus for orchestration + synthesis + the critic/grader reasoning that needs frontier
judgment.

---

## 5b. Workstream E1 — Eval-harness semantic guard (regression net for A)

**Why:** the offline golden-eval harness exists and passes, but its keyless default judge
(`RubricJudge`) scores by **content-word overlap** (lexical) — it cannot catch a report that cites a
real source whose text **contradicts** the claim, or one that is **over-hedged but lexically
"complete."** Because workstream A introduces new semantic support-checking in the live path, we add
an offline regression fixture that guards that behavior from silently degrading later.

**Boundary vs A:** A is the *runtime* support check (every cited claim, every run). E1 is the
*offline regression net* that proves A's semantic behavior holds across future code changes.
Complementary, not duplicative.

**Design:**
- Add an `LLMJudge` routing path in `calibrate/` plus a `bad gate --llm` flag selecting it over the
  default `RubricJudge`. Reuses the existing categorical `JudgeRail` (`pass/borderline/fail`) — **no
  float scores** (preserves the E2-rails fix already in place).
- Add two adversarial golden fixtures marked `requires_llm: true` that the lexical judge passes but
  the LLM judge must FAIL: `09_cited_contradiction` (claim cites a real source whose text contradicts
  it) and `10_over_hedged_completeness` (technically complete, substantively evasive).
- `requires_llm: true` fixtures are **skipped on the default keyless lexical run** and exercised only
  under `--llm` (and in CI where a host model is available), so the default `bad gate` stays
  $0/lexical and fast.

**Diff surface:** `calibrate/` judge routing (small) + 2 JSON fixtures. No pipeline-stage change.

## 6. Non-goals / constraints

- **No rewrite.** No new pipeline architecture; no new stages except the parallel 5th critic.
- **Keyless only.** No external API keys, no hosted cross-encoder, no torch/model download, no
  non-Anthropic model. Cross-model review → in-family prior-generation proxy (B③).
- **E1 in scope** (eval-harness semantic guard, §5b). **E2 deferred:** cross-run meta-review
  (`vault-meta-review.json` + recurring-failure prompt injection) is a separate follow-up — best done
  after A–E1 land and several real runs exist to seed it. DSPy MIPROv2 prompt optimization stays out
  (needs ~50 fixtures + a differentiable signal we don't have).
- Backward compatibility: old vault notes and bare `[[note-id]]` citations keep working.

---

## 7. Risks & mitigations

- **Schema migration** (`body_lines` column): bump SCHEMA_VERSION; lazy backfill on read; existing
  notes function with `line_start` NULL. Test the migration on a copied vault.
- **Citation-token regex change** could mis-parse existing `[[wikilink|alias]]` forms: the colon-
  suffix is additive; add unit tests for old + new token forms (round2-citation §5 open items:
  coalescer must NOT merge same-note different-line tokens — assert by test).
- **Grader round-1 aggregation (C-P3)** could miss issues critics entirely skipped: fresh-review
  (14.5) is the explicit backstop; rounds 2–3 still full-scan.
- **5th critic** adds findings volume the patcher must triage: it already triages multi-critic JSON;
  cap assumption-critic to the top-5 claims to bound output.
- **Merges (C)** remove recovery checkpoints: keep `reflections.md` (for 9→10) and the loci/tensions
  JSON artifacts (for 3→4, 7→6) so disk-recovery is preserved.

---

## 8. Testing approach (TDD)

The repo is pytest-heavy (`tests/test_*`), with a golden-eval harness. Each workstream is gated by
tests written first:
- **A:** unit tests for `body_to_lines`/`char_span_to_line_range` (incl. CRLF, trailing newline,
  multi-line spans); `extract_citations` parses `[[n:L1-L5]]` + legacy `[[n]]` + `[[n|alias]]`;
  `LineSpanJudge` returns `unsupported` for a known paraphrase-drift fixture and `supported` for a
  verbatim one; gate promotes `verify_score < PARTIAL_LOW` to critical; migration test on a copied
  vault. Add a golden fixture: cited-but-contradicting claim must now FAIL.
- **B:** assumption-critic emits valid `critic-findings-assumption.json` consumed by the patcher;
  `grader_history` accumulates across rounds; skill-prose changes covered by the existing
  `tests/test_skills` structural checks.
- **C:** stage-graph/structural tests updated to expect 17 stages; assert merged stages still emit
  their artifacts (`tensions.md`, loci JSON, inline digest); `--reasoning-effort` alias removed.
- **D:** assert `JUDGE_TIER == "work"`; assert decompose/tension-scan dispatch at work tier.
- **E1:** `bad gate --llm` routes to `LLMJudge`; default `bad gate` stays lexical and skips
  `requires_llm` fixtures; the two adversarial fixtures (`09_cited_contradiction`,
  `10_over_hedged_completeness`) FAIL under `RubricJudge`'s lexical scoring (proving the gap) and
  PASS-as-correctly-failed under `LLMJudge`.
- **Regression gate:** full golden-eval report must stay pass_rate=1.0 (or improve) after each
  workstream.

---

## 9. Sequencing (for the implementation plan)

1. **A** first (correctness; self-contained in `grounding/` + synth skill; highest value).
2. **E1** immediately after A (its regression net — write the `LLMJudge` path + the two
   `requires_llm` fixtures so A's new semantic behavior is locked against regression).
3. **C** merges (structural; rebase A's evidence-field change onto the merged 9→10 location).
4. **B** verification adds (5th critic, grader_history, fresh-review proxy, 2 prompt gaps).
5. **D** efficiency (tier flip + delegations; cheap, do alongside/after).
6. Run golden-eval after each; keep pass_rate=1.0 (default lexical run); E1's `--llm` fixtures green
   in CI.

The shipped result: same one-command surface, a shorter (17-stage) pipeline, line-anchored
support-checked citations that beat every competitor's grounding, one more verification lens than
any of them, and lower per-run cost.
