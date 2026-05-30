# bad-research Fast-mode (2-route consolidation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the three routes (`agentic-fast` / `light` / `full`) into two operator modes — **Fast** (a Perplexity-style bounded planner→writer loop with breadth sub-researcher fan-out + a slim citation-grounding pass) and **Full** (the existing deep pipeline, unchanged).

**Architecture:** Two stages. **Stage 1 (Tasks 1-7): consolidation** — a behavior-preserving refactor that merges the two shallow routes into `fast` and renames the skill; ships a working 2-mode router. **Stage 2 (Tasks 8-11): the quality builds** — make Fast shape-aware (breadth fan-out), add a scope brief, add a slim citation-grounding pass. Full is untouched throughout.

**Tech Stack:** Python 3.11-3.13, Typer CLI, pytest (+pytest-cov, gate `--cov-fail-under=80`), mypy `--strict`, ruff. Skills are markdown files validated by `tests/test_skills/validate.py`.

**Spec:** `docs/superpowers/specs/2026-05-29-bad-research-fast-mode-design.md`. RE companion: `docs/superpowers/specs/2026-05-29-bad-research-fast-mode-RE-gaps.md`.

---

## Conventions for every task

- **Branch:** already on `fast-mode` (created during brainstorming). Stay on it.
- **Single-test runs MUST pass `--no-cov`** — the global `addopts` carries `--cov-fail-under=80`, which fails any partial run. Example: `uv run pytest tests/test_skills/test_router.py -v --no-cov`.
- **Full green check (end of each task):** `uv run pytest -q` (coverage gate applies), then `uv run ruff check src tests` and `uv run mypy src`.
- Use `uv run <tool>` (the repo is uv-managed; `.venv/bin/<tool>` also works).
- This is largely a **rename/refactor**, so several tasks update existing tests to the new expectation *first* (they then fail against old source), then change source to green them — TDD-flavored refactoring.

---

## File Structure (what changes, and why)

**Stage 1 — consolidation**
- `src/bad_research/skills/router.py` — `Route` literal; `classify_route` (two non-full branches → `fast`); `route_reason`. *Sole producer of route strings.*
- `src/bad_research/skills/routing_constants.py` — `EFFORT_MAP` route values `light`→`fast`.
- `src/bad_research/pipeline.py` — second `Route` literal; `RunResult.route` default; route→funnel-mode mapping.
- `src/bad_research/calibrate/golden/{01,02,05,07,08}*.json` — `expected_route` → `fast`.
- `src/bad_research/cli/research.py` — `route_cmd` `--fast`/`--full` override flags; docstring.
- `src/bad_research/mcp/server.py` — `route_query` docstring only.
- `src/bad_research/core/hooks.py` — `_BAD_RESEARCH_STEP_SKILLS` roster entry rename; agent-prompt prose.
- `src/bad_research/skills/bad-research-agentic-fast.md` → `bad-research-fast.md` — frontmatter `name`, tier-gate route string.
- `src/bad_research/skills/bad-research.md` — route table 3→2 rows.
- `src/bad_research/skills/bad-research-query-router.md` — 3-way → 2-way classification.
- `src/bad_research/skills/bad-research-1-decompose.md` — `scope_brief` output field (Stage 2, Task 8).
- `tests/test_skills/*`, `tests/test_pipeline/test_run_query.py`, `tests/test_cli/test_cli_subcommands.py`, `tests/test_skills/test_plan_gate.py`, `tests/test_skills/test_light_critic.py` — route-string assertions.

**Stage 2 — quality builds**
- `src/bad_research/skills/bad-research-1-decompose.md` — scope brief.
- `src/bad_research/skills/routing_constants.py` — `AGENTIC_FAST_*` → `FAST_*` + bumped caps + `FAST_SUBRESEARCHER_K`.
- `src/bad_research/skills/bad-research-fast.md` — hybrid shape-aware loop + breadth fan-out + slim-grounding call.

**Decision (recorded):** the funnel `mode` axis (`light`/`full`) is an **internal fan-out dial, not the route**. It is NOT renamed in this plan — route `fast` maps to funnel-mode `light`. `FETCHER_TOOLCALL_CAP = {"light": 10, "full": 20}` keys stay. A funnel-axis rename is a deliberate follow-up, out of scope here (keeps the diff focused and every commit green).

---

## TASK 1: Collapse the router (`Route` literal + `classify_route` + `route_reason`)

**Files:**
- Modify: `src/bad_research/skills/router.py` (Route literal :34; `classify_route` :183-209; `route_reason` :212-233)
- Modify: `src/bad_research/pipeline.py` (Route literal :38; `RunResult.route` default :116; route→mode :248)
- Test: `tests/test_skills/test_router.py`, `tests/test_skills/test_router_tiering.py`, `tests/test_skills/test_router_modality.py`, `tests/test_skills/test_router_shape.py`

(Router and pipeline are type-coupled via two independent `Route` literals; change both in one task so `mypy --strict` stays green at commit.)

- [ ] **Step 1: Update the router unit tests to expect `fast`.** In `tests/test_skills/test_router.py`, change every shallow-route assertion to `"fast"` and rename the functions:
  - `:24` `test_trivial_single_domain_routes_agentic_fast` → `test_trivial_single_domain_routes_fast`, assert `== "fast"`.
  - `:29` `test_two_atomic_no_tension_routes_agentic_fast` → `..._routes_fast`, assert `== "fast"`.
  - `:34` `test_structured_midsize_routes_light` → `..._routes_fast`, assert `== "fast"`.
  - `:58` `test_short_with_three_atomic_routes_light` → `..._routes_fast`, assert `== "fast"`.
  - `:64` `test_entities_count_toward_atomic` — assert `== "fast"`.
  - Leave the three `== "full"` tests (`:40,:46,:52`) and `test_route_reason_mentions_full_trigger` (`:74`) unchanged.
  - Leave `:19` (`R.ROUTER_AGENTIC_MAX_ATOMIC == 2 and R.ROUTER_LIGHT_MAX_ATOMIC == 6`) unchanged — both constants survive (still referenced by `route_reason` / plan-gate).

  In `tests/test_skills/test_router_tiering.py`: `:168` assert `== "fast"` (rename `test_pipeline_tier_light_imposes_no_floor` → `..._fast_floor`); `:98` and `:109` assert `== "fast"`; `:157` assert `== "fast"`. Leave all `== "full"` and `pipeline_tier=` *inputs* untouched.

  In `tests/test_skills/test_router_modality.py`: `:86` and `:95` assert `== "fast"`; `:168` change `assert "light" in reason` → `assert "fast" in reason`.

  In `tests/test_skills/test_router_shape.py`: `:148,:151` assert `== "fast"`; `:156,:158,:192,:194` assert `== "fast"`. (The `query_shape` tests are orthogonal — do not touch.)

