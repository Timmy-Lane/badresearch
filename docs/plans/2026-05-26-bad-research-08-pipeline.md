# Bad Research — Plan 08: Pipeline + Skills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. You have full tool access (Read, Grep, Bash, Write, Edit). "Pure prompt" / "the test is structural" phrasing below restricts the *kind of test*, not your tools — read source freely.

**Goal:** Build the Claude-Code-skill orchestration layer for Bad Research — the prompt files Claude reads, the Python install machinery that drops them into `~/.claude/` (user-global by default), and the glue that wires the new deterministic backends (funnel, retrieval, grounding) into the pipeline. Concretely: (1) four NEW skills — `bad-research-0.5-clarify`, `bad-research-query-router`, `bad-research-agentic-fast`, `bad-research-fresh-review`; (2) MODIFY the kept stage skills so width-sweep calls `funnel.gather()`, depth/gap-fetch use tiered browse, synthesize renders grounded citations from retrieval top-chunks, plus a new `bad-research-11.5-citation-verifier` stage and a deterministic no-uncited-claim gate folded into step 16; (3) the `bad install` CLI (user-global default, `--project` opt-in, lazy step-skill install); (4) MCP tool additions exposing research + vault tools; (5) the entry-skill routing table (agentic-fast / light / full → stage sequences).

**Architecture:** This plan is the *fork rename + enhancement* of hyperresearch's skill/install/MCP layer. The package is `bad_research` (fork of `hyperresearch/src/hyperresearch/`). Skill prompts are pure Markdown with two-field frontmatter (`name`, `description`); they instruct Claude — they contain no executable code. The install machinery lives in `core/hooks.py` (forked, renamed `hyperresearch-*` → `bad-research-*`, default target flipped from project `.claude/` to user-global `~/.claude/`). The entry skill is a router that loads ONE stage skill at a time (the context-rot defense, invariant #2). New deterministic Python (`funnel.gather()`, `RetrievalEngine.search()`, `CitationVerifier.verify()`, `fetch_tiered()`) is exposed to the orchestrator as CLI subcommands + MCP tools so the skill prompts can call them via `Bash`/`Skill` — preserving the "disk is memory, context is scratchpad" invariant (the model never holds raw pages; it reads top-chunks + `[[note-id]]` pointers).

**Tech Stack:** Python 3.11+, Typer (CLI, reused from hyperresearch), FastMCP (`mcp>=1.6`), pytest. Skill prompts are Markdown. The install path tests assert files land under a temp `HOME` (`~/.claude/skills/bad-research/`, `~/.claude/agents/`, `~/.claude/settings.json`). A structural validator (`tests/test_skills/validate.py`) parses skill frontmatter + checks required sections + resolves cross-references. Consumes seams from Plans 01 (`llm/config`), 02 (`retrieval`), 04 (`browse.fetch_tiered`), 06 (`grounding.CitationVerifier`), 07 (`funnel.gather`).

---

## Dependencies on other plans

This plan is the *integration layer* — it wires together backends built by Plans 01–07. The consumed signatures are **frozen verbatim in `INTERFACES.md`** — this plan conforms to them, it does not redefine them. The funnel seam (Plan 07) is the one with a subtle shape: `gather()` is **async, dependency-injected (`FunnelDeps`), and returns `list[Chunk]`** (NOT a custom result object). This plan's `bad funnel-gather` CLI is the thin wrapper that builds `FunnelDeps`, runs the async `gather()`, and serializes the returned chunks + their `note_id`s to JSON for the skill prompts. The CLI's JSON envelope (a `FunnelEnvelope`, owned by THIS plan — not a cross-plan type) is the only new shape introduced, and it lives in `cli/research.py`, never in `INTERFACES.md`.

```python
# Plan 07 — funnel/orchestrator.py  (FROZEN in INTERFACES.md — consume verbatim)
@dataclass
class FunnelDeps:            # injected seams: providers / fetcher / postfetch_filter / vault / retrieval
    providers: list; fetcher: object; postfetch_filter: object; vault: object; retrieval: object
async def gather(query: str, *, mode: Literal["light","full"],
                 deps: FunnelDeps, queries: list[SearchQuery] | None = None) -> list[Chunk]: ...
# 6-stage funnel (fan-out→dedup→rank→read Tier0-3→filter+store→rerank). Returns reranked top
# Chunk[] + [[note-id]] pointers — NEVER raw page bodies. Stages A-E are $0 model cost.

# This plan's CLI envelope (cli/research.py — NOT a shared type):
@dataclass
class FunnelEnvelope:
    note_ids: list[str]      # derived from chunk.note_id (unique, order-preserving)
    top_chunks: list[dict]   # asdict(Chunk) for each returned chunk — what the model reads
    n_read: int              # len(note_ids); the ≤80 ceiling is enforced inside gather()

# Plan 02 — retrieval/engine.py  (consumed by synthesize + agentic-fast)
class RetrievalEngine:
    def search(self, query: str, *, mode: Literal["light","full"], top_k: int) -> list[Chunk]: ...

# Plan 06 — grounding/verifier.py  (consumed by step 11.5 + step-16 gate)
@dataclass
class VerifyResult:
    sentence: str
    cite_ids: list[str]                       # [[note-id]] / [N] targets in the sentence
    disposition: Literal["supported","partial","unsupported","contradicted"]
    verify_score: float                       # 0..1
    quoted_support: str | None
class CitationVerifier:
    def verify_report(self, report_path: str, *, vault_tag: str) -> list[VerifyResult]: ...
def uncited_claim_gate(report_path: str, anchors_db: str) -> list[dict]: ...  # [] = pass; deterministic, $0

# Plan 04 — browse/__init__.py  (consumed by depth + gap-fetch)
def fetch_tiered(url: str, *, tier_max: int, instruction: str | None = None,
                 schema: dict | None = None) -> WebResult: ...

# Plan 01 — config.py
@dataclass
class BadResearchConfig: ...   # vault_root, model_tiers, reasoning_effort, budget_usd, cheap
```

The skill prompts call these via two surfaces this plan creates:
- **CLI subcommands** (Task 12): `bad funnel-gather`, `bad retrieve`, `bad verify-citations`, `bad uncited-gate`, `bad route` — JSON-out wrappers around the seams above, callable from a skill's `Bash` step.
- **MCP tools** (Task 11): `funnel_gather`, `retrieve_chunks`, `verify_citations`, `route_query`, plus the inherited vault tools.

If a producing plan has NOT landed, Task 0 stubs the consumed function to return a deterministic fixture so this plan's tests pass in isolation; the real impl replaces the stub when its plan lands.

---

## Frozen constants (from `INTERFACES.md` + dossier 05 — cite verbatim, never re-derive)

```python
# bad_research/skills/routing_constants.py  (Task 2 — used by the router CLI + tests)
AGENTIC_FAST_MAX_STEPS = 10        # Perplexity max_steps hard cap            [INTERFACES; DR-loops §3,§5]
AGENTIC_FAST_MAX_CALLS = 15        # Claude per-subagent soft call cap         [DR-loops §5; CLR §14]
AGENTIC_FAST_TIMEOUT_S = 300       # Claude 300s per-agent wall                [DR-loops §5; CLR §CE.3]
SUBAGENT_FANOUT_DEFAULT = 3        # Claude default parallel subagents         [INTERFACES; CLR §CE.5]
SUBAGENT_FANOUT_MAX = 20           # Claude max (depth-1)                       [INTERFACES; CLR §CE.10]
CLARIFY_MAX_QUESTIONS = 3          # OpenAI clarifier cap                      [DR-loops §1; ODR §5]
READ_TOP_K_CEILING = 80            # funnel read ceiling (degrades past it)    [INTERFACES; HR]
RELEVANCE_GATE = 0.70              # chunk drop threshold                      [INTERFACES; Perplexity]
# Router heuristic thresholds (DR-loops §9.2 — the verbatim decision tree)
ROUTER_AGENTIC_MAX_ATOMIC = 2      # ≤2 atomic items → agentic-fast            [DR-loops §9.2]
ROUTER_LIGHT_MAX_ATOMIC = 6        # 3–6 atomic items → light                  [DR-loops §9.2]
# >6, or contested/argumentative/time_periods/multi-domain → full
```

The router classes **the decompose output**, not raw text. It reuses Step-1's `prompt-decomposition.json` fields (`atomic_items`/`sub_questions`+`entities`, `response_format`, `time_periods`, contradiction-likely terms). No new classifier model is added — the heuristic is free (DR-loops §9.2: "The signal is hyperresearch's OWN Stage-1 decomposition output — no new classifier needed").

---

## File Structure

The package is the fork `src/bad_research/` (of `hyperresearch/src/hyperresearch/`). This plan touches:

**NEW skill prompts** (Markdown, `src/bad_research/skills/`):

| File | Role | Tiers |
|---|---|---|
| `bad-research-0.5-clarify.md` | Triage-tier clarifier (≤3 Qs, default-proceed); writes `research/clarify.json`. Skipped for agentic-fast + `--auto`. | full, light |
| `bad-research-query-router.md` | Classifies decompose output → `agentic-fast` \| `light` \| `full`; writes `route` into `prompt-decomposition.json`. | all |
| `bad-research-agentic-fast.md` | Bounded ReAct loop (`max_steps≤10`), planner→writer, over `funnel.gather()` + `RetrievalEngine.search()` + vault. Single-pass writer, per-sentence `[N]`. | agentic-fast |
| `bad-research-fresh-review.md` | One bounded fresh-context reviewer pass before polish (catches what in-context critics miss). Single pass, not a loop. | full |
| `bad-research-11.5-citation-verifier.md` | Stage 11.5: runs `CitationVerifier`; dispositions feed the patcher. Tool-locked `[Read]`. | full |

**MODIFIED skill prompts** (rename `hyperresearch` → `bad-research` throughout + the wiring edits):

