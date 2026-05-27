"""Tests for AnthropicProvider — mocks the anthropic SDK.

Mirrors hyperresearch's test_exa_provider.py pattern: patch the SDK class at its
source module so the provider's lazy import picks up the mock. No network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.llm.base import LLMMessage, get_llm_provider


def _make_message_response(
    *,
    text: str = "the answer",
    model: str = "claude-opus-4-7",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_read: int = 0,
    cache_write: int = 0,
) -> SimpleNamespace:
    """Shape an anthropic Messages API response object (duck-typed)."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )


def _patch_sdk(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    """Patch `anthropic.Anthropic` at the source module the provider imports from."""
    import anthropic

    factory = MagicMock(return_value=client)
    monkeypatch.setattr(anthropic, "Anthropic", factory)


def _provider(monkeypatch: pytest.MonkeyPatch, client: MagicMock):
    from bad_research.llm.anthropic import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    return AnthropicProvider()


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.llm.anthropic import AnthropicProvider

    # _clear_provider_keys autouse fixture already removed ANTHROPIC_API_KEY.
    _patch_sdk(monkeypatch, MagicMock())
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_factory_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = get_llm_provider("anthropic")
    assert prov.name == "anthropic"


def test_tier_to_model_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(model="claude-haiku-4-5")
    prov = _provider(monkeypatch, client)

    assert prov._resolve_model("triage") == "claude-haiku-4-5"
    assert prov._resolve_model("work") == "claude-sonnet-4-6"
    assert prov._resolve_model("heavy") == "claude-opus-4-7"


def test_cheap_demotes_heavy_to_work(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.config import BadResearchConfig
    from bad_research.llm.anthropic import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = AnthropicProvider(config=BadResearchConfig(cheap=True))

    assert prov._resolve_model("heavy") == "claude-sonnet-4-6"  # demoted
    assert prov._resolve_model("work") == "claude-sonnet-4-6"   # unchanged
    assert prov._resolve_model("triage") == "claude-haiku-4-5"  # unchanged


def test_complete_returns_llmresponse(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(
        text="grounded answer", model="claude-sonnet-4-6",
        input_tokens=42, output_tokens=7, cache_read=30, cache_write=12,
    )
    prov = _provider(monkeypatch, client)

    resp = prov.complete(
        [LLMMessage(role="user", content="Q")],
        tier="work",
    )
    assert resp.text == "grounded answer"
    assert resp.model == "claude-sonnet-4-6"
    assert resp.usage == {
        "input_tokens": 42, "output_tokens": 7, "cache_read": 30, "cache_write": 12,
    }
    assert resp.tool_calls == []


def test_temperature_omitted_for_opus_heavy(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default config (cheap=False) so heavy -> claude-opus-4-7, which rejects
    # sampling params with a 400. temperature must NOT be forwarded.
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(model="claude-opus-4-7")
    prov = _provider(monkeypatch, client)

    prov.complete([LLMMessage(role="user", content="q")], tier="heavy")
    assert prov._resolve_model("heavy") == "claude-opus-4-7"
    assert "temperature" not in client.messages.create.call_args.kwargs


def test_temperature_included_for_sonnet_work(monkeypatch: pytest.MonkeyPatch) -> None:
    # work -> claude-sonnet-4-6 accepts sampling params; temperature forwarded.
    client = MagicMock()
    client.messages.create.return_value = _make_message_response(model="claude-sonnet-4-6")
    prov = _provider(monkeypatch, client)

    prov.complete([LLMMessage(role="user", content="q")], tier="work")
    assert prov._resolve_model("work") == "claude-sonnet-4-6"
    assert client.messages.create.call_args.kwargs["temperature"] == 0.1


def test_temperature_included_for_cheap_heavy_demoted_to_sonnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --cheap demotes heavy -> work (claude-sonnet-4-6), which accepts sampling
    # params, so temperature IS forwarded even though the requested tier is heavy.
    from bad_research.config import BadResearchConfig
    from bad_research.llm.anthropic import AnthropicProvider

    client = MagicMock()
    client.messages.create.return_value = _make_message_response(model="claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    prov = AnthropicProvider(config=BadResearchConfig(cheap=True))

    prov.complete([LLMMessage(role="user", content="q")], tier="heavy")
    assert prov._resolve_model("heavy") == "claude-sonnet-4-6"  # demoted
    assert client.messages.create.call_args.kwargs["temperature"] == 0.1


def test_system_messages_routed_to_system_param(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    prov.complete(
        [
            LLMMessage(role="system", content="You are bad."),
            LLMMessage(role="user", content="hello"),
        ],
        tier="heavy",
    )
    _, kwargs = client.messages.create.call_args
    # system goes to the top-level `system` param, NOT into messages[]
    assert any(b["text"] == "You are bad." for b in kwargs["system"])
    assert all(m["role"] != "system" for m in kwargs["messages"])
    assert kwargs["messages"][0]["role"] == "user"


def test_cache_stamps_control_on_system_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    tools = [
        {"name": "search", "description": "s", "input_schema": {"type": "object"}},
        {"name": "fetch", "description": "f", "input_schema": {"type": "object"}},
    ]
    prov.complete(
        [
            LLMMessage(role="system", content="STABLE PREFIX"),
            LLMMessage(role="user", content="q"),
        ],
        tier="heavy",
        tools=tools,
        cache=True,
    )
    _, kwargs = client.messages.create.call_args

    # cache_control stamped on the LAST system block
    assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
    # cache_control stamped on the LAST tool only (1 breakpoint for the tools block)
    assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kwargs["tools"][0]


def test_no_tool_cache_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # cache=False: the TOOLS breakpoint is NOT stamped (the explicit agent-loop
    # opt-in stays opt-in). The system-prefix breakpoint is E7's append-only
    # discipline and defaults ON — asserted separately below.
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    prov.complete(
        [LLMMessage(role="system", content="P"), LLMMessage(role="user", content="q")],
        tier="work",
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        cache=False,
    )
    _, kwargs = client.messages.create.call_args
    assert all("cache_control" not in t for t in kwargs["tools"])


# ── E7 — append-only prompt-cache discipline (headless AnthropicProvider) ─────
def test_e7_system_prefix_cached_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # E7: the STABLE prefix (the system block) carries a cache_control breakpoint
    # by DEFAULT — no cache= opt-in needed — so repeated headless calls (batched
    # reranker, N-sample vote, calibrate judge) hit the Anthropic prompt cache.
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    prov.complete(
        [LLMMessage(role="system", content="STABLE RERANK PROMPT"),
         LLMMessage(role="user", content="QUERY: q\nPASSAGES: ...")],
        tier="work",
    )
    _, kwargs = client.messages.create.call_args
    # The last (stable) system block is the cached prefix; variable user content
    # is in messages[] AFTER it (append-only — never before the cached prefix).
    assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["messages"][0]["role"] == "user"


def test_e7_no_crash_when_no_system_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # Degrade gracefully: a user-only call (no stable prefix) stamps nothing and
    # does not crash — there is simply no prefix to cache.
    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    prov = _provider(monkeypatch, client)

    resp = prov.complete([LLMMessage(role="user", content="q")], tier="work")
    _, kwargs = client.messages.create.call_args
    assert "system" not in kwargs or not kwargs.get("system")
    assert resp.text == "the answer"


def test_e7_prefix_cache_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # The discipline is disable-able (config flag) and degrades to no breakpoint
    # without breaking — for SDKs/models that don't support prompt caching.
    from bad_research.config import BadResearchConfig
    from bad_research.llm.anthropic import AnthropicProvider

    client = MagicMock()
    client.messages.create.return_value = _make_message_response()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    prov = AnthropicProvider(config=BadResearchConfig(prompt_cache=False))

    prov.complete(
        [LLMMessage(role="system", content="P"), LLMMessage(role="user", content="q")],
        tier="work",
    )
    _, kwargs = client.messages.create.call_args
    assert all("cache_control" not in b for b in kwargs["system"])


def test_tool_calls_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    resp_obj = _make_message_response(text="")
    resp_obj.content = [
        SimpleNamespace(type="text", text="let me search"),
        SimpleNamespace(
            type="tool_use", id="tu_1", name="search", input={"query": "x"}
        ),
    ]
    client.messages.create.return_value = resp_obj
    prov = _provider(monkeypatch, client)

    resp = prov.complete([LLMMessage(role="user", content="q")], tier="work")
    assert resp.text == "let me search"
    assert resp.tool_calls == [{"id": "tu_1", "name": "search", "input": {"query": "x"}}]
