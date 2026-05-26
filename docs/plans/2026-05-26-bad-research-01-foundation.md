# Bad Research — Plan 01: Foundation & Seams — Implementation Plan

For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development

## Goal

Stand up the `bad-research` package skeleton (a fork of `hyperresearch`) plus the two provider seams every later plan depends on:

1. **`llm/`** — the `LLMProvider` Protocol, the `LLMMessage`/`LLMResponse` dataclasses, and a working `AnthropicProvider` that resolves model **tiers** (`triage`/`work`/`heavy`) to concrete Claude model IDs, applies the `--cheap` demotion (`heavy`→`work`), and stamps Anthropic **prompt-cache `cache_control` breakpoints** on the stable system+tools prefix (the single cheapest cost win in the whole product — dossier 09 A1.2).
2. **`embed/`** — the `EmbedProvider` Protocol and a working `CohereEmbedProvider` (Cohere `embed-v3`, dim 1024, asymmetric `document`/`query` input types).
3. **`config.py`** — the `BadResearchConfig` dataclass exactly per `INTERFACES.md`, with env + `~/.config/bad-research/config.toml` precedence and the model-tier map.

When Plan 01 is done, an engineer can `pip install -e .`, run `bad --version` / `badr --version`, construct an `AnthropicProvider` and `CohereEmbedProvider` (mocked in tests), and load a `BadResearchConfig` from env+TOML. **No server, no pipeline yet** — those are Plans 02–08. This plan delivers only the foundation seams and the package that holds them.

Everything is user-side. No backend service is started anywhere in this plan.

## Architecture

`bad-research` is a fork of `hyperresearch` (`hyperresearch 0.8.6`, DB schema v8). The fork keeps the vault, FTS, web-provider Protocol, MCP, CLI, and skill machinery verbatim; this plan adds three *new* modules under `src/bad_research/` that did **not** exist in hyperresearch:

- hyperresearch has **zero LLM client** (verified: `grep anthropic src/` → 0 hits). It is Anthropic-only *by virtue of running inside Claude Code*. Bad Research adds a first-class `LLMProvider` seam so the deterministic Python backend (and, later, the standalone faces) can call Claude directly. This is extension-point **EP-D** from dossier 01 §3.4 — "the model backend extension point does not exist in hyperresearch today — we create it."
- hyperresearch has **no embeddings writer/reader** (the `embeddings` SQLite table is vestigial). Bad Research adds an `EmbedProvider` seam; Plan 02 wires it to LanceDB. This plan only delivers the seam + Cohere impl.
- `config.py` is the **new** Bad-Research-level config (distinct from hyperresearch's per-vault `core/config.py:VaultConfig`, which the fork keeps untouched). `BadResearchConfig` holds provider keys, the model-tier map, budget caps, and thresholds — the cross-cutting knobs from SPEC §12.

The two seams follow hyperresearch's `web/base.py` pattern verbatim: a `@runtime_checkable` `Protocol` + a dataclass unit-of-exchange + a string-dispatch factory, with **lazy SDK imports inside `__init__`** (so the optional dep stays optional) and **env-key resolution with a helpful `RuntimeError`** when the key is missing (mirrors `web/exa_provider.py:53-58`).

**KV-cache discipline (load-bearing).** `AnthropicProvider.complete(..., cache=True)` stamps `cache_control: {"type": "ephemeral"}` on the **last block of the stable system prefix** and on the **last tool definition**. Anthropic caches the matching byte-identical prefix across requests; the 2nd…Nth spawn of a worker type within a run pays ~10% of input-token cost (dossier 09 A1.2; Anthropic hard limit: ≤4 breakpoints/request — we use 2). The caller is responsible for keeping the system+tools prefix byte-identical across spawns; the provider only stamps the markers.

**Tier→model resolution.** `tier` is a `Literal["triage","work","heavy"]`. The provider holds a `model_tiers` dict (from config). `triage`→`claude-haiku-4-5`, `work`→`claude-sonnet-4-6`, `heavy`→`claude-opus-4-7`. With `cheap=True`, `heavy` resolves to the `work` model (Opus→Sonnet demotion, dossier 09 A3 `--cheap` flag). `triage`/`work` are never demoted.

## Tech Stack

- **Python 3.11–3.13**, `hatchling` build backend, `pyproject.toml` (fork of hyperresearch's).
- **`anthropic>=0.40`** SDK (`anthropic.Anthropic` client, `messages.create`). Hard dep (Bad Research's default and only LLM at GA).
- **`cohere>=5.0`** SDK (`cohere.ClientV2`, `embed`). Optional extra `[cohere]` (graceful degradation if absent — SPEC §12 "keys all optional").
- **`pytest>=7.4`** with `unittest.mock` / `monkeypatch`. SDK clients are mocked at the source module (`monkeypatch.setattr(anthropic, "Anthropic", factory)`) — the exact pattern in `tests/test_web/test_exa_provider.py:48-51`. No network calls in tests.
- **`tomllib`** (stdlib, 3.11+) for TOML config parsing — same as hyperresearch's `core/config.py:5`.

Reference clone (read-only): `/Users/seventyleven/Desktop/researchfms/hyperresearch/`.
Source root being built: `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/`.

---

## File Structure

All paths are under `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/`.

| File | Single responsibility |
|---|---|
| `pyproject.toml` | Package metadata; deps (`anthropic`, base hyperresearch deps); optional extras (`cohere`, `exa`, `mcp`); entry points `bad`/`badr` → `bad_research.cli:app`; hatchling wheel packaging of `src/bad_research`. |
| `src/bad_research/__init__.py` | Package marker + `__version__ = "0.1.0"`. |
| `src/bad_research/llm/__init__.py` | Re-exports `LLMProvider`, `LLMMessage`, `LLMResponse`, `ModelTier`, `get_llm_provider`. |
| `src/bad_research/llm/base.py` | `ModelTier` literal; `LLMMessage`, `LLMResponse` dataclasses; `LLMProvider` Protocol; `get_llm_provider()` factory. No SDK import. |
| `src/bad_research/llm/anthropic.py` | `AnthropicProvider`: lazy `anthropic` import, tier→model resolution (`_resolve_model`), `--cheap` demotion, `cache_control` stamping on system+tools prefix, `complete()` returning `LLMResponse`. |
| `src/bad_research/embed/__init__.py` | Re-exports `EmbedProvider`, `get_embed_provider`. |
| `src/bad_research/embed/base.py` | `EmbedProvider` Protocol; `get_embed_provider()` factory. No SDK import. |
| `src/bad_research/embed/cohere.py` | `CohereEmbedProvider`: lazy `cohere` import, `name="cohere"`, `dim=1024`, `embed(texts, input_type)` with asymmetric `search_document`/`search_query` mapping. |
| `src/bad_research/config.py` | `BadResearchConfig` dataclass (per INTERFACES.md) + `load()` with env > TOML > default precedence; `~/.config/bad-research/config.toml` reader. |
| `src/bad_research/cli.py` | Minimal `typer` app exposing `--version` so `bad`/`badr` entry points resolve. (Full CLI is later plans; this is the stub the entry points need.) |
| `tests/__init__.py` | Test package marker. |
| `tests/conftest.py` | Shared fixtures (env-key clearing). |
| `tests/test_llm/__init__.py` | Test subpackage marker. |
| `tests/test_llm/test_anthropic.py` | Tests: tier→model mapping, `--cheap` demotion, `cache_control` stamping, `LLMResponse` shape, missing-key error, factory dispatch. |
| `tests/test_embed/__init__.py` | Test subpackage marker. |
| `tests/test_embed/test_cohere.py` | Tests: `name`/`dim`, asymmetric `input_type` mapping, vector return, missing-key error, factory dispatch. |
| `tests/test_config/__init__.py` | Test subpackage marker. |
| `tests/test_config/test_config.py` | Tests: defaults match INTERFACES.md, env precedence, TOML precedence, env-over-TOML, `cheap`/`budget_usd` parsing. |

---

## Tasks

### Phase 0 — Fork the package skeleton

- [ ] **Task 0.1 — Copy hyperresearch source into the bad-research fork.** Run exactly:

```bash
mkdir -p /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src
cp -R /Users/seventyleven/Desktop/researchfms/hyperresearch/src/hyperresearch \
      /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research
ls /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research
```

Expected output includes: `cli  core  export  graph  indexgen  mcp  models  search  serve  skills  web  __init__.py`.

- [ ] **Task 0.2 — Fix the package import root.** The copied tree still says `from hyperresearch...` everywhere; Plans 02+ will migrate those incrementally. For Plan 01 we only touch the NEW modules and the package marker, so the legacy `hyperresearch` imports inside the copied subdirs are out of scope (they are not imported by anything Plan 01 builds). Replace the package `__init__.py` to declare the new version. Overwrite `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/__init__.py` with exactly:

```python
"""Bad Research — michael jackson bad. A fork-and-enhance of hyperresearch."""

__version__ = "0.1.0"
```

- [ ] **Task 0.3 — Remove the legacy CLI so the new stub owns the entry point.** The copied `cli/` is a package (`cli/__init__.py`) full of `from hyperresearch...` imports that would break `bad --version`. Plan 01 ships a single-file `cli.py` stub; later plans rebuild the full CLI. Run exactly:

```bash
rm -rf /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/cli
ls /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/ | grep -c '^cli$' || echo "cli dir removed"
```

Expected output: `cli dir removed` (the `grep -c` finds 0 matches and the `||` branch fires).

- [ ] **Task 0.4 — Write `pyproject.toml`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/pyproject.toml` with exactly:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bad-research"
version = "0.1.0"
description = "michael jackson bad — a deep-research agent that's bad (i.e. the best). A fork-and-enhance of hyperresearch."
readme = "README.md"
license = "MIT"
requires-python = ">=3.11,<3.14"
authors = [{name = "Bad Research"}]
keywords = ["research", "deep-research", "llm", "agent", "claude", "retrieval", "rag"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "jinja2>=3.1",
    "platformdirs>=4.0",
    "Crawl4AI>=0.4",
    "pymupdf>=1.24",
    "httpx>=0.27",
    "anthropic>=0.40",
]

[project.optional-dependencies]
cohere = ["cohere>=5.0"]
exa = ["exa-py>=2.0.0"]
mcp = ["mcp>=1.6"]
all = ["bad-research[cohere,exa,mcp]"]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "mypy>=1.8",
]

[project.scripts]
bad = "bad_research.cli:app"
badr = "bad_research.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/bad_research"]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "RUF"]
ignore = ["E501", "B008", "B904", "E402", "N817", "SIM105"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
```

- [ ] **Task 0.5 — Write a minimal README** so `readme = "README.md"` resolves at build. Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/README.md` with exactly:

```markdown
# Bad Research

> michael jackson bad — a deep-research agent that's *bad* (i.e. the best).

A fork-and-enhance of [hyperresearch](https://github.com/jordan-gibbs/hyperresearch),
driven as a Claude Code skill. See `ultimate-research/SPEC.md` for the design.

MIT licensed.
```

- [ ] **Task 0.6 — Write the CLI stub** so the `bad`/`badr` entry points resolve. Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/cli.py` with exactly:

```python
"""Bad Research CLI — entry-point stub (full CLI lands in later plans)."""

from __future__ import annotations

import typer

from bad_research import __version__


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bad-research v{__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="bad",
    help="michael jackson bad — deep-research agent.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version",
    ),
) -> None:
    pass
```

- [ ] **Task 0.7 — Install the package editable and verify the entry points.** Run exactly:

```bash
pip install -e '/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research[dev]' && \
  bad --version && badr --version
```

Expected output ends with two lines:

```
bad-research v0.1.0
bad-research v0.1.0
```

- [ ] **Task 0.8 — Commit the skeleton.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/pyproject.toml \
        ultimate-research/bad-research/README.md \
        ultimate-research/bad-research/src/bad_research/__init__.py \
        ultimate-research/bad-research/src/bad_research/cli.py && \
git commit -m "feat(bad-research): fork skeleton — pyproject (bad/badr entry points), CLI stub

Fork of hyperresearch 0.8.6. New package root bad_research; legacy cli/ dropped
for a single-file stub. Plan 01 Phase 0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Note: the copied `src/bad_research/{core,web,...}` subdirs are intentionally NOT committed yet — they still carry `hyperresearch` imports and are migrated in later plans. This commit is only the Plan-01 surface.

---

### Phase 1 — `config.py` (BadResearchConfig)

TDD: write the failing test, run it (FAIL), write the minimal impl, run it (PASS), commit.

- [ ] **Task 1.1 — Create test package markers and conftest.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/__init__.py` as an empty file (write a single newline). Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/conftest.py` with exactly:

```python
"""Shared test fixtures for bad-research."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no real provider keys leak into tests from the host environment."""
    for var in (
        "ANTHROPIC_API_KEY",
        "COHERE_API_KEY",
        "BAD_RESEARCH_BUDGET_USD",
        "BAD_RESEARCH_CHEAP",
        "BAD_RESEARCH_EMBED_MODEL",
        "BAD_RESEARCH_RERANK_MODEL",
        "BAD_RESEARCH_VAULT_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)
```

Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_config/__init__.py` as an empty file (single newline).

- [ ] **Task 1.2 — Write the failing config test.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_config/test_config.py` with exactly:

```python
"""Tests for BadResearchConfig — defaults, env precedence, TOML precedence."""

from __future__ import annotations

from pathlib import Path

import pytest

from bad_research.config import BadResearchConfig


def test_defaults_match_interfaces() -> None:
    """The frozen defaults from INTERFACES.md."""
    cfg = BadResearchConfig()
    assert cfg.vault_root == Path.home() / ".bad-research"
    assert cfg.model_tiers == {
        "triage": "claude-haiku-4-5",
        "work": "claude-sonnet-4-6",
        "heavy": "claude-opus-4-7",
    }
    assert cfg.embed_model == "embed-v3"
    assert cfg.rerank_model == "rerank-v3.5"
    assert cfg.budget_usd is None
    assert cfg.cheap is False


def test_load_returns_defaults_when_no_env_no_toml(tmp_path: Path) -> None:
    cfg = BadResearchConfig.load(config_path=tmp_path / "missing.toml")
    assert cfg.budget_usd is None
    assert cfg.cheap is False
    assert cfg.embed_model == "embed-v3"


def test_env_overrides_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BAD_RESEARCH_BUDGET_USD", "12.50")
    monkeypatch.setenv("BAD_RESEARCH_CHEAP", "1")
    cfg = BadResearchConfig.load(config_path=tmp_path / "missing.toml")
    assert cfg.budget_usd == 12.50
    assert cfg.cheap is True


def test_toml_overrides_default(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        "[bad-research]\n"
        "budget_usd = 7.0\n"
        "cheap = true\n"
        'embed_model = "embed-english-v3.0"\n'
        'rerank_model = "bge-reranker-v2-m3"\n'
        'vault_root = "/tmp/custom-vault"\n'
    )
    cfg = BadResearchConfig.load(config_path=toml)
    assert cfg.budget_usd == 7.0
    assert cfg.cheap is True
    assert cfg.embed_model == "embed-english-v3.0"
    assert cfg.rerank_model == "bge-reranker-v2-m3"
    assert cfg.vault_root == Path("/tmp/custom-vault")


def test_env_beats_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text("[bad-research]\nbudget_usd = 7.0\ncheap = false\n")
    monkeypatch.setenv("BAD_RESEARCH_BUDGET_USD", "99.0")
    monkeypatch.setenv("BAD_RESEARCH_CHEAP", "true")
    cfg = BadResearchConfig.load(config_path=toml)
    assert cfg.budget_usd == 99.0  # env wins
    assert cfg.cheap is True       # env wins


def test_cheap_falsey_env_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for falsey in ("0", "false", "False", "no", ""):
        monkeypatch.setenv("BAD_RESEARCH_CHEAP", falsey)
        cfg = BadResearchConfig.load(config_path=tmp_path / "missing.toml")
        assert cfg.cheap is False, f"{falsey!r} should parse falsey"
```

- [ ] **Task 1.3 — Run the config test; expect FAIL.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_config/test_config.py -q
```

Expected: a collection/import error — `ModuleNotFoundError: No module named 'bad_research.config'` (the module does not exist yet). The run ends with `errors` / `no tests ran` (non-zero exit).

- [ ] **Task 1.4 — Write the minimal `config.py`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/config.py` with exactly:

```python
"""Bad Research top-level configuration.

Distinct from hyperresearch's per-vault `core/config.py:VaultConfig` (kept verbatim
in the fork). This holds the cross-cutting knobs: provider keys (read lazily from
env), the model-tier map, budget caps, and thresholds. Precedence: env > TOML > default.

Default TOML location: ~/.config/bad-research/config.toml (XDG user config).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def default_config_path() -> Path:
    """The user-side config file location (~/.config/bad-research/config.toml)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "bad-research" / "config.toml"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BadResearchConfig:
    vault_root: Path = field(default_factory=lambda: Path.home() / ".bad-research")
    model_tiers: dict = field(
        default_factory=lambda: {
            "triage": "claude-haiku-4-5",
            "work": "claude-sonnet-4-6",
            "heavy": "claude-opus-4-7",
        }
    )
    embed_model: str = "embed-v3"          # Cohere
    rerank_model: str = "rerank-v3.5"      # Cohere; "bge-reranker-v2-m3" offline
    budget_usd: float | None = None        # None = uncapped
    cheap: bool = False                    # demote heavy->work
    # provider keys read from env / ~/.config/bad-research/config.toml at call sites

    @classmethod
    def load(cls, config_path: Path | None = None) -> BadResearchConfig:
        """Build a config with precedence env > TOML > dataclass default."""
        if config_path is None:
            config_path = default_config_path()

        cfg = cls()

        # --- TOML layer (overrides defaults) ---
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            section = data.get("bad-research", {})
            if "vault_root" in section:
                cfg.vault_root = Path(section["vault_root"])
            if "model_tiers" in section:
                cfg.model_tiers = dict(section["model_tiers"])
            if "embed_model" in section:
                cfg.embed_model = section["embed_model"]
            if "rerank_model" in section:
                cfg.rerank_model = section["rerank_model"]
            if "budget_usd" in section:
                cfg.budget_usd = float(section["budget_usd"])
            if "cheap" in section:
                cfg.cheap = bool(section["cheap"])

        # --- env layer (overrides TOML) ---
        if (v := os.environ.get("BAD_RESEARCH_VAULT_ROOT")) is not None:
            cfg.vault_root = Path(v)
        if (v := os.environ.get("BAD_RESEARCH_EMBED_MODEL")) is not None:
            cfg.embed_model = v
        if (v := os.environ.get("BAD_RESEARCH_RERANK_MODEL")) is not None:
            cfg.rerank_model = v
        if (v := os.environ.get("BAD_RESEARCH_BUDGET_USD")) is not None:
            cfg.budget_usd = float(v)
        if (v := os.environ.get("BAD_RESEARCH_CHEAP")) is not None:
            cfg.cheap = _parse_bool(v)

        return cfg
```

- [ ] **Task 1.5 — Run the config test; expect PASS.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_config/test_config.py -q
```

Expected: `6 passed` (last line shows `6 passed in <time>s`).

- [ ] **Task 1.6 — Commit config.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/src/bad_research/config.py \
        ultimate-research/bad-research/tests/__init__.py \
        ultimate-research/bad-research/tests/conftest.py \
        ultimate-research/bad-research/tests/test_config && \
git commit -m "feat(bad-research): BadResearchConfig — env>TOML>default precedence

Per INTERFACES.md: model_tiers, embed/rerank model, budget_usd, cheap.
XDG config at ~/.config/bad-research/config.toml. Plan 01 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Phase 2 — `llm/base.py` (the LLMProvider seam)

- [ ] **Task 2.1 — Write the failing base-seam test.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_llm/__init__.py` as an empty file (single newline). Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_llm/test_base.py` with exactly:

```python
"""Tests for the LLMProvider seam types and factory."""

from __future__ import annotations

import pytest

from bad_research.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    get_llm_provider,
)


def test_llmmessage_shape() -> None:
    m = LLMMessage(role="user", content="hello")
    assert m.role == "user"
    assert m.content == "hello"
    # content may also be a list[dict] (multimodal / tool blocks)
    m2 = LLMMessage(role="assistant", content=[{"type": "text", "text": "hi"}])
    assert isinstance(m2.content, list)


def test_llmresponse_shape() -> None:
    r = LLMResponse(
        text="answer",
        tool_calls=[],
        usage={"input_tokens": 10, "output_tokens": 5, "cache_read": 0, "cache_write": 0},
        model="claude-opus-4-7",
    )
    assert r.text == "answer"
    assert r.tool_calls == []
    assert r.usage["input_tokens"] == 10
    assert r.model == "claude-opus-4-7"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("does-not-exist")


def test_protocol_is_runtime_checkable() -> None:
    """A duck-typed object satisfying the surface is an LLMProvider instance."""

    class _Fake:
        name = "fake"

        def complete(self, messages, *, tier, tools=None, cache=False,
                     max_tokens=4096, temperature=0.1):
            return LLMResponse(text="", tool_calls=[], usage={}, model="fake")

    assert isinstance(_Fake(), LLMProvider)
```

- [ ] **Task 2.2 — Run the base test; expect FAIL.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_llm/test_base.py -q
```

Expected: `ModuleNotFoundError: No module named 'bad_research.llm'` (collection error, non-zero exit).

- [ ] **Task 2.3 — Write `llm/base.py`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/llm/__init__.py` with exactly:

```python
"""LLMProvider seam — Anthropic-first behind a thin Protocol (SPEC §3, dossier 06 A6)."""

from __future__ import annotations

from bad_research.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    ModelTier,
    get_llm_provider,
)

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "ModelTier",
    "get_llm_provider",
]
```

Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/llm/base.py` with exactly:

```python
"""Base types and factory for the LLMProvider seam.

Contract is frozen in ultimate-research/INTERFACES.md. The default impl is
AnthropicProvider (llm/anthropic.py); LiteLLMProvider is an optional future escape
hatch (dossier 06 A6). The factory keeps SDK imports lazy so optional deps stay optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

# triage -> Haiku, work -> Sonnet, heavy -> Opus (resolved via config.model_tiers).
ModelTier = Literal["triage", "work", "heavy"]


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # [] if none
    usage: dict = field(default_factory=dict)  # {input_tokens, output_tokens, cache_read, cache_write}
    model: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: ModelTier,
        tools: list[dict] | None = None,
        cache: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse: ...


def get_llm_provider(name: str = "anthropic", **kwargs) -> LLMProvider:
    """Load an LLM provider by name. Defaults to Anthropic (the GA backend)."""
    if name == "anthropic":
        from bad_research.llm.anthropic import AnthropicProvider

        return AnthropicProvider(**kwargs)

    raise ValueError(f"Unknown LLM provider: {name!r}. Available: anthropic")
```

- [ ] **Task 2.4 — Run the base test; expect PASS.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_llm/test_base.py -q
```

Expected: `4 passed`. (The factory dispatch to `anthropic` is exercised in Phase 3; `test_unknown_provider_raises` passes now because the `does-not-exist` branch raises before any import.)

- [ ] **Task 2.5 — Commit the LLM seam.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/src/bad_research/llm \
        ultimate-research/bad-research/tests/test_llm && \
git commit -m "feat(bad-research): LLMProvider seam — Protocol + LLMMessage/LLMResponse + factory

EP-D (dossier 01 §3.4): the model-backend extension point hyperresearch lacks.
Signatures verbatim from INTERFACES.md. Plan 01 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Phase 3 — `llm/anthropic.py` (AnthropicProvider: tiers, --cheap, cache_control)

- [ ] **Task 3.1 — Write the failing AnthropicProvider test.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_llm/test_anthropic.py` with exactly:

```python
"""Tests for AnthropicProvider — mocks the anthropic SDK.

Mirrors hyperresearch's test_exa_provider.py pattern: patch the SDK class at its
source module so the provider's lazy import picks up the mock. No network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.llm.base import LLMMessage, get_llm_provider


def _make_message_response(
    *,
    text: str = "the answer",
    model: str = "claude-opus-4-7",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_read: int = 0,
    cache_write: int = 0,
) -> SimpleNamespace:
    """Shape an anthropic Messages API response object (duck-typed)."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )


def _patch_sdk(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    """Patch `anthropic.Anthropic` at the source module the provider imports from."""
    import anthropic

    factory = MagicMock(return_value=client)
    monkeypatch.setattr(anthropic, "Anthropic", factory)


def _provider(monkeypatch: pytest.MonkeyPatch, client: MagicMock):
    from bad_research.llm.anthropic import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    return AnthropicProvider()


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.llm.anthropic import AnthropicProvider

    # _clear_provider_keys autouse fixture already removed ANTHROPIC_API_KEY.
    _patch_sdk(monkeypatch, MagicMock())
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_factory_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = get_llm_provider("anthropic")
    assert prov.name == "anthropic"


def test_tier_to_model_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(model="claude-haiku-4-5")
    prov = _provider(monkeypatch, client)

    assert prov._resolve_model("triage") == "claude-haiku-4-5"
    assert prov._resolve_model("work") == "claude-sonnet-4-6"
    assert prov._resolve_model("heavy") == "claude-opus-4-7"


def test_cheap_demotes_heavy_to_work(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.config import BadResearchConfig
    from bad_research.llm.anthropic import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = AnthropicProvider(config=BadResearchConfig(cheap=True))

    assert prov._resolve_model("heavy") == "claude-sonnet-4-6"  # demoted
    assert prov._resolve_model("work") == "claude-sonnet-4-6"   # unchanged
    assert prov._resolve_model("triage") == "claude-haiku-4-5"  # unchanged


def test_complete_returns_llmresponse(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(
        text="grounded answer", model="claude-sonnet-4-6",
        input_tokens=42, output_tokens=7, cache_read=30, cache_write=12,
    )
    prov = _provider(monkeypatch, client)

    resp = prov.complete(
        [LLMMessage(role="user", content="Q")],
        tier="work",
    )
    assert resp.text == "grounded answer"
    assert resp.model == "claude-sonnet-4-6"
    assert resp.usage == {
        "input_tokens": 42, "output_tokens": 7, "cache_read": 30, "cache_write": 12,
    }
    assert resp.tool_calls == []


def test_system_messages_routed_to_system_param(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    prov.complete(
        [
            LLMMessage(role="system", content="You are bad."),
            LLMMessage(role="user", content="hello"),
        ],
        tier="heavy",
    )
    _, kwargs = client.messages.create.call_args
    # system goes to the top-level `system` param, NOT into messages[]
    assert any(b["text"] == "You are bad." for b in kwargs["system"])
    assert all(m["role"] != "system" for m in kwargs["messages"])
    assert kwargs["messages"][0]["role"] == "user"


def test_cache_stamps_control_on_system_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    tools = [
        {"name": "search", "description": "s", "input_schema": {"type": "object"}},
        {"name": "fetch", "description": "f", "input_schema": {"type": "object"}},
    ]
    prov.complete(
        [
            LLMMessage(role="system", content="STABLE PREFIX"),
            LLMMessage(role="user", content="q"),
        ],
        tier="heavy",
        tools=tools,
        cache=True,
    )
    _, kwargs = client.messages.create.call_args

    # cache_control stamped on the LAST system block
    assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
    # cache_control stamped on the LAST tool only (1 breakpoint for the tools block)
    assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kwargs["tools"][0]


def test_no_cache_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    prov.complete(
        [LLMMessage(role="system", content="P"), LLMMessage(role="user", content="q")],
        tier="work",
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        cache=False,
    )
    _, kwargs = client.messages.create.call_args
    assert all("cache_control" not in b for b in kwargs["system"])
    assert all("cache_control" not in t for t in kwargs["tools"])


def test_tool_calls_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    resp_obj = _make_message_response(text="")
    resp_obj.content = [
        SimpleNamespace(type="text", text="let me search"),
        SimpleNamespace(
            type="tool_use", id="tu_1", name="search", input={"query": "x"}
        ),
    ]
    client.messages.create.return_value = resp_obj
    prov = _provider(monkeypatch, client)

    resp = prov.complete([LLMMessage(role="user", content="q")], tier="work")
    assert resp.text == "let me search"
    assert resp.tool_calls == [{"id": "tu_1", "name": "search", "input": {"query": "x"}}]
```

- [ ] **Task 3.2 — Run the AnthropicProvider test; expect FAIL.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_llm/test_anthropic.py -q
```

Expected: `ModuleNotFoundError: No module named 'bad_research.llm.anthropic'` (collection error, non-zero exit).

- [ ] **Task 3.3 — Write `llm/anthropic.py`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/llm/anthropic.py` with exactly:

```python
"""AnthropicProvider — the default LLM backend.

Resolves model TIERS (triage/work/heavy) to concrete Claude IDs via config, applies
the --cheap demotion (heavy->work), and stamps Anthropic prompt-cache cache_control
breakpoints on the stable system+tools prefix when cache=True. This is the single
cheapest cost win in the product (dossier 09 A1.2): the 2nd..Nth spawn of a worker
type within a run pays ~10% of input-token cost on the cached prefix.

Anthropic allows <=4 cache_control breakpoints per request; we use 2 (last system
block + last tool). The CALLER is responsible for keeping the system+tools prefix
byte-identical across spawns so the cache actually hits; this provider only stamps
the markers.
"""

from __future__ import annotations

import os
from typing import Any

from bad_research.config import BadResearchConfig
from bad_research.llm.base import LLMMessage, LLMResponse, ModelTier


class AnthropicProvider:
    """LLMProvider backed by the Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        config: BadResearchConfig | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - hard dep, defensive
            raise ImportError(
                "anthropic provider requires: pip install anthropic"
            ) from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it or put it in "
                "~/.config/bad-research/config.toml."
            )

        self._config = config or BadResearchConfig()
        self._client = anthropic.Anthropic(api_key=key)

    def _resolve_model(self, tier: ModelTier) -> str:
        """tier -> concrete model ID, applying the --cheap heavy->work demotion."""
        tiers = self._config.model_tiers
        if tier == "heavy" and self._config.cheap:
            return tiers["work"]
        return tiers[tier]

    @staticmethod
    def _split_messages(
        messages: list[LLMMessage],
    ) -> tuple[list[dict], list[dict]]:
        """Split into Anthropic's top-level `system` blocks and the `messages[]` array.

        Anthropic does NOT accept role="system" inside messages[]; system text goes
        to the top-level `system` param as a list of text blocks.
        """
        system_blocks: list[dict] = []
        convo: list[dict] = []
        for m in messages:
            if m.role == "system":
                text = m.content if isinstance(m.content, str) else ""
                system_blocks.append({"type": "text", "text": text})
            else:
                # tool role maps to a user turn carrying tool_result content
                role = "user" if m.role == "tool" else m.role
                convo.append({"role": role, "content": m.content})
        return system_blocks, convo

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: ModelTier,
        tools: list[dict] | None = None,
        cache: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        model = self._resolve_model(tier)
        system_blocks, convo = self._split_messages(messages)
        tools = list(tools) if tools else []

        if cache:
            # Stamp the stable prefix: last system block + last tool definition.
            # (<=4 breakpoints allowed; 2 used.) The cached prefix must be
            # byte-identical across spawns — that's the caller's job.
            if system_blocks:
                system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}
            if tools:
                tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": convo,
        }
        if system_blocks:
            kwargs["system"] = system_blocks
        if tools:
            kwargs["tools"] = tools

        resp = self._client.messages.create(**kwargs)
        return self._to_llmresponse(resp)

    @staticmethod
    def _to_llmresponse(resp: Any) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )

        usage_obj = resp.usage
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_read": getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(usage_obj, "cache_creation_input_tokens", 0) or 0,
        }

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=usage,
            model=getattr(resp, "model", ""),
        )
```

- [ ] **Task 3.4 — Run the AnthropicProvider test; expect PASS.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_llm/test_anthropic.py -q
```

Expected: `9 passed`.

- [ ] **Task 3.5 — Commit AnthropicProvider.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/src/bad_research/llm/anthropic.py \
        ultimate-research/bad-research/tests/test_llm/test_anthropic.py && \
git commit -m "feat(bad-research): AnthropicProvider — tiers, --cheap demotion, cache_control

tier->model resolution; heavy->work under --cheap; ephemeral cache_control on the
stable system+tools prefix (dossier 09 A1.2, ~10x input-cost cut on repeat spawns).
system messages routed to the top-level system param. Plan 01 Phase 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Phase 4 — `embed/base.py` + `embed/cohere.py` (the EmbedProvider seam)

- [ ] **Task 4.1 — Write the failing embed-base test.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_embed/__init__.py` as an empty file (single newline). Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_embed/test_base.py` with exactly:

```python
"""Tests for the EmbedProvider seam types and factory."""

from __future__ import annotations

import pytest

from bad_research.embed.base import EmbedProvider, get_embed_provider


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown embed provider"):
        get_embed_provider("does-not-exist")


def test_protocol_is_runtime_checkable() -> None:
    class _Fake:
        name = "fake"
        dim = 8

        def embed(self, texts, *, input_type):
            return [[0.0] * self.dim for _ in texts]

    assert isinstance(_Fake(), EmbedProvider)
```

- [ ] **Task 4.2 — Run the embed-base test; expect FAIL.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_embed/test_base.py -q
```

Expected: `ModuleNotFoundError: No module named 'bad_research.embed'` (collection error, non-zero exit).

- [ ] **Task 4.3 — Write `embed/base.py`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/embed/__init__.py` with exactly:

```python
"""EmbedProvider seam — API embedders only, asymmetric document/query (SPEC §3, §7)."""

from __future__ import annotations

from bad_research.embed.base import EmbedProvider, get_embed_provider

__all__ = ["EmbedProvider", "get_embed_provider"]
```

Then create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/embed/base.py` with exactly:

```python
"""Base Protocol and factory for the EmbedProvider seam.

API providers only (no self-hosted GPU — SPEC decision #5: an idle GPU doesn't
amortize at single-user scale). Default impl: CohereEmbedProvider (embed-v3, dim 1024).
Asymmetric input_type: documents embedded at index time, queries at retrieval time.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class EmbedProvider(Protocol):
    name: str
    dim: int

    def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"],
    ) -> list[list[float]]: ...


def get_embed_provider(name: str = "cohere", **kwargs) -> EmbedProvider:
    """Load an embed provider by name. Defaults to Cohere (the GA embedder)."""
    if name == "cohere":
        from bad_research.embed.cohere import CohereEmbedProvider

        return CohereEmbedProvider(**kwargs)

    raise ValueError(f"Unknown embed provider: {name!r}. Available: cohere")
```

- [ ] **Task 4.4 — Run the embed-base test; expect PASS.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_embed/test_base.py -q
```

Expected: `2 passed`.

- [ ] **Task 4.5 — Write the failing Cohere test.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/tests/test_embed/test_cohere.py` with exactly:

```python
"""Tests for CohereEmbedProvider — mocks the cohere SDK (ClientV2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.embed.base import get_embed_provider


def _make_embed_response(vectors: list[list[float]]) -> SimpleNamespace:
    """Shape a cohere v2 embed response: .embeddings.float is a list of vectors."""
    return SimpleNamespace(embeddings=SimpleNamespace(float=vectors))


def _patch_sdk(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    import cohere

    factory = MagicMock(return_value=client)
    monkeypatch.setattr(cohere, "ClientV2", factory)


def _provider(monkeypatch: pytest.MonkeyPatch, client: MagicMock):
    from bad_research.embed.cohere import CohereEmbedProvider

    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    return CohereEmbedProvider()


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.embed.cohere import CohereEmbedProvider

    _patch_sdk(monkeypatch, MagicMock())
    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        CohereEmbedProvider()


def test_name_and_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = _provider(monkeypatch, MagicMock())
    assert prov.name == "cohere"
    assert prov.dim == 1024


def test_factory_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = get_embed_provider("cohere")
    assert prov.name == "cohere"


def test_embed_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.1, 0.2], [0.3, 0.4]])
    prov = _provider(monkeypatch, client)

    out = prov.embed(["a", "b"], input_type="document")
    assert out == [[0.1, 0.2], [0.3, 0.4]]


def test_document_input_type_maps_to_search_document(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.0]])
    prov = _provider(monkeypatch, client)

    prov.embed(["doc"], input_type="document")
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "search_document"
    assert kwargs["model"] == "embed-v3"
    assert kwargs["texts"] == ["doc"]


def test_query_input_type_maps_to_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.0]])
    prov = _provider(monkeypatch, client)

    prov.embed(["what is x"], input_type="query")
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "search_query"
```

- [ ] **Task 4.6 — Run the Cohere test; expect FAIL.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_embed/test_cohere.py -q
```

Expected: `ModuleNotFoundError: No module named 'bad_research.embed.cohere'` (collection error, non-zero exit).

- [ ] **Task 4.7 — Write `embed/cohere.py`.** Create `/Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research/src/bad_research/embed/cohere.py` with exactly:

```python
"""CohereEmbedProvider — the default API embedder (embed-v3, dim 1024).

Asymmetric input_type per SPEC §7: "document" at index time, "query" at retrieval
time. Maps to Cohere's search_document / search_query input types. Uses the v2 client
(cohere.ClientV2.embed) with embedding_types=["float"].
"""

from __future__ import annotations

import os
from typing import Literal

# Cohere embed-v3 family is 1024-dim (INTERFACES.md frozen constant; dossier 02).
_DIM = 1024

_INPUT_TYPE_MAP = {
    "document": "search_document",
    "query": "search_query",
}


class CohereEmbedProvider:
    """EmbedProvider backed by the Cohere embeddings API."""

    name = "cohere"
    dim = _DIM

    def __init__(self, api_key: str | None = None, model: str = "embed-v3") -> None:
        try:
            import cohere
        except ImportError as exc:
            raise ImportError(
                'cohere provider requires: pip install "bad-research[cohere]"'
            ) from exc

        key = api_key or os.environ.get("COHERE_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "COHERE_API_KEY is not set. Get a key at "
                "https://dashboard.cohere.com/api-keys and export it."
            )

        self._model = model
        self._client = cohere.ClientV2(api_key=key)

    def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"],
    ) -> list[list[float]]:
        cohere_input_type = _INPUT_TYPE_MAP[input_type]
        resp = self._client.embed(
            texts=texts,
            model=self._model,
            input_type=cohere_input_type,
            embedding_types=["float"],
        )
        return resp.embeddings.float
