from bad_research.retrieval import constants as C


def test_frozen_constants_match_interfaces():
    assert C.ALPHA == 0.7
    assert C.TOP_K_RETRIEVE == 30
    assert C.RETRIEVAL_WEIGHT == {3: 0.75, 10: 0.60}
    assert C.DEEP_RANK_PENALTY == 0.005
    assert C.RELEVANCE_GATE == 0.70
    assert C.RERETRIEVE_PASS_FRACTION == 0.30
    assert C.RERETRIEVE_MAX_ROUNDS == 2
    assert C.SEMANTIC_CACHE_THRESHOLD == 0.92
    assert C.RRF_K == 60
    assert C.SOURCE_TYPE_WEIGHT["code"] == 1.2
    assert C.SOURCE_TYPE_WEIGHT["docs"] == 1.0
    assert C.SOURCE_TYPE_WEIGHT["paper"] == 0.9
    assert C.DEFAULT_SOURCE_TYPE_WEIGHT == 1.0
    assert (C.BM25_TITLE_WEIGHT, C.BM25_BODY_WEIGHT, C.BM25_TAGS_WEIGHT, C.BM25_ALIASES_WEIGHT) == (10.0, 1.0, 5.0, 3.0)
    assert C.BM25_STATUS_MULT == {"evergreen": 1.5, "stale": 0.7, "deprecated": 0.3}
    assert C.EMBED_TRUNC_CHARS == 16384
    assert C.EMBED_BATCH_CAP == 96
    assert C.LANCE_INDEX_MIN_ROWS == 256
    assert C.RRF_K == 60


def test_kr5_keyless_constants_present_and_exact():
    # dossier 15 §6.2 — token-set lexical cache threshold (looser than the 0.92 cosine).
    assert C.SEMANTIC_CACHE_THRESHOLD_LEXICAL == 0.85
    # dossier 15 §4.3 — auto-enable the [local] dense lane above this chunk count.
    assert C.NEURAL_RECALL_VAULT_THRESHOLD == 25_000
    # dossier 15 §5.3 — the rerank truncation (800) + batch (30) live at their single
    # source (web/search/rerank.py, KR-2's frozen prompt module); assert them there,
    # not as a dormant duplicate here.
    from bad_research.web.search import rerank as _w

    assert _w.LLM_RERANK_TRUNC_CHARS == 800
    assert _w.LLM_RERANK_BATCH == 30
    assert not hasattr(C, "LLM_RERANK_TRUNC_CHARS")  # no dormant duplicate in constants.py
    # The kept cosine threshold must still be 0.92 (used only under [local]).
    assert C.SEMANTIC_CACHE_THRESHOLD == 0.92
    # Stopwords for lexical-cache token normalization (dossier 15 §6.2).
    assert "how" in C.LLM_RERANK_STOPWORDS and "async" not in C.LLM_RERANK_STOPWORDS
