# Workstream D — Efficiency + Workstream E1 — Eval-Harness Semantic Guard

**Pre-reading:**
- Spec §5 (D) + §5b (E1): `/docs/superpowers/specs/2026-05-29-bad-research-super-skill-design.md`
- Research backing: `docs/superpowers/research/round2-efficiency.md`, `round2-verification.md`
- Depends on C landing first (Step 6.5 orphan-tension-scan lives inside
  `bad-research-6-cross-locus-reconcile.md` after C-2; D-3 delegates it from there).

**Authoritative files touched:**
- `src/bad_research/calibrate/constants.py` — JUDGE_TIER (line 23)
- `src/bad_research/calibrate/golden.py` — `evaluate_corpus`, `GoldenCase.from_json`, `load_golden_corpus`
- `src/bad_research/cli/calibrate.py` — `calibrate()` typer func + `_run_gate()`
- `src/bad_research/skills/bad-research-1-decompose.md`
- `src/bad_research/skills/bad-research-6-cross-locus-reconcile.md` (post-C-2 contains Step 6.5)
- `src/bad_research/calibrate/golden/` — new fixture files
- `tests/test_calibrate/test_golden.py`
- `tests/test_calibrate/test_gate_cmd.py`
- `tests/test_calibrate/test_judge.py`
- `tests/test_skills/test_modified_stages.py`

---

## Task D-1 — `JUDGE_TIER "heavy" → "work"` in `calibrate/constants.py`

**Rationale:** `constants.py:23` reads `JUDGE_TIER = "heavy"  # Opus; Sonnet acceptable (dossier 09 §A4 table L223)`.
The code's own comment endorses the change. The judge emits categorical rails only (`pass/borderline/fail`);
no frontier reasoning is required. Saves ~$0.55/full run.

### Step 1 — Write failing test

Add to `tests/test_calibrate/test_judge.py`:

```python
def test_judge_tier_is_work():
    """D-1: JUDGE_TIER must be 'work' — the code comment endorses Sonnet for categorical rails."""
    from bad_research.calibrate.constants import JUDGE_TIER
    assert JUDGE_TIER == "work", (
        f"JUDGE_TIER is '{JUDGE_TIER}'; change constants.py:23 to 'work' "
        "(Sonnet acceptable per the code comment — saves ~$0.55/run)"
    )
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_calibrate/test_judge.py::test_judge_tier_is_work -x
```

Fails: `AssertionError: JUDGE_TIER is 'heavy'`.

### Step 3 — Implement

Edit `src/bad_research/calibrate/constants.py` line 23:

```python
# Before:
JUDGE_TIER = "heavy"  # Opus; Sonnet acceptable (dossier 09 §A4 table L223)
# After:
JUDGE_TIER = "work"   # Sonnet — categorical rails only (pass/borderline/fail); Opus acknowledged overkill (dossier 09 §A4 table L223)
```

No other code change: `LLMJudge` in `judge.py:144` reads `JUDGE_TIER` as its default `tier` field;
`quality/grader.py` imports `JUDGE_TIER` transitively through the judge. Both inherit the new value.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_calibrate/test_judge.py::test_judge_tier_is_work \
       tests/test_calibrate/ -x
```

All calibrate tests pass (including `test_llm_judge_single_call_and_parse` which checks
`stub_llm.call_count == 1` — tier value doesn't affect stub behavior).

### Step 5 — Commit

```bash
git add src/bad_research/calibrate/constants.py tests/test_calibrate/test_judge.py
git commit -m "perf(calibrate): demote JUDGE_TIER heavy→work (Sonnet sufficient for categorical rails)"
```

---

## Task D-2 — Delegate step-1 decompose to a work-tier subagent

**Rationale:** Step 1 (`bad-research-1-decompose.md`) converts the canonical query into structured
JSON. It requires good instruction-following and JSON production but zero frontier analytical
reasoning — running it orchestrator-inline costs full Opus rate unnecessarily. The fix is a spawn
instruction at the top of the step telling the orchestrator to delegate the JSON extraction to a
work-tier subagent and read back the artifact, matching the existing pattern from step-5
depth investigators.

**No Python code change.** This is a skill-prose change only: one `Task(…tier="work"…)` spawn block
added to `bad-research-1-decompose.md`. The test asserts the instruction is present in the skill body.

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_decompose_delegates_to_work_tier(skills_dir):
    """D-2: Step 1 must instruct the orchestrator to spawn a work-tier subagent for
    the JSON extraction, not run it inline at Opus cost."""
    body = (skills_dir / "bad-research-1-decompose.md").read_text()
    # The spawn instruction must explicitly reference work tier or Sonnet
    assert (
        'tier="work"' in body or "tier: work" in body or "work-tier subagent" in body.lower()
    ), "bad-research-1-decompose.md must instruct orchestrator to delegate to a work-tier subagent"
    # The delegation must name the output artifact to read back
    assert "prompt-decomposition.json" in body  # already present; guard against accidental removal
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_decompose_delegates_to_work_tier -x
```

