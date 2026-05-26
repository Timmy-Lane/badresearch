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


# ── Task 2: lean base + optional-extras groups ───────────────────────────────
# Heavy deps that MUST NOT be in the base install (keep zero-key/lean small).
HEAVY_FORBIDDEN_IN_BASE = {
    "cohere",
    "tavily-python",
    "exa-py",
    "crawl4ai",
    "Crawl4AI",
    "browser-use",
    "sentence-transformers",
    "torch",
    "firecrawl-py",
    "agentql",
    "playwright",
    "FlagEmbedding",
    "stagehand",
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
    leaked = base & {n.lower() for n in HEAVY_FORBIDDEN_IN_BASE} | (base & HEAVY_FORBIDDEN_IN_BASE)
    assert not leaked, f"heavy deps leaked into base: {leaked}"
    # base must still carry the zero-key essentials
    assert {"anthropic", "lancedb", "httpx", "typer", "pymupdf"} <= base


def test_base_has_no_torch_or_playwright(pp):
    base = pp["project"]["dependencies"]
    assert all("torch" not in d and "playwright" not in d for d in base)


def test_extras_groups_exist(pp):
    extras = pp["project"]["optional-dependencies"]
    for group in ("search", "browse", "grounding", "mcp", "all", "dev"):
        assert group in extras, f"missing extras group: {group}"


def test_search_extra_contents(pp):
    search = _names(pp["project"]["optional-dependencies"]["search"])
    assert {"tavily-python", "exa-py", "cohere"} <= search


def test_browse_extra_contents(pp):
    browse = _names(pp["project"]["optional-dependencies"]["browse"])
    assert {"crawl4ai", "browser-use"} <= {n.lower() for n in browse}


def test_grounding_extra_contents(pp):
    grounding = _names(pp["project"]["optional-dependencies"]["grounding"])
    assert "sentence-transformers" in grounding  # NLI verifier + BGE reranker


def test_all_composes_extras(pp):
    all_dep = pp["project"]["optional-dependencies"]["all"]
    # `[all]` references the package's own extras, not a flat re-list.
    assert any("bad-research[" in d for d in all_dep)
