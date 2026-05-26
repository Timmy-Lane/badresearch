"""Tests for the LLMProvider seam types and factory."""

from __future__ import annotations

import pytest

from bad_research.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    get_llm_provider,
)


def test_llmmessage_shape() -> None:
    m = LLMMessage(role="user", content="hello")
    assert m.role == "user"
    assert m.content == "hello"
    # content may also be a list[dict] (multimodal / tool blocks)
    m2 = LLMMessage(role="assistant", content=[{"type": "text", "text": "hi"}])
    assert isinstance(m2.content, list)


def test_llmresponse_shape() -> None:
    r = LLMResponse(
        text="answer",
        tool_calls=[],
        usage={"input_tokens": 10, "output_tokens": 5, "cache_read": 0, "cache_write": 0},
        model="claude-opus-4-7",
    )
    assert r.text == "answer"
    assert r.tool_calls == []
    assert r.usage["input_tokens"] == 10
    assert r.model == "claude-opus-4-7"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("does-not-exist")


def test_protocol_is_runtime_checkable() -> None:
    """A duck-typed object satisfying the surface is an LLMProvider instance."""

    class _Fake:
        name = "fake"

        def complete(self, messages, *, tier, tools=None, cache=False,
                     max_tokens=4096, temperature=0.1):
            return LLMResponse(text="", tool_calls=[], usage={}, model="fake")

    assert isinstance(_Fake(), LLMProvider)
