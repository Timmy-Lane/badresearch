# Bad Research — Ultrafast Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third operator-facing route, `ultrafast` — a keyless, autonomous, 5–15 min commercial-Deep-Research-grade middle tier between `fast` and `full`.

**Architecture:** A new orchestration skill (`bad-research-ultrafast.md`) wires existing keyless parts at a middle budget: plan (internal, no gate) → K≤6 parallel `bad-research-fetcher` researchers → leader-only sectioned synthesis → slim citation-grounding → one slim critic → polish → uncited-gate. Selection is explicit-only via a `--ultrafast` flag on `bad route` (or an explicit "ultrafast mode" NL request the orchestrator honors). `classify_route` is never touched, so the golden eval corpus and auto-routing are unchanged.

**Tech Stack:** Python 3.12, Typer CLI, pytest, Claude Code skill files (Markdown). Spec: `docs/superpowers/specs/2026-05-30-bad-research-ultrafast-mode-design.md`.

---

## File Structure

**Modify:**
- `src/bad_research/skills/routing_constants.py` — add the `ULTRAFAST_*` constants block + an `"ultrafast"` key in `FETCHER_TOOLCALL_CAP`.
- `src/bad_research/skills/router.py` — extend the `Route` literal to include `"ultrafast"` (`classify_route` logic UNCHANGED — never auto-emits it).
- `src/bad_research/cli/research.py` — add the `--ultrafast` option to `route_cmd`, make the three force-flags mutually exclusive, and set an override `reason`.
- `src/bad_research/core/hooks.py` — add `"bad-research-ultrafast"` to the `_BAD_RESEARCH_STEP_SKILLS` install roster (mandatory: the installer **prunes** any skill dir not in this list).
- `src/bad_research/skills/bad-research.md` — entry skill: route-table row, half-step roster row, route-mapping bullet, a selection note, clarifier-skip + plan-gate-skip wiring, and the `FETCHER_TOOLCALL_CAP` prose mention.
- `src/bad_research/skills/bad-research-query-router.md` — document the `--ultrafast` passthrough + route the next step to `bad-research-ultrafast`.

**Create:**
- `src/bad_research/skills/bad-research-ultrafast.md` — the new orchestration skill.
- `tests/test_skills/test_ultrafast_skill.py` — structural tests for the new skill + the entry/query-router wiring (mirrors `test_fast_skill.py`).

**Modify (tests):**
- `tests/test_skills/test_router_effort.py:10` — update the frozen `FETCHER_TOOLCALL_CAP` assertion; add an `ULTRAFAST_*` constants test.
- `tests/test_cli/test_cli_subcommands.py` — add the `--ultrafast` override + three-way mutual-exclusivity tests.
- `tests/test_skills/test_router.py` — add a guard test that `classify_route` never auto-emits `ultrafast`.
- `tests/test_install/test_step_list.py` — bump the roster count 19→20 + assert `bad-research-ultrafast` membership.

**Deliberately NOT touched** (scope boundary — documented in spec §8):
- `src/bad_research/pipeline.py` — its `Route = Literal["fast","full"]` and `mode = "light" if route == "fast" else "full"` are the **headless calibrate path**, which routes via `classify_route` (never emits ultrafast) and has no `--ultrafast` flag. Ultrafast can never reach it. Leaving it alone keeps the change surgical.
- `classify_route` / `EFFORT_MAP` / the golden eval corpus.

---

### Task 1: `ULTRAFAST_*` constants + fetcher cap key

**Files:**
- Modify: `src/bad_research/skills/routing_constants.py:24` (after `FAST_SUBRESEARCHER_K`) and `:163` (`FETCHER_TOOLCALL_CAP`)
- Test: `tests/test_skills/test_router_effort.py:10`

- [ ] **Step 1: Update the frozen cap assertion + add the constants test**

In `tests/test_skills/test_router_effort.py`, change line 10 from:

```python
    assert R.FETCHER_TOOLCALL_CAP == {"light": 10, "full": 20}
```

to:

```python
    assert R.FETCHER_TOOLCALL_CAP == {"light": 10, "ultrafast": 15, "full": 20}
```

Then append this new test to the end of the file:

