---
name: bad-research-12.5-grader
user-invocable: false
description: >
  Step 12.5 of the Bad Research pipeline (full tier only) — the in-pipeline
  grader loop (judge → patch → re-judge, ≤3 rounds) that scores the report on 5
  quality axes and feeds failing-axis defects to the patcher (runs AFTER step 13
  despite its number).
---

# Step 12.5 — Grader loop (judge → patch → re-judge)

**Tier gate:** FULL tier ONLY. SKIP entirely for `light` and `agentic-fast` —
their quality contract is the forward binding + the deterministic uncited gate; a
grader loop on a $1–15 fast query is the overkill we explicitly reject. Run only
when the route in `research/prompt-decomposition.json` is `full`.

**Goal:** raise the report's quality on the four non-citation axes (factual,
completeness, source_quality, efficiency) by feeding the judge's defect findings
to the patcher and re-grading, capped at 3 rounds. Patch, never regenerate.

---

## Recover state

Read these inputs:
- `research/scaffold.md` — vault_tag, route
- `research/prompt-decomposition.json` — confirm `route == "full"`; read
  `required_section_headings` + atomic items (the judge maps completeness misses
  to these)
- `research/notes/final_report_<vault_tag>.md` — the report (already citation-
  verified at 11.5, critic-patched once at 12/14)
- `research/temp/evidence-digest.md` — the corpus the report had access to
- `research/query-<vault_tag>.md` — canonical research query

If `route != "full"`, write nothing and return to the entry skill immediately —
this step does not run.

---

## Step 12.5.1 — Build the corpus JSON for the judge

**Round 1 shortcut (C-4):** if `research/critic-findings-*.json` files exist
(i.e., step 12 ran), SKIP the full corpus JSON build for **round 1**. Instead,
**aggregate** the critic findings: read all `research/critic-findings-*.json`
files, collect their `findings` arrays into a single list, and ask the judge to
score the five axes against those findings rather than independently re-scanning
the corpus. This drops round-1 cost from a full Opus-tier corpus scan (~$3–5) to
a ~$0.50 verdict-aggregation — the 4 critics in step 12 already did the corpus
read, so round 1 is just a verdict over their findings, not a fresh scan.

**For rounds 2 and 3 only:** run the full corpus JSON build specified below,
because the first patch may introduce new issues that are NOT in the original
critic findings, so the later rounds need a full corpus scan to catch them.

The grader needs the evidence as a JSON list of `{note_id, url, text}`. Convert
the evidence-digest into that shape (one entry per cited note):

```bash
PYTHONIOENCODING=utf-8 $HPR search "" --tag <vault_tag> --json \
  | python -c "
import sys, json
d = json.load(sys.stdin)
rows = [{'note_id': r.get('id',''), 'url': r.get('url',''), 'text': (r.get('body') or r.get('snippet') or '')[:1200]}
        for r in d.get('data',{}).get('results',[])]
open('research/temp/grader-corpus.json','w').write(json.dumps(rows))
print(f'corpus rows: {len(rows)}')
"
```

---

## Step 12.5.2 — The grader loop (host-run, cap = MAX_GRADER_REVISIONS = 3)

`MAX_GRADER_REVISIONS = 3` (NOT Claude's 20 — we PATCH not REGENERATE, so each
round is a small surgical Edit and convergence is far faster). The loop is:

```
revisions = 0
while revisions < MAX_GRADER_REVISIONS:   # 3
    if revisions == 0 and glob("research/critic-findings-*.json"):
        # Round 1 (C-4): aggregate existing critic findings — no fresh corpus scan.
        # Collect every findings entry from steps 12a–12d, then ask the judge to
        # score the 5 axes against that aggregate, not by re-reading the corpus.
        aggregate_findings = [f for path in glob("research/critic-findings-*.json")
                              for f in json.load(open(path)).get("findings", [])]
        verdict = grade_from_findings(aggregate_findings)   # fast verdict-aggregation path
    else:
        # Rounds 2-3: full corpus scan (patches may add NEW issues not in critic findings).
        verdict = bad grade-report --report research/notes/final_report_<vault_tag>.md \
                    --corpus research/temp/grader-corpus.json --json
    #   -> {passed, scores{5 axes}, overall, findings:[{failure_mode,severity,location,recommendation}]}
    if verdict.passed:  break             # every axis >= 0.70 AND mean >= 0.75
    # write the failing-axis findings as a patcher-shaped findings file:
    write verdict.findings -> research/critic-findings-grader.json  (shape: {"findings":[...]})
    # run the patcher (step 14) over the grader findings (surgical Edits only):
    Skill(skill: "bad-research-14-patcher")   # the patcher reads critic-findings-grader.json too
    revisions += 1
# PASS or cap reached -> proceed
```

