"""Contract tests for the BrowseProvider / ExtractProvider Protocols and factories."""

from __future__ import annotations

from typing import Any

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


def test_get_browse_provider_browseruse_none_when_lib_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser-use not installed -> factory returns None, never raises ImportError."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "browser_use" or name.startswith("browser_use."):
            raise ImportError("No module named 'browser_use'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert get_browse_provider("browser-use") is None


def test_get_browse_provider_browserbase_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    assert get_browse_provider("browserbase") is None


def test_get_extract_provider_agentql_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
    assert get_extract_provider("agentql") is None
