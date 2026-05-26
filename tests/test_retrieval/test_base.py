from dataclasses import fields

from bad_research.retrieval.base import Chunk, Reranker, RetrievalEngine


def test_chunk_shape_matches_interfaces():
    names = {f.name for f in fields(Chunk)}
    assert names == {"chunk_id", "note_id", "text", "char_start", "char_end", "score", "source_id"}
    c = Chunk(chunk_id="a", note_id="n", text="t", char_start=0, char_end=1, score=0.5, source_id="s")
    assert c.score == 0.5 and c.char_end == 1


def test_reranker_is_protocol_with_rerank():
    # A class implementing rerank(query, docs) -> list[tuple[int,float]] is a Reranker
    class _Dummy:
        def rerank(self, query, docs):
            return [(i, 1.0 - i / 10) for i, _ in enumerate(docs)]
    assert isinstance(_Dummy(), Reranker)


def test_retrieval_engine_has_index_and_search():
    assert hasattr(RetrievalEngine, "index")
    assert hasattr(RetrievalEngine, "search")
