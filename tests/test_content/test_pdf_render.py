"""PDF page rendering -> PNG asset write/read path (host-vision multimodal rung).

A scanned / figure-dense PDF has no text layer, so pdf_to_markdown yields nothing
usable; the page's substance is in its pixels. These tests prove the rendering
helper (render_pdf_pages -> page.get_pixmap) produces a real PNG, that
save_pdf_page_assets persists it as an `assets` row + on-disk file, and that the
`bad assets` CLI resolves it back to a readable PNG.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bad_research.core.db import (
    get_asset,
    init_schema,
    insert_asset,
    list_assets,
)
from bad_research.web.content.fetch_clean import (
    PDF_PAGE_TEXT_FLOOR,
    page_is_figure_dense,
    pdf_to_markdown,
    render_pdf_pages,
)


def _figure_dense_pdf() -> bytes:
    """A 2-page PDF: page 0 is figure-dense (a drawn chart, ~no text), page 1 is
    a normal text page. Built with pymupdf so the test needs no fixtures."""
    import pymupdf  # fitz

    doc = pymupdf.open()
    # page 0 — a "chart": filled rectangles, a couple of axis ticks, NO prose.
    p0 = doc.new_page()
    for i, h in enumerate((40, 90, 60, 120)):
        x = 80 + i * 60
        p0.draw_rect(pymupdf.Rect(x, 300 - h, x + 40, 300), fill=(0.2, 0.4, 0.8))
    p0.insert_text((80, 320), "42", fontsize=8)  # < PDF_PAGE_TEXT_FLOOR chars
    # page 1 — a real text page with plenty of extractable text.
    p1 = doc.new_page()
    p1.insert_text(
        (72, 72),
        "This page has a full text layer with many readable words for extraction. " * 4,
        fontsize=10,
    )
    data = doc.tobytes()
    doc.close()
    return data


def _all_image_pdf() -> bytes:
    """A 1-page PDF whose only content is a drawn figure (no text at all) — the
    'scanned, text-layerless' case where the whole doc must be rendered."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_circle(pymupdf.Point(200, 200), 80, fill=(0.9, 0.1, 0.1))
    data = doc.tobytes()
    doc.close()
    return data


def test_page_is_figure_dense_flags_textless_page() -> None:
    import pymupdf

    doc = pymupdf.open(stream=_figure_dense_pdf(), filetype="pdf")
    pages = list(doc)
    assert page_is_figure_dense(pages[0]) is True   # the chart page
    assert page_is_figure_dense(pages[1]) is False  # the text page
    doc.close()


def test_render_pdf_pages_only_figure_dense_renders_chart_page_png() -> None:
    rendered = render_pdf_pages(_figure_dense_pdf(), only_figure_dense=True)
    # only the figure-dense page 0 is rendered; the text page is skipped.
    assert len(rendered) == 1
    entry = rendered[0]
    assert entry["page"] == 0
    assert entry["text_chars"] < PDF_PAGE_TEXT_FLOOR
    png = entry["png"]
    assert isinstance(png, bytes)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG magic header


def test_render_pdf_pages_all_pages_when_not_only_figure_dense() -> None:
    rendered = render_pdf_pages(_figure_dense_pdf(), only_figure_dense=False)
    assert {e["page"] for e in rendered} == {0, 1}


def test_render_pdf_pages_empty_on_garbage() -> None:
    assert render_pdf_pages(b"not a pdf at all") == []


def test_text_layerless_pdf_renders_when_markdown_is_empty() -> None:
    pdf = _all_image_pdf()
    # The text layer is empty -> pdf_to_markdown yields no real prose (pymupdf4llm
    # emits only an "image intentionally omitted" placeholder), which is exactly the
    # signal that the substance lives in the pixels and the page must be rendered.
    md = pdf_to_markdown(pdf)
    assert "intentionally omitted" in md or md.strip() == ""
    # ...so the page MUST be rendered for the host-vision path.
    rendered = render_pdf_pages(pdf, only_figure_dense=True)
    assert len(rendered) == 1
    assert rendered[0]["png"][:4] == b"\x89PNG"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _seed_note(conn: sqlite3.Connection, note_id: str) -> None:
    """Insert a minimal note row so the assets FK (note_id -> notes.id) holds."""
    conn.execute(
        "INSERT INTO notes (id, title, path, created, file_mtime, content_hash, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (note_id, "T", f"research/notes/{note_id}.md", "2026-06-01", 0.0, "h", "2026-06-01"),
    )
    conn.commit()


def test_insert_asset_round_trips() -> None:
    conn = _conn()
    _seed_note(conn, "n1")
    aid = insert_asset(
        conn,
        note_id="n1",
        filename="research/assets/n1/page-000-abcd.png",
        type="image",
        content_type="image/png",
        size_bytes=1234,
    )
    assert aid > 0
    got = get_asset(conn, aid)
    assert got is not None
    assert got.note_id == "n1"
    assert got.type == "image"
    assert got.filename == "research/assets/n1/page-000-abcd.png"
    assert got.size_bytes == 1234
    # listing + filtering
    assert len(list_assets(conn)) == 1
    assert len(list_assets(conn, note_id="n1", type="image")) == 1
    assert len(list_assets(conn, type="screenshot")) == 0


def test_insert_asset_rejects_bad_type() -> None:
    conn = _conn()
    _seed_note(conn, "n1")
    with pytest.raises(ValueError):
        insert_asset(conn, note_id="n1", filename="x.png", type="bogus")


def test_save_pdf_page_assets_persists_png_and_row(tmp_path: Path) -> None:
    from bad_research.cli.assets import save_pdf_page_assets

    conn = _conn()
    _seed_note(conn, "noteA")
    assets_dir = tmp_path / "research" / "assets" / "noteA"
    saved = save_pdf_page_assets(
        conn, "noteA", _figure_dense_pdf(), assets_dir, url="http://x/scan.pdf"
    )
    assert len(saved) == 1  # only the figure-dense page
    rec = saved[0]
    # The PNG file is real and readable.
    png_file = assets_dir / Path(rec["path"]).name
    assert png_file.exists()
    assert png_file.read_bytes()[:4] == b"\x89PNG"
    # An assets row was INSERTed (type='image', the figure-dense page).
    rows = list_assets(conn, note_id="noteA")
    assert len(rows) == 1
    assert rows[0].type == "image"
    assert rows[0].url == "http://x/scan.pdf"
    assert rows[0].id == rec["id"]


def test_persist_screenshot_writes_asset(tmp_path: Path) -> None:
    from bad_research.web.crawl4ai_provider import persist_screenshot

    conn = _conn()
    _seed_note(conn, "shotnote")
    # a minimal valid PNG (1x1) — proves the screenshot bytes become an asset row.
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    assets_dir = tmp_path / "research" / "assets" / "shotnote"
    manifest = persist_screenshot(conn, "shotnote", png, assets_dir, url="http://x")
    assert manifest is not None
    assert manifest["type"] == "screenshot"
    rows = list_assets(conn, note_id="shotnote", type="screenshot")
    assert len(rows) == 1
    saved_file = assets_dir / Path(rows[0].filename).name
    assert saved_file.exists()
    assert saved_file.read_bytes()[:4] == b"\x89PNG"
    # No screenshot bytes -> no row, no crash.
    assert persist_screenshot(conn, "shotnote", None, assets_dir) is None
