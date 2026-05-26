---
name: bad-research
description: >
  Deep research via the HYPERRESEARCH V8 architecture — a tier-adaptive 16-step
  pipeline (light / full) that scales from a ~30-minute light-tier answer to
  a 1.5–2.5 hour adversarially-audited report. This entry skill is a ROUTER.
  It does not contain step procedures — it tells you which Skill to invoke
  for each step, in order. Each step's instructions live in its own skill
  file (`bad-research-1-decompose` through `bad-research-16-readability-audit`)
  and are loaded fresh into context when you invoke them.
---

# Hyperresearch V8 — multi-skill chain orchestrator

You are the orchestrator (Opus). Your entire job in this conversation is:
1. Read this file once at the start.
2. Bootstrap canonical inputs (research_query, vault_tag, scaffold).
3. Invoke each step skill in sequence via the `Skill` tool.
4. Between steps, do nothing except mark todos and (optionally) think to `research/temp/orchestrator-notes.md`.

You do NOT do the work of any step yourself. The step skills do. You just sequence them.

---

## How the chain works (READ THIS CAREFULLY)

Each pipeline step is its own skill file. To run a step:

```
Skill(skill: "bad-research-N-stepname")
```

When you invoke a Skill, that skill's full procedure is loaded into your context **fresh**. You then execute that step's procedure, hit its exit criterion, and return to the entry skill (this file) to invoke the next step.

**Why this design?** Context compaction. V7 was one 1200-line skill that got compacted away by the time Layer 4 needed its triple-draft procedure. The orchestrator forgot the procedure, wrote a single draft, and produced a flat-scoring report. V8 fixes this at the source: each step's procedure is loaded into context **only at the moment it's needed**, fresh, with no eviction risk.

**The 16 step skills** (all prefixed `bad-research-`):

| # | Skill name | What it does | Tiers |
|---|---|---|---|
| 1 | `bad-research-1-decompose` | Canonical query → scaffold + decomposition + coverage matrix + tier classification | all |
| 2 | `bad-research-2-width-sweep` | Multi-perspective search plan + parallel fetcher waves | all |
| 3 | `bad-research-3-contradiction-graph` | Pair contradictions across the corpus into ranked fight clusters | full |
| 4 | `bad-research-4-loci-analysis` | 2 loci-analysts → scored loci.json with source budgets | full |
| 5 | `bad-research-5-depth-investigation` | K depth-investigators in parallel → interim notes with committed positions | full |
| 6 | `bad-research-6-cross-locus-reconcile` | Reconcile committed positions → comparisons.md | full |
| 7 | `bad-research-7-source-tensions` | Extract expert disagreements → source-tensions.json | full |
| 8 | `bad-research-8-corpus-critic` | "What source would overturn this?" + targeted gap-fill fetch | full |
| 9 | `bad-research-9-evidence-digest` | Top claims + verbatim quotes → evidence-digest.md | full |
| 10 | `bad-research-10-triple-draft` | Per-angle source curation + 3 parallel draft-orchestrators (3 angle-specific drafts) | all |
| 11 | `bad-research-11-synthesize` | Synthesis plan + outline + spawn synthesizer subagent (two-pass write) → final_report.md | full |
| 12 | `bad-research-12-critics` | 4 adversarial critics in parallel → findings JSONs | full |
| 13 | `bad-research-13-gap-fetch` | Fetch sources for critic-identified vault gaps | full |
| 14 | `bad-research-14-patcher` | Surgical Edit hunks applied to draft | full |
| 15 | `bad-research-15-polish` | Hygiene + filler pass (Edit-based subagent) | all |
| 16 | `bad-research-16-readability-audit` | Readability recommender writes JSON suggestions; orchestrator selectively applies via Edit | all |

---

## Tier routing

Step 1 decomposes the query; the query-router (step 1.5) classifies the
decomposition into a `route` (`agentic-fast` / `light` / `full`) written to
`research/prompt-decomposition.json`. After step 1.5, **read that file** for the
`route`, then sequence steps according to this mode table:

