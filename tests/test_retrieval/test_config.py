from bad_research.config import BadResearchConfig
from bad_research.retrieval import constants as C


def test_config_retrieval_defaults_match_frozen_constants():
    cfg = BadResearchConfig()
    assert cfg.retrieval_alpha == C.ALPHA
    assert cfg.relevance_gate == C.RELEVANCE_GATE
    assert cfg.semantic_cache_threshold == C.SEMANTIC_CACHE_THRESHOLD
    assert cfg.top_k_retrieve == C.TOP_K_RETRIEVE


def test_config_retrieval_overridable():
    cfg = BadResearchConfig(retrieval_alpha=0.5)
    assert cfg.retrieval_alpha == 0.5
