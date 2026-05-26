"""Render-rung SSRF gate (FIX 1).

The crawl4ai render rung drives a real headless Chromium that ignores the Python
httpx denylist. A malicious page can serve a thin static body to pass the static
check, trigger needs_js, then re-navigate (30x / <meta refresh> / JS window.location
/ fetch / XHR) to http://169.254.169.254/ or http://127.0.0.1/. We close this with a
Playwright context-level route handler that aborts any request resolving to a blocked
host — reusing the SAME predicate (core/fetcher.is_blocked_url) as assert_url_safe.

These tests exercise the handler logic WITHOUT spinning up a browser, via a fake
Playwright Route, plus assert the hook is wired into the crawl4ai strategy.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from bad_research.web.content.fetch_clean import _ssrf_route_handler


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeRoute:
    """Minimal Playwright Route stand-in recording abort()/continue_() calls."""

    def __init__(self, url: str) -> None:
        self.request = _FakeRequest(url)
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://localhost/admin",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",                # IPv4-mapped IPv6
    ],
)
def test_route_handler_aborts_blocked(url: str) -> None:
    route = _FakeRoute(url)
    asyncio.run(_ssrf_route_handler(route))
    assert route.aborted is True
    assert route.continued is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example-public-site.test/page",  # unresolvable -> allowed
        "https://1.1.1.1/",                        # public IP literal
    ],
)
def test_route_handler_continues_allowed(url: str) -> None:
    route = _FakeRoute(url)
    asyncio.run(_ssrf_route_handler(route))
    assert route.continued is True
    assert route.aborted is False


def test_on_context_created_hook_registers_route() -> None:
    # The hook must register a context-level route so ALL pages/frames/redirects are
    # intercepted, not just the main frame.
    from bad_research.web.content.fetch_clean import _ssrf_on_context_created

    context = MagicMock()
    context.route = MagicMock(
        side_effect=lambda *a, **k: asyncio.sleep(0)
    )
    page = MagicMock()
    asyncio.run(_ssrf_on_context_created(page, context=context))
    context.route.assert_called_once()
    pattern, handler = context.route.call_args.args
    assert pattern == "**/*"
    assert handler is _ssrf_route_handler


def test_render_fetch_wires_ssrf_hook(monkeypatch) -> None:
    # _render_fetch must construct a crawl4ai provider that has the SSRF route hook
    # registered on its Playwright strategy.
    import importlib

    from bad_research.web.base import WebResult

    # Resolve the submodule explicitly: the package __init__ may re-export the
    # fetch_clean *function*, shadowing the submodule attribute (see FIX 3).
    fc = importlib.import_module("bad_research.web.content.fetch_clean")

    captured: dict = {}

    class _FakeProvider:
        def __init__(self, *a, ssrf_guard: bool = False, **k) -> None:
            captured["ssrf_guard"] = ssrf_guard

        def fetch(self, url: str) -> WebResult:
            return WebResult(url=url, title="t", content="c", raw_html="<html></html>")

    monkeypatch.setattr(fc, "Crawl4AIProvider", _FakeProvider, raising=False)
    # Crawl4AIProvider is imported inside _render_fetch; patch the source module too.
    monkeypatch.setattr(
        "bad_research.web.crawl4ai_provider.Crawl4AIProvider", _FakeProvider
    )
    fc._render_fetch("https://example.test/page")
    assert captured["ssrf_guard"] is True


def test_crawl4ai_provider_registers_hook_when_guarded() -> None:
    # When ssrf_guard=True the provider's Playwright strategy must carry the
    # on_page_context_created hook bound to our handler.
    from bad_research.web.content.fetch_clean import _ssrf_on_context_created
    from bad_research.web.crawl4ai_provider import Crawl4AIProvider

    prov = Crawl4AIProvider(ssrf_guard=True)
    strat = prov._build_ssrf_strategy()
    assert strat.hooks.get("on_page_context_created") is _ssrf_on_context_created