```python
def test_ultrafast_loop_constants_present_and_between_fast_and_full():
    # The ultrafast middle tier: caps sit strictly between FAST_* and the full-tier caps.
    assert R.ULTRAFAST_MAX_SUBQUESTIONS == 8
    assert R.ULTRAFAST_SUBRESEARCHER_K == 6
    assert R.ULTRAFAST_MIN_SOURCES_PER_SUBQ == 4
    assert R.ULTRAFAST_FETCHER_TIMEOUT_S == 360
    assert R.ULTRAFAST_RESERVE_SYNTH_FRAC == 0.30
    assert R.ULTRAFAST_TIMEOUT_S == 900
    assert R.FAST_SUBRESEARCHER_K < R.ULTRAFAST_SUBRESEARCHER_K
    assert R.FAST_MIN_SOURCES_PER_SUBQ < R.ULTRAFAST_MIN_SOURCES_PER_SUBQ
    assert (R.FETCHER_TOOLCALL_CAP["light"]
            < R.FETCHER_TOOLCALL_CAP["ultrafast"]
            < R.FETCHER_TOOLCALL_CAP["full"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_skills/test_router_effort.py -v`
Expected: FAIL — `test_grader_and_cap_constants_present_and_frozen` (cap mismatch) and `test_ultrafast_loop_constants_present_and_between_fast_and_full` (`AttributeError: module ... has no attribute 'ULTRAFAST_MAX_SUBQUESTIONS'`).

- [ ] **Step 3: Add the constants**

In `src/bad_research/skills/routing_constants.py`, insert this block immediately after `FAST_SUBRESEARCHER_K = 3` (line 24, the end of the fast breadth section):

```python

# ---- Ultrafast-route constants (keyless commercial-DR middle tier) ----
# Sits between FAST_* and the full-tier caps: plan -> K parallel researchers ->
# leader-only sectioned synthesis. Parallel fetchers => wall-clock ~= one wave
# (~5-6 min) + synthesis/grounding (~4-6 min) = the 5-15 min target. Tunable;
# no control flow depends on the exact values (the skill prose reads them).
ULTRAFAST_MAX_SUBQUESTIONS     = 8     # report sections / parallel researcher streams (fast=3)
ULTRAFAST_SUBRESEARCHER_K      = 6     # parallel bad-research-fetcher cap (fast FAST_SUBRESEARCHER_K=3)
ULTRAFAST_MIN_SOURCES_PER_SUBQ = 4     # distinct domains to mark a sub-question green (fast=3)
ULTRAFAST_FETCHER_TIMEOUT_S    = 360   # per-researcher soft deadline (FETCHER_TIMEOUT_S default=300)
ULTRAFAST_RESERVE_SYNTH_FRAC   = 0.30  # budget reserved for the longer synthesis (FAST_RESERVE_SYNTH_FRAC=0.25)
ULTRAFAST_TIMEOUT_S            = 900    # wall-clock safety net, 15 min (FAST_TIMEOUT_S=600)
```

Then change line 163 from:

```python
FETCHER_TOOLCALL_CAP = {"light": 10, "full": 20}  # tool calls per fetcher
```

to:

```python
FETCHER_TOOLCALL_CAP = {"light": 10, "ultrafast": 15, "full": 20}  # tool calls per fetcher
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_skills/test_router_effort.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/routing_constants.py tests/test_skills/test_router_effort.py
git commit -m "feat(ultrafast): ULTRAFAST_* loop constants + fetcher cap key"
```

---

### Task 2: `Route` literal + `--ultrafast` override on `bad route`

**Files:**
- Modify: `src/bad_research/skills/router.py:34`
- Modify: `src/bad_research/cli/research.py:23-84` (`route_cmd`)
- Test: `tests/test_cli/test_cli_subcommands.py`, `tests/test_skills/test_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli/test_cli_subcommands.py`:

```python
def test_route_ultrafast_flag_overrides(tmp_path):
    # A decomposition the router would call "full" (multi-domain), forced to ultrafast.
    decomp = tmp_path / "decomp.json"
    decomp.write_text(json.dumps({
        "sub_questions": ["a", "b"], "entities": [], "time_periods": [],
        "response_format": "structured", "contradiction_terms": [],
        "domains": ["a", "b", "c"],
    }))
    result = runner.invoke(
        app, ["route", "--decomposition", str(decomp), "--ultrafast", "--apply", "--json"]
    )
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["route"] == "ultrafast"
    assert "ultrafast" in out["reason"]
    assert json.loads(decomp.read_text())["route"] == "ultrafast"


def test_route_ultrafast_mutually_exclusive_with_fast_and_full(tmp_path):
    decomp = tmp_path / "decomp.json"
    decomp.write_text(json.dumps({"sub_questions": ["a"], "entities": [], "domains": ["x"],
                                  "response_format": "short"}))
    r1 = runner.invoke(app, ["route", "--decomposition", str(decomp), "--ultrafast", "--fast"])
    assert r1.exit_code != 0
    r2 = runner.invoke(app, ["route", "--decomposition", str(decomp), "--ultrafast", "--full"])
    assert r2.exit_code != 0
```

Append to `tests/test_skills/test_router.py`:

```python
def test_classify_route_never_auto_emits_ultrafast():
    # ultrafast is an explicit-only override (--ultrafast / "ultrafast mode"); the
    # auto-classifier only ever returns fast/full, so the golden corpus is unaffected.
    cases = [
        _decomp(sub_questions=["what is the capital of France"], response_format="short"),
        _decomp(sub_questions=["q1", "q2", "q3"], domains=["a", "b", "c"],
                response_format="argumentative", contradiction_terms=["x"]),
    ]
    for d in cases:
        assert classify_route(d) in ("fast", "full")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli/test_cli_subcommands.py::test_route_ultrafast_flag_overrides tests/test_cli/test_cli_subcommands.py::test_route_ultrafast_mutually_exclusive_with_fast_and_full tests/test_skills/test_router.py::test_classify_route_never_auto_emits_ultrafast -v`
Expected: the two CLI tests FAIL (no `--ultrafast` option → `route` stays `full`/exit 0); the guard test PASSES already (it documents intent — keep it).

- [ ] **Step 3: Extend the `Route` literal**

In `src/bad_research/skills/router.py`, change line 34 from:

```python
Route = Literal["fast", "full"]
```

to:

```python
Route = Literal["fast", "full", "ultrafast"]
```

- [ ] **Step 4: Add the `--ultrafast` option + three-way exclusivity + override reason**

In `src/bad_research/cli/research.py`, in `route_cmd`, add the option right after the `full` option (line 30):

```python
    ultrafast: bool = typer.Option(
        False, "--ultrafast",
        help="Force the ultrafast route (commercial-DR middle tier; override auto).",
    ),
```

Then replace the existing override block (lines 56–62):

```python
    route = classify_route(decomp)
    if fast and full:
        raise typer.BadParameter("--fast and --full are mutually exclusive")
    if fast:
        route = "fast"
    elif full:
        route = "full"
```

with:

```python
    route = classify_route(decomp)
    if sum([fast, full, ultrafast]) > 1:
        raise typer.BadParameter("--fast, --full, and --ultrafast are mutually exclusive")
    if fast:
        route, reason = "fast", "fast: forced by --fast override"
    elif full:
        route, reason = "full", "full: forced by --full override"
    elif ultrafast:
        route, reason = "ultrafast", "ultrafast: forced by --ultrafast override (commercial-DR middle tier)"
    else:
        reason = route_reason(decomp)
```

Then change the `reason` field in the `out` dict (line 73) from:

```python
        "reason": route_reason(decomp),
```

to:

```python
        "reason": reason,
```