Fails: `bad-research-1-decompose.md` contains no `tier="work"` or `work-tier subagent` phrase.

### Step 3 — Implement

Edit `src/bad_research/skills/bad-research-1-decompose.md`.

After the `## Procedure` heading and before the numbered steps, insert a delegation block:

```markdown
## Delegation

The orchestrator delegates the JSON extraction in this step to a **work-tier subagent** —
structured JSON production does not require frontier reasoning. Spawn:

```
Task(
  prompt: "Execute bad-research-1-decompose steps 1–5 exactly. Read research/query-<vault_tag>.md,
           produce research/prompt-decomposition.json, then stop.",
  tier: "work",
  tools_allowed: [Read, Write, Bash],
  stop_conditions: "research/prompt-decomposition.json written"
)
```

Then read `research/prompt-decomposition.json` back into orchestrator context before proceeding
to step 1.5.
```

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py::test_decompose_delegates_to_work_tier \
       tests/test_skills/test_modified_stages.py \
       tests/test_skills/test_delegation_contract.py -x
```

### Step 5 — Commit

```bash
git add src/bad_research/skills/bad-research-1-decompose.md \
        tests/test_skills/test_modified_stages.py
git commit -m "perf(skills): delegate step-1 decompose JSON extraction to work-tier subagent"
```

---

## Task D-3 — Delegate Step 6.5 orphan-tension-scan to a work-tier subagent

**Rationale:** After C-2, the orphan tension scan (formerly step 7) lives as `Step 6.5` inside
`bad-research-6-cross-locus-reconcile.md`. This is structured extraction of expert disagreements
from vault notes into `tensions.md` — deterministic-format work, no frontier reasoning.
Delegating to a Sonnet subagent follows the D-2 pattern established above.

**Depends on C-2 landing first** (the `Step 6.5` subsection must already exist in the reconcile skill).
Do not implement D-3 before C-2 is committed.

**No Python code change.** Skill-prose only.

### Step 1 — Write failing test

Add to `tests/test_skills/test_modified_stages.py`:

```python
def test_reconcile_step65_delegates_tension_scan_to_work_tier(skills_dir):
    """D-3: Step 6.5 (orphan tension scan, post-C-2 merge) must instruct the orchestrator
    to delegate the tensions extraction to a work-tier subagent (reference: C-2, D spec §5)."""
    body = (skills_dir / "bad-research-6-cross-locus-reconcile.md").read_text()
    assert "Step 6.5" in body, (
        "Step 6.5 must exist (C-2 must land before D-3)"
    )
    # Work-tier delegation instruction must be present inside or immediately after the 6.5 section
    step65_idx = body.index("Step 6.5")
    after_65 = body[step65_idx : step65_idx + 1200]
    assert (
        'tier="work"' in after_65 or "tier: work" in after_65 or "work-tier" in after_65.lower()
    ), "Step 6.5 must delegate the tension scan to a work-tier subagent"
    # tensions.md artifact must still be named (not silently dropped)
    assert "tensions.md" in body
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_skills/test_modified_stages.py::test_reconcile_step65_delegates_tension_scan_to_work_tier -x
```

Fails: either `Step 6.5` not yet present (C-2 not landed) or no work-tier delegation phrase.

### Step 3 — Implement

Edit `src/bad_research/skills/bad-research-6-cross-locus-reconcile.md` inside the `## Step 6.5`
section (added by C-2). After the section intro, insert:

