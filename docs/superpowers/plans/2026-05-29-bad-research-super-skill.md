# bad-research Super-Skill Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **The task detail lives in four focused section files under `sections/` — execute them in the order given in §"Execution Order" below.**

**Goal:** Make `bad-research` (HYPERRESEARCH V8) verifiably better than every major deep-research product — line-anchored support-checked citations, one more verification lens than any competitor, a shorter pipeline, and lower per-run cost — without a rewrite and with the same one-command surface.

**Architecture:** Five surgical workstreams over the existing keyless, Claude-Code-native pipeline. A) line-anchored, support-checked citations in `grounding/`; B) verification-edge adds (5th critic, grader memory, fresh-review proxy, 2 prompt gaps); C) fold 3 mechanical bookkeeping stages into their consumers (21→17 stages, no adversarial loss); D) surgical efficiency; E1) an offline LLM-judge regression net guarding A. Everything is keyless (no external API keys, no hosted models).

**Tech Stack:** Python 3.11/3.12, pytest (TDD), SQLite (vault + anchors), Typer CLI, MCP server, Claude Code skills (markdown). Package managed by `uv` / `pyproject.toml`.

**Source spec:** `docs/superpowers/specs/2026-05-29-bad-research-super-skill-design.md`
**Research evidence:** `docs/superpowers/research/` (SYNTHESIS.md + round1/2/3 + round2 fragments)

---

## Section Files (task detail)

| Workstream | Section file | Tasks |
|---|---|---|
| A — Line-anchored citations | `sections/A-citations.md` | A-1 … A-9 |
| B — Verification edge | `sections/B-verification.md` | B-1 … B-5 |
| C — Simplification | `sections/C-simplify.md` | C-1 … C-6 |
| D — Efficiency + E1 — Eval guard | `sections/D-E1.md` | D-1 … D-4, E1-1 … E1-3 |

Each task in those files is fully fleshed: exact file paths, real test code, the implementation code, exact `pytest` commands with expected output, and a commit. No placeholders (scanned clean 2026-05-29).

---

## File Structure (created / modified)

**Workstream A** — `grounding/extract.py` (line helpers), `core/db.py` + `core/migrations.py` (`body_lines` column, SCHEMA_VERSION 9→10), `grounding/anchors.py` + `retrieval/anchors.py` (`line_start/line_end`), `grounding/render.py` (`[[id:L42-L58]]` token + `parse_line_anchor`), `grounding/verifier.py` (`LineSpanJudge`, line-span premise), `grounding/gate.py` (critical promotion + `_BOLD_SPAN_ONLY`), `mcp/server.py` (`note_find` tool), skills `bad-research-11-synthesize.md` + `bad-research-11.5-citation-verifier.md`.

**Workstream B** — `core/hooks.py` (5th critic agent constant + install + one-line `PATCHER_AGENT` update), skills `bad-research-12-critics.md`, `bad-research-12.5-grader.md`, `bad-research-fresh-review.md`, `bad-research-2-width-sweep.md`, `bad-research-5-depth-investigation.md`.

**Workstream C** — DELETE skills `bad-research-3-contradiction-graph.md`, `bad-research-7-source-tensions.md`, `bad-research-9-evidence-digest.md`; merge their content into `bad-research-4-loci-analysis.md` (Step 4.0), `bad-research-6-cross-locus-reconcile.md` (Step 6.5), `bad-research-10-triple-draft.md` (Step 10.0b Part 2); edit `bad-research-12.5-grader.md` (round-1 aggregate), `core/hooks.py` (roster), `cli/research.py` + `bad-research.md` (flag), `bad-research.md` (stage table/routes).

**Workstream D + E1** — `calibrate/constants.py` (`JUDGE_TIER`), skills `bad-research-1-decompose.md` + `bad-research-6-cross-locus-reconcile.md` (delegations), `calibrate/judge.py` is already done (LLMJudge exists), `cli` gate command (`--llm` flag), `calibrate/golden.py` (`requires_llm` parse + skip), 2 new golden fixtures.

---

## Authoritative Post-Merge Stage Map (17 full-tier stages)

