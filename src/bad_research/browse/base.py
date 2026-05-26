"""BrowseProvider / ExtractProvider Protocols + availability-gated factories.

Both Protocols match ultimate-research/INTERFACES.md verbatim. Factories return None
(never raise) when an optional backend's dependency or API key is unavailable — the
ladder treats None as "this tier is not available" and stops at the highest tier it can.
"""

from __future__ import annotations

import os
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
    """Resolve an ExtractProvider. Default = the zero-dep LLM extractor (always available).
    Returns None for unknown names or unavailable (key-gated) backends.
    """
    if name in (None, "llm"):
        from bad_research.browse.extract_llm import LLMExtractProvider

        return LLMExtractProvider()

    if name == "agentql":
        if not os.environ.get("AGENTQL_API_KEY"):
            return None
        try:
            from bad_research.browse.extract_agentql import AgentQLExtractProvider
        except ImportError:
            return None
        return AgentQLExtractProvider()

    if name == "stagehand":
        # Stagehand-extract needs a live session; only usable mid-Tier-3.
        # Not standalone-resolvable here, so the factory returns None and the
        # ladder constructs it from an active BrowserbaseProvider session instead.
        return None

    return None


def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    """Resolve a BrowseProvider. Default = Browser-Use self-host (if the lib is installed).
    Returns None for unknown names or unavailable backends.
    """
    if name in (None, "browser-use"):
        try:
            from bad_research.browse.browse_browseruse import BrowserUseProvider
        except ImportError:
            return None
        return BrowserUseProvider()

    if name == "browserbase":
        if not os.environ.get("BROWSERBASE_API_KEY"):
            return None
        try:
            from bad_research.browse.browse_browserbase import BrowserbaseProvider
        except ImportError:
            return None
        return BrowserbaseProvider()

    return None