| Route | Stage sequence | Cost | Time |
|---|---|---|---|
| `agentic-fast` | 0.5(skip) → 1 → 1.5 → agentic-fast → 15 → 16(+gate) | ~$1–5 | <3 min |
| `light` | 0.5 → 1 → 1.5 → 2(funnel) → 10(single draft) → 15 → 16(+gate) | ~$5–15 | ~30–40 min |
| `full` | 0.5 → 1 → 1.5 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 11.5 → 12 → 13 → 14 → 14.5(fresh-review) → 15 → 16(+gate) | ~$60–120 | ~1.5–2.5 h |

Where the stage numbers map to:
- 0.5 → `Skill(skill: "bad-research-0.5-clarify")` (triage clarifier; skipped for agentic-fast + --auto)
- 1.5 → `Skill(skill: "bad-research-query-router")` (the route decision)
- agentic-fast → `Skill(skill: "bad-research-agentic-fast")` (bounded ReAct; replaces 2–14)
- 11.5 → `Skill(skill: "bad-research-11.5-citation-verifier")` (backward grounding; full only)
- 14.5 → `Skill(skill: "bad-research-fresh-review")` (one fresh-context pass; full only)

**RESPECT THE ROUTE.** `agentic-fast` is the cheap bounded ReAct loop, not a
degraded full run; do NOT add the 16 stages "to be thorough." `full` ALWAYS runs
11.5 (citation verifier) and 14.5 (fresh-review). The deterministic
no-uncited-claim gate in step 16 is a **ship-block for ALL routes**. If
uncertain, route up — but never silently upgrade every query to `full`.

---

## Bootstrap (run BEFORE invoking step 1)

Before you invoke any step skill, do this:

0. **Auto-init if missing.** Two checks for the first-run-after-global-install case:
   - **Vault check.** If `.hyperresearch/` doesn't exist in the working directory, run `bad init . --json`. Creates the SQLite vault and `research/` directory.
   - **Step-skills check (lazy install).** If `.claude/skills/bad-research-1-decompose/SKILL.md` doesn't exist relative to the working directory, run `bad install --steps-only . --json`. The user-global install ships only the entry skill + agents + PreToolUse hook; the step skills materialize per-project on first `/bad-research` invocation via this command. It installs the step skill files needed by `Skill(skill: "bad-research-N-...")` calls in later steps.

   If either command fails because the binary isn't on PATH, tell the user to run `pip install bad-research` first. If both files already exist, both commands no-op cheaply — safe to run unconditionally.

0.5. **Archive any prior run's artifacts.** Run `hyperresearch archive-run --json`. If a previous `/hyperresearch` session left a scaffold, loci.json, comparisons.md, critic-findings, patch-log, polish-log, prompt-decomposition, or any `research/temp/*` scratch, this moves the whole set into `research/runs/archive-<prev-tag>-<UTC-timestamp>/` so the new run starts from a clean slate without losing the prior run's audit trail. Final reports (`research/notes/final_report_<tag>.md`) and canonical query files (`research/query-<tag>.md`) are already namespaced and stay in place. The command no-ops cheaply on a fresh vault — safe to run unconditionally. **Caveat:** this protects sequential runs only. Two `/hyperresearch` invocations that overlap in time still race on the new files they both write; if you need true parallel runs, namespace per-run artifacts under `research/runs/<vault_tag>/` instead.

1. **Resolve the canonical research query.** Order of precedence:
   - If `research/prompt.txt` exists (legacy harness / wrapped run), read it. Its contents are the canonical research query. GOSPEL.
   - Otherwise, use the user's verbatim prompt as the canonical research query.
   - Extract wrapper requirements separately: required save path, citation format, terminal-section shape, wrapper contract. These are binding but NOT part of the query.
   - If `research/wrapper_contract.json` exists, read it.

