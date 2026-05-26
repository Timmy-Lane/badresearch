"""feed/sitemap/llms_txt discovery tiers (dossier 12 §D/E/F). httpx mocked, real XML."""

from __future__ import annotations

import bad_research.web.content.sources as src
from bad_research.web.content.sources import feed_notes, llms_txt_notes, sitemap_urls

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Caching at scale</title>
    <link href="https://blog.ex.com/caching"/>
    <published>2024-02-01T00:00:00Z</published>
    <summary>How we cache results.</summary>
  </entry>
  <entry>
    <title>Retrieval fusion</title>
    <link href="https://blog.ex.com/fusion"/>
    <published>2024-03-10T00:00:00Z</published>
    <summary>RRF k=60 explained.</summary>
  </entry>
</feed>"""

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ex.com/a</loc><lastmod>2024-01-05</lastmod></url>
  <url><loc>https://ex.com/b</loc><lastmod>2024-06-20</lastmod></url>
</urlset>"""

ROBOTS = "User-agent: *\nSitemap: https://ex.com/sitemap.xml\n"

LLMS_FULL = "# Example Docs\n\n## Getting Started\n\nInstall and run.\n"
LLMS_INDEX = "# Example Docs\n\n- [Quickstart](https://ex.com/quickstart)\n- [API](https://ex.com/api)\n"


class _Resp:
    def __init__(self, text="", status=200, content=b""):
        self.text = text
        self.status_code = status
        self.content = content or text.encode("utf-8")


def test_feed_notes(monkeypatch) -> None:
    # feedparser.parse takes a URL or bytes; feed it the raw XML directly
    notes = feed_notes(ATOM_FEED)   # feedparser accepts a string of XML
    assert len(notes) == 2
    n = notes[0]
    assert n["source_type"] == "feed"
    assert n["title"] == "Caching at scale"
    assert n["source"] == "https://blog.ex.com/caching"
    assert n["published"].startswith("2024-02-01")
    assert "cache" in n["markdown"].lower()


def test_sitemap_urls(monkeypatch) -> None:
    def fake_get(url, **kw):
        if url.endswith("robots.txt"):
            return _Resp(text=ROBOTS)
        return _Resp(content=SITEMAP_XML.encode("utf-8"))

    monkeypatch.setattr(src.httpx, "get", fake_get)
    monkeypatch.setattr(src, "assert_url_safe", lambda u: None)
    out = sitemap_urls("ex.com")
    assert {u["source"] for u in out} == {"https://ex.com/a", "https://ex.com/b"}
    assert all(u["source_type"] == "sitemap" for u in out)
    b = next(u for u in out if u["source"].endswith("/b"))
    assert b["published"] == "2024-06-20"


def test_llms_txt_full(monkeypatch) -> None:
    def fake_get(url, **kw):
        if url.endswith("llms-full.txt"):
            return _Resp(text=LLMS_FULL)
        return _Resp(text="", status=404)

    monkeypatch.setattr(src.httpx, "get", fake_get)
    monkeypatch.setattr(src, "assert_url_safe", lambda u: None)
    out = llms_txt_notes("docs.ex.com")
    assert isinstance(out, dict)
    assert out["source_type"] == "llms_txt"
    assert "Getting Started" in out["markdown"]


def test_llms_txt_index_harvest(monkeypatch) -> None:
    def fake_get(url, **kw):
        if url.endswith("llms-full.txt"):
            return _Resp(text="", status=404)
        return _Resp(text=LLMS_INDEX)

    monkeypatch.setattr(src.httpx, "get", fake_get)
    monkeypatch.setattr(src, "assert_url_safe", lambda u: None)
    out = llms_txt_notes("docs.ex.com")
    assert isinstance(out, list)
    assert {n["source"] for n in out} == {"https://ex.com/quickstart", "https://ex.com/api"}
