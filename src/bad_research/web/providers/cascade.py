"""Web-search cascade: intent route -> fast keyword union -> conditional neural
rerank -> deep extract, with zero-key degradation. (SPEC §5, dossier 02 §6.3.)

This module owns ONLY routing/dedup/fusion. It composes provider instances passed
to CascadeProvider's constructor; it never talks to an upstream API directly.
"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bad_research.retrieval.constants import RRF_K as _RETRIEVAL_RRF_K
from bad_research.web.base import WebResult

# Frozen constants (INTERFACES.md "Frozen constants"). RRF_K is reused from
# Plan 02's single source of truth (retrieval/constants.py) so the fusion k stays
# consistent across the retrieval engine and the web cascade.
RRF_K = int(_RETRIEVAL_RRF_K)    # Reciprocal Rank Fusion k = 60 (EXA §6.2)
RELEVANCE_BAR = 0.70             # relevance drop threshold (Perplexity)
THIN_PASS_FRACTION = 0.30        # <30% pass -> Stage-2 fires (Perplexity failsafe)
MAX_RERETRIEVE_ROUNDS = 2        # re-retrieve max rounds

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = frozenset({"fbclid", "gclid", "mc_eid", "mc_cid", "ref"})


def _canonical_url(url: str) -> str:
    """Collapse cosmetic URL variants so dedup catches the same page.

    Lowercases scheme+host, strips a leading 'www.', drops the fragment, removes
    a trailing slash on non-root paths, strips utm_*/fbclid-style tracking params,
    and sorts the remaining query so order doesn't matter.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _TRACKING_PARAM_EXACT
        and not any(k.startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(kept))
    return urlunsplit((scheme, host, path, query, ""))


def _dedup_union(by_provider: dict[str, list[WebResult]]) -> list[WebResult]:
    """Merge per-provider result lists by canonical URL.

    Keeps the first-seen WebResult for each canonical URL and records every
    provider that returned it in metadata['found_by'].
    """
    seen: dict[str, WebResult] = {}
    found_by: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    for provider_name, results in by_provider.items():
        for r in results:
            key = _canonical_url(r.url)
            if key not in seen:
                seen[key] = r
                order.append(key)
            found_by[key].append(provider_name)
    out: list[WebResult] = []
    for key in order:
        r = seen[key]
        # Normalize the kept result's URL to the canonical form so downstream
        # stages key off one stable URL per page (dossier 02 §6.3 dedup).
        r.url = key
        r.metadata["found_by"] = found_by[key]
        out.append(r)
    return out


def _rrf_fuse(ranked_lists: list[list[WebResult]]) -> list[WebResult]:
    """Reciprocal Rank Fusion over multiple ranked lists. k = RRF_K (60).

    rrf(doc) = sum over lists L of 1 / (RRF_K + rank_L(doc)), rank is 1-based.
    Returns one WebResult per canonical URL, sorted by rrf_score descending, with
    the score recorded in metadata['rrf_score'].
    """
    scores: dict[str, float] = defaultdict(float)
    repr_result: dict[str, WebResult] = {}
    for ranked in ranked_lists:
        for rank, r in enumerate(ranked, start=1):
            key = _canonical_url(r.url)
            scores[key] += 1.0 / (RRF_K + rank)
            repr_result.setdefault(key, r)
    fused = sorted(repr_result.values(), key=lambda r: scores[_canonical_url(r.url)], reverse=True)
    for r in fused:
        r.metadata["rrf_score"] = scores[_canonical_url(r.url)]
    return fused