2. **Mint a unique vault tag.** First produce a short topical slug from the canonical query — 3–5 lowercase hyphen-separated words, e.g. `efield-dft-sac`. Then call `hyperresearch vault-tag <slug> --json` and parse the `vault_tag` field from the response. The CLI appends a random 6-hex-char suffix that's verified unique against every prior run's `research/query-*.md` and `research/notes/final_report_*.md` in this vault. The result — e.g. `efield-dft-sac-a3f9b7` — is the canonical vault_tag for the rest of the pipeline. The suffix guarantees no overwrite of a prior run's final report or query file, even if the user re-runs the exact same query or two different queries slug-collide.

3. **Persist the query file.** Write the verbatim canonical query to `research/query-<vault_tag>.md`:
   ```markdown
   ---
   vault_tag: <slug>
   created: <ISO-8601 timestamp>
   source: prompt.txt | user-prompt
   ---

   <verbatim query text, character-for-character>
   ```
   This file is the **canonical query reference for the entire pipeline**. Every step skill and every subagent reads it by path.

4. **Classify modality** (collect / synthesize / compare / forecast) — record in the scaffold. This is a label that calibrates step 10's drafting style:
   - **collect**: enumerative coverage, per-entity sections with named fields
   - **synthesize**: defended thesis with evidence chains
   - **compare**: proportionate per-entity depth + a committed recommendation
   - **forecast**: predictive claims grounded in past + present, explicit time horizon

5. **Write the scaffold.** Write `research/scaffold.md` (your private planning document — it MUST NOT appear anywhere in the final report). Include in scaffold:
   - User Prompt (VERBATIM — gospel)
   - Run config (vault_tag, query_file_path, modality, wrapper requirements)
   - Modality classification rationale
   - Tier rationale (filled in after step 1)
   - Wrapper requirements (save path, citation format, terminal sections)

6. **Seed the TodoWrite list.** Create todos for the step skill invocations using the step numbers, e.g.:
   - `Step 0.5 — Skill: bad-research-0.5-clarify`
   - `Step 1 — Skill: bad-research-1-decompose`
   - `Step 1.5 — Skill: bad-research-query-router`
   - `Step 2 — Skill: bad-research-2-width-sweep`
   - ... (through Step 16; the exact set depends on the route decided at 1.5)

   The todo list survives context compaction; it's your durable memory of where you are in the chain.

7. **Invoke the clarifier (step 0.5)** UNLESS this is an `--auto` / wrapped run
   (`research/wrapper_contract.json` present) — then skip straight to step 1:
   `Skill(skill: "bad-research-0.5-clarify")`. The clarifier is triage-tier,
   default-proceed, ≤3 questions; it writes `research/clarify.json`.

8. **Invoke step 1 (decompose):** `Skill(skill: "bad-research-1-decompose")`.

9. **Invoke step 1.5 (the query router):** `Skill(skill: "bad-research-query-router")`.
   It runs `bad route --apply` over the decomposition and writes the `route`
   field into `research/prompt-decomposition.json`.

After step 1.5 returns, read `research/prompt-decomposition.json` for the `route`,
then continue invoking step skills per the mode table above. For `agentic-fast`,
invoke `Skill(skill: "bad-research-agentic-fast")` then jump to step 15 polish +
step 16 gate. After each step's exit criterion is met, mark its todo complete and
move to the next.

---

## Four canonical rules (ALWAYS in force)

1. **NEVER EMIT BARE TEXT WHILE TASKS ARE RUNNING.** In non-interactive (`-p`) mode, a text-only response (no tool call) triggers `end_turn` — the process exits and the pipeline dies. Every response while subagent tasks are in flight MUST include a tool call. The best one is appending analytical thoughts to `research/temp/orchestrator-notes.md`. Vault count checks at most once per minute.

2. **PATCH, NEVER REGENERATE.** After step 11 produces the synthesized final report (or step 10 for light tier), the only modifications are surgical Edit hunks from step 14 (patcher) and step 15 (polish-auditor). Both subagents are tool-locked to `[Read, Edit]`. If a critic's finding would require rewriting a whole section, it escalates to you as a structural issue — not a rewrite. Keep hunks surgical.