| File | Change |
|---|---|
| `bad-research.md` (entry skill) | New routing table (agentic-fast/light/full → stage sequences); bootstrap calls clarify + router; lazy step-skill install via `bad install --steps-only`; recovery map gains new artifacts; Stage-16 gate. |
| `bad-research-2-width-sweep.md` | Replace the manual fetcher-batch procedure with a call to `bad funnel-gather` (the §6 funnel); model reads only `top_chunks`. |
| `bad-research-5-depth-investigation.md` | Depth investigators escalate hard sources via `bad fetch --tier-max 3` (Tier 0→3 browse). |
| `bad-research-11-synthesize.md` | Synthesizer reads retrieval top-chunks + renders grounded `[[note-id]]`/`[N]` citations bound to `claim_anchors`. |
| `bad-research-13-gap-fetch.md` | Gap-fetch uses tiered browse for critic-identified gaps. |
| `bad-research-16-readability-audit.md` | Append the deterministic no-uncited-claim hard gate (`bad uncited-gate`) as a ship-block. |

**MODIFIED Python:**

| File | Change |
|---|---|
| `core/hooks.py` | Rename roster + step list `bad-research-*`; add 5 new step-skill names to `_BAD_RESEARCH_STEP_SKILLS`; add fresh-reviewer agent; flip default install target to `~/.claude/`; entry-skill installs there. |
| `cli/install.py` | `bad install` — user-global default; `--project` opt-in; `--steps-only` lazy. |
| `cli/__init__.py` | Register `bad`/`badr` app; add `funnel-gather`, `retrieve`, `verify-citations`, `uncited-gate`, `route` subcommands. |
| `mcp/server.py` | Add `funnel_gather`, `retrieve_chunks`, `verify_citations`, `route_query` MCP tools; rename server to `bad-research`. |

**Tests** (`tests/test_skills/`, `tests/test_install/`, `tests/test_cli/`, `tests/test_mcp/`):
`validate.py` (the structural validator), `test_skill_frontmatter.py`, `test_skill_references.py`, `test_install_global.py`, `test_install_project.py`, `test_router.py`, `test_cli_subcommands.py`, `test_mcp_tools.py`, `tests/test_skills/conftest.py`.

---

## Task 0: Fork rename baseline + consumed-seam stubs

**Files:**
- Create: `tests/test_skills/__init__.py`, `tests/test_install/__init__.py`, `tests/test_mcp/__init__.py`
- Create (only if producing plan not landed): stub modules under `src/bad_research/{funnel,retrieval,grounding,browse}/`

- [ ] **Step 1: Confirm the fork exists**

Run: `test -d ultimate-research/bad-research/src/bad_research && echo "fork present" || echo "fork missing — Plan 01 creates it"`
Expected: `fork present`. If missing, this plan assumes Plan 01's Task 0 (the fork + rename) has landed. Do NOT re-fork here; coordinate with Plan 01. For the rest of this plan, all paths are under `ultimate-research/bad-research/`.

- [ ] **Step 2: Create test package markers**

`tests/test_skills/__init__.py`, `tests/test_install/__init__.py`, `tests/test_mcp/__init__.py`: empty files.

- [ ] **Step 3: Stub the consumed seams if their plans have not landed**

For each of `funnel.gather`, `retrieval.RetrievalEngine.search`, `grounding.CitationVerifier`/`uncited_claim_gate`, `browse.fetch_tiered` — if the module does not import, create a minimal deterministic stub matching the FROZEN `INTERFACES.md` signature (async, DI, returns `list[Chunk]`) so this plan's tests run in isolation. Example `src/bad_research/funnel/__init__.py` stub:

```python
"""STUB — replaced when Plan 07 lands. Deterministic fixture for Plan-08 tests.
Signature is frozen in INTERFACES.md: async, DI via FunnelDeps, returns list[Chunk]."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

@dataclass
class FunnelDeps:
    providers: list; fetcher: object; postfetch_filter: object; vault: object; retrieval: object

async def gather(query, *, mode, deps, queries=None):  # pragma: no cover
    return []   # list[Chunk]
```

Run: `python -c "import asyncio; from bad_research.funnel import gather, FunnelDeps; print('ok')"`
Expected: `ok`. (The retrieval/grounding/browse stubs mirror their own frozen `INTERFACES.md` signatures.)

Also stub the DI-builder helpers the CLI's `run_funnel` calls (Task 12) so `cli/research.py` imports in isolation. Add to `cli/research.py` (or a tiny `cli/_deps.py`) when Plans 03/04/05 haven't landed:
```python
def _build_providers(cfg): return []           # Plan 03 fills this
def _build_tiered_fetcher(cfg): return None     # Plan 04 fills this
def _build_postfetch(cfg): return lambda r: None  # Plan 05 fills this
```
These are replaced by the real builders when their plans land; the funnel stub returns `[]` so `run_funnel` produces an empty envelope in isolation (the CLI test asserts shape, not content).

- [ ] **Step 4: Commit**

```bash
git add tests/test_skills tests/test_install tests/test_mcp src/bad_research/funnel
git commit -m "chore(pipeline): test markers + consumed-seam stubs for Plan-08 isolation"
```

---

## Task 1: Add Plan-08 routing constants to INTERFACES.md (no new shared type)

**Files:**
- Modify: `ultimate-research/INTERFACES.md`

**This plan introduces NO new cross-plan seam type.** The funnel/retrieval/grounding/browse seams are already frozen in `INTERFACES.md`; this plan conforms to them. The only thing added to the contract is the routing constants this plan owns (so other plans see them) — the router heuristic, the agentic-fast bounds, and the user-global install default. The `FunnelEnvelope` is a CLI-internal shape and deliberately stays OUT of `INTERFACES.md`.

- [ ] **Step 1: Add routing constants to the frozen-constants table**

Append rows to the `## Frozen constants` table in `INTERFACES.md`:

```
| router agentic-max-atomic / light-max-atomic | `2 / 6` | DR-loops §9.2 |
| clarifier max questions | `3` | DR-loops §1 / ODR §5 |
| agentic-fast max_calls / timeout_s | `15 / 300` | DR-loops §5 / CLR §CE.3 |
| install default target | `~/.claude/` (user-global) | SPEC §12 |
```

- [ ] **Step 2: Verify the markdown still parses (no broken table) and the funnel seam is unchanged**

Run: `python -c "t=open('ultimate-research/INTERFACES.md').read(); assert 'router agentic-max-atomic' in t and 'install default target' in t and 'async def gather' in t; print('ok')"`
Expected: `ok` (asserts the routing rows landed AND the frozen async `gather` signature is still present, untouched).

- [ ] **Step 3: Commit**

```bash
git add ultimate-research/INTERFACES.md
git commit -m "docs(interfaces): add Plan-08 routing/install constants (no new seam type)"
```

---

## Task 2: Routing constants module + the router heuristic

**Files:**
- Create: `src/bad_research/skills/routing_constants.py`
- Create: `src/bad_research/skills/router.py`
- Test: `tests/test_skills/test_router.py`

- [ ] **Step 1: Write the failing test**

`tests/test_skills/test_router.py`:
```python
from bad_research.skills.router import classify_route
from bad_research.skills import routing_constants as R


def _decomp(**kw):
    base = dict(sub_questions=["q1"], entities=[], time_periods=[],
                response_format="short", contradiction_terms=[], domains=["tech"])
    base.update(kw); return base


def test_constants_match_interfaces():
    assert R.AGENTIC_FAST_MAX_STEPS == 10
    assert R.AGENTIC_FAST_MAX_CALLS == 15
    assert R.AGENTIC_FAST_TIMEOUT_S == 300
    assert R.SUBAGENT_FANOUT_DEFAULT == 3 and R.SUBAGENT_FANOUT_MAX == 20
    assert R.CLARIFY_MAX_QUESTIONS == 3
    assert R.READ_TOP_K_CEILING == 80
    assert R.ROUTER_AGENTIC_MAX_ATOMIC == 2 and R.ROUTER_LIGHT_MAX_ATOMIC == 6


def test_trivial_single_domain_routes_agentic_fast():
    d = _decomp(sub_questions=["what is the capital of France"], response_format="short")
    assert classify_route(d) == "agentic-fast"


def test_two_atomic_no_tension_routes_agentic_fast():
    d = _decomp(sub_questions=["q1", "q2"], response_format="short")
    assert classify_route(d) == "agentic-fast"


def test_structured_midsize_routes_light():
    d = _decomp(sub_questions=["q1", "q2", "q3", "q4"], response_format="structured")
    assert classify_route(d) == "light"


def test_time_periods_force_full():
    # period-pinned primary sources need Lens D + step-8 coverage → full
    d = _decomp(sub_questions=["q1"], response_format="short",
                time_periods=[{"period": "Q3 2024"}])
    assert classify_route(d) == "full"


def test_contested_argumentative_routes_full():
    d = _decomp(sub_questions=["q%d" % i for i in range(8)],
                response_format="argumentative", contradiction_terms=["versus"])
    assert classify_route(d) == "full"


def test_multi_domain_routes_full():
    d = _decomp(sub_questions=["q1", "q2"], response_format="structured",
                domains=["bio", "finance", "law"])
    assert classify_route(d) == "full"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.skills.router'`

- [ ] **Step 3: Write the implementation**

`src/bad_research/skills/routing_constants.py`:
```python
"""Frozen routing + bound constants for the Bad Research pipeline.

Every value cites INTERFACES.md / dossier 05 (DR-loops). DO NOT re-derive."""
from __future__ import annotations

# Agentic-fast ReAct loop bounds (Perplexity max_steps + Claude guards) — DR-loops §3,§5
AGENTIC_FAST_MAX_STEPS = 10
AGENTIC_FAST_MAX_CALLS = 15
AGENTIC_FAST_TIMEOUT_S = 300

# Parallel subagent fan-out (Claude depth-1) — INTERFACES / CLR §CE.5,§CE.10
SUBAGENT_FANOUT_DEFAULT = 3
SUBAGENT_FANOUT_MAX = 20

# Clarifier (OpenAI default-proceed) — DR-loops §1 / ODR §5
CLARIFY_MAX_QUESTIONS = 3

# Funnel + retrieval — INTERFACES
READ_TOP_K_CEILING = 80
RELEVANCE_GATE = 0.70

# Router heuristic boundaries — DR-loops §9.2 (the verbatim decision tree)
ROUTER_AGENTIC_MAX_ATOMIC = 2
ROUTER_LIGHT_MAX_ATOMIC = 6
```

