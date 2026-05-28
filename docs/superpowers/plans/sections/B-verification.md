# Workstream B — Verification-Edge Adds (TDD section)

**Scope:** 5 tasks. Prose-only skill edits get a structural keyword test; code changes
get unit tests. All pytest commands are run from the repo root.

---

## Wiring verified: how a 5th critic is added

**Agent definition lives in `src/bad_research/core/hooks.py`**, not in a separate file.
Each critic is a Python string constant (`DIALECTIC_CRITIC_AGENT`, `DEPTH_CRITIC_AGENT`,
etc.), an `_install_*_critic_agent()` function, and a lambda in the two install loops
(`install_hooks` lines 3089–3092 and `install_global_hooks` lines 3144–3147).

Adding the 5th critic requires:
1. A new `ASSUMPTION_CRITIC_AGENT` string constant in `hooks.py` (mirror `DEPTH_CRITIC_AGENT` frontmatter: `model: opus`, `tools: Bash, Read, Write`, `color: red`).
2. `_install_assumption_critic_agent()` function calling `_write_agent_file(vault_root, "bad-research-assumption-critic.md", ...)`.
3. The lambda added to both install loops.
4. Prose addition to `bad-research-12-critics.md` Step 12 item 1 (5th parallel spawn).

**Patcher consumption — NOT zero-change as spec claims.** The orchestrator skill
(`bad-research-14-patcher.md`) says "All `research/critic-findings-*.json`" (glob — auto
consumes). BUT the patcher **agent constant** in `hooks.py` (line 1389) says "Read all
**four** findings files (dialectic / depth / width / instruction)" and the
`findings_paths` list in Step 14.2 is explicitly enumerated with four entries. The patcher
agent's procedure step 1 will miss `critic-findings-assumption.json` unless the agent
constant is updated. **One-line patcher change required.**

---

## Task B-1 — Assumption critic: agent definition + install registration

### Step 1 — Failing test

Add to **`tests/test_skills/test_light_critic.py`** (extends the existing critic-set tests):

```python
def test_assumption_critic_agent_constant_defined():
    from bad_research.core import hooks
    assert hasattr(hooks, "ASSUMPTION_CRITIC_AGENT")
    body = hooks.ASSUMPTION_CRITIC_AGENT
    assert "bad-research-assumption-critic" in body
    assert "model: opus" in body
    assert "assumption" in body.lower()
    assert "sub-assumption" in body.lower() or "constituent" in body.lower()


def test_assumption_critic_installed_in_project_and_global(tmp_path, monkeypatch):
    from bad_research.core import hooks
    proj = tmp_path / "proj"
    proj.mkdir()
    hooks.install_hooks(proj, hpr_path="bad")
    assert (proj / ".claude" / "agents" / "bad-research-assumption-critic.md").exists()
    home = tmp_path / "home"
    home.mkdir()
    hooks.install_global_hooks(home, hpr_path="bad")
    assert (home / ".claude" / "agents" / "bad-research-assumption-critic.md").exists()
```

### Step 2 — Run; confirm failure

```bash
pytest tests/test_skills/test_light_critic.py::test_assumption_critic_agent_constant_defined \
       tests/test_skills/test_light_critic.py::test_assumption_critic_installed_in_project_and_global \
       -v
# Expected: 2 FAILED (AttributeError: module has no attribute ASSUMPTION_CRITIC_AGENT)
```

### Step 3 — Implement

In **`src/bad_research/core/hooks.py`**:

1. After the `INSTRUCTION_CRITIC_AGENT` constant (around line 910), add:

