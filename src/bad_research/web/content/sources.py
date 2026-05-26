"""Keyless source-type tiers — classify_source + the 6 extractors (dossier 12 §A-F).

Each extractor emits the normalized vault note shape (dossier 12 §"normalized vault
note"). yt-dlp + git are EXTERNAL CLIs: detected at call time, degrade gracefully via
ExtractorUnavailable when absent. KNOWN = repo/dossier convention; DESIGNED = the port.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from bad_research.core.fetcher import assert_url_safe


class ExtractorUnavailable(RuntimeError):
    """A required external CLI (yt-dlp / git) is not installed.

    Carries an `install_hint`. The orchestrator catches this and skips the tier
    (graceful degradation) rather than crashing the run.
    """

    def __init__(self, tool: str, install_hint: str) -> None:
        self.tool = tool
        self.install_hint = install_hint
        super().__init__(f"{tool} not found on PATH — {install_hint}")


def _iso(raw: str | None) -> str | None:
    """Normalize a date string to an ISO date, or None. Uses dateparser (keyless)."""
    if not raw:
        return None
    import dateparser  # type: ignore[import-untyped]

    dt = dateparser.parse(raw)
    return dt.date().isoformat() if dt else None


def _html_to_md(html: str) -> str:
    """Minimal HTML->text for feed summaries (no full pipeline needed)."""
    from bs4 import BeautifulSoup

    return BeautifulSoup(html or "", "lxml").get_text("\n", strip=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def classify_source(url: str) -> str:
    """URL-shape classifier, runs BEFORE the byte-fetch (dossier 12 §"Routing"). KNOWN.

    Returns one of: youtube | github | arxiv | feed | sitemap | llms_txt | html_or_pdf.
    For non-html_or_pdf types you must NOT scrape the URL's HTML — call the matching
    keyless extractor against the same identifier instead.
    """
    h = urlparse(url).hostname or ""
    if re.search(r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts)", url):
        return "youtube"
    if h == "github.com" and len(urlparse(url).path.strip("/").split("/")) >= 2:
        return "github"
    if re.search(r"arxiv\.org/(abs|pdf)/", url):
        return "arxiv"
    if url.rstrip("/").endswith(("/llms.txt", "/llms-full.txt")):
        return "llms_txt"
    if url.rstrip("/").endswith(("sitemap.xml", "/sitemap_index.xml")):
        return "sitemap"
    if re.search(r"(/feed/?$|/rss/?$|\.rss$|\.atom$|/atom\.xml$|/feed\.xml$)", url):
        return "feed"
    return "html_or_pdf"


def youtube_transcript(url: str) -> dict[str, Any]:
    raise NotImplementedError  # Task 13


def github_clone_notes(repo_url: str) -> list[dict[str, Any]]:
    raise NotImplementedError  # Task 13


def github_file(owner: str, repo: str, path: str,
                branch: str | None = None) -> dict[str, Any]:
    raise NotImplementedError  # Task 13


def arxiv_source_notes(url: str) -> dict[str, Any]:
    raise NotImplementedError  # Task 13


def feed_notes(feed_url: str) -> list[dict[str, Any]]:
    """RSS/Atom -> per-entry normalized notes (dossier 12 §D). KNOWN (feedparser).

    Accepts a feed URL or a raw XML string (feedparser handles both). Each entry yields
    {title, source=link, published, markdown}; full-content feeds inline the body.
    """
    import feedparser  # type: ignore[import-untyped]

    f = feedparser.parse(feed_url)
    out: list[dict[str, Any]] = []
    for e in f.entries:
        body = ""
        if e.get("content"):
            body = e["content"][0].get("value", "")
        body = body or e.get("summary", "")
        out.append({
            "title": e.get("title"),
            "source": e.get("link"),
            "source_type": "feed",
            "fetched_at": _now(),
            "published": _iso(e.get("published") or e.get("updated")),
            "provenance": f"feedparser {feed_url}",
            "markdown": _html_to_md(body),
        })
    return out


def _discover_sitemap(host: str) -> str:
    """robots.txt Sitemap: directive, else /sitemap.xml (dossier 12 §E)."""
    robots_url = f"https://{host}/robots.txt"
    assert_url_safe(robots_url)
    try:
        r = httpx.get(robots_url, follow_redirects=True, timeout=15)
        for line in r.text.splitlines():
            if line.lower().startswith("sitemap:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return f"https://{host}/sitemap.xml"


def _sitemap_urls_from(sitemap_url: str) -> list[dict[str, Any]]:
    assert_url_safe(sitemap_url)
    root = ET.fromstring(httpx.get(sitemap_url, follow_redirects=True, timeout=15).content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex"):
        out: list[dict[str, Any]] = []
        for c in root.findall(".//s:loc", ns):
            if c.text:
                out.extend(_sitemap_urls_from(c.text))
        return out
    return [
        {
            "source": loc.findtext("s:loc", None, ns),
            "published": _iso(loc.findtext("s:lastmod", None, ns)),
            "source_type": "sitemap",
        }
        for loc in root.findall(".//s:url", ns)
    ]


def sitemap_urls(host: str) -> list[dict[str, Any]]:
    """sitemap.xml -> {url, lastmod} crawl-frontier seeds (dossier 12 §E). KNOWN.

    robots.txt Sitemap: directive (authoritative) > /sitemap.xml; recurse into a
    sitemapindex. lastmod is the recency signal. Emits seeds, not content.
    """
    return _sitemap_urls_from(_discover_sitemap(host))


def llms_txt_notes(host: str) -> dict[str, Any] | list[dict[str, Any]]:
    """/llms-full.txt (whole corpus, one note) else /llms.txt link-harvest (§F). KNOWN.

    llms-full.txt present -> one pre-cleaned note (skip §2-6). Only llms.txt -> a curated,
    summarized link index harvested as crawl seeds.
    """
    full_url = f"https://{host}/llms-full.txt"
    assert_url_safe(full_url)
    full = httpx.get(full_url, follow_redirects=True, timeout=15)
    if full.status_code == 200 and full.text.strip():
        return {
            "title": f"{host} docs (llms-full)",
            "source": full_url,
            "source_type": "llms_txt",
            "fetched_at": _now(),
            "published": None,
            "provenance": f"GET {host}/llms-full.txt",
            "markdown": full.text,
        }
    idx_url = f"https://{host}/llms.txt"
    assert_url_safe(idx_url)
    idx = httpx.get(idx_url, follow_redirects=True, timeout=15)
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", idx.text)
    return [
        {
            "title": t,
            "source": u,
            "source_type": "llms_txt",
            "fetched_at": _now(),
            "published": None,
            "provenance": f"link in {host}/llms.txt",
            "markdown": "",
        }
        for t, u in links
    ]
