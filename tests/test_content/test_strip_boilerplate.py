"""strip_boilerplate — verbatim Firecrawl removeUnwantedElements.ts port (dossier 12 §2)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from bad_research.web.content.fetch_clean import strip_boilerplate


def test_strips_always_set(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    assert "var tracker" not in out          # <script> gone
    assert "color:red" not in out            # <style> gone


def test_strips_chrome_when_only_main(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    assert "Buy our product now" not in out  # .ad .advert removed
    assert "We use cookies" not in out       # .cookie removed
    assert "Related posts" not in out        # plain .sidebar removed
    assert "Privacy" not in out              # footer removed


def test_force_include_guard_keeps_main_in_sidebar(sample_html: str) -> None:
    # dossier 12 §2.3: a .sidebar that CONTAINS #main must be kept
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    assert "REAL ARTICLE INSIDE SIDEBAR keep me" in out


def test_keeps_article_body(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    assert "Retrieval-augmented generation combines a retriever" in out


def test_srcset_picks_biggest(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    soup = BeautifulSoup(out, "lxml")
    img = soup.find("img")
    assert img is not None
    # 1024w is the biggest candidate -> becomes src (then absolutified)
    assert img["src"].endswith("hero-1024.png")


def test_absolutifies_links(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=True)
    assert "https://ex.com/deep-dive" in out   # relative /deep-dive -> absolute


def test_only_main_false_keeps_chrome(sample_html: str) -> None:
    out = strip_boilerplate(sample_html, "https://ex.com/post", only_main=False)
    # script/style still always stripped, but chrome retained when only_main=False
    assert "Buy our product now" in out
    assert "var tracker" not in out
