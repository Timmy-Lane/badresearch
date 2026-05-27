---
name: bad-research-12-critics
user-invocable: false
description: >
  Step 12 of the Bad Research pipeline (full tier) — spawns 4 adversarial critics
  in parallel against the final report, each writing a findings JSON for the
  patcher (critics never edit the draft).
---

# Step 12 — Adversarial critique (parallel critics)

**Tier gate:** SKIP entirely for `light` tier — proceed directly to step 15 (polish). For `full` tier: spawn all 4 critics.

**Goal:** independent findings lists against the synthesized final report, each from a different adversarial angle. Critics complement rather than duplicate.

---

## Recover state

Read these inputs:
- `research/scaffold.md` — vault_tag
- `research/prompt-decomposition.json` — pipeline_tier, atomic items
- `research/notes/final_report_<vault_tag>.md` — merged draft from step 10
- `research/query-<vault_tag>.md` — canonical research query

---

## Procedure

1. **Spawn all 4 critics in parallel.** In ONE message:
   - `bad-research-dialectic-critic` → `research/critic-findings-dialectic.json` (counter-evidence the draft missed or straw-manned)
   - `bad-research-depth-critic` → `research/critic-findings-depth.json` (shallow spots where interim notes could fill substance)
   - `bad-research-width-critic` → `research/critic-findings-width.json` (corpus clusters the draft ignores despite evidence)
   - `bad-research-instruction-critic` → `research/critic-findings-instruction.json` (atomic items from the decomposition that the draft missed, under-covered, reordered, or reformatted)

2. **Pass each critic** (standard 3-piece contract):
   ```
   subagent_type: bad-research-<critic-name>-critic
   prompt: |
     RESEARCH QUERY (verbatim, gospel):
     > {{paste research/query-<vault_tag>.md body}}

     QUERY FILE: research/query-<vault_tag>.md

     PIPELINE POSITION: You are step 12 (<critic-name> critic) of the
     Bad Research pipeline. Step 11 (synthesizer) produced the final report at
     research/notes/final_report_<vault_tag>.md. After you return, step 13 may run a
     gap-fetch wave, then step 14 (patcher) applies findings as Edit hunks.

     YOUR INPUTS:
     - draft_path: research/notes/final_report_<vault_tag>.md
     - output_path: research/critic-findings-<critic-name>.json
     - vault_tag: <vault_tag>
     - decomposition_path: research/prompt-decomposition.json   (instruction-critic only)
   ```

3. **Wait for all critics.** If one fails, you can proceed with the partial set, but log the absence to the run log — the patch pass is less robust with missing critic coverage. **Do NOT skip the instruction-critic specifically** — it's the only critic measuring prompt adherence, which is the dimension with the widest variance.

4. **Do not read the findings yourself and apply them.** The patcher (step 14) reads the findings. Your job is to hand them to the patcher — AFTER step 13 (gap-fetch) runs.

---

## Exit criterion

- All 4 critic findings JSONs exist (`research/critic-findings-<name>.json`)
- Each is valid JSON with a `findings` array

---

## Next step

Return to the entry skill (`bad-research`). Invoke step 13:

```
Skill(skill: "bad-research-13-gap-fetch")
```
