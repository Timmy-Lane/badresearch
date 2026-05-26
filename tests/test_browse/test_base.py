"""Contract tests: BrowseProvider/ExtractProvider Protocols (kept) + keyless factories."""

from __future__ import annotations

import bad_research.browse.base as base
from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)


def test_browse_provider_protocol_is_runtime_checkable() -> None:
    class Ok:
        name = "x"
        def browse(self, url, instruction, *, max_steps=12, variables=None, replay_key=None):
            ...
    assert isinstance(Ok(), BrowseProvider)


def test_extract_provider_protocol_is_runtime_checkable() -> None:
    class Ok:
        name = "x"
        def extract(self, source, schema, instruction=""):
            return {}
    assert isinstance(Ok(), ExtractProvider)


def test_default_browse_provider_is_agent_browser_when_cli_present(monkeypatch) -> None:
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": True)
    prov = get_browse_provider()
    assert prov is not None
    assert prov.name == "agent-browser"


def test_browse_provider_none_when_cli_absent(monkeypatch) -> None:
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": False)
    assert get_browse_provider() is None
    assert get_browse_provider("agent-browser") is None


def test_extract_provider_llm_default_always_constructible() -> None:
    prov = get_extract_provider("llm")
    assert prov is not None and prov.name == "llm"
    assert get_extract_provider() is not None      # default == llm


def test_extract_provider_aql() -> None:
    prov = get_extract_provider("aql")
    assert prov is not None and prov.name == "aql"


def test_unknown_provider_returns_none() -> None:
    assert get_browse_provider("browserbase") is None     # keyed backend gone
    assert get_extract_provider("agentql") is None         # keyed backend gone