3. **ARGUE, DON'T JUST REPORT** (full force for `argumentative` response_format; relaxed for `structured` and `short`). The pipeline is engineered to push the final report toward argumentative density. Loci must include at least one dialectical locus. Depth investigators must commit to a position. Step 6 forces cross-locus reconciliation. Step 11's synthesizer requires every body section that touches a tension to engage it explicitly.

4. **RESPECT THE TIER GATE.** See tier routing table. Don't add steps "for thoroughness." Don't drop steps "for budget." The tier is a binding contract.

---

## Subagent spawn contract (applies to every Task call)

When a step skill instructs you to spawn a subagent, the prompt you pass MUST include three pieces near the top:

1. **`research_query` — verbatim, block-quoted** from `research/query-<vault_tag>.md`. Do not paraphrase, do not summarize.

2. **Pipeline position statement.** One sentence naming what step the subagent runs in, what came before, what comes after. Example: *"You are step 5 (depth investigator) of the hyperresearch V8 pipeline. Step 4's loci analysts produced `research/loci.json`; after you return, step 6 will reconcile your committed position against the other investigators'."*

3. **The subagent's specific inputs** (vault_tag, output_path, locus, etc.). Each step skill's spawn template documents the required fields.

Skipping any of these in a Task prompt is a process violation.

---

## Recovery: if you wake up uncertain where you are

Context compaction may eat parts of this conversation. If you're unsure what step you're on:

1. **Check the TodoWrite list.** It carries integer step numbers and survives compaction.
2. **Check disk artifacts.** Each step writes a canonical artifact:
   - Step 0.5: `research/clarify.json` (+ `## Brief` in scaffold)
   - Step 1: `research/scaffold.md`, `research/prompt-decomposition.json`, `research/temp/coverage-matrix.md`
   - Step 1.5: the `route` field inside `research/prompt-decomposition.json` (+ `## Route rationale` in scaffold)
   - agentic-fast: `research/temp/react-trace.md` (+ `research/notes/final_report_<vault_tag>.md`)
   - Step 2: vault notes tagged with vault_tag (`$HPR search "" --tag <vault_tag> -j`)
   - Step 3: `research/temp/contradiction-graph.json`, `research/temp/consensus-claims.json`
   - Step 4: `research/loci.json`
   - Step 5: vault notes with `type: interim` (`$HPR search "" --tag <vault_tag> --type interim -j`)
   - Step 6: `research/comparisons.md`
   - Step 7: `research/temp/source-tensions.json`
   - Step 8: `research/corpus-critic-gaps.json`, `research/temp/corpus-critic-results.md`
   - Step 9: `research/temp/evidence-digest.md`
   - Step 10: `research/temp/draft-{a,b,c}.md` (or `research/notes/final_report_<vault_tag>.md` for light tier single-pass)
   - Step 11: `research/temp/synthesis-plan.md`, `research/temp/synthesis-outline.md`, `research/temp/synthesis-evidence.md`, `research/temp/synthesis-pass1.md`, `research/notes/final_report_<vault_tag>.md`
   - Step 11.5: `research/temp/citation-verify-actions.json` (citation-verifier dispositions; full only)
   - Step 12: `research/critic-findings-{dialectic,depth,width,instruction}.json`
   - Step 13: `research/temp/post-critic-fetch-log.md`
   - Step 14: `research/patch-log.json` (and edited final_report.md)
   - Step 14.5: `research/temp/fresh-review.json` (fresh-context reviewer findings; full only)
   - Step 15: `research/polish-log.json` (and edited final_report.md)
   - Step 16: `research/readability-recommendations.json`, `research/readability-decisions.json`, the `bad uncited-gate` pass (and edited final_report.md)
3. **Find the highest-numbered step whose artifact exists.** Resume from the next step.
4. **Re-invoke this entry skill** if you've lost track entirely: `Skill(skill: "bad-research")`. It loads fresh.

If you're ever uncertain what to do next, the answer is: re-read this file and find the next step in the tier sequence.

