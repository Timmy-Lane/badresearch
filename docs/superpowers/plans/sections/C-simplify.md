# Workstream C — Simplification (Stage Merges)

## Authoritative Post-Merge Stage Map (17 stages)

```
0.5  bad-research-0.5-clarify
1    bad-research-1-decompose
1.5  bad-research-query-router
1.6  bad-research-1.6-plan-gate
2    bad-research-2-width-sweep
4*   bad-research-4-loci-analysis          ← was steps 3+4; Step 4.0 preamble = contradiction-graph logic
5    bad-research-5-depth-investigation
6*   bad-research-6-cross-locus-reconcile  ← was steps 6+7; Step 6.5 subsection = orphan tension scan
8    bad-research-8-corpus-critic
10*  bad-research-10-triple-draft           ← was steps 9+10; Step 10.0b builds evidence digest inline
11   bad-research-11-synthesize
11.5 bad-research-11.5-citation-verifier
12   bad-research-12-critics
13   bad-research-13-gap-fetch
12.5 bad-research-12.5-grader              ← round-1 aggregates critic-findings-*.json; rounds 2-3 full scan
14   bad-research-14-patcher
14.5 bad-research-fresh-review
15   bad-research-15-polish
16   bad-research-16-readability-audit

Removed skill files: bad-research-3-contradiction-graph.md
                     bad-research-7-source-tensions.md
                     bad-research-9-evidence-digest.md
```

---

## Task C-1 — MERGE step 3 into step 4 (contradiction-graph → loci-analysis preamble)

**Artifacts preserved:** `research/temp/contradiction-graph.json`, `research/temp/consensus-claims.json`

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_step3_merged_into_step4_preamble(skills_dir):
    """After C-1: step 3 content lives as Step 4.0 inside bad-research-4-loci-analysis.md."""
    # step 3 must no longer exist as a standalone skill file
    assert not (skills_dir / "bad-research-3-contradiction-graph.md").exists(), \
        "bad-research-3-contradiction-graph.md must be removed after C-1 merge"
    # step 4 must contain the contradiction-graph procedure as a preamble
    body = (skills_dir / "bad-research-4-loci-analysis.md").read_text()
    assert "Step 4.0" in body, "loci-analysis must have a Step 4.0 preamble section"
    assert "contradiction-graph.json" in body
    assert "consensus-claims.json" in body
    assert "claim-pairing" in body.lower() or "pair contradiction" in body.lower()

def test_step3_removed_from_hooks_roster(skills_dir):
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-3-contradiction-graph" not in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-4-loci-analysis" in _BAD_RESEARCH_STEP_SKILLS
```

Add to `tests/test_skills/test_all_skills_valid.py` (existing `test_every_step_skill_in_roster_has_a_file` already enforces this once hooks.py is updated — no new test needed there).

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_step3_merged_into_step4_preamble \
       tests/test_skills/test_modified_stages.py::test_step3_removed_from_hooks_roster -x
```

Both fail: `bad-research-3-contradiction-graph.md` still exists; `_BAD_RESEARCH_STEP_SKILLS` still contains it.

### Step 3 — Implement

1. **Edit `src/bad_research/skills/bad-research-4-loci-analysis.md`:**
   - Insert a new `## Step 4.0 — Contradiction graph (preamble)` section immediately after the `## Recover state` block.
   - Copy the full procedure from `bad-research-3-contradiction-graph.md` §Procedure (steps 1–6 verbatim), renaming step references to "Step 4.0 substep N".
   - Preserve all claim-pairing logic, fight-cluster schema, consensus-claims logic, and both output paths (`contradiction-graph.json`, `consensus-claims.json`).
   - Add tier gate inline: `**Tier gate for Step 4.0:** SKIP if no claims-*.json files exist (fall through to Step 1 below).`
   - Preserve the existing step 4 `## Recover state` note that `contradiction-graph.json` is read as input — remove the redundancy (the preamble now writes what the body reads).

2. **Remove `src/bad_research/skills/bad-research-3-contradiction-graph.md`** (delete the file).

3. **Edit `src/bad_research/core/hooks.py`** — remove `"bad-research-3-contradiction-graph"` from `_BAD_RESEARCH_STEP_SKILLS` (line ~3654).

