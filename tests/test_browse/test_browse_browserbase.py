"""BrowserbaseProvider: mocked Stagehand agent -> WebResult; verified stealth; replay."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.web.base import WebResult


def _fake_stagehand_factory(final_text: str, final_url: str = "https://site.test/done"):
    """Build a fake Stagehand client whose agent.execute returns a result and whose
    page.extract / page text yields content."""
    stagehand = MagicMock()
    agent = MagicMock()
    agent.execute.return_value = MagicMock(success=True)
    stagehand.agent.return_value = agent
    page = MagicMock()
    page.url = final_url
    page.extract.return_value = {"text": final_text}
    page.content.return_value = f"<html><body>{final_text}</body></html>"
    stagehand.page = page
    return stagehand, agent, page


def test_browse_drives_agent_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    stagehand, agent, page = _fake_stagehand_factory("Recovered content behind Cloudflare. " * 8)

    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", lambda **kw: stagehand)

    prov = mod.BrowserbaseProvider()
    r = prov.browse("https://site.test", "dismiss the wall and read the article", max_steps=10)
    assert isinstance(r, WebResult)
    assert "Recovered content" in r.content
    assert r.url == "https://site.test/done"
    agent.execute.assert_called_once()


def test_browse_uses_verified_stealth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-bot tier must request verified stealth (stealth_level 2)."""
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    captured = {}

    def fake_make(**kw):
        captured.update(kw)
        stagehand, _, _ = _fake_stagehand_factory("content " * 50)
        return stagehand

    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", fake_make)

    mod.BrowserbaseProvider().browse("https://site.test", "read it")
    assert captured.get("verified") is True


def test_browse_replay_cache_hit_skips_connection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    from bad_research.browse import browse_browserbase as mod
    from bad_research.browse.cache import ActCache, replay_key_for

    sentinel = MagicMock(side_effect=AssertionError("should not connect on cache hit"))
    monkeypatch.setattr(mod, "_make_stagehand", sentinel)

    cache = ActCache(root=tmp_path)
    key = replay_key_for("read it", "https://site.test", variables=None)
    cache.put(key, {"content": "CACHED bb body " * 10, "final_url": "https://site.test/a"})

    prov = mod.BrowserbaseProvider(cache=cache)
    r = prov.browse("https://site.test", "read it", replay_key=key)
    assert "CACHED bb body" in r.content


def test_browse_connection_error_returns_junk_webresult(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the remote browser fails, return an empty WebResult (caller sees junk, doesn't crash)."""
    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    from bad_research.browse import browse_browserbase as mod
    monkeypatch.setattr(mod, "_make_stagehand", MagicMock(side_effect=RuntimeError("net down")))

    r = mod.BrowserbaseProvider().browse("https://site.test", "read it")
    assert isinstance(r, WebResult)
    assert r.content == ""