This is prose procedure for the orchestrator LLM, not literal Python. The
**round-1 judge prompt** for the aggregate path is: *"These are the critic
findings from steps 12a–12d. Score the report on the 5 quality axes (factual,
completeness, source_quality, efficiency, readability). You are aggregating
those findings into a verdict, NOT independently scanning the corpus."* Round 2
and round 3 fall through to the full `bad grade-report` corpus scan as before.

Concretely, each round:

1. Run the grader.
   - **Round 1 (revisions == 0) — aggregate, do not rescan:** if
     `research/critic-findings-*.json` exist, collect every entry from their
     `findings` arrays into one aggregate list and have the judge score the 5
     axes against that aggregate (the verdict-aggregation fast path). Write the
     verdict to `research/temp/grade-round-1.json` in the same
     `{passed, scores, overall, findings}` shape the full grader emits.
   - **Rounds 2–3 (revisions >= 1) — full corpus scan:** run the full grader
     over the rebuilt corpus JSON, because the prior patch may have introduced
     new issues the critic findings never saw:
   ```bash
   bad grade-report --report research/notes/final_report_<vault_tag>.md \
       --corpus research/temp/grader-corpus.json --json > research/temp/grade-round-<N>.json
   ```
2. Parse `passed`. If `true`, the loop is done — record it in
   `research/temp/orchestrator-notes.md` and proceed to "Exit criterion."
3. If `false`, extract the `findings` array and write the grader findings file:
   ```bash
   python -c "
   import json, pathlib
   v = json.loads(pathlib.Path('research/temp/grade-round-<N>.json').read_text())
   pathlib.Path('research/critic-findings-grader.json').write_text(
       json.dumps({'findings': v.get('findings', [])}))
   print('grader findings:', len(v.get('findings', [])))
   "
   ```
4. Re-judge after patching: re-run the patcher (`Skill(skill: "bad-research-14-patcher")`).
   The patcher already globs `research/critic-findings-*.json`, so it picks up
   `critic-findings-grader.json` automatically and applies the grader's surgical
   Edits; the next loop iteration re-judges (re-grades) the patched report.
5. Increment the round counter in your TodoWrite note and loop.

**Track the loop counter in `research/temp/orchestrator-notes.md`** (it survives
compaction): write a line `grader-loop round <N>: passed=<bool> overall=<x>` each
round. The cap of 3 is the cost ceiling — never run a 4th round.

**Never emit bare text while the patcher Task is in flight** — append to
`research/temp/orchestrator-notes.md` instead.

---

## Step 12.5.3 — Convergence note

When the loop exits (PASS or cap reached), write `research/grader-log.json`:

```bash
python -c "
import json, pathlib
rounds = sorted(pathlib.Path('research/temp').glob('grade-round-*.json'))
log = {'rounds': len(rounds), 'final_passed': False, 'overall': None}
if rounds:
    v = json.loads(rounds[-1].read_text())
    log['final_passed'] = bool(v.get('passed'))
    log['overall'] = v.get('overall')
pathlib.Path('research/grader-log.json').write_text(json.dumps(log))
print(log)
"
```

If the cap was reached without a PASS, that is acceptable — the report still ships
(the deterministic uncited gate at step 16 is the hard ship-block, not the grader).
Record the non-PASS in the log for the audit trail; do NOT loop a 4th time.

---

## Exit criterion

- `research/grader-log.json` exists with `rounds` set and `final_passed` recorded.
- The grader loop ran ≤ MAX_GRADER_REVISIONS (3) rounds.
- `research/notes/final_report_<vault_tag>.md` reflects any grader-driven patches.
- For a `light` / `agentic-fast` route: this step was skipped (no `grader-log.json`).

---

## Next step

Return to the entry skill (`bad-research`). The patcher's final convergence (step
14) is complete; invoke step 14.5:

```
Skill(skill: "bad-research-fresh-review")
```
