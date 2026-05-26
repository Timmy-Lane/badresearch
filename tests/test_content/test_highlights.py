"""highlights — BM25 sliding-window query-biased passages (dossier 12 §7)."""

from __future__ import annotations

from bad_research.web.content.fetch_clean import highlights


def test_returns_top_k_with_scores() -> None:
    md = ("The caching layer stores results in sqlite with a 14 day ttl. " * 5
          + "Unrelated filler about weather and sports. " * 20
          + "Cache eviction uses an lru policy keyed by url hash. " * 5)
    hl = highlights(md, query="cache eviction policy", k=3)
    assert len(hl) <= 3
    assert all("text" in h and "score" in h for h in hl)
    # the eviction passage outranks the weather filler
    top = hl[0]["text"].lower()
    assert "eviction" in top or "cache" in top


def test_char_cap() -> None:
    md = "word " * 500
    hl = highlights(md, query="word", k=1)
    assert len(hl[0]["text"]) <= 500


def test_empty_markdown() -> None:
    hl = highlights("", query="anything", k=3)
    assert hl == [] or all("text" in h for h in hl)