`src/bad_research/skills/router.py`:
```python
"""Query router — classify the Step-1 decompose output into a pipeline mode.

Reuses the existing atomic-item analysis (no new classifier). The decision
tree is verbatim from DR-loops §9.2:

  agentic-fast  if atomic_items <= 2 AND no contradiction terms AND no time_periods
                AND response_format == "short" AND single domain
  light         elif response_format == "structured" OR atomic_items 3-6 OR mild tension
  full          else (multi-domain, contested, argumentative, time_periods, >=7 items)
"""
from __future__ import annotations

from typing import Literal

from bad_research.skills import routing_constants as R

Route = Literal["agentic-fast", "light", "full"]


def _atomic_count(decomp: dict) -> int:
    # atomic items = sub_questions + named entities (the Step-1 taxonomy)
    return len(decomp.get("sub_questions") or []) + len(decomp.get("entities") or [])


def classify_route(decomp: dict) -> Route:
    n = _atomic_count(decomp)
    fmt = decomp.get("response_format", "structured")
    time_periods = decomp.get("time_periods") or []
    contradiction = decomp.get("contradiction_terms") or []
    domains = decomp.get("domains") or []
    multi_domain = len(domains) >= 3

    # FULL: anything that needs Lens D primaries, dialectics, or breadth across domains.
    if (time_periods or fmt == "argumentative" or contradiction
            or multi_domain or n > R.ROUTER_LIGHT_MAX_ATOMIC):
        return "full"

    # AGENTIC-FAST: trivial, bounded, single-domain, short.
    if (n <= R.ROUTER_AGENTIC_MAX_ATOMIC and not contradiction
            and not time_periods and fmt == "short" and not multi_domain):
        return "agentic-fast"

    # LIGHT: the middle band — structured coverage or 3-6 atomic items.
    return "light"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_router.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/routing_constants.py src/bad_research/skills/router.py tests/test_skills/test_router.py
git commit -m "feat(router): query-router heuristic (decompose → agentic-fast|light|full) + frozen bounds"
```

---

## Task 3: The skill structural validator (the "test" for prompt files)

**Files:**
- Create: `tests/test_skills/validate.py`
- Create: `tests/test_skills/conftest.py`
- Test: `tests/test_skills/test_validate_self.py`

Skill `.md` files are PROMPTS — the rigorous test for them is a structural validator (frontmatter parses, required sections present, cross-references resolve), not behavioral assertions. This task builds that validator; Tasks 4–10 each run it on the skill they write.

- [ ] **Step 1: Write the validator + its self-test (failing)**

`tests/test_skills/validate.py`:
```python
"""Structural validator for Bad Research skill prompts.

A skill .md is valid iff:
  - it has YAML frontmatter delimited by `---` with `name` and `description`
  - `name` matches the filename slug (sans .md)
  - it contains every required section header for its kind (entry vs step)
  - every `Skill(skill: "X")` / `bad-research-N-...` reference resolves to a
    skill that exists in the same skills dir (or is the entry skill)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ENTRY_REQUIRED = ["## Tier routing", "## Bootstrap", "## Recovery"]
STEP_REQUIRED = ["**Tier gate:**", "**Goal:**", "## Recover state", "## Exit criterion"]


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        raise ValueError("no frontmatter block")
    fm = yaml.safe_load(m.group(1))
    if "name" not in fm or "description" not in fm:
        raise ValueError("frontmatter missing name/description")
    return fm


def referenced_skills(text: str) -> set[str]:
    refs = set(re.findall(r'Skill\(skill:\s*"([a-z0-9.\-]+)"\)', text))
    refs |= set(re.findall(r"\b(bad-research-[0-9.]+-[a-z\-]+)\b", text))
    return refs


def validate_skill(path: Path, known_skills: set[str]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    slug = path.stem if path.name != "SKILL.md" else path.parent.name
    try:
        fm = parse_frontmatter(text)
    except ValueError as e:
        return [f"{path.name}: {e}"]
    if fm["name"] != slug:
        errors.append(f"{path.name}: name '{fm['name']}' != slug '{slug}'")
    required = ENTRY_REQUIRED if fm["name"] in ("bad-research", "hyperresearch") else STEP_REQUIRED
    for section in required:
        if section not in text:
            errors.append(f"{path.name}: missing required section '{section}'")
    for ref in referenced_skills(text):
        if ref not in known_skills and ref != "bad-research":
            errors.append(f"{path.name}: unresolved skill reference '{ref}'")
    return errors
```

`tests/test_skills/conftest.py`:
```python
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "src" / "bad_research" / "skills"


@pytest.fixture
def skills_dir() -> Path:
    return SKILLS_DIR


@pytest.fixture
def known_skills(skills_dir: Path) -> set[str]:
    return {p.stem for p in skills_dir.glob("bad-research*.md")} | {"bad-research"}
```

`tests/test_skills/test_validate_self.py`:
```python
from tests.test_skills.validate import parse_frontmatter, referenced_skills, validate_skill


def test_parse_frontmatter_extracts_name():
    fm = parse_frontmatter("---\nname: x\ndescription: y\n---\nbody")
    assert fm["name"] == "x"


def test_parse_frontmatter_rejects_missing():
    import pytest
    with pytest.raises(ValueError):
        parse_frontmatter("no frontmatter here")


def test_referenced_skills_finds_skill_calls():
    text = 'Invoke `Skill(skill: "bad-research-2-width-sweep")`.'
    assert "bad-research-2-width-sweep" in referenced_skills(text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_validate_self.py -v`
Expected: FAIL with `ModuleNotFoundError` (validate.py not yet importable as a package path) — if so, add `pip install pyyaml` and ensure `tests/` is importable (it has `__init__.py` from Task 0). Re-run.
Expected after fix: FAIL only if validate.py logic is wrong; otherwise PASS once the file exists.

- [ ] **Step 3: Verify it passes**

