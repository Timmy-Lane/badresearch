from bad_research.retrieval.store import LanceChunkStore


def _rows(embedder, texts):
    vecs = embedder.embed(texts, input_type="document")
    return [
        {"chunk_id": f"c{i}", "vector": vecs[i], "note_id": f"n{i}",
         "char_start": 0, "char_end": len(texts[i]), "model": embedder.name, "dim": embedder.dim}
        for i in range(len(texts))
    ]


def test_create_and_count(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha beta", "gamma delta"]))
    assert store.count() == 2


def test_upsert_is_idempotent_on_chunk_id(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    rows = _rows(stub_embedder, ["alpha beta"])
    store.upsert(rows)
    store.upsert(rows)  # same chunk_id again
    assert store.count() == 1


def test_flat_vector_search_returns_nearest_first(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha alpha alpha", "zeta zeta zeta", "alpha beta"]))
    qv = stub_embedder.embed(["alpha alpha alpha"], input_type="query")[0]
    hits = store.search_vector(qv, top_k=3)
    # Each hit is (chunk_id, distance). Nearest (identical token-bag) is first.
    assert hits[0][0] == "c0"
    # Sorted ascending by distance.
    dists = [d for _, d in hits]
    assert dists == sorted(dists)


def test_search_returns_scores_in_unit_range_via_cosine(tmp_path, stub_embedder):
    store = LanceChunkStore(tmp_path / "lance", dim=stub_embedder.dim)
    store.upsert(_rows(stub_embedder, ["alpha beta gamma"]))
    qv = stub_embedder.embed(["alpha beta gamma"], input_type="query")[0]
    hits = store.search_vector(qv, top_k=1)
    cid, dist = hits[0]
    # Identical vectors → cosine distance ~0.
    assert cid == "c0"
    assert dist < 1e-3


def test_to_score_converts_cosine_distance_to_similarity():
    # similarity = 1 - distance, clamped to [0,1].
    assert abs(LanceChunkStore.distance_to_score(0.0) - 1.0) < 1e-9
    assert abs(LanceChunkStore.distance_to_score(1.0) - 0.0) < 1e-9
    assert LanceChunkStore.distance_to_score(2.0) == 0.0
