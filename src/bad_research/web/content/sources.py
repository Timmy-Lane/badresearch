"""Keyless source-type tiers — classify_source + the 6 extractors (dossier 12 §A-F).

Each extractor emits the normalized vault note shape (dossier 12 §"normalized vault
note"). yt-dlp + git are EXTERNAL CLIs: detected at call time, degrade gracefully via
ExtractorUnavailable when absent. KNOWN = repo/dossier convention; DESIGNED = the port.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


class ExtractorUnavailable(RuntimeError):
    """A required external CLI (yt-dlp / git) is not installed.

    Carries an `install_hint`. The orchestrator catches this and skips the tier
    (graceful degradation) rather than crashing the run.
    """

    def __init__(self, tool: str, install_hint: str) -> None:
        self.tool = tool
        self.install_hint = install_hint
        super().__init__(f"{tool} not found on PATH — {install_hint}")


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
    raise NotImplementedError  # Task 12


def sitemap_urls(host: str) -> list[dict[str, Any]]:
    raise NotImplementedError  # Task 12


def llms_txt_notes(host: str) -> dict[str, Any] | list[dict[str, Any]]:
    raise NotImplementedError  # Task 12
