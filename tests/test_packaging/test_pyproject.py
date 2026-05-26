"""pyproject.toml metadata + entry-point resolution + lean-base / extras groups."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # .../badresearch/
PYPROJECT = ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pp() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


# ── Task 1: metadata + entry points ──────────────────────────────────────────
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


# Keyed / paid SDKs + the GPU stack that MUST NOT be in the keyless base.
HEAVY_FORBIDDEN_IN_BASE = {
    "cohere",
    "tavily-python",
    "exa-py",
    "browser-use",
    "agentql",
    "stagehand",
    "firecrawl-py",
    "sentence-transformers",
    "torch",
    "lancedb",
    "pyarrow",
    "playwright",
    "FlagEmbedding",
}


def _names(dep_list: list[str]) -> set[str]:
    out = set()
    for d in dep_list:
        name = d.split(";")[0].strip()
        for sep in (">=", "==", "~=", "<", ">", "[", " "):
            name = name.split(sep)[0]
        out.add(name.strip())
    return out


def test_base_install_is_lean(pp):
    base = _names(pp["project"]["dependencies"])
    leaked = (base & {n.lower() for n in HEAVY_FORBIDDEN_IN_BASE}) | (base & HEAVY_FORBIDDEN_IN_BASE)
    assert not leaked, f"keyed/heavy deps leaked into base: {leaked}"
    # base carries the keyless essentials (numpy stays: grounding/nli.py imports it directly)
    assert {"anthropic", "httpx", "typer", "pymupdf", "crawl4ai", "ddgs", "trafilatura", "numpy"} <= base


def test_base_has_no_torch_lancedb_or_keyed_sdk(pp):
    base = pp["project"]["dependencies"]
    for forbidden in ("torch", "lancedb", "pyarrow", "cohere", "tavily", "exa-py", "playwright"):
        assert all(forbidden not in d for d in base), f"{forbidden} leaked into base"


def test_search_extra_is_gone(pp):
    extras = pp["project"]["optional-dependencies"]
    assert "search" not in extras, "the [search] extra must be deleted (pure keyless)"


def test_extras_groups_exist(pp):
    extras = pp["project"]["optional-dependencies"]
    for group in ("browse", "local", "mcp", "all", "dev"):
        assert group in extras, f"missing extras group: {group}"


def test_browse_extra_is_playwright_only(pp):
    browse = _names(pp["project"]["optional-dependencies"]["browse"])
    assert "playwright" in browse
    for gone in ("browser-use", "agentql", "crawl4ai"):
        assert gone not in {n.lower() for n in browse}


def test_local_extra_holds_the_neural_stack(pp):
    local = _names(pp["project"]["optional-dependencies"]["local"])
    assert {"torch", "sentence-transformers", "lancedb", "pyarrow"} <= local


def test_all_composes_extras(pp):
    all_dep = pp["project"]["optional-dependencies"]["all"]
    assert any("bad-research[" in d for d in all_dep)
