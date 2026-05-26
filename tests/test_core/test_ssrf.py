"""SSRF guard — the fetch entry refuses private/loopback/cloud-metadata URLs."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from bad_research.core.fetcher import SSRFError, assert_url_safe, fetch_and_save
from bad_research.web.base import WebResult


# ── unit: assert_url_safe blocks the denylist ────────────────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.5.5.5/secret",
        "http://localhost/admin",
        "http://10.0.0.1/",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/",
        "http://0.0.0.0/",
    ],
)
def test_assert_url_safe_blocks_private_and_metadata(url):
    with pytest.raises(SSRFError):
        assert_url_safe(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://1.1.1.1/",          # public IP literal
        "https://8.8.8.8/resolve",
    ],
)
def test_assert_url_safe_allows_public(url):
    # Should not raise. (1.1.1.1 / 8.8.8.8 are public; example.com may or may not
    # resolve in the sandbox — unresolvable hosts are allowed through.)
    assert_url_safe(url)


def test_assert_url_safe_blocks_ipv4_mapped_ipv6():
    with pytest.raises(SSRFError):
        assert_url_safe("http://[::ffff:127.0.0.1]/")


def test_assert_url_safe_rejects_no_host():
    with pytest.raises(SSRFError):
        assert_url_safe("file:///etc/passwd")


def test_assert_url_safe_blocks_hostname_resolving_to_private(monkeypatch):
    # A hostname that DNS-resolves to a private IP must be blocked too.
    import bad_research.core.fetcher as f

    monkeypatch.setattr(
        f.socket, "getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))],
    )
    with pytest.raises(SSRFError):
        assert_url_safe("http://evil.internal.example/")


# ── integration: fetch_and_save refuses before any network call ──────────────
def _fake_vault(tmp_path):
    vault = MagicMock()
    vault.root = tmp_path
    vault.notes_dir = tmp_path / "research" / "notes"
    vault.notes_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE sources (url TEXT, note_id TEXT, domain TEXT, "
        "fetched_at TEXT, provider TEXT, content_hash TEXT)"
    )
    vault.db = conn
    cfg = MagicMock()
    cfg.web_provider = "builtin"
    cfg.web_profile = None
    cfg.web_magic = False
    vault.config = cfg
    return vault


def test_fetch_and_save_blocks_metadata_url(tmp_path, monkeypatch):
    vault = _fake_vault(tmp_path)
    fetched = {"n": 0}

    def _boom(*a, **k):  # the provider must never be reached
        fetched["n"] += 1
        return WebResult(url="x", title="t", content="c")

    monkeypatch.setattr("bad_research.web.base.get_provider", lambda *a, **k: MagicMock(fetch=_boom))
    with pytest.raises(SSRFError):
        fetch_and_save(vault, "http://169.254.169.254/latest/meta-data/")
    assert fetched["n"] == 0  # blocked before any fetch