4. **Edit `src/bad_research/skills/bad-research.md`:**
   - In the stage table (row 3), replace the separate step-3 row with a note: `3→4* (merged) | bad-research-4-loci-analysis | Step 4.0 preamble: contradiction graph; Step 4.1+: loci analysts | full`.
   - In the `full` route sequence on line ~95, change `→ 3 → 4 →` to `→ 4* →`.
   - Remove the `3-contradiction-graph` Skill() call from the step sequence table (line ~43, ~115).

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py::test_step3_merged_into_step4_preamble \
       tests/test_skills/test_modified_stages.py::test_step3_removed_from_hooks_roster \
       tests/test_skills/test_all_skills_valid.py \
       tests/test_skills/test_entry_skill.py -x
```

### Step 5 — Commit

```
feat(C-1): merge step 3 contradiction-graph into step 4 loci-analysis preamble
```

---

## Task C-2 — MERGE step 7 into step 6 (source-tensions → cross-locus-reconcile Step 6.5)

**Artifacts preserved:** all tensions surfaced; output renamed from `comparisons.md` + `source-tensions.json` → single `research/temp/tensions.md` (richer, combined).

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_step7_merged_into_step6_subsection(skills_dir):
    """After C-2: step 7 content lives as Step 6.5 inside bad-research-6-cross-locus-reconcile.md."""
    assert not (skills_dir / "bad-research-7-source-tensions.md").exists(), \
        "bad-research-7-source-tensions.md must be removed after C-2 merge"
    body = (skills_dir / "bad-research-6-cross-locus-reconcile.md").read_text()
    assert "Step 6.5" in body, "reconcile skill must contain a Step 6.5 orphan-scan subsection"
    assert "tensions.md" in body, "merged output artifact must be tensions.md"
    assert "orphan" in body.lower(), "orphan tension scan procedure must be present"
    # old separate artifacts must no longer be the exit criterion
    assert "source-tensions.json" not in body or "tensions.md" in body

def test_step7_removed_from_hooks_roster(skills_dir):
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-7-source-tensions" not in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-6-cross-locus-reconcile" in _BAD_RESEARCH_STEP_SKILLS

def test_step10_reads_tensions_md_not_source_tensions_json(skills_dir):
    body = (skills_dir / "bad-research-10-triple-draft.md").read_text()
    assert "tensions.md" in body, "step 10 must read the merged tensions.md artifact"
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_step7_merged_into_step6_subsection \
       tests/test_skills/test_modified_stages.py::test_step7_removed_from_hooks_roster \
       tests/test_skills/test_modified_stages.py::test_step10_reads_tensions_md_not_source_tensions_json -x
```

### Step 3 — Implement

1. **Edit `src/bad_research/skills/bad-research-6-cross-locus-reconcile.md`:**
   - Rename the output artifact from `research/comparisons.md` to `research/temp/tensions.md` throughout.
   - Append a `## Step 6.5 — Orphan tension scan` section before the exit criterion. Copy the full procedure from `bad-research-7-source-tensions.md` §Procedure steps 2–5 verbatim (the orphan-scan pass over 8–12 source bodies), adapted: "After writing the cross-locus tensions above, scan the top 8–12 source bodies for orphan tensions (tensions that slipped past loci analysis). Merge findings into `research/temp/tensions.md`, combining: (a) cross-locus tensions from the reconciliation above, (b) orphan tensions from this scan."
   - Preserve the full `source-tensions.json` schema inside `tensions.md` as inline JSON blocks per tension (each tension entry retains `side_a`, `side_b`, `resolution`, `origin`, `decision_relevance` fields).
   - Update the exit criterion: `research/temp/tensions.md` exists with 3–7 tensions (cross-locus + orphan).
   - Update `## Next step` to point to step 8 (was step 7 → step 8, now step 6 → step 8 directly).

2. **Remove `src/bad_research/skills/bad-research-7-source-tensions.md`** (delete the file).

3. **Edit `src/bad_research/core/hooks.py`** — remove `"bad-research-7-source-tensions"` from `_BAD_RESEARCH_STEP_SKILLS`.

4. **Edit `src/bad_research/skills/bad-research-10-triple-draft.md`:**
   - In the `## Recover state` block, change `research/temp/source-tensions.json (full tier) — expert disagreements` → `research/temp/tensions.md (full tier) — cross-locus + orphan expert disagreements`.

