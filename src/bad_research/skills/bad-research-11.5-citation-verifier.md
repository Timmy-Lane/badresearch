---
name: bad-research-11.5-citation-verifier
user-invocable: false
description: >
  Step 11.5 of the Bad Research pipeline (full tier only) — the backward
  grounding pass that verifies every cited sentence against its source note and
  writes per-claim dispositions (supported / partial / unsupported / contradicted)
  for the patcher. Tool-locked to [Read].
---

# Step 11.5 — Citation verifier (backward grounding)

**Tier gate:** Runs for `full` after step 11 (synthesize), before step 12
(critics). Also runs in **Slim mode** for the `fast` route (see the `## Slim
mode (fast route)` section below) — invoked by the fast skill after the writer,
before the slim critic. The full Read-locked patcher-routed `## Procedure` is
`full`-only; the slim pass is Read+Edit and applies dispositions inline.

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
       --vault-tag <vault_tag> [--effort high] --json
   ```
   **E4 high-effort lane:** when the run's `--effort` is `high` (read it from
   the scaffold's run config / `EFFORT_MAP`), pass `--effort high`. That switches the
   Tier-C high-stakes band (the NLI-ambiguous claims below) from the single batched
   judge to an **N-sample self-consistency vote** (universal self-consistency — sample
   N host judgments, the majority verdict wins; keyless, costs N host calls per
   high-stakes claim). On any other effort, OMIT the flag — the default single-judge
   behaviour is unchanged (no extra calls).

   Per cited sentence it runs, cheapest-first:
   - **(A) byte-identity** — re-`find` the `quoted_support` in the cited note +
     SHA match ($0; kills fabricated quotes).
   - **(B) NLI entailment** — does the note text entail the sentence? Checked by
     a local natural-language-inference model, `nli-deberta-v3-base` ($0) when
     `[local]` is installed. On the keyless path, `LineSpanJudge` (the Tier-B
     replacement for `CitationPresentNLI`) routes near-verbatim pairs to accept
     and genuine paraphrases to the batched Tier-C judge — using the specific
     cited line span (L42-L58) as the premise, not the full `quoted_support`.
     For the ~10% neutral band (neither entailed nor contradicted), a `triage`-tier
     LLM-judge fallback (batched ~20/call).
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

## Slim mode (fast route)

On the `fast` route there is no step-14 patcher, so the slim pass applies dispositions INLINE
(this invocation is Read+Edit, not Read-locked). It runs the same Tier-A byte-identity + Tier-B
LineSpanJudge check, then acts directly with Edit. **This gate is the genuinely additive quality
step** — Anthropic's CitationAgent has NO faithfulness check, so unsupported claims would otherwise
ship silently uncited (`CLAUDE_RESEARCH.md` R5.2); OpenAI's faithfulness is RL-internal/un-portable.

**Which sentences to check (OpenAI 3-tier, `OPENAI_DEEP_RESEARCH.md` §R5.1C — keeps it cheap):**
MUST verify the load-bearing facts + anything likely changed since cutoff (numbers, dates, prices,
versions, "current/latest"); SHOULD verify other web-supportable statements; EXEMPT common knowledge
and pure synthesis. Then run the same check, dispositioned inline:

```bash
bad verify-citations --report research/notes/final_report_<vault_tag>.md \
    --vault-tag <vault_tag> --json
```

- **Disposition by support score (OpenAI thresholds, §R5.3):** ACCEPT ≥0.75 keep · TIGHTEN ≥0.55
  narrow the claim to what the span supports (Edit) · FLAG ≥0.35 soften/hedge (Edit) · DROP-CITE
  <0.35 remove the `[N]`; if load-bearing, `bad fetch --tier-max 3` and re-cite · DROP-SENTENCE: a
  MUST-verify claim with no supporting span is struck.
- **Placement (Claude `citations_agent.md`, verbatim R5.1):** key facts only (not common knowledge),
  one citation per (source, sentence) placed AFTER the period, never mid-fragment.

Skip Tier-C re-fetch arbitration and the `--effort high` self-consistency vote (full-tier
only). This pass sits just upstream of the step-16.6 `bad uncited-gate` ship-block — backward
grounding (does the cited note support the sentence?) complementing the gate's forward check
(does every claim carry a cite at all?).

## Exit criterion

- `research/temp/citation-verify-actions.json` exists
- The `claim_anchors` table has `verified`/`verify_score` for every cited sentence
- No edits made to the report in this step (tool-lock holds)

## Next step

Return to the entry skill (`bad-research`). Invoke step 12:
`Skill(skill: "bad-research-12-critics")`.
