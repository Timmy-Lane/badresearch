import pytest

from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import BGEReranker, ClaudeCodeReranker, get_reranker


def test_claude_code_reranker_is_a_reranker() -> None:
    rr = ClaudeCodeReranker()
    assert isinstance(rr, Reranker)


def test_claude_code_reranker_rerank_is_kr5_stub() -> None:
    """KR-1 ships the type; KR-5 fills the host-model body."""
    rr = ClaudeCodeReranker()
    with pytest.raises(NotImplementedError, match="KR-5"):
        rr.rerank("q", ["a", "b"])


def test_get_reranker_default_is_host() -> None:
    class _Cfg:
        reranker = "host"

    rr = get_reranker(_Cfg())
    assert isinstance(rr, ClaudeCodeReranker)


def test_get_reranker_none_is_identity() -> None:
    class _Cfg:
        reranker = "none"

    rr = get_reranker(_Cfg())
    out = rr.rerank("q", ["a", "b", "c"])
    # identity: original order, descending pseudo-scores, stable.
    assert [i for i, _ in out] == [0, 1, 2]
    assert len(out) == 3


def test_get_reranker_local_is_bge_with_injected_scorer() -> None:
    class _Cfg:
        reranker = "local"

    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    assert isinstance(rr, BGEReranker)
    out = rr.rerank("q", ["a", "b", "c"])
    assert [i for i, _ in out] == [0, 1, 2]  # ties -> stable index order
