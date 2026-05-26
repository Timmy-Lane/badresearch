from bad_research.retrieval.base import Reranker
from bad_research.retrieval.rerank import CohereReranker, get_reranker


class _FakeCohereResp:
    def __init__(self, results):
        self.results = results


class _FakeResult:
    def __init__(self, index, relevance_score):
        self.index = index
        self.relevance_score = relevance_score


class _FakeCohereClient:
    """Mimics cohere.ClientV2.rerank: returns results sorted by relevance desc."""
    def __init__(self):
        self.calls = []

    def rerank(self, *, model, query, documents, top_n=None):
        self.calls.append({"model": model, "query": query, "n": len(documents)})
        # Deterministic fake: score = 1.0 for the doc containing 'match', else 0.1,
        # returned already sorted desc (as Cohere does).
        scored = [(i, 0.95 if "match" in d else 0.10) for i, d in enumerate(documents)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return _FakeCohereResp([_FakeResult(i, s) for i, s in scored])


def test_cohere_reranker_is_a_reranker_and_orders_by_relevance():
    client = _FakeCohereClient()
    rr = CohereReranker(model="rerank-v3.5", client=client)
    assert isinstance(rr, Reranker)
    docs = ["nope one", "the match here", "nope two"]
    out = rr.rerank("find the match", docs)
    # (idx, score) desc; the 'match' doc (index 1) ranks first.
    assert out[0][0] == 1
    assert out[0][1] == 0.95
    assert [i for i, _ in out] == [1, 0, 2] or [i for i, _ in out][0] == 1
    # The full candidate set is reranked (NIA: reranks ALL 30), not truncated.
    assert client.calls[0]["n"] == 3
    assert client.calls[0]["model"] == "rerank-v3.5"


def test_get_reranker_prefers_cohere_when_key_present(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test-key")

    class _Cfg:
        rerank_model = "rerank-v3.5"

    rr = get_reranker(_Cfg(), client=_FakeCohereClient())
    assert isinstance(rr, CohereReranker)


def test_get_reranker_falls_back_to_bge_when_model_is_bge():
    class _Cfg:
        rerank_model = "bge-reranker-v2-m3"

    rr = get_reranker(_Cfg(), bge_scorer=lambda pairs: [0.3] * len(pairs))
    out = rr.rerank("q", ["a", "b", "c"])
    assert isinstance(rr, Reranker)
    assert len(out) == 3
    # ties broken by stable index order.
    assert [i for i, _ in out] == [0, 1, 2]
