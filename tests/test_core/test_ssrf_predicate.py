"""is_blocked_url — the DRY SSRF predicate shared by assert_url_safe + the render
route handler (FIX 1). Pure, network-free, browser-free.
"""

from __future__ import annotations

import pytest

from bad_research.core.fetcher import is_blocked_url


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",                # IPv4-mapped IPv6
        "http://0.0.0.0/",
        "file:///etc/passwd",                        # no host
    ],
)
def test_is_blocked_url_blocks(url: str) -> None:
    assert is_blocked_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://1.1.1.1/",   # public IP literal
        "https://8.8.8.8/resolve",
        "https://example.com/",  # may be unresolvable in sandbox -> allowed
    ],
)
def test_is_blocked_url_allows_public(url: str) -> None:
    assert is_blocked_url(url) is False


def test_is_blocked_url_blocks_hostname_resolving_to_private(monkeypatch) -> None:
    import bad_research.core.fetcher as f

    monkeypatch.setattr(
        f.socket, "getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))],
    )
    assert is_blocked_url("http://evil.internal.example/") is True


def test_assert_url_safe_uses_predicate() -> None:
    # assert_url_safe must be a thin wrapper over the shared predicate (DRY): a
    # blocked URL raises, an allowed one does not.
    from bad_research.core.fetcher import SSRFError, assert_url_safe

    with pytest.raises(SSRFError):
        assert_url_safe("http://169.254.169.254/latest/meta-data/")
    assert_url_safe("https://1.1.1.1/")  # public -> no raise
