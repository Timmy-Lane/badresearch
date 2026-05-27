---
name: bad-research-4-loci-analysis
user-invocable: false
description: >
  Step 4 of the Bad Research pipeline (full tier) — spawns 2 parallel analysts to
  surface 1-6 loci (the contested sub-questions worth deep investigation), then
  scores and source-budgets each into research/loci.json.
---

# Step 4 — Loci analysis (parallel, 2 analysts)

**Tier gate:** SKIP entirely for `light` tier — proceed directly to step 9. Only `full` tier runs loci analysis.

**Goal:** identify 1–6 specific questions where depth investigation will pay off.

---

## Recover state

Read these inputs:
- `research/scaffold.md` — vault_tag
- `research/prompt-decomposition.json` — atomic items, sub-questions, **`query_shape`** (set by step 1.5 — drives the step-5 fan-out arrangement, see step 6 below)
- `research/temp/contradiction-graph.json` — ranked fight clusters (if step 3 ran)
- `research/temp/coverage-gaps.md` — which atomic items have weak coverage

Survey the corpus: `$HPR search "" --tag <vault_tag> -j` to confirm width sweep is complete.

---

## Procedure

1. **Spawn 2 `bad-research-loci-analyst` subagents in parallel** (ONE message, both Task calls). Both read the same width corpus but return independently.

   **Spawn template:**
   ```
   subagent_type: bad-research-loci-analyst
   prompt: |
     RESEARCH QUERY (verbatim, gospel):
     > {{paste research/query-<vault_tag>.md body}}

     QUERY FILE: research/query-<vault_tag>.md

     PIPELINE POSITION: You are step 4 (loci-analyst, instance A or B) of
     the Bad Research pipeline. The width sweep (step 2) populated the vault
     tagged <vault_tag>. The contradiction graph (step 3) lives at
     research/temp/contradiction-graph.json. After you and the other
     analyst return, the orchestrator dedupes your loci and assigns budgets.

     YOUR INPUTS:
     - corpus_tag: <vault_tag>
     - analyst_id: "a" (for one) / "b" (for the other)
     - output_path: research/loci-a.json (or research/loci-b.json)
   ```

2. **Wait for both.** If one fails, proceed with the single successful output. If both fail (empty loci lists), tell the user the width sweep was too thin and stop — do not force depth on a weak corpus.

3. **Deduplicate and clamp to 6.**
   - Read both JSON outputs.
   - Dedupe on `name` (exact match) or near-match (same core question, different phrasing). When in doubt, prefer the entry with stronger `corpus_evidence`.
   - If the deduped list exceeds 6, drop the weakest entries — rank by how load-bearing the rationale is for the canonical research query.
   - **Persist both analysts' `skip_loci` arrays** in the merged output — union them under a top-level `skip_loci` key. These justifications matter downstream.

4. **Score and budget each locus (dynamic depth allocation).** For each surviving locus, compute four dimensions:
   - **importance** (0-10): how central is this locus to the research_query? A locus that directly answers a primary sub-question scores 8-10; tangential enrichment scores 2-4.
   - **uncertainty** (0-10): how uncertain is the current evidence? If the contradiction graph shows a sharp fight with equal-quality evidence on both sides, uncertainty is high (8-10). If one side has clearly stronger evidence, moderate (4-6). If the corpus already resolves this, low (1-3).
   - **disagreement** (0-10): how many independent sources disagree? Proxy from the contradiction cluster size. Singletons score low (2-3); multi-source fights score high (7-10). If no contradiction graph exists, estimate from the loci analyst's `opposing_positions`.
   - **decision_impact** (0-10): would resolving this locus change the draft's recommendation or thesis? If yes, high (8-10). If it adds nuance but doesn't change direction, moderate (4-6).

   **Composite score** = importance + uncertainty + disagreement + decision_impact (max 40).

   **Allocate source budgets.** Total source budget for step 5 is 40. Distribute proportionally:
   - Loci scoring 30-40: `source_budget` up to 15 (deep dive)
   - Loci scoring 20-29: `source_budget` up to 10 (standard)
   - Loci scoring 10-19: `source_budget` up to 5 (shallow pass)
   - Loci scoring <10: `source_budget` 0-3, or skip investigation entirely

   It's fine if only 1-2 loci score above 20 — allocate heavily to them.

5. **Write scored loci to `research/loci.json`.** Schema:
   ```json
   {
     "loci": [
       {
         "name": "...",
         "one_line": "...",
         "flavor": "dialectical|synthesis|technical",
         "importance": 8,
         "uncertainty": 7,
         "disagreement": 6,
         "decision_impact": 9,
         "composite_score": 30,
         "source_budget": 12,
         "rationale": "..."
       }
     ],
     "skip_loci": [...union from both analysts...]
   }
   ```

6. **Decide investigator count AND fan-out arrangement (branch on `query_shape`).** Read `query_shape` from `research/prompt-decomposition.json` (set by step 1.5). The fan-out *shape* — orthogonal to the tier — decides how step 5's investigators are *arranged* (Claude Research `research_lead_agent.md:12-29`):

   - **`breadth_first`** → investigators run **in parallel** across the independent sub-questions / loci, **importance-ordered** (highest composite-score locus first), `K = min(n_subq, cap)` capped at 6. This is the default arrangement for surveys/comparisons/collections — the loci are independent so they go wide simultaneously.
   - **`depth_first`** → **2–4 SEQUENTIAL** perspectives on the **one** highest-impact locus. Do NOT fan out across many loci; instead pick the single most contested/load-bearing locus and queue 2–4 investigators that run one after another, each reading the prior's committed position (set up in step 5). One topic, many angles, going deep.
   - **`straightforward`** → a **single** investigator on the one locus that matters. No ensemble.

   Record the chosen arrangement (`parallel` / `sequential` / `single`) and the ordered locus list in `research/loci.json` under a top-level `"fanout"` key so step 5 dispatches accordingly. Absent a `query_shape` (older runs), default to the legacy parallel-per-locus behavior. The base rule still holds: one depth-investigator per locus with `source_budget > 0`, capped at 6; if only 1 locus passes scoring, spawn 1.

**INVARIANT:** at least one `flavor: "dialectical"` locus must be present unless an analyst's `skip_loci` justifies its absence with specific evidence of a univocal corpus. No dialectical locus + no justification = re-spawn the loci-analyst with a tighter prompt.

**Placeholder-breadcrumb ban:** depth investigators will fetch sources; do not hand them breadcrumb placeholders like `bad-research-locus-seed` — use real source note ids from the vault or omit `--suggested-by` entirely.

---

## Exit criterion

- `research/loci.json` exists with at least 1 locus (or both analysts justified skip with `skip_loci`)
- At least one dialectical locus OR a documented justification in `skip_loci`
- All retained loci have `source_budget` allocated

---

## Next step

Return to the entry skill (`bad-research`). Invoke step 5:

```
Skill(skill: "bad-research-5-depth-investigation")
```
