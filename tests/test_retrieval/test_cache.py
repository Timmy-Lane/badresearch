from bad_research.retrieval.cache import SemanticCache, has_negation


def test_has_negation_detects_markers():
    assert has_negation("how does X work without async")
    assert has_negation("X but NOT in no_std")
    assert has_negation("this isn't supported")
    assert not has_negation("how does X wrap source chains")


def test_cache_hit_on_paraphrase(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function wrap chains", {"answer": "A"})
    # Paraphrase with heavy token overlap → cosine >= 0.92 under the stub → HIT.
    hit = cache.get("how does function wrap chains")
    assert hit is not None
    assert hit["payload"] == {"answer": "A"}
    assert hit["cache_similarity"] >= 0.92


def test_cache_miss_when_negation_added(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function wrap chains", {"answer": "A"})
    # Same tokens + a NEGATION word the cached query lacked → forced MISS,
    # even if the raw cosine would clear 0.92 (NIA negation-blindness fix §4.3).
    assert cache.get("how does function NOT wrap chains") is None


def test_cache_miss_on_different_topic(tmp_path, stub_embedder):
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("alpha beta gamma delta", {"answer": "A"})
    assert cache.get("zeta eta theta iota") is None


def test_cache_negation_to_negation_can_hit(tmp_path, stub_embedder):
    # If BOTH queries carry negation, the guard does not force a miss —
    # they are semantically aligned on the negation.
    cache = SemanticCache(tmp_path / "cache.db", stub_embedder)
    cache.put("how does function NOT wrap chains", {"answer": "neg"})
    hit = cache.get("how does function NOT wrap chains")
    assert hit is not None and hit["payload"] == {"answer": "neg"}
