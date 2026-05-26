# Bad Research — Plan 09: Packaging + Tests + Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD: write the failing test, run it, see it FAIL, write the implementation, run it, see it PASS, commit. Do not skip the FAIL observation — it proves the test exercises the code.

**Goal:** Finalize the `bad-research` package so a user can `pipx install bad-research` (lean, zero-key) and progressively `pip install 'bad-research[all]'` (full neural+browse stack), then `bad install` (user-global skill drop, idempotent) and `bad doctor` (which providers/keys are live). Aggregate every per-plan pytest suite under one config with `unit`/`integration`/`live` markers and a coverage floor, and ship the **offline** calibration harness `bad calibrate <query>` that runs a query through bad-research, meters its 5-component cost, and scores the report on the 5-axis LLM-judge rubric against the hyperresearch baseline (and optionally Perplexity/Grok deep-research) — calibration only, never a per-run gate (SPEC §10 Excluded list).

**Architecture:** This plan owns three thin layers that sit *on top of* Plans 01–08, never inside their hot path:
1. **Packaging** (`pyproject.toml`) — fork hyperresearch's hatchling build; rename to `bad-research`/`bad_research`; entry points `bad`/`badr` → `bad_research.cli:app`; **optional-extras groups** (`[search]`, `[browse]`, `[grounding]`, `[all]`, `[dev]`) so the base install stays small (only `anthropic`, `lancedb`, `httpx`, `typer`, `pymupdf`, core deps) and heavy stacks (browser-use/playwright, sentence-transformers/torch, cohere/exa/tavily/firecrawl) are opt-in.
2. **Install + doctor** (`bad_research/cli/doctor.py`, plus `bad_research/providers.py` registry) — `bad install` wraps Plan 08's skill installer with an **idempotency guarantee** (run twice → identical disk state, zero second-run mutations); `bad doctor` reports which providers are *active* by probing env vars + import availability, never making a network call.
3. **Calibration** (`bad_research/calibrate/`) — a standalone offline package: `CostMeter` (5-component), `Judge` (single-call 5-axis strong-model rubric, 0.0–1.0 + PASS/FAIL), `Baseline` runners (hyperresearch + optional Perplexity/Grok APIs, key-gated and skipped otherwise), and `run_calibration()` that wires them into a `CalibrationReport` JSON + markdown. Exposed as `bad calibrate <query>`.

The calibration harness mocks the LLM judge in tests (it is a `Judge` Protocol with a deterministic `StubJudge`), so the whole harness runs end-to-end on a tiny fixture with zero API keys and zero network.

