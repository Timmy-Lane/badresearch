# Codex Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bad install --codex`, which materializes the full bad-research pipeline as a single auto-discovered Codex skill under `~/.codex/skills/bad-research/`, translated from the existing Claude Code skill/agent sources at install time.

**Architecture:** A pure-function translation layer (tool-vocabulary + frontmatter rewriting) feeds a Codex installer that writes one skill dir: `SKILL.md` (router, Codex execution-model preamble prepended) + `references/<step>.md` (the 22 step procedures) + `references/agents/<agent>.md` (the 16 subagent prompts) + `references/dispatch-table.md` + `agents/openai.yaml`. The installer also injects an AGENTS.md blurb (replacing the Claude PreToolUse hook) and ensures `[features] multi_agent = true` in `~/.codex/config.toml`. The `bad` CLI core is untouched.

**Tech Stack:** Python 3.11+, Typer (CLI), pytest, `importlib.resources` (source reading), stdlib `re` / `tomllib`.

---

## Source-of-truth facts (read before starting)

- Step procedures: 22 files `src/bad_research/skills/bad-research-*.md`, roster = `hooks._BAD_RESEARCH_STEP_SKILLS`. Read raw (no `.format`).
- Subagent prompts: 16 string constants in `src/bad_research/core/hooks.py`. Each is `.format(hpr_path=...)`-safe (JSON braces are `{{ }}`-escaped).
- Claude installer reference: `hooks.install_global_hooks` / `hooks.install_hooks`. Do NOT modify these.
- Existing tests pattern: `tests/test_install/test_install_global.py` — `home = tmp_path/"home"`, call installer, assert files.
- Codex skill rule: SKILL.md frontmatter may contain ONLY `name` + `description` (+ optional `metadata.short-description`). Reference files are plain docs.
- Skill-name → reference-path rule (used everywhere): strip the `bad-research-` prefix and place under `references/`. Example: `bad-research-5-depth-investigation` → `references/5-depth-investigation.md`.

### Agent constant → Codex filename map (the 16)

| hooks.py constant | Codex file `references/agents/…` |
|---|---|
| `RESEARCHER_AGENT` | `fetcher.md` |
| `LOCI_ANALYST_AGENT` | `loci-analyst.md` |
| `SOURCE_ANALYST_AGENT` | `source-analyst.md` |
| `DEPTH_INVESTIGATOR_AGENT` | `depth-investigator.md` |
| `DIALECTIC_CRITIC_AGENT` | `dialectic-critic.md` |
| `DEPTH_CRITIC_AGENT` | `depth-critic.md` |
| `WIDTH_CRITIC_AGENT` | `width-critic.md` |
| `INSTRUCTION_CRITIC_AGENT` | `instruction-critic.md` |
| `LIGHT_CRITIC_AGENT` | `light-critic.md` |
| `CORPUS_CRITIC_AGENT` | `corpus-critic.md` |
| `DRAFT_ORCHESTRATOR_AGENT` | `draft-orchestrator.md` |
| `SYNTHESIZER_AGENT` | `synthesizer.md` |
| `PATCHER_AGENT` | `patcher.md` |
| `POLISH_AUDITOR_AGENT` | `polish-auditor.md` |
| `READABILITY_REFORMATTER_AGENT` | `readability-reformatter.md` |
| `FRESH_REVIEWER_AGENT` | `fresh-reviewer.md` |

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/bad_research/core/codex_translate.py` | Pure translation functions (tool vocab, frontmatter, skill-ref paths) | Create |
| `src/bad_research/core/codex_install.py` | Codex installer: skill dir, references, agents, openai.yaml, AGENTS.md, config | Create |
| `src/bad_research/skills/codex/router-preamble.md` | Codex execution-model preamble prepended to SKILL.md | Create |
| `src/bad_research/skills/codex/dispatch-table.md` | Stage → agent-file → parallelism → model/tool-lock table | Create |
| `src/bad_research/cli/install.py` | Add `--codex` flag | Modify |
| `tests/test_install/test_codex_translate.py` | Unit tests for translation layer | Create |
| `tests/test_install/test_codex_install.py` | Install layout, leak-lint, idempotency | Create |

---

## Task 1: Skill-name → reference-path helper

**Files:**
- Create: `src/bad_research/core/codex_translate.py`
- Test: `tests/test_install/test_codex_translate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_install/test_codex_translate.py
from bad_research.core.codex_translate import skillref_path


def test_skillref_path_strips_prefix_and_adds_references():
    assert skillref_path("bad-research-5-depth-investigation") == "references/5-depth-investigation.md"
    assert skillref_path("bad-research-0.5-clarify") == "references/0.5-clarify.md"
    assert skillref_path("bad-research-query-router") == "references/query-router.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_translate.py::test_skillref_path_strips_prefix_and_adds_references -v`