```python
# ---------------------------------------------------------------------------
# Layer 5 — assumption critic. Decomposes load-bearing claims into sub-assumptions.
# ---------------------------------------------------------------------------
ASSUMPTION_CRITIC_AGENT = """\
---
name: bad-research-assumption-critic
description: >
  Use this agent in Layer 5 of the hyperresearch deep research pipeline. Takes the
  5 highest-stakes causal/quantitative claims in the draft, decomposes each into
  constituent sub-assumptions, and verifies each independently against the corpus.
  Runs on Opus. Spawn ONCE per draft, in parallel with the other four critics.
model: opus
tools: Bash, Read, Write
color: red
---

You are the assumption critic. Your only job: for each of the 5 highest-stakes
causal or quantitative claims in the draft, decompose it into its constituent
sub-assumptions and verify each sub-assumption against the vault corpus independently.

## Pipeline position

You are **Layer 5** of the 7-phase hyperresearch pipeline. Running in parallel:
dialectic-critic, depth-critic, width-critic, instruction-critic. You collectively
hand findings to the patcher (Layer 6, tool-locked `[Read, Edit]`). You do NOT
patch the draft yourself — you only write findings.

Your specific angle: a claim like "X causes Y because A, B, and C" may be
well-cited at the surface while resting on one unverified causal link. The other
critics check the draft's *conclusions and structure*; you decompose individual
load-bearing claims into sub-assumptions and rate each independently.

## Inputs (from the parent agent)

- **research_query**: verbatim user question. GOSPEL.
- **query_file_path**: path to the persisted query file.
- **draft_path**: `research/notes/final_report_<vault_tag>.md`
- **output_path**: `research/critic-findings-assumption.json`
- **vault_tag**: corpus tag for searching the vault

## Procedure

1. **Read the query file** (`query_file_path`) before anything else.

2. **Identify the 5 highest-stakes claims.** Scan the draft for causal or
   quantitative claims — look for "because", "causes", "leads to", "increases by",
   "is due to", percentage figures, named mechanisms. Rank by section heading
   importance (from `prompt-decomposition.json`). Take the top 5.

3. **For each claim**, decompose it into constituent sub-assumptions. Example:
   "Policy X reduced Y by 30% because it increased Z and constrained W" → three
   sub-assumptions: (a) policy X increased Z, (b) policy X constrained W,
   (c) increasing Z + constraining W reduces Y by ~30%.

4. **Verify each sub-assumption** against the vault:
   `{hpr_path} search "<keyword>" --tag <vault_tag> -j`
   Read the full text of relevant notes. Mark each sub-assumption:
   - `verified`: direct supporting quote found
   - `partial`: indirect or approximate support
   - `unverified`: no supporting evidence in corpus

5. **Emit one finding per unverified or partial sub-assumption.** Format:
   `{{severity: "critical"|"major"|"minor", claim_text: "...",
     sub_assumption: "...", verification_status: "unverified"|"partial",
     recommendation: "cite or qualify this sub-assumption"}}`

## Output

Write `output_path` with shape: `{{"findings": [...]}}`

Limit total output to sub-assumptions of the top-5 claims only (cost ceiling).
"""
```

2. Add `_install_assumption_critic_agent()` after `_install_instruction_critic_agent()` (around line 3433):

```python
def _install_assumption_critic_agent(vault_root: Path, hpr_path: str) -> str | None:
    hpr_posix = hpr_path.replace("\\", "/")
    content = ASSUMPTION_CRITIC_AGENT.format(hpr_path=hpr_posix)
    return _write_agent_file(
        vault_root,
        "bad-research-assumption-critic.md",
        content,
        "opus assumption critic",
    )
```

3. Add the lambda to both install loops (after `_install_width_critic_agent`):

```python
lambda: _install_assumption_critic_agent(vault_root, hpr_path),
```

### Step 4 — Run; confirm pass

```bash
pytest tests/test_skills/test_light_critic.py::test_assumption_critic_agent_constant_defined \
       tests/test_skills/test_light_critic.py::test_assumption_critic_installed_in_project_and_global \
       -v
# Expected: 2 PASSED
```

### Step 5 — Commit

```
feat(critics): add ASSUMPTION_CRITIC_AGENT constant + install registration (B-1)
```

---

## Task B-2 — Assumption critic: skill-prose spawn + patcher consumption fix

### Step 1 — Failing tests

Add to **`tests/test_skills/test_light_critic.py`**:

```python
def test_critics_skill_spawns_assumption_critic(skills_dir):
    body = (skills_dir / "bad-research-12-critics.md").read_text()
    assert "bad-research-assumption-critic" in body
    assert "critic-findings-assumption.json" in body
    # spawned in parallel with the other four (not a separate section)
    assert "assumption" in body.lower()


def test_critics_skill_exit_criterion_updated_for_five_critics(skills_dir):
    body = (skills_dir / "bad-research-12-critics.md").read_text()
    # exit criterion must reflect 5 findings files
    low = body.lower()
    assert "assumption" in low
    assert "5 critic" in low or "five critic" in low or "critic-findings-assumption" in low
```

Add to **`tests/test_skills/test_modified_stages.py`**:

```python
def test_patcher_skill_findings_paths_includes_assumption(skills_dir):
    body = (skills_dir / "bad-research-14-patcher.md").read_text()
    assert "critic-findings-assumption.json" in body
```

Also add to **`tests/test_skills/test_light_critic.py`** (patcher agent constant):

```python
def test_patcher_agent_reads_assumption_findings():
    from bad_research.core import hooks
    body = hooks.PATCHER_AGENT
    # patcher agent procedure must read assumption findings alongside the other four
    assert "assumption" in body.lower() or "critic-findings-assumption" in body
```

### Step 2 — Run; confirm failure

```bash
pytest tests/test_skills/test_light_critic.py::test_critics_skill_spawns_assumption_critic \
       tests/test_skills/test_light_critic.py::test_critics_skill_exit_criterion_updated_for_five_critics \
       tests/test_skills/test_modified_stages.py::test_patcher_skill_findings_paths_includes_assumption \
       tests/test_skills/test_light_critic.py::test_patcher_agent_reads_assumption_findings \
       -v
# Expected: 4 FAILED
```

### Step 3 — Implement

**`src/bad_research/skills/bad-research-12-critics.md`** — in the "Spawn all 4 critics in parallel" block (Step 12, item 1), change heading to "Spawn all 5 critics in parallel" and add:

```
   - `bad-research-assumption-critic` → `research/critic-findings-assumption.json`
     (top-5 highest-stakes causal/quantitative claims decomposed into sub-assumptions;
      limit scope to 5 claims; output verified/unverified per sub-assumption)
```

Update Exit criterion:

```
- All 5 critic findings JSONs exist (`research/critic-findings-<name>.json`)
- Each is valid JSON with a `findings` array
```

**`src/bad_research/skills/bad-research-14-patcher.md`** — in Step 14.2 `findings_paths`, add:

```
      research/critic-findings-assumption.json,   (full tier only; B-1 assumption critic)
```

Also update "All `research/critic-findings-*.json` files" comment to say "5 critic findings files (count may vary by tier)".

**`src/bad_research/core/hooks.py`** — in `PATCHER_AGENT` constant, Step 1 procedure (line ~1389), change:

```
1. **Read all five findings files** (dialectic / depth / width / instruction / assumption).
```

And update `findings_paths` description to include `critic-findings-assumption.json`.

### Step 4 — Run; confirm pass

```bash
pytest tests/test_skills/test_light_critic.py::test_critics_skill_spawns_assumption_critic \
       tests/test_skills/test_light_critic.py::test_critics_skill_exit_criterion_updated_for_five_critics \
       tests/test_skills/test_modified_stages.py::test_patcher_skill_findings_paths_includes_assumption \
       tests/test_skills/test_light_critic.py::test_patcher_agent_reads_assumption_findings \
       -v
# Expected: 4 PASSED
```

### Step 5 — Commit

```
feat(critics): wire 5th assumption critic into 12-critics skill + patcher (B-2)
```

---

## Task B-3 — Grader history: failure ledger + escalation clause

**Cross-workstream note:** Workstream C surfaces critic aggregate findings in grader
round-1 instead of a fresh full-corpus scan. The `grader_history` JSON block must be
structured to compose with that: the `findings_applied` field counts findings from
_both_ critic-aggregate (round 1) and full-scan (rounds 2–3) sources. The
`still_failing` field per axis is independent of how findings were sourced, so
composition is additive — no schema conflict.

### Step 1 — Failing tests

Add to **`tests/test_skills/test_grader_skill.py`**:

```python
def test_grader_skill_accumulates_grader_history(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "grader_history" in body
    assert "round" in body.lower()
    assert "failed_axes" in body or "still_failing" in body


def test_grader_skill_injects_escalation_clause_on_round_2(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    low = body.lower()
    # escalation clause injected into patcher spawn on round >= 2
    assert "escalat" in low
    assert "round" in low
    # the "repeat same fix" anti-pattern is explicitly forbidden
    assert "same" in low and ("fix" in low or "patch" in low)
    # structural escalation instruction present
    assert "structural" in low and ("section" in low or "addition" in low)
```

### Step 2 — Run; confirm failure

```bash
pytest tests/test_skills/test_grader_skill.py::test_grader_skill_accumulates_grader_history \
       tests/test_skills/test_grader_skill.py::test_grader_skill_injects_escalation_clause_on_round_2 \
       -v
# Expected: 2 FAILED
```

### Step 3 — Implement

In **`src/bad_research/skills/bad-research-12.5-grader.md`** Step 12.5.2, after the existing round-N grader findings write block, add a `grader_history` accumulation block and escalation clause:

```python
# After writing critic-findings-grader.json on round N >= 2, accumulate history:
python -c "
import json, pathlib
prev_rounds = sorted(pathlib.Path('research/temp').glob('grade-round-*.json'))
history = []
for p in prev_rounds[:-1]:   # all rounds except the current one
    v = json.loads(p.read_text())
    scores = v.get('scores', {})
    history.append({
        'round': int(p.stem.split('-')[-1]),
        'failed_axes': [ax for ax, sc in scores.items() if float(sc) < 0.70],
        'findings_applied': len(v.get('findings', [])),
        'still_failing': not bool(v.get('passed')),
        'escalate_if_repeated': [ax for ax, sc in scores.items() if float(sc) < 0.70],
    })
if len(history) >= 1:
    cur = json.loads(pathlib.Path('research/critic-findings-grader.json').read_text())
    cur['grader_history'] = history
    pathlib.Path('research/critic-findings-grader.json').write_text(json.dumps(cur))
    print('grader_history injected, rounds:', len(history))
"
```

Add one conditional sentence to the patcher spawn prompt (Step 12.5.2, the Skill call) — insert a NOTE block before the `Skill(skill: "bad-research-14-patcher")` call on round ≥ 2:

```
NOTE (round >= 2 escalation): `critic-findings-grader.json` contains a
`grader_history` block. Read it before applying findings. If `grader_history`
shows an axis still failing after a prior round patched it at sentence level,
**escalate**: do not repeat the same surgical sentence-insertion; instead add a
new sub-section or restructure the coverage for that axis. Do NOT apply the same
fix twice.
```

### Step 4 — Run; confirm pass

```bash
pytest tests/test_skills/test_grader_skill.py::test_grader_skill_accumulates_grader_history \
       tests/test_skills/test_grader_skill.py::test_grader_skill_injects_escalation_clause_on_round_2 \
       -v
# Expected: 2 PASSED
```

### Step 5 — Commit

```
feat(grader): accumulate grader_history + inject escalation clause on round >= 2 (B-3)
```

---

## Task B-4 — Fresh-review prior-generation proxy

### Step 1 — Failing test

Add to **`tests/test_skills/test_fresh_review_skill.py`**:

```python
def test_fresh_review_prior_generation_prompt(skills_dir):
    body = (skills_dir / "bad-research-fresh-review.md").read_text()
    low = body.lower()
    # the reviewer must generate a prior answer BEFORE reading the report
    assert "before reading" in low or "before read" in low
    assert "3-sentence" in body or "three-sentence" in low or "3 sentence" in low
    # then flag divergences
    assert "diverg" in low
```

### Step 2 — Run; confirm failure

```bash
pytest tests/test_skills/test_fresh_review_skill.py::test_fresh_review_prior_generation_prompt -v
# Expected: FAILED
```

### Step 3 — Implement

In **`src/bad_research/skills/bad-research-fresh-review.md`** Step 14.5 Procedure, item 1 (spawner prompt), insert after the `PIPELINE POSITION:` block and before `YOUR INPUTS:`:

