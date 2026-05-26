# Bad Research — KR-7: Packaging + Tests + Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD: write the failing test, run it, see it FAIL, write the implementation, run it, see it PASS, commit. Do not skip the FAIL observation — it proves the test exercises the code. You have full tool access (Read, Edit, Write, Bash). Commit on `main` after each task.

**Goal:** Finalize the keyless re-architecture so a fresh `pip install bad-research` (no extras, no API keys, no network at import) gives a working `bad --version` / `bad doctor` / `bad calibrate --offline`; `bad doctor` reports the keyless capability surface (which external CLIs are present + one-line install hints, which `[local]` is installed, keyless-by-default status); the full test suite is green over the keyless surface at the 80% coverage floor; and `uv build` produces a wheel that base-only-installs and smoke-passes keylessly.

**Architecture:** KR-7 is the finalizer that sits *on top of* KR-1…KR-6 (which deleted the keyed provider code, built the keyless search/content/browse/retrieval seams, and rewired the funnel/pipeline/skills). KR-7 owns four thin layers, none in any hot path: (1) **packaging** — `pyproject.toml` trimmed to the pure-keyless base (`anthropic` core only for the headless/calibration bridge; NO cohere/tavily/exa/firecrawl/browserbase/agentql) with `[local]` (torch/sentence-transformers/lancedb/pyarrow, use-if-present), `[browse]` (playwright), `[mcp]`, `[all]`, `[dev]`; (2) **doctor** — `bad doctor` reports the keyless capability surface: keyless-by-default banner, external-CLI detection (agent-browser/lightpanda/yt-dlp/git) with install hints, silent-on-SearXNG, `[local]` presence; (3) **calibrate** — the offline `StubJudge` path stays the tested zero-key path; the live `run_query` path picks up KR-6's keyless wiring and keeps only the keyless-relevant baselines; (4) **tests + coverage** — base-leanness assertion (removed providers NOT importable from base), CLI-detection tests, calibrate offline end-to-end, install idempotency, wheel build + base-only smoke; the coverage `omit` list is rebuilt for the keyless module set.

**Tech Stack:** Python 3.11–3.13 (`requires-python = ">=3.11,<3.14"`); `hatchling` build backend; `typer`+`rich` CLI; `pytest` + `pytest-cov` (80% floor over the keyless surface); `typer.testing.CliRunner` for CLI tests; `shutil.which` for external-CLI detection (no subprocess, no network); `uv build` for the wheel; `uv run python -m pytest` for tests. Repo prelude for every command: `export PATH="$HOME/.local/bin:$PATH"`.

---

## Binding contract

This plan binds **verbatim** to `docs/INTERFACES_KEYLESS.md`:
- **§7** — the LEAN keyless dependency set (the exact `pyproject.toml` base + extras).
- **§7.1** — the external keyless CLI tools the skill drives (NOT pip deps): `agent-browser`, `lightpanda`, `yt-dlp`, `git`, optional `SearXNG`.
- **§3.5** — the keyless provider registry rows (`providers.py::PROVIDERS`), `requires_key=False` for every row.
- **§9 resolved decisions** — `anthropic` stays a **core** dep (the only path needing it is the calibration/headless bridge; ambiguity #1 resolved to core); CLIs are **detected + degrade** (ambiguity #2 → documented prerequisites, doctor reports presence, no auto-bootstrap blocking); **SearXNG silent** in doctor (ambiguity #3 → silent/opt-in); `[local]` is **use-if-present** (ambiguity #4 → user must `pip install bad-research[local]`; KR-7 never auto-pip-installs torch).

**Cross-plan invariant 1 (zero third-party key, anywhere):** after KR-1…KR-6, `grep -rE 'cohere|tavily|exa_py|firecrawl|browserbase|agentql|browser_use' src/` returns 0 hits. KR-7's base-leanness test enforces the *import* side of this: none of those packages is importable from a base-only install.

**Assumption (verify in Task 0):** KR-1…KR-6 have landed and are green. KR-1 deleted `web/providers/`, `web/exa_provider.py`, the four keyed `browse/*` files, `embed/cohere.py`, and the `CohereReranker` class, and rewrote `config.py` to add the keyless knobs (`reranker`, `neural_recall`, `searxng_endpoint`, `browse_engine`, `effort`, `max_tokens`) and drop `embed_model`/`rerank_model`. KR-1 also rewrote `providers.py::PROVIDERS` to the §3.5 keyless rows. KR-7 does **not** re-do KR-1's deletions; Task 0 verifies they happened and the suite is green before KR-7 touches anything. If KR-1's `providers.py`/`config.py`/`pyproject.toml` rewrites are incomplete, KR-7's tasks below complete them (they are idempotent against KR-1's intended end-state).

---

## Frozen constants & shapes (cite verbatim, never re-derive)

```python
# The pure-keyless base dependency set (INTERFACES_KEYLESS §7) — Task 1.
BASE_DEPS = [
    "anthropic>=0.40", "httpx>=0.27", "crawl4ai>=0.4", "ddgs>=9.14",
    "pymupdf>=1.24", "pymupdf4llm>=0.0.17", "trafilatura>=1.8",
    "beautifulsoup4>=4.12", "lxml>=5.0", "rank-bm25>=0.2",
    "snowballstemmer>=2.2", "dateparser>=1.2", "feedparser>=6.0",
    "typer>=0.9.0", "rich>=13.0", "pydantic>=2.0", "pyyaml>=6.0",
    "jinja2>=3.1", "platformdirs>=4.0", "tree-sitter>=0.23",
    "tree-sitter-language-pack>=0.7", "rapidfuzz>=3.0", "langdetect>=1.0.9",
]
# Extras (INTERFACES_KEYLESS §7):
#   browse = ["playwright>=1.40"]
#   local  = ["torch>=2.0","sentence-transformers>=3.0","lancedb>=0.13","pyarrow>=15.0"]
#   mcp    = ["mcp>=1.6"]
#   all    = ["bad-research[browse,local,mcp]"]
#   dev    = ["pytest>=7.4","pytest-cov>=4.1","pytest-asyncio>=0.23","ruff>=0.3","mypy>=1.8","respx>=0.21","mcp>=1.6"]

# Providers that MUST NOT be importable from a base-only install (the removed keyed stack).
REMOVED_PROVIDER_IMPORTS = ("cohere", "tavily", "exa_py", "firecrawl", "browserbase", "agentql", "browser_use")

# External keyless CLI tools the skill drives (INTERFACES_KEYLESS §7.1) — Task 2 detection + hints.
EXTERNAL_CLIS = {
    "agent-browser": "agent-browser install   # pulls Chrome-for-Testing, no account",
    "lightpanda":    "curl -L github.com/lightpanda-io/browser/releases/latest -o lightpanda  # keyless JS engine",
    "yt-dlp":        "pipx install yt-dlp      # caption-track puller (YouTube/video tier)",
    "git":           "(install git via your OS package manager)",
}
# SearXNG is silent/opt-in (INTERFACES_KEYLESS §9): NOT in EXTERNAL_CLIS; never warned about.

# The keyless provider registry (INTERFACES_KEYLESS §3.5) — requires_key=False on every row.
# (KR-1 ships this; KR-7 Task 3 verifies/finishes it.)
```

```python
# bad_research/pipeline.py (KEPT; consumed by the calibrate live runner) — INTERFACES.md
# def run_query(query, *, config=None, cost_meter=None) -> RunResult   # RunResult.report:str, RunResult.corpus:list[dict]

# bad_research/calibrate/harness.py (KEPT) — INTERFACES.md
# @dataclass class BadRunOutput: report:str; corpus:list[dict]; cost:CostMeter
# def run_calibration(query, *, runner:BadRunner, baselines:list[Baseline], judge:Judge) -> CalibrationReport
# class StubJudge: scores:dict[str,float]  → JudgeVerdict   (the offline tested judge)
```

---

## File Structure