```markdown
### Delegation

The orchestrator delegates this tension scan to a **work-tier subagent** — structured extraction
of expert disagreements is deterministic-format work requiring no frontier reasoning:

```
Task(
  prompt: "Execute Step 6.5: read all vault interim notes for vault_tag=<vault_tag>,
           extract orphan source tensions into research/tensions.md following the schema below,
           then stop.",
  tier: "work",
  tools_allowed: [Read, Write, Bash],
  stop_conditions: "research/tensions.md written"
)
```

Read `research/tensions.md` back into orchestrator context before proceeding to step 8.
```

### Step 4 — Run, confirm pass

```bash
pytest tests/test_skills/test_modified_stages.py::test_reconcile_step65_delegates_tension_scan_to_work_tier \
       tests/test_skills/test_modified_stages.py \
       tests/test_skills/test_delegation_contract.py -x
```

### Step 5 — Commit

```bash
git add src/bad_research/skills/bad-research-6-cross-locus-reconcile.md \
        tests/test_skills/test_modified_stages.py
git commit -m "perf(skills): delegate step-6.5 orphan tension scan to work-tier subagent (D-3)"
```

---

## Task D-4 — (OPTIONAL) Step-8 ∥ inline-digest overlap

**Status: DOCUMENTED OPPORTUNITY ONLY — do not implement in this workstream.**

The research (`round2-efficiency.md §3 Option D`) confirms that step 8 (corpus-critic) and the
evidence-digest work (now in step 10.0b after C-3) read the same corpus and write to different
artifacts with no read dependency on each other. Spawning step 8 as a subagent while the
orchestrator runs step 10.0b inline would save ~2–3 wall-clock minutes on a 90-minute run (~2–3%).

**Why skipping here:** the overlap requires step 8 to run as a spawned subagent (currently
orchestrator-inline), which is a larger skill-prose refactor than D-2/D-3 and depends on C-3
(step 9→10 merge) landing cleanly first. The wall-clock saving (~2%) is marginal on a 90-minute
run. Implement in a follow-up iteration after A+C+D are stable if wall-clock latency is measured
to be a user pain point.

