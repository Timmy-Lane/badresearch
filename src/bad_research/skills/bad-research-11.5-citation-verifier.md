---
name: bad-research-11.5-citation-verifier
description: >
  Stage 11.5 of the Bad Research pipeline — the backward grounding pass. Runs
  the CitationVerifier over the synthesized report: per cited sentence,
  cheapest-first byte-identity → local NLI entailment → triage-LLM-judge for the
  ~10% neutral band → re-fetch arbitration (gated to contradicted+critical).
  Dispositions route to the patcher. Tool-locked [Read]. Invoked via Skill tool
  from the entry skill after step 11 synthesize (full tier only).
---

# Step 11.5 — Citation verifier (backward grounding)

**Tier gate:** SKIP for `light` and `agentic-fast` (their grounding is the
forward binding-at-fetch + the step-16 gate). Runs for `full` only, after
step 11 (synthesize), before step 12 (critics).

**Goal:** verify that every cited sentence in the final report is actually
supported by the cited vault note, using the cheapest sufficient method per
sentence. This is the no-hallucination backstop — it kills fabricated quotes
($0 byte-identity) before any expensive method runs.

## Recover state

This step is tool-locked to `[Read]`. Read:
- `research/notes/final_report_<vault_tag>.md` — the synthesized report
- `research/prompt-decomposition.json` — citation_style
- `research/scaffold.md` — vault_tag

## Procedure

1. Run the verifier (deterministic Python from the grounding seam):
   ```bash
   bad verify-citations --report research/notes/final_report_<vault_tag>.md \
       --vault-tag <vault_tag> --json
   ```
   Per cited sentence it runs, cheapest-first:
   - **(A) byte-identity** — re-`find` the `quoted_support` in the cited note +
     SHA match ($0; kills fabricated quotes).
   - **(B) NLI entailment** — local `nli-deberta-v3-base` ($0). For the ~10%
     NLI-neutral band, a `triage`-tier LLM-judge fallback (batched ~20/call).
   - **(C) re-fetch arbitration** — gated to contradicted + critical sentences
     only.

   It writes per-sentence dispositions and updates the `claim_anchors` table
   (`anchor_id = quote_sha`, `verified`, `verify_score`). Output JSON:
   ```json
   {"results": [
     {"sentence": "...", "cite_ids": ["[[note-id]]"],
      "disposition": "supported|partial|unsupported|contradicted",
      "verify_score": 0.0, "quoted_support": "..."}]}
   ```

2. Route dispositions to the patcher (step 14 applies them as surgical Edits):
   - **supported** → keep as-is.
   - **partial** → hedge the claim (the patcher softens the assertion).
   - **unsupported** → drop the citation; if the sentence has no other support,
     the patcher flags it for removal or re-grounding via gap-fetch (step 13).
   - **contradicted** → feed into `research/temp/contradiction-graph.json` (the
     report must engage the contradiction, not assert one side).

   Write the routed actions to `research/temp/citation-verify-actions.json` —
   the patcher reads this alongside the critic findings.

3. Do NOT edit the report here ([Read]-locked). All changes flow through the
   patcher (step 14), preserving PATCH-NEVER-REGENERATE.

## Exit criterion

- `research/temp/citation-verify-actions.json` exists
- The `claim_anchors` table has `verified`/`verify_score` for every cited sentence
- No edits made to the report in this step (tool-lock holds)

## Next step

Return to the entry skill (`bad-research`). Invoke step 12:
`Skill(skill: "bad-research-12-critics")`.