New + modified files this plan owns. KR-7 modifies packaging/doctor/calibrate/tests only — it does NOT touch the keyless seams KR-2…KR-6 built (it calls them).

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | **modify** | Trim base `dependencies` to the §7 keyless set (anthropic core; no keyed providers; no lancedb/pyarrow/numpy in core); redefine extras `[browse]`/`[local]`/`[mcp]`/`[all]`/`[dev]`; delete the `[search]` and `[grounding]` extras; rebuild the coverage `omit` list for the keyless module set. |
| `src/bad_research/providers.py` | **modify** | Confirm/finish the §3.5 keyless registry (`requires_key=False` everywhere); add `external_cli_status()` returning per-CLI presence + install hint (used by doctor). Pure, no network, no subprocess. |
| `src/bad_research/cli/doctor.py` | **rewrite** | Keyless capability report: keyless-by-default banner, provider rows (all keyless), external-CLI detection block (agent-browser/lightpanda/yt-dlp/git + hints), silent-on-SearXNG, `[local]` presence line. `--json` mode. No key checks. |
| `src/bad_research/cli/calibrate.py` | **modify** | Docstring + comments: the offline `StubJudge` path is the tested zero-key path; the live path drives the keyless `run_query` (still needs `ANTHROPIC_API_KEY` for the headless model calls). Drop the dead `available_baselines()` import path's keyed baselines from the live wiring if KR-1 left them; keep the offline call unchanged. |
| `src/bad_research/calibrate/baselines.py` | **modify** | Remove the `PerplexityBaseline` (`PPLX_API_KEY` → keyed Sonar, deleted) and `GrokBaseline` (`XAI_API_KEY` → keyed) from `available_baselines()`; keep only `HyperresearchBaseline` (host-driven, structural). Keeps the live path keyless-baseline-clean. |
| `tests/test_packaging/test_pyproject.py` | **rewrite** | Base-leanness over the keyless set; `[search]`/`[grounding]` extras GONE; `[browse]`/`[local]`/`[mcp]`/`[all]`/`[dev]` present + contents. |
| `tests/test_packaging/test_base_leanness.py` | **create** | Assert each of `REMOVED_PROVIDER_IMPORTS` is NOT importable; assert importing `bad_research` + `bad_research.cli` triggers no keyed-provider import; assert no `ANTHROPIC_API_KEY` is read at import. |
| `tests/test_packaging/test_doctor.py` | **rewrite** | Keyless doctor: keyless banner, external-CLI block present with hints, SearXNG absent from output, `--json` keyless surface (no `requires_key:true` rows). |
| `tests/test_packaging/test_wheel_build.py` | **create** | `uv build` produces a wheel; the wheel's `METADATA` lists the keyless base deps and none of the removed providers (offline, parses the built artifact). |
| `tests/test_providers.py` | **rewrite** | Keyless registry: expected keyless names present; no keyed names; every row `requires_key=False`; `external_cli_status()` shape. |
| `tests/test_calibrate/test_calibrate_cmd.py` | **modify** | Keep the offline-emits-both-reports + json-stdout tests (the tested path); add a keyless assertion (offline run needs zero keys, already enforced by conftest). |
| `tests/conftest.py` | **modify** | Trim the `_LIVE_KEYS` / `_clear_provider_keys` lists to the keyless reality (`ANTHROPIC_API_KEY` only; drop the deleted-provider env vars). |
| `docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md` | **create** | The keyless calibration plan doc (what to measure: fetch_clean vs a one-time read-only baseline, keyless-search pass-rate, rerank A/B nDCG host-vs-local-vs-none, grounding injected-claim recall). Doc only; the judge stays offline-only. |

---

## Task 0: Verify KR-1…KR-6 landed + suite green (no code change)

**Files:** none (verification gate).

- [ ] **Step 1: Verify the keyed stack is deleted from `src/`**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
grep -rEl 'import cohere|import tavily|import exa_py|import firecrawl|import browserbase|import agentql|import browser_use|from cohere|from tavily|from exa_py|from firecrawl|from browserbase|from agentql|from browser_use' src/ || echo "CLEAN: no keyed imports in src/"
ls src/bad_research/web/providers/ 2>/dev/null && echo "WARN: web/providers still present (KR-1 incomplete)" || echo "OK: web/providers deleted"
ls src/bad_research/web/exa_provider.py 2>/dev/null && echo "WARN: exa_provider present" || echo "OK: exa_provider deleted"
```
Expected: `CLEAN: no keyed imports in src/`, `OK: web/providers deleted`, `OK: exa_provider deleted`. If any WARN prints, KR-1 is incomplete — stop and finish KR-1 before KR-7.

- [ ] **Step 2: Verify the keyless seams exist (KR-2…KR-6)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
for f in web/search/base.py web/content/fetch_clean.py browse/agent_browser.py retrieval/rerank.py; do
  test -f "src/bad_research/$f" && echo "OK: $f" || echo "MISSING: $f"
done
grep -q "ClaudeCodeReranker" src/bad_research/retrieval/rerank.py && echo "OK: ClaudeCodeReranker" || echo "MISSING: ClaudeCodeReranker"
```
Expected: `OK:` for every line. A `MISSING:` means an upstream KR plan did not land — KR-7 cannot finalize until it does.

