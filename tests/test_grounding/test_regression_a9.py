"""Regression fixture A-9: a cited-but-contradicting claim must be caught at
RUNTIME by the LineSpanJudge + CitationVerifier + gate path.

This is the deterministic (no-LLM) in-process half of the regression guard.
The full offline golden fixture (09_cited_contradiction, requires_llm: true)
lives in Workstream E1 (see docs/superpowers/plans/sections/D-E1.md) and is
exercised by the LLMJudge gap-proofs in tests/test_calibrate/test_golden.py.
This file does NOT depend on that fixture: it uses the FakeLLMProvider stub so
the Tier-C judgement is deterministic without any live model or key.

Deviation note (vs the A-9 plan text): the plan's example fixture used the claim
"GDP grew 2.1% year-over-year." against the span "GDP declined 2.1% year-over-year
due to trade disruptions." That pair has lexical overlap == 0.80, which is
>= CLAIM_QUOTE_OVERLAP_SKIP (0.8), so LineSpanJudge routes it to ENTAILMENT and it
never reaches Tier-C — the fake LLM would never be consulted and the contradiction
would be (wrongly) rubber-stamped SUPPORTED. To preserve the task's INTENT (a cited
claim that contradicts its span is caught at runtime), the report sentence is phrased
as a genuine paraphrase (overlap < 0.8) so it correctly escalates to the batched
Tier-C judge, where the (faked) host model returns "contradicted".
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import gate_blocks_ship, no_uncited_claim_gate
from bad_research.grounding.verifier import (
    CitationVerifier,
    LineSpanJudge,
    VerifyVerdict,
)
from tests.test_grounding.conftest import FakeLLMProvider


def _store_with_anchor(anchor: ClaimAnchor) -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    store.upsert(anchor)
    return store


@pytest.fixture
def contradicting_fixture():
    """A note whose cited span says the economy DECLINED; the report claims it
    EXPANDED. The cited span contradicts the claim — and the report sentence is a
    genuine paraphrase (low lexical overlap) so it escalates past Tier-B to the
    Tier-C judge, where the contradiction is caught."""
    body = (
        "Economic indicators for Q4 2024:\n"
        "GDP declined 2.1% year-over-year due to trade disruptions.\n"
        "Unemployment rose to 8.3% in the same period.\n"
    )
    quote = "GDP declined 2.1% year-over-year due to trade disruptions."
    start = body.index(quote)
    end = start + len(quote)

    from bad_research.grounding.extract import body_to_lines, char_span_to_line_range

    bl = body_to_lines(body)
    ls, le = char_span_to_line_range(bl, start, end)

    anchor = ClaimAnchor(
        note_id="n1",
        char_start=start,
        char_end=end,
        # A paraphrase that asserts the OPPOSITE of the cited span.
        claim="The regional economy expanded over the past year.",
        quoted_support=quote,
        line_start=ls,
        line_end=le,
    )
    # Report sentence == the claim text (paraphrase, overlap < CLAIM_QUOTE_OVERLAP_SKIP).
    report_sentence = "The regional economy expanded over the past year."
    return body, anchor, report_sentence


def test_contradicting_claim_reaches_tier_c(contradicting_fixture):
    """The report sentence asserts expansion; the cited span says decline.
    LineSpanJudge routes the paraphrase (low overlap) to NEUTRAL -> Tier-C, where
    the faked host judge returns 'contradicted'. The runtime verdict must be
    CONTRADICTED (NOT SUPPORTED) with a sub-PARTIAL_LOW score, and the anchor must
    be stamped verified=0."""
    body, anchor, report_sentence = contradicting_fixture
    store = _store_with_anchor(anchor)

    # Fake LLM returns "contradicted" for this (claim, span) pair — the single
    # batched Tier-C call. With an empty/short script the verifier would default
    # to UNSUPPORTED; here we assert the explicit contradiction path.
    fake_llm = FakeLLMProvider(
        script=[
            json.dumps(
                [
                    {
                        "id": 0,
                        "verdict": "contradicted",
                        "score": 0.05,
                        "reason": "span says declined, claim says expanded",
                    }
                ]
            )
        ]
    )

    nli = LineSpanJudge(fake_llm)
    verifier = CitationVerifier(nli=nli, llm=fake_llm)

    report = f"{report_sentence} [[{anchor.anchor_id}]]"
    result = verifier.verify(report, store, {"n1": body})

    # It escalated to the batched Tier-C judge (i.e. the host model was consulted).
    assert len(fake_llm.calls) == 1, "paraphrase must escalate to the Tier-C judge"

    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.verdict == VerifyVerdict.CONTRADICTED, (
        f"Expected CONTRADICTED for a span-vs-claim mismatch, got {f.verdict}"
    )
    assert f.verdict != VerifyVerdict.SUPPORTED
    assert f.score < 0.40  # well below PARTIAL_LOW

    # Runtime persistence: a non-SUPPORTED verdict stamps the anchor verified=0
    # (the G4 fix end-to-end — a contradicting cite never reads as verified).
    stamped = store.get(anchor.anchor_id)
    assert stamped is not None
    assert stamped.verified == 0
    assert stamped.verify_score is not None and stamped.verify_score < 0.40


def test_gate_blocks_ship_on_contradicted_low_score_cite(contradicting_fixture):
    """After the verifier stamps verify_score < PARTIAL_LOW, the gate must emit a
    CRITICAL finding that blocks ship (gate_blocks_ship returns True)."""
    body, anchor, _report_sentence = contradicting_fixture
    # Stamp the anchor as failed with a low score (the post-verify state).
    anchor.verified = 0
    anchor.verify_score = 0.05  # below PARTIAL_LOW=0.40

    store = _store_with_anchor(anchor)

    # A factual report sentence citing the contradicted anchor (numbers trip the
    # is_factual_claim gate; the gate keys off the stored anchor's verify_score).
    report = f"The regional GDP rose 2.1% in 2024. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    assert gate_blocks_ship(findings), (
        "A cited-but-contradicting claim with verify_score < PARTIAL_LOW must block ship"
    )
    critical = [f for f in findings if f.severity == "critical"]
    assert critical, f"Expected at least one critical finding, got: {findings}"


# Dependency note: E1 builds the golden fixture 09_cited_contradiction with
# requires_llm: true; the LLMJudge gap-proofs in tests/test_calibrate/test_golden.py
# exercise that path. The tests above cover the deterministic in-process runtime
# path (Tier-C fake LLM) — they need no key and no live model.
