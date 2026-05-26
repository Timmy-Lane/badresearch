from __future__ import annotations

import pytest

from bad_research.llm.base import LLMMessage, LLMResponse


class FakeLLMProvider:
    """Structural LLMProvider for tests. Returns a scripted JSON body per call.

    Set `.script` to a list of response-text strings (popped FIFO); when empty,
    returns "[]". Records every call in `.calls` so tests can assert batching.
    """

    name = "fake"

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: str,
        tools: list[dict] | None = None,
        cache: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tier": tier})
        text = self.script.pop(0) if self.script else "[]"
        return LLMResponse(text=text, model="fake-haiku")


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()