- [ ] **Step 2: Run the router tests to verify they fail.**

Run: `uv run pytest tests/test_skills/test_router.py tests/test_skills/test_router_tiering.py tests/test_skills/test_router_modality.py tests/test_skills/test_router_shape.py -v --no-cov`
Expected: FAIL — old source still returns `"agentic-fast"`/`"light"` (e.g. `assert 'agentic-fast' == 'fast'`).

- [ ] **Step 3: Collapse `classify_route` in `router.py`.** Replace the function body (`:183-209`) with:

```python
def classify_route(decomp: dict[str, Any]) -> Route:
    fmt = decomp.get("response_format", "structured")
    time_periods = decomp.get("time_periods") or []
    contradiction = decomp.get("contradiction_terms") or []
    domains = decomp.get("domains") or []
    multi_domain = len(domains) >= 3

    # FULL: explicit pipeline_tier floor, time_periods, argumentative, contradiction,
    # multi-domain, or a breadth count that survives the modality gate. UNCHANGED.
    if (_pipeline_tier_floor_full(decomp)
            or time_periods or fmt == "argumentative" or contradiction
            or multi_domain or _breadth_forces_full(decomp)):
        return "full"

    # FAST: everything else. The former agentic-fast (trivial/bounded) and light
    # (mid-band structured) bands both run the bounded planner->writer loop; the
    # split is now an internal shape+effort knob, not a route.
    return "fast"
```

- [ ] **Step 4: Update the `Route` literal + `route_reason` in `router.py`.** Change `:34` to `Route = Literal["fast", "full"]`. Replace `route_reason` (`:212-233`) with:

```python
def route_reason(decomp: dict[str, Any]) -> str:
    """A one-line, human-readable rationale for the chosen route."""
    route = classify_route(decomp)
    n = _atomic_count(decomp)
    modality = detect_modality(decomp)
    if route == "full":
        triggers = _full_triggers(decomp)
        return "full: " + ("; ".join(triggers) if triggers else "complex query")
    # FAST: call out when an EXPLICIT broad-curation modality spared a high-breadth
    # query from full (the B-5 gate) so the rationale line is auditable.
    if _explicit_breadth_modality(decomp) and n > R.ROUTER_LIGHT_MAX_ATOMIC:
        return (f"fast: {n} atomic item(s) but explicit {modality} modality / low "
                f"contestedness — breadth alone does not force full (B-5)")
    return f"fast: {n} atomic item(s), no full-tier trigger"
```

(Leave `plan_gate_fires` unchanged — it special-cases only `== "full"`; its atomic-count clause already covers what was light/agentic-fast.)

- [ ] **Step 5: Update `pipeline.py`.** Change `:38` to `Route = Literal["fast", "full"]`. Change `:116` `route: Route = "light"` → `route: Route = "fast"`. Change `:248`:

```python
        mode = "light" if route == "fast" else "full"
```

(`mode` here is the funnel-mode axis — `fast` maps to funnel-`light`. Update the `tests/test_pipeline/test_run_query.py` route assertions in Task 3.)

- [ ] **Step 6: Run the router tests to verify they pass.**

Run: `uv run pytest tests/test_skills/test_router.py tests/test_skills/test_router_tiering.py tests/test_skills/test_router_modality.py tests/test_skills/test_router_shape.py -v --no-cov`
Expected: PASS.

- [ ] **Step 7: Lint + type-check the two changed modules.**

Run: `uv run ruff check src/bad_research/skills/router.py src/bad_research/pipeline.py && uv run mypy src/bad_research/skills/router.py src/bad_research/pipeline.py`
Expected: no errors. (If ruff flags an unused `n`/`fmt`, confirm `fmt` is still used in the full branch and that `n = _atomic_count(decomp)` was removed from `classify_route`.)

- [ ] **Step 8: Commit.**

```bash
git add src/bad_research/skills/router.py src/bad_research/pipeline.py \
        tests/test_skills/test_router.py tests/test_skills/test_router_tiering.py \
        tests/test_skills/test_router_modality.py tests/test_skills/test_router_shape.py
git commit -m "refactor(router): collapse agentic-fast+light -> fast (2-route)"
```

---

## TASK 2: `EFFORT_MAP` route values + effort test

**Files:**
- Modify: `src/bad_research/skills/routing_constants.py` (`EFFORT_MAP` :159-168)
- Test: `tests/test_skills/test_router_effort.py`

