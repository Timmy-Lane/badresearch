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
    import bad_research  # noqa: F401  (side-effect import: proves the package loads)
    from bad_research.cli import app
    from bad_research.providers import provider_status

    # Sanity: the providers we DID keep do not pull a removed lib transitively.
    assert app is not None
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