5. **Edit `src/bad_research/skills/bad-research.md`:**
   - Merge row 7 into row 6 in the stage table.
   - In the `full` route sequence, change `→ 6 → 7 → 8 →` to `→ 6* → 8 →`.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py \
       tests/test_skills/test_all_skills_valid.py \
       tests/test_skills/test_entry_skill.py -x
```

### Step 5 — Commit

```
feat(C-2): merge step 7 source-tensions into step 6 reconcile as Step 6.5 orphan scan
```

---

## Task C-3 — CUT step 9 into step 10.0b (evidence-digest built inline)

**Artifacts preserved:** `research/temp/evidence-digest.md` still written; `research/temp/reflections.md` retained as recovery checkpoint.

**Cross-workstream note (Workstream A):** Workstream A adds `line_start`/`line_end` fields to the synthesis evidence layer (spec §2, layer 3: `synthesis-evidence.md` built at step 11.4b). After this C-3 merge, the evidence-digest-building code now lives inside `bad-research-10-triple-draft.md` step 10.0b. The Workstream A implementer must carry `line_start`/`line_end` through to that inline location (converted from `char_start`/`char_end` via `char_span_to_line_range`) — do NOT implement here, only note the dependency.

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_step9_merged_inline_into_step10(skills_dir):
    """After C-3: step 9 no longer exists; evidence-digest procedure is in step 10.0b."""
    assert not (skills_dir / "bad-research-9-evidence-digest.md").exists(), \
        "bad-research-9-evidence-digest.md must be removed after C-3 merge"
    body = (skills_dir / "bad-research-10-triple-draft.md").read_text()
    assert "evidence-digest.md" in body, "step 10 must build evidence-digest.md inline"
    assert "10.0b" in body or "Step 10.0b" in body, "inline digest build must be Step 10.0b"
    # the 80-120 claim cap and quoted_support discipline must survive
    assert "80" in body and "120" in body
    assert "quoted_support" in body

def test_step9_removed_from_hooks_roster(skills_dir):
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-9-evidence-digest" not in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-10-triple-draft" in _BAD_RESEARCH_STEP_SKILLS

def test_step12_5_grader_still_reads_evidence_digest(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "evidence-digest.md" in body, "grader must still reference evidence-digest.md artifact"
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_step9_merged_inline_into_step10 \
       tests/test_skills/test_modified_stages.py::test_step9_removed_from_hooks_roster \
       tests/test_skills/test_modified_stages.py::test_step12_5_grader_still_reads_evidence_digest -x
```

### Step 3 — Implement

