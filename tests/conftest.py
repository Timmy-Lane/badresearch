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