- [ ] **Step 1: Update the effort tests.** In `tests/test_skills/test_router_effort.py`:
  - `:22` `assert row["route"] in ("light", "full")` → `("fast", "full")`.
  - `:39` `assert ov["route"] == "light"` → `== "fast"` (rename `test_effort_overrides_minimal_forces_light_single_draft` → `..._minimal_forces_fast_single_draft`).
  - `:64` `assert ov["route"] == "light"` → `== "fast"`.
  - Leave `:10` (`R.FETCHER_TOOLCALL_CAP == {"light": 10, "full": 20}`) unchanged — funnel-mode keys, not routes.
  - Leave `:46` (`== "full"`) and `test_effort_can_downgrade_full_to_light` `:62` (`classify_route(...) == "full"`) unchanged.

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_router_effort.py -v --no-cov`
Expected: FAIL — `EFFORT_MAP` still has `"route": "light"`.

- [ ] **Step 3: Update `EFFORT_MAP`.** In `routing_constants.py`, change the two shallow rows:

```python
EFFORT_MAP = {
    "minimal": {"route": "fast", "tier": "triage", "fetchers_max": 4,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "low":     {"route": "fast", "tier": "work",   "fetchers_max": 8,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "medium":  {"route": "full",  "tier": "default", "fetchers_max": 12, "loci_max": 4,
                "extended_thinking": True,  "single_draft": False},
    "high":    {"route": "full",  "tier": "heavy",  "fetchers_max": 12, "loci_max": 6,
                "extended_thinking": True,  "single_draft": False},
}
```

- [ ] **Step 4: Run to verify pass.**

Run: `uv run pytest tests/test_skills/test_router_effort.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/bad_research/skills/routing_constants.py tests/test_skills/test_router_effort.py
git commit -m "refactor(router): EFFORT_MAP minimal/low route -> fast"
```

---

## TASK 3: Golden corpus + pipeline test route values

**Files:**
- Modify: `src/bad_research/calibrate/golden/01_causal_light.json`, `02_comparison.json`, `05_definitional.json`, `07_breadth_list.json`, `08_numeric_precise.json` (`expected_route`)
- Test: `tests/test_calibrate/test_golden.py`, `tests/test_pipeline/test_run_query.py`

- [ ] **Step 1: Update `test_run_query.py`.** Change the route assertions at `:29,:45,:72` from `"agentic-fast"` to `"fast"` (rename any function with `agentic_fast` in its name to `fast`).

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_pipeline/test_run_query.py tests/test_calibrate/test_golden.py -v --no-cov`
Expected: FAIL — golden fixtures still say `agentic-fast`/`light`, and `classify_route` now returns `fast` (`_check_decompose` string-equality mismatch).

- [ ] **Step 3: Rewrite the 5 fixtures' `expected_route`.** In each file set `components.decompose.expected_route` to `"fast"`:
  - `01_causal_light.json` (`light`→`fast`), `02_comparison.json` (`light`→`fast`), `05_definitional.json` (`agentic-fast`→`fast`), `07_breadth_list.json` (`light`→`fast`), `08_numeric_precise.json` (`light`→`fast`).
  - Do NOT touch `03`, `04`, `06` (`full`) or `09`, `10` (no route).

- [ ] **Step 4: Run to verify pass.**

Run: `uv run pytest tests/test_pipeline/test_run_query.py tests/test_calibrate/test_golden.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/bad_research/calibrate/golden/01_causal_light.json \
        src/bad_research/calibrate/golden/02_comparison.json \
        src/bad_research/calibrate/golden/05_definitional.json \
        src/bad_research/calibrate/golden/07_breadth_list.json \
        src/bad_research/calibrate/golden/08_numeric_precise.json \
        tests/test_pipeline/test_run_query.py
git commit -m "refactor(eval): golden expected_route agentic-fast/light -> fast"
```

---

## TASK 4: CLI `--fast` / `--full` override flags

**Files:**
- Modify: `src/bad_research/cli/research.py` (`route_cmd` :23-77; docstring :32)
- Modify: `src/bad_research/mcp/server.py` (docstring :418)
- Test: `tests/test_cli/test_cli_subcommands.py`

- [ ] **Step 1: Write the failing test.** Append to `tests/test_cli/test_cli_subcommands.py` (match the file's existing CliRunner style; it already invokes `bad route` and asserts on JSON output around `:17,:38,:57,:73` — first sweep those four assertions: `agentic-fast`→`fast`, `light`→`fast`). Then add:

```python
def test_route_fast_flag_overrides(tmp_path):
    # A decomposition the router would call "full" (multi-domain), forced to fast.
    decomp = tmp_path / "decomp.json"
    decomp.write_text(json.dumps({
        "sub_questions": ["a", "b"], "entities": [], "time_periods": [],
        "response_format": "structured", "contradiction_terms": [],
        "domains": ["a", "b", "c"],
    }))
    result = runner.invoke(app, ["route", "--decomposition", str(decomp), "--fast", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["route"] == "fast"


def test_route_fast_and_full_mutually_exclusive(tmp_path):
    decomp = tmp_path / "decomp.json"
    decomp.write_text(json.dumps({"sub_questions": ["a"], "entities": [], "domains": ["x"],
                                  "response_format": "short"}))
    result = runner.invoke(app, ["route", "--decomposition", str(decomp), "--fast", "--full"])
    assert result.exit_code != 0
```

(If `app`/`runner`/`json` aren't already imported at the top of the file, add `import json` and reuse the existing `runner = CliRunner()` / `from bad_research.cli import app` — check the file header and match it.)

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_cli/test_cli_subcommands.py -k "fast" -v --no-cov`
Expected: FAIL — `--fast` is an unknown option.

- [ ] **Step 3: Add the flags to `route_cmd`.** In `research.py`, add two options to the `route_cmd` signature (after `est_cost`):

```python
    fast: bool = typer.Option(False, "--fast", help="Force the fast route (override auto)."),
    full: bool = typer.Option(False, "--full", help="Force the full route (override auto)."),
```

Then, immediately after `route = classify_route(decomp)` (`:55`), insert:

```python
    if fast and full:
        raise typer.BadParameter("--fast and --full are mutually exclusive")
    if fast:
        route = "fast"
    elif full:
        route = "full"
```

Update the docstring (`:32`) `(agentic-fast|light|full)` → `(fast|full)`.

- [ ] **Step 4: Update the MCP docstring.** In `mcp/server.py:418`, change `(agentic-fast|light|full)` → `(fast|full)`. (Body unchanged — it passes through `classify_route`.)

- [ ] **Step 5: Run to verify pass.**

Run: `uv run pytest tests/test_cli/test_cli_subcommands.py -v --no-cov`
Expected: PASS.

- [ ] **Step 6: Lint + types.**

Run: `uv run ruff check src/bad_research/cli/research.py src/bad_research/mcp/server.py && uv run mypy src/bad_research/cli/research.py`
Expected: no errors.

- [ ] **Step 7: Commit.**

```bash
git add src/bad_research/cli/research.py src/bad_research/mcp/server.py tests/test_cli/test_cli_subcommands.py
git commit -m "feat(cli): add --fast/--full route override to 'bad route'"
```

---

## TASK 5: Rename the fast skill file + hooks roster + agent prose

**Files:**
- Rename: `src/bad_research/skills/bad-research-agentic-fast.md` → `src/bad_research/skills/bad-research-fast.md`
- Modify: that file's frontmatter `name:` + tier-gate route string (`:12`, `:25-28`)
- Modify: `src/bad_research/core/hooks.py` (`_BAD_RESEARCH_STEP_SKILLS` entry; registry string :3750; `LIGHT_CRITIC_AGENT` prose :1265,:1279,:1290,:1300; description :3526)
- Rename: `tests/test_skills/test_agentic_fast_skill.py` → `tests/test_skills/test_fast_skill.py`
- Modify: `tests/test_skills/test_entry_skill.py` (:16), `tests/test_skills/test_all_skills_valid.py` (:30)

- [ ] **Step 1: Update the skill validation tests.** Rename `test_agentic_fast_skill.py` → `test_fast_skill.py`. Inside, change both filename literals `"bad-research-agentic-fast.md"` (`:5,:11`) → `"bad-research-fast.md"`, rename the two functions (`test_fast_skill_valid`, `test_fast_has_loop_bounds_and_planner_writer`). Keep the body-content asserts for now (`"max_steps"`, `"10"`, `"300"`, `"15"`, `planner`/`writer`, `funnel`, `"[N]"`) — the loop-bound numbers change in Task 10; this task only renames.

  In `tests/test_skills/test_entry_skill.py:16`, change `assert "bad-research-agentic-fast" in body` → `assert "bad-research-fast" in body`.

  In `tests/test_skills/test_all_skills_valid.py:30`, change the exclusion `s != "bad-research-agentic-fast"` → `s != "bad-research-fast"`. (The `== 18` count holds — one renamed entry, not added/removed.)

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_fast_skill.py tests/test_skills/test_entry_skill.py tests/test_skills/test_all_skills_valid.py -v --no-cov`
Expected: FAIL — `bad-research-fast.md` doesn't exist yet; roster still lists `bad-research-agentic-fast`.

- [ ] **Step 3: Rename the skill file + fix frontmatter/route gate.**

```bash
git mv src/bad_research/skills/bad-research-agentic-fast.md src/bad_research/skills/bad-research-fast.md
```

In `bad-research-fast.md`: set frontmatter `name: bad-research-fast` (MUST equal the new slug — `validate.py:45` enforces it). In the body, change the tier-gate text and the route guard from `route == "agentic-fast"` to `route == "fast"` (the two occurrences around `:12` and `:25-28`: "Runs ONLY for the `agentic-fast` route" → "`fast` route"; "If `route != "agentic-fast"`" → "`!= "fast"`").

- [ ] **Step 4: Update `hooks.py`.** In `src/bad_research/core/hooks.py`:
  - `_BAD_RESEARCH_STEP_SKILLS`: rename the `"bad-research-agentic-fast"` entry to `"bad-research-fast"` (this is the roster `test_all_skills_valid.py` + `test_step_list.py` read).
  - `:3750` registry list string `"bad-research-agentic-fast"` → `"bad-research-fast"`.
  - `LIGHT_CRITIC_AGENT` prose `:1265,:1279,:1290,:1300` and description `:3526`: replace "light / agentic-fast" / "light + agentic-fast" with "fast" (the slim critic now runs on the single `fast` route).

- [ ] **Step 5: Run to verify pass.**

Run: `uv run pytest tests/test_skills/ -v --no-cov`
Expected: PASS (all skill tests, including `test_fast_skill`, `test_entry_skill`, `test_all_skills_valid`).

- [ ] **Step 6: Commit.**

```bash
git add -A src/bad_research/skills/ src/bad_research/core/hooks.py tests/test_skills/
git commit -m "refactor(skills): rename agentic-fast skill -> bad-research-fast + roster/prose"
```

---

## TASK 6: Entry skill + query-router skill route tables (3 → 2)

**Files:**
- Modify: `src/bad_research/skills/bad-research.md` (route table; "13 step skills" header; per-route sequences; recovery)
- Modify: `src/bad_research/skills/bad-research-query-router.md` (the decision tree + next-step routing)
- Test: `tests/test_skills/test_entry_skill.py` (:12), `tests/test_skills/test_router_skill.py` (:12)

- [ ] **Step 1: Update the skill-content tests.** In `tests/test_skills/test_entry_skill.py:12`, change the tuple `("agentic-fast", "light", "full")` → `("fast", "full")` and rename `test_entry_skill_has_three_route_sequences` → `..._two_route_sequences`. In `tests/test_skills/test_router_skill.py:12`, change `("agentic-fast", "light", "full")` → `("fast", "full")` and rename `..._names_three_routes_and_cli` → `..._names_two_routes_and_cli`.

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_entry_skill.py tests/test_skills/test_router_skill.py -v --no-cov`
Expected: FAIL — the entry/router skill bodies still contain `agentic-fast`/`light` and not the 2-route framing.

- [ ] **Step 3: Rewrite the entry skill route table.** In `bad-research.md`, replace the per-route mode table (the `| Route | Step sequence | Cost | Time |` block) with two rows:

```markdown
| Route | Step sequence | Cost | Time |
|---|---|---|---|
| `fast` | 0.5 → 1 → 1.5 → bad-research-fast (shape-aware loop ± breadth fan-out) → slim citation-grounding → 12(slim critic) → 15 → 16(+gate) | ~$1–8 | ≤8–10 min |
| `full` | 0.5 → 1 → 1.5 → 1.6 → 2 → 4* → 5 → 6* → 8 → 10* → 11 → 11.5 → 12 → 13 → 12.5 → 14 → 14.5 → 15 → 16(+gate+recitation) | ~$60–120 | ~1.5–2.5 h |
```

Update the surrounding prose that enumerates the three routes: the "Complete pipeline order" note, the "`light` runs … `agentic-fast` runs …" sentence (replace with a single `fast` sentence), the RESPECT-THE-ROUTE paragraph, the `--effort` table (minimal/low → fast; medium/high → full), the half-step list (`agentic-fast → Skill(... )` becomes `fast → Skill(skill: "bad-research-fast")`), the bootstrap todo-seeding note, and the recovery artifacts list (`agentic-fast: research/temp/react-trace.md` → `fast: …`). Steps 2 and 10 stay listed as **Full-only**.

- [ ] **Step 4: Rewrite the query-router skill decision tree.** In `bad-research-query-router.md`, replace the 3-way decision tree with 2-way:

```markdown
   - **fast** if NOT a full-tier trigger (no contradiction terms, no time_periods,
     not argumentative, not multi-domain, breadth survives the modality gate)
   - **full** else
```

Update the `## Next step` routing so `fast → Skill(skill: "bad-research-fast")` and `full → Skill(skill: "bad-research-2-width-sweep")`. Keep the `query_shape` section verbatim (orthogonal — it now selects the Fast loop's internal arrangement). Update the exit-criterion line `route ∈ {agentic-fast, light, full}` → `{fast, full}`.

- [ ] **Step 5: Run to verify pass.**

Run: `uv run pytest tests/test_skills/ -v --no-cov`
Expected: PASS (validators confirm frontmatter/sections/refs; content tests confirm 2-route framing).

- [ ] **Step 6: Commit.**

```bash
git add src/bad_research/skills/bad-research.md src/bad_research/skills/bad-research-query-router.md \
        tests/test_skills/test_entry_skill.py tests/test_skills/test_router_skill.py
git commit -m "docs(skills): entry + query-router route tables 3 -> 2 (fast/full)"
```

---

## TASK 7: Sweep remaining route-string references + full green gate

**Files:**
- Modify: `tests/test_skills/test_plan_gate.py` (:125,:133), `tests/test_skills/test_light_critic.py` (:61), and any other test grep-hits
- Modify: residual skill-doc mentions in `bad-research-12-critics.md`, `bad-research-12.5-grader.md`, `bad-research-11.5-citation-verifier.md`, `bad-research-fresh-review.md`, `bad-research-0.5-clarify.md`, `bad-research-16-readability-audit.md`, `bad-research-1-decompose.md`

- [ ] **Step 1: Find every residual reference.**

Run: `grep -rn "agentic-fast\|agentic_fast" src/bad_research tests | grep -v ".pyc"`
Expected: a list of remaining hits (plan-gate test, light-critic test, the slim-critic skill docs that say "light/agentic-fast", etc.). Also run `grep -rn '"light"' tests/test_skills tests/test_cli tests/test_pipeline` and triage each: route-string → change to `fast`; funnel-`mode`/`pipeline_tier`/`tier` value → leave.

- [ ] **Step 2: Update the test assertions.** In `tests/test_skills/test_plan_gate.py:125` (`agentic-fast`) and `:133` (`light`): these assert the plan-gate does NOT fire on cheap routes — change both to a `fast`-route decomposition and assert `plan_gate_fires(...) is False`. In `tests/test_skills/test_light_critic.py:61`, change the route enumeration to `("fast", "full")` (or drop `agentic-fast`/`light` to `fast`).

- [ ] **Step 3: Update residual skill docs.** In the step skills' "Tier gate" lines, replace "light / agentic-fast" with "fast" wherever the slim-critic / skip-on-shallow behavior is described (`bad-research-12-critics.md`, `bad-research-12.5-grader.md`, `bad-research-11.5-citation-verifier.md` tier-gate, `bad-research-fresh-review.md`, `bad-research-0.5-clarify.md:16`, `bad-research-16-readability-audit.md:150`, `bad-research-1-decompose.md:127`). These are prose; no test asserts the old strings except those already swept.

- [ ] **Step 4: Run the FULL suite + lint + types.**

Run: `uv run pytest -q` — **the full pytest suite MUST be green, coverage ≥ 80%.** This is the real ship gate; once every residual route-string assertion is swept the suite goes green. Known stragglers to sweep (besides this task's named files): `tests/test_skills/test_plan_gate.py` (:125 `agentic-fast`, :133 `light`), `tests/test_skills/test_light_critic.py` (:61/:89 old skill filename), and **three install tests carrying the old skill name** — `tests/test_install/test_step_list.py:8`, `tests/test_install/test_install_cli_e2e.py:34`, `tests/test_install/test_install_project.py:10`. Also triage every other `grep` hit (route-string → `fast`; funnel-`mode`/`pipeline_tier`/`tier` value → LEAVE).

Then `uv run ruff check src tests` and `uv run mypy src` — these MUST introduce **NO NEW errors vs the `ee692ce` baseline**. The repo carries pre-existing failures that are NOT ours to fix: ~17 ruff errors in `tests/test_web/*` (unused imports) and ~142 mypy errors across ~31 files. Verify "no new" by comparing the HEAD error set to `ee692ce` (line-number shifts of an identical message do not count as new). Do **not** attempt to zero out the pre-existing baseline.

- [ ] **Step 5: Commit (Stage 1 complete — working 2-mode router).**

```bash
git add -A
git commit -m "refactor: sweep residual agentic-fast/light references; 2-mode consolidation complete"
```

---

## TASK 8: Decompose emits a `scope_brief`

**Files:**
- Modify: `src/bad_research/skills/bad-research-1-decompose.md` (Step-4 JSON contract; exit criterion)
- Test: `tests/test_skills/` — add a content assertion (new file `test_decompose_skill.py` or extend an existing decompose test)

- [ ] **Step 1: Write the failing content test.** Create `tests/test_skills/test_decompose_skill.py`:

```python
from tests.test_skills.validate import validate_skill


def test_decompose_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-1-decompose.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_decompose_emits_scope_brief(skills_dir):
    body = (skills_dir / "bad-research-1-decompose.md").read_text()
    assert "scope_brief" in body  # one-paragraph framing for the fast writer
```

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_decompose_skill.py -v --no-cov`
Expected: FAIL on `test_decompose_emits_scope_brief` — `scope_brief` not in the skill.

- [ ] **Step 3: Add `scope_brief` to the decompose contract.** In `bad-research-1-decompose.md`, in the Step-4 output JSON example, insert after `sub_questions`:

```json
  "sub_questions": ["...", "..."],
  "scope_brief": "One paragraph: the core subject, what the report will and will not cover, and the boundary conditions. The fast-mode writer reads this as its framing.",
  "entities": [ ... ],
```

Add one sentence to the step procedure instructing the writer to author the paragraph, and add `scope_brief` to the Exit-criterion field list. (Non-breaking: `GoldenCase.from_json` and `classify_route` ignore unknown keys.)

- [ ] **Step 4: Run to verify pass.**

Run: `uv run pytest tests/test_skills/test_decompose_skill.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/bad_research/skills/bad-research-1-decompose.md tests/test_skills/test_decompose_skill.py
git commit -m "feat(skills): decompose emits a scope_brief for the fast writer"
```

---

## TASK 9: Rename loop constants `AGENTIC_FAST_*` → `FAST_*` + bump caps

**Files:**
- Modify: `src/bad_research/skills/routing_constants.py` (`:6-13` loop bounds; add `FAST_SUBRESEARCHER_K`)
- Test: `tests/test_skills/test_router.py` or `test_router_effort.py` — add a constant-presence test

- [ ] **Step 1: Write the failing constant test.** Add to `tests/test_skills/test_router_effort.py`. These values are the evidence-anchored set from the RE synthesis (`researchfms/teardowns/DEEP_RESEARCH_FAST_MODE_RE.md` PART 2.2 — each cited to a cloned DR repo):

```python
def test_fast_loop_constants_present_and_anchored():
    assert R.FAST_MAX_STEPS == 6                 # open_deep_research supervisor cap; Perplexity hard-caps 10
    assert R.FAST_MAX_QUERIES_PER_STEP == 4      # dzhng breadth default
    assert R.FAST_MAX_RESULTS_PER_QUERY == 5     # dzhng + gpt-researcher agree
    assert R.FAST_MIN_NEW_DOMAINS == 2           # "last 2 searches returned similar info" -> novelty floor
    assert R.FAST_STALL_PATIENCE == 1            # fast mode stops after the first stalled step
    assert R.FAST_MIN_SOURCES_PER_SUBQ == 3      # open_deep_research "3+ relevant sources"
    assert R.FAST_MAX_SUBQUESTIONS == 3          # three clones converge on 3
    assert R.FAST_SUBRESEARCHER_K == 3           # breadth fan-out cap
    assert R.FAST_TIMEOUT_S == 600               # wall-clock safety net (8-10 min budget)
    assert R.FAST_RESERVE_SYNTH_FRAC == 0.25     # reserve 25% of budget for the writer
    assert R.FAST_CONTENT_TRIM_CHARS == 25000    # dzhng + gpt-researcher agree
    assert R.FAST_TEMPERATURE == 0.4             # gpt-researcher planner/extractor temp
```

(Note: `FAST_RESERVE_SYNTH_FRAC` (a fraction) is **distinct** from the existing token-valued `RESERVE_FOR_SYNTHESIS = 40_000` — do not rename or clobber that. We do NOT add `FAST_CONFIDENCE_STOP` (needs a calibrated scorer we lack keyless), periodic-replanning, or a separate `FAST_MAX_CALLS` — all skipped as overkill; the step×queries budget + the novelty gate bound the loop.)

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_router_effort.py -k fast_loop -v --no-cov`
Expected: FAIL — `AttributeError: module ... has no attribute 'FAST_MAX_STEPS'`.

- [ ] **Step 3: Replace the loop bounds in `routing_constants.py`.** Replace lines `:6-13` (the old `AGENTIC_FAST_*` block) with the evidence-anchored FAST set (each value cited in RE synthesis PART 2.2):

```python
# ---- Fast-route loop constants (keyless deep-research replica) ----
# Evidence-anchored: see researchfms/teardowns/DEEP_RESEARCH_FAST_MODE_RE.md PART 2.2, each
# value cited to a cloned DR repo (open_deep_research / gpt-researcher / dzhng / smolagents /
# local-deep-research). The 8-10 min budget sits at the LOW end of the open-clone range.
FAST_MAX_STEPS            = 6      # hard step cap (open_deep_research supervisor=6; Perplexity caps 10)
FAST_MAX_QUERIES_PER_STEP = 4      # parallel queries fanned out per step (dzhng breadth=4)
FAST_MAX_RESULTS_PER_QUERY = 5     # SERP results per query (dzhng + gpt-researcher agree)
FAST_MIN_NEW_DOMAINS      = 2      # < this many NEW distinct domains in a step => diminishing returns
FAST_STALL_PATIENCE       = 1      # consecutive low-novelty steps tolerated before stopping
FAST_MIN_SOURCES_PER_SUBQ = 3      # distinct domains to mark a sub-question "green" (coverage gate)
FAST_MAX_SUBQUESTIONS     = 3      # sub-questions the decomposer emits in fast mode
FAST_CONTENT_TRIM_CHARS   = 25000  # per-page content cap before it enters context
FAST_TEMPERATURE          = 0.4    # planner/extractor temperature
FAST_RESERVE_SYNTH_FRAC   = 0.25   # fraction of budget reserved for the writer (distinct from
                                   # the token-valued RESERVE_FOR_SYNTHESIS below — do NOT merge)
FAST_TIMEOUT_S            = 600    # wall-clock safety net (belt-and-suspenders on the step cap)

# Breadth-shape parallel sub-researcher fan-out cap for the fast loop.
FAST_SUBRESEARCHER_K = 3

# Parallel subagent fan-out (Claude depth-1) — INTERFACES / CLR §CE.5,§CE.10
SUBAGENT_FANOUT_DEFAULT = 3
SUBAGENT_FANOUT_MAX = 20
```

(Then `grep -rn "AGENTIC_FAST_" src tests` — there should be no Python references after this; skill-markdown references are updated in Task 10. Leave the existing `RESERVE_FOR_SYNTHESIS = 40_000` token constant untouched.)

- [ ] **Step 4: Run to verify pass.**

Run: `uv run pytest tests/test_skills/test_router_effort.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Lint + types + commit.**

```bash
uv run ruff check src/bad_research/skills/routing_constants.py && uv run mypy src/bad_research/skills/routing_constants.py
git add src/bad_research/skills/routing_constants.py tests/test_skills/test_router_effort.py
git commit -m "feat(constants): evidence-anchored FAST_* stop-rule constants (XSTOP-1)"
```

---

## TASK 10: Fast skill — shape-aware hybrid loop + breadth fan-out

**Files:**
- Modify: `src/bad_research/skills/bad-research-fast.md` (the loop section; bounds; breadth branch)
- Test: `tests/test_skills/test_fast_skill.py`

- [ ] **Step 1: Update the fast-skill content test.** In `tests/test_skills/test_fast_skill.py`, update `test_fast_has_loop_bounds_and_planner_writer` to the new bounds and add a breadth assertion:

```python
def test_fast_has_loop_bounds_and_planner_writer(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    assert "FAST_MAX_STEPS" in body and "6" in body
    assert "600" in body                            # FAST_TIMEOUT_S wall-clock guard
    assert "planner" in body.lower() and "writer" in body.lower()
    assert "bad funnel-gather" in body or "funnel" in body.lower()
    assert "[N]" in body                            # per-sentence single-index cites
    assert "breadth" in body.lower()                # shape-aware fan-out
    assert "bad-research-fetcher" in body           # the parallel sub-researcher


def test_fast_has_auditable_stop_rule(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    assert "research_complete" in body              # keyless convergence flag
    assert "distinct domain" in body.lower()        # the new-domains novelty proxy
    assert "FAST_MIN_NEW_DOMAINS" in body and "FAST_MIN_SOURCES_PER_SUBQ" in body
    assert "checklist" in body.lower()              # per-sub-question coverage
```

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_fast_skill.py -v --no-cov`
Expected: FAIL — body still has old bounds (10/300/15) and no breadth branch.

- [ ] **Step 3: Rewrite the loop section of `bad-research-fast.md`.** Replace the `## The loop (planner → writer split)` section so it (a) reads `research/prompt-decomposition.json` `query_shape`, (b) maintains a per-sub-question coverage checklist + cumulative seen-domains/URLs sets, (c) branches on shape, (d) applies the auditable XSTOP-1 4-clause stop rule, and (e) passes the writer ONLY `(original_query, dedup'd evidence, prior learnings)` — never the planner trace, with a partial-answer-better-than-none fallback (Perplexity §R5.2/§R5.4). Use this content:

```markdown
## The loop (shape-aware, planner → writer split)

Read `query_shape` from `research/prompt-decomposition.json` and the one-paragraph
`scope_brief` (your framing). Then run by shape:

- **straightforward** → ONE bounded ReAct loop, ≤3 steps.
- **depth_first** → ONE bounded ReAct loop, up to `FAST_MAX_STEPS` (6) steps,
  reflect-then-narrow (each step deepens the prior).
- **breadth_first** → spawn K = min(n_independent_subq, `FAST_SUBRESEARCHER_K` = 3)
  parallel `bad-research-fetcher` sub-researchers, ONE per sub-question, each a
  bounded fetch loop (`FETCHER_TOOLCALL_CAP["light"]`, `FETCHER_TIMEOUT_S`). You are
  the LEADER and the ONLY writer (sub-researchers return claims+sources, never prose).
  Use the seven-piece subagent spawn contract from the entry skill. Gather all waves
  (per-wave deadline = `FETCHER_TIMEOUT_S`) before writing.

The single-loop body (straightforward/depth), persisting `(thought, action, observation)`
to `research/temp/react-trace.md`:

​```
step=0; stalled=0; deadline=now+600                      # FAST_TIMEOUT_S (wall-clock safety net)
next_queries = sub_questions[:FAST_MAX_QUERIES_PER_STEP]  # step-0 queries = the sub-questions
while step < 6 and next_queries and now < deadline:      # (1) hard cap = FAST_MAX_STEPS
    step += 1
    before = (len(seen_domains), len(seen_urls))
    ACT: fan out <=4 queries (FAST_MAX_QUERIES_PER_STEP), <=5 results each (FAST_MAX_RESULTS_PER_QUERY):
        bad funnel-gather "<q>" --mode light --vault-tag <tag> --max-queries 4 --read-top-k 12 --json
        for each NEW url: seen_domains.add(domain); add that domain to the checklist entry of the sub-q this query served
    OBSERVE: bad retrieve "<original verbatim query>" --mode light --top-k 12 --json
    new_domains, new_urls = deltas vs `before`           # loop counters, ZERO model calls
    if all sub-qs have >= FAST_MIN_SOURCES_PER_SUBQ (3) distinct domains: break          # (2) coverage complete
    if new_domains < FAST_MIN_NEW_DOMAINS (2) and new_urls < FAST_MIN_NEW_DOMAINS:
        stalled += 1
        if stalled >= FAST_STALL_PATIENCE (1): break                                     # (3) diminishing returns
    else: stalled = 0
    decision = REFLECT(...)                               # the reflect/stop JSON below (one model call)
    if decision.research_complete or decision.coverage_complete or decision.can_answer_confidently: break   # (4) model-declared
    next_queries = decision.next_queries[:FAST_MAX_QUERIES_PER_STEP]   # target WEAKEST sub-qs; never repeat/paraphrase a past query
# reserve FAST_RESERVE_SYNTH_FRAC (25%) of budget for the writer; a partial answer beats no answer
​```

**Math queries:** use `execute_python` in ACT, never compute in prose. The domain/URL deltas are
loop counters, not model claims — the stop is auditable even if the model lies about diminishing returns.

### Reflect/stop prompt (emit once per step — returns ONE JSON object)

Embed the verbatim reflect/stop prompt from the RE synthesis (`researchfms/teardowns/DEEP_RESEARCH_FAST_MODE_RE.md` PART 2.3, ~lines 534-575). It shows the planner the loop-computed `new_distinct_domains`/`new_distinct_urls` + the coverage checklist + trimmed step findings, enforces the HARD LIMITS (stop if every sub-q has FAST_MIN_SOURCES_PER_SUBQ+ domains / stop if new_domains < FAST_MIN_NEW_DOMAINS / stop if answerable), and returns ONLY:

    { "learnings": [...], "checklist_update": {"<sub-q>": <distinct-domain count>, ...},
      "coverage_complete": <bool>, "diminishing_returns": <bool>,
      "can_answer_confidently": <bool>, "research_complete": <bool>,
      "next_queries": [...] }   // [] when research_complete is true
```

Keep the `## Write (the writer split — system B)` section's Perplexity contract (per-sentence `[N]`, no `## References`, tables not lists); length scales up for breadth runs. Add three lifts the R5 deltas confirmed: (i) the writer receives ONLY `(original_query, dedup'd evidence, prior learnings)`, never the planner's raw trace (Perplexity §R5.2) — and once the writer starts, the loop does NOT fan out again (Grok terminal-synthesis seam, `GROK_HEAVY.md:598`); (ii) a word governor — ≤25 words verbatim from any single source, ≤1 quote/source (Claude copyright cap; OpenAI `[wordlim 200]`); (iii) partial-answer-better-than-none if the loop stopped early. Update `## Next step` to point at the slim citation-grounding pass (Task 11) before the slim critic.

- [ ] **Step 4: Run to verify pass.**

Run: `uv run pytest tests/test_skills/ -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/bad_research/skills/bad-research-fast.md tests/test_skills/test_fast_skill.py
git commit -m "feat(skills): fast loop is shape-aware + breadth sub-researcher fan-out"
```

---

## TASK 11: Slim citation-grounding pass for the fast route

**Files:**
- Modify: `src/bad_research/skills/bad-research-11.5-citation-verifier.md` (add a `### Slim mode (fast route)` section) — OR add the steps inline into `bad-research-fast.md`. This plan adds a slim section to 11.5 and calls it from the fast skill.
- Modify: `src/bad_research/skills/bad-research-fast.md` (`## Next step` invokes the slim grounding)
- Test: `tests/test_skills/` — content assertions

- [ ] **Step 1: Write the failing content test.** Add to `tests/test_skills/test_fast_skill.py`:

```python
def test_fast_runs_slim_citation_grounding_before_gate(skills_dir):
    body = (skills_dir / "bad-research-fast.md").read_text()
    # slim backward-grounding sits between the writer and the step-16 uncited gate
    assert "verify-citations" in body
    assert "uncited" in body.lower()
```

And add to `tests/test_skills/test_citation_verifier_skill.py` (create if absent):

```python
from tests.test_skills.validate import validate_skill


def test_citation_verifier_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-11.5-citation-verifier.md"
    assert validate_skill(p, known_skills) == []


def test_citation_verifier_has_slim_fast_mode(skills_dir):
    body = (skills_dir / "bad-research-11.5-citation-verifier.md").read_text()
    assert "slim" in body.lower() and "fast" in body.lower()
    assert "Edit" in body  # slim mode applies dispositions inline (no step-14 patcher)
    assert "common knowledge" in body.lower()       # the OpenAI 3-tier cite exemption
    assert "DROP-CITE" in body or "ACCEPT" in body   # the grounding-score thresholds
```

- [ ] **Step 2: Run to verify fail.**

Run: `uv run pytest tests/test_skills/test_fast_skill.py tests/test_skills/test_citation_verifier_skill.py -v --no-cov`
Expected: FAIL — no slim mode / no grounding call yet.

- [ ] **Step 3: Add the slim mode to 11.5.** In `bad-research-11.5-citation-verifier.md`, after the `## Procedure`, add:

```markdown
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

​```bash
bad verify-citations --report research/notes/final_report_<vault_tag>.md \
    --vault-tag <vault_tag> --json
​```

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
```

(Update the 11.5 `**Tier gate:**` line: it now also runs in slim mode for `fast`, not "SKIP for fast".)

- [ ] **Step 4: Wire it into the fast skill.** In `bad-research-fast.md` `## Next step`, sequence: after the writer, invoke `Skill(skill: "bad-research-11.5-citation-verifier")` (its **Slim mode** section), THEN the slim critic (`bad-research-12-critics`), THEN `bad-research-15-polish`, then the step-16 gate.

- [ ] **Step 5: Run to verify pass.**

Run: `uv run pytest tests/test_skills/ -v --no-cov`
Expected: PASS.

- [ ] **Step 6: Full green gate + commit.**

```bash
uv run pytest -q && uv run ruff check src tests && uv run mypy src
git add src/bad_research/skills/bad-research-11.5-citation-verifier.md src/bad_research/skills/bad-research-fast.md tests/test_skills/
git commit -m "feat(skills): slim citation-grounding pass on the fast route"
```

---

## Final verification (after Task 11)

- [ ] **Whole pytest suite green:** `uv run pytest -q` — all pass, coverage ≥ 80%. `uv run ruff check src tests` + `uv run mypy src` introduce **no NEW errors** vs `ee692ce` (pre-existing baseline ≈17 ruff in `tests/test_web/*` + ≈142 mypy — not ours to fix).
- [ ] **No residual old route strings:** `grep -rn "agentic-fast\|agentic_fast\|AGENTIC_FAST" src tests` returns nothing (skill prose + Python both swept).
- [ ] **Route literals consistent:** `grep -rn 'Literal\["fast"' src/bad_research` shows both `router.py` and `pipeline.py`.
- [ ] **CLI smoke:** `uv run bad route --help` lists `--fast` / `--full`; a multi-domain decomposition with `--fast` returns `{"route": "fast"}`.
- [ ] **Doctor (optional):** `uv run bad doctor` still reports the skill set wired (now `bad-research-fast`).

---

## Self-review notes (filled during writing)

- **Spec coverage:** §2 consolidation → Tasks 1-7; §3 hybrid loop → Tasks 9-10; §5 slim grounding → Task 11; §6 breadth fan-out → Task 10; §7 change map → all tasks; scope-brief (design §3) → Task 8. All covered.
- **Funnel-mode decision** recorded (kept `light`/`full` internal) — resolves the one ambiguity the route-consumer mapping surfaced.
- **Type consistency:** `Route = Literal["fast","full"]` defined identically in `router.py` and `pipeline.py`; `FAST_MAX_STEPS/CALLS/TIMEOUT_S/SUBRESEARCHER_K` used consistently in constants (Task 9) and skill body (Task 10).
- **Coverage-gate caveat** (`--no-cov` on single-test runs) stated in Conventions and used in every single-test command.
