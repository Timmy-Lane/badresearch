"""Stage 1 — pre-fetch source filtering (dossier 07 §1).

Pure Python: regex + set membership. No network, no LLM, microseconds per candidate.
This is the cheapest garbage to reject — the URL you never fetch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class TierInfo:
    """A DOMAIN_TIER entry: authority multiplier + pre-fetch fetch order."""

    name: str
    multiplier: float
    prefetch_priority: int  # 0 = fetch first, 9 = last/drop


# Static domain-authority table (dossier 07 §1.2, §7.2; multipliers frozen in INTERFACES.md).
# Research-tuned from NIA §5.3's SOURCE_TYPE_WEIGHT mechanism (which biases toward code);
# we invert toward primary/authoritative sources for general research.
DOMAIN_TIER: dict[str, TierInfo] = {
    "primary":    TierInfo("primary", 1.30, 0),
    "docs":       TierInfo("docs", 1.15, 1),
    "reference":  TierInfo("reference", 1.10, 1),
    "news_tier1": TierInfo("news_tier1", 1.00, 2),
    "blog":       TierInfo("blog", 0.85, 3),
    "forum":      TierInfo("forum", 0.80, 3),
    "seo_farm":   TierInfo("seo_farm", 0.50, 9),
}

# Curated domain → tier sets (small + durable; the SEO classifier generalizes the rest).
_PRIMARY_TLDS = (".gov", ".edu", ".mil")
_PRIMARY_DOMAINS = {"sec.gov", "uspto.gov", "patents.google.com"}
_DOCS_HOST_PREFIXES = ("docs.", "developer.", "devdocs.")
_DOCS_DOMAINS = {"docs.python.org", "developer.mozilla.org", "datatracker.ietf.org"}
_REFERENCE_DOMAINS = {
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
}
_REFERENCE_SUFFIXES = ("wikipedia.org",)
_NEWS_TIER1_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "nytimes.com",
    "wsj.com", "economist.com", "bbc.com",
}
_FORUM_DOMAINS = {
    "news.ycombinator.com", "reddit.com", "stackoverflow.com",
    "stackexchange.com", "discourse.org",
}


def _host(url: str) -> str:
    return (urlparse(url or "").netloc or "").lower()


def domain_tier(url: str) -> TierInfo:
    """Assign a DOMAIN_TIER from the URL host (pre-fetch). Defaults to 'blog'."""
    host = _host(url)
    if not host:
        return DOMAIN_TIER["blog"]

    base = host[4:] if host.startswith("www.") else host

    if any(base.endswith(t) for t in _PRIMARY_TLDS) or base in _PRIMARY_DOMAINS:
        return DOMAIN_TIER["primary"]
    if base in _DOCS_DOMAINS or any(host.startswith(p) for p in _DOCS_HOST_PREFIXES):
        return DOMAIN_TIER["docs"]
    if base in _REFERENCE_DOMAINS or any(base.endswith(s) for s in _REFERENCE_SUFFIXES):
        return DOMAIN_TIER["reference"]
    if base in _NEWS_TIER1_DOMAINS:
        return DOMAIN_TIER["news_tier1"]
    if base in _FORUM_DOMAINS or any(base.endswith("." + d) or base == d for d in _FORUM_DOMAINS):
        return DOMAIN_TIER["forum"]
    return DOMAIN_TIER["blog"]
