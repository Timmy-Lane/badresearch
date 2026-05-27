"""`uv build` produces a wheel whose metadata is keyless (no removed providers)."""

from __future__ import annotations

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
def wheel_contents(tmp_path_factory) -> dict[str, str]:
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
        ep_name = next(
            (n for n in zf.namelist() if n.endswith("entry_points.txt")), None
        )
        return {
            "metadata": zf.read(meta_name).decode("utf-8"),
            "entry_points": zf.read(ep_name).decode("utf-8") if ep_name else "",
        }


@pytest.fixture(scope="module")
def wheel_metadata(wheel_contents) -> str:
    return wheel_contents["metadata"]


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


def test_wheel_entry_points(wheel_contents):
    # The wheel must declare the `bad`/`badr` console scripts (entry_points.txt).
    # METADATA does not carry entry points; the fixture read entry_points.txt.
    assert sys.version_info >= (3, 11)
    ep = wheel_contents["entry_points"]
    assert "bad = bad_research.cli:app" in ep
    assert "badr = bad_research.cli:app" in ep