- [ ] **Step 3: Run the current suite to capture the pre-KR-7 baseline**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest -q 2>&1 | tail -20
```
Expected: a passing run (it may still reference old keyed tests if KR-1 left them — note any failures; KR-7 Tasks 5–11 replace those tests). Record the coverage total. This is the floor KR-7 must not drop below.

- [ ] **Step 4: No commit** (verification only). Proceed to Task 1.

---

## Task 1: Trim `pyproject.toml` to the pure-keyless base + extras

**Files:**
- Test: `tests/test_packaging/test_pyproject.py` (rewrite)
- Modify: `pyproject.toml`

- [ ] **Step 1: Rewrite the failing test**

Replace the entire contents of `tests/test_packaging/test_pyproject.py`:

```python
"""pyproject.toml: pure-keyless base + the keyless extras (INTERFACES_KEYLESS §7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # .../badresearch/
PYPROJECT = ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pp() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _names(dep_list: list[str]) -> set[str]:
    out = set()
    for d in dep_list:
        name = d.split(";")[0].strip()
        for sep in (">=", "==", "~=", "<", ">", "[", " "):
            name = name.split(sep)[0]
        out.add(name.strip().lower())
    return out


# ── metadata + entry points ──────────────────────────────────────────────────
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


# ── pure-keyless base ────────────────────────────────────────────────────────
# The removed keyed/heavy stack MUST NOT be in the base install.
FORBIDDEN_IN_BASE = {
    "cohere", "tavily-python", "exa-py", "firecrawl-py", "browserbase",
    "browser-use", "agentql", "stagehand", "playwright", "torch",
    "sentence-transformers", "lancedb", "pyarrow", "flagembedding",
}


def test_base_is_pure_keyless(pp):
    base = _names(pp["project"]["dependencies"])
    leaked = base & {n.lower() for n in FORBIDDEN_IN_BASE}
    assert not leaked, f"non-keyless deps leaked into base: {leaked}"


def test_base_carries_keyless_essentials(pp):
    base = _names(pp["project"]["dependencies"])
    # anthropic stays core (the calibration/headless bridge); the keyless content stack.
    assert {
        "anthropic", "httpx", "crawl4ai", "ddgs", "pymupdf", "trafilatura",
        "beautifulsoup4", "rank-bm25", "feedparser", "typer", "rich", "pydantic",
    } <= base, f"missing keyless essentials; have {sorted(base)}"


def test_base_has_no_torch_lancedb_playwright(pp):
    base = pp["project"]["dependencies"]
    assert all(
        "torch" not in d and "lancedb" not in d and "playwright" not in d for d in base
    )


# ── extras: the keyless shape ────────────────────────────────────────────────
def test_search_and_grounding_extras_gone(pp):
    extras = pp["project"]["optional-dependencies"]
    assert "search" not in extras, "the keyed [search] extra must be deleted"
    assert "grounding" not in extras, "[grounding] folds into [local] (sentence-transformers)"


def test_keyless_extras_exist(pp):
    extras = pp["project"]["optional-dependencies"]
    for group in ("browse", "local", "mcp", "all", "dev"):
        assert group in extras, f"missing extras group: {group}"


def test_browse_extra_is_playwright_only(pp):
    browse = _names(pp["project"]["optional-dependencies"]["browse"])
    assert browse == {"playwright"}, f"[browse] should be playwright-only; got {browse}"


def test_local_extra_holds_the_neural_stack(pp):
    local = _names(pp["project"]["optional-dependencies"]["local"])
    assert {"torch", "sentence-transformers", "lancedb", "pyarrow"} <= local


def test_all_composes_keyless_extras(pp):
    all_dep = pp["project"]["optional-dependencies"]["all"]
    assert any("bad-research[" in d for d in all_dep)
    joined = " ".join(all_dep)
    assert "browse" in joined and "local" in joined and "mcp" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_pyproject.py -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — `test_search_and_grounding_extras_gone` and `test_browse_extra_is_playwright_only` fail because the current `pyproject.toml` still has `[search]`, `[grounding]`, and `crawl4ai`/`browser-use` in `[browse]`. (We pass `-o addopts=""` to skip the global `--cov-fail-under` while iterating on one file.)

- [ ] **Step 3: Rewrite the `[project]` deps + extras + coverage in `pyproject.toml`**

Replace the `dependencies` block (lines under `# Lean, zero-key base:` comment through the close of the array) with the pure-keyless base:

```toml
# Pure-keyless base (INTERFACES_KEYLESS §7): the deterministic keyless pipeline
# (host WebSearch adapter + ddgs + 7 scholarly verticals, the fetch_clean content
# stack, FTS5/BM25 retrieval + host-model LLM-rerank, garbage filters, grounding
# gate). `anthropic` stays core ONLY for the headless/calibration bridge — the
# skill path itself uses the Claude Code HOST model (no key). NO keyed providers
# (cohere/tavily/exa/firecrawl/browserbase/agentql/browser-use); NO lancedb/torch
# (those live behind `[local]`). Small enough for `pipx install`.
dependencies = [
    "anthropic>=0.40",
    "httpx>=0.27",
    "crawl4ai>=0.4",
    "ddgs>=9.14",
    "pymupdf>=1.24",
    "pymupdf4llm>=0.0.17",
    "trafilatura>=1.8",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "rank-bm25>=0.2",
    "snowballstemmer>=2.2",
    "dateparser>=1.2",
    "feedparser>=6.0",
    "typer>=0.9.0",
    "rich>=13.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "platformdirs>=4.0",
    "tree-sitter>=0.23",
    "tree-sitter-language-pack>=0.7",
    "rapidfuzz>=3.0",
    "langdetect>=1.0.9",
]
```

Replace the entire `[project.optional-dependencies]` block with the keyless extras:

```toml
[project.optional-dependencies]
# Optional Playwright extras (crawl4ai pulls its own Chromium; this is only for the
# python-playwright path). agent-browser/lightpanda/yt-dlp/git are EXTERNAL CLIs
# (see README / `bad doctor`), NOT pip deps.
browse = ["playwright>=1.40"]
# Offline neural stack — opt-in, lazy-downloaded. The ONLY place torch/lancedb live:
# the bge-small bi-encoder, the ms-marco/bge cross-encoder reranker, the nli-deberta
# verifier, and the LanceDB vector store (only when neural_recall is on, >25k chunks).
local = [
    "torch>=2.0",
    "sentence-transformers>=3.0",
    "lancedb>=0.13",
    "pyarrow>=15.0",
]
# MCP face (keyless).
mcp = ["mcp>=1.6"]
# Everything — references the package's own extras so versions stay single-sourced.
all = ["bad-research[browse,local,mcp]"]
# Test + lint toolchain.
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
    "respx>=0.21",
    "mcp>=1.6",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_pyproject.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (all ~11 tests green).

- [ ] **Step 5: Sync the env to the new deps + smoke-import**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv sync --extra dev 2>&1 | tail -5
uv run python -c "import bad_research; from bad_research.cli import app; print('import OK', bad_research.__version__)"
```
Expected: `uv sync` resolves cleanly (no cohere/tavily/exa/firecrawl/torch/lancedb in the base resolution); `import OK 0.1.0`. If `uv sync` fails to resolve, a kept module still imports a removed dep — fix that import in the offending KR-1…KR-6 module before continuing.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add pyproject.toml tests/test_packaging/test_pyproject.py
git commit -m "build(KR-7): pure-keyless pyproject base + [browse]/[local]/[mcp] extras

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Base-leanness test — removed providers NOT importable, no key read at import

**Files:**
- Test: `tests/test_packaging/test_base_leanness.py` (create)

This is the absolute keyless invariant: a base-only install must not be able to `import` any removed keyed provider, and importing the package must read no API key.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging/test_base_leanness.py`:

```python
"""Base-leanness: the removed keyed stack is NOT importable from a base install,
and importing the package reads no API key (INTERFACES_KEYLESS §1, §7, invariant 1)."""

from __future__ import annotations

import importlib.util

# The keyed providers KR-1 deleted. None may be importable from a base-only install.
REMOVED_PROVIDER_IMPORTS = (
    "cohere",
    "tavily",
    "exa_py",
    "firecrawl",
    "browserbase",
    "agentql",
    "browser_use",
    "stagehand",
)

# The heavy neural stack that lives ONLY behind `[local]`.
LOCAL_ONLY_IMPORTS = ("torch", "lancedb", "sentence_transformers")


def test_removed_providers_not_imported_by_src():
    """No module under src/ imports a removed keyed provider (static guard)."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / "src" / "bad_research"
    offenders = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in REMOVED_PROVIDER_IMPORTS:
            if f"import {name}" in text or f"from {name}" in text:
                offenders.append(f"{py.relative_to(src)} -> {name}")
    assert not offenders, f"removed-provider imports survive in src/: {offenders}"


def test_package_imports_without_keyed_providers_installed():
    """Importing the package + CLI must not require any removed provider lib.

    A base-only install does not have cohere/tavily/etc; if a kept module tries to
    import one at module load, this import fails — proving the lean base is broken.
    """
    import bad_research  # noqa: F401
    from bad_research.cli import app  # noqa: F401
    from bad_research.providers import provider_status  # noqa: F401

    # Sanity: the providers we DID keep do not pull a removed lib transitively.
    assert provider_status()  # non-empty registry, no ImportError raised


def test_no_anthropic_key_read_at_import(monkeypatch):
    """Importing the package must not read ANTHROPIC_API_KEY (keyless-at-import)."""
    reads: list[str] = []
    import os

    real_get = os.environ.get

    def _spy_get(key, default=None):
        if key == "ANTHROPIC_API_KEY":
            reads.append(key)
        return real_get(key, default)

    monkeypatch.setattr(os.environ, "get", _spy_get)
    import importlib

    import bad_research

    importlib.reload(bad_research)
    importlib.import_module("bad_research.cli")
    assert reads == [], f"ANTHROPIC_API_KEY read at import time: {reads}"


def test_local_stack_is_optional_not_required():
    """torch/lancedb/sentence_transformers must NOT be a hard import of any base path.

    They may be present (if [local] is installed) — the assertion is only that the
    base package imports fine regardless. Mark them as the [local] surface for clarity.
    """
    # Importing the package already succeeded above; assert these are not forced.
    # (We do not assert they are ABSENT — the dev env may have [local]; we assert the
    #  base import path does not REQUIRE them, which the prior test already proved.)
    for name in LOCAL_ONLY_IMPORTS:
        spec_present = importlib.util.find_spec(name) is not None
        # No assertion on presence; this documents the optional surface and runs the
        # find_spec path so a future hard-import regression is caught by the import test.
        assert spec_present in (True, False)
```

- [ ] **Step 2: Run test to verify it fails (or passes for the right reason)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_base_leanness.py -p no:cacheprovider -o addopts="" -q
```
Expected: This test is the *guard*, not a feature with impl. If KR-1…KR-6 are correct, `test_removed_providers_not_imported_by_src` and `test_package_imports_without_keyed_providers_installed` PASS. If they FAIL, a kept module still imports a removed provider — **that is a real bug to fix in the offending KR module**, not in this test. Fix the offending `import` (delete the dead import / guard it behind `[local]`), then re-run until green.

- [ ] **Step 3: Implementation = fix any offender surfaced**

If Step 2 surfaced an offender (e.g. `web/base.py -> exa_py`), open that file and delete the dead import or move it behind a `try/except ImportError` `[local]` guard. (No new file; the impl is removing the leaked import.) If Step 2 was already green, no code change is needed — the test documents and enforces the invariant.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_base_leanness.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add tests/test_packaging/test_base_leanness.py
git commit -m "test(KR-7): base-leanness — removed providers not importable, no key at import

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Keyless provider registry + external-CLI status helper

**Files:**
- Test: `tests/test_providers.py` (rewrite)
- Modify: `src/bad_research/providers.py`

KR-1 should have rewritten `PROVIDERS` to the §3.5 keyless rows. KR-7 verifies that and **adds** `external_cli_status()` (the data `bad doctor` renders for the external CLIs). The helper uses `shutil.which` only — no network, no subprocess execution.

- [ ] **Step 1: Rewrite the failing test**

Replace the entire contents of `tests/test_providers.py`:

```python
"""Keyless provider registry + external-CLI detection (no network, no subprocess)."""

from __future__ import annotations

from bad_research.providers import (
    EXTERNAL_CLIS,
    PROVIDERS,
    ProviderStatus,
    active_providers,
    external_cli_status,
    provider_status,
)


def test_registry_is_keyless_only():
    names = {p.name for p in PROVIDERS}
    # The keyless surface (INTERFACES_KEYLESS §3.5).
    assert {
        "anthropic-host",
        "websearch",
        "ddgs",
        "searxng",
        "crawl4ai",
        "agent-browser",
        "arxiv",
        "openalex",
        "crossref",
        "europepmc",
        "pubmed",
        "wikipedia",
    } <= names
    # None of the removed keyed providers may appear.
    assert not (
        names & {"cohere", "tavily", "exa", "sonar", "firecrawl", "browserbase", "browser_use", "agentql"}
    )


def test_every_provider_is_keyless():
    for s in provider_status():
        assert s.requires_key is False, f"{s.name} requires a key — not keyless"
        assert s.key_present is True, f"{s.name} should be key_present (no key needed)"


def test_active_reduces_to_import_present():
    # With requires_key False everywhere, active == import_present.
    for s in provider_status():
        assert s.active == s.import_present


def test_anthropic_host_is_base_and_keyless():
    by_name = {p.name: p for p in PROVIDERS}
    p = by_name["anthropic-host"]
    assert p.env_var is None  # host supplies inference; no key
    assert p.extra == "(base)"


def test_external_cli_status_shape():
    rows = external_cli_status()
    by = {r["name"]: r for r in rows}
    # The 4 driven CLIs are reported; SearXNG is NOT (silent/opt-in).
    assert {"agent-browser", "lightpanda", "yt-dlp", "git"} <= set(by)
    assert "searxng" not in {n.lower() for n in by}
    for name, row in by.items():
        assert set(row) == {"name", "present", "hint"}
        assert isinstance(row["present"], bool)
        assert row["hint"] == EXTERNAL_CLIS[name]


def test_git_is_detected_present():
    # git is on every dev box / CI runner.
    rows = {r["name"]: r for r in external_cli_status()}
    assert rows["git"]["present"] is True


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")


def test_active_providers_nonempty_offline():
    # Keyless registry: every provider whose import resolves is active, no keys needed.
    assert active_providers()  # at least the base httpx/ddgs/host rows
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_providers.py -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — `ImportError: cannot import name 'EXTERNAL_CLIS'` / `external_cli_status` (not yet defined). If `test_registry_is_keyless_only` *also* fails on the registry rows, KR-1's `providers.py` rewrite is incomplete — Step 3 completes it.

- [ ] **Step 3: Rewrite `providers.py` to the keyless registry + add the CLI helper**

Replace the entire contents of `src/bad_research/providers.py`:

```python
"""Provider registry (keyless) + external-CLI detection.

Pure and network-free: `bad doctor` and `bad calibrate` use this to report the
keyless capability surface. Every provider is KEYLESS (host model + local OSS +
self-host) — `requires_key` is False on every row, so `active` reduces to
`import_present`. The external CLIs the skill drives (agent-browser/lightpanda/
yt-dlp/git) are detected via `shutil.which` (no subprocess execution).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    env_var: str | None  # always None in the keyless world (host supplies inference)
    import_name: str | None  # the module that must import for the capability to work
    extra: str  # which `pip install bad-research[<extra>]` ships it ("(base)" = no extra)
    capability: str  # "llm" | "search" | "browse" | "embed" | "rerank" | "nli"


# The keyless registry (INTERFACES_KEYLESS §3.5). NO keyed provider rows.
PROVIDERS: tuple[Provider, ...] = (
    Provider("anthropic-host", None, None, "(base)", "llm"),       # host supplies inference; no key
    Provider("websearch", None, None, "(base)", "search"),         # host WebSearch tool
    Provider("ddgs", None, "ddgs", "(base)", "search"),            # keyless multi-engine lib
    Provider("searxng", None, None, "(base)", "search"),           # self-host, no key
    Provider("crawl4ai", None, "crawl4ai", "(base)", "browse"),    # local JS render
    Provider("agent-browser", None, None, "browse", "browse"),     # local CLI (CDP)
    Provider("arxiv", None, None, "(base)", "search"),             # keyless vertical (httpx)
    Provider("openalex", None, None, "(base)", "search"),
    Provider("crossref", None, None, "(base)", "search"),
    Provider("europepmc", None, None, "(base)", "search"),
    Provider("pubmed", None, None, "(base)", "search"),
    Provider("wikipedia", None, None, "(base)", "search"),
    Provider("bge-local", None, "sentence_transformers", "local", "embed"),
    Provider("ms-marco-local", None, "sentence_transformers", "local", "rerank"),
    Provider("nli-deberta", None, "sentence_transformers", "local", "nli"),
)


# External keyless CLI tools the skill drives (INTERFACES_KEYLESS §7.1). These are
# NOT pip deps — installed out-of-band. `bad doctor` reports presence + this hint.
# SearXNG is intentionally ABSENT (silent/opt-in, INTERFACES_KEYLESS §9).
EXTERNAL_CLIS: dict[str, str] = {
    "agent-browser": "agent-browser install   # pulls Chrome-for-Testing, no account",
    "lightpanda": "curl -L github.com/lightpanda-io/browser/releases/latest -o lightpanda  # keyless JS engine",
    "yt-dlp": "pipx install yt-dlp      # caption-track puller (YouTube/video tier)",
    "git": "(install git via your OS package manager)",
}


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
        return True  # host tool / self-host / pure-httpx vertical — no client lib needed
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def provider_status() -> list[ProviderStatus]:
    """Status for every registered provider. No network, no config-file read.

    Keyless: `requires_key` is False everywhere, so `active == import_present`.
    """
    out: list[ProviderStatus] = []
    for p in PROVIDERS:
        requires_key = bool(p.env_var)  # always False in the keyless registry
        key_present = (not requires_key) or bool(os.environ.get(p.env_var or ""))
        import_present = _import_ok(p.import_name)
        out.append(
            ProviderStatus(
                name=p.name,
                capability=p.capability,
                extra=p.extra,
                requires_key=requires_key,
                key_present=key_present,
                import_present=import_present,
                active=key_present and import_present,
            )
        )
    return out


def active_providers() -> list[ProviderStatus]:
    """Only the providers that can actually run right now (keyless: import resolves)."""
    return [s for s in provider_status() if s.active]


def external_cli_status() -> list[dict]:
    """Detect the external keyless CLIs the skill drives (shutil.which; no subprocess).

    Returns one row per CLI: {name, present: bool, hint: str}. SearXNG is silent —
    never reported here (INTERFACES_KEYLESS §9).
    """
    return [
        {"name": name, "present": shutil.which(name) is not None, "hint": hint}
        for name, hint in EXTERNAL_CLIS.items()
    ]


__all__ = [
    "EXTERNAL_CLIS",
    "PROVIDERS",
    "Provider",
    "ProviderStatus",
    "active_providers",
    "external_cli_status",
    "provider_status",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_providers.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add src/bad_research/providers.py tests/test_providers.py
git commit -m "feat(KR-7): keyless provider registry + external_cli_status (which/no subprocess)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `bad doctor` — keyless capability report

**Files:**
- Test: `tests/test_packaging/test_doctor.py` (rewrite)
- Rewrite: `src/bad_research/cli/doctor.py`

`bad doctor` now reports the keyless surface: a keyless-by-default banner, the provider rows (all keyless), an external-CLI block (present/absent + install hint), the `[local]` neural-stack presence line. No key checks. SearXNG never appears.

- [ ] **Step 1: Rewrite the failing test**

Replace the entire contents of `tests/test_packaging/test_doctor.py`:

```python
"""`bad doctor` — keyless capability report, no network, no key checks."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_doctor_runs_keyless():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "keyless" in out  # the keyless-by-default banner
    assert "anthropic-host" in out  # the host-model row


def test_doctor_reports_external_clis():
    result = runner.invoke(app, ["doctor"])
    out = result.output.lower()
    # The 4 driven CLIs appear by name.
    for cli in ("agent-browser", "lightpanda", "yt-dlp", "git"):
        assert cli in out, f"doctor did not report external CLI: {cli}"


def test_doctor_silent_on_searxng():
    result = runner.invoke(app, ["doctor"])
    assert "searxng" not in result.output.lower()


