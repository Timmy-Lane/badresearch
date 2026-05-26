"""gather() — the public funnel entry point. Wires Stage A→B→C→D→E→F.

INVARIANT: callers receive list[Chunk] (reranked top chunks) + [[note-id]]
pointers — NEVER raw page bodies. Sources scale (12→80 notes); context stays
flat (~5-15k tokens) because only Stage-F chunks ever cross into the prompt.

Stages A-E run at $0 model cost. The seams (providers/fetch_tiered/postfetch_
filter/RetrievalEngine/vault) are injected via FunnelDeps so the funnel logic
is testable in isolation; the width-sweep skill backend (Plan 08) assembles the
real wiring. Every SYNCHRONOUS seam (search_ex, fetch_tiered) is reached through
funnel._async.acall inside fan_out / read_top_k.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bad_research.funnel.config import FunnelConfig
from bad_research.funnel.dedup import dedup
from bad_research.funnel.fanout import fan_out, plan_queries
from bad_research.funnel.filter import filter_and_store
from bad_research.funnel.rank import rank_candidates
from bad_research.funnel.read import read_top_k


@dataclass
class FunnelDeps:
    """The cross-plan seams the funnel composes (all behind Protocols).

    providers:        list[WebSearchProvider]  (Plan 03 cascade survivors)
    fetcher:          obj with async fetch_tiered(url, *, tier_max, ...) (Plan 04)
    postfetch_filter: callable(WebResult) -> str | None  (Plan 05)
    vault:            obj with store_note(*, title, body, url, provider) -> note_id
    retrieval:        RetrievalEngine (Plan 02) — .index(notes), .search(q, mode, top_k)
    """

    providers: list
    fetcher: object
    postfetch_filter: object
    vault: object
    retrieval: object


async def gather(
    query: str,
    *,
    mode: Literal["light", "full"],
    deps: FunnelDeps,
    queries: list | None = None,
) -> list:
    """Run the six-stage funnel and return reranked Chunk[] (never raw pages).

    `queries` (optional): a caller-supplied lens-driven SearchQuery plan
    (the width-sweep skill passes its 3-lens A/B/C/D plan). When omitted we fall
    back to plan_queries (deterministic expansion).
    """
    cfg = FunnelConfig.for_mode(mode)

    # ── Stage A — FAN-OUT (parallel, cheap, never near the model) ──────────
    if queries is None:
        queries = plan_queries(query, m_queries=cfg.m_queries, k_per_query=cfg.k_per_query)
    active_providers = deps.providers[: cfg.p_providers]
    raw_hits = await fan_out(queries, active_providers)

    # ── Stage B — DEDUP (URL-canonical + content-hash, free) ───────────────
    candidates = dedup(raw_hits)
    candidates = candidates[: cfg.candidate_pool]   # cap the pool

    # ── Stage C — RANK un-read candidates (RRF k=60 + utility) ─────────────
    ranked = rank_candidates(candidates, query, rrf_k=cfg.rrf_k)

    # ── Stage D — READ top-K (≤80 ceiling, batched, chained-crawl) ─────────
    pages = await read_top_k(
        ranked,
        fetcher=deps.fetcher,
        read_top_k=cfg.read_top_k,
        concurrency=cfg.read_concurrency,
        max_chain_depth=cfg.max_chain_depth,
        max_links_per_hub=cfg.max_links_per_hub,
        query=query,
        ceiling=FunnelConfig.READ_CEILING,
    )

    # ── Stage E — FILTER (junk + >60% redundancy) + STORE to vault ─────────
    stored = filter_and_store(
        pages,
        vault=deps.vault,
        postfetch_filter=deps.postfetch_filter,
        redundancy_overlap=cfg.redundancy_overlap,
        shingle_n=cfg.shingle_n,
    )
    if not stored:
        return []   # honest gap, never hallucinate (SPEC §13)

    # ── Stage F — RERANK chunks via RetrievalEngine → top set ──────────────
    # The vault holds the breadth (raw bodies on disk); the engine indexes them
    # and returns only the reranked top chunks the model will see.
    deps.retrieval.index(stored)
    chunks = deps.retrieval.search(query, mode=mode, top_k=cfg.top_chunks)
    return chunks
