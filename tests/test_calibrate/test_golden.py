"""E1 — golden-set eval corpus + per-step regression gate (the keystone).

Pattern: Palantir 10%->90% by building evals from historical queries first
(PALANTIR.md:L341-353); CoCounsel 999/1000 release gate (YC_ROOT_ACCESS.md:L13664).

The golden corpus runs OFFLINE (no keys) through the categorical (E2) judge, emits
a per-component (decompose / retrieval / synthesis) pass-rate report, and a gate
that exits non-zero on regression — the gate later enhancements run against.
"""

from __future__ import annotations

import json
from pathlib import Path

from bad_research.calibrate.golden import (
    GOLDEN_DIR,
    GoldenCase,
    evaluate_corpus,
    load_golden_corpus,
)


# ── corpus loading + schema ──────────────────────────────────────────────────
def test_golden_dir_ships_a_seed_corpus():
    cases = load_golden_corpus()
    assert GOLDEN_DIR.is_dir()
    assert 6 <= len(cases) <= 100, "seed set is ~6-10 (extensible to 100)"
    for c in cases:
        assert isinstance(c, GoldenCase)
        assert c.query
        assert c.expected_behavior  # Anthropic-style rubric, non-empty
        assert set(c.axes_floor).issubset(
            {"factual", "citation", "completeness", "source_quality", "efficiency"}
        )


def test_corpus_is_trivially_extensible(tmp_path: Path):
    # Dropping a single JSON file into the dir adds a case — no code change.
    case = {
        "id": "extra-1",
        "query": "Is the sky blue?",
        "report": "# Is the sky blue?\n\nRayleigh scattering makes it blue [1].\n",
        "corpus": [{"note_id": "1", "url": "https://a.edu", "text": "Rayleigh scattering makes the sky blue."}],
        "expected_behavior": ["names Rayleigh scattering", "cites a source"],
        "axes_floor": {"citation": "pass"},
        "components": {},
    }
    (tmp_path / "extra-1.json").write_text(json.dumps(case))
    cases = load_golden_corpus(tmp_path)
    assert len(cases) == 1
    assert cases[0].id == "extra-1"


# ── per-component eval split (decompose / retrieval / synthesis) ──────────────
def test_decompose_component_is_scored_offline():
    """A case with a decompose fixture checks classify_route deterministically ($0)."""
    cases = load_golden_corpus()
    report = evaluate_corpus(cases)  # offline: StubJudge-free, deterministic judge
    assert "decompose" in report.components
    assert "retrieval" in report.components
    assert "synthesis" in report.components


def test_evaluate_corpus_emits_a_pass_rate_report():
    cases = load_golden_corpus()
    report = evaluate_corpus(cases)
    assert 0.0 <= report.pass_rate <= 1.0
    assert report.total == len(cases)
    # the seed corpus is built to PASS (it is the baseline the gate defends).
    assert report.pass_rate >= 0.8
    d = report.to_dict()
    assert "pass_rate" in d and "components" in d and "cases" in d


# ── the regression gate ───────────────────────────────────────────────────────
def test_gate_passes_on_a_passing_corpus():
    cases = load_golden_corpus()
    report = evaluate_corpus(cases)
    assert report.gate_ok(floor=0.8) is True


def test_gate_fails_on_a_deliberately_broken_case():
    # An uncited, evidence-contradicting report must fail the judge -> gate trips.
    bad = GoldenCase(
        id="broken",
        query="Does coffee cure cancer?",
        report="# Does coffee cure cancer?\n\nCoffee definitively cures all cancers.\n",
        corpus=[{"note_id": "1", "url": "https://a.edu", "text": "No causal link is established."}],
        expected_behavior=["does NOT overclaim", "stays grounded in the corpus"],
        axes_floor={"citation": "pass", "factual": "pass"},
        components={},
    )
    report = evaluate_corpus([bad])
    assert report.pass_rate < 0.8
    assert report.gate_ok(floor=0.8) is False


def test_gate_trips_below_a_stored_baseline():
    cases = load_golden_corpus()
    report = evaluate_corpus(cases)
    # a baseline ABOVE the current pass-rate is a regression -> gate trips.
    assert report.gate_ok(baseline=report.pass_rate + 0.01) is False
    # at-or-below baseline is fine.
    assert report.gate_ok(baseline=report.pass_rate) is True


# ── the corpus runs with ZERO keys (the keystone invariant) ───────────────────
def test_corpus_eval_needs_zero_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cases = load_golden_corpus()
    report = evaluate_corpus(cases)  # must not require a provider
    assert report.total == len(cases)