1. **Edit `src/bad_research/skills/bad-research-10-triple-draft.md`:**
   - In `## Step 10.0b`, after the three existing distilled-memory substeps (plan, batch-read, spans-survive), add `## Step 10.0b — Part 2: Build evidence digest (inline)`. Copy the full procedure from `bad-research-9-evidence-digest.md` §Procedure steps 1–5 verbatim.
   - Add: `Write research/temp/evidence-digest.md now (before spawning draft-orchestrators). This replaces the former step 9 invocation.`
   - Preserve the 80–120 claim cap, the filter/rank criteria (confidence high OR empirical/statistical), the group-by-atomic-item structure, and the `quoted_support` verbatim block format.
   - Add A-layer annotation comment: `# NOTE (Workstream A): when A lands, carry line_start/line_end per chunk here (converted from char_start/char_end via char_span_to_line_range).`
   - Update the `## Recover state` block: remove the line `research/temp/evidence-digest.md` from "Read these inputs" (it's now built in this step, not read).

2. **Remove `src/bad_research/skills/bad-research-9-evidence-digest.md`** (delete the file).

3. **Edit `src/bad_research/core/hooks.py`** — remove `"bad-research-9-evidence-digest"` from `_BAD_RESEARCH_STEP_SKILLS`.

4. **Edit `src/bad_research/skills/bad-research.md`:**
   - Merge row 9 into row 10 in the stage table.
   - In the `full` route sequence, change `→ 8 → 9 → 10 →` to `→ 8 → 10* →`.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py \
       tests/test_skills/test_all_skills_valid.py \
       tests/test_skills/test_entry_skill.py -x
```

### Step 5 — Commit

```
feat(C-3): cut step 9 evidence-digest as separate stage; build inline in step 10.0b
```

---

## Task C-4 — Grader round-1 aggregates critic-findings-*.json (P3)

**Preserved:** convergence loop (≤3 rounds), 0.70 axis floor, patch-not-regenerate, `grader-log.json` audit trail. Rounds 2–3 remain full-corpus scans.

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_grader_round1_aggregates_critic_findings(skills_dir):
    """After C-4: grader round 1 scores from critic-findings-*.json, not a fresh corpus scan."""
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    low = body.lower()
    # round 1 uses existing critic findings
    assert "round 1" in low or "round-1" in low or "first round" in low
    assert "critic-findings" in body, "round 1 must reference critic-findings-*.json"
    assert "aggregate" in low or "aggregat" in low, "round 1 must aggregate, not rescan"
    # rounds 2-3 remain full scans
    assert "round 2" in low or "round-2" in low or "second round" in low
    assert "full" in low and ("scan" in low or "corpus" in low), \
        "rounds 2-3 must still perform full corpus scan"
    # convergence loop and floor preserved
    assert "0.70" in body or "0.7" in body
    assert "MAX_GRADER_REVISIONS" in body or "3" in body
    assert "grader-log.json" in body
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_grader_round1_aggregates_critic_findings -x
```

### Step 3 — Implement

Edit `src/bad_research/skills/bad-research-12.5-grader.md`:

- In `## Step 12.5.1 — Build the corpus JSON for the judge`, add a prefacing note:

  > **Round 1 shortcut:** if `research/critic-findings-*.json` files exist (i.e., step 12 ran), skip the full corpus JSON build for round 1. Instead, aggregate critic findings: read all `critic-findings-*.json` files, collect their `findings` arrays, and ask the judge to score the five axes against those findings rather than independently scanning the corpus. This reduces round-1 cost from a full Opus-tier corpus scan (~$3–5) to a $0.50 verdict-aggregation.
  >
  > **For rounds 2 and 3 only:** run the full corpus JSON build as specified below, because the first patch may introduce new issues not in the original critic findings.

- Update `## Step 12.5.2 — The grader loop` to add a branch at the top of the loop body:

  ```
  if revisions == 0 and glob("research/critic-findings-*.json"):
      # Round 1: aggregate existing critic findings into a single findings list.
      # Ask the judge: "Given these critic findings, score the report on the 5 axes."
      aggregate_findings = [f for path in glob("research/critic-findings-*.json")
                            for f in json.load(open(path)).get("findings", [])]
      verdict = grade_from_findings(aggregate_findings)  # fast path
  else:
      verdict = bad grade-report --report ... --corpus research/temp/grader-corpus.json --json
  ```

  (This is prose procedure for the orchestrator LLM; not literal Python. The judge prompt in the round-1 path is: "These are the critic findings from steps 12a–12d. Score the report on the 5 quality axes (factual, completeness, source_quality, efficiency, readability). You are aggregating, not independently scanning.")

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py::test_grader_round1_aggregates_critic_findings \
       tests/test_skills/test_grader_skill.py -x 2>/dev/null || \
pytest tests/test_skills/test_modified_stages.py::test_grader_round1_aggregates_critic_findings -x
```

### Step 5 — Commit

```
feat(C-4): grader round 1 aggregates critic-findings instead of fresh corpus scan
```

---

## Task C-5 — Operator surface: remove `--reasoning-effort` alias; confirm `--interactive` auto-default

### Step 1 — Write failing test

Add to `tests/test_cli/test_cli_subcommands.py` (and update the existing test at line 193):

```python
def test_run_cmd_has_only_effort_flag_not_reasoning_effort_alias():
    """After C-5: --reasoning-effort alias removed; only --effort is canonical."""
    from bad_research.cli.research import app
    from typer.testing import CliRunner
    r = CliRunner().invoke(app, ["run", "--help"])
    assert "--effort" in r.stdout, "--effort flag must be present"
    assert "--reasoning-effort" not in r.stdout, \
        "--reasoning-effort alias must be removed; use --effort only"

def test_funnel_gather_cmd_has_only_effort_not_reasoning_effort_alias():
    from bad_research.cli.research import app
    from typer.testing import CliRunner
    r = CliRunner().invoke(app, ["funnel-gather", "--help"])
    assert "--effort" in r.stdout
    assert "--reasoning-effort" not in r.stdout
```

Also update the existing test at `tests/test_cli/test_cli_subcommands.py:193`:
```python
# OLD: assert "--effort" in res.stdout or "--reasoning-effort" in res.stdout
# NEW:
assert "--effort" in res.stdout
assert "--reasoning-effort" not in res.stdout
```

And `tests/test_skills/test_delegation_contract.py:44`:
```python
# OLD: assert "--reasoning-effort" in body or "--effort" in body
# NEW:
assert "--effort" in body
```

And `tests/test_cli/test_keyless_rewire.py:91`:
```python
# OLD: assert "reasoning_effort" in sig.parameters
# The parameter name in the function signature can stay `effort` (Python ident);
# the Typer option string "--reasoning-effort" is what we remove.
# Update this test to check the Typer CLI string, not the Python parameter name.
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_cli/test_cli_subcommands.py::test_run_cmd_has_only_effort_flag_not_reasoning_effort_alias \
       tests/test_cli/test_cli_subcommands.py::test_funnel_gather_cmd_has_only_effort_not_reasoning_effort_alias -x
```

### Step 3 — Implement

1. **Edit `src/bad_research/cli/research.py`:**
   - At line 188: change `typer.Option(None, "--reasoning-effort", "--effort")` → `typer.Option(None, "--effort")`. (Remove the `"--reasoning-effort"` alias string.)
   - At line 342–343: same change for the `verify-citations` subcommand.
   - Rename the Python parameter from `reasoning_effort` to `effort` (or leave it as-is — the alias removal is the functional change; the Python name is internal). If renaming, update all downstream uses of the variable name in the function body.

2. **Edit `src/bad_research/skills/bad-research.md`:**
   - At line ~126: change `The \`--reasoning-effort\` flag (alias \`--effort\`)` → `The \`--effort\` flag`.
   - Everywhere `--reasoning-effort` appears in the skill prose, replace with `--effort`.

3. **Confirm `--interactive` auto-default (read-only verification):** check that `plan_gate_fires()` in `src/bad_research/skills/router.py` already defaults `interactive=False` and fires only when the CLI context is interactive. Add a one-line comment in `bad-research.md` if not already documented: `--interactive is auto-detected from CLI context; plan_gate_fires() returns True only in interactive non-auto runs.`

### Step 4 — Run, confirm pass

```bash
pytest tests/test_cli/ tests/test_skills/test_delegation_contract.py -x
```

### Step 5 — Commit

```
feat(C-5): remove --reasoning-effort alias; --effort is the single canonical flag
```

---

## Task C-6 — Update structural tests to assert 17-stage roster

This task ensures the `_BAD_RESEARCH_STEP_SKILLS` roster in `hooks.py` and all stage-count assertions match the 17-stage post-merge map. C-1 through C-5 each update the roster piecemeal; this task adds an explicit count guard.

### Step 1 — Write failing test

Add to `tests/test_skills/test_all_skills_valid.py`:

```python
def test_step_skill_roster_is_exactly_17_full_tier_stages():
    """Post-merge: the full-tier stage roster must contain exactly 17 invocable stages
    (excludes bad-research-agentic-fast which is its own route, not a full-tier step)."""
    from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS
    full_tier_steps = [s for s in _BAD_RESEARCH_STEP_SKILLS
                       if s != "bad-research-agentic-fast"]
    removed = {
        "bad-research-3-contradiction-graph",
        "bad-research-7-source-tensions",
        "bad-research-9-evidence-digest",
    }
    for name in removed:
        assert name not in full_tier_steps, f"{name} must be removed (C-1/C-2/C-3)"
    # 21 original full-tier steps - 3 removed + agentic-fast already excluded = 17
    assert len(full_tier_steps) == 17, \
        f"Expected 17 full-tier stages, got {len(full_tier_steps)}: {full_tier_steps}"
```

### Step 2 — Run, confirm failure (before C-1/C-2/C-3)

```bash
pytest tests/test_skills/test_all_skills_valid.py::test_step_skill_roster_is_exactly_17_full_tier_stages -x
```

### Step 3 — Implement

No new code — this test passes once C-1, C-2, and C-3 have updated `hooks.py`. Run after those tasks complete.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/ tests/test_cli/ -x
```

### Step 5 — Commit

```
test(C-6): add 17-stage roster guard; all C-workstream structural tests green
```

---

## Regression gate (run after all C tasks)

```bash
pytest tests/test_skills/ tests/test_cli/ tests/test_pipeline/ -x
bad gate  # golden eval pass_rate must stay 1.0 on the default lexical run
```
