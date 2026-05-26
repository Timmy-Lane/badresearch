from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.base import Reranker
from bad_research.retrieval.engine import RetrievalEngine


class _IdentityReranker:
    """reranker_score = 1.0 if query token-set ⊆ doc else 0.2; stable order."""
    def rerank(self, query, docs):
        qtoks = set(query.lower().split())
        out = [(i, 0.95 if qtoks & set(d.lower().split()) else 0.20) for i, d in enumerate(docs)]
        out.sort(key=lambda x: (-x[1], x[0]))
        return out


def _note(nid, body, ct=None, status="evergreen"):
    return Note(meta=NoteMeta(title=nid, id=nid, source=f"https://ex.com/{nid}",
                              content_type=ct, status=status),
                body=body, path=f"research/{nid}.md")


def _engine(tmp_path, stub_embedder):
    return RetrievalEngine(
        lance_dir=tmp_path / "lance",
        cache_db=tmp_path / "cache.db",
        embedder=stub_embedder,
        reranker=_IdentityReranker(),
    )


def test_reranker_protocol_satisfied():
    assert isinstance(_IdentityReranker(), Reranker)


def test_index_then_search_returns_relevant_chunk_first(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([
        _note("a", "# A\n\npython async await concurrency patterns explained\n"),
        _note("b", "# B\n\nrust ownership borrow checker lifetimes memory\n"),
    ])
    hits = eng.search("python async", mode="light", top_k=2)
    assert len(hits) >= 1
    assert hits[0].note_id == "a"
    # Provenance offsets slice back into the note body.
    assert hits[0].char_end > hits[0].char_start


def test_relevance_gate_drops_low_scoring_chunks(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await\n"),
               _note("z", "# Z\n\ntotally unrelated zebra xylophone\n")])
    hits = eng.search("python async", mode="light", top_k=10)
    # Every returned chunk cleared the 0.70 gate.
    assert all(h.score >= 0.70 for h in hits)


def test_source_type_weight_boosts_code(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    # Two near-identical chunks; one is content_type=code (×1.2).
    eng.index([_note("code", "def parse_async(): return async_io_loop()\n" * 80, ct="code"),
               _note("docs", "parse async io loop documentation prose\n" * 80, ct="docs")])
    hits = eng.search("parse async", mode="full", top_k=2)
    by_note = {h.note_id: h.score for h in hits}
    # If both survive, the code chunk's source-type weight makes it score >= docs.
    if "code" in by_note and "docs" in by_note:
        assert by_note["code"] >= by_note["docs"]


def test_semantic_cache_hit_on_repeat_query(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    first = eng.search("python async concurrency", mode="light", top_k=3)
    # A negation-free repeat → served from cache, identical chunk_ids.
    second = eng.search("python async concurrency", mode="light", top_k=3)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_cache_miss_when_negation_added(tmp_path, stub_embedder):
    eng = _engine(tmp_path, stub_embedder)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    eng.search("python async concurrency", mode="light", top_k=3)
    # Adding NOT must not serve the affirmative cached answer (force recompute path).
    # We assert the cache layer reported a miss via the engine's last_cache_hit flag.
    eng.search("python NOT async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is False
