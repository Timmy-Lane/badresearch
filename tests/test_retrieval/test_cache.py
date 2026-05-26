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


# ── LexicalCacheBackend (token-set overlap 0.85) + get_cache selector ─────────


def test_lexical_cache_hit_on_token_reorder(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("python async concurrency patterns", {"answer": "A"})
    # Same token set, reordered → overlap 1.0 → HIT (dossier 15 §6.2, NIA 0.9701 case).
    hit = cache.get("concurrency patterns python async")
    assert hit is not None and hit["payload"] == {"answer": "A"}


def test_lexical_cache_hit_on_suffix_noise(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("binary quantization memory", {"answer": "B"})
    # Superset query (extra tokens) → overlap-coefficient ignores the larger side → HIT
    # (matches NIA's +9-token suffix-noise 0.9242 case).
    hit = cache.get("binary quantization memory reduction sixteen times faster lookup")
    assert hit is not None and hit["payload"] == {"answer": "B"}


def test_lexical_cache_miss_on_paraphrase(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("how to cut vector RAM", {"answer": "C"})
    # Zero content-token overlap → MISS (just re-runs, never a wrong answer; §6.2).
    assert cache.get("binary quantization reduced memory sixteen fold") is None


def test_lexical_cache_miss_when_negation_added(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend
    cache = LexicalCacheBackend(tmp_path / "lex.db")
    cache.put("does it support async in no_std", {"answer": "yes"})
    # The negation guard forces a miss even if token overlap clears 0.85 (§6.2 belt-and-suspenders).
    assert cache.get("does it NOT support async in no_std") is None


def test_get_cache_selects_lexical_when_no_embedder(tmp_path):
    from bad_research.retrieval.cache import LexicalCacheBackend, get_cache
    cache = get_cache(tmp_path / "c.db", embedder=None)
    assert isinstance(cache, LexicalCacheBackend)


def test_get_cache_selects_cosine_when_embedder_present(tmp_path, stub_embedder):
    from bad_research.retrieval.cache import SemanticCache, get_cache
    cache = get_cache(tmp_path / "c.db", embedder=stub_embedder)
    assert isinstance(cache, SemanticCache)
