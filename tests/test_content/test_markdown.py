"""html2text markdown conversion + postclean (dossier 12 §4, §7-postclean)."""

from __future__ import annotations

from bad_research.web.content.fetch_clean import html_to_markdown, postclean


def test_html_to_markdown_basic() -> None:
    html = "<article><h1>Title</h1><p>A paragraph of body text here.</p></article>"
    md = html_to_markdown(html, base_url="https://ex.com")
    assert "Title" in md
    assert "A paragraph of body text here." in md


def test_postclean_strips_base64_images() -> None:
    md = "Before\n\n![x](data:image/png;base64,iVBORw0KGgoAAAANS)\n\nAfter"
    out = postclean(md)
    assert "data:image/png;base64" not in out
    assert "Before" in out and "After" in out


def test_postclean_collapses_blank_lines() -> None:
    md = "a\n\n\n\n\nb"
    out = postclean(md)
    assert "\n\n\n" not in out


def test_postclean_fixes_indented_fences() -> None:
    md = "text\n    ```python\n    x = 1\n    ```\n"
    out = postclean(md)
    assert "    ```" not in out
    assert "```" in out
