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


# ── redirect-to-internal SSRF bypass (fix #4) ────────────────────────────────
class _Resp:
    """Minimal httpx.Response stand-in: a redirect (is_redirect=True + Location) or
    a terminal 200."""

    def __init__(self, *, status_code=200, location=None, text="ok", url="http://x/"):
        self.status_code = status_code
        self.is_redirect = location is not None
        self.headers = {"location": location} if location else {}
        self.text = text
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class _FakeClient:
    """Fake httpx.Client that returns a scripted sequence of responses (one per
    .get) and records every URL it was asked to GET."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requested: list[str] = []

    def get(self, url, headers=None):
        self.requested.append(url)
        return self._responses.pop(0)


def test_safe_redirect_get_refuses_redirect_to_metadata():
    # A public URL whose 302 Location points at the cloud-metadata IP must be
    # REFUSED on the 2nd hop — assert_url_safe runs before the redirect is followed.
    from bad_research.core.fetcher import safe_redirect_get

    client = _FakeClient([
        _Resp(status_code=302, location="http://169.254.169.254/latest/meta-data/"),
        _Resp(status_code=200, text="SECRET CREDS"),  # must never be returned
    ])
    with pytest.raises(SSRFError):
        safe_redirect_get(client, "https://public.example.com/redirector")
    # Only the first (public) URL was actually GET — the internal hop was blocked
    # before its request went out.
    assert client.requested == ["https://public.example.com/redirector"]


def test_safe_redirect_get_follows_safe_public_redirect():
    # A public->public redirect chain is followed and returns the terminal response.
    from bad_research.core.fetcher import safe_redirect_get

    client = _FakeClient([
        _Resp(status_code=302, location="https://other.example.com/final"),
        _Resp(status_code=200, text="hello world"),
    ])
    resp = safe_redirect_get(client, "https://public.example.com/start")
    assert resp.status_code == 200
    assert resp.text == "hello world"
    assert client.requested == [
        "https://public.example.com/start",
        "https://other.example.com/final",
    ]


def test_safe_redirect_get_relative_redirect_revalidated():
    # A relative Location is resolved against the current URL before re-validation.
    from bad_research.core.fetcher import safe_redirect_get

    client = _FakeClient([
        _Resp(status_code=302, location="/next"),
        _Resp(status_code=200, text="done"),
    ])
    resp = safe_redirect_get(client, "https://public.example.com/a/b")
    assert resp.text == "done"
    assert client.requested == [
        "https://public.example.com/a/b",
        "https://public.example.com/next",
    ]


def test_safe_redirect_get_caps_hops():
    from bad_research.core.fetcher import safe_redirect_get

    # An endless redirect loop (always 302 to another public URL) is capped.
    loop = [_Resp(status_code=302, location=f"https://public.example.com/{i}") for i in range(20)]
    client = _FakeClient(loop)
    with pytest.raises(RuntimeError, match="too many redirects"):
        safe_redirect_get(client, "https://public.example.com/start", max_hops=3)


def test_builtin_provider_refuses_redirect_to_internal(monkeypatch):
    # End-to-end through BuiltinProvider._download: a public URL that 302s to an
    # internal host must raise SSRFError, not be followed. This exercises the REAL
    # fetch path with follow_redirects=False + safe_redirect_get.
    import httpx

    from bad_research.web.builtin import BuiltinProvider

    captured = {}

    def _fake_client(*, follow_redirects, timeout):
        # The provider MUST disable httpx's own redirect following, else the per-hop
        # SSRF check would be bypassed.
        captured["follow_redirects"] = follow_redirects
        return _FakeClientCtx(_FakeClient([
            _Resp(status_code=302, location="http://169.254.169.254/latest/meta-data/"),
            _Resp(status_code=200, text="SECRET"),
        ]))

    monkeypatch.setattr(httpx, "Client", _fake_client)
    with pytest.raises(SSRFError):
        BuiltinProvider()._download("https://public.example.com/redirector")
    assert captured["follow_redirects"] is False


class _FakeClientCtx:
    """Context-manager wrapper so `with httpx.Client(...) as client:` works."""

    def __init__(self, client):
        self._client = client

    def __enter__(self):
        return self._client

    def __exit__(self, *exc):
        return False
