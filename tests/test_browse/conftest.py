"""Shared fixtures for the browse-ladder tests. Mocks everything external."""

from __future__ import annotations

from typing import Any

import pytest

from bad_research.web.base import WebResult


def make_result(content: str, *, url: str = "https://example.test/page",
                title: str = "Example") -> WebResult:
    return WebResult(url=url, title=title, content=content)


@pytest.fixture
def good_result() -> WebResult:
    # Long, clean content — passes looks_like_junk (>= 300 chars, no bot/error signals).
    body = ("This is a substantial article about a real topic. " * 20)
    return make_result(body, title="A Real Article")


@pytest.fixture
def empty_result() -> WebResult:
    # < 300 chars -> looks_like_junk == "Empty or near-empty content" -> escalate 0->1.
    return make_result("tiny", title="Stub")


@pytest.fixture
def bot_result() -> WebResult:
    # Cloudflare interstitial -> looks_like_junk == "Bot detection page: ..." -> escalate to 3b.
    return make_result("Just a moment... Checking your browser. Ray ID: abc123. " * 10,
                       title="Just a moment...")


@pytest.fixture
def login_result() -> WebResult:
    # Short + login signals + /login path -> looks_like_login_wall == True -> escalate to 3.
    return make_result("Please sign in to continue. Create account.",
                       url="https://example.test/login", title="Sign in")


class FakeLLM:
    """A stand-in LLMProvider: returns a canned text per call. Records calls."""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages, *, tier="triage", tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        self.calls.append({"messages": messages, "tier": tier, "temperature": temperature})
        from bad_research.llm.base import LLMResponse

        text = self._replies.pop(0) if self._replies else "{}"
        return LLMResponse(text=text, tool_calls=[], usage={}, model="fake")


@pytest.fixture
def fake_llm() -> Any:
    return FakeLLM