Expected: FAIL with `ModuleNotFoundError: bad_research.core.codex_translate`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/core/codex_translate.py
"""Translate Claude Code skill/agent sources into Codex equivalents.

Pure functions only — no filesystem side effects. The Codex installer
(codex_install.py) composes these to render the skill directory.
"""

from __future__ import annotations

import re

_SKILL_PREFIX = "bad-research-"


def skillref_path(skill_name: str) -> str:
    """`bad-research-5-depth-investigation` -> `references/5-depth-investigation.md`."""
    rest = skill_name[len(_SKILL_PREFIX):] if skill_name.startswith(_SKILL_PREFIX) else skill_name
    return f"references/{rest}.md"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_translate.py tests/test_install/test_codex_translate.py
git commit -m "feat(codex): skill-name to reference-path helper"
```

---

## Task 2: Tool-vocabulary translator

**Files:**
- Modify: `src/bad_research/core/codex_translate.py`
- Test: `tests/test_install/test_codex_translate.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_translate.py
from bad_research.core.codex_translate import translate_tool_vocabulary


def test_translate_rewrites_skill_calls_to_reference_reads():
    src = 'Run a step: Skill(skill: "bad-research-5-depth-investigation")'
    out = translate_tool_vocabulary(src)
    assert "Skill(" not in out
    assert "references/5-depth-investigation.md" in out


def test_translate_rewrites_task_and_todowrite_and_subagent():
    src = "Use Task(subagent_type=X) and the Task tool; seed the TodoWrite list; pass subagent_type."
    out = translate_tool_vocabulary(src)
    assert "Task(" not in out
    assert "TodoWrite" not in out
    assert "subagent_type" not in out
    assert "spawn_agent" in out
    assert "update_plan" in out


def test_translate_is_idempotent():
    src = 'Skill(skill: "bad-research-1-decompose"); TodoWrite'
    once = translate_tool_vocabulary(src)
    twice = translate_tool_vocabulary(once)
    assert once == twice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_translate.py -v`
Expected: FAIL with `ImportError: cannot import name 'translate_tool_vocabulary'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/bad_research/core/codex_translate.py

# Ordered: the Skill(...) regex runs first (consumes the structured call),
# then literal-token substitutions. Order matters — do not reorder casually.
_SKILL_CALL_RE = re.compile(r'Skill\(skill:\s*"([^"]+)"\)')

# Literal substitutions applied after the Skill() regex. Each is (old, new).
_LITERAL_SUBS: tuple[tuple[str, str], ...] = (
    ("Task(subagent_type=", "spawn_agent(agent="),
    ("Task(", "spawn_agent("),
    ("the Task tool", "the spawn_agent tool"),
    ("Task tool", "spawn_agent tool"),
    ("subagent_type", "agent"),
    ("TodoWrite", "update_plan"),
    ("the Skill tool", "the file-read tool"),
    ("Skill tool", "file-read tool"),
    ("orchestrator (Opus)", "orchestrator"),
)


def translate_tool_vocabulary(text: str) -> str:
    """Rewrite Claude Code tool references into Codex equivalents.

    Idempotent: running twice yields the same result (the output contains
    none of the source tokens, so a second pass is a no-op).
    """
    text = _SKILL_CALL_RE.sub(
        lambda m: f"read `{skillref_path(m.group(1))}`", text
    )
    for old, new in _LITERAL_SUBS:
        text = text.replace(old, new)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_translate.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_translate.py tests/test_install/test_codex_translate.py
git commit -m "feat(codex): tool-vocabulary translator (Skill/Task/TodoWrite -> Codex)"
```

---

## Task 3: Codex frontmatter rewriter + frontmatter stripper

**Files:**
- Modify: `src/bad_research/core/codex_translate.py`
- Test: `tests/test_install/test_codex_translate.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_translate.py
from bad_research.core.codex_translate import to_codex_skill_frontmatter, strip_frontmatter

_SRC = """---
name: bad-research
user-invocable: false
description: >
  A multi-line
  description here.
color: green
---

# Body

Content.
"""


def test_to_codex_skill_frontmatter_keeps_only_name_and_description():
    out = to_codex_skill_frontmatter(_SRC)
    assert out.startswith("---\n")
    assert "name: bad-research" in out
    assert "description:" in out
    assert "A multi-line description here." in out  # folded to one line
    assert "user-invocable" not in out
    assert "color: green" not in out
    assert "# Body" in out


def test_strip_frontmatter_removes_yaml_block():
    out = strip_frontmatter(_SRC)
    assert not out.lstrip().startswith("---")
    assert "name: bad-research" not in out
    assert "# Body" in out


