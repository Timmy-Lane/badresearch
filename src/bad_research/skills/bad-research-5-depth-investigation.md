---
name: bad-research-5-depth-investigation
description: >
  Step 5 of the hyperresearch V8 pipeline. Spawns K depth-investigator
  subagents in parallel (one per scored locus), each producing one
  interim note with a Committed Position section. Investigators read
  full source bodies for their locus and may fetch additional sources
  within their source_budget. Invoked via Skill tool from the entry
  skill (full tier only).
---

# Step 5 — Depth investigation (parallel, K = len(loci))

**Tier gate:** SKIP entirely for `light` tier. Only `full` tier runs depth investigation.

**Goal:** produce ONE `interim-{locus}.md` note per locus with dense synthesis that the draft sub-orchestrators (step 10) will draft from.

---

## Recover state

Read these inputs:
- `research/scaffold.md` — vault_tag
- `research/loci.json` — scored loci with source_budget per locus
- `research/temp/contradiction-graph.json` (if step 3 ran)
- `research/query-<vault_tag>.md` — canonical research query

---

## Procedure

1. **Spawn K `bad-research-depth-investigator` subagents in parallel** (ONE message, all Task calls). One per locus with `source_budget > 0`, capped at 6.

   **Spawn template** (carries the 7-field delegation contract — the four added
   fields `objective`, `output_shape`, `tools_allowed`, `stop_conditions` appear
   as the uppercase blocks below):
   ```
   subagent_type: bad-research-depth-investigator
   prompt: |
     RESEARCH QUERY (verbatim, gospel):
     > {{paste research/query-<vault_tag>.md body}}

     QUERY FILE: research/query-<vault_tag>.md

     PIPELINE POSITION: You are step 5 (depth-investigator) of the
     hyperresearch V8 pipeline. Step 4's loci analysts produced research/loci.json;
     after you return, step 6 will reconcile your committed position against
     the other investigators' positions in research/comparisons.md.

     YOUR LOCUS (from research/loci.json):
     - name: "<locus name>"
     - one_line: "<one-line locus description>"
     - flavor: "dialectical" / "synthesis" / "technical"
     - source_budget: <integer from loci.json>
     - rationale: "<why this locus matters>"

     YOUR INPUTS:
     - corpus_tag: <vault_tag>
     - locus_name: <locus name>
     - source_budget: <hard cap on additional sources you can fetch>

     OBJECTIVE: investigate the assigned locus to a committed position, grounding
     every claim in primary sources.

     OUTPUT_SHAPE: an interim note ending in `## Committed position`, plus a claims
     JSON array of {claim, note_id, quoted_support, char_start, char_end}.

     TOOLS_ALLOWED: ["fetch_url", "web_search", "Read", "Write", "execute_python"]

     STOP_CONDITIONS: halt when the locus is investigated to a committed position OR
     you reach the fetcher tool-call cap (FETCHER_TOOLCALL_CAP) OR INVESTIGATOR_TIMEOUT_S
     (900s) elapses — then return your committed position with the evidence gathered so
     far. Do not keep searching for nonexistent sources. Hard kill at SUBAGENT_SOURCE_KILL (100).

     CRITICAL: Read the full source text of relevant vault notes (via
     `hyperresearch note show <id1> <id2> ... -j`) BEFORE writing your
     interim note. Drafting from summaries alone produces paraphrase;
     drafting from full text produces synthesis. Use your source_budget
     to fetch additional sources beyond the width corpus if needed.

     OUTPUT: Write a single interim note via the hyperresearch CLI with
     type=interim, tags = <vault_tag> + locus-<locus-name>. The note MUST
     end with a "## Committed position" section that takes a SIDE on the
     dialectical question (or a synthesis verdict for non-dialectical
     loci). Include calibration: confidence level, what evidence would
     change your mind.
   ```

   Each investigator's hard cap is `locus.source_budget`, not a flat number.

   **Hard sources (JS-heavy, login-walled, anti-bot):** when a load-bearing
   source fails a Tier-0/1 fetch (returns junk or a login wall), escalate it
   through the Tier 0→3 browse ladder instead of giving up:

   ```bash
   bad fetch "<url>" --tier-max 3 --tag <vault_tag> \
       --instruction "extract the section about <topic>" --json
   ```

   Tier 0 = HTTP, Tier 1 = crawl4ai (JS render), Tier 2 = typed extract
   (AgentQL / LLM-extract), Tier 3 = agentic browse (Browser-Use self-host).
   Escalation is gated by `looks_like_junk()` / `looks_like_login_wall()` — only
   hard pages climb the ladder; cheap pages stop at Tier 0. The SSRF guard
   refuses any private/loopback/metadata URL before the fetch runs.

2. **Each investigator writes ONE interim note** into the vault with `type: interim` and tags `<vault_tag>` + `locus-<locus-name>`. Return value is the note id.

3. **Wait for all K to complete.** Investigators can fail independently. Proceed with whichever succeeded. If >50% failed, stop and reassess loci quality with the user.

4. **Read the interim notes.** After all return, list them:
   ```bash
   $HPR search "" --tag <vault_tag> --type interim --json
   ```
   Then batch-read them:
   ```bash
   $HPR note show <id1> <id2> ... -j
   ```
   Hold the Committed Position sections in your context — they are the load-bearing input to step 6 (cross-locus reconciliation).

**INVARIANT:** Every interim note ends with a `## Committed position` section. An interim note ending with descriptive summary only is defective — flag it and re-spawn that investigator with the committed-position requirement emphasized.

---

## Exit criterion

- One interim note per locus with `source_budget > 0`, each tagged `<vault_tag>` + `locus-<locus-name>`
- Every interim note ends with `## Committed position`

If >50% of investigators failed: stop and escalate.

---

## Next step

Return to the entry skill (`hyperresearch`). Invoke step 6:

```
Skill(skill: "bad-research-6-cross-locus-reconcile")
```