(Note: this gives `--fast`/`--full` an explicit override reason too. Safe — `test_route_apply_idempotent_and_reason_present` only asserts `out["reason"]` is truthy, never its text.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_cli/test_cli_subcommands.py tests/test_skills/test_router.py -v`
Expected: PASS (all, including the pre-existing route tests).

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/skills/router.py src/bad_research/cli/research.py tests/test_cli/test_cli_subcommands.py tests/test_skills/test_router.py
git commit -m "feat(ultrafast): --ultrafast route override on 'bad route' + Route literal"
```

---

### Task 3: The `bad-research-ultrafast.md` orchestration skill

**Files:**
- Create: `src/bad_research/skills/bad-research-ultrafast.md`
- Create: `tests/test_skills/test_ultrafast_skill.py`

- [ ] **Step 1: Write the failing structural tests**

Create `tests/test_skills/test_ultrafast_skill.py`:

```python
from tests.test_skills.validate import validate_skill


def test_ultrafast_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-ultrafast.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_ultrafast_is_lead_plus_parallel_researchers(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "ULTRAFAST_SUBRESEARCHER_K" in body
    assert "ULTRAFAST_MIN_SOURCES_PER_SUBQ" in body
    assert "bad-research-fetcher" in body            # the parallel sub-researcher
    assert "seven-piece" in body.lower() or "seven-field" in body.lower()
    assert "parallel" in body.lower()
    assert "leader-only" in body.lower() or "only writer" in body.lower()
    assert "[N]" in body                             # per-sentence single-index cites


def test_ultrafast_is_autonomous_and_bounded(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "autonomous" in body.lower()
    assert "ULTRAFAST_TIMEOUT_S" in body             # 15-min wall-clock net
    assert "ultrafast" in body.lower()               # the route gate


def test_ultrafast_runs_slim_grounding_before_gate(skills_dir):
    body = (skills_dir / "bad-research-ultrafast.md").read_text()
    assert "verify-citations" in body
    assert "uncited" in body.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_skills/test_ultrafast_skill.py -v`
Expected: FAIL — `assert p.exists()` is False (file not yet created).

- [ ] **Step 3: Create the skill file**

Create `src/bad_research/skills/bad-research-ultrafast.md` with exactly this content:

````markdown
---
name: bad-research-ultrafast
user-invocable: false
description: >
  The commercial-DR middle tier of Bad Research (ultrafast route only) — an
  autonomous plan → K parallel researchers → leader-only sectioned synthesis that
  produces a long, fully-cited report in 5–15 minutes, replacing the 16-step
  pipeline. Keyless; stacks the best pattern from Perplexity / Gemini / Grok /
  OpenAI / Claude Deep Research.
---

# Ultrafast — autonomous lead + parallel researchers (commercial-DR middle tier)

**Tier gate:** Runs ONLY for the `ultrafast` route. It is fully **autonomous** — no
clarifier (0.5) and no plan-gate (1.6) precede it; the entry skill skips both. It
does NOT run the width-sweep funnel as a fixed step; the lead spawns parallel
sub-researchers that each *call* retrieval.

**Goal:** answer a moderately broad query at commercial-Deep-Research grade in a
**5–15 minute** target — a research plan, a wide parallel multi-source browse, and
ONE long sectioned report with per-sentence citations. Deeper than `fast` (a single
shallow loop), far cheaper than `full` (no contradiction graph, loci, depth
investigation, triple-draft, 5-critic fan-out, grader loop, or fresh-review).

## Recover state

Read:
- `research/query-<vault_tag>.md` — canonical query (GOSPEL)
- `research/prompt-decomposition.json` — confirm `route == "ultrafast"`; read the
  `sub_questions` (capped at ULTRAFAST_MAX_SUBQUESTIONS = 8) and the `scope_brief`

If `route != "ultrafast"`, STOP and return to the entry skill — you were invoked by
mistake.

## The pipeline (PLAN → BROWSE → SYNTH)

You are the **lead** and the **only writer**. Maintain, across the whole run, a
per-sub-question coverage **checklist** (each sub-question → the set of distinct
supporting domains seen so far) plus cumulative `seen_domains` / `seen_urls` sets. A
sub-question is GREEN once it has ULTRAFAST_MIN_SOURCES_PER_SUBQ (4) distinct domains.

### 1. PLAN (internal — no gate; Gemini DR plan run autonomously)

The decomposition's `sub_questions` ARE the report's sections. Order them by
importance (Claude breadth-first ordering). Do NOT pause for approval — ultrafast is
autonomous. Write the ordered section plan to `research/temp/ultrafast-plan.md`.

### 2. BROWSE (wide parallel multi-source — Claude lead + parallel subagents)

Spawn `K = min(n_sub_questions, ULTRAFAST_SUBRESEARCHER_K = 6)` parallel
`bad-research-fetcher` sub-researchers, ONE per sub-question, importance-ordered.
Each is a bounded agentic browse loop (Perplexity/OpenAI pattern):
`FETCHER_TOOLCALL_CAP["ultrafast"]` (15) tool calls, ULTRAFAST_FETCHER_TIMEOUT_S
(360s) soft deadline, chasing 3–8 primary sources via citation chains.
Sub-researchers return **claims + sources JSON, never prose** (Grok leader-only
seam). Use the **seven-piece subagent spawn contract** from the entry skill —
`research_query` (verbatim) / `pipeline_position` / `inputs` / `objective` /
`output_shape` (the `claims-*.json` shape) / `tools_allowed`
(`["web_search","fetch_url","execute_python"]`) / `stop_conditions` (halt when
ULTRAFAST_MIN_SOURCES_PER_SUBQ distinct domains found OR the tool-call cap is hit OR
ULTRAFAST_FETCHER_TIMEOUT_S elapses).

Gather all waves with a per-wave deadline = ULTRAFAST_FETCHER_TIMEOUT_S; proceed with
returned results if a wave exceeds it. After the first wave, if any sub-question is
still below the green gate, spawn ONE optional gap-fill wave targeting only the weak
sub-questions (never re-spawn green ones). The whole BROWSE stage is bounded by
ULTRAFAST_TIMEOUT_S (900s wall-clock net).

Math sub-claims: the fetchers use `execute_python`, never compute in prose.

### 3. SYNTH (leader-only terminal synthesis — Grok seam + Gemini/OpenAI report)

When BROWSE ends you become the **writer**. Reserve ULTRAFAST_RESERVE_SYNTH_FRAC
(30%) of budget for this. Three boundaries (same discipline as `fast`):

1. **Writer context boundary (Perplexity):** synthesize from `(original_query,
   dedup'd evidence, the researchers' returned claims)` only — never raw browse
   traces. Once writing starts, do NOT fan out again (Grok terminal-synthesis seam).
2. **Word governor (Claude copyright cap; OpenAI `[wordlim]`):** ≤25 words verbatim
   from any single source, ≤1 quote per source.
3. **Partial-answer-better-than-none (Perplexity):** if a wave stalled, still write
   the best grounded report from what was gathered — flag the thin sub-questions
   rather than refusing.

**Realism:** when the answer estimates software/technical effort, assume an
agentic-coding world — hours-to-days, never weeks or months — and omit calendar
estimates unless the query asks for one.

Write the report in ONE pass to `research/notes/final_report_<vault_tag>.md`:
- A direct lead answer, then **one section per sub-question** (importance-ordered),
  **tables over bullet lists** where the data is comparative.
- Length **1500–4000 words**, scaling with breadth.
- Per-sentence single-index `[N]` citations: each index in its own bracket
  (`[1][2]`, never `[1,2]`), ≤3 per sentence, no space before the bracket.
- No `## References` section — the `[N]` resolves to the vault note out-of-band.

## Exit criterion

- `research/notes/final_report_<vault_tag>.md` exists, 1500–4000 words, sectioned
- `research/temp/ultrafast-plan.md` has the ordered section plan
- Every non-trivial sentence carries a `[N]` resolving to a vault note (the slim
  citation-grounding pass + the step-16 `bad uncited-gate` enforce this)

## Next step

Return to the entry skill (`bad-research`). After the writer, sequence the same slim
tail as the fast route:

1. **Slim citation grounding** — `Skill(skill: "bad-research-11.5-citation-verifier")`
   (its **Slim mode (fast route)** section): backward-ground the cited sentences with
   `bad verify-citations`, applying ACCEPT/TIGHTEN/FLAG/DROP-CITE dispositions INLINE
   (Read+Edit, no patcher).
2. **Slim single critic** — `Skill(skill: "bad-research-12-critics")` (its **Light-tier
   slim critic** section): one adversarial dialectic+instruction pass, applied inline;
   no fan-out, no patcher.
3. **Polish** — `Skill(skill: "bad-research-15-polish")`.
4. Then the step-16 gate (`bad uncited-gate`).
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_skills/test_ultrafast_skill.py -v`
Expected: PASS (all four). If `test_ultrafast_skill_valid` fails on `validate_skill`, the frontmatter `name:` must equal the filename stem `bad-research-ultrafast` and any `Skill(skill: "X")` reference must name a real skill — both already satisfied above.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-ultrafast.md tests/test_skills/test_ultrafast_skill.py
git commit -m "feat(ultrafast): the bad-research-ultrafast orchestration skill"
```

---

### Task 4: Register the skill + wire the entry skill & query-router

**Files:**
- Modify: `src/bad_research/core/hooks.py:3750` (`_BAD_RESEARCH_STEP_SKILLS`)
- Modify: `src/bad_research/skills/bad-research.md` (route table + roster row + bullet + selection note + skip wiring + cap prose)
- Modify: `src/bad_research/skills/bad-research-query-router.md` (passthrough + next-step)
- Test: `tests/test_install/test_step_list.py`, `tests/test_skills/test_ultrafast_skill.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_install/test_step_list.py`, add to `test_step_list_has_new_stages` (after the `assert "bad-research-fast" in s` line):

```python
    assert "bad-research-ultrafast" in s
```

Then change `test_step_list_has_19_entries`. Rename it and update both assertions + the comment:

```python
def test_step_list_has_20_entries():
    # 16 kept + 5 prior new + 1 E11 plan-gate = 22, MINUS the 3 Workstream-C
    # stage merges = 19, PLUS the ultrafast route skill = 20.
    assert len(_BAD_RESEARCH_STEP_SKILLS) == 20
    assert len(set(_BAD_RESEARCH_STEP_SKILLS)) == 20  # no dupes
    assert "bad-research-1.6-plan-gate" in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-ultrafast" in _BAD_RESEARCH_STEP_SKILLS
    # the 3 merged-away stages are gone from the roster
    assert "bad-research-3-contradiction-graph" not in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-7-source-tensions" not in _BAD_RESEARCH_STEP_SKILLS
    assert "bad-research-9-evidence-digest" not in _BAD_RESEARCH_STEP_SKILLS
```

In `tests/test_skills/test_ultrafast_skill.py`, append the wiring tests:

```python
def test_entry_skill_wires_ultrafast_route(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "bad-research-ultrafast" in body
    assert "--ultrafast" in body          # explicit-only selection documented
    # the fetcher cap prose is updated to include the ultrafast key
    assert '"ultrafast":15' in body or '"ultrafast": 15' in body


def test_query_router_routes_ultrafast(skills_dir):
    body = (skills_dir / "bad-research-query-router.md").read_text()
    assert "--ultrafast" in body
    assert "bad-research-ultrafast" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_install/test_step_list.py tests/test_skills/test_ultrafast_skill.py -v`
Expected: FAIL — roster membership/count (19≠20), entry-skill wiring, and query-router routing all missing.

- [ ] **Step 3: Register the skill in the install roster**

In `src/bad_research/core/hooks.py`, change the end of `_BAD_RESEARCH_STEP_SKILLS` (line 3750) from:

```python
    "bad-research-fast",
]
```

to:

```python
    "bad-research-fast",
    "bad-research-ultrafast",
]
```

- [ ] **Step 4: Wire the entry skill `bad-research.md`**

**(4a)** In the half-step roster table, after the `bad-research-fast` row (line 65), add:

```markdown
| — | `bad-research-ultrafast` | The commercial-DR middle tier (a *route* — plan → K parallel researchers → leader synthesis; replaces steps 2–14 when route == `ultrafast`) | ultrafast |
```

**(4b)** In the `## Tier routing` mode table, insert an `ultrafast` row between the `fast` and `full` rows:

```markdown
| `ultrafast` | 1 → 1.5 → bad-research-ultrafast (plan → K≤6 parallel researchers → leader synthesis) → slim citation-grounding → 12(slim critic) → 15 → 16(+gate) | mid, broad, autonomous (5–15 min); explicit `--ultrafast` only |
```

**(4c)** Immediately after that mode table (before the `**On 0.5 (clarify):**` paragraph), add this selection note:

```markdown
**On `ultrafast` (the commercial-DR middle tier):** it is **never auto-selected** —
`classify_route` only emits `fast`/`full`. It is forced two ways, resolved at
bootstrap: (a) the **`--ultrafast` flag** (the orchestrator runs `bad route --apply
--ultrafast`), or (b) an explicit **"ultrafast mode"** request in the user prompt (the
orchestrator recognizes the intent and applies the same override; conservative — only
an explicit "ultrafast" mention counts, never an inferred "make it fast"). It is
**fully autonomous**: it SKIPS step 0.5 (clarifier) and step 1.6 (plan-gate) like an
`--auto` run, then runs plan → K≤6 parallel `bad-research-fetcher` researchers →
leader-only sectioned synthesis → slim grounding → slim critic → polish → gate.
```

**(4d)** In the route-mapping bullet list, after the `fast →` bullet (line 111), add:

```markdown
- ultrafast → `Skill(skill: "bad-research-ultrafast")` (commercial-DR middle tier — plan → K parallel researchers → leader synthesis; replaces 2–14; explicit `--ultrafast`/"ultrafast mode" only, fully autonomous — skips 0.5 + 1.6)
```

**(4e)** In bootstrap step 7 (the clarifier), change:

```markdown
7. **Invoke the clarifier (step 0.5)** UNLESS this is an `--auto` / wrapped run
   (`research/wrapper_contract.json` present) — then skip straight to step 1:
```

to:

```markdown
7. **Invoke the clarifier (step 0.5)** UNLESS this is an `--auto` / wrapped run
   (`research/wrapper_contract.json` present) **or an `ultrafast` run** (the
   `--ultrafast` flag or an explicit "ultrafast mode" request) — then skip straight
   to step 1:
```

**(4f)** In bootstrap step 9 (the query router), append after "...writes the `route` field into `research/prompt-decomposition.json`.":

```markdown
   For an `ultrafast` run, the orchestrator passes the override instead: `bad route
   --apply --ultrafast` — forcing `route="ultrafast"` regardless of the
   auto-classification (mutually exclusive with `--fast`/`--full`).
```

**(4g)** In bootstrap step 10 (the plan-gate), change "**Skip it for `fast`** (a small bounded run is never gated)." to:

```markdown
**Skip it for `fast`** (a small bounded run is never gated) **and for `ultrafast`**
(autonomous by design).
```

**(4h)** In the subagent spawn contract section, update the `FETCHER_TOOLCALL_CAP` prose mention (line 264) from `FETCHER_TOOLCALL_CAP={"light":10,"full":20}` to `FETCHER_TOOLCALL_CAP={"light":10,"ultrafast":15,"full":20}`.

- [ ] **Step 5: Wire the query-router `bad-research-query-router.md`**

**(5a)** In `## Procedure`, after step 3 (the `--apply` block, line 69), add:

```markdown
   **Ultrafast override:** if the run was launched with `--ultrafast` (or the user
   explicitly asked for "ultrafast mode"), run instead
   `bad route --decomposition research/prompt-decomposition.json --apply --ultrafast --json`,
   which forces `route="ultrafast"`. `--ultrafast` is mutually exclusive with
   `--fast`/`--full`.
```

**(5b)** In `## Exit criterion`, change `∈ {fast, full}` (line 77) to `∈ {fast, full, ultrafast}`.

**(5c)** In `## Next step`, after the `**fast** →` bullet, add:

```markdown
- **ultrafast** → `Skill(skill: "bad-research-ultrafast")` (commercial-DR middle tier — plan → K parallel researchers → leader synthesis; then the same slim citation-grounding + slim critic tail as fast)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_install/test_step_list.py tests/test_skills/test_ultrafast_skill.py -v`
Expected: PASS (all). If a pre-existing entry-skill test (`tests/test_skills/test_entry_skill.py`, `tests/test_skills/test_delegation_contract.py`) asserts a fixed row/skill count, update that count to include the new row — they assert substring presence, not counts, in the version surveyed, so none is expected to break.

- [ ] **Step 7: Commit**

```bash
git add src/bad_research/core/hooks.py src/bad_research/skills/bad-research.md src/bad_research/skills/bad-research-query-router.md tests/test_install/test_step_list.py tests/test_skills/test_ultrafast_skill.py
git commit -m "feat(ultrafast): register skill + wire entry route table & query-router"
```

---

### Task 5: Full-suite regression + lint/mypy/golden + manual smoke

**Files:** none (verification task; commit only if a fix is needed)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`
Expected: PASS at the pre-existing baseline (per project memory: ~991 passed / 9 skipped, coverage ~88%) plus the new ultrafast tests. Zero failures.

- [ ] **Step 2: Confirm the golden eval corpus did not move**

Run: `pytest tests/test_calibrate/test_golden.py -v`
Expected: PASS unchanged — `classify_route` was never touched, so every fixture routes exactly as before.

- [ ] **Step 3: Lint + type-check at baseline**

Run: `ruff check src tests && mypy src`
Expected: no NEW ruff/mypy errors beyond the documented pre-existing baseline (17 ruff in `tests/test_web/*`, 142 mypy). If the new code adds any, fix them (e.g. add the `ultrafast` option with a trailing comma; keep line length within the project's ruff config).

- [ ] **Step 4: Manual CLI smoke test**

Run:
```bash
python -c "import json,tempfile,os; p=tempfile.mktemp(suffix='.json'); open(p,'w').write(json.dumps({'sub_questions':['a','b'],'entities':[],'domains':['a','b','c'],'response_format':'structured','contradiction_terms':[],'time_periods':[]})); os.system(f'bad route --decomposition {p} --ultrafast --json'); os.system(f'bad route --decomposition {p} --ultrafast --full')"
```
Expected: first call prints `"route": "ultrafast"`; second call exits non-zero with the mutual-exclusivity error.

- [ ] **Step 5: Confirm the install roster materializes the skill**

Run: `bad install --steps-only /tmp/ultrafast-smoke --json && ls /tmp/ultrafast-smoke/.claude/skills/ | grep ultrafast`
Expected: `bad-research-ultrafast` directory present (proves it's in the roster and not pruned).

- [ ] **Step 6: Final grep sanity**

Run: `grep -rn "ultrafast" src/bad_research | grep -v "__pycache__" | wc -l`
Expected: non-zero across `routing_constants.py`, `router.py`, `cli/research.py`, `core/hooks.py`, and the two skill files — the full wiring is present.

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "test(ultrafast): full-suite green + lint/mypy/golden baseline"
```

---

## Self-Review

**1. Spec coverage:**
- Spec §2 (positioning table) → Task 1 (caps), Task 3 (behavior), Task 4b (route table). ✓
- Spec §3 (explicit-only selection + autonomous) → Task 2 (flag), Task 4c/4e/4f/4g (wiring + skips). ✓
- Spec §4 (pipeline + steal-list) → Task 3 (skill body). ✓
- Spec §5 (`ULTRAFAST_*` constants) → Task 1. ✓
- Spec §6 (touchpoints table) → maps 1:1 onto Tasks 1–4; the `pipeline.py` "leave alone" row → File Structure note. ✓
- Spec §9 (success criteria) → Task 2 tests (override + exclusivity), Task 3 tests (report shape rules in prose), Task 5 (suite + golden + smoke). ✓

**2. Placeholder scan:** No "TBD/TODO/handle edge cases". Every code step shows complete code; every skill edit shows exact anchor + exact text. ✓

**3. Type consistency:** `Route` literal `["fast","full","ultrafast"]` (Task 2) is consistent with `route_cmd`'s `route` assignments (Task 2) and the skill's `route == "ultrafast"` gate (Task 3). `FETCHER_TOOLCALL_CAP["ultrafast"]` (Task 1) matches the skill's reference (Task 3) and the entry-skill prose (Task 4h). `_BAD_RESEARCH_STEP_SKILLS` count 20 (Task 4 test) matches the single appended entry (Task 4 Step 3). Constant names (`ULTRAFAST_MAX_SUBQUESTIONS`, `ULTRAFAST_SUBRESEARCHER_K`, `ULTRAFAST_MIN_SOURCES_PER_SUBQ`, `ULTRAFAST_FETCHER_TIMEOUT_S`, `ULTRAFAST_RESERVE_SYNTH_FRAC`, `ULTRAFAST_TIMEOUT_S`) are identical across Task 1 (definition + test) and Task 3 (skill body + structural test). ✓
