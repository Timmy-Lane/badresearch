"""Populate the `sources` provenance/dedup table (INTERFACES.md vault schema).

source_id = 16-char SHA-256 of the canonical URL. domain_tier REAL = the multiplier;
tier INT = the prefetch_priority (0..9). Dual-temporal {document_date, event_date}
read from WebResult.metadata when the extractor set them (Plan 06 grounding).
DDL is owned by Plan 01/02 schema migration; this module only writes rows.
"""

from __future__ import annotations

import hashlib
import sqlite3

from bad_research.quality.prefilter import canonical_url, domain_tier
from bad_research.web.base import WebResult

# ── E8: source-quality epistemic penalty (STEAL_LIST #5) ──────────────────────
# Anthropic's worker prompts carry a verbatim negative-signal list (research_subagent
# pattern): "news aggregators rather than original sources, false authority, passive
# voice with nameless sources, general qualifiers without specifics, unconfirmed
# reports, marketing language, spin language, speculation, cherry-picked data." The
# discipline is FLAG, not suppress (the fetcher flags; rank.py reconciles). The
# DOMAIN_TIER/seo_farm layer catches what regex/domain can see; these flags catch the
# epistemic junk a regex can't (a marketing-spin page on a GOOD domain). Each flag is
# an independent multiplicative down-weight applied ALONGSIDE the domain-tier multiplier,
# so a spin page on docs.* still drops below a clean primary. Penalties are tuned so a
# single hard flag (marketing_spin/nameless_source) roughly cancels a one-tier authority
# bump; soft flags (vague_qualifier/speculation) nudge. Provenance: each flag maps to one
# named signal in the verbatim list above.
EPISTEMIC_PENALTY: dict[str, float] = {
    "aggregator": 0.70,       # news aggregator, not the original source
    "false_authority": 0.55,  # cites authority it doesn't actually have / misattributes
    "nameless_source": 0.60,  # passive voice w/ nameless sources ("experts say")
    "vague_qualifier": 0.80,  # general qualifiers without specifics ("many", "often")
    "unconfirmed": 0.65,      # unconfirmed reports / rumor not yet verified
    "marketing_spin": 0.50,   # marketing language + spin language (hardest down-weight)
    "speculation": 0.75,      # speculation presented as finding
    "cherry_picked": 0.60,    # cherry-picked data / selective evidence
}


def epistemic_multiplier(flags: list[str] | None) -> float:
    """Compound the EPISTEMIC_PENALTY for each recognized source-quality flag. No
    flags -> 1.0 (flag, don't suppress: an unflagged source is unchanged). Unknown
    flags are ignored (forward-compatible: a future prompt's new flag never silently
    zeroes a source). Multiplicative because flags are independent evidence of junk."""
    if not flags:
        return 1.0
    mult = 1.0
    for f in flags:
        mult *= EPISTEMIC_PENALTY.get(f, 1.0)
    return mult


def source_id(url: str) -> str:
    """16-char SHA-256 hex of the canonical URL (INTERFACES.md `sources.source_id`)."""
    canon = canonical_url(url)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def build_source_row(result: WebResult, *, fetch_provider: str, fetch_tier: int) -> dict[str, object]:
    """Build the `sources` row dict for a fetched WebResult.

    fetch_tier is the Tier 0-3 fetch ladder level (browse/base.fetch_tiered), distinct
    from the DOMAIN_TIER authority. We persist DOMAIN_TIER as domain_tier(REAL)+tier(INT).
    """
    info = domain_tier(result.url)
    return {
        "source_id": source_id(result.url),
        "url": result.url,
        "domain": result.domain,
        "domain_tier": info.multiplier,                 # REAL: 1.30 … 0.50
        "fetch_provider": fetch_provider,
        "tier": info.prefetch_priority,                 # INT: 0 … 9
        "fetched_at": result.fetched_at.isoformat(),
        "document_date": result.metadata.get("document_date"),
        "event_date": result.metadata.get("event_date"),
    }


def upsert_source(conn: sqlite3.Connection, result: WebResult, *,
                  fetch_provider: str, fetch_tier: int) -> None:
    """Idempotently write a sources row (INSERT OR REPLACE on source_id PK)."""
    row = build_source_row(result, fetch_provider=fetch_provider, fetch_tier=fetch_tier)
    conn.execute(
        "INSERT OR REPLACE INTO sources "
        "(source_id, url, domain, domain_tier, fetch_provider, tier, fetched_at, "
        " document_date, event_date) "
        "VALUES (:source_id, :url, :domain, :domain_tier, :fetch_provider, :tier, "
        ":fetched_at, :document_date, :event_date)",
        row,
    )
    conn.commit()
