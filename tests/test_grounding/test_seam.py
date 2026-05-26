from __future__ import annotations

from bad_research.llm.base import LLMMessage, LLMProvider, LLMResponse


def test_llm_seam_protocol_shape(fake_llm):
    # fake_llm is a fixture satisfying the LLMProvider Protocol structurally.
    assert isinstance(fake_llm, LLMProvider)
    resp = fake_llm.complete([LLMMessage(role="user", content="hi")], tier="triage")
    assert isinstance(resp, LLMResponse)
    assert resp.text == "[]"  # fake returns empty JSON list by default
