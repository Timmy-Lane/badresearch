from __future__ import annotations

import sqlite3

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import (
    Finding,
    gate_blocks_ship,
    is_factual_claim,
    no_uncited_claim_gate,
)


def _store_with(anchors):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_is_factual_claim_filters_trivia():
    assert is_factual_claim("Latency dropped to 12.4 ms under load.") is True   # number
    assert is_factual_claim("Vietnam led Southeast Asia in penetration.") is True  # named entity + superlative
    assert is_factual_claim("This report covers three regions.") is False       # meta-sentence
    assert is_factual_claim("What drives adoption?") is False                   # question
    assert is_factual_claim("In general, markets vary.") is False               # hedge-frame opener


def test_gate_fails_report_with_uncited_factual_claim():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024.\n"  # hard number, no [N]
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "uncited-claim" and f.severity == "critical" for f in findings)
    assert gate_blocks_ship(findings) is True


def test_gate_passes_fully_cited_verified_report():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 1
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert findings == []
    assert gate_blocks_ship(findings) is False


def test_gate_flags_dangling_cite():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024. [[no-such-anchor]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "dangling-cite" and f.severity == "critical" for f in findings)


def test_gate_flags_unverified_cite():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 0  # resolves but verifier never passed it
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "unverified-cite" and f.severity == "major" for f in findings)
    # major alone does not block ship.
    assert gate_blocks_ship(findings) is False


def test_gate_ignores_sources_section():
    store = _store_with([])
    report = (
        "This report covers three regions.\n"
        "## Sources\n"
        "1. https://example.com  Some uncited claim with a number 42 here.\n"
    )
    findings = no_uncited_claim_gate(report, store)
    assert findings == []
