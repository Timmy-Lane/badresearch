"""Stage 5 — source-authority ranking (dossier 07 §5).

final = reranker_score x DOMAIN_TIER_multiplier x EPISTEMIC_multiplier, sorted desc.
The deterministic encoding of Claude Research eval axis #4 ("primary sources over
lower-quality secondary"). DEMOTES, never drops (dropping is Stages 1-2).
NIA's deep-rank long-tail penalty is CUT (our per-run corpus is small; §5.1).

E8 (STEAL_LIST #5): the EPISTEMIC multiplier folds the fetcher's per-source
`source_quality_flags` (marketing_spin / nameless_source / cherry_picked / …) in
ALONGSIDE the domain tier, so a marketing-spin page on a good domain is still
down-ranked below an unflagged lower-domain primary. Flag, don't suppress.
"""

from __future__ import annotations

from bad_research.quality.dedup import _tier_mult  # reuse the stamp-or-classify helper
from bad_research.quality.sources import epistemic_multiplier
from bad_research.web.base import WebResult


def authority_rank(results: list[WebResult]) -> list[WebResult]:
    """Sort by relevance_score x domain_tier_multiplier x epistemic_multiplier, desc.

    The epistemic multiplier comes from `metadata["source_quality_flags"]` (the
    additive claims-*.json field the fetcher now emits); absent/empty -> 1.0, so an
    unflagged source ranks exactly as before (backward-compatible)."""
    for r in results:
        rel = float(r.metadata.get("relevance_score", 0.0))
        epi = epistemic_multiplier(r.metadata.get("source_quality_flags"))
        r.metadata["epistemic_multiplier"] = epi
        r.metadata["authority_score"] = rel * _tier_mult(r) * epi
    return sorted(results, key=lambda r: r.metadata["authority_score"], reverse=True)
