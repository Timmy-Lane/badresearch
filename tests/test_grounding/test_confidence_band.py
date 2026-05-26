"""KR-6 — confidence-band derivation (dossier 16 §7). verify_score x fetcher-
confidence x n_independent_sources -> high/medium/low -> a hedge word in prose."""
from __future__ import annotations

from bad_research.grounding.verifier import confidence_band


def test_high_band_needs_strong_score_and_consensus():
    assert confidence_band(verify_score=0.85, fetcher_confidence="high", n_sources=3) == "high"


def test_medium_band_on_single_source():
    # verify_score high but only one source -> medium (dossier §7 rule)
    assert confidence_band(verify_score=0.85, fetcher_confidence="high", n_sources=1) == "medium"


def test_medium_band_on_mid_score():
    assert confidence_band(verify_score=0.55, fetcher_confidence="high", n_sources=3) == "medium"


def test_low_band_on_weak_score():
    assert confidence_band(verify_score=0.30, fetcher_confidence="high", n_sources=5) == "low"


def test_low_band_on_low_fetcher_confidence():
    assert confidence_band(verify_score=0.90, fetcher_confidence="low", n_sources=4) == "low"


def test_band_defaults_are_conservative():
    # missing fetcher confidence + single source -> not high
    assert confidence_band(verify_score=0.90, fetcher_confidence=None, n_sources=1) != "high"
