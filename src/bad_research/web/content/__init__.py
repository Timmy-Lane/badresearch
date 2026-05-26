"""Keyless content extraction — URL -> clean markdown + the 6 source-type tiers.

KR-3. Replaces the paid Firecrawl/Exa/Tavily `URL -> clean markdown` primitive with
a deterministic local pipeline (dossier 12) + the 6 keyless non-HTML source tiers.
Zero third-party API key; the only model touch is the optional host-model `llm_clean`.
"""

from __future__ import annotations

from bad_research.web.content.fetch_clean import (
    FIRECRAWL_CLEAN_PROMPT,
    extract_metadata,
    extract_published_date,
    fetch_clean,
    highlights,
    llm_clean,
    main_content,
    pdf_to_markdown,
    strip_boilerplate,
)
from bad_research.web.content.sources import (
    ExtractorUnavailable,
    arxiv_source_notes,
    classify_source,
    feed_notes,
    github_clone_notes,
    github_file,
    llms_txt_notes,
    sitemap_urls,
    youtube_transcript,
)

__all__ = [
    "FIRECRAWL_CLEAN_PROMPT",
    "ExtractorUnavailable",
    "arxiv_source_notes",
    "classify_source",
    "extract_metadata",
    "extract_published_date",
    "feed_notes",
    "fetch_clean",
    "github_clone_notes",
    "github_file",
    "highlights",
    "llm_clean",
    "llms_txt_notes",
    "main_content",
    "pdf_to_markdown",
    "sitemap_urls",
    "strip_boilerplate",
    "youtube_transcript",
]
