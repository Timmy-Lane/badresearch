"""Keyless provider registry: every row is keyless (requires_key False)."""

from __future__ import annotations

from bad_research.providers import (
    PROVIDERS,
    ProviderStatus,
    active_providers,
    provider_status,
)


def test_registry_is_keyless_only():
    names = {p.name for p in PROVIDERS}
    # keyless rows present
    assert {"anthropic-host", "websearch", "ddgs", "searxng", "agent-browser"} <= names
    # no keyed provider survives KR-1
    for gone in ("cohere", "tavily", "exa", "firecrawl", "agentql", "browserbase", "browser_use", "sonar"):
        assert gone not in names


def test_every_provider_requires_no_key():
    for s in provider_status():
        assert s.requires_key is False, f"{s.name} still requires a key"
        assert s.key_present is True  # no key required -> always "present"


def test_active_reduces_to_import_present():
    for s in provider_status():
        assert s.active == s.import_present


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")


def test_active_providers_subset():
    active = active_providers()
    assert all(s.active for s in active)
