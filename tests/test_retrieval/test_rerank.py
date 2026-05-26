"""ClaudeCodeReranker (KR-5) — the keyless DEFAULT reranker.

It SHARES the single frozen LLM-rerank prompt + the hardened parser created by
KR-2 in web/search/rerank.py (the brief's "ONE rerank prompt" rule). These tests
assert the shared-import identity, the prompt assembly, the JSON parse, graceful
0.0 degradation, and the get_reranker host/local/none factory — all keyless via
the FakeLLMProvider double (no network, no key)."""
import pytest

from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import (
    LLM_RERANK_SYSTEM,
    ClaudeCodeReranker,
    get_reranker,
)
from tests.test_retrieval.conftest import FakeLLMProvider


def test_one_frozen_prompt_is_shared_with_kr2_search_reranker():
    # The brief: there is ONE rerank prompt in the codebase. retrieval/rerank.py
    # re-exports the SAME object KR-2 froze in web/search/rerank.py — not a copy.
    from bad_research.web.search.rerank import LLM_RERANK_PROMPT_SYSTEM
    assert LLM_RERANK_SYSTEM is LLM_RERANK_PROMPT_SYSTEM


def test_claude_code_reranker_is_a_reranker():
    rr = ClaudeCodeReranker(llm=FakeLLMProvider(reply_text="[]"))
    assert isinstance(rr, Reranker)


def test_reranker_returns_empty_for_no_docs():
    rr = ClaudeCodeReranker(llm=FakeLLMProvider(reply_text="[]"))
    assert rr.rerank("q", []) == []


def test_prompt_contains_query_rubric_and_numbered_chunks():
    llm = FakeLLMProvider(reply_text='[{"i":0,"s":0.0},{"i":1,"s":1.0}]')
    rr = ClaudeCodeReranker(llm=llm)
    rr.rerank("why did they pick alpha=0.7", ["irrelevant text", "alpha=0.7 explained here"])
    # One batched call (dossier 15 §5.3 — all candidates in ONE host-model call).
    assert len(llm.calls) == 1
    sysmsg = llm.calls[0]["messages"][0]
    usermsg = llm.calls[0]["messages"][1]
    assert sysmsg.role == "system"
    # The frozen rubric anchors (verbatim from the ONE KR-2 LLM_RERANK_PROMPT_SYSTEM).
    assert "relevance scorer" in sysmsg.content
    assert "[0.00, 1.00]" in sysmsg.content
    assert '{"i": <int>, "s": <float>}' in sysmsg.content
    # The injection preamble is baked into the frozen prompt (KR-2).
    assert "UNTRUSTED external web content" in sysmsg.content
    # The user message carries the query + numbered chunks (0-based, matching the
    # KR-2 parser).
    assert "QUERY: why did they pick alpha=0.7" in usermsg.content
    assert "[0]" in usermsg.content and "[1]" in usermsg.content
    # Determinism: temperature=0 (dossier 15 §5.3).
    assert llm.calls[0]["temperature"] == 0


def test_scores_parsed_and_returned_descending():
    # Two chunks; the host says chunk index 1 is the most relevant.
    llm = FakeLLMProvider(reply_text='[{"i":0,"s":0.10},{"i":1,"s":0.90}]')
    rr = ClaudeCodeReranker(llm=llm)
    out = rr.rerank("q", ["a", "b"])
    assert out[0] == (1, 0.90)
    assert out[1] == (0, 0.10)


def test_chunks_truncated_to_trunc_chars_in_prompt():
    from bad_research.retrieval.constants import LLM_RERANK_TRUNC_CHARS
    llm = FakeLLMProvider(reply_text='[{"i":0,"s":0.5}]')
    rr = ClaudeCodeReranker(llm=llm)
    long_doc = "x" * (LLM_RERANK_TRUNC_CHARS + 500)
    rr.rerank("q", [long_doc])
    usermsg = llm.calls[0]["messages"][1].content
    # The 500 overflow chars never reach the prompt.
    assert ("x" * (LLM_RERANK_TRUNC_CHARS + 1)) not in usermsg
    assert ("x" * LLM_RERANK_TRUNC_CHARS) in usermsg


# ── get_reranker host/local/none ─────────────────────────────────────────────


def test_get_reranker_default_host_returns_claude_code():
    class _Cfg:
        reranker = "host"
    rr = get_reranker(_Cfg(), llm=FakeLLMProvider(reply_text="[]"))
    assert isinstance(rr, ClaudeCodeReranker)


def test_get_reranker_none_is_identity_sort_by_input_order():
    class _Cfg:
        reranker = "none"
    rr = get_reranker(_Cfg())
    # "none" → identity: input order preserved (the --no-rerank floor, §5.1).
    out = rr.rerank("q", ["a", "b", "c"])
    assert [i for i, _ in out] == [0, 1, 2]


def test_get_reranker_local_lazy_imports_bge():
    # "local" must NOT import torch at factory time when a scorer is injected (test-only path).
    class _Cfg:
        reranker = "local"
    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    out = rr.rerank("q", ["a", "b"])
    assert len(out) == 2
    # Stable tie-break by ascending index.
    assert [i for i, _ in out] == [0, 1]


def test_malformed_json_degrades_each_missing_chunk_to_zero():
    # Host returns a score only for chunk 0; chunk 1 missing → 0.0 (graceful, §5.3).
    llm = FakeLLMProvider(reply_text='[{"i":0,"s":0.8}]')
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b"]))
    assert out[0] == 0.8
    assert out[1] == 0.0


def test_entire_call_unparseable_returns_all_zero():
    # Whole reply is junk → every chunk 0.0 (engine then leans on `initial`, §5.3).
    llm = FakeLLMProvider(reply_text="sorry, I can't do that")
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b", "c"]))
    assert out == {0: 0.0, 1: 0.0, 2: 0.0}


def test_json_inside_markdown_fence_is_still_parsed():
    # Robustness: the model wraps the array in a ```json fence despite the instruction.
    llm = FakeLLMProvider(reply_text='```json\n[{"i":0,"s":0.4},{"i":1,"s":0.6}]\n```')
    rr = ClaudeCodeReranker(llm=llm)
    out = dict(rr.rerank("q", ["a", "b"]))
    assert out[0] == 0.4 and out[1] == 0.6


def test_llm_call_exception_degrades_to_all_zero():
    # If the host provider raises, retrieval must not crash — all 0.0 (§5.3).
    class _BoomLLM:
        name = "boom"

        def complete(self, *a, **k):
            raise RuntimeError("host model unavailable")

    rr = ClaudeCodeReranker(llm=_BoomLLM())
    out = dict(rr.rerank("q", ["a", "b"]))
    assert out == {0: 0.0, 1: 0.0}
