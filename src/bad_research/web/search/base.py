"""Keyless web-provider stubs (KR-2 fills the bodies).

KR-1 leaves typed, named stubs so `web/base.py::get_provider` resolves and the
registry/CLI work. Each `search`/`search_ex`/`fetch` raises NotImplementedError
with a 'KR-2' pointer until the real `web/search/` package lands.
"""

from __future__ import annotations

from bad_research.web.base import SearchQuery, WebResult


class _KeylessStub:
    """A typed keyless WebProvider stub. cost_per_search=0.0 (keyless)."""

    capabilities: frozenset[str] = frozenset({"keyword"})
    cost_per_search: float = 0.0
    p50_ms: int = 0

    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        raise NotImplementedError(f"{self.name} search is built in KR-2 (web/search/)")

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        raise NotImplementedError(f"{self.name} search_ex is built in KR-2 (web/search/)")

    def fetch(self, url: str) -> WebResult:
        raise NotImplementedError(f"{self.name} fetch is built in KR-3 (web/content/)")


def get_keyless_provider(name: str = "websearch") -> _KeylessStub:
    """Return a keyless provider stub by name (KR-2 replaces the bodies)."""
    if name not in ("websearch", "ddgs", "searxng"):
        raise ValueError(f"Unknown keyless provider: {name!r}")
    return _KeylessStub(name)
