"""Keyless source-type tiers — classify_source + the 6 extractors (dossier 12 §A-F).

Each extractor emits the normalized vault note shape (dossier 12 §"normalized vault
note"). yt-dlp + git are EXTERNAL CLIs: detected at call time, degrade gracefully via
ExtractorUnavailable when absent. KNOWN = repo/dossier convention; DESIGNED = the port.
"""

from __future__ import annotations


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
    raise NotImplementedError  # Task 11


def youtube_transcript(url: str) -> dict:
    raise NotImplementedError  # Task 13


def github_clone_notes(repo_url: str) -> list[dict]:
    raise NotImplementedError  # Task 13


def github_file(owner: str, repo: str, path: str, branch: str | None = None) -> dict:
    raise NotImplementedError  # Task 13


def arxiv_source_notes(url: str) -> dict:
    raise NotImplementedError  # Task 13


def feed_notes(feed_url: str) -> list[dict]:
    raise NotImplementedError  # Task 12


def sitemap_urls(host: str) -> list[dict]:
    raise NotImplementedError  # Task 12


def llms_txt_notes(host: str) -> dict | list[dict]:
    raise NotImplementedError  # Task 12
