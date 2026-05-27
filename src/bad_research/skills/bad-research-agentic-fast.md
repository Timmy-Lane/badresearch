---
name: bad-research-agentic-fast
user-invocable: false
description: >
  The bounded-ReAct fast mode of Bad Research (agentic-fast route only) — a
  step-bounded (max_steps ≤ 10) planner→writer loop that produces a fast, cheap,
  per-sentence-cited answer, replacing the 16-step pipeline.
---

# Agentic-fast — bounded ReAct

**Tier gate:** Runs ONLY for the `agentic-fast` route. It does NOT run the
width-sweep funnel (`bad funnel-gather`) as a fixed step; it does a bounded
loop that *calls* the funnel / retrieval per iteration. No clarifier, no
decompose-time fan-out — fast by design.

**Goal:** answer a trivial, bounded, single-domain query in < 3 minutes and
$1–5 with grounded per-sentence citations. Terminate when the model judges
coverage complete OR the step cap is hit — whichever comes first.

## Recover state

Read:
- `research/query-<vault_tag>.md` — canonical query (GOSPEL)
- `research/prompt-decomposition.json` — confirm `route == "agentic-fast"`

If `route != "agentic-fast"`, STOP and return to the entry skill — you were
invoked by mistake.

## The loop (planner → writer split)

You are the **planner** (system A). Run a ReAct loop, persisting an auditable
`(thought, action, observation)` trace to `research/temp/react-trace.md`:

```
step = 0; calls = 0; deadline = now + 300s     # AGENTIC_FAST_TIMEOUT_S
while step < 10 and now < deadline:             # AGENTIC_FAST_MAX_STEPS
    step += 1
    THINK: write one paragraph to react-trace.md — what's still unknown, what to fetch.
    if you judge coverage complete: break        # model-judged stop
    ACT (one step = a LIST of queries, fanned out, NOT one search):
        bad funnel-gather "<query>" --mode light --vault-tag <tag> \
            --max-queries 6 --read-top-k 12 --json
      # the funnel fans out, dedups, ranks, reads (Tier 0→3), filters, chunks,
      # stores in vault, and returns top_chunks — you read ONLY top_chunks.
      calls += 1
    OBSERVE: read the returned top_chunks; rerank against the ORIGINAL query:
        bad retrieve "<original verbatim query>" --mode light --top-k 12 --json
      calls += 1
    append the (thought, action, observation) to react-trace.md
    if calls >= 15: break                        # AGENTIC_FAST_MAX_CALLS guard
```

**Hard guards (safety net):** never exceed 10 steps, 15 tool
calls, or 300 seconds. These are belt-and-suspenders on top of the
model-judged stop — a stuck loop must die.

**Math queries:** if the question needs computation over retrieved numbers,
use `execute_python` (Bash → a sandboxed `python -c`) in the ACT phase rather
than guessing — never compute in prose.

## Write (the writer split — system B)

When the loop ends, you become the **writer**. The writer sees the RANKED
top-chunks (the evidence), NOT the planner's raw reasoning trace. Write the
answer in ONE pass:
- Direct answer first; 500–2000 words (short response_format).
- Per-sentence single-index `[N]` citations: each index in its own bracket
  (`[1][2]`, never `[1,2]`), ≤3 per sentence, no space before the bracket.
- No `## References` section in the prose — the `[N]` resolves to the vault
  note out-of-band (the CLI/host renders the source list).
- Write to `research/notes/final_report_<vault_tag>.md`.

## Exit criterion

- `research/notes/final_report_<vault_tag>.md` exists, in the short range
- `research/temp/react-trace.md` has the full (thought, action, observation) trace
- Every non-trivial sentence carries a `[N]` resolving to a vault note

## Next step

Return to the entry skill (`bad-research`). Agentic-fast runs the light-tier
slim single critic before polish (E3 — one adversarial dialectic+instruction
pass, findings applied inline; no fan-out, no patcher): invoke
`Skill(skill: "bad-research-12-critics")` (its **Light-tier slim critic** section),
THEN `Skill(skill: "bad-research-15-polish")`, then the step-16 gate.
