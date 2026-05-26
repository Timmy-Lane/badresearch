"""core/fetcher delegates to fetch_tiered with the right args when tiers are requested."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.web.base import WebResult


@pytest.fixture
def fake_vault(tmp_path):
    """Minimal vault stub: a config with web_provider/profile, an in-memory sqlite, dirs."""
    import sqlite3

    vault = MagicMock()
    vault.root = tmp_path
    vault.notes_dir = tmp_path / "research" / "notes"
    vault.notes_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sources (url TEXT, note_id TEXT, domain TEXT, "
                 "fetched_at TEXT, provider TEXT, content_hash TEXT)")
    vault.db = conn
    cfg = MagicMock()
    cfg.web_provider = "builtin"
    cfg.web_profile = None
    cfg.web_magic = False
    vault.config = cfg
    return vault


def test_no_tier_args_uses_plain_provider_fetch(monkeypatch, fake_vault):
    """Default call -> fetch_tiered NOT used; behaviour unchanged (existing get_provider path)."""
    from bad_research.core import fetcher

    called = {"tiered": 0}
    monkeypatch.setattr(fetcher, "fetch_tiered",
                        lambda *a, **k: called.__setitem__("tiered", called["tiered"] + 1) or
                        WebResult(url="x", title="t", content="c"))

    prov = MagicMock()
    prov.name = "builtin"
    prov.fetch.return_value = WebResult(url="https://x.test", title="Real",
                                        content="Substantial article content. " * 30)
    monkeypatch.setattr("bad_research.web.base.get_provider", lambda *a, **k: prov)
    # Avoid touching real sync machinery.
    monkeypatch.setattr(fetcher, "_persist_note", lambda *a, **k: "note-1", raising=False)

    fetcher.fetch_and_save(fake_vault, "https://x.test")
    assert called["tiered"] == 0
    prov.fetch.assert_called_once()


def test_tier_args_route_through_fetch_tiered(monkeypatch, fake_vault):
    """tier_max/instruction/schema set -> fetch_tiered is called with them."""
    from bad_research.core import fetcher

    captured = {}

    def fake_tiered(url, *, tier_max, instruction=None, schema=None, **kw):
        captured.update(url=url, tier_max=tier_max, instruction=instruction, schema=schema)
        return WebResult(url=url, title="Browsed", content="Recovered content. " * 40,
                         metadata={"extracted": {"k": "v"}})

    monkeypatch.setattr(fetcher, "fetch_tiered", fake_tiered)
    monkeypatch.setattr(fetcher, "_persist_note", lambda *a, **k: "note-1", raising=False)

    fetcher.fetch_and_save(fake_vault, "https://x.test", tier_max=3,
                           instruction="log in and read", schema={"type": "object"})
    assert captured["url"] == "https://x.test"
    assert captured["tier_max"] == 3
    assert captured["instruction"] == "log in and read"
    assert captured["schema"] == {"type": "object"}