def test_strip_frontmatter_noop_when_absent():
    assert strip_frontmatter("# No frontmatter\n") == "# No frontmatter\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_translate.py -v`
Expected: FAIL with `ImportError: cannot import name 'to_codex_skill_frontmatter'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/bad_research/core/codex_translate.py

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block_without_fences, body). frontmatter is None if absent."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def _extract_field(fm: str, field: str) -> str | None:
    """Extract a scalar or folded (`>`) YAML field value from a frontmatter block.

    Handles both `field: value` and the folded block form:
        field: >
          line one
          line two
    Returns the value folded to a single space-joined line, or None.
    """
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith(f"{field}:"):
            continue
        rest = line[len(field) + 1:].strip()
        if rest and rest not in (">", "|", ">-", "|-"):
            return rest
        # Folded/literal block: collect subsequent more-indented lines.
        collected: list[str] = []
        for cont in lines[i + 1:]:
            if cont.strip() == "":
                continue
            if not cont.startswith((" ", "\t")):
                break
            collected.append(cont.strip())
        return " ".join(collected) if collected else None
    return None


def to_codex_skill_frontmatter(text: str) -> str:
    """Rewrite a Claude skill's frontmatter to Codex-valid (name + description only)."""
    fm, body = _split_frontmatter(text)
    if fm is None:
        return text
    name = _extract_field(fm, "name") or "bad-research"
    description = _extract_field(fm, "description") or ""
    new_fm = f"---\nname: {name}\ndescription: {description}\n---\n"
    return new_fm + body


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block entirely (for reference docs)."""
    _, body = _split_frontmatter(text)
    return body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_translate.py tests/test_install/test_codex_translate.py
git commit -m "feat(codex): frontmatter rewriter + stripper"
```

---

## Task 4: Router preamble + dispatch-table source assets

**Files:**
- Create: `src/bad_research/skills/codex/router-preamble.md`
- Create: `src/bad_research/skills/codex/dispatch-table.md`

