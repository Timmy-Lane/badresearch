"""extract_metadata + extract_published_date — verbatim extractMetadata.ts (dossier 12 §8)."""

from __future__ import annotations

from bad_research.web.content.fetch_clean import extract_metadata, extract_published_date


def test_extract_metadata_core_fields(sample_html: str) -> None:
    meta = extract_metadata(sample_html, "https://ex.com/post")
    assert meta["title"] == "How Retrieval-Augmented Generation Works"
    assert meta["description"] == "A deep dive into RAG pipelines."
    assert meta["keywords"] == "rag, retrieval, llm"
    assert meta.get("language") == "en"
    assert meta.get("og:title") == "RAG Explained"


def test_published_date_from_article_meta(sample_html: str) -> None:
    d = extract_published_date(sample_html)
    assert d is not None
    assert d.startswith("2024-03-15")


def test_published_date_time_tag_fallback() -> None:
    html = '<html><body><time datetime="2023-01-02T00:00:00Z">Jan 2</time></body></html>'
    d = extract_published_date(html)
    assert d is not None
    assert d.startswith("2023-01-02")


def test_published_date_visible_text_fallback() -> None:
    html = "<html><body><p>Published on 2022-07-08 by the team.</p></body></html>"
    d = extract_published_date(html)
    assert d is not None
    assert d.startswith("2022-07-08")


def test_published_date_none_when_absent() -> None:
    html = "<html><body><p>No date here at all, just prose.</p></body></html>"
    assert extract_published_date(html) is None


def test_param_renamed_to_html(sample_html: str) -> None:
    # FIX 4: the param is `html` (the pipeline passes FULL html, not stripped — see
    # the fetch_clean call site), so the keyword call must work.
    meta = extract_metadata(html=sample_html, url="https://ex.com/post")
    assert meta["title"] == "How Retrieval-Augmented Generation Works"
    d = extract_published_date(html=sample_html)
    assert d is not None and d.startswith("2024-03-15")
