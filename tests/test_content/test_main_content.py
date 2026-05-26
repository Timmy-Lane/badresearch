"""main_content — crawl4ai Pruning/BM25 readability + trafilatura fallback (dossier 12 §3)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from bad_research.web.content.fetch_clean import main_content, strip_boilerplate


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def test_pruning_keeps_dense_article(sample_html: str) -> None:
    stripped = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    out = main_content(stripped, query=None)
    assert "Retrieval-augmented generation combines a retriever" in _text(out)


def test_bm25_keeps_query_relevant(sample_html: str) -> None:
    stripped = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    out = main_content(stripped, query="chunk size and overlap")
    text = _text(out)
    assert "Chunk size and overlap matter" in text


def test_trafilatura_fallback_on_thin_pruning() -> None:
    # A page where the pruning filter would yield < 200 chars triggers the trafilatura
    # fallback (dossier 12 §3.5). A long single <p> in a bare doc still survives via fallback.
    body = "Recovery via trafilatura. " * 20  # ~ 520 chars
    html = f"<html><body><article><p>{body}</p></article></body></html>"
    out = main_content(html, query=None)
    assert "Recovery via trafilatura" in out


def test_returns_str() -> None:
    out = main_content("<html><body><p>hello world this is content padding padding "
                       "padding padding padding padding padding padding</p></body></html>")
    assert isinstance(out, str)