These are static prose assets read verbatim by the installer. No tests (validated via Task 7's install tests).

- [ ] **Step 1: Create the router preamble**

Create `src/bad_research/skills/codex/router-preamble.md` with EXACTLY this content:

```markdown
## Execution model on Codex (READ FIRST)

This skill is the Codex build of the bad-research pipeline. The mechanics below
override any Claude-Code-specific phrasing in the sections that follow.

- **Step procedures are bundled reference files.** Every step that the body
  refers to as a separate skill lives in `references/` inside THIS skill dir
  (e.g. `references/5-depth-investigation.md`). To "run a step," READ that
  reference file with your native file-read tool at the moment the step runs.
  There is no separate `Skill` tool and no `.claude/skills` lazy install on
  Codex — ignore any bootstrap step that tells you to run
  `bad install --steps-only`; the procedures are already here.
- **Subagents are dispatched with `spawn_agent`.** Each subagent's prompt lives
  in `references/agents/<name>.md`. To dispatch one: read that file, append the
  per-call inputs (verbatim `research_query`, pipeline position, file paths),
  and call `spawn_agent` with the result as an inline prompt. Collect results
  with `wait_agent`; free finished slots with `close_agent`. Parallel fan-outs
  (fetcher waves, two loci-analysts, per-locus depth-investigators, the four
  step-12 critics) = multiple `spawn_agent` calls. See
  `references/dispatch-table.md` for which agent runs at which stage and how
  many run in parallel.
- **Model & tool-locks.** Codex runs a single model. Where the agent files name
  `model: opus` use your highest reasoning effort; `model: sonnet` = default
  effort. Where an agent file names a restricted tool set (e.g.
  `tools: Read` for the fresh-reviewer, `Read, Edit` for the patcher / polish
  auditor / readability reformatter), HONOR that restriction in the spawned
  agent's instructions — do not let it Write or run shell commands beyond what
  the lock allows. The pipeline's CLI gates (`bad uncited-gate`,
  `bad recitation-gate`, grounding, patch-log) enforce the rest and are
  unchanged.
- **Task tracking** uses `update_plan` (not `TodoWrite`).
- **The `bad` CLI is identical to every other platform.** Run `bad fetch`,
  `bad search`, `bad note ...` etc. through your native shell tool exactly as
  the step procedures describe.
```

- [ ] **Step 2: Create the dispatch table**

Create `src/bad_research/skills/codex/dispatch-table.md` with EXACTLY this content:

```markdown
# Subagent dispatch table (Codex)

Read this when a step calls for subagents. Each row: the pipeline stage, the
prompt file under `references/agents/`, how many run in parallel, and the
intended model / tool-lock to encode in the spawned agent's instructions.

| Stage | Agent prompt file | Parallel | Model | Tool-lock |
|---|---|---|---|---|
| Width sweep (step 2) + depth fetches | `fetcher.md` | wave (2–6) | sonnet | Bash, Read, Write |
| Long-source digest | `source-analyst.md` | per long source | sonnet | Bash, Read, Write |
| Loci analysis (step 4) | `loci-analyst.md` | 2 | sonnet | Bash, Read, Write |
| Depth investigation (step 5) | `depth-investigator.md` | one per locus | sonnet | Bash, Read, Write, spawn_agent |
| Corpus critic (step 8) | `corpus-critic.md` | 1 | sonnet | Bash, Read, Write |
| Triple draft (step 10) | `draft-orchestrator.md` | 3 | opus | Bash, Read, Write |
| Synthesize (step 11) | `synthesizer.md` | 1 | opus | Read, Write |
| Critics (step 12, full) | `dialectic-critic.md`, `depth-critic.md`, `width-critic.md`, `instruction-critic.md` | 4 | opus | Bash, Read, Write |
| Critic (light / agentic-fast) | `light-critic.md` | 1 | sonnet | Bash, Read, Write |
| Patcher (step 14) | `patcher.md` | 1 | opus | Read, Edit |
| Fresh review (step 14.5, full) | `fresh-reviewer.md` | 1 | opus | Read |
| Polish (step 15) | `polish-auditor.md` | 1 | opus | Read, Edit |
| Readability (step 16) | `readability-reformatter.md` | 1 | opus | Read, Edit |
```

- [ ] **Step 3: Commit**

```bash
git add src/bad_research/skills/codex/router-preamble.md src/bad_research/skills/codex/dispatch-table.md
git commit -m "feat(codex): router preamble + subagent dispatch table assets"
```

---

## Task 5: Codex source reader + agent roster

**Files:**
- Create: `src/bad_research/core/codex_install.py`
- Test: `tests/test_install/test_codex_install.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_install/test_codex_install.py
from bad_research.core.codex_install import AGENT_FILES, read_codex_asset


def test_agent_files_has_all_sixteen():
    assert len(AGENT_FILES) == 16
    assert "fetcher.md" in AGENT_FILES
    assert "fresh-reviewer.md" in AGENT_FILES
    # content is formatted (no leftover hpr placeholder)
    assert "{hpr_path}" not in AGENT_FILES["fetcher.md"]
    assert "bad" in AGENT_FILES["fetcher.md"]  # hpr_path substituted


def test_read_codex_asset_loads_router_preamble():
    text = read_codex_asset("router-preamble.md")
    assert "Execution model on Codex" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: FAIL with `ModuleNotFoundError: bad_research.core.codex_install`

- [ ] **Step 3: Write minimal implementation**

```python
# src/bad_research/core/codex_install.py
"""`bad install --codex` — render the bad-research pipeline as a Codex skill.

Single source of truth: reads the same step-skill .md files and agent prompt
constants the Claude installer uses (hooks.py), translates them via
codex_translate, and writes ~/.codex/skills/bad-research/.
"""

from __future__ import annotations

from pathlib import Path

from bad_research.core import hooks
from bad_research.core.codex_translate import (
    skillref_path,
    strip_frontmatter,
    to_codex_skill_frontmatter,
    translate_tool_vocabulary,
)

# Agent constant -> Codex filename. Built from hooks.py constants so the two
# installers cannot drift in substance.
_AGENT_CONSTANTS: tuple[tuple[str, str], ...] = (
    ("fetcher.md", "RESEARCHER_AGENT"),
    ("loci-analyst.md", "LOCI_ANALYST_AGENT"),
    ("source-analyst.md", "SOURCE_ANALYST_AGENT"),
    ("depth-investigator.md", "DEPTH_INVESTIGATOR_AGENT"),
    ("dialectic-critic.md", "DIALECTIC_CRITIC_AGENT"),
    ("depth-critic.md", "DEPTH_CRITIC_AGENT"),
    ("width-critic.md", "WIDTH_CRITIC_AGENT"),
    ("instruction-critic.md", "INSTRUCTION_CRITIC_AGENT"),
    ("light-critic.md", "LIGHT_CRITIC_AGENT"),
    ("corpus-critic.md", "CORPUS_CRITIC_AGENT"),
    ("draft-orchestrator.md", "DRAFT_ORCHESTRATOR_AGENT"),
    ("synthesizer.md", "SYNTHESIZER_AGENT"),
    ("patcher.md", "PATCHER_AGENT"),
    ("polish-auditor.md", "POLISH_AUDITOR_AGENT"),
    ("readability-reformatter.md", "READABILITY_REFORMATTER_AGENT"),
    ("fresh-reviewer.md", "FRESH_REVIEWER_AGENT"),
)


def _build_agent_files(hpr_path: str = "bad") -> dict[str, str]:
    out: dict[str, str] = {}
    for filename, const_name in _AGENT_CONSTANTS:
        raw = getattr(hooks, const_name)
        formatted = raw.format(hpr_path=hpr_path)
        out[filename] = translate_tool_vocabulary(formatted)
    return out


AGENT_FILES: dict[str, str] = _build_agent_files()


def read_codex_asset(name: str) -> str:
    """Read a static Codex asset from src/bad_research/skills/codex/."""
    import importlib.resources

    try:
        return (
            importlib.resources.files("bad_research.skills.codex")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )
    except Exception:
        path = Path(__file__).parent.parent / "skills" / "codex" / name
        return path.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: PASS

Note: if `read_codex_asset` import-resources path fails, ensure `src/bad_research/skills/codex/` is shipped — add `__init__.py`? No: it is a data dir, covered by package-data globbing. Verify Task 8 e2e; if the resource read fails in an installed wheel, confirm `pyproject.toml` `[tool.setuptools.package-data]` (or equivalent) includes `skills/codex/*.md`. The filesystem fallback already covers editable installs.

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_install.py tests/test_install/test_codex_install.py
git commit -m "feat(codex): agent roster builder + asset reader"
```

---

## Task 6: Render the skill directory (SKILL.md + references)

**Files:**
- Modify: `src/bad_research/core/codex_install.py`
- Test: `tests/test_install/test_codex_install.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_install.py
from bad_research.core.codex_install import write_codex_skill


def test_write_codex_skill_lays_out_dir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    assert (root / "SKILL.md").exists()
    # 22 step references
    assert (root / "references" / "5-depth-investigation.md").exists()
    assert (root / "references" / "agentic-fast.md").exists()
    # 16 agent references
    assert (root / "references" / "agents" / "fetcher.md").exists()
    assert (root / "references" / "agents" / "patcher.md").exists()
    # static assets
    assert (root / "references" / "dispatch-table.md").exists()


def test_skill_md_frontmatter_is_codex_valid(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    fm = (home / ".codex" / "skills" / "bad-research" / "SKILL.md").read_text()
    head = fm.split("---\n")[1]  # first frontmatter block
    keys = [ln.split(":")[0].strip() for ln in head.splitlines() if ":" in ln]
    assert set(keys) <= {"name", "description"}
    assert "Execution model on Codex" in fm  # preamble prepended


def test_step_references_have_no_frontmatter(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_codex_skill(home, hpr_path="bad")
    txt = (home / ".codex" / "skills" / "bad-research" / "references" / "1-decompose.md").read_text()
    assert not txt.lstrip().startswith("---")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_codex_skill'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/bad_research/core/codex_install.py

def _codex_skill_root(home: Path) -> Path:
    return home / ".codex" / "skills" / "bad-research"


def write_codex_skill(home: Path, hpr_path: str = "bad") -> list[str]:
    """Write ~/.codex/skills/bad-research/ (SKILL.md + references). Returns actions."""
    root = _codex_skill_root(home)
    refs = root / "references"
    agents = refs / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []

    # SKILL.md = Codex frontmatter + preamble + translated router body.
    entry_src = hooks._read_skill_source("bad-research.md")
    if entry_src is None:
        raise RuntimeError("bad-research.md entry skill source missing")
    entry = to_codex_skill_frontmatter(entry_src)
    fm, body = entry.split("---\n", 2)[1], entry.split("---\n", 2)[2]
    preamble = read_codex_asset("router-preamble.md")
    skill_md = f"---\n{fm}---\n\n{preamble}\n\n{translate_tool_vocabulary(body)}"
    _write(root / "SKILL.md", skill_md, actions, "Codex: skills/bad-research/SKILL.md")

    # Step procedures -> references/<rest>.md (frontmatter stripped, vocab translated).
    for skill_name in hooks._BAD_RESEARCH_STEP_SKILLS:
        src = hooks._read_skill_source(f"{skill_name}.md")
        if src is None:
            continue
        rel = skillref_path(skill_name)  # references/<rest>.md
        dest = root / rel
        content = translate_tool_vocabulary(strip_frontmatter(src))
        _write(dest, content, actions, f"Codex: {rel}")

    # Subagent prompts -> references/agents/<name>.md (frontmatter KEPT as orchestrator hints).
    for filename, content in _build_agent_files(hpr_path).items():
        _write(agents / filename, content, actions, f"Codex: references/agents/{filename}")

    # Static dispatch table.
    _write(refs / "dispatch-table.md", read_codex_asset("dispatch-table.md"),
           actions, "Codex: references/dispatch-table.md")

    return actions


def _write(path: Path, content: str, actions: list[str], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")
    actions.append(label)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_install.py tests/test_install/test_codex_install.py
git commit -m "feat(codex): render SKILL.md + step/agent references"
```

---

## Task 7: openai.yaml + AGENTS.md injection + config multi_agent

**Files:**
- Modify: `src/bad_research/core/codex_install.py`
- Test: `tests/test_install/test_codex_install.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_install.py
from bad_research.core.codex_install import (
    write_openai_yaml,
    inject_codex_agents_md,
    ensure_multi_agent,
)


def test_write_openai_yaml(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    write_openai_yaml(home)
    y = (home / ".codex" / "skills" / "bad-research" / "agents" / "openai.yaml").read_text()
    assert "display_name:" in y
    assert "default_prompt:" in y


def test_inject_agents_md_creates_marker_section(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    inject_codex_agents_md(home, hpr_path="bad")
    txt = (home / ".codex" / "AGENTS.md").read_text()
    assert "bad-research:start" in txt
    assert "bad fetch" in txt


def test_inject_agents_md_preserves_existing(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "AGENTS.md").write_text("# My notes\nkeep me\n", encoding="utf-8")
    inject_codex_agents_md(home, hpr_path="bad")
    txt = (home / ".codex" / "AGENTS.md").read_text()
    assert "keep me" in txt
    assert "bad-research:start" in txt


def test_ensure_multi_agent_adds_flag(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    ensure_multi_agent(home)
    cfg = (home / ".codex" / "config.toml").read_text()
    assert "[features]" in cfg
    assert "multi_agent = true" in cfg


def test_ensure_multi_agent_idempotent(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    (home / ".codex").mkdir()
    cfg_path = home / ".codex" / "config.toml"
    cfg_path.write_text("[features]\nmulti_agent = true\n", encoding="utf-8")
    assert ensure_multi_agent(home) is None  # no change
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_openai_yaml'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/bad_research/core/codex_install.py
import re as _re

_OPENAI_YAML = """\
display_name: Bad Research
short_description: Deep, multi-source, fully-cited research pipeline
default_prompt: Run deep research on the following question, with a fully-cited report
"""

_AGENTS_MD_START = "<!-- bad-research:start -->"
_AGENTS_MD_END = "<!-- bad-research:end -->"

_AGENTS_MD_BLURB = """\
{start}
## Research Base (bad-research)

Deep-research pipeline available as the `bad-research` Codex skill. To run a
fully-cited research session, trigger that skill; its SKILL.md is the router.

**Prefer the vault over raw web access.** Before any raw web search/fetch on a
research topic, check the local research base and fetch through the CLI:

- `{hpr} search "<query>" --json` — search the vault first
- `{hpr} fetch "<url>" --json` — fetch sources (auto-extracts PDFs); do NOT use
  a raw web-fetch tool for source pages
- `{hpr} note show <id> --json` — read a stored note

The `bad` CLI is identical across platforms; run it through your shell tool.
{end}
"""


def write_openai_yaml(home: Path) -> list[str]:
    dest = _codex_skill_root(home) / "agents" / "openai.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []
    _write(dest, _OPENAI_YAML, actions, "Codex: skills/bad-research/agents/openai.yaml")
    return actions


def inject_codex_agents_md(home: Path, hpr_path: str = "bad") -> list[str]:
    from bad_research.core.agent_docs import _inject_into_file

    hpr = hpr_path.replace("\\", "/")
    blurb = _AGENTS_MD_BLURB.format(start=_AGENTS_MD_START, end=_AGENTS_MD_END, hpr=hpr)
    # _inject_into_file matches on a fixed marker constant; temporarily reuse the
    # generic helper by passing our own markers via a thin wrapper.
    target = home / ".codex" / "AGENTS.md"
    actions: list[str] = []
    result = _inject_markered(target, blurb, _AGENTS_MD_START, _AGENTS_MD_END, "AGENTS.md")
    if result:
        actions.append(f"Codex: {result}")
    return actions


def _inject_markered(path: Path, blurb: str, start: str, end: str, label: str) -> str | None:
    if path.exists():
        content = path.read_text(encoding="utf-8-sig")
        if start in content:
            pat = _re.compile(_re.escape(start) + r".*?" + _re.escape(end), _re.DOTALL)
            new = pat.sub(lambda _: blurb.strip(), content)
            if new != content:
                path.write_text(new, encoding="utf-8")
                return f"{label} (updated)"
            return None
        sep = "\n\n" if not content.endswith("\n") else "\n"
        path.write_text(content + sep + blurb.strip() + "\n", encoding="utf-8")
        return f"{label} (appended)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n" + blurb.strip() + "\n", encoding="utf-8")
    return f"{label} (created)"


def ensure_multi_agent(home: Path) -> str | None:
    """Idempotently ensure [features] multi_agent = true in ~/.codex/config.toml."""
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if _re.search(r"^\s*multi_agent\s*=\s*true", text, _re.MULTILINE):
        return None
    if _re.search(r"^\[features\]", text, _re.MULTILINE):
        new = _re.sub(r"^\[features\]\s*\n", "[features]\nmulti_agent = true\n", text,
                      count=1, flags=_re.MULTILINE)
    else:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new = text + sep + "\n[features]\nmulti_agent = true\n"
    path.write_text(new, encoding="utf-8")
    return "Codex: config.toml ([features] multi_agent = true)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_install.py tests/test_install/test_codex_install.py
git commit -m "feat(codex): openai.yaml + AGENTS.md injection + multi_agent config"
```

---

## Task 8: Top-level `install_codex()` + CLI `--codex` flag

**Files:**
- Modify: `src/bad_research/core/codex_install.py`
- Modify: `src/bad_research/cli/install.py:22-60`
- Test: `tests/test_install/test_codex_install.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_install.py
from bad_research.core.codex_install import install_codex


def test_install_codex_full(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    actions = install_codex(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    assert (root / "SKILL.md").exists()
    assert (root / "agents" / "openai.yaml").exists()
    assert (home / ".codex" / "AGENTS.md").exists()
    cfg = (home / ".codex" / "config.toml").read_text()
    assert "multi_agent = true" in cfg
    assert len(actions) > 0


def test_install_codex_idempotent(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    install_codex(home, hpr_path="bad")
    second = install_codex(home, hpr_path="bad")
    assert second == []  # nothing changed on second run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: FAIL with `ImportError: cannot import name 'install_codex'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/bad_research/core/codex_install.py

def install_codex(home: Path | None = None, hpr_path: str = "bad") -> list[str]:
    """Full Codex install: skill dir + references + openai.yaml + AGENTS.md + config."""
    home = home or Path.home()
    actions: list[str] = []
    actions += write_codex_skill(home, hpr_path=hpr_path)
    actions += write_openai_yaml(home)
    actions += inject_codex_agents_md(home, hpr_path=hpr_path)
    cfg = ensure_multi_agent(home)
    if cfg:
        actions.append(cfg)
    return actions
```

Now wire the CLI. Modify `src/bad_research/cli/install.py`:

```python
# add to the install() signature, after the steps_only option:
    codex: bool = typer.Option(
        False, "--codex",
        help="Install into Codex (~/.codex/skills/) instead of Claude Code (~/.claude/).",
    ),
```

```python
# inside install(), change the import block and branch order so --codex wins first:
    from bad_research.core.agent_docs import _resolve_executable
    from bad_research.core.hooks import (
        _install_bad_research_step_skills,
        install_global_hooks,
        install_hooks,
    )

    hpr = _resolve_executable()

    if codex:
        from bad_research.core.codex_install import install_codex
        actions = install_codex(Path.home(), hpr_path=hpr)
        msg = "Ready. bad-research available as a Codex skill (~/.codex/skills/bad-research/)."
    elif steps_only:
        root = Path(path).resolve()
        result = _install_bad_research_step_skills(root)
        actions = [result] if result else []
        msg = "Step skills installed (lazy)."
    elif project:
        root = Path(path).resolve()
        actions = install_hooks(root, hpr_path=hpr)
        msg = f"Project install complete at {root}. /bad-research available in this project."
    else:
        actions = install_global_hooks(Path.home(), hpr_path=hpr)
        msg = "Ready. /bad-research available in every Claude Code session."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: PASS

Then verify the CLI wiring end to end:

Run: `uv run bad install --codex --json`
Expected: JSON with `"ok": true` and actions listing `Codex: skills/bad-research/SKILL.md` etc. (writes into your real `~/.codex/` — safe, idempotent).

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_install.py src/bad_research/cli/install.py tests/test_install/test_codex_install.py
git commit -m "feat(codex): install_codex() entrypoint + bad install --codex flag"
```

---

## Task 9: Translation-leak lint + roster-completeness guard

**Files:**
- Test: `tests/test_install/test_codex_install.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_install/test_codex_install.py
import pytest

_FORBIDDEN = ("Skill(", "Task(", "TodoWrite", "subagent_type", ".claude/")


def _all_rendered_files(root):
    return list(root.rglob("*.md"))


def test_no_claude_tokens_leak_into_codex_render(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    install_codex(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    offenders = []
    for f in _all_rendered_files(root):
        text = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN:
            if tok in text:
                offenders.append(f"{f.relative_to(root)}: {tok}")
    assert not offenders, "Claude tokens leaked:\n" + "\n".join(offenders)


def test_all_step_references_present(tmp_path):
    from bad_research.core import hooks
    from bad_research.core.codex_translate import skillref_path
    home = tmp_path / "home"; home.mkdir()
    install_codex(home, hpr_path="bad")
    root = home / ".codex" / "skills" / "bad-research"
    for skill_name in hooks._BAD_RESEARCH_STEP_SKILLS:
        assert (root / skillref_path(skill_name)).exists(), skill_name
```

- [ ] **Step 2: Run test to verify it (likely) fails**

Run: `uv run pytest tests/test_install/test_codex_install.py::test_no_claude_tokens_leak_into_codex_render -v`
Expected: FAIL listing any leftover tokens (e.g. a `.claude/` mention in a step body, or a `Task(` form the literal subs missed).

- [ ] **Step 3: Fix the translator to close leaks**

For each offender the test reports, extend `_LITERAL_SUBS` in `codex_translate.py` with the missing form. Likely additions:

```python
# add to _LITERAL_SUBS in src/bad_research/core/codex_translate.py
    (".claude/skills/", "references/"),
    (".claude/agents/", "references/agents/"),
    (".claude/", ".codex/"),
    ("the Skill(", "read the reference "),
```

Re-run after each addition until the leak test passes. Do NOT weaken the test to pass — fix the translation.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install/test_codex_install.py -v`
Expected: PASS (all tests including leak + roster)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/core/codex_translate.py tests/test_install/test_codex_install.py
git commit -m "test(codex): translation-leak lint + roster guard; close leaks"
```

---

## Task 10: Full suite + manual smoke + docs

**Files:**
- Modify: `README.md` (install section)

- [ ] **Step 1: Run the whole install test suite**

Run: `uv run pytest tests/test_install/ -v`
Expected: PASS (existing Claude tests untouched + new Codex tests green)

- [ ] **Step 2: Run lint/type gates the repo uses**

Run: `uv run ruff check src/bad_research/core/codex_install.py src/bad_research/core/codex_translate.py src/bad_research/cli/install.py`
Run: `uv run mypy src/bad_research/core/codex_install.py src/bad_research/core/codex_translate.py`
Expected: clean (fix any reported issues inline)

- [ ] **Step 3: Manual smoke (real `~/.codex/`)**

Run: `uv run bad install --codex --json`
Then inspect:
Run: `ls ~/.codex/skills/bad-research/ ~/.codex/skills/bad-research/references/ ~/.codex/skills/bad-research/references/agents/`
Expected: SKILL.md, agents/openai.yaml, 22 step references, 16 agent references, dispatch-table.md.
Run: `grep -c multi_agent ~/.codex/config.toml`
Expected: ≥1.

Then, in the Codex app, start a short light-tier query and confirm the orchestrator reads `references/…` and dispatches `spawn_agent`. (Manual — note any prompt phrasing that still reads Claude-specific and feed it back into `_LITERAL_SUBS`.)

- [ ] **Step 4: Document the flag in README**

Add to the install section of `README.md`:

```markdown
### Codex

`bad install --codex` installs the pipeline as a Codex skill at
`~/.codex/skills/bad-research/` and enables `[features] multi_agent` in
`~/.codex/config.toml`. Restart Codex after installing so it discovers the skill.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(codex): document bad install --codex"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** D1 (full parity) → Tasks 5/6 (agent files) + Task 4 dispatch-table + preamble (model/tool-lock guidance) + Task 7 multi_agent. D2 (one skill + references) → Task 6 layout. D3 (`bad install --codex`) → Task 8. D4 (single-source transform) → `_build_agent_files` reads hooks constants; step refs read `_read_skill_source`; no parallel tree. Translation table → Tasks 2/9. AGENTS.md (hook replacement) → Task 7. Tests → Tasks 1-3, 6-9.
- **Open items carried from spec:** exact `spawn_agent` model/tools params (resolved at Task 10 manual smoke / Codex docs — preamble + dispatch-table express them as instructions regardless); project-local Codex skills deferred (install is global-only, matching the spec's fallback).
- **Type consistency:** `skillref_path`, `translate_tool_vocabulary`, `strip_frontmatter`, `to_codex_skill_frontmatter`, `_build_agent_files`, `_write`, `write_codex_skill`, `write_openai_yaml`, `inject_codex_agents_md`, `ensure_multi_agent`, `install_codex` — names used consistently across Tasks 1-9.
- **Placeholder scan:** no TBD/TODO; every code step shows full code; the only deferred decisions are the spec's two open items, each with a concrete fallback already implemented.