```

- [ ] **Task 4.8 — Run the Cohere test; expect PASS.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/test_embed/test_cohere.py -q
```

Expected: `6 passed`.

- [ ] **Task 4.9 — Commit the embed seam.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/src/bad_research/embed \
        ultimate-research/bad-research/tests/test_embed && \
git commit -m "feat(bad-research): EmbedProvider seam + CohereEmbedProvider (embed-v3, dim 1024)

Protocol + factory; asymmetric document/query -> search_document/search_query.
API embedder only (SPEC decision #5: no GPU at single-user scale). Plan 01 Phase 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Phase 5 — Full-suite verification

- [ ] **Task 5.1 — Run the entire Plan-01 test suite; expect all green.** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -m pytest tests/ -q
```

Expected: `27 passed` (6 config + 4 llm/base + 9 llm/anthropic + 2 embed/base + 6 embed/cohere). If a count differs, a phase regressed — fix before proceeding (use superpowers:systematic-debugging).

- [ ] **Task 5.2 — Verify the public seams import cleanly (the contract Plans 02-08 consume).** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms/ultimate-research/bad-research && \
python -c "
from bad_research.config import BadResearchConfig
from bad_research.llm import LLMProvider, LLMMessage, LLMResponse, ModelTier, get_llm_provider
from bad_research.embed import EmbedProvider, get_embed_provider
c = BadResearchConfig()
assert c.model_tiers['heavy'] == 'claude-opus-4-7'
assert c.model_tiers['work'] == 'claude-sonnet-4-6'
assert c.model_tiers['triage'] == 'claude-haiku-4-5'
print('OK: seams importable; tier map frozen-correct')
"
```

Expected output: `OK: seams importable; tier map frozen-correct`.

- [ ] **Task 5.3 — Final commit (full suite green).** Run exactly:

```bash
cd /Users/seventyleven/Desktop/researchfms && \
git add ultimate-research/bad-research/tests/test_embed/test_base.py \
        ultimate-research/bad-research/tests/test_llm/test_base.py && \
git commit -m "test(bad-research): Plan 01 seams green — 27 tests (config, llm, embed)

Foundation complete: LLMProvider+AnthropicProvider, EmbedProvider+Cohere,
BadResearchConfig. The contract Plans 02-08 build on. Plan 01 Phase 5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" || echo "nothing new to commit (test files already committed in their phases)"
```

(The `|| echo` guards the case where `test_base.py` files were already staged in their own phases; the final commit then has nothing to add and the message just notes that.)

---

## Done criteria

- `pip install -e '.[dev]'` succeeds; `bad --version` and `badr --version` both print `bad-research v0.1.0`.
- `python -m pytest tests/ -q` → `27 passed`, zero network calls (SDKs mocked).
- The public interfaces below import and match `INTERFACES.md` verbatim.
- Every claim labeled: all code here is **DESIGNED** (our build) implementing the **frozen** INTERFACES.md contract; the fork-pattern choices (lazy import, env-key `RuntimeError`, SDK-mock-at-source) are **KNOWN** from hyperresearch's own `web/exa_provider.py` + `tests/test_web/test_exa_provider.py`.

## Public interfaces Plan 01 exposes (must match INTERFACES.md)

```python
# bad_research.config
@dataclass
class BadResearchConfig:
    vault_root: Path = Path.home() / ".bad-research"
    model_tiers: dict   # {"triage":"claude-haiku-4-5","work":"claude-sonnet-4-6","heavy":"claude-opus-4-7"}
    embed_model: str = "embed-v3"
    rerank_model: str = "rerank-v3.5"
    budget_usd: float | None = None
    cheap: bool = False
    @classmethod
    def load(cls, config_path: Path | None = None) -> BadResearchConfig: ...

# bad_research.llm  (base.py)
ModelTier = Literal["triage", "work", "heavy"]
@dataclass
class LLMMessage: role: Literal["system","user","assistant","tool"]; content: str | list[dict]
@dataclass
class LLMResponse: text: str; tool_calls: list[dict]; usage: dict; model: str
class LLMProvider(Protocol):
    name: str
    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1) -> LLMResponse: ...
def get_llm_provider(name="anthropic", **kwargs) -> LLMProvider: ...
# AnthropicProvider(api_key=None, config=None); ._resolve_model(tier)->str

# bad_research.embed  (base.py)
class EmbedProvider(Protocol):
    name: str; dim: int
    def embed(self, texts, *, input_type: Literal["document","query"]) -> list[list[float]]: ...
def get_embed_provider(name="cohere", **kwargs) -> EmbedProvider: ...
# CohereEmbedProvider(api_key=None, model="embed-v3"); name="cohere", dim=1024
```

All signatures match INTERFACES.md §"Seam signatures" and §"Config" verbatim.
