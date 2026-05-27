"""E8 — source-quality negative-signal list (STEAL_LIST #5).

The ALGORITHMIC layer (seo_farm_score, DOMAIN_TIER) catches what regex/domain can
see. E8 adds the PROMPT-level epistemic layer: the fetcher flags a source for false
authority / nameless sources / marketing-spin / cherry-picked data (judgment a regex
can't make), emits `source_quality_flags` in claims-*.json (additive), and rank.py
applies an EPISTEMIC_PENALTY multiplier ALONGSIDE the domain-tier multiplier — so a
marketing-spin page on a good domain still gets down-ranked. Flag, don't suppress.
"""
from __future__ import annotations

from datetime import UTC, datetime

from bad_research.quality.rank import authority_rank
from bad_research.quality.sources import EPISTEMIC_PENALTY, epistemic_multiplier
from bad_research.web.base import WebResult


def _wr(url: str, score: float, flags: list[str] | None = None) -> WebResult:
    r = WebResult(url=url, title="t", content="body " * 40,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    r.metadata["relevance_score"] = score
    if flags is not None:
        r.metadata["source_quality_flags"] = flags
    return r


# ── the flag→multiplier map ──────────────────────────────────────────────────

def test_epistemic_penalty_map_covers_the_anthropic_signals():
    # The verbatim Anthropic negative-signal classes must each have a penalty.
    for flag in ("aggregator", "false_authority", "nameless_source",
                 "vague_qualifier", "unconfirmed", "marketing_spin",
                 "speculation", "cherry_picked"):
        assert flag in EPISTEMIC_PENALTY
        assert 0.0 < EPISTEMIC_PENALTY[flag] <= 1.0


def test_epistemic_multiplier_is_one_when_no_flags():
    # Flag, don't suppress: an unflagged source is unchanged (multiplier 1.0).
    assert epistemic_multiplier([]) == 1.0
    assert epistemic_multiplier(None) == 1.0


def test_epistemic_multiplier_multiplies_multiple_flags():
    # Several flags compound multiplicatively (each is an independent down-weight).
    m = epistemic_multiplier(["aggregator", "marketing_spin"])
    assert abs(m - (EPISTEMIC_PENALTY["aggregator"] * EPISTEMIC_PENALTY["marketing_spin"])) < 1e-9


def test_epistemic_multiplier_ignores_unknown_flags():
    # An unknown flag is a no-op (forward-compatible: a new flag from a future
    # fetcher prompt does not silently zero a source out).
    assert epistemic_multiplier(["not_a_real_flag"]) == 1.0


# ── the rank-order move (THE acceptance test) ────────────────────────────────

def test_flagged_high_domain_source_ranks_below_unflagged_primary():
    # A marketing-spin docs page (high domain tier 1.15) must rank BELOW an unflagged
    # lower-domain primary source, EVEN when the spin page scored higher pre-penalty.
    # docs spin:    0.95 * 1.15 * 0.50(marketing_spin) = 0.546
    # primary clean:0.70 * 1.30 * 1.00                  = 0.910  -> primary wins
    spin_docs = _wr("https://docs.example.com/our-amazing-product", 0.95,
                    flags=["marketing_spin"])
    clean_primary = _wr("https://www.sec.gov/filing", 0.70, flags=[])
    ranked = authority_rank([spin_docs, clean_primary])
    assert ranked[0].url == "https://www.sec.gov/filing"


def test_unflagged_source_authority_score_unchanged_by_e8():
    # Backward compat: a source with NO source_quality_flags scores exactly as before
    # (relevance * domain_tier), i.e. the epistemic multiplier is 1.0.
    primary = _wr("https://www.sec.gov/filing", 0.80)  # no flags key at all
    ranked = authority_rank([primary])
    assert abs(ranked[0].metadata["authority_score"] - 1.04) < 1e-9  # 0.80 * 1.30


def test_flagged_source_stamps_epistemic_multiplier_in_metadata():
    # The applied penalty is observable (debuggability) and folds into authority_score.
    spin = _wr("https://blog.example/post", 0.90, flags=["marketing_spin"])
    ranked = authority_rank([spin])
    # 0.90 * 0.85(blog) * 0.50(marketing_spin) = 0.3825
    assert abs(ranked[0].metadata["authority_score"] - 0.3825) < 1e-9
    assert abs(ranked[0].metadata["epistemic_multiplier"] - 0.50) < 1e-9
