"""Shared fixtures for the quality-pipeline test suite. No network anywhere."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bad_research.web.base import WebResult

# --- Labeled SEO-farm vs clean URL/snippet fixtures (dossier 07 §1.1, §7 calibration) ---

FARM_CANDIDATES = [
    # listicle_title (+1) + money_page_path (+1) = 2  -> BLOCK
    ("https://gadgetdeals.example/best-laptops-2026-review",
     "The 17 best laptops you can buy in 2026 — top picks ranked"),
    # clickbait_title (+1) + money_page_path (+1) = 2  -> BLOCK
    ("https://clickfarm.example/cheap-vpn-deals",
     "You won't believe this one trick to get a VPN for almost free"),
    # listicle_title (+1) + stuffed_keywords (+1) = 2  -> BLOCK (query='vpn')
    ("https://spam.example/article",
     "Top 10 VPN tips: vpn vpn vpn vpn vpn for the best vpn experience"),
]

CLEAN_CANDIDATES = [
    # zero signals -> KEEP
    ("https://arxiv.org/abs/2403.01234",
     "Scaling Laws for Neural Language Models: an empirical study of compute-optimal training"),
    # primary-tier even though title has a number -> KEEP (allowlist exempt, score irrelevant)
    ("https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
     "Apple Inc. Form 10-K annual report for fiscal year ended September 28, 2024"),
    # one signal only (listicle) -> score 1 < 2 -> KEEP
    ("https://blog.example/notes",
     "5 things I learned migrating Postgres to a new region"),
]


@pytest.fixture
def farm_candidates() -> list[tuple[str, str]]:
    return FARM_CANDIDATES


@pytest.fixture
def clean_candidates() -> list[tuple[str, str]]:
    return CLEAN_CANDIDATES


# --- Near-duplicate document fixtures (dossier 07 §3.1) ---

_BASE_DOC = (
    "The transformer architecture introduced multi-head self-attention to replace recurrence. "
    "It computes scaled dot-product attention across all positions in parallel, which makes "
    "training far more efficient on modern accelerators. Positional encodings inject order "
    "information because attention itself is permutation invariant. The original model used "
    "six encoder and six decoder layers with residual connections and layer normalization."
)
# ~95% overlap: change only the final sentence's tail.
_NEAR_DUP = _BASE_DOC.replace(
    "six encoder and six decoder layers with residual connections and layer normalization.",
    "six encoder and six decoder blocks with residual links and layer normalization steps.",
)
_DISTINCT_DOC = (
    "Photosynthesis converts light energy into chemical energy stored in glucose. "
    "Chlorophyll absorbs red and blue wavelengths while reflecting green light. "
    "The light-dependent reactions occur in the thylakoid membrane and produce ATP and NADPH, "
    "which the Calvin cycle then uses to fix carbon dioxide into sugars in the stroma."
)


def _wr(url: str, content: str, *, tier: str = "blog", title: str = "Doc") -> WebResult:
    r = WebResult(url=url, title=title, content=content,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    r.metadata["domain_tier_name"] = tier
    return r


@pytest.fixture
def near_dup_pair() -> tuple[WebResult, WebResult]:
    return (_wr("https://a.example/transformer", _BASE_DOC, tier="blog"),
            _wr("https://b.example/transformer-repost", _NEAR_DUP, tier="forum"))


@pytest.fixture
def distinct_pair() -> tuple[WebResult, WebResult]:
    return (_wr("https://a.example/transformer", _BASE_DOC),
            _wr("https://c.example/photosynthesis", _DISTINCT_DOC))


# --- Deterministic reranker double (no network) for relevance/rank tests ---

class FakeReranker:
    """Returns a fixed score per doc by index, descending. Satisfies the Reranker Protocol."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        scored = [(i, self._scores[i]) for i in range(len(docs))]
        return sorted(scored, key=lambda t: t[1], reverse=True)


@pytest.fixture
def fake_reranker_factory():
    return FakeReranker
