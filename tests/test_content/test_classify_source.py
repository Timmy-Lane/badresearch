"""classify_source — URL-shape routing (dossier 12 §"Routing")."""

from __future__ import annotations

import pytest

from bad_research.web.content.sources import classify_source


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123", "youtube"),
    ("https://youtu.be/abc123", "youtube"),
    ("https://www.youtube.com/shorts/xyz", "youtube"),
    ("https://github.com/owner/repo", "github"),
    ("https://github.com/owner/repo/blob/main/src/x.py", "github"),
    ("https://arxiv.org/abs/2403.12345", "arxiv"),
    ("https://arxiv.org/pdf/2403.12345", "arxiv"),
    ("https://docs.example.com/llms.txt", "llms_txt"),
    ("https://docs.example.com/llms-full.txt", "llms_txt"),
    ("https://example.com/sitemap.xml", "sitemap"),
    ("https://example.com/sitemap_index.xml", "sitemap"),
    ("https://blog.example.com/feed", "feed"),
    ("https://blog.example.com/rss", "feed"),
    ("https://blog.example.com/atom.xml", "feed"),
    ("https://example.com/articles/how-rag-works", "html_or_pdf"),
    ("https://example.com/paper.pdf", "html_or_pdf"),
    ("https://github.com/owner", "html_or_pdf"),   # single path segment -> not a repo
])
def test_classify(url: str, expected: str) -> None:
    assert classify_source(url) == expected
