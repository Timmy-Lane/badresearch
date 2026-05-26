"""HostModelReranker: prompt assembly + JSON-score parse + graceful 0.0."""

from __future__ import annotations

from bad_research.llm.base import LLMMessage, LLMResponse
from bad_research.web.search.rerank import (
    INJECTION_PREAMBLE,
    LLM_RERANK_PROMPT_SYSTEM,
    HostModelReranker,
    _parse_scores,
)


class _StubLLM:
    name = "stub"

    def __init__(self, text):
        self._text = text
        self.calls = []

    def complete(self, messages, *, tier="work", tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        self.calls.append((messages, tier, temperature))
        return LLMResponse(text=self._text, model="stub")


def test_prompt_constants_have_injection_and_rubric():
    assert "UNTRUSTED" in INJECTION_PREAMBLE
    # the 0.0/0.1/0.4/0.7/1.0 rubric (dossier 13 §4.1)
    for anchor in ("1.00", "0.70", "0.30", "0.00"):
        assert anchor in LLM_RERANK_PROMPT_SYSTEM


def test_rerank_parses_scores_and_returns_idx_desc():
    llm = _StubLLM('[{"i":0,"s":0.2},{"i":1,"s":0.9}]')
    rr = HostModelReranker(llm=llm)
    out = rr.rerank("query", ["doc zero", "doc one"])
    assert out == [(1, 0.9), (0, 0.2)]   # sorted desc by score
    # temperature=0 for determinism; one batched call
    assert len(llm.calls) == 1
    _, _, temp = llm.calls[0]
    assert temp == 0.0


def test_rerank_assembles_query_and_numbered_passages():
    llm = _StubLLM('[{"i":0,"s":1.0}]')
    HostModelReranker(llm=llm).rerank("what is RRF?", ["RRF fuses ranked lists"])
    msgs, _, _ = llm.calls[0]
    system = next(m for m in msgs if m.role == "system").content
    user = next(m for m in msgs if m.role == "user").content
    assert "UNTRUSTED" in system
    assert "what is RRF?" in user
    assert "[0]" in user            # numbered passage
    assert "RRF fuses ranked lists" in user


def test_rerank_truncates_long_passages_to_800_chars():
    llm = _StubLLM('[{"i":0,"s":0.5}]')
    long_doc = "x" * 5000
    HostModelReranker(llm=llm).rerank("q", [long_doc])
    user = next(m for m in llm.calls[0][0] if m.role == "user").content
    assert "x" * 800 in user
    assert "x" * 801 not in user


def test_rerank_caps_batch_at_top_n():
    llm = _StubLLM("[]")
    docs = [f"d{i}" for i in range(50)]
    HostModelReranker(llm=llm, top_n=30).rerank("q", docs)
    user = next(m for m in llm.calls[0][0] if m.role == "user").content
    assert "[29]" in user and "[30]" not in user


def test_rerank_malformed_item_scores_zero():
    # missing one id, one non-numeric score → both default 0.0, still 3 rows
    llm = _StubLLM('[{"i":0,"s":0.8},{"i":1,"s":"bad"}]')
    out = HostModelReranker(llm=llm).rerank("q", ["a", "b", "c"])
    by_idx = dict(out)
    assert by_idx[0] == 0.8
    assert by_idx[1] == 0.0   # non-numeric → 0.0
    assert by_idx[2] == 0.0   # absent from response → 0.0
    assert len(out) == 3


def test_parse_scores_accepts_id_and_score_keys():
    assert _parse_scores('[{"id":0,"score":0.5}]', n=1) == [0.5]


def test_parse_scores_strips_json_code_fence():
    raw = '```json\n[{"i":0,"s":0.9},{"i":1,"s":0.3}]\n```'
    assert _parse_scores(raw, n=2) == [0.9, 0.3]


def test_parse_scores_ignores_stray_leading_bracket_in_prose():
    # a real model: "[0] is the best, then [1]." before the real array.
    raw = 'Passage [0] is best, then [1]. Scores: [{"i":0,"s":1.0},{"i":1,"s":0.4}]'
    assert _parse_scores(raw, n=2) == [1.0, 0.4]


def test_parse_scores_tolerates_trailing_comma():
    assert _parse_scores('[{"i":0,"s":0.7},{"i":1,"s":0.5},]', n=2) == [0.7, 0.5]


def test_parse_scores_recovers_complete_objects_from_truncated_array():
    # max_tokens cut the stream mid-object: leading complete items still score.
    raw = '[{"i":0,"s":0.9},{"i":1,"s":0.6},{"i":2,"s":'
    assert _parse_scores(raw, n=3) == [0.9, 0.6, 0.0]


def test_parse_scores_unparseable_degrades_to_zeros():
    assert _parse_scores("I cannot score these passages.", n=3) == [0.0, 0.0, 0.0]


def test_rerank_fenced_output_degrades_to_input_order_only_when_unparseable():
    # fenced + valid → real scores (not the all-0.0 input-order fallback)
    llm = _StubLLM('```json\n[{"i":0,"s":0.2},{"i":1,"s":0.95}]\n```')
    out = HostModelReranker(llm=llm).rerank("q", ["a", "b"])
    assert out == [(1, 0.95), (0, 0.2)]


def test_rerank_empty_docs():
    assert HostModelReranker(llm=_StubLLM("[]")).rerank("q", []) == []