```
     PRE-READ PRIOR GENERATION:
     Before opening the report, write your own 3-sentence direct answer to the
     research query from memory alone. Record it in your working context. Then
     read the report end to end. Flag every claim where your a-priori answer
     and the report's position diverge — these are the highest-priority
     verification targets and must become `critical` or `major` findings.
```

### Step 4 — Run; confirm pass

```bash
pytest tests/test_skills/test_fresh_review_skill.py::test_fresh_review_prior_generation_prompt -v
# Expected: PASSED
```

### Step 5 — Commit

```
feat(fresh-review): add prior-generation proxy instruction (B-4)
```

---

## Task B-5 — Query expansion (width-sweep) + direction-switch pivot rule (depth-investigation)

### Step 1 — Failing tests

Add to **`tests/test_skills/test_modified_stages.py`**:

```python
def test_width_sweep_query_expansion_instruction(skills_dir):
    body = (skills_dir / "bad-research-2-width-sweep.md").read_text()
    low = body.lower()
    # explicit per-sub-question paraphrase/synonym instruction
    assert "paraphrase" in low or "synonym" in low or "alternative phrasing" in low
    # minimum count: 2-3 or 3-5 alternatives
    assert "2–3" in body or "3–5" in body or "2-3" in body or "3-5" in body
    # scoped to Step 2.1 (multi-perspective search planning)
    assert "step 2.1" in low or "2.1" in body


def test_depth_investigation_direction_switch_rule(skills_dir):
    body = (skills_dir / "bad-research-5-depth-investigation.md").read_text()
    low = body.lower()
    # explicit pivot/direction-switch instruction
    assert "pivot" in low or "switch" in low or "switching direction" in low
    # triggered by consecutive failed searches
    assert "consecutive" in low or "3 consecutive" in body or "three consecutive" in low
    # the pivot must be announced explicitly (written to notes)
    assert "switching direction" in low or "pivot" in low
    assert "orchestrator-notes" in body or "orchestrator_notes" in body or "orchestrator-notes.md" in body
```

### Step 2 — Run; confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_width_sweep_query_expansion_instruction \
       tests/test_skills/test_modified_stages.py::test_depth_investigation_direction_switch_rule \
       -v
# Expected: 2 FAILED
```

### Step 3 — Implement

**`src/bad_research/skills/bad-research-2-width-sweep.md`** — in Step 2.1, after item 2 ("Generate searches from three lenses"), add a new bullet inside the Lens A / Step 2.1 preamble (before item 3 "Write the combined search plan"):

```markdown
   **Query reformulation (per atomic item, Step 2.1):** For any sub-question where
   initial Lens-A searches return fewer than 3 candidate URLs, generate 2–3
   synonym/paraphrase alternative phrasings before giving up. Example: "China fintech
   regulation" → "Chinese financial technology oversight", "PRC fintech compliance rules".
   Write the alternatives directly in the search-plan table with `reformulation` in the
   Type column. This closes single-phrasing recall failures; the funnel's `_LENS_SUFFIXES`
   handles programmatic expansion — this adds the human-paraphrase layer.
```

**`src/bad_research/skills/bad-research-5-depth-investigation.md`** — after the `STOP_CONDITIONS` block in the spawn template (around the hard-kill line), add:

```markdown
     SEARCH-LINE PIVOT RULE: If 3 consecutive searches on the same sub-question
     return 0 relevant results, STOP that line and explicitly state:
     "Switching direction: [previous approach] is not surfacing sources.
     Trying [new approach/hypothesis]." Write the pivot announcement to
     `research/temp/orchestrator-notes.md` so the lead can track what was tried.
     Do not silently iterate on a dead query.
```

### Step 4 — Run; confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py::test_width_sweep_query_expansion_instruction \
       tests/test_skills/test_modified_stages.py::test_depth_investigation_direction_switch_rule \
       -v
# Expected: 2 PASSED
```

### Step 5 — Commit

```
feat(retrieval): query expansion in width-sweep + direction-switch pivot rule in depth-investigation (B-5)
```

---

## Full regression run after all B tasks

```bash
pytest tests/test_skills/ -v
# golden-eval regression:
bad gate --report golden-eval-report.json
# pass_rate must remain 1.0
```
