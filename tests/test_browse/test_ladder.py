"""fetch_tiered escalation decisions — the heart of Plan 04. All providers mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.browse.ladder import fetch_tiered
from bad_research.web.base import WebResult
from tests.test_browse.conftest import make_result


def _good(url="https://x.test"):
    return make_result("Substantial real article content. " * 30, url=url, title="Real")


def _empty(url="https://x.test"):
    return make_result("tiny", url=url, title="Stub")


def _bot(url="https://x.test"):
    return make_result("Just a moment... checking your browser ray id " * 10,
                       url=url, title="Just a moment...")


def _login(url="https://x.test/login"):
    return make_result("Please sign in. create account.", url=url, title="Sign in")


def test_tier0_good_result_no_escalation() -> None:
    """Tier 0 returns clean content -> ladder stops at Tier 0, never builds Tier 1."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    t1 = MagicMock()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t0.fetch.assert_called_once()
    t1.fetch.assert_not_called()


def test_tier0_empty_escalates_to_tier1() -> None:
    """Empty Tier-0 (< 300 chars) -> escalate to crawl4ai Tier 1."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t1.fetch.assert_called_once()


def test_tier1_unavailable_returns_best_lower_tier() -> None:
    """crawl4ai missing -> ladder keeps the (empty) Tier-0 result, never raises."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: None)  # None = unavailable
    assert r.content == "tiny"


def test_tier_max_caps_escalation() -> None:
    """tier_max=0 forbids leaving Tier 0 even on an empty result."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=0,
                     _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content == "tiny"
    t1.fetch.assert_not_called()


def test_bot_wall_escalates_to_browserbase() -> None:
    """Tier-1 bot-detection page + tier_max>=3 -> Tier-3b Browserbase browse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _bot()
    bb = MagicMock(); bb.browse.return_value = make_result("Recovered behind cloudflare. " * 20)
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1,
                     _browserbase=bb, _browseruse=None)
    assert "Recovered behind cloudflare" in r.content
    bb.browse.assert_called_once()


def test_login_wall_escalates_to_agentic_browse() -> None:
    """Tier-1 login wall + tier_max>=3 -> Tier-3 agentic (Browser-Use) browse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    bu = MagicMock(); bu.browse.return_value = make_result("Logged-in dashboard content. " * 20)
    r = fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                     _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    assert "Logged-in dashboard" in r.content
    bu.browse.assert_called_once()


def test_schema_triggers_tier2_extract_attaches_dict() -> None:
    """A schema arg -> Tier-2 extract; typed dict attaches to metadata['extracted']."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    extractor = MagicMock(); extractor.extract.return_value = {"title": "Real", "n": 3}
    r = fetch_tiered("https://x.test", tier_max=2,
                     schema={"type": "object", "properties": {"title": {"type": "string"}}},
                     _tier0=t0, _tier1_factory=lambda: MagicMock(),
                     _extractor=extractor)
    assert r.metadata["extracted"] == {"title": "Real", "n": 3}
    assert r.content.startswith("Substantial real")  # prose preserved
    extractor.extract.assert_called_once()


def test_schema_extract_empty_leaves_result_unchanged() -> None:
    """Extractor returns {} (no provider) -> result unchanged, no metadata['extracted']."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    extractor = MagicMock(); extractor.extract.return_value = {}
    r = fetch_tiered("https://x.test", tier_max=2,
                     schema={"type": "object"}, _tier0=t0,
                     _tier1_factory=lambda: MagicMock(), _extractor=extractor)
    assert "extracted" not in r.metadata


def test_instruction_triggers_tier3_browse() -> None:
    """An instruction (multi-step goal) -> Tier-3 browse even when Tier-0 looked OK-ish empty."""
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()  # JS render works...
    bu = MagicMock(); bu.browse.return_value = make_result("Paginated, all 50 reviews loaded. " * 10)
    r = fetch_tiered("https://x.test", tier_max=3, instruction="load all reviews",
                     _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    assert "all 50 reviews" in r.content
    bu.browse.assert_called_once()


def test_no_browse_provider_stays_on_lower_tier() -> None:
    """instruction set but no browse provider available -> keep best lower-tier result."""
    t0 = MagicMock(); t0.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3, instruction="paginate",
                     _tier0=t0, _tier1_factory=lambda: MagicMock(),
                     _browseruse=None, _browserbase=None)
    assert r.content.startswith("Substantial real")


def test_replay_key_threaded_to_browse() -> None:
    """A replay_key is forwarded to the browse provider for cache reuse."""
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    bu = MagicMock(); bu.browse.return_value = make_result("dashboard " * 60)
    fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                 replay_key="rk-123",
                 _tier0=t0, _tier1_factory=lambda: t1, _browseruse=bu)
    _, kwargs = bu.browse.call_args
    assert kwargs["replay_key"] == "rk-123"