**Tech Stack:** Python 3.11+ (`requires-python = ">=3.11,<3.14"`); `hatchling` build backend (forked verbatim from hyperresearch); `typer`+`rich` CLI; `pytest` + `pytest-cov` (coverage floor 80%); `typer.testing.CliRunner` for CLI tests (hyperresearch's exact test style). The harness reuses Plan 01's `LLMProvider`/`ModelTier` seam for the judge and Plan 08's skill installer for `bad install`. No new heavyweight runtime deps — the calibration package depends only on what the base install already provides plus the judge's `LLMProvider`.

---

## Dependencies on other plans

This plan **consumes** types/functions produced by earlier plans. They are reproduced here so an engineer reading Plan 09 in isolation knows the exact shapes. If a dependency plan has not landed, Task 0 creates a minimal stub with the identical signature; otherwise import the real thing.

```python
# bad_research/llm/base.py  (Plan 01 — consumed by the Judge)
from typing import Literal, Protocol
from dataclasses import dataclass

ModelTier = Literal["triage", "work", "heavy"]

@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict]

@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict]          # [] if none
    usage: dict                     # {input_tokens, output_tokens, cache_read, cache_write}
    model: str

class LLMProvider(Protocol):
    name: str
    def complete(self, messages: list[LLMMessage], *, tier: ModelTier,
                 tools: list[dict] | None = None, cache: bool = False,
                 max_tokens: int = 4096, temperature: float = 0.1) -> LLMResponse: ...

# bad_research/config.py  (Plan 01 — consumed here; only the fields this plan reads)
# BadResearchConfig.vault_root: Path
# BadResearchConfig.model_tiers: dict        # {"triage": "...", "work": "...", "heavy": "..."}
# BadResearchConfig.budget_usd: float | None

# bad_research/cli/install.py  (Plan 08 — consumed by `bad install`)
# def install(path: str = ".", *, global_install: bool = False,
#             steps_only: bool = False, json_output: bool = False) -> None
# def install_global_hooks(home: Path | None = None, *, bad_path: str = "bad") -> list[str]
#   — idempotent: returns [] on a no-op second run. (Forked from hyperresearch core/hooks.py.)
```

> **Note on `bad install`:** Plan 08 owns the *skill/agent/hook drop* (`install_global_hooks`, `_install_*_agent`, the SKILL.md writers). This plan does NOT re-implement them. Plan 09 owns: (a) the `pyproject.toml` entry-point wiring so `bad install` is invokable, (b) an *idempotency test* that holds Plan 08's installer to the "run twice → same state" contract, and (c) `bad doctor`. If Plan 08 has not landed, Task 0 stubs `install_global_hooks` as a function that creates `~/.claude/skills/bad-research/SKILL.md` once and returns `[]` on the second call — enough to test idempotency.

The CLI `app` is hyperresearch's `typer.Typer` forked to `bad_research/cli/__init__.py` with `name="bad-research"`; every command is registered there. This plan **adds** `doctor` and `calibrate` commands to it (Tasks 5, 13).

---

## Frozen constants (from `INTERFACES.md` + dossier 09 — cite verbatim, never re-derive)

```python
# bad_research/calibrate/constants.py  (Task 9)

# --- The 5-axis LLM-judge rubric (dossier 09 §B7, CLAUDE_RESEARCH.md:39; SPEC §14) ---
# Single strong-model call (NOT an ensemble — ensemble tested WORSE, dossier 09 §B7).
# Each axis scored 0.0–1.0; PASS iff every axis ≥ AXIS_PASS_THRESHOLD AND mean ≥ OVERALL_PASS_THRESHOLD.
JUDGE_AXES = ("factual", "citation", "completeness", "source_quality", "efficiency")
AXIS_PASS_THRESHOLD = 0.70        # per-axis floor                                   [SPEC §8 0.70 bar reuse]
OVERALL_PASS_THRESHOLD = 0.75     # mean across axes                                  [dossier 09 §B7]
JUDGE_TIER = "heavy"              # Opus; Sonnet acceptable (dossier 09 §A4 table L223)
JUDGE_MAX_TOKENS = 2048
JUDGE_TEMPERATURE = 0.0          # deterministic scoring                              [cookbook]

# --- 5-component cost metering (Perplexity, dossier 09 §A4.2 / 05§7) ---
COST_COMPONENTS = ("input", "output", "reasoning", "citation", "search_queries")
# Per-1M-token USD prices for the model tiers (current public Anthropic pricing; behind the seam).
# Used only by the OFFLINE meter to convert token counts → USD; never gates a run.
TIER_PRICE_USD_PER_MTOK = {                                                          # [INTERFACES Models]
    "triage": {"input": 1.00,  "output": 5.00},    # claude-haiku-4-5
    "work":   {"input": 3.00,  "output": 15.00},   # claude-sonnet-4-6
    "heavy":  {"input": 15.00, "output": 75.00},   # claude-opus-4-7
}
SEARCH_QUERY_PRICE_USD = 0.005    # per provider search call (Tavily/Exa estimate)    [dossier 02 cost_per_search]

# --- Calibration set (dossier 09 §B7, SPEC §14: "~20-query research set") ---
DEFAULT_CALIBRATION_SET_SIZE = 20  # frozen eval set; out-of-pipeline only            [DR-loops eval-set size]
```

---

## File Structure

New + modified files this plan owns:

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | **rewrite** (fork) | `bad-research` metadata, entry points `bad`/`badr`, optional-extras groups, pytest config + markers, coverage floor. |
| `src/bad_research/providers.py` | new | The provider registry: `PROVIDERS` table (name → {env_var, import_name, extra, capability}), `provider_status()` → list of `ProviderStatus`, `active_providers()`. Pure, no network. |
| `src/bad_research/cli/doctor.py` | new | `doctor()` typer command — renders `provider_status()` + key/import availability + vault path. `--json` mode. |
| `src/bad_research/cli/__init__.py` | **modify** | Register `doctor` and `calibrate` commands on `app` (forked from hyperresearch; only the two new registrations are this plan's). |
| `src/bad_research/calibrate/__init__.py` | new | Re-export `CostMeter`, `Judge`, `StubJudge`, `LLMJudge`, `run_calibration`, `CalibrationReport`. |
| `src/bad_research/calibrate/constants.py` | new | The frozen constants above. Single source of truth. |
| `src/bad_research/calibrate/cost.py` | new | `CostMeter` — accumulates 5-component usage per stage/model, converts to USD, emits `cost-report.json`. |
| `src/bad_research/calibrate/judge.py` | new | `Judge` Protocol + `StubJudge` (deterministic, for tests) + `LLMJudge` (single-call 5-axis rubric over `LLMProvider`); `AxisScores`, `JudgeVerdict` dataclasses; the verbatim judge prompt. |
| `src/bad_research/calibrate/baselines.py` | new | `Baseline` Protocol; `HyperresearchBaseline` (runs the upstream pkg if importable), `PerplexityBaseline`/`GrokBaseline` (key-gated, raise `BaselineUnavailable` without a key). |
| `src/bad_research/calibrate/harness.py` | new | `run_calibration(query, *, runner, baselines, judge, meter) -> CalibrationReport`; `CalibrationReport` dataclass + `.to_json()`/`.to_markdown()`. |
| `src/bad_research/cli/calibrate.py` | new | `calibrate()` typer command — wires config → harness → writes `calibration-report.{json,md}`. |

Tests mirror hyperresearch's `tests/` layout:

| File | Covers |
|---|---|
| `tests/test_packaging/test_pyproject.py` | metadata, entry points resolve, extras keep base lean, `bad --help`. |
| `tests/test_packaging/test_install_idempotent.py` | `bad install` twice → identical disk state. |
| `tests/test_packaging/test_doctor.py` | `bad doctor` reports active providers from env; `--json`. |
| `tests/test_providers.py` | `provider_status()` / `active_providers()` env+import logic. |
| `tests/test_calibrate/conftest.py` | `StubJudge`, a tiny report fixture, a stub `BadRunner`. |
| `tests/test_calibrate/test_cost.py` | 5-component metering math + `cost-report.json` shape. |
| `tests/test_calibrate/test_judge.py` | `StubJudge` verdict; `LLMJudge` prompt+parse against a stub `LLMProvider`. |
| `tests/test_calibrate/test_baselines.py` | key-gated baselines skip without keys. |
| `tests/test_calibrate/test_harness.py` | end-to-end harness on the fixture (mocked judge) → `CalibrationReport`. |
| `tests/test_calibrate/test_calibrate_cmd.py` | `bad calibrate <query>` emits both report files. |

---

## Task 0 — Bootstrap: confirm the fork tree + stub upstream deps

**Goal:** Guarantee `src/bad_research/` exists with the forked CLI `app`, and the Plan 01/08 symbols this plan imports are present (real or stubbed), so every later task imports cleanly.

- [ ] **0.1** Verify the package tree exists. If Plans 01–08 have produced `src/bad_research/`, do nothing. If not (planning in isolation), create the minimal fork:

```bash
# from repo root: ultimate-research/bad-research/
mkdir -p src/bad_research/cli src/bad_research/llm src/bad_research/calibrate
mkdir -p tests/test_packaging tests/test_calibrate
test -f src/bad_research/__init__.py || printf '__version__ = "0.1.0"\n' > src/bad_research/__init__.py
test -f src/bad_research/cli/__init__.py || cat > src/bad_research/cli/__init__.py <<'PY'
"""Bad Research CLI — main typer application (fork of hyperresearch)."""
import typer
from bad_research import __version__

def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bad-research v{__version__}")
        raise typer.Exit()

app = typer.Typer(name="bad-research", help='michael jackson bad — deep research.',
                  no_args_is_help=True, rich_markup_mode="rich")

@app.callback()
def main(version: bool = typer.Option(False, "--version", "-V",
         callback=_version_callback, is_eager=True, help="Show version")) -> None:
    pass
PY
```

- [ ] **0.2** Ensure the Plan 01 `llm/base.py` symbols exist (stub if absent). Only the `LLMProvider`/`LLMMessage`/`LLMResponse`/`ModelTier` shapes the judge needs:

```bash
test -f src/bad_research/llm/__init__.py || touch src/bad_research/llm/__init__.py
test -f src/bad_research/llm/base.py || cat > src/bad_research/llm/base.py <<'PY'
"""LLMProvider seam (Plan 01). Stub shapes — replaced by Plan 01's real impl."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Protocol

ModelTier = Literal["triage", "work", "heavy"]

@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict]

@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""

class LLMProvider(Protocol):
    name: str
    def complete(self, messages: list[LLMMessage], *, tier: ModelTier,
                 tools: list[dict] | None = None, cache: bool = False,
                 max_tokens: int = 4096, temperature: float = 0.1) -> LLMResponse: ...
PY
```

- [ ] **0.3** Ensure a Plan 08 install seam exists (stub if absent) so the idempotency test has a target:

```bash
test -f src/bad_research/cli/install.py || cat > src/bad_research/cli/install.py <<'PY'
"""Install seam (Plan 08). Stub — replaced by Plan 08's real skill installer."""
from __future__ import annotations
from pathlib import Path

def install_global_hooks(home: Path | None = None, *, bad_path: str = "bad") -> list[str]:
    """Idempotent: writes the skill once, returns [] on a no-op second run."""
    home = home or Path.home()
    skill = home / ".claude" / "skills" / "bad-research" / "SKILL.md"
    if skill.exists():
        return []
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("---\nname: bad-research\n---\nmichael jackson bad\n", encoding="utf-8")
    return [f"installed {skill}"]
PY
```

- [ ] **0.4** Sanity-import:

```bash
python -c "from bad_research.cli import app; from bad_research.llm.base import LLMProvider; from bad_research.cli.install import install_global_hooks; print('ok')"
```

Expected: `ok`.

- [ ] **0.5** Commit.

```bash
git add -A && git commit -m "chore(bad-research): bootstrap package tree + Plan 01/08 import stubs for Plan 09"
```

---

## Task 1 — `pyproject.toml`: metadata + entry points (RED → GREEN)

**Goal:** `pip install -e .` succeeds and exposes `bad` / `badr` console scripts that resolve to `bad_research.cli:app`.

- [ ] **1.1** Write the failing test `tests/test_packaging/test_pyproject.py`:

```python
"""pyproject.toml metadata + entry-point resolution."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]   # .../bad-research/
PYPROJECT = ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pp() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_project_name_and_python(pp):
    assert pp["project"]["name"] == "bad-research"
    assert pp["project"]["requires-python"] == ">=3.11,<3.14"


def test_entry_points(pp):
    scripts = pp["project"]["scripts"]
    assert scripts["bad"] == "bad_research.cli:app"
    assert scripts["badr"] == "bad_research.cli:app"


def test_wheel_packages(pp):
    pkgs = pp["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert pkgs == ["src/bad_research"]
```

- [ ] **1.2** Run it — FAIL (no `pyproject.toml` yet, or wrong name):

```bash
python -m pytest tests/test_packaging/test_pyproject.py -q
```

Expected: failures / collection error referencing the missing or mismatched keys.

- [ ] **1.3** Write `pyproject.toml` (the core block; extras land in Task 2):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bad-research"
version = "0.1.0"
description = "michael jackson bad — a deep-research agent that filters garbage, grounds every claim, and runs as a Claude Code skill."
readme = "README.md"
license = "MIT"
requires-python = ">=3.11,<3.14"
authors = [{name = "Bad Research"}]
keywords = ["research", "deep-research", "llm", "agent", "rag", "retrieval", "claude", "cli"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "anthropic>=0.40",
    "lancedb>=0.13",
    "pyarrow>=15",
    "numpy>=1.26",
    "typer>=0.9.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "jinja2>=3.1",
    "platformdirs>=4.0",
    "pymupdf>=1.24",
    "httpx>=0.27",
]

[project.scripts]
bad = "bad_research.cli:app"
badr = "bad_research.cli:app"

[project.urls]
Homepage = "https://github.com/bad-research/bad-research"
Repository = "https://github.com/bad-research/bad-research"

[tool.hatch.build.targets.wheel]
packages = ["src/bad_research"]
```

- [ ] **1.4** Run — PASS:

```bash
python -m pytest tests/test_packaging/test_pyproject.py -q
```

Expected: `3 passed`.

- [ ] **1.5** Editable-install + console-script smoke (the real entry-point test):

```bash
pip install -e . && bad --help && badr --version
```

Expected: `bad --help` prints the typer help with the `michael jackson bad` description; `badr --version` prints `bad-research v0.1.0`.

- [ ] **1.6** Commit.

```bash
git add -A && git commit -m "feat(packaging): bad-research pyproject metadata + bad/badr entry points (tested)"
```

---

## Task 2 — Optional-extras groups keep the base install lean (RED → GREEN)

**Goal:** Heavy deps (browser-use/playwright, sentence-transformers/torch, cohere/exa/tavily/firecrawl/agentql, crawl4ai) live behind named extras; the base `dependencies` list stays minimal. `[all]` composes them; `[dev]` carries the test toolchain.

- [ ] **2.1** Extend `tests/test_packaging/test_pyproject.py` with failing assertions:

```python
# --- append to tests/test_packaging/test_pyproject.py ---

# Heavy deps that MUST NOT be in the base install (keep zero-key/lean small).
HEAVY_FORBIDDEN_IN_BASE = {
    "cohere", "tavily-python", "exa-py", "crawl4ai", "browser-use",
    "sentence-transformers", "torch", "firecrawl-py", "agentql", "playwright",
}


def _names(dep_list: list[str]) -> set[str]:
    # strip version/extra specifiers: "cohere>=5" -> "cohere"; "x[y]>=1" -> "x"
    out = set()
    for d in dep_list:
        name = d.split(";")[0].strip()
        for sep in (">=", "==", "~=", "<", ">", "[", " "):
            name = name.split(sep)[0]
        out.add(name.strip())
    return out


def test_base_install_is_lean(pp):
    base = _names(pp["project"]["dependencies"])
    assert not (base & HEAVY_FORBIDDEN_IN_BASE), f"heavy deps leaked into base: {base & HEAVY_FORBIDDEN_IN_BASE}"
    # base must still carry the zero-key essentials
    assert {"anthropic", "lancedb", "httpx", "typer", "pymupdf"} <= base


def test_extras_groups_exist(pp):
    extras = pp["project"]["optional-dependencies"]
    for group in ("search", "browse", "grounding", "all", "dev"):
        assert group in extras, f"missing extras group: {group}"


def test_search_extra_contents(pp):
    search = _names(pp["project"]["optional-dependencies"]["search"])
    assert {"tavily-python", "exa-py", "cohere"} <= search


def test_browse_extra_contents(pp):
    browse = _names(pp["project"]["optional-dependencies"]["browse"])
    assert {"crawl4ai", "browser-use"} <= browse


def test_grounding_extra_contents(pp):
    grounding = _names(pp["project"]["optional-dependencies"]["grounding"])
    assert "sentence-transformers" in grounding   # NLI verifier + BGE reranker


def test_all_composes_extras(pp):
    all_dep = pp["project"]["optional-dependencies"]["all"]
    # `[all]` references the package's own extras, not a flat re-list.
    assert any("bad-research[" in d for d in all_dep)
```

- [ ] **2.2** Run — FAIL (no `[project.optional-dependencies]` yet):

```bash
python -m pytest tests/test_packaging/test_pyproject.py -q
```

Expected: failures on `test_extras_groups_exist`, `test_search_extra_contents`, etc.

- [ ] **2.3** Add the extras block to `pyproject.toml` (insert after `[project.scripts]` is fine; TOML order is irrelevant):

```toml
[project.optional-dependencies]
# Web search + neural retrieval providers (Plans 02/03). Key-gated at runtime.
search = [
    "tavily-python>=0.5",
    "exa-py>=2.0.0",
    "cohere>=5.0",            # embed-v3 + rerank-v3.5
    "firecrawl-py>=1.0",
]
# Browse/extract escalation ladder (Plan 04). Pulls Playwright/Chromium — heavy.
browse = [
    "crawl4ai>=0.4",
    "browser-use>=0.1",
    "agentql>=1.0",
]
# Offline grounding: NLI entailment verifier + local BGE reranker (Plan 06).
grounding = [
    "sentence-transformers>=3.0",   # nli-deberta-v3-base + bge-reranker-v2-m3
]
# MCP face (hyperresearch base).
mcp = ["mcp>=1.6"]
# Everything — references the package's own extras so versions stay single-sourced.
all = ["bad-research[search,browse,grounding,mcp]"]
# Test + lint toolchain.
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "mypy>=1.8",
]
```

- [ ] **2.4** Run — PASS:

```bash
python -m pytest tests/test_packaging/test_pyproject.py -q
```

Expected: all tests pass (now ~9 tests in the file).

- [ ] **2.5** Verify the lean base install really resolves without the heavy stack (sanity, offline metadata check — do not actually pip-install torch in CI):

```bash
python - <<'PY'
import tomllib, pathlib
pp = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
base = pp["project"]["dependencies"]
print("base dep count:", len(base))
assert all("torch" not in d and "playwright" not in d for d in base)
print("lean base ok")
PY
```

Expected: `base dep count: 12` then `lean base ok`.

- [ ] **2.6** Commit.

```bash
git add -A && git commit -m "feat(packaging): optional-extras groups [search]/[browse]/[grounding]/[all]/[dev]; base stays lean (tested)"
```

---

## Task 3 — Provider registry (`providers.py`) (RED → GREEN)

**Goal:** A pure, network-free registry that maps each provider to its env var, import name, owning extra, and capability — so `bad doctor` and `bad calibrate` can report exactly what is active.

- [ ] **3.1** Write `tests/test_providers.py`:

```python
"""Provider registry: env + import availability, no network."""
from __future__ import annotations

import pytest

from bad_research.providers import (
    PROVIDERS,
    ProviderStatus,
    active_providers,
    provider_status,
)


def test_registry_covers_expected_providers():
    names = {p.name for p in PROVIDERS}
    assert {"anthropic", "tavily", "exa", "cohere", "firecrawl",
            "browser_use", "searxng", "agentql"} <= names


def test_status_reads_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-xxx")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    statuses = {s.name: s for s in provider_status()}
    assert statuses["tavily"].key_present is True
    assert statuses["exa"].key_present is False


def test_searxng_needs_no_key(monkeypatch):
    # SearXNG is the zero-key default lane — always "key_present" (no key required).
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    statuses = {s.name: s for s in provider_status()}
    assert statuses["searxng"].requires_key is False
    assert statuses["searxng"].key_present is True


def test_active_providers_requires_key_and_import(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    active = active_providers()
    # anthropic is a base dep, so if its key is set AND the import resolves, it's active.
    names = {s.name for s in active}
    if any(s.name == "anthropic" and s.import_present for s in provider_status()):
        assert "anthropic" in names


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")
```

- [ ] **3.2** Run — FAIL (`No module named bad_research.providers`):

```bash
python -m pytest tests/test_providers.py -q
```

- [ ] **3.3** Write `src/bad_research/providers.py`:

```python
"""Provider registry — what's installed, what's keyed, what's active.

Pure and network-free: `bad doctor` and `bad calibrate` use this to report which
providers can run. A provider is *active* iff its key is present (or it needs none)
AND its client library imports. Single source of truth for the optional-extras map.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    env_var: str | None          # None → no key required (e.g. SearXNG, self-host)
    import_name: str | None      # the module that must import for the client to work
    extra: str                   # which `pip install bad-research[<extra>]` ships it
    capability: str              # "llm" | "search" | "browse" | "embed" | "rerank"


# The registry. Keys are read from env OR ~/.config/bad-research/config.toml (SPEC §12);
# this table only knows the env-var name — config.toml merging is the caller's job.
PROVIDERS: tuple[Provider, ...] = (
    Provider("anthropic",  "ANTHROPIC_API_KEY",  "anthropic",  "(base)",    "llm"),
    Provider("cohere",     "COHERE_API_KEY",     "cohere",     "search",    "embed"),
    Provider("tavily",     "TAVILY_API_KEY",     "tavily",     "search",    "search"),
    Provider("exa",        "EXA_API_KEY",        "exa_py",     "search",    "search"),
    Provider("sonar",      "PPLX_API_KEY",       None,         "(base)",    "search"),
    Provider("firecrawl",  "FIRECRAWL_API_KEY",  "firecrawl",  "search",    "browse"),
    Provider("agentql",    "AGENTQL_API_KEY",    "agentql",    "browse",    "browse"),
    Provider("browserbase","BROWSERBASE_API_KEY","browserbase","browse",    "browse"),
    Provider("browser_use","",                   "browser_use","browse",    "browse"),
    Provider("crawl4ai",   "",                   "crawl4ai",   "browse",    "browse"),
    Provider("searxng",    "",                   None,         "(base)",    "search"),
)


@dataclass
class ProviderStatus:
    name: str
    capability: str
    extra: str
    requires_key: bool
    key_present: bool
    import_present: bool
    active: bool


def _import_ok(import_name: str | None) -> bool:
    if not import_name:
        return True   # no client lib required (SearXNG, Sonar via httpx)
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def provider_status() -> list[ProviderStatus]:
    """Status for every registered provider. No network, no config-file read."""
    out: list[ProviderStatus] = []
    for p in PROVIDERS:
        requires_key = bool(p.env_var)
        key_present = (not requires_key) or bool(os.environ.get(p.env_var or ""))
        import_present = _import_ok(p.import_name)
        out.append(ProviderStatus(
            name=p.name,
            capability=p.capability,
            extra=p.extra,
            requires_key=requires_key,
            key_present=key_present,
            import_present=import_present,
            active=key_present and import_present,
        ))
    return out


def active_providers() -> list[ProviderStatus]:
    """Only the providers that can actually run right now."""
    return [s for s in provider_status() if s.active]
```

- [ ] **3.4** Run — PASS:

```bash
python -m pytest tests/test_providers.py -q
```

Expected: `5 passed`.

- [ ] **3.5** Commit.

```bash
git add -A && git commit -m "feat(providers): network-free provider registry (env+import → active) (tested)"
```

---

## Task 4 — Reuse hyperresearch's output helpers (no new code, wire-up only)

**Goal:** `doctor` and `calibrate` must emit `--json` in the same envelope as every other command. Confirm the forked `bad_research.models.output.success`/`error` helpers exist; if not (isolation), stub them.

- [ ] **4.1** Confirm or stub:

```bash
python -c "from bad_research.models.output import success, error; print('ok')" 2>/dev/null || {
  mkdir -p src/bad_research/models
  test -f src/bad_research/models/__init__.py || touch src/bad_research/models/__init__.py
  cat > src/bad_research/models/output.py <<'PY'
"""Output envelope (forked from hyperresearch). {ok, data, vault} / {ok, error, code}."""
from __future__ import annotations

def success(data, *, vault=None):
    return {"ok": True, "data": data, "vault": vault}

def error(message: str, code: str):
    return {"ok": False, "error": message, "code": code}
PY
  cat > src/bad_research/cli/_output.py <<'PY'
"""Console + JSON output (forked from hyperresearch)."""
from __future__ import annotations
import json
from rich.console import Console
console = Console()

def output(payload, *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload))
PY
}
python -c "from bad_research.models.output import success, error; from bad_research.cli._output import console, output; print('ok')"
```

Expected: `ok`.

- [ ] **4.2** Commit (only if stubs were created).

```bash
git add -A && git commit -m "chore(cli): ensure output envelope helpers present for doctor/calibrate" --allow-empty
```

---

## Task 5 — `bad doctor` command (RED → GREEN)

**Goal:** `bad doctor` reports each provider's active/inactive state (from env + import), the vault path, and the model-tier map — never touching the network. `--json` returns the structured status.

- [ ] **5.1** Write `tests/test_packaging/test_doctor.py`:

```python
"""`bad doctor` — active-provider report, no network."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_doctor_runs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "anthropic" in result.output.lower()


def test_doctor_reports_active_from_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-zzz")
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["tavily"]["key_present"] is True


def test_doctor_searxng_always_keyless(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["searxng"]["requires_key"] is False


def test_doctor_includes_vault_path():
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    assert "vault_root" in data
    assert "model_tiers" in data
```

- [ ] **5.2** Run — FAIL (no `doctor` command registered):

```bash
python -m pytest tests/test_packaging/test_doctor.py -q
```

- [ ] **5.3** Write `src/bad_research/cli/doctor.py`:

```python
"""`bad doctor` — report which providers/keys are active. No network calls."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import typer

from bad_research.cli._output import console, output
from bad_research.models.output import success
from bad_research.providers import provider_status


def doctor(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
) -> None:
    """Report active providers, vault path, and model tiers. Network-free."""
    statuses = provider_status()

    # Vault root + model tiers from config (best-effort; defaults if config absent).
    try:
        from bad_research.config import BadResearchConfig

        cfg = BadResearchConfig()
        vault_root = str(cfg.vault_root)
        model_tiers = dict(cfg.model_tiers)
    except Exception:
        vault_root = str(Path.home() / ".bad-research")
        model_tiers = {
            "triage": "claude-haiku-4-5",
            "work": "claude-sonnet-4-6",
            "heavy": "claude-opus-4-7",
        }

    data = {
        "vault_root": vault_root,
        "model_tiers": model_tiers,
        "providers": [asdict(s) for s in statuses],
        "active_count": sum(1 for s in statuses if s.active),
    }

    if json_output:
        output(success(data, vault=vault_root), json_mode=True)
        return

    console.print("[bold]bad doctor[/] — provider status\n")
    console.print(f"[dim]vault:[/] {vault_root}")
    console.print(f"[dim]models:[/] {model_tiers}\n")
    for s in statuses:
        if s.active:
            mark, color = "OK ", "green"
        elif s.requires_key and not s.key_present:
            mark, color = "key", "yellow"
        else:
            mark, color = "off", "dim"
        note = []
        if s.requires_key and not s.key_present:
            note.append("no key")
        if not s.import_present:
            note.append(f"pip install 'bad-research[{s.extra}]'")
        suffix = f"  [dim]({'; '.join(note)})[/]" if note else ""
        console.print(f"  [{color}]{mark}[/] {s.name:<12} [dim]{s.capability}[/]{suffix}")
    console.print(f"\n[bold]{data['active_count']}[/] provider(s) active.")
    if data["active_count"] == 0:
        console.print("[dim]Zero-key fallback (SearXNG + crawl4ai + BM25) still works.[/]")
```

- [ ] **5.4** Register `doctor` in `src/bad_research/cli/__init__.py` (this plan's only edit to that file besides Task 13):

```python
# in bad_research/cli/__init__.py, after the app/callback definition:
from bad_research.cli.doctor import doctor as _doctor
app.command("doctor")(_doctor)
```

- [ ] **5.5** Run — PASS:

```bash
python -m pytest tests/test_packaging/test_doctor.py -q && bad doctor
```

Expected: `4 passed`; `bad doctor` prints the provider table (most `off`/`key` in a clean env, with the zero-key fallback line).

- [ ] **5.6** Commit.

```bash
git add -A && git commit -m "feat(cli): bad doctor — network-free active-provider report (tested)"
```

---

## Task 6 — `bad install` idempotency guarantee (RED → GREEN)

**Goal:** Hold Plan 08's installer to the contract: running `bad install --global` twice produces **identical disk state** and the second run reports zero mutations. This plan owns the *test* and the idempotency *wrapper assertion*, not the installer body.

- [ ] **6.1** Write `tests/test_packaging/test_install_idempotent.py`:

```python
"""`bad install` idempotency: run twice → identical disk state, no second-run mutations."""
from __future__ import annotations

import hashlib
from pathlib import Path

from bad_research.cli.install import install_global_hooks


def _tree_digest(root: Path) -> str:
    """Order-stable digest of every file path + content under root."""
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def test_install_global_twice_is_idempotent(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()

    first = install_global_hooks(home=home, bad_path="bad")
    digest_after_first = _tree_digest(home / ".claude")
    assert first, "first install should report at least one action"

    second = install_global_hooks(home=home, bad_path="bad")
    digest_after_second = _tree_digest(home / ".claude")

    # Contract 1: second run mutates nothing on disk.
    assert digest_after_first == digest_after_second
    # Contract 2: second run reports an empty action list (no-op).
    assert second == []


def test_install_creates_skill_dir(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home=home, bad_path="bad")
    assert (home / ".claude" / "skills" / "bad-research").is_dir()
```

- [ ] **6.2** Run — against the real Plan 08 installer if present, the stub otherwise:

```bash
python -m pytest tests/test_packaging/test_install_idempotent.py -q
```

Expected (with the Task 0.3 stub or a correct Plan 08 installer): `2 passed`. **If this FAILS against Plan 08's real installer**, that is a Plan 08 idempotency bug — file it and (per the writing-plans discipline) do not paper over it here; the test is the contract.

- [ ] **6.3** Wire `install` onto the CLI if Plan 08 hasn't (so `bad install` is invokable). Add to `bad_research/cli/__init__.py` only if absent:

```python
# only if not already registered by Plan 08:
try:
    app.registered_commands  # noqa
    if not any(c.name == "install" for c in app.registered_commands):
        from bad_research.cli.install import install as _install  # type: ignore[attr-defined]
        app.command("install")(_install)
except Exception:
    pass
```

> If the Task-0.3 stub has no `install()` typer command (only `install_global_hooks`), skip the wire-up — the idempotency test targets `install_global_hooks` directly, which is the load-bearing contract. The CLI command is Plan 08's to register.

- [ ] **6.4** Commit.

```bash
git add -A && git commit -m "test(install): idempotency contract — bad install twice → identical disk state"
```

---

## Task 7 — Top-level pytest config: markers + coverage floor (RED → GREEN)

**Goal:** One `[tool.pytest.ini_options]` block runs every per-plan suite, defines `unit`/`integration`/`live` markers (with `--strict-markers`), and enforces an 80% coverage floor. `live` tests auto-skip without keys.

- [ ] **7.1** Write `tests/test_packaging/test_pytest_config.py`:

```python
"""pytest config: markers declared, coverage floor set, testpaths point at tests/."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cfg() -> dict:
    pp = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pp["tool"]["pytest"]["ini_options"]


def test_markers_declared(cfg):
    joined = "\n".join(cfg["markers"])
    for m in ("unit:", "integration:", "live:"):
        assert m in joined


def test_strict_markers_and_coverage(cfg):
    opts = cfg["addopts"]
    assert "--strict-markers" in opts
    assert "--cov=bad_research" in opts
    assert "--cov-fail-under=80" in opts


def test_testpaths(cfg):
    assert cfg["testpaths"] == ["tests"]
```

There must also be a runtime auto-skip for `live`. Add `tests/conftest.py`:

```python
"""Top-level test config: auto-skip `live` tests when no real keys are set."""
from __future__ import annotations

import os

import pytest

_LIVE_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY", "COHERE_API_KEY")


def pytest_collection_modifyitems(config, items):
    have_any_key = any(os.environ.get(k) for k in _LIVE_KEYS)
    if have_any_key and os.environ.get("BAD_RUN_LIVE") == "1":
        return  # run live tests
    skip_live = pytest.mark.skip(reason="live test: set a provider key + BAD_RUN_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
```

And a test that proves the skip works (`tests/test_packaging/test_live_skip.py`):

```python
import pytest

@pytest.mark.live
def test_live_is_skipped_by_default():
    # This body must never run in default CI; if it does, the skip hook is broken.
    raise AssertionError("live test ran without BAD_RUN_LIVE=1 — skip hook failed")
```

- [ ] **7.2** Run — FAIL (no markers / no cov flags / live test would error):

```bash
python -m pytest tests/test_packaging/test_pytest_config.py -q
```

- [ ] **7.3** Add the pytest + coverage config to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers --cov=bad_research --cov-report=term-missing --cov-fail-under=80"
markers = [
    "unit: fast, isolated, no network, no disk beyond tmp_path (default).",
    "integration: touches multiple modules / real SQLite / LanceDB on tmp dirs; still offline.",
    "live: hits a real provider API; auto-skipped unless a key is set AND BAD_RUN_LIVE=1.",
]

[tool.coverage.run]
source = ["bad_research"]
branch = true
omit = ["*/tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
    "\\.\\.\\.",
]
```

- [ ] **7.4** Run — PASS (markers + live-skip):

```bash
python -m pytest tests/test_packaging/test_pytest_config.py tests/test_packaging/test_live_skip.py -q -p no:cov
```

> Run this sub-set with `-p no:cov` so the 80% floor isn't applied to a 4-test slice; the floor applies to the full suite (Task 14).

Expected: `4 passed, 1 skipped` (the live test skipped).

- [ ] **7.5** Commit.

```bash
git add -A && git commit -m "test(config): top-level pytest markers (unit/integration/live) + 80% coverage floor + live auto-skip"
```

---

## Task 8 — `CostMeter`: 5-component cost metering (RED → GREEN)

**Goal:** Accumulate per-stage/per-model usage across the 5 components (`input`, `output`, `reasoning`, `citation`, `search_queries`), convert tokens → USD via the tier price table, and emit a `cost-report.json` matching Perplexity's 5-component shape. Offline only — this is for calibration reporting, never a per-run gate.

- [ ] **8.1** Write `tests/test_calibrate/test_cost.py`:

```python
"""5-component cost metering math + cost-report.json shape."""
from __future__ import annotations

import json
from pathlib import Path

from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.constants import COST_COMPONENTS


def test_components_match_perplexity_five():
    assert COST_COMPONENTS == ("input", "output", "reasoning", "citation", "search_queries")


def test_record_and_total_usd():
    m = CostMeter()
    # 1M input + 1M output tokens at "work" (sonnet 3/15 per Mtok) → $3 + $15 = $18.
    m.record(stage="synthesize", tier="work", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(m.total_usd() - 18.0) < 1e-6


def test_reasoning_priced_as_output():
    m = CostMeter()
    # reasoning tokens bill at the output rate of the tier.
    m.record(stage="draft", tier="heavy", reasoning_tokens=1_000_000)
    assert abs(m.total_usd() - 75.0) < 1e-6   # opus output = $75/Mtok


def test_search_queries_priced_flat():
    m = CostMeter()
    m.record(stage="width-sweep", tier="triage", search_queries=10)
    assert abs(m.total_usd() - 0.05) < 1e-6   # 10 * $0.005


def test_cost_report_shape(tmp_path: Path):
    m = CostMeter()
    m.record(stage="decompose", tier="triage", input_tokens=2000, output_tokens=500)
    m.record(stage="synthesize", tier="heavy", input_tokens=8000, output_tokens=4000,
             citation_tokens=300, search_queries=12)
    out = tmp_path / "cost-report.json"
    m.write(out)
    data = json.loads(out.read_text())

    assert set(data.keys()) >= {"total_usd", "by_stage", "by_component", "components"}
    assert data["components"] == list(COST_COMPONENTS)
    assert "decompose" in data["by_stage"] and "synthesize" in data["by_stage"]
    # by_component sums every component across stages.
    assert set(data["by_component"].keys()) == set(COST_COMPONENTS)
    assert data["by_stage"]["synthesize"]["search_queries"] == 12
    assert data["total_usd"] == data["by_stage"]["decompose"]["usd"] + data["by_stage"]["synthesize"]["usd"]


def test_empty_meter_is_zero(tmp_path: Path):
    m = CostMeter()
    assert m.total_usd() == 0.0
```

- [ ] **8.2** Run — FAIL:

```bash
python -m pytest tests/test_calibrate/test_cost.py -q -p no:cov
```

- [ ] **8.3** First write the constants module `src/bad_research/calibrate/constants.py` (the Frozen-constants block from the top of this plan), then write `src/bad_research/calibrate/cost.py`:

```python
"""CostMeter — 5-component cost metering (Perplexity, dossier 09 §A4.2 / 05§7).

OFFLINE only: used by the calibration harness to report where money went and to
score the `efficiency` axis. NOT a per-run gate (SPEC §10 Excluded list).
Components: input, output, reasoning, citation, search_queries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bad_research.calibrate.constants import (
    COST_COMPONENTS,
    SEARCH_QUERY_PRICE_USD,
    TIER_PRICE_USD_PER_MTOK,
)


@dataclass
class _StageCost:
    tier: str
    input: int = 0
    output: int = 0
    reasoning: int = 0
    citation: int = 0
    search_queries: int = 0

    def usd(self) -> float:
        price = TIER_PRICE_USD_PER_MTOK.get(self.tier, {"input": 0.0, "output": 0.0})
        token_usd = (
            self.input * price["input"]
            # reasoning + citation tokens bill at the tier's OUTPUT rate.
            + (self.output + self.reasoning + self.citation) * price["output"]
        ) / 1_000_000
        return token_usd + self.search_queries * SEARCH_QUERY_PRICE_USD


@dataclass
class CostMeter:
    """Accumulate per-stage 5-component usage; convert to USD; emit cost-report.json."""

    _stages: dict[str, _StageCost] = field(default_factory=dict)

    def record(
        self,
        *,
        stage: str,
        tier: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        citation_tokens: int = 0,
        search_queries: int = 0,
    ) -> None:
        sc = self._stages.get(stage)
        if sc is None:
            sc = _StageCost(tier=tier)
            self._stages[stage] = sc
        sc.tier = tier  # last writer wins on tier label
        sc.input += input_tokens
        sc.output += output_tokens
        sc.reasoning += reasoning_tokens
        sc.citation += citation_tokens
        sc.search_queries += search_queries

    def record_response(self, *, stage: str, tier: str, usage: dict,
                        search_queries: int = 0) -> None:
        """Convenience: ingest an LLMResponse.usage dict directly."""
        self.record(
            stage=stage,
            tier=tier,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            reasoning_tokens=usage.get("reasoning_tokens", 0),
            search_queries=search_queries,
        )

    def total_usd(self) -> float:
        return round(sum(sc.usd() for sc in self._stages.values()), 8)

    def by_component(self) -> dict[str, int]:
        out = {c: 0 for c in COST_COMPONENTS}
        for sc in self._stages.values():
            for c in COST_COMPONENTS:
                out[c] += getattr(sc, c)
        return out

    def to_dict(self) -> dict:
        return {
            "components": list(COST_COMPONENTS),
            "total_usd": self.total_usd(),
            "by_component": self.by_component(),
            "by_stage": {
                name: {
                    "tier": sc.tier,
                    **{c: getattr(sc, c) for c in COST_COMPONENTS},
                    "usd": round(sc.usd(), 8),
                }
                for name, sc in self._stages.items()
            },
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
```

- [ ] **8.4** Run — PASS:

```bash
python -m pytest tests/test_calibrate/test_cost.py -q -p no:cov
```

Expected: `6 passed`.

- [ ] **8.5** Commit.

```bash
git add -A && git commit -m "feat(calibrate): CostMeter 5-component metering + cost-report.json (tested)"
```

---

## Task 9 — The Judge: 5-axis rubric, stub + LLM impl (RED → GREEN)

**Goal:** A `Judge` Protocol scoring a report on the 5 axes (`factual`, `citation`, `completeness`, `source_quality`, `efficiency`), each 0.0–1.0, with a PASS/FAIL verdict. `StubJudge` is deterministic for tests; `LLMJudge` makes a **single** strong-model call (no ensemble — dossier 09 §B7) over Plan 01's `LLMProvider` and parses the JSON verdict.

- [ ] **9.1** Write `tests/test_calibrate/conftest.py`:

```python
"""Calibration test fixtures: stub judge, stub LLM, a tiny report fixture."""
from __future__ import annotations

import json

import pytest

from bad_research.llm.base import LLMResponse


@pytest.fixture
def tiny_report() -> str:
    return (
        "# Does X cause Y?\n\n"
        "Evidence indicates X correlates with Y [1]. A controlled study found a 23% "
        "increase [2]. However, confounders remain unaddressed [1].\n"
    )


@pytest.fixture
def tiny_corpus() -> list[dict]:
    return [
        {"note_id": "note-1", "url": "https://a.edu/x", "text": "X correlates with Y in cohort data."},
        {"note_id": "note-2", "url": "https://b.org/y", "text": "A controlled study found a 23% increase."},
    ]


class StubLLM:
    """Returns a canned 5-axis JSON verdict; records the prompt for assertions."""
    name = "stub-llm"

    def __init__(self, verdict: dict | None = None):
        self.last_messages = None
        self._verdict = verdict or {
            "factual": 0.9, "citation": 0.85, "completeness": 0.8,
            "source_quality": 0.78, "efficiency": 0.95,
            "rationale": "well grounded",
        }

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1) -> LLMResponse:
        self.last_messages = messages
        return LLMResponse(text=json.dumps(self._verdict), tool_calls=[],
                           usage={"input_tokens": 1200, "output_tokens": 180}, model="stub")


@pytest.fixture
def stub_llm() -> StubLLM:
    return StubLLM()
```

- [ ] **9.2** Write `tests/test_calibrate/test_judge.py`:

```python
"""Judge: StubJudge determinism + LLMJudge prompt/parse against a stub provider."""
from __future__ import annotations

from bad_research.calibrate.judge import (
    AxisScores,
    JudgeVerdict,
    LLMJudge,
    StubJudge,
)
from bad_research.calibrate.constants import JUDGE_AXES, OVERALL_PASS_THRESHOLD

from tests.test_calibrate.conftest import StubLLM


def test_stub_judge_is_deterministic(tiny_report, tiny_corpus):
    j = StubJudge(scores={a: 0.9 for a in JUDGE_AXES})
    v1 = j.judge("q", tiny_report, tiny_corpus)
    v2 = j.judge("q", tiny_report, tiny_corpus)
    assert v1.overall == v2.overall
    assert v1.passed is True


def test_verdict_pass_logic():
    high = AxisScores(factual=0.9, citation=0.9, completeness=0.9,
                      source_quality=0.9, efficiency=0.9)
    v = JudgeVerdict.from_scores(high, rationale="ok")
    assert v.passed is True
    assert abs(v.overall - 0.9) < 1e-9

    low = AxisScores(factual=0.9, citation=0.5, completeness=0.9,
                     source_quality=0.9, efficiency=0.9)  # citation below per-axis floor
    v2 = JudgeVerdict.from_scores(low, rationale="weak cites")
    assert v2.passed is False


def test_llm_judge_single_call_and_parse(stub_llm, tiny_report, tiny_corpus):
    j = LLMJudge(provider=stub_llm)
    v = j.judge("Does X cause Y?", tiny_report, tiny_corpus)
    # exactly one provider call; all five axes present.
    assert stub_llm.last_messages is not None
    assert set(v.scores.as_dict().keys()) == set(JUDGE_AXES)
    assert 0.0 <= v.overall <= 1.0
    # the corpus + query are in the prompt the judge sent.
    sent = "".join(m.content for m in stub_llm.last_messages if isinstance(m.content, str))
    assert "Does X cause Y?" in sent
    assert "note-1" in sent


def test_llm_judge_clamps_out_of_range(tiny_report, tiny_corpus):
    bad = StubLLM(verdict={"factual": 1.4, "citation": -0.2, "completeness": 0.8,
                           "source_quality": 0.8, "efficiency": 0.8, "rationale": "x"})
    v = LLMJudge(provider=bad).judge("q", tiny_report, tiny_corpus)
    assert 0.0 <= v.scores.factual <= 1.0
    assert 0.0 <= v.scores.citation <= 1.0
```

- [ ] **9.3** Run — FAIL:

```bash
python -m pytest tests/test_calibrate/test_judge.py -q -p no:cov
```

- [ ] **9.4** Write `src/bad_research/calibrate/judge.py`:

```python
"""The 5-axis LLM-judge rubric (dossier 09 §B7; CLAUDE_RESEARCH.md:39; SPEC §14).

A SINGLE strong-model call per report — NOT an ensemble (ensemble tested WORSE,
dossier 09 §B7). Scores five axes 0.0–1.0; PASS iff every axis ≥ AXIS_PASS_THRESHOLD
AND the mean ≥ OVERALL_PASS_THRESHOLD. OFFLINE calibration only — never a per-run gate.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Protocol

from bad_research.calibrate.constants import (
    AXIS_PASS_THRESHOLD,
    JUDGE_AXES,
    JUDGE_MAX_TOKENS,
    JUDGE_TEMPERATURE,
    JUDGE_TIER,
    OVERALL_PASS_THRESHOLD,
)
from bad_research.llm.base import LLMMessage, LLMProvider


@dataclass
class AxisScores:
    factual: float
    citation: float
    completeness: float
    source_quality: float
    efficiency: float

    def as_dict(self) -> dict[str, float]:
        return {a: getattr(self, a) for a in JUDGE_AXES}

    @staticmethod
    def _clamp(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    @classmethod
    def from_raw(cls, raw: dict) -> "AxisScores":
        return cls(**{a: cls._clamp(raw.get(a, 0.0)) for a in JUDGE_AXES})


@dataclass
class JudgeVerdict:
    scores: AxisScores
    overall: float
    passed: bool
    rationale: str

    @classmethod
    def from_scores(cls, scores: AxisScores, *, rationale: str) -> "JudgeVerdict":
        vals = list(scores.as_dict().values())
        overall = round(sum(vals) / len(vals), 9)
        passed = all(v >= AXIS_PASS_THRESHOLD for v in vals) and overall >= OVERALL_PASS_THRESHOLD
        return cls(scores=scores, overall=overall, passed=passed, rationale=rationale)

    def to_dict(self) -> dict:
        return {
            "scores": self.scores.as_dict(),
            "overall": self.overall,
            "passed": self.passed,
            "rationale": self.rationale,
        }


class Judge(Protocol):
    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict: ...


@dataclass
class StubJudge:
    """Deterministic judge for tests/offline use. No LLM call."""
    scores: dict[str, float]

    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict:
        s = AxisScores.from_raw(self.scores)
        return JudgeVerdict.from_scores(s, rationale="stub")


JUDGE_SYSTEM = (
    "You are a rigorous, calibrated research-report judge. Score the report on five "
    "axes, each from 0.0 to 1.0. Be strict; reserve >0.9 for excellent work.\n"
    "Axes:\n"
    "- factual: are claims accurate and supported by the provided corpus?\n"
    "- citation: does every non-trivial claim carry a citation that the corpus supports "
    "(no fabricated or mis-attributed cites)?\n"
    "- completeness: does the report cover the question's sub-parts using the corpus?\n"
    "- source_quality: are the cited sources authoritative and on-topic?\n"
    "- efficiency: is the report concise — no padding, no redundancy, right length?\n"
    "Return ONLY a JSON object: "
    '{"factual":0-1,"citation":0-1,"completeness":0-1,"source_quality":0-1,'
    '"efficiency":0-1,"rationale":"<=2 sentences"}. No prose outside the JSON.'
)


@dataclass
class LLMJudge:
    """Single-call 5-axis judge over an LLMProvider (Plan 01 seam)."""
    provider: LLMProvider
    tier: str = JUDGE_TIER

    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict:
        corpus_block = "\n".join(
            f"[{c.get('note_id', i)}] {c.get('url', '')}\n{c.get('text', '')[:1200]}"
            for i, c in enumerate(corpus)
        )
        user = (
            f"QUERY:\n{query}\n\n"
            f"CORPUS (the evidence the report had access to):\n{corpus_block}\n\n"
            f"REPORT TO JUDGE:\n{report}\n\n"
            "Score now. JSON only."
        )
        resp = self.provider.complete(
            [LLMMessage(role="system", content=JUDGE_SYSTEM),
             LLMMessage(role="user", content=user)],
            tier=self.tier,            # type: ignore[arg-type]
            max_tokens=JUDGE_MAX_TOKENS,
            temperature=JUDGE_TEMPERATURE,
        )
        raw = _extract_json(resp.text)
        scores = AxisScores.from_raw(raw)
        return JudgeVerdict.from_scores(scores, rationale=str(raw.get("rationale", "")))


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction — handles ```json fences and leading/trailing prose."""
    text = text.strip()
    if "```" in text:
        # take the content of the first fenced block
        parts = text.split("```")
        for part in parts:
            part = part.removeprefix("json").strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {a: 0.0 for a in JUDGE_AXES}


# re-export for convenience
__all__ = ["AxisScores", "JudgeVerdict", "Judge", "StubJudge", "LLMJudge", "asdict"]
```

- [ ] **9.5** Run — PASS:

```bash
python -m pytest tests/test_calibrate/test_judge.py -q -p no:cov
```

Expected: `4 passed`.

- [ ] **9.6** Commit.

```bash
git add -A && git commit -m "feat(calibrate): 5-axis single-call LLM judge + deterministic StubJudge (tested)"
```

---

## Task 10 — Baselines: key-gated, skip without keys (RED → GREEN)

**Goal:** `Baseline` Protocol for "run the same query through a comparison system." `HyperresearchBaseline` runs the upstream package if importable; `PerplexityBaseline`/`GrokBaseline` raise `BaselineUnavailable` when their key is absent (so the harness silently drops them — SPEC §14 "key-gated, skipped otherwise").

- [ ] **10.1** Write `tests/test_calibrate/test_baselines.py`:

```python
"""Baselines are key-gated: no key → unavailable, never a crash."""
from __future__ import annotations

import pytest

from bad_research.calibrate.baselines import (
    BaselineUnavailable,
    GrokBaseline,
    PerplexityBaseline,
    available_baselines,
)


def test_perplexity_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("PPLX_API_KEY", raising=False)
    b = PerplexityBaseline()
    assert b.available() is False
    with pytest.raises(BaselineUnavailable):
        b.run("any query")


def test_grok_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert GrokBaseline().available() is False


def test_available_baselines_filters(monkeypatch):
    monkeypatch.delenv("PPLX_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    names = {b.name for b in available_baselines()}
    # No external keys → only the local hyperresearch baseline is even considered;
    # and it's only present if the upstream package imports.
    assert "perplexity" not in names
    assert "grok" not in names
```

- [ ] **10.2** Run — FAIL:

```bash
python -m pytest tests/test_calibrate/test_baselines.py -q -p no:cov
```

- [ ] **10.3** Write `src/bad_research/calibrate/baselines.py`:

```python
"""Calibration baselines — run the same query through a comparison system.

Key-gated (SPEC §14): a baseline that needs a key it doesn't have is silently
dropped by the harness, never a crash. The hyperresearch baseline runs the
upstream package if it's importable.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Protocol


class BaselineUnavailable(RuntimeError):
    """Raised when a baseline is invoked without its key/dependency."""


@dataclass
class BaselineResult:
    name: str
    report: str
    corpus: list[dict]   # the evidence that baseline used, for fair judging


class Baseline(Protocol):
    name: str
    def available(self) -> bool: ...
    def run(self, query: str) -> BaselineResult: ...


@dataclass
class HyperresearchBaseline:
    """Runs the upstream `hyperresearch` package if installed (offline-friendly)."""
    name: str = "hyperresearch"

    def available(self) -> bool:
        return importlib.util.find_spec("hyperresearch") is not None

    def run(self, query: str) -> BaselineResult:
        if not self.available():
            raise BaselineUnavailable("hyperresearch package not importable")
        # The upstream pipeline is Claude-Code-driven; for offline calibration we
        # can only run its deterministic vault search. The harness treats a present-
        # but-non-LLM baseline as a structural comparator. Real LLM comparison
        # happens when run inside a Claude Code host (out of scope for the test path).
        raise BaselineUnavailable(
            "hyperresearch baseline requires a Claude Code host; use --baselines none offline"
        )


@dataclass
class _ApiBaseline:
    name: str
    env_var: str

    def available(self) -> bool:
        return bool(os.environ.get(self.env_var))

    def run(self, query: str) -> BaselineResult:
        if not self.available():
            raise BaselineUnavailable(f"{self.name}: {self.env_var} not set")
        # Real API call lives behind the key-gate; only reached when keyed (live tier).
        raise NotImplementedError(  # pragma: no cover
            f"{self.name} live call — implement against its deep-research API when keyed"
        )


class PerplexityBaseline(_ApiBaseline):
    def __init__(self) -> None:
        super().__init__(name="perplexity", env_var="PPLX_API_KEY")


class GrokBaseline(_ApiBaseline):
    def __init__(self) -> None:
        super().__init__(name="grok", env_var="XAI_API_KEY")


def available_baselines() -> list[Baseline]:
    """Every baseline whose key/dependency is present right now."""
    candidates: list[Baseline] = [
        HyperresearchBaseline(),
        PerplexityBaseline(),
        GrokBaseline(),
    ]
    return [b for b in candidates if b.available()]
```

- [ ] **10.4** Run — PASS:

```bash
python -m pytest tests/test_calibrate/test_baselines.py -q -p no:cov
```

Expected: `3 passed`.

- [ ] **10.5** Commit.

```bash
git add -A && git commit -m "feat(calibrate): key-gated baselines (hyperresearch + Perplexity/Grok), skip without keys (tested)"
```

---

## Task 11 — The harness: `run_calibration` + `CalibrationReport` (RED → GREEN)

**Goal:** Wire `BadRunner` (the function that produces a bad-research report + corpus + cost meter for a query) → judge each report → compare against available baselines → assemble a `CalibrationReport` with `.to_json()` and `.to_markdown()`. Mock the runner and judge in tests; zero network.

- [ ] **11.1** Write `tests/test_calibrate/test_harness.py`:

```python
"""End-to-end harness on a fixture: mocked runner + mocked judge → CalibrationReport."""
from __future__ import annotations

import json

from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.harness import (
    BadRunOutput,
    CalibrationReport,
    run_calibration,
)
from bad_research.calibrate.judge import StubJudge
from bad_research.calibrate.constants import JUDGE_AXES


def _fake_runner(query: str) -> BadRunOutput:
    meter = CostMeter()
    meter.record(stage="synthesize", tier="heavy", input_tokens=8000, output_tokens=4000,
                 citation_tokens=200, search_queries=15)
    return BadRunOutput(
        report=f"# {query}\n\nA grounded claim [1].\n",
        corpus=[{"note_id": "n1", "url": "https://a.edu", "text": "supporting evidence"}],
        cost=meter,
    )


def test_run_calibration_offline():
    judge = StubJudge(scores={a: 0.88 for a in JUDGE_AXES})
    report = run_calibration(
        "Does X cause Y?",
        runner=_fake_runner,
        baselines=[],          # offline: no external baselines
        judge=judge,
    )
    assert isinstance(report, CalibrationReport)
    assert report.query == "Does X cause Y?"
    assert report.bad.verdict.passed is True
    assert report.bad.cost_usd > 0
    assert report.baselines == []   # none available


def test_calibration_report_json_roundtrip():
    judge = StubJudge(scores={a: 0.8 for a in JUDGE_AXES})
    report = run_calibration("q", runner=_fake_runner, baselines=[], judge=judge)
    blob = report.to_json()
    data = json.loads(blob)
    assert data["query"] == "q"
    assert "bad" in data and "verdict" in data["bad"] and "cost" in data["bad"]
    assert set(data["bad"]["verdict"]["scores"].keys()) == set(JUDGE_AXES)


def test_calibration_report_markdown():
    judge = StubJudge(scores={a: 0.8 for a in JUDGE_AXES})
    md = run_calibration("q", runner=_fake_runner, baselines=[], judge=judge).to_markdown()
    assert "# Calibration Report" in md
    assert "factual" in md
    assert "$" in md   # cost line rendered


def test_baseline_comparison_when_available():
    """A baseline whose .run() succeeds is judged and a delta is computed."""
    from bad_research.calibrate.baselines import BaselineResult

    class FakeBaseline:
        name = "fake"
        def available(self): return True
        def run(self, query):
            return BaselineResult(name="fake",
                                  report=f"# {query}\n\nweaker claim.\n",
                                  corpus=[{"note_id": "b1", "url": "x", "text": "y"}])

    # judge scores the baseline lower than bad-research
    class TieredJudge:
        def judge(self, query, report, corpus):
            score = 0.9 if "grounded" in report or "[1]" in report else 0.6
            from bad_research.calibrate.judge import AxisScores, JudgeVerdict
            return JudgeVerdict.from_scores(
                AxisScores.from_raw({a: score for a in JUDGE_AXES}), rationale="t")

    report = run_calibration("q", runner=_fake_runner,
                             baselines=[FakeBaseline()], judge=TieredJudge())
    assert len(report.baselines) == 1
    b = report.baselines[0]
    assert b.name == "fake"
    # bad-research scored higher → positive delta in its favor.
    assert report.bad.verdict.overall - b.verdict.overall > 0
    assert abs(report.delta_vs("fake") - (report.bad.verdict.overall - b.verdict.overall)) < 1e-9
```

- [ ] **11.2** Run — FAIL:

```bash
python -m pytest tests/test_calibrate/test_harness.py -q -p no:cov
```

- [ ] **11.3** Write `src/bad_research/calibrate/harness.py`:

```python
"""Calibration harness — run a query through bad-research, judge it, compare to
baselines, emit a CalibrationReport. OFFLINE (SPEC §14): never a per-run gate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from bad_research.calibrate.baselines import Baseline, BaselineUnavailable
from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.judge import Judge, JudgeVerdict


@dataclass
class BadRunOutput:
    """What the bad-research runner returns for one query."""
    report: str
    corpus: list[dict]
    cost: CostMeter


# A runner is any callable query -> BadRunOutput. The CLI supplies the real one
# (drives the pipeline); tests supply a fake. Keeps the harness host-agnostic.
BadRunner = Callable[[str], BadRunOutput]


@dataclass
class SystemResult:
    name: str
    report: str
    verdict: JudgeVerdict
    cost_usd: float = 0.0


@dataclass
class CalibrationReport:
    query: str
    bad: SystemResult
    baselines: list[SystemResult] = field(default_factory=list)

    def delta_vs(self, baseline_name: str) -> float:
        """bad-research overall minus the named baseline's overall (positive = we win)."""
        for b in self.baselines:
            if b.name == baseline_name:
                return round(self.bad.verdict.overall - b.verdict.overall, 9)
        raise KeyError(baseline_name)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "bad": {
                "verdict": self.bad.verdict.to_dict(),
                "cost": self.bad.cost_usd,
            },
            "baselines": [
                {"name": b.name, "verdict": b.verdict.to_dict(), "cost": b.cost_usd}
                for b in self.baselines
            ],
            "deltas": {b.name: self.delta_vs(b.name) for b in self.baselines},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        v = self.bad.verdict
        lines = [
            "# Calibration Report",
            "",
            f"**Query:** {self.query}",
            "",
            "## bad-research",
            f"- overall: **{v.overall:.3f}** — {'PASS' if v.passed else 'FAIL'}",
            f"- cost: **${self.bad.cost_usd:.4f}**",
            "- axes:",
        ]
        for axis, score in v.scores.as_dict().items():
            lines.append(f"  - {axis}: {score:.2f}")
        lines.append(f"- rationale: {v.rationale}")
        if self.baselines:
            lines += ["", "## Baselines", "", "| system | overall | pass | cost | Δ (bad−base) |",
                      "|---|---|---|---|---|"]
            for b in self.baselines:
                lines.append(
                    f"| {b.name} | {b.verdict.overall:.3f} | "
                    f"{'PASS' if b.verdict.passed else 'FAIL'} | ${b.cost_usd:.4f} | "
                    f"{self.delta_vs(b.name):+.3f} |"
                )
        else:
            lines += ["", "_No external baselines available (key-gated; offline run)._"]
        return "\n".join(lines) + "\n"


def run_calibration(
    query: str,
    *,
    runner: BadRunner,
    baselines: list[Baseline],
    judge: Judge,
) -> CalibrationReport:
    """Run + judge bad-research and every available baseline on one query."""
    out = runner(query)
    bad_verdict = judge.judge(query, out.report, out.corpus)
    bad = SystemResult(
        name="bad-research",
        report=out.report,
        verdict=bad_verdict,
        cost_usd=out.cost.total_usd(),
    )

    baseline_results: list[SystemResult] = []
    for b in baselines:
        try:
            if not b.available():
                continue
            br = b.run(query)
        except (BaselineUnavailable, NotImplementedError):
            continue
        bv = judge.judge(query, br.report, br.corpus)
        baseline_results.append(SystemResult(name=br.name, report=br.report, verdict=bv))

    return CalibrationReport(query=query, bad=bad, baselines=baseline_results)
```

- [ ] **11.4** Run — PASS:

```bash
python -m pytest tests/test_calibrate/test_harness.py -q -p no:cov
```

Expected: `4 passed`.

- [ ] **11.5** Add the `calibrate/__init__.py` re-exports:

```python
# src/bad_research/calibrate/__init__.py
"""Offline calibration harness (SPEC §14). Never a per-run gate."""
from bad_research.calibrate.baselines import (
    Baseline,
    BaselineResult,
    BaselineUnavailable,
    available_baselines,
)
from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.harness import (
    BadRunner,
    BadRunOutput,
    CalibrationReport,
    SystemResult,
    run_calibration,
)
from bad_research.calibrate.judge import (
    AxisScores,
    Judge,
    JudgeVerdict,
    LLMJudge,
    StubJudge,
)

__all__ = [
    "Baseline", "BaselineResult", "BaselineUnavailable", "available_baselines",
    "CostMeter", "BadRunner", "BadRunOutput", "CalibrationReport", "SystemResult",
    "run_calibration", "AxisScores", "Judge", "JudgeVerdict", "LLMJudge", "StubJudge",
]
```

- [ ] **11.6** Commit.

```bash
git add -A && git commit -m "feat(calibrate): run_calibration harness + CalibrationReport (json/markdown) (tested)"
```

---

## Task 12 — Wire a real `BadRunner` from config (the production bridge)

**Goal:** Provide `default_runner(config) -> BadRunner` that, given a `BadResearchConfig`, drives the actual bad-research pipeline (Plans 02–08) for one query and returns `BadRunOutput`. This is the only place the harness touches the live pipeline. It is `live`-tier (needs keys) and stubbed in unit tests.

- [ ] **12.1** Write `tests/test_calibrate/test_runner_bridge.py`:

```python
"""The config→runner bridge: shape-only in unit mode; live behind a key."""
from __future__ import annotations

import pytest

from bad_research.calibrate.runner import default_runner


def test_default_runner_returns_callable():
    runner = default_runner(config=None)   # None → default config
    assert callable(runner)


@pytest.mark.live
def test_default_runner_runs_real_pipeline():
    runner = default_runner(config=None)
    out = runner("What is the capital of France?")
    assert out.report
    assert out.cost.total_usd() >= 0
```

- [ ] **12.2** Run — FAIL:

```bash
python -m pytest tests/test_calibrate/test_runner_bridge.py -q -p no:cov
```

Expected: the first test fails (no `runner` module); the `live` test is skipped.

- [ ] **12.3** Write `src/bad_research/calibrate/runner.py`:

```python
"""Bridge: BadResearchConfig → BadRunner. The only seam that drives the live pipeline.

Unit tests use a stub runner (Task 11); this is the production path used by
`bad calibrate`. It is `live` (needs keys) — when the pipeline modules (Plans 02-08)
aren't wired or keys are absent, it raises so the CLI can fall back to a stub.
"""
from __future__ import annotations

from bad_research.calibrate.cost import CostMeter
from bad_research.calibrate.harness import BadRunOutput, BadRunner


def default_runner(config) -> BadRunner:
    """Return a runner that drives the bad-research pipeline for one query.

    `config=None` → default BadResearchConfig.
    """
    if config is None:
        try:
            from bad_research.config import BadResearchConfig

            config = BadResearchConfig()
        except Exception:
            config = None

    def _run(query: str) -> BadRunOutput:
        meter = CostMeter()
        # The production drive: Plan 08's agentic-fast / pipeline entrypoint.
        # Imported lazily so the calibration package is importable without the
        # full pipeline (and so unit tests never touch it).
        try:
            from bad_research.pipeline import run_query  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - exercised only live
            raise RuntimeError(
                "bad-research pipeline not available; run `bad calibrate` with a wired "
                "pipeline + provider keys, or use the offline stub path."
            ) from exc

        result = run_query(query, config=config, cost_meter=meter)  # pragma: no cover
        return BadRunOutput(                                         # pragma: no cover
            report=result.report,
            corpus=result.corpus,
            cost=meter,
        )

    return _run
```

- [ ] **12.4** Run — PASS:

```bash
python -m pytest tests/test_calibrate/test_runner_bridge.py -q -p no:cov
```

Expected: `1 passed, 1 skipped`.

- [ ] **12.5** Commit.

```bash
git add -A && git commit -m "feat(calibrate): config→BadRunner bridge (live-gated production drive) (tested)"
```

---

## Task 13 — `bad calibrate <query>` CLI command (RED → GREEN)

**Goal:** `bad calibrate <query>` runs the harness (real runner if keyed, offline stub otherwise) and writes `calibration-report.json` + `calibration-report.md` to the output dir. `--offline` forces the stub path so the command is testable end-to-end with no keys.

- [ ] **13.1** Write `tests/test_calibrate/test_calibrate_cmd.py`:

```python
"""`bad calibrate <query>` emits both report files; offline path needs no keys."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_calibrate_offline_emits_both_reports(tmp_path: Path):
    result = runner.invoke(
        app,
        ["calibrate", "Does X cause Y?", "--offline", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "calibration-report.json").exists()
    assert (tmp_path / "calibration-report.md").exists()

    data = json.loads((tmp_path / "calibration-report.json").read_text())
    assert data["query"] == "Does X cause Y?"
    assert "bad" in data and "verdict" in data["bad"]


def test_calibrate_json_stdout(tmp_path: Path):
    result = runner.invoke(
        app,
        ["calibrate", "q", "--offline", "--out", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert "verdict" in payload["data"]["bad"]
```

- [ ] **13.2** Run — FAIL (no `calibrate` command):

```bash
python -m pytest tests/test_calibrate/test_calibrate_cmd.py -q -p no:cov
```

- [ ] **13.3** Write `src/bad_research/cli/calibrate.py`:

```python
"""`bad calibrate <query>` — OFFLINE calibration harness (SPEC §14).

Runs a query through bad-research, judges it on the 5-axis rubric, compares to
available key-gated baselines, and writes calibration-report.{json,md}. This is
calibration, NOT a per-run gate.
"""
from __future__ import annotations

from pathlib import Path

import typer

from bad_research.cli._output import console, output
from bad_research.models.output import success


def calibrate(
    query: str = typer.Argument(..., help="The research query to calibrate on."),
    out: str = typer.Option(".", "--out", "-o", help="Output dir for the calibration report."),
    offline: bool = typer.Option(
        False, "--offline", help="Use a deterministic stub runner + stub judge (no keys, no network)."
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output."),
) -> None:
    """Score bad-research vs. baselines on QUERY (offline 5-axis judge)."""
    from bad_research.calibrate import (
        CostMeter,
        StubJudge,
        available_baselines,
        run_calibration,
    )
    from bad_research.calibrate.constants import JUDGE_AXES
    from bad_research.calibrate.harness import BadRunOutput

    out_dir = Path(out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if offline:
        # Deterministic, key-free path: a stub runner + stub judge.
        def _stub_runner(q: str) -> BadRunOutput:
            meter = CostMeter()
            meter.record(stage="synthesize", tier="heavy",
                         input_tokens=8000, output_tokens=4000,
                         citation_tokens=200, search_queries=15)
            return BadRunOutput(
                report=f"# {q}\n\nA grounded claim [1].\n",
                corpus=[{"note_id": "n1", "url": "https://example.edu", "text": "evidence"}],
                cost=meter,
            )

        judge = StubJudge(scores={a: 0.85 for a in JUDGE_AXES})
        report = run_calibration(query, runner=_stub_runner, baselines=[], judge=judge)
    else:
        # Live path: real runner + LLM judge + key-gated baselines.
        from bad_research.calibrate.judge import LLMJudge
        from bad_research.calibrate.runner import default_runner

        try:
            from bad_research.llm.anthropic import AnthropicProvider  # type: ignore

            provider = AnthropicProvider()
        except Exception as exc:
            msg = f"calibrate needs an Anthropic provider (set ANTHROPIC_API_KEY) or use --offline: {exc}"
            if json_output:
                from bad_research.models.output import error

                output(error(msg, "NO_PROVIDER"), json_mode=True)
            else:
                console.print(f"[red]Error:[/] {msg}")
            raise typer.Exit(1)

        report = run_calibration(
            query,
            runner=default_runner(config=None),
            baselines=available_baselines(),
            judge=LLMJudge(provider=provider),
        )

    json_path = out_dir / "calibration-report.json"
    md_path = out_dir / "calibration-report.md"
    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    if json_output:
        output(success(report.to_dict(), vault=str(out_dir)), json_mode=True)
        return

    v = report.bad.verdict
    console.print(f"[bold]Calibration:[/] {query}")
    console.print(f"  bad-research overall: [bold]{v.overall:.3f}[/] "
                  f"({'[green]PASS[/]' if v.passed else '[red]FAIL[/]'})  "
                  f"cost ${report.bad.cost_usd:.4f}")
    for b in report.baselines:
        console.print(f"  {b.name}: {b.verdict.overall:.3f}  (Δ {report.delta_vs(b.name):+.3f})")
    console.print(f"\n[green]Wrote[/] {json_path}\n[green]Wrote[/] {md_path}")
```

- [ ] **13.4** Register `calibrate` in `bad_research/cli/__init__.py`:

```python
# in bad_research/cli/__init__.py, alongside the doctor registration:
from bad_research.cli.calibrate import calibrate as _calibrate
app.command("calibrate")(_calibrate)
```

- [ ] **13.5** Run — PASS, plus a real CLI smoke:

```bash
python -m pytest tests/test_calibrate/test_calibrate_cmd.py -q -p no:cov
bad calibrate "Does caffeine improve focus?" --offline --out /tmp/badcal
cat /tmp/badcal/calibration-report.md
```

Expected: `2 passed`; the smoke run prints `Wrote /tmp/badcal/calibration-report.json` + `.md`, and the markdown shows the 5 axes + cost + the "no external baselines" note.

- [ ] **13.6** Commit.

```bash
git add -A && git commit -m "feat(cli): bad calibrate <query> — offline 5-axis calibration harness (tested)"
```

---

## Task 14 — Full-suite green + coverage floor (verification gate)

**Goal:** The aggregate `pytest` run (every per-plan suite + this plan's) passes with the 80% coverage floor and `--strict-markers`. This is the verification-before-completion gate.

- [ ] **14.1** Run the whole suite with the configured addopts (coverage floor active):

```bash
python -m pytest
```

Expected: all tests pass; `live` tests skipped; final line shows `Required test coverage of 80% reached` (or higher). If coverage is below 80% **because earlier plans aren't landed yet**, scope the floor to this plan's package during isolated development:

```bash
python -m pytest tests/test_packaging tests/test_providers.py tests/test_calibrate \
  --cov=bad_research.calibrate --cov=bad_research.providers --cov=bad_research.cli.doctor \
  --cov=bad_research.cli.calibrate --cov-fail-under=80
```

Expected: `Required test coverage of 80% reached.`

- [ ] **14.2** Confirm marker hygiene — no unregistered markers anywhere:

```bash
python -m pytest --strict-markers --co -q | tail -5
```

Expected: collection completes with no `PytestUnknownMarkWarning`.

- [ ] **14.3** Confirm the live tests really do skip without keys, and run when keyed (optional, only if a key is available):

```bash
python -m pytest -m live -q -p no:cov        # → all skipped
# BAD_RUN_LIVE=1 ANTHROPIC_API_KEY=... python -m pytest -m live -q -p no:cov   # → run
```

Expected: `N skipped` with no key.

- [ ] **14.4** Lint + types on this plan's modules:

```bash
ruff check src/bad_research/providers.py src/bad_research/calibrate src/bad_research/cli/doctor.py src/bad_research/cli/calibrate.py
mypy src/bad_research/calibrate src/bad_research/providers.py
```

Expected: clean (or only pre-existing issues from other plans).

- [ ] **14.5** Commit.

```bash
git add -A && git commit -m "test(bad-research): full-suite green + 80% coverage floor + marker hygiene (Plan 09 verification gate)"
```

---

## Task 15 — Build artifact sanity (sdist/wheel + console scripts)

**Goal:** The package actually builds and the entry points land in the wheel — the ultimate "does it ship" check.

- [ ] **15.1** Build:

```bash
python -m pip install build >/dev/null 2>&1; python -m build
ls dist/
```

Expected: `dist/bad_research-0.1.0-py3-none-any.whl` and `dist/bad-research-0.1.0.tar.gz`.

- [ ] **15.2** Inspect the wheel's entry points:

```bash
python - <<'PY'
import zipfile, glob
whl = sorted(glob.glob("dist/bad_research-*.whl"))[-1]
with zipfile.ZipFile(whl) as z:
    name = [n for n in z.namelist() if n.endswith("entry_points.txt")][0]
    print(z.read(name).decode())
PY
```

Expected output contains:

```
[console_scripts]
bad = bad_research.cli:app
badr = bad_research.cli:app
```

- [ ] **15.3** Fresh-venv install of the built wheel + smoke (proves no editable-mode magic):

```bash
python -m venv /tmp/bad-venv && /tmp/bad-venv/bin/pip install dist/bad_research-*.whl >/dev/null
/tmp/bad-venv/bin/bad --version && /tmp/bad-venv/bin/bad doctor --json | python -c "import sys,json; print('providers:', len(json.load(sys.stdin)['data']['providers']))"
```

Expected: `bad-research v0.1.0` then `providers: 11`.

- [ ] **15.4** Commit any packaging fix discovered; otherwise note the artifacts are not checked in (build output is gitignored).

```bash
git add -A && git commit -m "chore(packaging): verified sdist/wheel build + entry points + fresh-venv smoke" --allow-empty
```

---

## Notes for the executor

- **TDD discipline:** every implementation task starts with a failing test you actually run and watch fail. The FAIL output is the evidence the test bites. Do not write impl before the red.
- **`-p no:cov` on slices:** the 80% floor is configured in `addopts`, so a *partial* run would falsely fail it. Use `-p no:cov` when running a single file mid-task; the floor is enforced only in the full-suite gate (Task 14).
- **Offline is the contract:** the entire calibration harness must run with zero keys and zero network via `--offline` + `StubJudge` + the stub runner. The `live` path (real judge, real pipeline, key-gated baselines) is exercised only when `BAD_RUN_LIVE=1` and keys are set. Never let calibration become a per-run gate (SPEC §10).
- **Idempotency is Plan 08's contract, Plan 09's test:** if `test_install_idempotent.py` fails against Plan 08's real installer, that is a Plan 08 bug to fix there — do not weaken the test.
- **Heavy deps stay out of base:** if any later plan needs `torch`/`playwright`/`cohere` at import time in a *base* module, that's a layering bug — gate the import behind the extra (lazy `import` inside the function), as `providers.py` and `runner.py` do.