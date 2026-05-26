"""Stage 1 — pre-fetch source filtering (dossier 07 §1).

Pure Python: regex + set membership. No network, no LLM, microseconds per candidate.
This is the cheapest garbage to reject — the URL you never fetch.
"""

from __future__ import annotations

import re

# --- SEO content-farm signals (dossier 07 §1.1). +1 each; block when total >= 2. ---

_RE_LISTICLE_TITLE = re.compile(
    r"\b(\d+\s+(best|top|ways|tips|reasons|things)|top\s+\d+)\b", re.IGNORECASE
)
_RE_CLICKBAIT_TITLE = re.compile(
    r"(you won'?t believe|this one trick|what happens next|in 20\d\d\b)", re.IGNORECASE
)
_RE_MONEY_PAGE_PATH = re.compile(
    r"/(best-|top-|review|vs-|cheap|deals|coupon|affiliate)", re.IGNORECASE
)

SEO_FARM_BLOCK_THRESHOLD = 2  # dossier 07 §1.1 / INTERFACES.md


def seo_farm_score(url: str, snippet: str, query: str = "") -> int:
    """Deterministic SEO-farm classifier. Returns a signal count; block if >= 2.

    Implements Claude Research failure-mode #4/#5 ("SEO-optimized content over
    authoritative sources") as code rather than a prompt nudge (dossier 07 §1.1).
    """
    url = url or ""
    snippet = snippet or ""
    score = 0

    # listicle_title (+1)
    if _RE_LISTICLE_TITLE.search(snippet):
        score += 1
    # clickbait_title (+1)
    if _RE_CLICKBAIT_TITLE.search(snippet):
        score += 1
    # money_page_path (+1)
    if _RE_MONEY_PAGE_PATH.search(url):
        score += 1
    # thin_snippet (+1): SERP snippet < 120 chars AND ends mid-sentence "..."
    s = snippet.strip()
    if len(s) < 120 and s.endswith("..."):
        score += 1
    # stuffed_keywords (+1): a query term repeats > 4x in the first 160 chars
    if query:
        window = snippet[:160].lower()
        for term in query.lower().split():
            if len(term) >= 3 and window.count(term) > 4:
                score += 1
                break

    return score