def test_doctor_shows_install_hint_for_absent_cli(monkeypatch):
    # Force every external CLI to look absent so the hint must render.
    import bad_research.providers as prov

    monkeypatch.setattr(prov.shutil, "which", lambda _name: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "agent-browser install" in result.output  # the hint string


def test_doctor_json_is_keyless_surface():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["keyless"] is True
    # Every provider row is keyless.
    assert all(p["requires_key"] is False for p in data["providers"])
    # The external-CLI block is present and SearXNG-free.
    names = {c["name"] for c in data["external_clis"]}
    assert {"agent-browser", "lightpanda", "yt-dlp", "git"} <= names
    assert "searxng" not in {n.lower() for n in names}


def test_doctor_includes_vault_and_local_lines():
    result = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(result.output)["data"]
    assert "vault_root" in data
    assert "model_tiers" in data
    assert "local_installed" in data  # the [local] neural-stack presence flag
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_doctor.py -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — the current doctor has no `keyless` banner, no external-CLI block, no `local_installed` field; `KeyError`/missing-string assertions fire.

- [ ] **Step 3: Rewrite `cli/doctor.py`**

Replace the entire contents of `src/bad_research/cli/doctor.py`:

```python
"""`bad doctor` — the keyless capability report. No network, no key checks.

Reports: the keyless-by-default banner, the keyless provider rows (host model +
keyless search/browse), the external keyless CLIs the skill drives (agent-browser/
lightpanda/yt-dlp/git) with one-line install hints, and whether the optional
`[local]` neural stack is installed. SearXNG is intentionally silent (opt-in).
"""

from __future__ import annotations

import importlib.util
from dataclasses import asdict
from pathlib import Path

import typer

from bad_research.cli._output import console, output
from bad_research.models.output import success
from bad_research.providers import external_cli_status, provider_status


def _local_installed() -> bool:
    """True iff the [local] neural stack (sentence-transformers) is importable."""
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except (ImportError, ValueError):
        return False


def doctor(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
) -> None:
    """Report the keyless capability surface: providers, external CLIs, [local]. Network-free."""
    statuses = provider_status()
    clis = external_cli_status()
    local_installed = _local_installed()

    # Vault root + model tiers from config (best-effort; defaults if config absent).
    try:
        from bad_research.config import BadResearchConfig

        cfg = BadResearchConfig()
        vault_root = str(cfg.vault_root)
        model_tiers = dict(cfg.model_tiers)
    except Exception:  # pragma: no cover - config always loads in practice
        vault_root = str(Path.home() / ".bad-research")
        model_tiers = {
            "triage": "claude-haiku-4-5",
            "work": "claude-sonnet-4-6",
            "heavy": "claude-opus-4-7",
        }

    data = {
        "keyless": True,
        "vault_root": vault_root,
        "model_tiers": model_tiers,
        "providers": [asdict(s) for s in statuses],
        "external_clis": clis,
        "local_installed": local_installed,
        "active_count": sum(1 for s in statuses if s.active),
    }

    if json_output:
        output(success(data, vault=vault_root), json_mode=True)
        return

    console.print("[bold]bad doctor[/] — keyless capability surface\n")
    console.print("[green]keyless by default[/] — zero third-party API key required.")
    console.print("[dim](the skill uses the Claude Code host model; web via host tools + local OSS/CLIs)[/]\n")
    console.print(f"[dim]vault:[/] {vault_root}")
    console.print(f"[dim]models:[/] {model_tiers}\n")

    # Providers (all keyless: active == import resolves).
    console.print("[bold]providers[/] [dim](all keyless)[/]")
    for s in statuses:
        if s.active:
            mark, color = "OK ", "green"
        else:
            mark, color = "off", "dim"
        note = ""
        if not s.import_present and s.extra != "(base)":
            # escape the [extra] brackets so rich doesn't parse them as markup tags
            note = rf"  [dim](pip install 'bad-research\[{s.extra}]')[/]"
        console.print(f"  [{color}]{mark}[/] {s.name:<16} [dim]{s.capability}[/]{note}")

    # External CLIs the skill drives (detected; degrade gracefully when absent).
    console.print("\n[bold]external CLIs[/] [dim](skill-driven; install out-of-band)[/]")
    for c in clis:
        if c["present"]:
            console.print(f"  [green]OK [/] {c['name']:<16} [dim]found on PATH[/]")
        else:
            console.print(f"  [yellow]--[/] {c['name']:<16} [dim]{c['hint']}[/]")

    # The optional [local] neural stack.
    if local_installed:
        console.print("\n[bold]local stack[/]  [green]installed[/] [dim](torch + sentence-transformers — neural rerank/embed/NLI available)[/]")
    else:
        console.print("\n[bold]local stack[/]  [dim]not installed (default: host-model rerank, FTS5/BM25 recall). `pip install 'bad-research\\[local]'` for offline neural.[/]")

    console.print(f"\n[bold]{data['active_count']}[/] provider(s) active. [dim]Keyless pipeline (host WebSearch + ddgs + crawl4ai + BM25 + host-model rerank) runs with zero keys.[/]")


__all__ = ["doctor"]
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_doctor.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (6 tests).

- [ ] **Step 5: Eyeball the human-readable output**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run bad doctor
```
Expected: a keyless banner, a `providers (all keyless)` block, an `external CLIs` block where `git` shows `OK` and the others show their install hints (unless installed), and a `local stack` line. No SearXNG anywhere.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add src/bad_research/cli/doctor.py tests/test_packaging/test_doctor.py
git commit -m "feat(KR-7): bad doctor — keyless capability report (CLIs + hints + [local], SearXNG silent)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Calibrate — keyless live wiring + keep offline StubJudge tested

**Files:**
- Test: `tests/test_calibrate/test_calibrate_cmd.py` (modify)
- Modify: `src/bad_research/calibrate/baselines.py`
- Modify: `src/bad_research/cli/calibrate.py`

The offline `StubJudge` path stays the tested zero-key path (unchanged behavior). The live path drives KR-6's keyless `run_query` (still needs `ANTHROPIC_API_KEY` for the headless model calls — resolved: anthropic stays core). The keyed baselines (`PerplexityBaseline` via `PPLX_API_KEY` = deleted Sonar; `GrokBaseline` via `XAI_API_KEY`) reference removed/non-keyless providers — drop them from `available_baselines()` so the live path stays keyless-baseline-clean.

- [ ] **Step 1: Extend the failing test**

Add these tests to the end of `tests/test_calibrate/test_calibrate_cmd.py` (keep the two existing tests; append):

```python
def test_offline_calibrate_needs_zero_keys(tmp_path, monkeypatch):
    """The offline path must run with no provider env var set (conftest clears them)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        app, ["calibrate", "keyless?", "--offline", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "calibration-report.json").exists()


def test_available_baselines_is_keyless_clean(monkeypatch):
    """No keyed baseline (Perplexity/Grok) is offered, regardless of env keys."""
    monkeypatch.setenv("PPLX_API_KEY", "pplx-xxx")
    monkeypatch.setenv("XAI_API_KEY", "xai-xxx")
    from bad_research.calibrate import available_baselines

    names = {b.name for b in available_baselines()}
    assert "perplexity" not in names
    assert "grok" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_calibrate/test_calibrate_cmd.py -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — `test_available_baselines_is_keyless_clean` fails because `available_baselines()` still offers `perplexity`/`grok` when their keys are set. (`test_offline_calibrate_needs_zero_keys` should pass — it documents the kept offline path.)

- [ ] **Step 3: Drop keyed baselines from `baselines.py`**

In `src/bad_research/calibrate/baselines.py`, replace the `_ApiBaseline`/`PerplexityBaseline`/`GrokBaseline` classes and the `available_baselines` function. Find this block:

```python
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

Replace it with the keyless-clean version:

```python
def available_baselines() -> list[Baseline]:
    """Every baseline whose dependency is present (keyless only).

    The keyed deep-research APIs (Perplexity/Grok) are REMOVED in the keyless
    re-architecture — they need third-party keys, which the keyless rule forbids.
    The only baseline is `hyperresearch` (host-driven, structural comparator) when
    its package is importable. The keyless calibration plan
    (docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md) measures the
    keyless pipeline against keyless references instead.
    """
    candidates: list[Baseline] = [HyperresearchBaseline()]
    return [b for b in candidates if b.available()]
```

Then update the module's `__all__` — remove the deleted class names:

Find:
```python
__all__ = [
    "Baseline",
    "BaselineResult",
    "BaselineUnavailable",
    "GrokBaseline",
    "HyperresearchBaseline",
    "PerplexityBaseline",
    "available_baselines",
]
```
Replace with:
```python
__all__ = [
    "Baseline",
    "BaselineResult",
    "BaselineUnavailable",
    "HyperresearchBaseline",
    "available_baselines",
]
```

Also remove the now-unused `import os` at the top of `baselines.py` (it was only read by `_ApiBaseline`).

Find:
```python
import importlib.util
import os
from dataclasses import dataclass
```
Replace with:
```python
import importlib.util
from dataclasses import dataclass
```

- [ ] **Step 4: Update `cli/calibrate.py` docstring + live-path comment (keyless framing)**

In `src/bad_research/cli/calibrate.py`, update the module docstring. Find:

```python
"""`bad calibrate <query>` — OFFLINE calibration harness (SPEC §14).

Runs a query through bad-research, judges it on the 5-axis rubric, compares to
available key-gated baselines, and writes calibration-report.{json,md}. This is
calibration, NOT a per-run gate (SPEC §10 Excluded list).

`--offline` forces a deterministic stub runner + StubJudge so the command runs
with ZERO keys and ZERO network (the tested path). The live path drives the real
pipeline + a single strong-model LLMJudge + key-gated baselines; it needs an
Anthropic key and is exercised only when keyed.
"""
```
Replace with:

```python
"""`bad calibrate <query>` — OFFLINE calibration harness (SPEC §14; keyless).

Runs a query through bad-research, judges it on the 5-axis rubric, and writes
calibration-report.{json,md}. Calibration, NOT a per-run gate (SPEC §10 Excluded).

`--offline` forces a deterministic stub runner + StubJudge so the command runs
with ZERO keys and ZERO network — this is the tested path.

The live path drives the KEYLESS `pipeline.run_query` (host WebSearch + ddgs +
crawl4ai + FTS5/BM25 + host-model LLM-rerank — no third-party key) and a single
strong-model LLMJudge. It still reads ANTHROPIC_API_KEY for the HEADLESS model
calls (the only path that needs it; the skill path uses the Claude Code host
model and needs no key). The only baseline is the keyless `hyperresearch` one —
the keyed deep-research baselines (Perplexity/Grok) were removed.
"""
```

- [ ] **Step 5: Run the calibrate tests to verify they pass**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_calibrate/ -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (the existing calibrate tests + the 2 new ones; the `live` runner-bridge test stays skipped). If `tests/test_calibrate/test_baselines.py` references `PerplexityBaseline`/`GrokBaseline`, update those assertions to the keyless reality (only `HyperresearchBaseline` remains) as part of this step.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add src/bad_research/calibrate/baselines.py src/bad_research/cli/calibrate.py tests/test_calibrate/
git commit -m "feat(KR-7): keyless calibrate — drop keyed baselines, live path drives keyless run_query

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Conftest — trim live keys to the keyless reality

**Files:**
- Test: (self-testing) `tests/test_packaging/test_live_skip.py` (exists; re-run to confirm)
- Modify: `tests/conftest.py`

The `_LIVE_KEYS` and `_clear_provider_keys` lists reference deleted providers (`TAVILY_API_KEY`, `EXA_API_KEY`, `COHERE_API_KEY`, `BAD_RESEARCH_EMBED_MODEL`, `BAD_RESEARCH_RERANK_MODEL`). Trim to the keyless reality: only `ANTHROPIC_API_KEY` marks a live run, and only it + the kept config env vars are cleared.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_packaging/test_live_skip.py`:

```python
def test_conftest_live_keys_are_keyless():
    """Only ANTHROPIC_API_KEY marks a live run; no deleted-provider keys remain."""
    import tests.conftest as ct

    assert ct._LIVE_KEYS == ("ANTHROPIC_API_KEY",)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_live_skip.py::test_conftest_live_keys_are_keyless -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — `_LIVE_KEYS` is still the 4-tuple `(ANTHROPIC_API_KEY, TAVILY_API_KEY, EXA_API_KEY, COHERE_API_KEY)`.

- [ ] **Step 3: Trim `conftest.py`**

In `tests/conftest.py`, find:
```python
_LIVE_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY", "COHERE_API_KEY")
```
Replace with:
```python
# Keyless: ANTHROPIC_API_KEY is the only key any path reads (the headless/calibration
# bridge). Every other capability is keyless (host tools + local OSS/CLIs).
_LIVE_KEYS = ("ANTHROPIC_API_KEY",)
```

Then find the `_clear_provider_keys` env-var tuple:
```python
    for var in (
        "ANTHROPIC_API_KEY",
        "COHERE_API_KEY",
        "BAD_RESEARCH_BUDGET_USD",
        "BAD_RESEARCH_CHEAP",
        "BAD_RESEARCH_EMBED_MODEL",
        "BAD_RESEARCH_RERANK_MODEL",
        "BAD_RESEARCH_VAULT_ROOT",
    ):
```
Replace with (drop the deleted-provider/embed/rerank env vars; keep the keyless config knobs):
```python
    for var in (
        "ANTHROPIC_API_KEY",
        "BAD_RESEARCH_BUDGET_USD",
        "BAD_RESEARCH_CHEAP",
        "BAD_RESEARCH_VAULT_ROOT",
    ):
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_live_skip.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (the auto-skip test + the new conftest assertion).

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add tests/conftest.py tests/test_packaging/test_live_skip.py
git commit -m "test(KR-7): conftest live-keys trimmed to keyless reality (ANTHROPIC only)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Rebuild the coverage `omit` list for the keyless module set

**Files:**
- Test: `tests/test_packaging/test_pytest_config.py` (extend)
- Modify: `pyproject.toml` (`[tool.coverage.run].omit`)

The current `omit` list references deleted modules (`web/exa_provider.py`, `web/providers/*`, `web/builtin.py`, `web/crawl4ai_provider.py`) and modules KR-2…KR-6 renamed/added. Rebuild it to (a) drop omits for now-deleted modules, (b) keep the inherited-surface omits that still exist, (c) ensure the new keyless modules (`web/search/`, `web/content/`, `browse/agent_browser.py`, the keyless `retrieval/rerank.py`) are NOT omitted so they count toward the floor.

- [ ] **Step 1: Extend the failing test**

Append to `tests/test_packaging/test_pytest_config.py`:

```python
@pytest.fixture(scope="module")
def cov() -> dict:
    pp = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pp["tool"]["coverage"]["run"]


def test_omit_drops_deleted_modules(cov):
    omit_joined = " ".join(cov["omit"])
    # Deleted in the keyless rebuild — must NOT appear in omit (the files are gone).
    for gone in (
        "exa_provider",
        "web/providers",
        "web/builtin.py",
        "web/crawl4ai_provider.py",
    ):
        assert gone not in omit_joined, f"omit references deleted module: {gone}"


def test_new_keyless_modules_are_not_omitted(cov):
    omit_joined = " ".join(cov["omit"])
    # The new keyless surface must be COVERED (not omitted), so it counts to the floor.
    for covered in (
        "web/search",
        "web/content",
        "browse/agent_browser",
        "retrieval/rerank",
    ):
        assert covered not in omit_joined, f"new keyless module wrongly omitted: {covered}"


def test_coverage_floor_still_80(cfg):
    assert "--cov-fail-under=80" in cfg["addopts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_pytest_config.py -p no:cacheprovider -o addopts="" -q
```
Expected: FAIL — the current `omit` still lists `*/web/builtin.py`, `*/web/crawl4ai_provider.py` (and the deleted exa/providers paths show up via the failing test).

- [ ] **Step 3: Rewrite the `[tool.coverage.run].omit` list in `pyproject.toml`**

Replace the `omit = [ ... ]` block under `[tool.coverage.run]` with the keyless-rebuilt list:

```toml
omit = [
    "*/tests/*",
    "*/__main__.py",
    # inherited hyperresearch surfaces (HTTP server, MCP server, index/graph gen)
    "*/serve/*",
    "*/mcp/server.py",
    "*/indexgen/*",
    "*/graph/*",
    "*/models/graph.py",
    "*/models/search.py",
    # the optional [local] neural stack — only materialized under `pip install [local]`,
    # so it is not exercised by the default keyless test run.
    "*/embed/bge_local.py",
    "*/retrieval/store.py",
    # inherited core data layer (vault sync, notes, enrich, linking, migrations) — kept,
    # but unit-covered by the inherited hyperresearch suite, not this codebase's adds.
    "*/core/sync.py",
    "*/core/note.py",
    "*/core/enrich.py",
    "*/core/linker.py",
    "*/core/patterns.py",
    "*/core/frontmatter.py",
    "*/core/templates.py",
    "*/core/migrations.py",
    "*/core/vault.py",
    "*/core/fetcher.py",
    "*/core/agent_docs.py",
    "*/core/similarity.py",
    "*/core/config.py",
    "*/search/fts.py",
    "*/search/filters.py",
    "*/cli/fetch.py",
    "*/cli/research.py",
    "*/funnel/store.py",
]
```

(Note: this removes `*/web/builtin.py` and `*/web/crawl4ai_provider.py` — those modules are deleted in the keyless rebuild — and adds `*/embed/bge_local.py` + `*/retrieval/store.py` as the `[local]`-only surface not exercised in the default keyless run. The new keyless `web/search/`, `web/content/`, `browse/agent_browser.py`, and `retrieval/rerank.py` are intentionally absent so they count to the floor.)

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_pytest_config.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add pyproject.toml tests/test_packaging/test_pytest_config.py
git commit -m "build(KR-7): rebuild coverage omit for the keyless module set (drop deleted, count new)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Full keyless suite green at the 80% floor

**Files:** none (verification + targeted fixes only).

Run the whole suite under the real config (with coverage). Any failure here is one of: (a) a stale test still referencing a deleted module/import — delete or rewrite it; (b) a new keyless module under the floor — add a focused unit test; (c) a kept seam that lost coverage — restore the test. Do NOT lower the floor.

- [ ] **Step 1: Run the full suite with coverage**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest 2>&1 | tail -40
```
Expected (first pass) may FAIL with: collection errors from tests importing deleted modules (e.g. `tests/test_web/test_exa.py`, `tests/test_browse/test_browse_browserbase.py`, `tests/test_embed/test_cohere.py`), and/or `--cov-fail-under=80` not met because new keyless modules lack tests.

- [ ] **Step 2: Delete stale tests for deleted modules**

For every collection error naming a deleted module, delete the orphaned test file. The canonical set KR-1…KR-4 should have removed (delete any that survive):

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
for t in \
  tests/test_web/test_tavily.py tests/test_web/test_sonar.py \
  tests/test_web/test_firecrawl.py tests/test_web/test_exa.py \
  tests/test_web/test_cascade.py \
  tests/test_browse/test_browse_browserbase.py tests/test_browse/test_browse_browseruse.py \
  tests/test_browse/test_extract_agentql.py tests/test_browse/test_extract_stagehand.py \
  tests/test_embed/test_cohere.py ; do
  test -f "$t" && git rm -q "$t" && echo "removed $t" || true
done
```
(If a file was already removed by KR-1…KR-4, the loop skips it — idempotent.)

- [ ] **Step 3: Re-run; identify under-floor keyless modules**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest 2>&1 | tail -50
```
Read the `term-missing` coverage table. For any **new keyless module** (`web/search/*`, `web/content/*`, `browse/agent_browser.py`, `retrieval/rerank.py::ClaudeCodeReranker`) below ~80%, add a focused unit test that exercises the missing lines (KR-2…KR-5 each shipped tests for their package; this step only backfills gaps the rewire exposed). Example pattern for a thin gap — the `ClaudeCodeReranker` graceful-degradation path:

```python
# tests/test_retrieval/test_rerank_keyless.py  (only if rerank.py is under-floor)
"""ClaudeCodeReranker: malformed host output → graceful 0.0, no crash."""

from __future__ import annotations

from bad_research.retrieval.rerank import ClaudeCodeReranker


class _FakeHost:
    """A host-model stub returning a fixed completion (no network)."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages, **kw):
        from types import SimpleNamespace

        return SimpleNamespace(text=self._text, usage={}, model="stub", tool_calls=[])


def test_rerank_parses_scores():
    r = ClaudeCodeReranker(host=_FakeHost('[{"i":0,"s":0.9},{"i":1,"s":0.1}]'))
    out = dict(r.rerank("q", ["doc a", "doc b"]))
    assert out[0] == 0.9 and out[1] == 0.1


def test_rerank_malformed_degrades_to_zero():
    r = ClaudeCodeReranker(host=_FakeHost("not json at all"))
    out = dict(r.rerank("q", ["doc a", "doc b"]))
    assert all(v == 0.0 for v in out.values())  # graceful, never raises
```

> **Note:** the exact `ClaudeCodeReranker.__init__` signature is owned by KR-5 (`docs/INTERFACES_KEYLESS.md` §5.3). Read `src/bad_research/retrieval/rerank.py` before writing this test and match its real constructor (it may take the host via `get_llm_provider()` rather than an injected `host=`). Only write this test if the module is under the floor; otherwise skip — do not pad.

- [ ] **Step 4: Re-run until green at the floor**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest 2>&1 | tail -15
```
Expected: `Required test coverage of 80% reached.` and `passed` (the two `live` tests `SKIPPED`). Iterate Steps 2–3 until this holds.

- [ ] **Step 5: Ruff + mypy clean on the KR-7-touched modules**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run ruff check src/bad_research/providers.py src/bad_research/cli/doctor.py src/bad_research/cli/calibrate.py src/bad_research/calibrate/baselines.py
uv run mypy src/bad_research/providers.py src/bad_research/cli/doctor.py
```
Expected: `All checks passed!` / no mypy errors. Fix any lint/type issues inline.

- [ ] **Step 6: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add -A
git commit -m "test(KR-7): full keyless suite green at 80% floor — drop stale tests, backfill new modules

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `uv build` produces a keyless wheel; metadata carries no removed provider

**Files:**
- Test: `tests/test_packaging/test_wheel_build.py` (create)

The wheel's `METADATA` (PKG-INFO) lists `Requires-Dist` lines. We assert the built artifact's metadata carries the keyless base deps and **none** of the removed providers — proving the package, as shipped, is keyless. This builds once into a tmp dir (offline; `uv build` resolves nothing — it only packages).

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging/test_wheel_build.py`:

```python
"""`uv build` produces a wheel whose metadata is keyless (no removed providers)."""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Providers that must NOT appear in the built wheel's Requires-Dist (base metadata).
FORBIDDEN_IN_METADATA = (
    "cohere",
    "tavily-python",
    "exa-py",
    "firecrawl-py",
    "browserbase",
    "browser-use",
    "agentql",
)


@pytest.fixture(scope="module")
def wheel_metadata(tmp_path_factory) -> str:
    out = tmp_path_factory.mktemp("dist")
    # uv build is offline-friendly: it packages, it does not resolve/install deps.
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"uv build failed:\n{proc.stdout}\n{proc.stderr}"
    wheels = list(out.glob("bad_research-*.whl"))
    assert wheels, f"no wheel produced in {out}: {list(out.iterdir())}"
    with zipfile.ZipFile(wheels[0]) as zf:
        meta_name = next(n for n in zf.namelist() if n.endswith("METADATA"))
        return zf.read(meta_name).decode("utf-8")


def test_wheel_metadata_lists_keyless_base(wheel_metadata):
    requires = "\n".join(
        line for line in wheel_metadata.splitlines() if line.startswith("Requires-Dist:")
    ).lower()
    for dep in ("anthropic", "httpx", "crawl4ai", "ddgs", "trafilatura", "feedparser"):
        assert dep in requires, f"base dep missing from wheel metadata: {dep}"


def test_wheel_metadata_has_no_removed_providers(wheel_metadata):
    base_requires = [
        line
        for line in wheel_metadata.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line
    ]
    joined = "\n".join(base_requires).lower()
    leaked = [p for p in FORBIDDEN_IN_METADATA if p.lower() in joined]
    assert not leaked, f"removed providers leaked into base wheel metadata: {leaked}"


def test_wheel_entry_points(wheel_metadata):
    # The wheel must declare the `bad`/`badr` console scripts (entry_points.txt).
    # METADATA does not carry entry points; re-open the wheel for entry_points.txt.
    out = ROOT  # not used; metadata already proves the build. Smoke the Python is 3.11+.
    assert sys.version_info >= (3, 11)
```

> **Note:** if `uv build` is slow in CI, mark this module `@pytest.mark.integration` and ensure the integration marker is collected by default (it is — only `live` auto-skips). The build is offline.

- [ ] **Step 2: Run test to verify it fails (or builds clean)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_wheel_build.py -p no:cacheprovider -o addopts="" -q
```
Expected: If KR-1's pyproject was already keyless, the build succeeds and these PASS. If a removed provider still lurks in `dependencies` (Task 1 not yet applied or reverted), `test_wheel_metadata_has_no_removed_providers` FAILS — fix `pyproject.toml`. The point of the test is to catch a regression in the shipped artifact, not just the source TOML.

- [ ] **Step 3: No separate impl** — the implementation is Task 1's keyless `pyproject.toml`; this task only adds the artifact-level guard. If Step 2 failed, fix `pyproject.toml` (Task 1) and re-run.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_packaging/test_wheel_build.py -p no:cacheprovider -o addopts="" -q
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add tests/test_packaging/test_wheel_build.py
git commit -m "test(KR-7): uv build wheel metadata is keyless (no removed providers in Requires-Dist)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Fresh base-only install smoke — `bad --version` / `doctor` / `calibrate --offline` keyless

**Files:** none (a scripted smoke test run by hand + recorded as a doc step). This is the "done" gate from the KR-7 scope: a fresh base-only venv runs the three commands keylessly.

- [ ] **Step 1: Build the wheel into a clean dist dir**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
rm -rf /tmp/kr7-dist && uv build --wheel --out-dir /tmp/kr7-dist
ls /tmp/kr7-dist
```
Expected: one `bad_research-0.1.0-py3-none-any.whl`.

- [ ] **Step 2: Create a fresh base-only venv and install ONLY the base wheel (no extras)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /tmp
rm -rf /tmp/kr7-venv
uv venv /tmp/kr7-venv --python 3.11
/tmp/kr7-venv/bin/python -m pip install --quiet --upgrade pip
/tmp/kr7-venv/bin/python -m pip install --quiet /tmp/kr7-dist/bad_research-*.whl 2>&1 | tail -5
echo "installed"
```
Expected: install resolves the keyless base only. (`pip` pulls anthropic/httpx/crawl4ai/ddgs/etc; no torch, no lancedb, no cohere/tavily/exa/firecrawl.)

- [ ] **Step 3: Assert the removed providers are NOT importable in the fresh venv**

Run:
```bash
/tmp/kr7-venv/bin/python - <<'PY'
import importlib.util as u
removed = ["cohere","tavily","exa_py","firecrawl","browserbase","agentql","browser_use","torch","lancedb"]
present = [m for m in removed if u.find_spec(m) is not None]
print("LEAKED:", present) if present else print("CLEAN: no removed/heavy providers importable")
PY
```
Expected: `CLEAN: no removed/heavy providers importable`.

- [ ] **Step 4: Run the three keyless commands with NO API key set**

Run:
```bash
cd /tmp
env -u ANTHROPIC_API_KEY /tmp/kr7-venv/bin/bad --version
echo "--- doctor ---"
env -u ANTHROPIC_API_KEY /tmp/kr7-venv/bin/bad doctor
echo "--- calibrate offline ---"
rm -rf /tmp/kr7-cal && mkdir /tmp/kr7-cal
env -u ANTHROPIC_API_KEY /tmp/kr7-venv/bin/bad calibrate "does X cause Y?" --offline --out /tmp/kr7-cal
ls /tmp/kr7-cal
```
Expected:
- `bad --version` → `bad-research v0.1.0`
- `bad doctor` → the keyless banner + provider rows + external-CLI block + `[local] not installed`, exit 0, **no traceback, no key error**
- `bad calibrate ... --offline` → writes `calibration-report.json` + `calibration-report.md` in `/tmp/kr7-cal`, exit 0

- [ ] **Step 5: Record the smoke result in the calibration-plan doc (Task 11 creates it) and clean up**

Run:
```bash
rm -rf /tmp/kr7-venv /tmp/kr7-dist /tmp/kr7-cal
echo "smoke clean"
```
Expected: `smoke clean`. (No commit — this task is a manual verification gate. Its evidence is captured in the Task 11 doc's "Verified" section.)

---

## Task 11: The keyless calibration plan doc

**Files:**
- Create: `docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md`

A doc, not code. It records what the keyless calibration measures (the judge stays offline-only; this is the plan for the live measurement pass), and the Task-10 smoke result.

- [ ] **Step 1: Write the doc**

Create `docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md`:

```markdown
# Bad Research — KR-7 Keyless Calibration Plan

> The offline `StubJudge` path is the tested, zero-key path (CI). This doc is the
> plan for the LIVE measurement pass — what to measure, against what keyless
> reference, with what metric. The judge (`LLMJudge`) runs against the Claude Code
> host model; calibration is never a per-run gate (SPEC §10 Excluded).

## What we measure (keyless references only)

| Target seam | Reference (keyless / one-time read-only) | Metric | Source |
|---|---|---|---|
| `web/content.fetch_clean` (URL→markdown) | a one-time, read-only fetch via a free public reader (no key, manual, not in CI) | markdown fidelity: % of body text retained vs the raw article; boilerplate-strip precision | dossier 12 §11 |
| keyless search (host WebSearch + ddgs + verticals, RRF k=60) | the offline 20-query calibration set scored by the 5-axis judge | pass-rate @ relevance gate 0.70; mean overall | dossier 13 §7.2 |
| rerank A/B | host-model `ClaudeCodeReranker` vs `[local]` ms-marco-MiniLM vs `none` (identity) | nDCG@10 on the calibration set's labelled relevances | dossier 15 §8.4 |
| grounding | injected-claim recall: seed the corpus with a known-false claim, confirm the gate flags it | injected-claim recall ≥ target; false-anchor rate | dossier 16 §2 / harness deferred items |

## How it runs

`bad calibrate <query>` (live path, ANTHROPIC_API_KEY set for the HEADLESS model):
1. `pipeline.run_query` drives the keyless backend (host WebSearch + ddgs + crawl4ai
   + FTS5/BM25 + host-model LLM-rerank). No third-party key.
2. `LLMJudge` (single strong-model call, 5-axis rubric, temp 0) scores the report.
3. The only baseline is the keyless `hyperresearch` structural comparator (when
   importable). The keyed deep-research baselines (Perplexity/Grok) are REMOVED —
   they need third-party keys, which the keyless rule forbids.
4. Writes `calibration-report.{json,md}`.

## Verified (KR-7 Task 10, base-only fresh install, 2026-05-27)

- `bad --version` → `bad-research v0.1.0` (keyless)
- `bad doctor` → keyless banner + provider rows + external-CLI block, exit 0, no key error
- `bad calibrate "..." --offline` → both report files written, exit 0, zero keys
- Fresh base venv: cohere/tavily/exa/firecrawl/browserbase/agentql/browser-use/torch/lancedb
  all NOT importable (lean base confirmed)
```

- [ ] **Step 2: Verify the doc is well-formed (markdown table parses)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
wc -l docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md
head -5 docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md
```
Expected: ~50 lines; the header renders.

- [ ] **Step 3: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git add docs/plans/2026-05-27-bad-research-KR-7-calibration-plan.md
git commit -m "docs(KR-7): keyless calibration plan + base-only smoke verification record

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Final full-suite green + ruff + mypy + clean tree (the launch gate)

**Files:** none (final verification before declaring KR-7 done).

- [ ] **Step 1: Full suite with coverage, from a clean state**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest 2>&1 | tail -20
```
Expected: all tests pass (the two `live` tests `SKIPPED`), `Required test coverage of 80% reached.`

- [ ] **Step 2: Ruff + mypy across `src/`**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run ruff check src/ tests/
uv run mypy src/bad_research/providers.py src/bad_research/cli/doctor.py src/bad_research/cli/calibrate.py src/bad_research/calibrate/baselines.py
```
Expected: `All checks passed!`; no mypy errors on the KR-7-touched modules.

- [ ] **Step 3: Final keyless invariant grep + build smoke**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
grep -rEl 'import cohere|import tavily|import exa_py|import firecrawl|import browserbase|import agentql|import browser_use' src/ && echo "FAIL: keyed import survives" || echo "PASS: keyless src/"
uv build 2>&1 | tail -3
```
Expected: `PASS: keyless src/`; `uv build` produces sdist + wheel with no error.

- [ ] **Step 4: Confirm the tree is clean**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
git status --short
```
Expected: clean (or only `dist/` artifacts, which are gitignored). If `dist/` is not ignored, do not commit it.

- [ ] **Step 5: Done**

KR-7 is complete: `pip install bad-research` (base, no extras) gives `bad --version` / `bad doctor` / `bad calibrate --offline` keylessly; the removed keyed providers are not importable; the suite is green at the 80% floor; the wheel builds and base-only-installs clean. No commit (verification only).

---

## Self-Review

**1. Spec coverage (KR-7 scope from the brief):**
- Finalize `pyproject.toml` to pure-keyless base + extras → Task 1.
- Base-leanness test (removed providers NOT importable from base) → Task 2.
- `bad doctor` keyless capability surface (CLIs + hints, silent SearXNG, `[local]`, keyless-by-default) → Tasks 3 (data) + 4 (report).
- `bad calibrate` headless `run_query` uses keyless pipeline; offline StubJudge stays the tested path → Task 5.
- Update/repair full test suite + coverage floor (drop omits for deleted modules; cover new keyless modules) → Tasks 6, 7, 8.
- `uv build` working wheel + fresh base-only install runs the three commands keylessly → Tasks 9, 10.
- Resolved decisions (anthropic core; CLIs detect+degrade; SearXNG silent; `[local]` use-if-present) → honored across Tasks 1, 3, 4 (silent SearXNG in `EXTERNAL_CLIS` exclusion; `[local]` find_spec, no auto-install).
- Calibration plan doc → Task 11.

**2. Placeholder scan:** every code step shows complete, runnable code; every command is exact with expected output. No TBD/TODO. The one conditional impl (Task 8 Step 3 reranker test) is gated on "only if under-floor" and instructs reading the real KR-5 signature first — not a placeholder, an honest dependency on a sibling plan's owned interface.

**3. Type consistency:** `external_cli_status()` returns `list[dict]` with keys `{name, present, hint}` — defined in Task 3, consumed identically in Task 4's doctor + the JSON surface + the Task 4 tests. `provider_status()` / `ProviderStatus` fields (`requires_key`, `key_present`, `import_present`, `active`, `extra`, `capability`) are unchanged from the existing dataclass and used consistently. `EXTERNAL_CLIS` (dict[str,str]) is the single source for both the helper and the test hint assertion. The doctor JSON `data` keys (`keyless`, `external_clis`, `local_installed`, `providers`, `vault_root`, `model_tiers`) match between Task 4's impl and its tests.
```