```
0.5 clarify → 1 decompose → 1.5 router → 1.6 plan-gate → 2 width-sweep →
4*  loci-analysis        (Step 4.0 = contradiction-graph preamble; was 3+4) →
5   depth-investigation →
6*  cross-locus-reconcile(Step 6.5 = orphan tension scan; was 6+7) →
8   corpus-critic →
10* triple-draft         (Step 10.0b Part 2 = inline evidence digest; was 9+10) →
11  synthesize → 11.5 citation-verifier →
12  critics (now 5: dialectic/depth/width/instruction/ASSUMPTION) →
13  gap-fetch → 12.5 grader (round-1 aggregates critic findings) →
14  patcher → 14.5 fresh-review → 15 polish → 16 readability-audit
Removed skill files: bad-research-{3-contradiction-graph, 7-source-tensions, 9-evidence-digest}.md
```

---

## Execution Order

Ordered so each workstream builds on stable ground and shared-file edits don't churn:

1. **A (A-1 → A-8)** — correctness, self-contained in `grounding/` + synth skills. Highest value.
2. **E1 (E1-1 → E1-3)** — the offline regression net for A's new semantic behavior. Do right after A so A is locked.
3. **A-9** — the in-process runtime regression test for the cited-contradiction case. (Self-contained; references but does not require E1's offline fixture.)
4. **C (C-1 → C-6)** — structural merges. C-3 rebases A's `line_start/line_end` evidence change onto the merged step-10.0b location (note already embedded in C-3). Finish ALL `core/hooks.py` roster edits here before B touches `hooks.py`.
5. **B (B-1 → B-5)** — verification adds. B-3 (grader_history) composes on top of C-4 (grader round-1 aggregate) in the same `bad-research-12.5-grader.md`. B's `hooks.py` edits (critic constants) are disjoint from C's roster edits.
6. **D (D-1 → D-4)** — efficiency. D-3 delegates C's new Step 6.5 scan, so it runs after C-2.
7. **Regression gate after every workstream:** `pytest -q` green; `bad gate` golden-eval `pass_rate` stays 1.0 on the default lexical run; E1's `--llm` fixtures green in CI.

---

## Complete Task Index

**A — `sections/A-citations.md`**
- [ ] A-1 `body_to_lines` + `char_span_to_line_range` (`grounding/extract.py`)
- [ ] A-2 `body_lines` column + SCHEMA_VERSION 9→10 + lazy backfill (`core/db.py`, `core/migrations.py`)
- [ ] A-3 `line_start`/`line_end` on `ClaimAnchor` + both DDLs (`grounding/anchors.py`, `retrieval/anchors.py`)
- [ ] A-4 `[[id:L42-L58]]` token + `parse_line_anchor`; legacy/alias still parse (`grounding/render.py`)
- [ ] A-5 `LineSpanJudge` + line-span premise in `CitationVerifier.verify` (`grounding/verifier.py`) — closes G4
- [ ] A-6 promote `verify_score < PARTIAL_LOW` to critical + `_BOLD_SPAN_ONLY` (`grounding/gate.py`) — closes G1/G4 gate layer
- [ ] A-7 `note_find` MCP tool (`mcp/server.py`)
- [ ] A-8 skill prose: line-anchored evidence format + token instruction (synthesize, citation-verifier)
- [ ] A-9 in-process regression: cited-but-contradicting claim is caught

**E1 — `sections/D-E1.md`**
- [ ] E1-1 `LLMJudge` routing + `bad gate --llm` flag (LLMJudge already exists; add flag + skip logic)
- [ ] E1-2 two `requires_llm:true` fixtures `09_cited_contradiction`, `10_over_hedged_completeness`; default lexical run skips them
- [ ] E1-3 gap proof: `RubricJudge` lexical passes both; `LLMJudge` correctly fails both

**C — `sections/C-simplify.md`**
- [ ] C-1 MERGE 3→4 (contradiction-graph → loci Step 4.0)
- [ ] C-2 MERGE 7→6 (source-tensions → reconcile Step 6.5; `comparisons.md`+`source-tensions.json` → `tensions.md`)
- [ ] C-3 CUT 9→10 (evidence-digest inline in Step 10.0b; carries A's line fields)
- [ ] C-4 grader round-1 aggregates `critic-findings-*.json`
- [ ] C-5 remove `--reasoning-effort` alias; confirm `--interactive` auto-default
- [ ] C-6 17-stage roster guard

**B — `sections/B-verification.md`**
- [ ] B-1 assumption-critic agent constant + install registration (`hooks.py`)
- [ ] B-2 assumption-critic spawn prose (`bad-research-12-critics.md`) + `PATCHER_AGENT` one-line update (`hooks.py`, `bad-research-14-patcher.md`)
- [ ] B-3 grader_history failure ledger + escalation clause (`bad-research-12.5-grader.md`)
- [ ] B-4 fresh-review prior-generation proxy (`bad-research-fresh-review.md`)
- [ ] B-5 query expansion (width-sweep Step 2.1) + direction-switch pivot rule (depth-investigation)

**D — `sections/D-E1.md`**
- [ ] D-1 `JUDGE_TIER "heavy" → "work"` (`calibrate/constants.py:23`)
- [ ] D-2 delegate decompose to work-tier subagent (`bad-research-1-decompose.md`)
- [ ] D-3 delegate Step 6.5 orphan-tension-scan to work-tier subagent (after C-2)
- [ ] D-4 (OPTIONAL) document step-8 ∥ inline-digest overlap — not implemented

---

## Cross-Workstream Consistency Notes (verified during self-review)

1. **Shared symbols (A-internal):** `body_to_lines`/`char_span_to_line_range` (A-1) are consumed by A-5, A-7, and the C-3 inline digest. `ClaimAnchor.line_start/line_end` (A-3) are consumed by A-5 and A-6. Names are consistent across all references.
2. **`PARTIAL_LOW` (A-6 precondition):** A-6 does `from .verifier import PARTIAL_LOW`. Confirm this constant exists in `grounding/verifier.py` before A-6; per round2-citation §4 it is an existing verifier threshold. If absent, define it in A-5 alongside `LineSpanJudge`.
3. **Citation-token → anchor resolution (A integration point):** `extract_citations` (A-4) now returns the full `note-id:L42-L58` token; `parse_line_anchor` strips the suffix. Confirm the verifier resolves the citation to its `ClaimAnchor` (keyed by `quote_sha`) after stripping the line suffix — A's tests cite by `anchor_id`, so verify the suffix path during A-4/A-5 execution.
4. **`bad-research-12.5-grader.md` is edited twice:** C-4 (round-1 aggregate) then B-3 (grader_history). Do C-4 first; B-3 adds the failure ledger on top. They touch different subsections — no overlap.
5. **`core/hooks.py` is edited by both C and B:** C edits `_BAD_RESEARCH_STEP_SKILLS` (roster); B adds `ASSUMPTION_CRITIC_AGENT` + install hooks + `PATCHER_AGENT`. Finish C's roster edits before B to avoid churn. They are disjoint regions.
6. **5th critic does NOT change the 17-count:** the assumption-critic is a spawned sub-agent, not an entry in `_BAD_RESEARCH_STEP_SKILLS`. C-6's `== 17` guard stays correct after B lands.
7. **A-9 vs E1:** A-9 is a self-contained *in-process runtime* regression test; E1-2/E1-3 add the *offline golden* version. Complementary; A-9 does not block on E1.

---

## Self-Review Results

- **Spec coverage:** every spec section maps to tasks — §2 (A)→A-1..A-9; §3 (B)→B-1..B-5; §4 (C)→C-1..C-6; §5 (D)→D-1..D-4; §5b (E1)→E1-1..E1-3. No spec requirement is unimplemented. Cross-model review (§3 B③, infeasible keyless) is delivered as the fresh-review prior-generation proxy (B-4).
- **Placeholder scan:** clean across all 4 section files (one false positive: legitimate fixture data `expected_behavior=["placeholder"]`).
- **Type/name consistency:** shared symbols checked (note 1); three integration points flagged for execution-time confirmation (notes 2, 3, 5).
- **Scope:** five surgical workstreams, one plan; sequenced and independently committable. No decomposition needed.

---

## Regression Gate (run after each workstream)

```bash
cd /Users/seventyleven/Desktop/badresearch
pytest -q                       # full suite green
bad gate                        # golden-eval pass_rate stays 1.0 (default lexical run)
# after E1:
bad gate --llm                  # the two requires_llm fixtures correctly FAIL the bad reports
```
