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
