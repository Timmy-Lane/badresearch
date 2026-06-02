"""Tests for export.html — full-document render + resolved References appendix."""

from __future__ import annotations

import re

from bad_research.export import export_report, render_report_html, source_refs_from_notes

_SOURCES = {
    "solar-note": '---\ntitle: "IEA Renewables 2023"\nsource: "https://iea.org/r"\n---\n\nbody',
    "wind-note": '---\ntitle: "GWEC Wind Report"\nsource: "https://gwec.net/w"\n---\n\nbody',
}

_REPORT = (
    "# Energy Report\n\n"
    "Solar grew 24 percent [[solar-note]].\n"
    "Wind grew 15 percent [[wind-note]].\n"
    "Projections continue [1].\n"
)


def test_render_report_html_resolves_markers_to_anchors():
    refs = source_refs_from_notes(_SOURCES)
    doc, resolved = render_report_html(_REPORT, refs)
    # No bare [[note-id]] wiki-link tokens remain in the body prose.
    assert "[[solar-note]]" not in doc
    assert "[[wind-note]]" not in doc
    # Every in-text marker is a clickable superscript anchor into the appendix.
    assert '<sup class="cite"><a href="#ref-1">[1]</a></sup>' in doc
    assert '<sup class="cite"><a href="#ref-3">[3]</a></sup>' in doc
    # The References section carries the resolved titles + urls + anchor ids.
    assert 'id="ref-1"' in doc
    assert "IEA Renewables 2023" in doc
    assert "https://iea.org/r" in doc
    assert len(resolved) == 3


def test_render_report_html_no_bare_numeric_markers_outside_sup():
    refs = source_refs_from_notes(_SOURCES)
    doc, _ = render_report_html(_REPORT, refs)
    # Strip the <sup>...</sup> spans; no bare [N] should survive in the prose body.
    body = doc.split('<section class="references">')[0]
    stripped = re.sub(r'<sup class="cite">.*?</sup>', "", body)
    assert not re.search(r"\[\d+\]", stripped)
    assert not re.search(r"\[\[[^\]]+\]\]", stripped)


def test_render_report_html_title_inferred_from_h1():
    doc, _ = render_report_html(_REPORT, source_refs_from_notes(_SOURCES))
    assert "<title>Energy Report</title>" in doc


def test_export_report_writes_html_and_audit(tmp_path):
    out_html = tmp_path / "report.html"
    result = export_report(_REPORT, source_refs_from_notes(_SOURCES), out_html)
    assert out_html.is_file()
    assert result.n_markers == 3
    assert result.n_resolved == 3
    assert result.n_dangling == 0
    assert result.pdf_path is None  # not requested


def test_export_report_dangling_marker_is_disclosed_not_dropped(tmp_path):
    out_html = tmp_path / "r.html"
    md = "# T\n\nClaim [[ghost-note]].\n"
    result = export_report(md, source_refs_from_notes(_SOURCES), out_html)
    assert result.n_markers == 1
    assert result.n_dangling == 1
    doc = out_html.read_text(encoding="utf-8")
    assert "unresolved citation" in doc


def test_export_report_pdf_when_pymupdf_available(tmp_path):
    import importlib.util

    if importlib.util.find_spec("fitz") is None:
        # pymupdf absent -> export degrades to HTML-only (no new dep). Assert that.
        out_html = tmp_path / "r.html"
        result = export_report(
            _REPORT, source_refs_from_notes(_SOURCES), out_html, out_pdf=tmp_path / "r.pdf"
        )
        assert result.pdf_path is None
        return
    out_html = tmp_path / "r.html"
    out_pdf = tmp_path / "r.pdf"
    result = export_report(
        _REPORT, source_refs_from_notes(_SOURCES), out_html, out_pdf=out_pdf
    )
    assert result.pdf_path == out_pdf
    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 0
    # PDF magic bytes.
    assert out_pdf.read_bytes()[:4] == b"%PDF"
