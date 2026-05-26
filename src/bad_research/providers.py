"""Provider registry — what's installed, what's keyed, what's active.

Pure and network-free: `bad doctor` and `bad calibrate` use this to report which
providers can run. A provider is *active* iff its key is present (or it needs none)
AND its client library imports. Single source of truth for the optional-extras map.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    env_var: str | None  # None → no key required (e.g. SearXNG, self-host)
    import_name: str | None  # the module that must import for the client to work
    extra: str  # which `pip install bad-research[<extra>]` ships it
    capability: str  # "llm" | "search" | "browse" | "embed" | "rerank"


# The registry. Keys are read from env OR ~/.config/bad-research/config.toml (SPEC §12);
# this table only knows the env-var name — config.toml merging is the caller's job.
PROVIDERS: tuple[Provider, ...] = (
    Provider("anthropic-host", None, "anthropic", "(base)", "llm"),    # host supplies inference; no key
    Provider("websearch", None, None, "(base)", "search"),             # host WebSearch tool (KR-2)
    Provider("ddgs", None, "ddgs", "(base)", "search"),                # keyless multi-engine lib (KR-2)
    Provider("searxng", None, None, "(base)", "search"),               # self-host JSON, no key (KR-2)
    Provider("crawl4ai", None, "crawl4ai", "browse", "browse"),        # local JS render
    Provider("agent-browser", None, None, "browse", "browse"),         # local CLI (CDP); KR-4
    Provider("arxiv", None, None, "(base)", "search"),                 # keyless vertical (httpx); KR-2
    Provider("openalex", None, None, "(base)", "search"),
    Provider("crossref", None, None, "(base)", "search"),
    Provider("europepmc", None, None, "(base)", "search"),
    Provider("pubmed", None, None, "(base)", "search"),
    Provider("wikipedia", None, None, "(base)", "search"),
    Provider("bge-local", None, "sentence_transformers", "local", "embed"),     # [local] opt-in; KR-5
    Provider("ms-marco-local", None, "sentence_transformers", "local", "rerank"),
    Provider("nli-deberta", None, "sentence_transformers", "local", "nli"),
)


@dataclass
class ProviderStatus:
    name: str
    capability: str
    extra: str
    requires_key: bool
    key_present: bool
    import_present: bool
    active: bool


def _import_ok(import_name: str | None) -> bool:
    if not import_name:
        return True  # no client lib required (SearXNG, Sonar via httpx)
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def provider_status() -> list[ProviderStatus]:
    """Status for every registered provider. No network, no config-file read."""
    out: list[ProviderStatus] = []
    for p in PROVIDERS:
        requires_key = bool(p.env_var)
        key_present = (not requires_key) or bool(os.environ.get(p.env_var or ""))
        import_present = _import_ok(p.import_name)
        out.append(
            ProviderStatus(
                name=p.name,
                capability=p.capability,
                extra=p.extra,
                requires_key=requires_key,
                key_present=key_present,
                import_present=import_present,
                active=key_present and import_present,
            )
        )
    return out


def active_providers() -> list[ProviderStatus]:
    """Only the providers that can actually run right now."""
    return [s for s in provider_status() if s.active]


__all__ = [
    "PROVIDERS",
    "Provider",
    "ProviderStatus",
    "active_providers",
    "provider_status",
]
