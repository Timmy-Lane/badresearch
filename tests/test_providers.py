"""Provider registry: env + import availability, no network."""

from __future__ import annotations

from bad_research.providers import (
    PROVIDERS,
    ProviderStatus,
    active_providers,
    provider_status,
)


def test_registry_covers_expected_providers():
    names = {p.name for p in PROVIDERS}
    assert {
        "anthropic",
        "tavily",
        "exa",
        "cohere",
        "firecrawl",
        "browser_use",
        "searxng",
        "agentql",
    } <= names


def test_status_reads_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-xxx")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    statuses = {s.name: s for s in provider_status()}
    assert statuses["tavily"].key_present is True
    assert statuses["exa"].key_present is False


def test_searxng_needs_no_key(monkeypatch):
    # SearXNG is the zero-key default lane — always "key_present" (no key required).
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    statuses = {s.name: s for s in provider_status()}
    assert statuses["searxng"].requires_key is False
    assert statuses["searxng"].key_present is True


def test_active_providers_requires_key_and_import(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    active = active_providers()
    names = {s.name for s in active}
    # anthropic is a base dep, so if its key is set AND the import resolves, it's active.
    if any(s.name == "anthropic" and s.import_present for s in provider_status()):
        assert "anthropic" in names


def test_inactive_when_no_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    statuses = {s.name: s for s in provider_status()}
    assert statuses["exa"].active is False  # no key → never active


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")
