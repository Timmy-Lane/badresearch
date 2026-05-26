"""BrowseProvider / ExtractProvider Protocols + availability-gated factories.

Both Protocols match ultimate-research/INTERFACES.md verbatim. Factories return None
(never raise) when an optional backend's dependency or API key is unavailable — the
ladder treats None as "this tier is not available" and stops at the highest tier it can.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bad_research.web.base import WebResult


@runtime_checkable
class BrowseProvider(Protocol):
    """Tier-3: LLM-driven, multi-step browse. Returns a WebResult like any provider,
    but reaches it through an agent loop (login, paginate, click, dismiss modals)."""

    name: str

    def browse(
        self,
        url: str,
        instruction: str,
        *,
        max_steps: int = 12,
        variables: dict | None = None,
        replay_key: str | None = None,
    ) -> WebResult: ...


@runtime_checkable
class ExtractProvider(Protocol):
    """Tier-2: schema-driven typed extraction. Returns a dict conforming to `schema`;
    missing fields are null — never fabricated."""

    name: str

    def extract(
        self,
        source: str | WebResult,
        schema: dict[str, Any] | str,
        instruction: str = "",
    ) -> dict: ...


def get_extract_provider(name: str | None = None) -> ExtractProvider | None:
    """Resolve an ExtractProvider. Default = the zero-dep LLM extractor (host model,
    always constructible). `aql` is built in KR-4; unknown/unavailable -> None."""
    if name in (None, "llm"):
        from bad_research.browse.extract_llm import LLMExtractProvider

        return LLMExtractProvider()

    if name == "aql":
        # KR-4 ships browse/aql.py::AqlExtractProvider (ported AgentQL parser +
        # host-model resolver). Until then this rung is simply unavailable.
        return None

    return None


def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    """Resolve a keyless BrowseProvider. Default = the local agent-browser CLI
    (built in KR-4: browse/agent_browser.py::AgentBrowserProvider). Until KR-4
    lands, the backend is unavailable -> return None (graceful: the ladder keeps
    the best lower-tier result). No API key, no cloud SDK — keyless only."""
    if name in (None, "agent-browser"):
        try:
            from bad_research.browse.agent_browser import (  # type: ignore[import-not-found]
                AgentBrowserProvider,
            )
        except ImportError:
            return None
        return AgentBrowserProvider()

    return None
