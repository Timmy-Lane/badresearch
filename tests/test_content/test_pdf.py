"""pdf_to_markdown — pymupdf4llm (dossier 12 §5)."""

from __future__ import annotations

from bad_research.web.content.fetch_clean import pdf_to_markdown


def test_pdf_to_markdown_extracts_text(sample_pdf_bytes: bytes) -> None:
    md = pdf_to_markdown(sample_pdf_bytes)
    assert isinstance(md, str)
    assert "Keyless PDF Extraction" in md
    assert "pymupdf4llm markdown conversion" in md


def test_pdf_to_markdown_empty_on_garbage() -> None:
    # Non-PDF bytes must not crash — returns empty string (caller treats as junk).
    md = pdf_to_markdown(b"not a pdf at all")
    assert md == ""
