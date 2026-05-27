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
