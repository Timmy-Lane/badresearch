"""sources.py extractors must NOT auto-follow redirects to internal hosts (FIX 2).

Every extractor httpx.get used follow_redirects=True, the exact bypass safe_redirect_get
closes: a public URL that 302s to http://169.254.169.254/ would be followed by httpx
with no per-hop SSRF re-check. These tests drive the real extractor code with an
httpx.MockTransport that 302s the public URL to the cloud-metadata IP and assert the
internal hop is REFUSED (SSRFError), not silently fetched.
"""

from __future__ import annotations

import httpx
import pytest

import bad_research.web.content.sources as src
from bad_research.core.fetcher import SSRFError

_META = "http://169.254.169.254/latest/meta-data/"


def _redirect_to_metadata_transport() -> httpx.MockTransport:
    """A transport that 302-redirects ANY request to the cloud-metadata IP, and would
    serve "SECRET" if the internal hop were ever followed."""

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "169.254.169.254":
            return httpx.Response(200, text="SECRET CREDS")  # must never be reached
        return httpx.Response(302, headers={"location": _META})

    return httpx.MockTransport(handler)


@pytest.fixture
def _patch_client(monkeypatch):
    """Patch httpx.Client so the extractor's safe_redirect_get path uses our transport
    while keeping follow_redirects=False enforcement intact."""
    transport = _redirect_to_metadata_transport()
    real_client = httpx.Client

    def _client(*a, **kw):
        kw.pop("transport", None)
        return real_client(*a, transport=transport, **kw)

    monkeypatch.setattr(src.httpx, "Client", _client)
    return transport


def test_sitemap_refuses_redirect_to_internal(_patch_client, monkeypatch) -> None:
    # _discover_sitemap returns a public sitemap URL; fetching it must refuse the
    # 302->metadata hop rather than read the internal host.
    monkeypatch.setattr(src, "_discover_sitemap", lambda host: "https://ex.com/sitemap.xml")
    with pytest.raises(SSRFError):
        src.sitemap_urls("ex.com")


def test_github_file_refuses_redirect_to_internal(_patch_client) -> None:
    with pytest.raises(SSRFError):
        src.github_file("owner", "repo", "README.md", branch="main")


def test_arxiv_refuses_redirect_to_internal(_patch_client) -> None:
    with pytest.raises(SSRFError):
        src.arxiv_source_notes("https://arxiv.org/abs/2401.00001")
