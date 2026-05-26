"""Stage D — read ONLY the top-K ranked candidates (≤80 ceiling), batched.

The cheap-search -> expensive-read gate pays off here: we fetch the Stage-C
winners and NEVER the full pool. The ~80-read ceiling is load-bearing
(dossier 10 §3.3: reading past it degrades synthesis) and enforced even if a
caller misconfigures read_top_k.

Reads run through fetch_tiered (Plan 04, the Tier 0->3 escalation ladder),
wrapped in funnel._async.acall (the real fetch_tiered is SYNCHRONOUS), bounded
by an asyncio.Semaphore (read_concurrency 10-12 full / 3-5 light).

Chained crawl (browse_page pattern, dossier 10 §2.2): a hub page's outbound
links are ranked by a free JS-cosine score against the query and the top
max_links_per_hub are queued, depth <= max_chain_depth; queued links re-enter
the seen-set so they are never double-read.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import Counter

from bad_research.funnel._async import acall

_DEFAULT_CEILING = 80
_HUB_LINK_FLOOR = 10   # a page with >=10 outbound links is treated as a hub


def _js_cosine(query: str, text: str) -> float:
    """Firecrawl-style pure-JS bag-of-words cosine (dossier 10 §2.2 / FC §28.6).
    No embedding model — tokenize on \\W+, count, dot/magnitudes. Dirt cheap."""
    qt = [t for t in re.split(r"\W+", query.lower()) if t]
    dt = [t for t in re.split(r"\W+", text.lower()) if t]
    if not qt or not dt:
        return 0.0
    qc, dc = Counter(qt), Counter(dt)
    common = set(qc) & set(dc)
    dot = sum(qc[t] * dc[t] for t in common)
    qmag = math.sqrt(sum(v * v for v in qc.values()))
    dmag = math.sqrt(sum(v * v for v in dc.values()))
    return dot / (qmag * dmag) if qmag and dmag else 0.0


def _rank_hub_links(query: str, links: list[dict], limit: int) -> list[str]:
    """Rank a hub's outbound links by JS-cosine of (anchor text) vs query, keep top `limit`."""
    scored = []
    for ln in links:
        href = ln.get("href") or ""
        if not href.startswith("http"):
            continue
        text = (ln.get("text") or "") + " " + href
        scored.append((_js_cosine(query, text), href))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [href for _, href in scored[:limit]]


async def read_top_k(
    ranked: list,
    *,
    fetcher,
    read_top_k: int,
    concurrency: int,
    max_chain_depth: int,
    max_links_per_hub: int,
    query: str = "",
    ceiling: int = _DEFAULT_CEILING,
) -> list:
    """Read the top candidates via fetch_tiered, batched + chained.

    Returns the list of read WebResults (junk not yet filtered — Stage E does
    that). Never reads more than min(read_top_k, ceiling) primary candidates;
    chained-crawl children also count against the same read budget.
    """
    budget = min(read_top_k, ceiling)
    sem = asyncio.Semaphore(max(1, concurrency))
    seen: set[str] = set()
    results: list = []
    reads_done = 0
    lock = asyncio.Lock()

    async def _fetch(url: str):
        async with sem:
            return await acall(fetcher.fetch_tiered, url, tier_max=1)

    async def _try_read(url: str):
        nonlocal reads_done
        async with lock:
            if url in seen or reads_done >= budget:
                return None
            seen.add(url)
            reads_done += 1
        return await _fetch(url)

    # Primary wave: the top-budget ranked candidates, batched.
    primaries = ranked[:budget]
    primary_results = await asyncio.gather(*[_try_read(c.canonical_url) for c in primaries])
    results.extend(r for r in primary_results if r is not None)

    # Chained crawl: follow the best outbound links of hub pages, bounded.
    if max_chain_depth > 0 and max_links_per_hub > 0:
        frontier = list(results)
        depth = 1
        while frontier and depth <= max_chain_depth:
            next_frontier: list = []
            queued: list[str] = []
            for page in frontier:
                links = getattr(page, "links", []) or []
                if len(links) < _HUB_LINK_FLOOR and len(links) < max_links_per_hub * 2:
                    # not hub-like enough; still allow following if it has links
                    if not links:
                        continue
                for href in _rank_hub_links(query, links, max_links_per_hub):
                    if href not in seen:
                        queued.append(href)
            # read queued links under the SAME budget; re-dedup via seen-set
            child_results = await asyncio.gather(*[_try_read(u) for u in queued])
            for cr in child_results:
                if cr is not None:
                    results.append(cr)
                    next_frontier.append(cr)
            frontier = next_frontier
            depth += 1

    return results
