"""Keyless provider registry + external-CLI detection (no network, no subprocess)."""

from __future__ import annotations

from bad_research.providers import (
    EXTERNAL_CLIS,
    PROVIDERS,
    ProviderStatus,
    active_providers,
    external_cli_status,
    provider_status,
)


def test_registry_is_keyless_only():
    names = {p.name for p in PROVIDERS}
    # The keyless surface (INTERFACES_KEYLESS §3.5).
    assert {
        "anthropic-host",
        "websearch",
        "ddgs",
        "searxng",
        "crawl4ai",
        "agent-browser",
        "arxiv",
        "openalex",
        "crossref",
        "europepmc",
        "pubmed",
        "wikipedia",
    } <= names
    # None of the removed keyed providers may appear.
    assert not (
        names & {"cohere", "tavily", "exa", "sonar", "firecrawl", "browserbase", "browser_use", "agentql"}
    )


def test_every_provider_is_keyless():
    for s in provider_status():
        assert s.requires_key is False, f"{s.name} requires a key — not keyless"
        assert s.key_present is True, f"{s.name} should be key_present (no key needed)"


def test_active_reduces_to_import_present():
    # With requires_key False everywhere, active == import_present.
    for s in provider_status():
        assert s.active == s.import_present


def test_anthropic_host_is_base_and_keyless():
    by_name = {p.name: p for p in PROVIDERS}
    p = by_name["anthropic-host"]
    assert p.env_var is None  # host supplies inference; no key
    assert p.extra == "(base)"


def test_external_cli_status_shape():
    rows = external_cli_status()
    by = {r["name"]: r for r in rows}
    # The 4 driven CLIs are reported; SearXNG is NOT (silent/opt-in).
    assert {"agent-browser", "lightpanda", "yt-dlp", "git"} <= set(by)
    assert "searxng" not in {n.lower() for n in by}
    for name, row in by.items():
        assert set(row) == {"name", "present", "hint"}
        assert isinstance(row["present"], bool)
        assert row["hint"] == EXTERNAL_CLIS[name]


def test_git_is_detected_present():
    # git is on every dev box / CI runner.
    rows = {r["name"]: r for r in external_cli_status()}
    assert rows["git"]["present"] is True


def test_status_is_dataclass():
    s = provider_status()[0]
    assert isinstance(s, ProviderStatus)
    assert hasattr(s, "name") and hasattr(s, "active") and hasattr(s, "extra")


def test_active_providers_nonempty_offline():
    # Keyless registry: every provider whose import resolves is active, no keys needed.
    assert active_providers()  # at least the base httpx/ddgs/host rows