**If later implementing:** add a test in `tests/test_skills/test_modified_stages.py` asserting that
`bad-research-8-corpus-critic.md` (or the entry-skill's step-8 spawn block) carries a
`tier="work"` spawn instruction, and that the step-10 prose no longer waits for step-8 sequentially.

---

## Task E1-1 — Add `LLMJudge` routing + `bad gate --llm` flag

**Rationale:** `RubricJudge` scores by content-word overlap and cannot catch cited-but-contradicting
synthesis or over-hedged completeness. `LLMJudge` already exists in `calibrate/judge.py:140-168`
with the correct categorical-rails interface. The gap is: no CLI flag selects it, and
`evaluate_corpus` / `_run_gate` always use the keyless `RubricJudge` default.
The fix is: add `--llm` to `bad calibrate --gate` and thread it through `_run_gate` → `evaluate_corpus`.

**Existing code:**
- `calibrate/judge.py:140` — `LLMJudge` fully implemented, correct `Judge` protocol, uses `JUDGE_TIER`.
- `cli/calibrate.py:43` — `gate: bool` option already present; `_run_gate()` at line 163 calls
  `evaluate_corpus(cases)` with no judge argument (defaults to `RubricJudge`).
- `calibrate/golden.py:267-278` — `evaluate_corpus(cases, *, judge=None)`: `None` → `RubricJudge()`.

**No float scores introduced.** `LLMJudge` returns `JudgeVerdict` built from `AxisRails` / `JudgeRail`
categorical values, exactly like `RubricJudge`. The `JudgeRail` enum (`judge.py:34`) and
`RAIL_CREDIT` map (`constants.py:21`) are unchanged.

### Step 1 — Write failing tests

Add to `tests/test_calibrate/test_gate_cmd.py`:

```python
def test_gate_llm_flag_routes_to_llm_judge(tmp_path, monkeypatch):
    """E1-1: --llm flag must route evaluate_corpus to LLMJudge, not RubricJudge."""
    from bad_research.calibrate import golden as golden_mod
    calls = []

    class TrackingJudge:
        def judge(self, query, report, corpus):
            calls.append("llm")
            from bad_research.calibrate.judge import AxisRails, JudgeRail, JudgeVerdict
            rails = AxisRails(
                factual=JudgeRail.PASS, citation=JudgeRail.PASS,
                completeness=JudgeRail.PASS, source_quality=JudgeRail.PASS,
                efficiency=JudgeRail.PASS,
            )
            return JudgeVerdict.from_rails(rails, rationale="tracking")

    monkeypatch.setattr(
        "bad_research.cli.calibrate._make_llm_judge",
        lambda: TrackingJudge(),
    )
    result = runner.invoke(app, ["calibrate", "--gate", "--llm", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(calls) > 0, "--llm flag must invoke LLMJudge path"


def test_gate_default_is_rubric_judge_not_llm(tmp_path, monkeypatch):
    """E1-1: default bad gate (no --llm) must not invoke LLMJudge."""
    from bad_research.calibrate import golden as golden_mod
    llm_calls = []

    monkeypatch.setattr(
        "bad_research.cli.calibrate._make_llm_judge",
        lambda: (_ for _ in ()).throw(AssertionError("LLMJudge must not be called without --llm")),
    )
    # patch is a sentinel; if _make_llm_judge is called without --llm the test fails
    result = runner.invoke(app, ["calibrate", "--gate", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_calibrate/test_gate_cmd.py::test_gate_llm_flag_routes_to_llm_judge \
       tests/test_calibrate/test_gate_cmd.py::test_gate_default_is_rubric_judge_not_llm -x
```

Both fail: `--llm` is not a recognized option.

### Step 3 — Implement

**A. Add `_make_llm_judge()` helper and `--llm` flag to `cli/calibrate.py`:**

1. Add `llm: bool = typer.Option(False, "--llm", help="Use LLMJudge over the full corpus (requires host model; slow).")` to the `calibrate()` signature alongside the existing `gate: bool` parameter.

2. Thread `llm=llm` into the `_run_gate(...)` call at line 65.

3. Add `*, llm: bool = False` to `_run_gate()` signature.

4. Inside `_run_gate()`, after `cases = load_golden_corpus(golden_dir)`, add:

```python
if llm:
    judge: Judge | None = _make_llm_judge()
else:
    judge = None  # evaluate_corpus defaults to RubricJudge
report = evaluate_corpus(cases, judge=judge)
```

5. Add the helper below `_run_gate`:

```python
def _make_llm_judge():
    """Construct an LLMJudge for the --llm gate path.
    Requires the host model (ANTHROPIC_API_KEY or Claude Code host)."""
    from bad_research.calibrate.judge import LLMJudge
    from bad_research.llm.base import get_llm_provider
    return LLMJudge(provider=get_llm_provider())
```

**B. Add `Judge` import at top of `cli/calibrate.py`** (lazy import inside the function body is fine
to avoid circular; already pattern-matched in the file's existing lazy-import style).

No changes to `calibrate/golden.py`, `calibrate/judge.py`, or any other module.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_calibrate/test_gate_cmd.py -x
```

All gate cmd tests pass including the two new ones and the existing keyless invariant test
(`test_gate_is_keyless` — no `--llm` flag → still keyless).

### Step 5 — Commit

```bash
git add src/bad_research/cli/calibrate.py \
        tests/test_calibrate/test_gate_cmd.py
git commit -m "feat(calibrate): add bad gate --llm flag routing to LLMJudge (E1-1)"
```

---

## Task E1-2 — Add `requires_llm: true` golden fixtures 09 and 10

**Rationale:** Two adversarial fixtures prove the lexical gap: a cited-but-contradicting report and
an over-hedged-but-technically-complete report. Both are marked `"requires_llm": true` so the
default `bad gate` (keyless) skips them. The default run's pass_rate=1.0 invariant is preserved.

**Fixture schema** (copy exactly from `01_causal_light.json` / `04_contested_argumentative.json`):

```json
{
  "id": "...",
  "query": "...",
  "report": "<markdown>",
  "corpus": [{"note_id": "...", "url": "https://...", "text": "..."}],
  "expected_behavior": ["...", "..."],
  "axes_floor": {"factual": "pass", "citation": "pass"},
  "requires_llm": true,
  "components": {}
}
```

`requires_llm: true` is a new field. `GoldenCase.from_json` (line 62–72 of `golden.py`) must be
updated to parse it; `evaluate_corpus` must skip cases where `requires_llm is True` and
`judge` is a `RubricJudge` (i.e., not the `--llm` path).

### Step 1 — Write failing tests

Add to `tests/test_calibrate/test_golden.py`:

```python
def test_default_lexical_run_skips_requires_llm_fixtures(tmp_path):
    """E1-2: fixtures marked requires_llm=true must be excluded from the keyless run."""
    from bad_research.calibrate.golden import GoldenCase, RubricJudge, evaluate_corpus

    llm_case = GoldenCase(
        id="99_requires_llm",
        query="Does X cause Y?",
        report="# Does X cause Y?\n\nX definitely causes Y [1].\n",
        corpus=[{"note_id": "1", "url": "https://a.edu", "text": "X may relate to Y."}],
        expected_behavior=["placeholder"],
        axes_floor={},
        components={},
        requires_llm=True,
    )
    normal_case = GoldenCase(
        id="00_normal",
        query="Is the sky blue?",
        report="# Is the sky blue?\n\nRayleigh scattering makes it blue [1].\n",
        corpus=[{"note_id": "1", "url": "https://a.edu", "text": "Rayleigh scattering makes the sky blue."}],
        expected_behavior=["names Rayleigh scattering"],
        axes_floor={"citation": "pass"},
        components={},
        requires_llm=False,
    )
    report = evaluate_corpus([llm_case, normal_case])
    # Only the normal case is scored; the llm case is skipped entirely
    assert report.total == 1, (
        f"expected 1 case (llm case skipped), got {report.total}"
    )
    assert report.cases[0].id == "00_normal"


def test_shipped_fixtures_09_and_10_exist_and_are_well_formed():
    """E1-2: the two requires_llm fixtures must be in the shipped golden/ dir."""
    from bad_research.calibrate.golden import GOLDEN_DIR, load_golden_corpus
    import json

    for name in ("09_cited_contradiction.json", "10_over_hedged_completeness.json"):
        fp = GOLDEN_DIR / name
        assert fp.exists(), f"Missing fixture: {name}"
        data = json.loads(fp.read_text())
        assert data.get("requires_llm") is True, f"{name} must have requires_llm: true"
        assert data.get("id")
        assert data.get("query")
        assert data.get("report")
        assert data.get("corpus")
        assert data.get("expected_behavior")


def test_seed_corpus_total_includes_llm_fixtures_in_raw_load():
    """After E1-2: raw load returns all 10 fixtures; evaluated (keyless) total is 8."""
    from bad_research.calibrate.golden import load_golden_corpus, evaluate_corpus
    all_cases = load_golden_corpus()
    assert len(all_cases) == 10, f"Expected 10 total fixtures (8 + 2 requires_llm), got {len(all_cases)}"
    report = evaluate_corpus(all_cases)
    assert report.total == 8, f"Keyless run must score only 8 (skip 2 requires_llm), got {report.total}"
    assert report.pass_rate == 1.0  # existing 8 still pass
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_calibrate/test_golden.py::test_default_lexical_run_skips_requires_llm_fixtures \
       tests/test_calibrate/test_golden.py::test_shipped_fixtures_09_and_10_exist_and_are_well_formed \
       tests/test_calibrate/test_golden.py::test_seed_corpus_total_includes_llm_fixtures_in_raw_load -x
```

Fails: `GoldenCase` has no `requires_llm` field; fixture files don't exist; `evaluate_corpus` doesn't skip.

### Step 3 — Implement

**A. Update `GoldenCase` in `calibrate/golden.py`:**

Add `requires_llm: bool = False` field to the `@dataclass` (after `components`).

Update `GoldenCase.from_json` to parse it:
```python
requires_llm=bool(data.get("requires_llm", False)),
```

**B. Update `evaluate_corpus` in `calibrate/golden.py`:**

At the top of the `for case in cases:` loop, add:

```python
# E1-2: skip requires_llm fixtures on the keyless RubricJudge path
if getattr(case, "requires_llm", False) and isinstance(j, RubricJudge):
    continue
```

This keeps `evaluate_corpus` correct when called with an `LLMJudge` (all cases scored) and when
called keyless (requires_llm cases skipped, total reflects only scored cases).

**C. Update `__all__` in `golden.py`** — no change needed (GoldenCase is already exported).

**D. Write fixture `src/bad_research/calibrate/golden/09_cited_contradiction.json`:**

```json
{
  "id": "09_cited_contradiction",
  "query": "Does regular sleep deprivation raise cardiovascular risk?",
  "report": "# Does regular sleep deprivation raise cardiovascular risk?\n\nContrary to popular concern, regular sleep deprivation has no demonstrated effect on cardiovascular risk according to the leading cohort studies [1]. The Whitehall II study found no significant association between sleep duration and major cardiac events [2].\n",
  "corpus": [
    {
      "note_id": "1",
      "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/sleep-cv-risk",
      "text": "A meta-analysis of 15 cohort studies found that short sleep duration (< 6 hours) is associated with a 20% increased risk of cardiovascular disease compared to 7–8 hours of sleep."
    },
    {
      "note_id": "2",
      "url": "https://pubmed.ncbi.nlm.nih.gov/whitehall-sleep",
      "text": "The Whitehall II prospective cohort study found that short sleep duration was significantly associated with increased risk of coronary heart disease and stroke over a 25-year follow-up."
    }
  ],
  "expected_behavior": [
    "must NOT invert the causal direction — both corpus sources establish elevated risk, not absence of risk",
    "the report's factual claim directly contradicts its cited sources",
    "LLMJudge must fail the factual axis"
  ],
  "axes_floor": {"factual": "pass", "citation": "pass"},
  "requires_llm": true,
  "components": {}
}
```

**E. Write fixture `src/bad_research/calibrate/golden/10_over_hedged_completeness.json`:**

```json
{
  "id": "10_over_hedged_completeness",
  "query": "What are the primary causes of the 2008 financial crisis?",
  "report": "# What are the primary causes of the 2008 financial crisis?\n\nThe 2008 financial crisis was a complex event [1]. Scholars have proposed various contributing factors, though the relative importance of each remains debated [2]. Some analysts point to mortgage markets, while others emphasize regulatory frameworks, and still others focus on systemic factors [1][2]. Ultimately, the causes are multifaceted and context-dependent, and any definitive account would require significantly more research than can be summarized here [1].\n",
  "corpus": [
    {
      "note_id": "1",
      "url": "https://www.federalreserve.gov/pubs/feds/2012/crisis-causes",
      "text": "The primary causes of the 2008 financial crisis include: (1) the collapse of the US subprime mortgage market and associated mortgage-backed securities, (2) excessive leverage at major financial institutions, (3) inadequate regulatory oversight of shadow banking, and (4) systemic contagion through interconnected derivatives exposure."
    },
    {
      "note_id": "2",
      "url": "https://www.brookings.edu/financial-crisis-retrospective",
      "text": "Economists broadly agree on four root causes: subprime lending expansion, securitization opacity, regulatory gaps in the shadow banking system, and the pro-cyclical nature of capital requirements under Basel II."
    }
  ],
  "expected_behavior": [
    "must name the specific causes from the corpus — subprime lending, leverage, regulatory failure, securitization",
    "the corpus contains a clear enumerated list of causes; the report's evasive hedging fails completeness",
    "LLMJudge must fail the completeness axis — the answer is technically present in citations but buried under evasion",
    "RubricJudge passes (content-word overlap is sufficient, hedging language not in _OVERCLAIM list)"
  ],
  "axes_floor": {"completeness": "pass"},
  "requires_llm": true,
  "components": {}
}
```

### Step 4 — Run, confirm pass

```bash
pytest tests/test_calibrate/test_golden.py -x
```

All golden tests pass including:
- `test_seed_corpus_total_includes_llm_fixtures_in_raw_load` — total=10, evaluated=8, pass_rate=1.0
- `test_corpus_eval_needs_zero_keys` — still passes (requires_llm cases are skipped, no LLM call)
- `test_golden_dir_ships_a_seed_corpus` — updated lower bound check: existing test asserts `6 <= len(cases) <= 100`; 10 is in range.

Also run the gate cmd tests to confirm the `--gate` default is unaffected:

```bash
pytest tests/test_calibrate/test_gate_cmd.py -x
```

### Step 5 — Commit

```bash
git add src/bad_research/calibrate/golden.py \
        src/bad_research/calibrate/golden/09_cited_contradiction.json \
        src/bad_research/calibrate/golden/10_over_hedged_completeness.json \
        tests/test_calibrate/test_golden.py
git commit -m "feat(calibrate): add requires_llm fixtures 09+10 and skip logic in evaluate_corpus (E1-2)"
```

---

## Task E1-3 — Prove the gap: RubricJudge passes, LLMJudge fails the two adversarial fixtures

**Rationale:** The design spec (§5b) requires that the two fixtures are NOT caught by `RubricJudge`
lexical scoring (proving the semantic gap) but ARE correctly failed by `LLMJudge`.
E1-3 provides that proof as executable tests — they are the regression net that guards A's
new semantic behavior from silently degrading in future code changes.

**Note on E1-3 vs E1-1/E1-2 ordering:** E1-3 tests reference the two fixtures written in E1-2 and
the `LLMJudge` path from E1-1. Implement E1-3 after both prior tasks pass.

### Step 1 — Write failing tests

Add to `tests/test_calibrate/test_golden.py`:

```python
def test_rubric_judge_passes_cited_contradiction_fixture():
    """E1-3 gap proof: RubricJudge must PASS 09_cited_contradiction (it cannot detect
    semantic inversion — content-word overlap is sufficient). If this test fails, the
    fixture is too obviously bad and needs to be re-written with better lexical overlap."""
    from bad_research.calibrate.golden import GOLDEN_DIR, GoldenCase, RubricJudge
    import json

    fp = GOLDEN_DIR / "09_cited_contradiction.json"
    case = GoldenCase.from_json(json.loads(fp.read_text()))
    verdict = RubricJudge().judge(case.query, case.report, case.corpus)
    assert verdict.passed, (
        "RubricJudge should PASS 09_cited_contradiction (lexical overlap is sufficient); "
        "if it fails, the fixture's report text does not overlap corpus vocabulary enough "
        "to prove the semantic gap — revise the fixture report."
    )


def test_rubric_judge_passes_over_hedged_completeness_fixture():
    """E1-3 gap proof: RubricJudge must PASS 10_over_hedged_completeness.
    The over-hedged report shares corpus vocabulary (completeness rail: body exists),
    so lexical scoring is blind to the evasion. This proves the gap."""
    from bad_research.calibrate.golden import GOLDEN_DIR, GoldenCase, RubricJudge
    import json

    fp = GOLDEN_DIR / "10_over_hedged_completeness.json"
    case = GoldenCase.from_json(json.loads(fp.read_text()))
    verdict = RubricJudge().judge(case.query, case.report, case.corpus)
    assert verdict.passed, (
        "RubricJudge should PASS 10_over_hedged_completeness (over-hedging is invisible "
        "to lexical overlap scoring). If it fails, fix the fixture text."
    )


def test_llm_judge_fails_cited_contradiction_fixture(stub_llm_fail_factual):
    """E1-3 semantic guard: LLMJudge must FAIL 09_cited_contradiction on the factual axis.
    Uses a stub that returns factual=fail to represent correct LLM behavior."""
    from bad_research.calibrate.golden import GOLDEN_DIR, GoldenCase
    from bad_research.calibrate.judge import LLMJudge
    import json

    fp = GOLDEN_DIR / "09_cited_contradiction.json"
    case = GoldenCase.from_json(json.loads(fp.read_text()))
    verdict = LLMJudge(provider=stub_llm_fail_factual).judge(case.query, case.report, case.corpus)
    # The LLM correctly identifies the factual inversion
    assert not verdict.passed, "LLMJudge must FAIL 09_cited_contradiction"
    from bad_research.calibrate.judge import JudgeRail
    assert verdict.rails.factual is JudgeRail.FAIL


def test_llm_judge_fails_over_hedged_completeness_fixture(stub_llm_fail_completeness):
    """E1-3 semantic guard: LLMJudge must FAIL 10_over_hedged_completeness on completeness."""
    from bad_research.calibrate.golden import GOLDEN_DIR, GoldenCase
    from bad_research.calibrate.judge import LLMJudge
    import json

    fp = GOLDEN_DIR / "10_over_hedged_completeness.json"
    case = GoldenCase.from_json(json.loads(fp.read_text()))
    verdict = LLMJudge(provider=stub_llm_fail_completeness).judge(case.query, case.report, case.corpus)
    assert not verdict.passed, "LLMJudge must FAIL 10_over_hedged_completeness"
    from bad_research.calibrate.judge import JudgeRail
    assert verdict.rails.completeness is JudgeRail.FAIL
```

Add two new fixtures to `tests/test_calibrate/conftest.py`:

```python
from tests.test_calibrate.conftest import StubLLM

@pytest.fixture
def stub_llm_fail_factual():
    """StubLLM that returns factual=fail (all others pass) — models LLMJudge correctly
    identifying a cited-but-contradicting claim."""
    return StubLLM(verdict={
        "factual": "fail",
        "citation": "pass",
        "completeness": "pass",
        "source_quality": "pass",
        "efficiency": "pass",
        "rationale": "report inverts the causal direction of its cited sources",
    })


@pytest.fixture
def stub_llm_fail_completeness():
    """StubLLM that returns completeness=fail — models LLMJudge detecting over-hedged evasion."""
    return StubLLM(verdict={
        "factual": "pass",
        "citation": "pass",
        "completeness": "fail",
        "source_quality": "pass",
        "efficiency": "pass",
        "rationale": "answer technically present but buried in hedge; corpus provides clear enumeration",
    })
```

### Step 2 — Run, confirm failure

```bash
pytest tests/test_calibrate/test_golden.py::test_rubric_judge_passes_cited_contradiction_fixture \
       tests/test_calibrate/test_golden.py::test_rubric_judge_passes_over_hedged_completeness_fixture \
       tests/test_calibrate/test_golden.py::test_llm_judge_fails_cited_contradiction_fixture \
       tests/test_calibrate/test_golden.py::test_llm_judge_fails_over_hedged_completeness_fixture -x
```

All four fail: fixture files not yet loaded correctly (E1-2 not yet committed) or conftest fixtures
`stub_llm_fail_factual` / `stub_llm_fail_completeness` not yet defined.

Once E1-1 and E1-2 are committed, only the conftest fixtures are missing — they fail with
`fixture 'stub_llm_fail_factual' not found`.

### Step 3 — Implement

1. Add the two stub fixtures to `tests/test_calibrate/conftest.py` as shown in Step 1 above.
2. No source code changes needed beyond what E1-1 and E1-2 already implement.
3. Verify that `09_cited_contradiction.json`'s report text shares vocabulary with the corpus
   (words like "sleep", "cardiovascular", "risk", "study", "cohort" appear in both) so that
   `RubricJudge` passes on word-overlap even though it inverts causation.
4. Verify that `10_over_hedged_completeness.json`'s report text shares vocabulary
   (words like "crisis", "mortgage", "regulatory", "financial", "causes" appear in both) so
   that `RubricJudge` passes on word-overlap while `LLMJudge` correctly fails completeness.

### Step 4 — Run, confirm pass

```bash
pytest tests/test_calibrate/test_golden.py tests/test_calibrate/test_gate_cmd.py \
       tests/test_calibrate/test_judge.py -x
```

Full calibrate test suite green. Final regression check:

```bash
pytest tests/test_calibrate/ tests/test_skills/test_modified_stages.py \
       tests/test_skills/test_delegation_contract.py -x
```

### Step 5 — Commit

```bash
git add tests/test_calibrate/conftest.py \
        tests/test_calibrate/test_golden.py
git commit -m "test(calibrate): E1-3 gap proofs — RubricJudge blind spot + LLMJudge semantic guard for fixtures 09+10"
```

---

## Regression Gate After D + E1

Run the full default (keyless) golden eval to confirm pass_rate stays 1.0:

```bash
pytest tests/test_calibrate/ tests/test_skills/ -x
```

The `--llm` path is exercised in CI only when `ANTHROPIC_API_KEY` is set; the default path remains
$0 and deterministic.
