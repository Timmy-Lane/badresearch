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


# --- Stage 0-3 routing (Task 8) ------------------------------------------------

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from bad_research.web.base import ProviderError, SearchQuery


class _RerankerLike(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...


_MIN_CONTENT_CHARS = 300  # below this a SERP row is content-less -> Stage-3 extract


def _route_intent(q: SearchQuery) -> SearchQuery:
    """Stage 0 — cheap local intent route. Fills recency from query tokens and
    upgrades intent to 'neural' for similarity-style queries.
    """
    lowered = q.query.lower()
    recency = q.recency_days
    if recency is None and any(
        tok in lowered for tok in ("latest", "today", "this week", "right now", "2026")
    ):
        recency = 7
    intent = q.intent
    if intent == "keyword" and (
        lowered.startswith("find sites like")
        or lowered.startswith("similar to")
        or "http://" in lowered
        or "https://" in lowered
    ):
        intent = "neural"
    return SearchQuery(
        query=q.query,
        intent=intent,
        recency_days=recency,
        include_domains=q.include_domains,
        exclude_domains=q.exclude_domains,
        max_results=q.max_results,
    )


def _passes_bar(r: WebResult, bar: float = RELEVANCE_BAR) -> bool:
    """A result clears the bar if its score >= bar. Score-less rows count as
    below the bar (forces Stage-2 when SERP providers return no score)."""
    score = r.metadata.get("score")
    return score is not None and score >= bar


class CascadeProvider:
    """Composes the provider set into the four-stage cascade. name = 'cascade'."""

    name = "cascade"
    capabilities = {"keyword", "neural", "extract"}
    cost_per_search = 0.0  # computed dynamically; placeholder for the Protocol attr
    p50_ms = 600

    def __init__(
        self,
        keyword_providers: list,
        neural_provider=None,
        extractor=None,
        reranker: _RerankerLike | None = None,
        extract_top_n: int = 0,
    ):
        self._keyword = list(keyword_providers)
        self._neural = neural_provider
        self._extractor = extractor
        self._reranker = reranker
        self._extract_top_n = extract_top_n

    # -- Stage 1 ---------------------------------------------------------------
    def _stage1(self, q: SearchQuery) -> list[WebResult]:
        by_provider: dict[str, list[WebResult]] = {}

        def _run(provider) -> tuple[str, list[WebResult]]:
            try:
                return provider.name, provider.search_ex(q)
            except ProviderError:
                return provider.name, []   # ladder degradation — skip dead provider

        if not self._keyword:
            return []
        with ThreadPoolExecutor(max_workers=max(len(self._keyword), 1)) as pool:
            for name, results in pool.map(_run, self._keyword):
                by_provider[name] = results
        return _dedup_union(by_provider)

    # -- Stage 2 ---------------------------------------------------------------
    def _should_fire_neural(self, q: SearchQuery, stage1: list[WebResult]) -> bool:
        if self._neural is None:
            return False
        if q.intent == "neural":
            return True
        if not stage1:
            return True
        passing = sum(1 for r in stage1 if _passes_bar(r))
        return (passing / len(stage1)) < THIN_PASS_FRACTION

    def _stage2(self, q: SearchQuery, stage1: list[WebResult]) -> list[WebResult]:
        try:
            neural_results = self._neural.search_ex(q)
        except ProviderError:
            neural_results = []
        fused = _rrf_fuse([stage1, neural_results])
        if self._reranker is not None and fused:
            order = self._reranker.rerank(q.query, [r.content for r in fused])
            fused = [fused[idx] for idx, _score in order]
        return fused

    # -- Stage 3 ---------------------------------------------------------------
    def _stage3(self, results: list[WebResult]) -> list[WebResult]:
        if self._extractor is None or self._extract_top_n <= 0:
            return results
        out: list[WebResult] = []
        extracted = 0
        for r in results:
            needs_extract = (
                extracted < self._extract_top_n and r.looks_like_junk() is not None
            )
            if needs_extract:
                try:
                    fetched = self._extractor.fetch(r.url)
                except ProviderError:
                    out.append(r)
                    continue
                extracted += 1
                if fetched.looks_like_junk() is not None or fetched.looks_like_login_wall(r.url):
                    continue  # drop junk/login-wall after extraction
                fetched.metadata.update(r.metadata)
                out.append(fetched)
            else:
                out.append(r)
        return out

    def search_ex(self, q: SearchQuery) -> list[WebResult]:
        routed = _route_intent(q)
        stage1 = self._stage1(routed)
        results = stage1
        if self._should_fire_neural(routed, stage1):
            results = self._stage2(routed, stage1)
        results = self._stage3(results)
        return results[: q.max_results] if q.max_results else results

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return self.search_ex(SearchQuery(query=query, max_results=max_results))

    def fetch(self, url: str) -> WebResult:
        if self._extractor is not None:
            return self._extractor.fetch(url)
        if self._keyword:
            return self._keyword[0].fetch(url)
        raise ProviderError("Cascade has no provider capable of fetch().")


def cascade_search(
    q: SearchQuery,
    *,
    keyword_providers: list,
    neural_provider=None,
    extractor=None,
    reranker: _RerankerLike | None = None,
    extract_top_n: int = 0,
) -> list[WebResult]:
    """Build a CascadeProvider from the given provider set and run one query."""
    return CascadeProvider(
        keyword_providers=keyword_providers,
        neural_provider=neural_provider,
        extractor=extractor,
        reranker=reranker,
        extract_top_n=extract_top_n,
    ).search_ex(q)
