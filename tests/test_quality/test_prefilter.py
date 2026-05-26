"""Tests for Stage-1 pre-fetch source filtering (dossier 07 §1)."""

from __future__ import annotations

from bad_research.quality.prefilter import seo_farm_score


def test_seo_farm_score_blocks_listicle_plus_money_path(farm_candidates):
    url, snippet = farm_candidates[0]  # best-laptops-2026-review + "17 best ... top picks"
    assert seo_farm_score(url, snippet, query="laptops") >= 2


def test_seo_farm_score_blocks_clickbait_plus_money_path(farm_candidates):
    url, snippet = farm_candidates[1]
    assert seo_farm_score(url, snippet, query="vpn") >= 2


def test_seo_farm_score_blocks_keyword_stuffing(farm_candidates):
    url, snippet = farm_candidates[2]
    assert seo_farm_score(url, snippet, query="vpn") >= 2


def test_seo_farm_score_keeps_arxiv(clean_candidates):
    url, snippet = clean_candidates[0]
    assert seo_farm_score(url, snippet, query="scaling laws") < 2


def test_seo_farm_score_keeps_single_signal_blog(clean_candidates):
    url, snippet = clean_candidates[2]  # one listicle signal only
    assert seo_farm_score(url, snippet, query="postgres") == 1


def test_seo_farm_score_thin_snippet_signal():
    # snippet < 120 chars AND ends mid-sentence "..." = +1
    score = seo_farm_score("https://x.example/p",
                           "A short teaser that cuts off mid thought and ...",
                           query="anything")
    assert score == 1
