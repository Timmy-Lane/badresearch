"""Contract tests for the BrowseProvider / ExtractProvider Protocols and factories."""

from __future__ import annotations

import pytest

from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)
from bad_research.web.base import WebResult


class _DummyBrowse:
    name = "dummy"

    def browse(self, url, instruction, *, max_steps=12, variables=None, replay_key=None):
        return WebResult(url=url, title="t", content="browsed " + instruction)


class _DummyExtract:
    name = "dummy"

    def extract(self, source, schema, instruction=""):
        return {"ok": True}


def test_browse_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyBrowse(), BrowseProvider)


def test_extract_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyExtract(), ExtractProvider)


def test_browse_signature_accepts_keyword_only_args() -> None:
    p = _DummyBrowse()
    r = p.browse("https://x.test", "load all reviews", max_steps=5,
                 variables={"u": "user"}, replay_key="k")
    assert isinstance(r, WebResult)
    assert r.content == "browsed load all reviews"


def test_get_extract_provider_default_is_llm() -> None:
    """Default extract provider is the zero-dep LLM extractor (always available)."""
    p = get_extract_provider()  # no name -> default
    assert p is not None
    assert p.name == "llm"


def test_get_extract_provider_unknown_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown / unavailable extract backend -> None (graceful), never raises."""
    assert get_extract_provider("does-not-exist") is None


def test_get_browse_provider_unknown_returns_none() -> None:
    assert get_browse_provider("does-not-exist") is None


def test_get_browse_provider_default_none_until_kr4() -> None:
    """agent-browser CLI wrapper not built yet (KR-4) -> None, never raises."""
    assert get_browse_provider() is None
    assert get_browse_provider("agent-browser") is None


def test_get_extract_provider_aql_none_until_kr4() -> None:
    assert get_extract_provider("aql") is None
