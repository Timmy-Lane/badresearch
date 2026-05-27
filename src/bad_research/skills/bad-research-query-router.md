---
name: bad-research-query-router
description: >
  Step 1.5 of the Bad Research pipeline — classifies the decomposition into a
  route (agentic-fast / light / full) and writes it to
  research/prompt-decomposition.json. Invoked in order by the bad-research router.
---

# Step 1.5 — Query router

**Tier gate:** Runs for ALL runs (it IS the tier/mode decision). The router
never down-routes a query that step 1 marked `full` for a stated reason —
contested topics, time_periods, and argumentative formats always route `full`.

**Goal:** route trivial/single-domain queries to the cheap bounded ReAct
fast-mode, mid-size structured queries to `light`, and complex/contested
queries to the full 16-step pipeline. The signal is Bad Research's OWN
Step-1 decomposition — no new classifier.

## Recover state

Read:
- `research/prompt-decomposition.json` — sub_questions, entities, response_format,
  time_periods, contradiction_terms, domains, pipeline_tier
- `research/scaffold.md` — vault_tag

## Procedure

1. Run the deterministic router over the decomposition:
   ```bash
   bad route --decomposition research/prompt-decomposition.json --json
   ```
   It applies this fixed decision tree (mirrors `router.py::classify_route`):
   - **agentic-fast** if atomic_items ≤ 2 AND no contradiction terms AND no
     time_periods AND response_format == "short" AND single domain
   - **light** elif response_format == "structured" OR atomic_items 3–6
   - **full** else (multi-domain, contested, argumentative, time_periods, ≥7 items)

   The command prints `{"route": "agentic-fast"|"light"|"full", "reason": "...", "applied": false}`.

2. **Honor the existing tier.** If step 1 set `pipeline_tier: "full"` for a
   stated reason (time_periods present, argumentative, contested), the router
   MUST NOT down-route below `full`. The router can only refine `light` ↔
   `agentic-fast` and up-route to `full`; never silently demote a `full`.

3. Write the chosen route back into the decomposition:
   ```bash
   bad route --decomposition research/prompt-decomposition.json --apply --json
   ```
   This adds a top-level `"route"` field to `research/prompt-decomposition.json`.

4. Record a one-line rationale (the CLI's `reason` field) in `research/scaffold.md`
   under a `## Route rationale` subsection.

## Exit criterion

- `research/prompt-decomposition.json` has a `"route"` field ∈ {agentic-fast, light, full}
- A route never demotes a justified `full`
- `research/scaffold.md` has a `## Route rationale` subsection

## Next step

Return to the entry skill (`bad-research`). Sequence by route:
- **agentic-fast** → `Skill(skill: "bad-research-agentic-fast")` (then straight to step 15 polish)
- **light** → `Skill(skill: "bad-research-2-width-sweep")` (light path)
- **full** → `Skill(skill: "bad-research-2-width-sweep")` (full path)
