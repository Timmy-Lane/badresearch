"""Deterministic fixtures for content-extraction tests — real HTML/VTT/PDF, no network."""

from __future__ import annotations

import pytest

# A realistic page: chrome (nav/footer/sidebar/ad/cookie) wrapping a real article,
# plus a srcset image, a relative link, and a #main-containing sidebar to exercise
# the force-include guard (dossier 12 §2.3).
SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>How Retrieval-Augmented Generation Works</title>
  <meta charset="utf-8">
  <meta name="description" content="A deep dive into RAG pipelines.">
  <meta name="keywords" content="rag, retrieval, llm">
  <meta property="article:published_time" content="2024-03-15T09:30:00Z">
  <meta property="og:title" content="RAG Explained">
  <script>var tracker = 1;</script>
  <style>.x{color:red}</style>
</head>
<body>
  <header class="navbar"><a href="/home">Home</a><a href="/about">About</a></header>
  <nav class="navigation"><a href="/docs">Docs</a></nav>
  <div class="cookie">We use cookies. Accept?</div>
  <div class="ad advert">Buy our product now!</div>
  <aside class="sidebar"><a href="/related">Related posts</a></aside>
  <aside class="sidebar"><div id="main">REAL ARTICLE INSIDE SIDEBAR keep me</div></aside>
  <article>
    <h1>How Retrieval-Augmented Generation Works</h1>
    <p>Retrieval-augmented generation combines a retriever with a generator to ground
    responses in external documents. The retriever finds relevant passages and the
    generator conditions on them. This reduces hallucination substantially.</p>
    <p>A typical pipeline embeds the corpus, indexes the vectors, retrieves top-k
    passages for a query, and feeds them as context. Chunk size and overlap matter.</p>
    <img src="hero.png" srcset="hero-480.png 480w, hero-1024.png 1024w" alt="diagram">
    <a href="/deep-dive">Read the deep dive</a>
  </article>
  <footer class="footer"><a href="/privacy">Privacy</a></footer>
  <div class="social-links"><a href="/twitter">Tweet</a></div>
</body>
</html>"""

# A YouTube-style auto-sub VTT with rolling captions + inline timing tags (dossier 12 §A).
SAMPLE_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
so<00:00:00.400><c> today</c>

00:00:02.000 --> 00:00:04.000 align:start position:0%
so today<00:00:02.400><c> we're</c><00:00:02.800><c> talking</c>

00:00:04.000 --> 00:00:06.000 align:start position:0%
so today we're talking<00:00:04.400><c> about</c><00:00:04.800><c> caching</c>

00:00:06.000 --> 00:00:08.000 align:start position:0%
the cache hit rate is forty percent

00:00:08.000 --> 00:00:10.000 align:start position:0%
the cache hit rate is forty percent
"""


@pytest.fixture
def sample_html() -> str:
    return SAMPLE_HTML


@pytest.fixture
def sample_vtt() -> str:
    return SAMPLE_VTT


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """A tiny real PDF generated with pymupdf — has a heading + body text."""
    import pymupdf  # fitz

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Keyless PDF Extraction", fontsize=18)
    page.insert_text((72, 110), "This document validates pymupdf4llm markdown conversion.",
                     fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data