Run: `pytest tests/test_skills/test_validate_self.py -v`
Expected: PASS (3 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_skills/validate.py tests/test_skills/conftest.py tests/test_skills/test_validate_self.py
git commit -m "test(skills): structural validator (frontmatter, required sections, ref resolution)"
```

---

## Task 4: NEW skill — `bad-research-0.5-clarify.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-0.5-clarify.md`
- Test: `tests/test_skills/test_clarify_skill.py`

The triage-tier clarifier (DR-loops §1): ≤3 questions, default-to-proceed, skipped for agentic-fast and `--auto`. Verbatim bias copied from OpenAI's host prompt: "if you don't recognize a concept/name, assume it is a browsing request and proceed."

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_clarify_skill.py`:
```python
from pathlib import Path

from tests.test_skills.validate import validate_skill


def test_clarify_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-0.5-clarify.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_clarify_has_default_proceed_and_cap(skills_dir):
    body = (skills_dir / "bad-research-0.5-clarify.md").read_text()
    assert "default" in body.lower() and "proceed" in body.lower()
    assert "3" in body  # max 3 questions
    assert "research/clarify.json" in body
    assert "triage" in body.lower()  # triage-tier model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_clarify_skill.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Write the complete skill prompt**

`src/bad_research/skills/bad-research-0.5-clarify.md`:
```markdown
---
name: bad-research-0.5-clarify
description: >
  Stage 0.5 of the Bad Research pipeline. A triage-tier clarifier that decides
  whether the query is ready for an expensive autonomous run or whether ONE
  round of clarification would materially improve it. Default-to-proceed:
  ambiguity is rare; most queries proceed silently. Skipped entirely for
  agentic-fast mode and for --auto / wrapped runs (the GOSPEL query is binding).
  Invoked via Skill tool from the entry skill BEFORE step 1.
---

# Step 0.5 — Clarify (triage tier, default-proceed)

**Tier gate:** Runs for `light` and `full` interactive runs only. SKIP for
`agentic-fast` (it is fast by design — no gate). SKIP when
`research/wrapper_contract.json` exists or `--auto` is set (the wrapper/GOSPEL
query is binding and must not be questioned).

**Goal:** spend one cheap triage-tier (Haiku-class) decision to avoid wasting a
$5–120 run on a misread query. Fire a clarification ONLY on genuine ambiguity;
otherwise proceed silently and distill a clean `brief`.

## Recover state

The orchestrator bootstrap has produced:
- `research/scaffold.md` — vault_tag, modality, wrapper requirements
- `research/query-<vault_tag>.md` — canonical research query (GOSPEL)

Read both. If `research/wrapper_contract.json` exists OR the run is `--auto`,
write `{"action":"proceed","skipped":"wrapper/auto"}` to `research/clarify.json`
and exit immediately — do NOT question a binding query.

## Procedure

1. Read the verbatim query end to end.

2. Decide `clarify | proceed` using this rule (a triage-tier judgement, ONE call):

   **Clarify (emit 1–3 questions) ONLY if the query has:**
   - ambiguous acronyms or names with multiple plausible referents (which "Mercury"? the planet, the element, the car, the Freddie?)
   - unbounded scope ("tell me about X" with no constraint, time window, or angle)
   - an undefined time window where the answer materially depends on it

   **DEFAULT TO PROCEED.** If you do not recognize a concept or name, assume it
   is a browsing request and proceed — do NOT ask the user to define it. Never
   ask more than **3** questions. When in doubt, proceed: a wrong clarification
   costs a round-trip; a missed one costs at most a slightly-wider search.

3. Distill the `brief` — a 1–3 paragraph paraphrase of the research question
   with scope + constraints made explicit. This is the clean handoff payload;
   it does NOT replace the GOSPEL query (the pipeline still cites the verbatim
   query everywhere), it sharpens the scaffold.

4. Write `research/clarify.json`:
   ```json
   {
     "action": "clarify" | "proceed",
     "questions": ["...", "..."],   // [] when action == "proceed", max 3
     "brief": "<1-3 paragraph distilled research question with scope + constraints>"
   }
   ```

5. If `action == "clarify"` AND the run is interactive: surface the questions to
   the user, collect answers, append them to `research/query-<vault_tag>.md`
   under a `## Clarifications` section (the answers become part of GOSPEL), then
   re-run this decision once. After one round, always proceed.

6. Append the `brief` to `research/scaffold.md` under a `## Brief` subsection.

## Exit criterion

- `research/clarify.json` exists with a valid `action`
- If `clarify`, at most 3 questions; if interactive, answers folded into the query file
- `research/scaffold.md` has a `## Brief` subsection

## Next step

Return to the entry skill (`bad-research`). Invoke step 1:
`Skill(skill: "bad-research-1-decompose")`.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_clarify_skill.py -v`
Expected: PASS (2 passed). The validator treats this as a step skill (has Tier gate / Goal / Recover state / Exit criterion).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-0.5-clarify.md tests/test_skills/test_clarify_skill.py
git commit -m "feat(skills): bad-research-0.5-clarify (triage clarifier, default-proceed, <=3 Qs)"
```

---

## Task 5: NEW skill — `bad-research-query-router.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-query-router.md`
- Test: `tests/test_skills/test_router_skill.py`

The router skill calls `bad route --decomposition research/prompt-decomposition.json` (the CLI wrapper around `classify_route`, Task 12) and writes the result back into the decomposition JSON. The heuristic is the Python from Task 2 — the skill is the prompt that invokes it and acts on the result.

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_router_skill.py`:
```python
from tests.test_skills.validate import validate_skill


def test_router_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-query-router.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_router_skill_names_three_routes_and_cli(skills_dir):
    body = (skills_dir / "bad-research-query-router.md").read_text()
    for route in ("agentic-fast", "light", "full"):
        assert route in body
    assert "bad route" in body  # invokes the deterministic CLI heuristic
    assert "prompt-decomposition.json" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_router_skill.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Write the complete skill prompt**

`src/bad_research/skills/bad-research-query-router.md`:
```markdown
---
name: bad-research-query-router
description: >
  Stage 1.5 of the Bad Research pipeline. Classifies the Step-1 decompose
  output into one of three modes — agentic-fast | light | full — using a free
  deterministic heuristic over the decomposition (no new model call). Writes the
  chosen `route` into research/prompt-decomposition.json; the entry skill reads
  it to pick the stage sequence. Invoked via Skill tool from the entry skill
  after step 1 completes.
---

# Step 1.5 — Query router

**Tier gate:** Runs for ALL runs (it IS the tier/mode decision). The router
never down-routes a query that step 1 marked `full` for a stated reason —
contested topics, time_periods, and argumentative formats always route `full`.

**Goal:** route trivial/single-domain queries to the cheap bounded ReAct
fast-mode, mid-size structured queries to `light`, and complex/contested
queries to the full 16-stage pipeline. The signal is hyperresearch's OWN
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
   It applies the verbatim DR-loops §9.2 decision tree:
   - **agentic-fast** if atomic_items ≤ 2 AND no contradiction terms AND no
     time_periods AND response_format == "short" AND single domain
   - **light** elif response_format == "structured" OR atomic_items 3–6
   - **full** else (multi-domain, contested, argumentative, time_periods, ≥7 items)

   The command prints `{"route": "agentic-fast"|"light"|"full", "reason": "..."}`.

2. **Honor the existing tier.** If step 1 set `pipeline_tier: "full"` for a
   stated reason (time_periods present, argumentative, contested), the router
   MUST NOT down-route below `full`. The router can only refine `light` ↔
   `agentic-fast` and up-route to `full`; never silently demote a `full`.

3. Write the chosen route back into the decomposition:
   ```bash
   bad route --decomposition research/prompt-decomposition.json --apply --json
   ```
   This adds a top-level `"route"` field to `research/prompt-decomposition.json`.

4. Record a one-line rationale in `research/scaffold.md` under a `## Route
   rationale` subsection.

## Exit criterion

- `research/prompt-decomposition.json` has a `"route"` field ∈ {agentic-fast, light, full}
- A route never demotes a justified `full`
- `research/scaffold.md` has a `## Route rationale` subsection

## Next step

Return to the entry skill (`bad-research`). Sequence by route:
- **agentic-fast** → `Skill(skill: "bad-research-agentic-fast")` (then straight to step 15 polish)
- **light** → `Skill(skill: "bad-research-2-width-sweep")` (light path)
- **full** → `Skill(skill: "bad-research-2-width-sweep")` (full path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_router_skill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-query-router.md tests/test_skills/test_router_skill.py
git commit -m "feat(skills): bad-research-query-router (decompose → agentic-fast|light|full)"
```

---

## Task 6: NEW skill — `bad-research-agentic-fast.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-agentic-fast.md`
- Test: `tests/test_skills/test_agentic_fast_skill.py`

The bounded ReAct fast-mode (DR-loops §9.2 reimplementable loop): `max_steps≤10`, planner→writer split, per-step query fan-out, terminate on model-done OR step==10, Claude per-call guards (300s, ≤15 calls). It runs over `funnel.gather()` + `RetrievalEngine.search()` + the vault — the SAME backends as the full pipeline, just bounded.

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_agentic_fast_skill.py`:
```python
from tests.test_skills.validate import validate_skill


def test_agentic_fast_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-agentic-fast.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_agentic_fast_has_loop_bounds_and_planner_writer(skills_dir):
    body = (skills_dir / "bad-research-agentic-fast.md").read_text()
    assert "max_steps" in body and "10" in body
    assert "300" in body and "15" in body  # Claude guards
    assert "planner" in body.lower() and "writer" in body.lower()
    assert "bad funnel-gather" in body or "funnel" in body.lower()
    assert "[N]" in body  # per-sentence single-index cites
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_agentic_fast_skill.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Write the complete skill prompt**

`src/bad_research/skills/bad-research-agentic-fast.md`:
```markdown
---
name: bad-research-agentic-fast
description: >
  The bounded-ReAct fast mode of Bad Research. A step-bounded (max_steps ≤ 10)
  planner→writer loop over the same providers + retrieval + vault as the full
  pipeline, for fast/cheap answers to trivial single-domain queries. Single-pass
  writer with per-sentence [N] citations. Replaces the entire 16-stage pipeline
  for queries the router classified `agentic-fast`. Invoked via Skill tool from
  the entry skill (agentic-fast route only).
---

# Agentic-fast — bounded ReAct (the Perplexity engine)

**Tier gate:** Runs ONLY for the `agentic-fast` route. It does NOT run the
§6 funnel as a fixed stage; it does a bounded loop that *calls* the funnel /
retrieval per step. No clarifier, no decompose-time fan-out — fast by design.

**Goal:** answer a trivial, bounded, single-domain query in < 3 minutes and
$1–5 with grounded per-sentence citations. Terminate when the model judges
coverage complete OR the step cap is hit — whichever comes first.

## Recover state

Read:
- `research/query-<vault_tag>.md` — canonical query (GOSPEL)
- `research/prompt-decomposition.json` — confirm `route == "agentic-fast"`

If `route != "agentic-fast"`, STOP and return to the entry skill — you were
invoked by mistake.

## The loop (planner → writer split, DR-loops §9.2)

You are the **planner** (system A). Run a ReAct loop, persisting an auditable
`(thought, action, observation)` trace to `research/temp/react-trace.md`:

```
step = 0; deadline = now + 300s            # AGENTIC_FAST_TIMEOUT_S
while step < 10 and now < deadline:        # AGENTIC_FAST_MAX_STEPS
    step += 1
    THINK: write one paragraph to react-trace.md — what's still unknown, what to fetch.
    if you judge coverage complete: break   # model-judged stop
    ACT (one step = a LIST of queries, fanned out, NOT one search):
        bad funnel-gather "<query>" --mode light --vault-tag <tag> \
            --max-queries 6 --read-top-k 12 --json
      # the funnel fans out, dedups, ranks, reads (Tier 0→3), filters, chunks,
      # stores in vault, and returns top_chunks — you read ONLY top_chunks.
    OBSERVE: read the returned top_chunks; rerank against the ORIGINAL query:
        bad retrieve "<original verbatim query>" --mode light --top-k 12 --json
    append the (thought, action, observation) to react-trace.md
    if total_tool_calls >= 15: break        # AGENTIC_FAST_MAX_CALLS guard
```

**Hard guards (Claude §CE.5 safety net):** never exceed 10 steps, 15 tool
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

Return to the entry skill (`bad-research`). Agentic-fast skips straight to
polish: `Skill(skill: "bad-research-15-polish")`, then the step-16 gate.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_agentic_fast_skill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-agentic-fast.md tests/test_skills/test_agentic_fast_skill.py
git commit -m "feat(skills): bad-research-agentic-fast (bounded ReAct, max_steps<=10, planner->writer)"
```

---

## Task 7: NEW skill — `bad-research-fresh-review.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-fresh-review.md`
- Test: `tests/test_skills/test_fresh_review_skill.py`

One bounded fresh-context reviewer pass before polish (SPEC §4: "catches issues the in-context critics miss; Anthropic/Devin pattern; single pass, not a loop"). It runs after the patcher (step 14), before polish (step 15), full tier only. Tool-locked `[Read]` — it reports findings; it does not edit (the patcher already ran; remaining structural issues escalate to the orchestrator).

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_fresh_review_skill.py`:
```python
from tests.test_skills.validate import validate_skill


def test_fresh_review_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-fresh-review.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_fresh_review_is_single_pass_and_read_only(skills_dir):
    body = (skills_dir / "bad-research-fresh-review.md").read_text()
    assert "single pass" in body.lower() or "one pass" in body.lower()
    assert "not a loop" in body.lower()
    assert "fresh" in body.lower()  # fresh-context reviewer
    assert "research/temp/fresh-review.json" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_fresh_review_skill.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Write the complete skill prompt**

`src/bad_research/skills/bad-research-fresh-review.md`:
```markdown
---
name: bad-research-fresh-review
description: >
  Stage 14.5 of the Bad Research pipeline. ONE bounded fresh-context reviewer
  pass over the patched final report, before polish. A fresh Opus session with
  zero pipeline-dispatch context catches whole-report issues the in-context
  critics (who saw the report grow) miss — narrative drift, an unanswered
  sub-question, a thesis the body contradicts. Single pass, NOT a loop. Invoked
  via Skill tool from the entry skill after step 14 (full tier only).
---

# Step 14.5 — Fresh-context review (single pass)

**Tier gate:** SKIP for `light` and `agentic-fast`. Runs for `full` only, after
the patcher (step 14), before polish (step 15).

**Goal:** spend ONE fresh reviewer pass to catch what the in-context critics
missed. The step-12 critics watched the report grow over a long context; a
fresh reader with no dispatch history reads it cold and catches drift. This is
the Anthropic/Devin "fresh-context review before ship" pattern — explicitly a
single pass, **not a loop** (a loop is the Excluded grader-ensemble cost).

## Recover state

This step spawns a fresh-context reviewer subagent. The reviewer is tool-locked
to `[Read]` — it reports findings; it does NOT edit. Read for the spawn:
- `research/query-<vault_tag>.md` — GOSPEL query
- `research/prompt-decomposition.json` — required_section_headings, sub_questions
- `research/notes/final_report_<vault_tag>.md` — the patched report

## Procedure

1. Spawn ONE `bad-research-fresh-reviewer` subagent (fresh Opus, `[Read]` lock,
   no pipeline context). Standard 3-piece spawn contract:
   ```
   subagent_type: bad-research-fresh-reviewer
   prompt: |
     RESEARCH QUERY (verbatim, gospel):
     > {{paste research/query-<vault_tag>.md body}}

     PIPELINE POSITION: You are step 14.5 of the Bad Research pipeline — a
     fresh-context final reviewer. The report has been drafted, synthesized,
     critiqued, and patched. You read it COLD, with no memory of how it was
     built, and report whole-report issues the in-context critics missed.
     You are tool-locked to [Read]. You do NOT edit. After you return, the
     orchestrator applies surgical Edits for your critical findings, then
     step 15 polishes.

     YOUR INPUTS:
     - query_file_path: research/query-<vault_tag>.md
     - report_path: research/notes/final_report_<vault_tag>.md
     - decomposition_path: research/prompt-decomposition.json
     - output_path: research/temp/fresh-review.json
   ```
   The reviewer reads the report once, end to end, and emits findings to
   `research/temp/fresh-review.json`:
   ```json
   {"findings": [
     {"severity": "critical|major|minor",
      "kind": "drift|unanswered-subq|thesis-contradiction|structural|redundancy",
      "where": "<H2 heading or line region>",
      "issue": "<what is wrong>",
      "fix_hint": "<minimal surgical fix>"}]}
   ```

2. **Apply ONLY critical/major findings**, surgically, via `Edit` on the report
   (PATCH NEVER REGENERATE — the post-step-11 invariant holds). Minor findings
   are left for polish (step 15) to absorb. Do NOT re-spawn the reviewer; this
   is a single pass.

3. If a critical finding requires a structural rewrite (not a surgical Edit),
   record it in `research/temp/fresh-review.json` as `applied: false` and note
   it — do not regenerate.

## Exit criterion

- `research/temp/fresh-review.json` exists
- All critical/major surgically-applicable findings applied via Edit
- The report was NOT regenerated; the reviewer ran exactly once

## Next step

Return to the entry skill (`bad-research`). Invoke step 15:
`Skill(skill: "bad-research-15-polish")`.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_fresh_review_skill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-fresh-review.md tests/test_skills/test_fresh_review_skill.py
git commit -m "feat(skills): bad-research-fresh-review (single fresh-context pass, Read-locked)"
```

---

## Task 8: NEW skill — `bad-research-11.5-citation-verifier.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-11.5-citation-verifier.md`
- Test: `tests/test_skills/test_citation_verifier_skill.py`

Stage 11.5 (SPEC §9). Runs `CitationVerifier.verify_report()` (Plan 06) — cheapest-first: byte-identity → local NLI → triage-LLM-judge for the neutral band → re-fetch arbitration (gated). Dispositions: supported→keep, partial→hedge, unsupported→drop cite, contradicted→contradiction-graph. The verifier itself is Python (Plan 06); this skill is the prompt that runs it via `bad verify-citations` and routes dispositions to the patcher. Tool-locked `[Read]`.

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_citation_verifier_skill.py`:
```python
from tests.test_skills.validate import validate_skill


def test_citation_verifier_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-11.5-citation-verifier.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_citation_verifier_names_dispositions_and_cli(skills_dir):
    body = (skills_dir / "bad-research-11.5-citation-verifier.md").read_text()
    for disp in ("supported", "partial", "unsupported", "contradicted"):
        assert disp in body
    assert "bad verify-citations" in body
    assert "claim_anchors" in body
    assert "[Read]" in body  # tool-lock
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_citation_verifier_skill.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Write the complete skill prompt**

`src/bad_research/skills/bad-research-11.5-citation-verifier.md`:
```markdown
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills/test_citation_verifier_skill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/bad-research-11.5-citation-verifier.md tests/test_skills/test_citation_verifier_skill.py
git commit -m "feat(skills): bad-research-11.5-citation-verifier (backward grounding, Read-locked)"
```

---

## Task 9: MODIFY stage skills — wire the new backends

**Files:**
- Modify: `src/bad_research/skills/bad-research-2-width-sweep.md`
- Modify: `src/bad_research/skills/bad-research-5-depth-investigation.md`
- Modify: `src/bad_research/skills/bad-research-11-synthesize.md`
- Modify: `src/bad_research/skills/bad-research-13-gap-fetch.md`
- Modify: `src/bad_research/skills/bad-research-16-readability-audit.md`
- Test: `tests/test_skills/test_modified_stages.py`

These are the *kept* hyperresearch stage skills (already renamed `bad-research-*` by Plan 01's fork) with surgical wiring edits — NOT rewrites. Each edit adds a call to the new Python backend while preserving the existing procedure.

- [ ] **Step 1: Write the failing structural test**

`tests/test_skills/test_modified_stages.py`:
```python
from tests.test_skills.validate import validate_skill

STAGES = [
    "bad-research-2-width-sweep.md",
    "bad-research-5-depth-investigation.md",
    "bad-research-11-synthesize.md",
    "bad-research-13-gap-fetch.md",
    "bad-research-16-readability-audit.md",
]


def test_all_modified_stages_valid(skills_dir, known_skills):
    for s in STAGES:
        p = skills_dir / s
        assert p.exists(), s
        assert validate_skill(p, known_skills) == [], s


def test_width_sweep_calls_funnel(skills_dir):
    body = (skills_dir / "bad-research-2-width-sweep.md").read_text()
    assert "bad funnel-gather" in body
    assert "top_chunks" in body or "top-chunks" in body


def test_depth_uses_tiered_browse(skills_dir):
    body = (skills_dir / "bad-research-5-depth-investigation.md").read_text()
    assert "--tier-max" in body


def test_synthesize_renders_grounded_citations(skills_dir):
    body = (skills_dir / "bad-research-11-synthesize.md").read_text()
    assert "claim_anchors" in body or "grounded" in body.lower()
    assert "bad retrieve" in body  # synthesizer reads retrieval top-chunks


def test_gap_fetch_uses_tiered_browse(skills_dir):
    body = (skills_dir / "bad-research-13-gap-fetch.md").read_text()
    assert "--tier-max" in body


def test_step16_has_uncited_gate(skills_dir):
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    assert "bad uncited-gate" in body
    assert "ship-block" in body.lower() or "ship block" in body.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills/test_modified_stages.py -v`
Expected: FAIL (the wiring edits not yet made — and the files may not yet be renamed `bad-research-*` if Plan 01 hasn't run; if missing, copy the `hyperresearch-N-*.md` source and rename frontmatter `name:` first, then edit).

- [ ] **Step 3: Width-sweep — replace the manual fetcher procedure with the funnel call**

In `bad-research-2-width-sweep.md`, replace **Step 2.2–2.4** (the manual URL-queue/batch/parallel-fetcher procedure) with a single funnel call. Add, after Step 2.1 (the search plan stays — it feeds the funnel):

```markdown
## Step 2.2 — Run the scraper funnel

The width-sweep no longer hand-dispatches fetcher batches. It hands the search
plan to the deterministic six-stage funnel (fan-out → dedup → rank → read
Tier 0→3 → filter junk → chunk+store → rerank). The model reads ONLY the
funnel's `top_chunks` — never raw pages. This is the "disk is memory, context
is scratchpad" invariant: sources scale (45→80) while context stays flat.

```bash
bad funnel-gather --query-file research/query-<vault_tag>.md \
    --search-plan research/temp/search-plan.md \
    --mode <light|full> --vault-tag <vault_tag> \
    --reasoning-effort <minimal|low|medium|high> --json
```

Returns `FunnelEnvelope` JSON: `{note_ids, top_chunks, n_read}`.
- `note_ids` — sources written to the vault this run.
- `top_chunks` — the reranked chunks (≤ TOP_CHUNKS for the mode) the model may
  read. Read these; do NOT re-read full pages.
- `n_read` ≤ 80 (the load-bearing read ceiling — the funnel enforces it internally;
  reading past it degrades synthesis).

**Fan-out constants are indexed by mode** (the funnel applies them internally via
its `FunnelConfig`): `light` = 12–20 queries / 1–2 providers / read top 12–20;
`full` = 40–100 queries / 2–4 providers / read top 60–80.
```

Then update **Step 2.5 (coverage check)** — the funnel returns reranked chunks,
not a coverage map, so the orchestrator computes coverage by mapping
`note_ids` → atomic items (same well/adequate/thin/uncovered logic as before),
and triggers a second, smaller `funnel-gather` call with a gap-targeted query
for any `thin`/`uncovered` item. Keep Step 2.6 (redundancy audit) — the funnel's
filter handles >60%-overlap, but the audit's `derivative-of` tagging is still
useful for `full`.

- [ ] **Step 4: Depth-investigation — tiered browse for hard sources**

In `bad-research-5-depth-investigation.md`, in the depth-investigator spawn
section, add to the investigator's instructions:

```markdown
**Hard sources (JS-heavy, login-walled, anti-bot):** when a load-bearing
source fails Tier-0/1 fetch (returns junk or a login wall), escalate it
through the Tier 0→3 browse ladder:

```bash
bad fetch "<url>" --tier-max 3 --tag <vault_tag> \
    --instruction "extract the section about <topic>" --json
```

Tier 0 = HTTP, Tier 1 = crawl4ai (JS), Tier 2 = typed extract (AgentQL/
LLM-extract), Tier 3 = agentic browse (Browser-Use self-host). Escalation is
gated by `looks_like_junk()` / `looks_like_login_wall()` — only hard pages
climb the ladder; cheap pages stop at Tier 0.
```

- [ ] **Step 5: Synthesize — read retrieval top-chunks + grounded citation render**

In `bad-research-11-synthesize.md`, add a new subsection after Step 11.4
(synthesis outline), before the verification gate:

```markdown
## Step 11.4b — Pull grounded evidence for the synthesizer

The synthesizer writes only from evidence, never from the orchestrator's
reasoning (the Perplexity planner→writer split). Before spawning it, pull the
top-ranked grounded chunks for each planned section so the synthesizer cites
against `claim_anchors`, not its own recall:

```bash
bad retrieve "<section topic / sub-question>" --mode full --top-k 20 --json
```

For each returned chunk, the `note_id` + `char_start`/`char_end` are the
citation anchor. Write the section→chunks map to
`research/temp/synthesis-evidence.md`; pass its path to the synthesizer.

**Grounded citation rendering** (the synthesizer's spawn instructions, added to
the existing citation-rendering block):
- Every `[[note-id]]` / `[N]` the synthesizer emits MUST correspond to a chunk
  in `synthesis-evidence.md` whose `quoted_support` is in the `claim_anchors`
  table. A claim with no locatable anchor is NOT written (forward binding).
- The CitationVerifier (step 11.5) will check every cite byte-for-byte after —
  fabricated cites are caught and dropped, so emit only anchored ones.
```

The synthesizer spawn template gains `synthesis_evidence_path:
research/temp/synthesis-evidence.md` in its `YOUR INPUTS`.

- [ ] **Step 6: Gap-fetch — tiered browse**

In `bad-research-13-gap-fetch.md`, replace the raw fetch instruction with the
tiered-browse call (same pattern as Step 4): critic-identified gap URLs fetch
via `bad fetch "<url>" --tier-max 3 --tag <vault_tag> --json`.

- [ ] **Step 7: Step 16 — append the deterministic no-uncited-claim gate**

In `bad-research-16-readability-audit.md`, before the "Next step" section, add:

```markdown
## Step 16.5 — No-uncited-claim hard gate (deterministic ship-block)

After readability edits, run the deterministic ($0) grounding gate. It is a
ship-block: the report does NOT ship if any non-trivial claim lacks a
verifiable citation resolving to a `claim_anchors` row.

```bash
bad uncited-gate --report research/notes/final_report_<vault_tag>.md \
    --vault-tag <vault_tag> --json
```

- Output `{"uncited": []}` → PASS, ship.
- Output `{"uncited": [{"sentence": "...", "reason": "..."}]}` → BLOCK. For each
  uncited non-trivial claim, either (a) add a citation via a surgical Edit if a
  supporting note exists, (b) run one targeted `bad fetch` to ground it, or
  (c) soften the claim to a non-assertion. Re-run the gate until `uncited == []`.

This is deterministic, so it is a hard pass/fail — never "good enough."
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_skills/test_modified_stages.py -v`
Expected: PASS (6 passed)

- [ ] **Step 9: Commit**

```bash
git add src/bad_research/skills/bad-research-2-width-sweep.md \
        src/bad_research/skills/bad-research-5-depth-investigation.md \
        src/bad_research/skills/bad-research-11-synthesize.md \
        src/bad_research/skills/bad-research-13-gap-fetch.md \
        src/bad_research/skills/bad-research-16-readability-audit.md \
        tests/test_skills/test_modified_stages.py
git commit -m "feat(skills): wire funnel.gather, tiered browse, grounded synthesize, uncited gate into stage skills"
```

---

## Task 10: MODIFY entry skill + step list + fresh-reviewer agent

**Files:**
- Modify: `src/bad_research/skills/bad-research.md` (entry skill)
- Modify: `src/bad_research/core/hooks.py` (`_BAD_RESEARCH_STEP_SKILLS`, agent roster, install target)
- Test: `tests/test_skills/test_entry_skill.py`, `tests/test_install/test_step_list.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_skills/test_entry_skill.py`:
```python
from tests.test_skills.validate import validate_skill


def test_entry_skill_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_entry_skill_has_three_route_sequences(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    # the routing table must name all three modes and their stage sequences
    for route in ("agentic-fast", "light", "full"):
        assert route in body
    # new stages must appear in the entry routing
    assert "bad-research-0.5-clarify" in body
    assert "bad-research-query-router" in body
    assert "bad-research-agentic-fast" in body
    assert "bad-research-11.5-citation-verifier" in body
    assert "bad-research-fresh-review" in body
    # lazy step-skill install on first invocation
    assert "bad install --steps-only" in body
    # the deterministic ship gate
    assert "uncited" in body.lower()
```

`tests/test_install/test_step_list.py`:
```python
from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS


def test_step_list_has_new_stages():
    s = set(_BAD_RESEARCH_STEP_SKILLS)
    assert "bad-research-0.5-clarify" in s
    assert "bad-research-query-router" in s
    assert "bad-research-agentic-fast" in s
    assert "bad-research-11.5-citation-verifier" in s
    assert "bad-research-fresh-review" in s
    # the original 16 kept (renamed)
    assert "bad-research-1-decompose" in s
    assert "bad-research-16-readability-audit" in s
    # ordering: clarify before decompose, router after decompose
    assert _BAD_RESEARCH_STEP_SKILLS.index("bad-research-0.5-clarify") < \
           _BAD_RESEARCH_STEP_SKILLS.index("bad-research-1-decompose")
    assert _BAD_RESEARCH_STEP_SKILLS.index("bad-research-1-decompose") < \
           _BAD_RESEARCH_STEP_SKILLS.index("bad-research-query-router")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skills/test_entry_skill.py tests/test_install/test_step_list.py -v`
Expected: FAIL.

- [ ] **Step 3: Update `_BAD_RESEARCH_STEP_SKILLS` in `core/hooks.py`**

Replace the (renamed) step list so it includes the 5 new skills in pipeline order:
```python
_BAD_RESEARCH_STEP_SKILLS = [
    "bad-research-0.5-clarify",
    "bad-research-1-decompose",
    "bad-research-query-router",
    "bad-research-2-width-sweep",
    "bad-research-3-contradiction-graph",
    "bad-research-4-loci-analysis",
    "bad-research-5-depth-investigation",
    "bad-research-6-cross-locus-reconcile",
    "bad-research-7-source-tensions",
    "bad-research-8-corpus-critic",
    "bad-research-9-evidence-digest",
    "bad-research-10-triple-draft",
    "bad-research-11-synthesize",
    "bad-research-11.5-citation-verifier",
    "bad-research-12-critics",
    "bad-research-13-gap-fetch",
    "bad-research-14-patcher",
    "bad-research-fresh-review",
    "bad-research-15-polish",
    "bad-research-16-readability-audit",
    "bad-research-agentic-fast",
]
```
(21 entries: the 16 kept + 5 new. The installer auto-discovers any name in this list, copies `<name>.md` → `.claude/skills/<name>/SKILL.md`, and prunes any `bad-research-*` dir not in the list — verbatim mechanism from `_install_hyperresearch_step_skills`.)

- [ ] **Step 4: Add the fresh-reviewer agent to the roster**

Add a `FRESH_REVIEWER_AGENT` string constant (frontmatter `name: bad-research-fresh-reviewer`, `model: opus`, `tools: Read`, `color: ...`) modeled on the existing critic agents but tool-locked to `[Read]` only. Add `_install_fresh_reviewer_agent(vault_root, hpr_path)` and append it to BOTH install loops (`install_hooks` and `install_global_hooks`) — the §3.3 recipe. (The agentic-fast loop does not need a new subagent — the orchestrator runs the ReAct loop itself; the clarifier/router run as orchestrator-side skills, no subagent.)

- [ ] **Step 5: Rewrite the entry skill routing table + bootstrap**

In `bad-research.md`, replace the tier-routing table with the three-mode table:

```markdown
## Mode routing

Step 1 decomposes; the query-router (step 1.5) classifies the decomposition
into a `route`. After step 1.5, read `research/prompt-decomposition.json` for
`route`, then sequence:

| Route | Stage sequence | Cost | Time |
|---|---|---|---|
| `agentic-fast` | 0.5(skip) → 1 → 1.5 → agentic-fast → 15 → 16(+gate) | ~$1–5 | <3 min |
| `light` | 0.5 → 1 → 1.5 → 2(funnel) → 10(single draft) → 15 → 16(+gate) | ~$5–15 | ~30–40 min |
| `full` | 0.5 → 1 → 1.5 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 11.5 → 12 → 13 → 14 → 14.5(fresh-review) → 15 → 16(+gate) | ~$60–120 | ~1.5–2.5 h |

**RESPECT THE ROUTE.** agentic-fast is the cheap bounded ReAct loop, not a
degraded full run. full always runs 11.5 (citation verifier) and 14.5
(fresh-review). The deterministic no-uncited-claim gate in step 16 is a
ship-block for ALL routes.
```

In the bootstrap section, add after vault/step-skills auto-init:
- **Step-skills check**: `If .claude/skills/bad-research-1-decompose/SKILL.md
  doesn't exist, run bad install --steps-only . --json` (lazy install on first
  `/bad-research` invocation — the user-global install ships only the entry
  skill + agents; step skills materialize per-project on first run).
- After bootstrap, invoke `Skill(skill: "bad-research-0.5-clarify")` (unless
  `--auto`/wrapped → skip clarify, go to step 1).

Update the recovery artifact map to add: step 0.5 → `research/clarify.json`;
step 1.5 → `route` field in `prompt-decomposition.json`; step 11.5 →
`research/temp/citation-verify-actions.json`; step 14.5 →
`research/temp/fresh-review.json`; agentic-fast → `research/temp/react-trace.md`.

Add a "## Recovery" header section and keep the "## Tier routing" header
present (the validator's `ENTRY_REQUIRED` expects `## Tier routing`,
`## Bootstrap`, `## Recovery` — keep all three as headers; the mode table can
live under `## Tier routing`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_skills/test_entry_skill.py tests/test_install/test_step_list.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Run the full skill-validation sweep**

`tests/test_skills/test_all_skills_valid.py`:
```python
from tests.test_skills.validate import validate_skill


def test_every_skill_validates(skills_dir, known_skills):
    errors = []
    for p in sorted(skills_dir.glob("bad-research*.md")):
        errors += validate_skill(p, known_skills)
    assert errors == [], "\n".join(errors)
```
Run: `pytest tests/test_skills/ -v`
Expected: PASS — every skill validates, all references resolve.

- [ ] **Step 8: Commit**

```bash
git add src/bad_research/skills/bad-research.md src/bad_research/core/hooks.py \
        tests/test_skills/test_entry_skill.py tests/test_skills/test_all_skills_valid.py \
        tests/test_install/test_step_list.py
git commit -m "feat(skills): entry-skill 3-mode routing + step list (21) + fresh-reviewer agent"
```

---

## Task 11: MCP tool additions

**Files:**
- Modify: `src/bad_research/mcp/server.py`
- Test: `tests/test_mcp/test_mcp_tools.py`

Expose the research + vault backends as MCP tools so a Claude Code session (or any MCP client) can call them. Inherit the 13 vault tools (renamed server `bad-research`); add 4 research tools.

- [ ] **Step 1: Write the failing test**

`tests/test_mcp/test_mcp_tools.py`:
```python
import asyncio


def test_server_named_bad_research():
    from bad_research.mcp.server import server
    assert server.name == "bad-research"


def test_research_tools_registered():
    from bad_research.mcp.server import server
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    # inherited vault tools
    assert {"search_notes", "read_note", "fetch_url"} <= names
    # new research tools
    assert {"funnel_gather", "retrieve_chunks", "verify_citations", "route_query"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp/test_mcp_tools.py -v`
Expected: FAIL — server still named `hyperresearch`, new tools absent.

- [ ] **Step 3: Add the tools**

In `mcp/server.py`, rename the server to `FastMCP("bad-research", instructions=...)` and add (each `@server.tool()`-decorated, returning a JSON string, calling the seam):

```python
@server.tool()
def route_query(decomposition_path: str) -> str:
    """Classify a Step-1 decomposition into a pipeline route (agentic-fast|light|full)."""
    import json
    from bad_research.skills.router import classify_route
    decomp = json.loads(open(decomposition_path, encoding="utf-8").read())
    return json.dumps({"route": classify_route(decomp)})


@server.tool()
def funnel_gather(query: str, mode: str = "light", vault_tag: str = "") -> str:
    """Run the scraper funnel: fan-out→dedup→rank→read(Tier0-3)→filter→chunk→rerank.
    Returns FunnelEnvelope JSON {note_ids, top_chunks, n_read}. The model reads top_chunks only."""
    import json
    from bad_research.cli.research import run_funnel   # builds FunnelDeps, runs async gather()
    return json.dumps(run_funnel(query, mode=mode, vault_tag=vault_tag))


@server.tool()
def retrieve_chunks(query: str, mode: str = "full", top_k: int = 20) -> str:
    """Hybrid retrieval: vector+BM25 fuse (alpha=0.7) → rerank → 0.70 gate. Returns top_k Chunks."""
    import json
    from dataclasses import asdict
    from bad_research.retrieval.engine import get_engine
    chunks = get_engine().search(query, mode=mode, top_k=top_k)
    return json.dumps([asdict(c) for c in chunks], default=str)


@server.tool()
def verify_citations(report_path: str, vault_tag: str) -> str:
    """Run the CitationVerifier over a report. Returns per-sentence dispositions."""
    import json
    from dataclasses import asdict
    from bad_research.grounding.verifier import CitationVerifier
    results = CitationVerifier().verify_report(report_path, vault_tag=vault_tag)
    return json.dumps([asdict(r) for r in results], default=str)
```

Guard imports of not-yet-landed seams so the server still imports when a
producing plan is absent (each tool lazy-imports inside the function — a missing
backend fails only when that tool is *called*, not at registration). The Task-0
stubs make the import succeed in isolation.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp/test_mcp_tools.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/mcp/server.py tests/test_mcp/test_mcp_tools.py
git commit -m "feat(mcp): bad-research server + funnel_gather/retrieve_chunks/verify_citations/route_query tools"
```

---

## Task 12: CLI subcommands (the skill→Python bridge) + `bad route --apply`

**Files:**
- Modify: `src/bad_research/cli/__init__.py`
- Create: `src/bad_research/cli/research.py` (the new subcommands)
- Test: `tests/test_cli/test_cli_subcommands.py`

The skill prompts call these via `Bash`. Each is a thin JSON-out Typer command over a seam.

- [ ] **Step 1: Write the failing test**

`tests/test_cli/test_cli_subcommands.py`:
```python
import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_route_command_classifies(tmp_path):
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": ["what is X"], "entities": [],
                             "response_format": "short", "time_periods": [],
                             "contradiction_terms": [], "domains": ["tech"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["route"] == "agentic-fast"


def test_route_apply_writes_field(tmp_path):
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": ["q%d" % i for i in range(8)],
                             "entities": [], "response_format": "argumentative",
                             "time_periods": [], "contradiction_terms": ["vs"],
                             "domains": ["a"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--apply", "--json"])
    assert res.exit_code == 0
    assert json.loads(d.read_text())["route"] == "full"


def test_uncited_gate_command_registered():
    res = runner.invoke(app, ["uncited-gate", "--help"])
    assert res.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli/test_cli_subcommands.py -v`
Expected: FAIL — commands not registered.

- [ ] **Step 3: Implement `cli/research.py`**

```python
"""Research-pipeline CLI subcommands — JSON-out bridges the skills call via Bash."""
from __future__ import annotations

import json
from pathlib import Path

import typer


def route_cmd(
    decomposition: str = typer.Option(..., "--decomposition"),
    apply: bool = typer.Option(False, "--apply"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    from bad_research.skills.router import classify_route
    path = Path(decomposition)
    decomp = json.loads(path.read_text(encoding="utf-8"))
    route = classify_route(decomp)
    if apply:
        decomp["route"] = route
        path.write_text(json.dumps(decomp, indent=2), encoding="utf-8")
    out = {"route": route, "applied": apply}
    typer.echo(json.dumps(out) if json_output else f"route: {route}")


def run_funnel(query: str, *, mode: str, vault_tag: str) -> dict:
    """Build FunnelDeps from config + run the FROZEN async gather(), then collapse
    the returned list[Chunk] into a FunnelEnvelope dict. Shared by CLI + MCP."""
    import asyncio
    from dataclasses import asdict
    from bad_research.funnel import gather, FunnelDeps
    from bad_research.config import BadResearchConfig
    from bad_research.retrieval.engine import get_engine
    from bad_research.core.vault import Vault
    # assemble the DI seams (providers/fetcher/postfetch_filter/vault/retrieval)
    cfg = BadResearchConfig()
    deps = FunnelDeps(
        providers=_build_providers(cfg),          # Plan 03 cascade survivors
        fetcher=_build_tiered_fetcher(cfg),        # Plan 04 fetch_tiered
        postfetch_filter=_build_postfetch(cfg),    # Plan 05
        vault=Vault.discover(),
        retrieval=get_engine(),                    # Plan 02
    )
    chunks = asyncio.run(gather(query, mode=mode, deps=deps))
    note_ids, seen = [], set()
    for c in chunks:
        if c.note_id not in seen:
            seen.add(c.note_id); note_ids.append(c.note_id)
    return {"note_ids": note_ids, "top_chunks": [asdict(c) for c in chunks], "n_read": len(note_ids)}


def funnel_gather_cmd(
    query_file: str = typer.Option(..., "--query-file"),
    search_plan: str = typer.Option(None, "--search-plan"),  # informational; gather builds its own queries
    mode: str = typer.Option("light", "--mode"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    query = Path(query_file).read_text(encoding="utf-8")
    typer.echo(json.dumps(run_funnel(query, mode=mode, vault_tag=vault_tag), default=str))


def retrieve_cmd(
    query: str = typer.Argument(...),
    mode: str = typer.Option("full", "--mode"),
    top_k: int = typer.Option(20, "--top-k"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    from dataclasses import asdict
    from bad_research.retrieval.engine import get_engine
    chunks = get_engine().search(query, mode=mode, top_k=top_k)
    typer.echo(json.dumps([asdict(c) for c in chunks], default=str))


def verify_citations_cmd(
    report: str = typer.Option(..., "--report"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    from dataclasses import asdict
    from bad_research.grounding.verifier import CitationVerifier
    res = CitationVerifier().verify_report(report, vault_tag=vault_tag)
    typer.echo(json.dumps([asdict(r) for r in res], default=str))


def uncited_gate_cmd(
    report: str = typer.Option(..., "--report"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    from bad_research.grounding.verifier import uncited_claim_gate
    from bad_research.core.vault import Vault
    anchors_db = str(Vault.discover().root / ".bad-research" / "bad-research.db")
    uncited = uncited_claim_gate(report, anchors_db)
    typer.echo(json.dumps({"uncited": uncited}))
    if uncited:
        raise typer.Exit(1)   # non-zero exit makes the ship-block visible to the skill
```

- [ ] **Step 4: Register them in `cli/__init__.py`**

After the existing `app.command(...)` registrations, add:
```python
from bad_research.cli.research import (
    funnel_gather_cmd, retrieve_cmd, route_cmd, uncited_gate_cmd, verify_citations_cmd,
)
app.command("route")(route_cmd)
app.command("funnel-gather")(funnel_gather_cmd)
app.command("retrieve")(retrieve_cmd)
app.command("verify-citations")(verify_citations_cmd)
app.command("uncited-gate")(uncited_gate_cmd)
```
(`app` is already the `bad`/`badr` Typer app via the renamed `pyproject.toml` entry points from Plan 01.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cli/test_cli_subcommands.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/cli/research.py src/bad_research/cli/__init__.py tests/test_cli/test_cli_subcommands.py
git commit -m "feat(cli): route/funnel-gather/retrieve/verify-citations/uncited-gate subcommands"
```

---

## Task 13: The `bad install` command — user-global default

**Files:**
- Modify: `src/bad_research/cli/install.py`
- Modify: `src/bad_research/core/hooks.py` (default install target → `~/.claude/`)
- Test: `tests/test_install/test_install_global.py`, `tests/test_install/test_install_project.py`

The headline behavior change (SPEC §12 / invariant #3): `bad install` defaults to user-global (`~/.claude/`), `--project` opts into project-local `.claude/`. This flips hyperresearch's project-default. The global install ships the entry skill + agents + a PreToolUse hook into `~/.claude/`; step skills lazy-install per-project on first `/bad-research`.

- [ ] **Step 1: Write the failing install-path tests**

`tests/test_install/test_install_global.py`:
```python
import json

from bad_research.core.hooks import install_global_hooks


def test_global_install_drops_entry_skill(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    # entry skill lands at ~/.claude/skills/bad-research/SKILL.md
    entry = home / ".claude" / "skills" / "bad-research" / "SKILL.md"
    assert entry.exists()
    assert "name: bad-research" in entry.read_text(encoding="utf-8")


def test_global_install_drops_agents(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    agents = home / ".claude" / "agents"
    assert (agents / "bad-research-fresh-reviewer.md").exists()
    # the kept critics, renamed
    assert (agents / "bad-research-synthesizer.md").exists()


def test_global_install_skips_step_skills(tmp_path):
    # step skills must NOT install globally (system-reminder bloat) — lazy per-project
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    assert not (home / ".claude" / "skills" / "bad-research-1-decompose").exists()


def test_global_install_writes_pretooluse_hook(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    settings = home / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text(encoding="utf-8"))
    cmds = [h["command"] for entry in data["hooks"]["PreToolUse"] for h in entry["hooks"]]
    assert any("bad-research" in c for c in cmds)
```

`tests/test_install/test_install_project.py`:
```python
from bad_research.core.hooks import install_hooks


def test_project_install_drops_all_step_skills(tmp_path):
    root = tmp_path / "proj"
    (root / ".bad-research").mkdir(parents=True)  # vault marker
    install_hooks(root, hpr_path="bad")
    skills = root / ".claude" / "skills"
    assert (skills / "bad-research-1-decompose" / "SKILL.md").exists()
    assert (skills / "bad-research-agentic-fast" / "SKILL.md").exists()
    assert (skills / "bad-research" / "SKILL.md").exists()  # entry skill too
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install/ -v`
Expected: FAIL (renamed functions not yet behaving as specified).

- [ ] **Step 3: Update `install_global_hooks` to write the PreToolUse hook**

In `core/hooks.py`, the global install must NOW include the PreToolUse hook
(hyperresearch deliberately skipped it; SPEC §12 says the global install drops
"the entry skill + step-skills + agents + PreToolUse hook" — but step skills
stay lazy). Modify `install_global_hooks` to:
- call `_install_bad_research_skill(home)` (entry skill → `~/.claude/skills/bad-research/SKILL.md`)
- call every `_install_*_agent(home, hpr_path)` including the new `_install_fresh_reviewer_agent`
- call `_install_claude_hook(home, hpr_path)` — write the PreToolUse hook into
  `~/.claude/settings.json` (the hook script goes to `~/.bad-research/hook.js`,
  matched on `Glob|Grep|WebSearch|WebFetch`, nudging "check `bad search` first").
- NOT call `_install_bad_research_step_skills` (lazy per-project).
- prune retired agents + any globally-installed step skills.

Keep `install_hooks` (project mode) installing ALL step skills + entry + agents
+ hook into the project's `.claude/`.

- [ ] **Step 4: Flip the `bad install` default in `cli/install.py`**

Rewrite the `install` command signature:
```python
def install(
    path: str = typer.Argument(".", help="Project path (only used with --project)"),
    project: bool = typer.Option(
        False, "--project", "-p",
        help="Install into project-local .claude/ + ./research/ instead of user-global ~/.claude/."),
    steps_only: bool = typer.Option(False, "--steps-only", help="(internal) lazy step-skill install"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    ...
```
Logic:
- `steps_only` → `_install_bad_research_step_skills(Path(path).resolve())` (unchanged mechanism, renamed function). Called by the entry-skill bootstrap.
- **default (no flag)** → `install_global_hooks(Path.home(), hpr_path=_resolve_executable())`. This is the NEW default — user-global. Print "Ready. /bad-research available in every Claude Code session."
- `--project` → the old project install path (vault init + CLAUDE.md inject + `install_hooks(root)`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_install/ -v`
Expected: PASS (5 passed)

- [ ] **Step 6: End-to-end smoke — `bad install` into a temp HOME via the CLI**

`tests/test_install/test_install_cli_e2e.py`:
```python
import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_bad_install_default_is_global(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    res = runner.invoke(app, ["install", "--json"])
    assert res.exit_code == 0
    assert (home / ".claude" / "skills" / "bad-research" / "SKILL.md").exists()
    # step skills NOT global
    assert not (home / ".claude" / "skills" / "bad-research-1-decompose").exists()
```
Run: `pytest tests/test_install/test_install_cli_e2e.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add src/bad_research/cli/install.py src/bad_research/core/hooks.py \
        tests/test_install/test_install_global.py tests/test_install/test_install_project.py \
        tests/test_install/test_install_cli_e2e.py
git commit -m "feat(install): bad install — user-global default (~/.claude/), --project opt-in, lazy step skills"
```

---

## Task 14: Full-suite green + integration verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire Plan-08 test surface**

Run: `pytest tests/test_skills/ tests/test_install/ tests/test_cli/test_cli_subcommands.py tests/test_mcp/ -v`
Expected: ALL PASS. Record the count.

- [ ] **Step 2: Verify the install lands the exact expected file set in a temp HOME**

Run:
```bash
python - <<'PY'
import tempfile, pathlib
from bad_research.core.hooks import install_global_hooks
home = pathlib.Path(tempfile.mkdtemp())
install_global_hooks(home, hpr_path="bad")
got = sorted(str(p.relative_to(home)) for p in (home/".claude").rglob("*") if p.is_file())
for g in got: print(g)
PY
```
Expected output includes: `.claude/skills/bad-research/SKILL.md`, `.claude/agents/bad-research-fresh-reviewer.md`, `.claude/agents/bad-research-synthesizer.md` (+ the other renamed agents), `.claude/settings.json`. Must NOT include any `.claude/skills/bad-research-1-decompose/...` (lazy).

- [ ] **Step 3: Verify every skill reference resolves across the whole skills dir**

Run: `pytest tests/test_skills/test_all_skills_valid.py -v`
Expected: PASS — zero unresolved references, every skill frontmatter parses.

- [ ] **Step 4: Verify the modified synthesize stage references the grounding gate**

Run: `grep -l "bad retrieve" src/bad_research/skills/bad-research-11-synthesize.md && grep -l "claim_anchors" src/bad_research/skills/bad-research-11-synthesize.md && echo "synthesize wired"`
Expected: `synthesize wired`. (The synthesizer reads retrieval top-chunks and renders anchored citations — the §9 forward binding.)

- [ ] **Step 5: Use the superpowers verification-before-completion skill**

Invoke `superpowers:verification-before-completion`. Confirm with evidence (the pytest output + the temp-HOME file listing) before claiming the plan complete. Do NOT assert "done" without the run output in hand.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "test(pipeline): full Plan-08 suite green — skills, install, router, MCP, CLI"
```

---

## Done criteria (the whole plan)

- 5 NEW skill prompts exist and validate: `bad-research-0.5-clarify`, `bad-research-query-router`, `bad-research-agentic-fast`, `bad-research-fresh-review`, `bad-research-11.5-citation-verifier`.
- 5 MODIFIED stage skills wire the backends: width-sweep → `funnel.gather()`; depth + gap-fetch → tiered browse; synthesize → retrieval top-chunks + grounded `claim_anchors` citations; step 16 → deterministic uncited-claim ship-gate.
- The entry skill routes `agentic-fast | light | full` to distinct stage sequences; `_BAD_RESEARCH_STEP_SKILLS` has all 21 names; the installer auto-discovers + prunes; the fresh-reviewer agent is `[Read]`-locked in both install loops.
- `bad install` defaults to user-global `~/.claude/` (entry skill + agents + PreToolUse hook); `--project` opts into `.claude/`; step skills lazy-install per-project. Verified by temp-HOME path assertions.
- 4 new MCP tools register on the `bad-research` server; 5 new CLI subcommands bridge skills→Python.
- NO new cross-plan seam type (the funnel/retrieval/grounding/browse seams are consumed verbatim from the frozen `INTERFACES.md`); only 4 routing/install constants are added to the contract. The `FunnelEnvelope` is a CLI-internal shape, intentionally kept out of `INTERFACES.md`.
- The router classifies fixtures correctly (trivial→agentic-fast, structured-midsize→light, contested/time_periods→full).

## The 3 riskiest steps

1. **Task 13 Step 3–4 — flipping the install default to user-global + adding the PreToolUse hook globally.** hyperresearch *deliberately* skips the global hook (it would fire in every Claude Code session). SPEC §12 mandates it for Bad Research, so the hook script must be vault-conditional (only nudge when a `.bad-research/` vault is found by walking up from cwd — the existing `findVault()` logic). Risk: a non-conditional global hook spams every unrelated session. Mitigation: keep the hook's `findVault()` walk so it stays silent outside research projects; test that the settings.json hook command is present but the hook body short-circuits with no vault.
2. **Task 9 Step 3 — replacing width-sweep's hand-dispatched fetcher waves with one `funnel.gather()` call.** This is the largest behavioral change to a kept crown-jewel stage. Risk: losing the coverage-check / redundancy-audit discipline that made hyperresearch comprehensive. Mitigation: keep Step 2.5 (coverage) and 2.6 (redundancy) but feed them off the funnel's `coverage` dict; the funnel must surface per-atomic-item coverage so the gap-targeted second `funnel-gather` still fires for thin items.
3. **Task 10 — entry-skill 3-mode routing while preserving the disk-state-machine recovery + the validator's required headers.** The entry skill is load-bearing for crash-resume; adding 5 stages to the recovery map and 3 route sequences risks an inconsistency between the routing table, `_BAD_RESEARCH_STEP_SKILLS`, and the recovery artifact map (a mismatch silently breaks resume). Mitigation: the `test_step_list.py` ordering asserts + `test_all_skills_valid.py` reference-resolution catch table/list drift; manually cross-check the recovery map lists an artifact for every new stage.
```