---

## Final integrity gate (after step 16)

Once step 16 returns, run the integrity check:

```bash
for f in research/critic-findings-dialectic.json \
         research/critic-findings-depth.json \
         research/critic-findings-width.json \
         research/critic-findings-instruction.json \
         research/patch-log.json \
         research/polish-log.json; do
  test -f "$f" || echo "MISSING: $f"
done
```

(Light tier skips critics + patcher entirely — the critic-findings and patch-log files won't exist. That's expected; only `polish-log.json` is required for light.)

Then run lint:
```bash
$HPR lint --rule wrapper-report --json
$HPR lint --rule locus-coverage --json
$HPR lint --rule scaffold-prompt --json
$HPR lint --rule patch-surgery --json
```

If any rule returns `error` severity issues, address them before declaring complete. Then ship: the final report lives at `research/notes/final_report_<vault_tag>.md`.

---

## Invariants you cannot break

1. **PATCHING not REGENERATION after step 11.** Once step 11 produces the final report (or step 10 for light tier), modifications are surgical Edit hunks only.
2. **One final report.** Step 11's synthesizer writes the final report ONCE. No re-synthesizing. (Light tier: step 10 writes it once.)
3. **At least one dialectical locus.** Step 4 must surface ≥1 dialectical locus unless skip is justified.
4. **Every interim note commits to a position.** Step 5 investigators end with `## Committed position`.
5. **`research/comparisons.md` exists when loci count ≥ 1.** Step 6 is mandatory whenever step 4 produced any loci.
6. **Steps are sequential at the outermost level, parallel within.** You cannot start step N+1 before step N completes. Within a step, parallelism is mandatory when there are multiple subagents.
7. **Canonical research query is gospel everywhere.** Every subagent gets the verbatim query.
8. **Hygiene rules apply to the final report only.** Workspace artifacts (scaffold, loci JSONs, interim notes, comparisons.md, patch log) can look however they need to look.
9. **NEVER skip a step that the tier gate says to run.** For `full` tier, ALL 16 steps run. For `light`, the prescribed 5 steps run.
10. **Step 10 triple-draft ensemble is MANDATORY for `full` tier.** You MUST spawn 3 `bad-research-draft-orchestrator` subagents. Writing `research/notes/final_report_<vault_tag>.md` directly in step 10 (instead of going through the synthesizer in step 11) is a PIPELINE VIOLATION for these tiers.
11. **Step 11 synthesis is MANDATORY for `full` tier.** The synthesizer subagent (Read+Write tool-locked) writes the final report from the 3 drafts. The orchestrator does NOT write the final report itself for these tiers.
12. **Subagents read full source text.** Draft sub-orchestrators MUST batch-read every note in their `must_read_note_ids` list before writing. Fetchers MUST chase 3-8 primary sources via citation chains.
13. **NEVER emit a bare text response while subagent tasks are in flight.**

---

## Why V8

V7 was one 1200-line skill loaded once. By Layer 4 (line ~2200 in a 3000-line conversation), context compaction had evicted the procedure. The orchestrator silently dropped Layer 3.7 (corpus critic), rewrote its todo to replace the triple-draft ensemble with a single draft, and produced a flat-scoring report. This happened in 100% of runs where the orchestrator didn't re-read the skill file.

V8 makes re-reading structural. Each step skill is loaded fresh via the `Skill` tool at the moment it's needed. The procedure is in context exactly when it matters. Compaction can evict an old step's procedure — that's fine, the orchestrator never needs it again because each step is self-contained and reads its inputs from disk.

The trade: 16 skill files instead of 1, plus 16 invocations of the `Skill` tool over the run. The cost is negligible; the reliability gain is the difference between Q57 (55.9, full pipeline) and Q9 (52.6, single-draft fallback).

---

## Now begin

If you've read this far and the bootstrap (above) is done, invoke step 1:

```
Skill(skill: "bad-research-1-decompose")
```

If the bootstrap is NOT done, do the bootstrap first, then invoke step 1.
