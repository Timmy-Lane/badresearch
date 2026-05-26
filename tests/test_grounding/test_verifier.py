from __future__ import annotations

from bad_research.grounding.anchors import ClaimAnchor
from bad_research.grounding.verifier import VerifyVerdict, tier_a_byte_identity


def test_tier_a_passes_when_quote_matches_offsets_and_sha():
    body = "Latency dropped to 12.4 ms under load in the benchmark."
    quote = "Latency dropped to 12.4 ms under load"
    start = body.find(quote)
    anchor = ClaimAnchor("n1", start, start + len(quote), "Latency fell.", quote)
    ok = tier_a_byte_identity(anchor, body)
    assert ok is True


def test_tier_a_fails_on_sha_mismatch_fabricated_quote():
    # Anchor claims a quote that is NOT at those offsets in the body -> fabricated.
    body = "The benchmark reported no latency regression at all."
    anchor = ClaimAnchor("n1", 0, 30, "Latency fell.", "Latency dropped to 12.4 ms under load")
    ok = tier_a_byte_identity(anchor, body)
    assert ok is False


import json

from bad_research.grounding.verifier import JUDGE_BATCH_SIZE, tier_c_judge


def test_tier_c_judge_parses_batched_json(fake_llm):
    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "supported", "score": 0.9, "reason": "exact"},
        {"id": 1, "verdict": "unsupported", "score": 0.2, "reason": "scope add"},
    ])]
    pairs = [
        ("SEA GMV grew 12.4%.", "a 12.4% YoY expansion"),
        ("Vietnam led at 64%.", "Vietnam was mentioned"),
    ]
    results = tier_c_judge(pairs, fake_llm)
    assert results[0] == (VerifyVerdict.SUPPORTED, 0.9)
    assert results[1] == (VerifyVerdict.UNSUPPORTED, 0.2)
    # Used exactly one batched triage call for the two pairs.
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["tier"] == "triage"


def test_tier_c_batches_in_chunks_of_20(fake_llm):
    # 25 pairs -> 2 calls (20 + 5). Script enough empty arrays to satisfy parse.
    fake_llm.script = [
        json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(20)]),
        json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(5)]),
    ]
    pairs = [(f"claim {i}", f"quote {i}") for i in range(25)]
    results = tier_c_judge(pairs, fake_llm)
    assert len(results) == 25
    assert len(fake_llm.calls) == 2
    assert JUDGE_BATCH_SIZE == 20


from bad_research.grounding.anchors import AnchorStore
from bad_research.grounding.verifier import CitationVerifier


class StubNLI:
    """Deterministic NLI: maps a quote substring -> fixed softmax."""

    def __init__(self, table):
        self.table = table  # dict[str, dict[str,float]]

    def predict(self, premise, hypothesis):
        for key, scores in self.table.items():
            if key in premise:
                return scores
        return {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}


def _store_with(anchors):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_verify_entailed_claim_supported_non_entailed_unsupported(fake_llm):
    body_a = "Latency dropped to 12.4 ms under load."
    body_b = "The author also enjoys hiking on weekends."
    qa = "Latency dropped to 12.4 ms under load"
    qb = "The author also enjoys hiking on weekends"
    aa = ClaimAnchor("nA", 0, len(qa), "Latency fell to 12.4 ms.", qa)
    ab = ClaimAnchor("nB", 0, len(qb), "Latency fell to 5 ms.", qb)
    store = _store_with([aa, ab])
    nli = StubNLI({
        qa: {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01},
        qb: {"entailment": 0.02, "neutral": 0.05, "contradiction": 0.93},
    })
    report = (
        f"Latency fell to 12.4 ms. [[{aa.anchor_id}]]\n"
        f"Latency fell to 5 ms. [[{ab.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body_a, "nB": body_b})
    by_anchor = {r.anchor_id: r for r in result.findings}
    assert by_anchor[aa.anchor_id].verdict is VerifyVerdict.SUPPORTED
    assert by_anchor[ab.anchor_id].verdict is VerifyVerdict.CONTRADICTED
    # Disposition persisted: supported anchor flagged verified=1.
    assert store.get(aa.anchor_id).verified == 1
    assert store.get(ab.anchor_id).verified == 0


def test_verify_fabricated_quote_tier_a_fails_unsupported(fake_llm):
    # Offsets point at body text that is NOT the quote -> Tier A fails -> unsupported.
    body = "No latency regression was observed in any trial."
    fabricated = "Latency dropped to 12.4 ms under load"
    a = ClaimAnchor("nA", 0, 30, "Latency fell.", fabricated)
    store = _store_with([a])
    nli = StubNLI({})  # never consulted -- Tier A short-circuits
    report = f"Latency fell. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.UNSUPPORTED
    assert len(fake_llm.calls) == 0  # no LLM spent on a fabricated quote


def test_verify_neutral_band_escalates_to_tier_c(fake_llm):
    import json
    body = "Adoption grew over the period across several markets."
    quote = "Adoption grew over the period across several markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption grew 12.4% in SEA.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})  # neutral
    fake_llm.script = [json.dumps([{"id": 0, "verdict": "partial", "score": 0.5}])]
    report = f"Adoption grew 12.4% in SEA. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.PARTIAL
    assert len(fake_llm.calls) == 1  # only the neutral band paid for an LLM call


class HypothesisAwareNLI:
    """NLI stub that decides from the HYPOTHESIS (report sentence), proving the
    verifier checks the sentence as written -- not the stored anchor.claim."""

    def predict(self, premise, hypothesis):
        if "DECLINED" in hypothesis or "fell" in hypothesis:
            return {"entailment": 0.02, "neutral": 0.05, "contradiction": 0.93}
        return {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01}


def test_verify_checks_report_sentence_not_stored_claim(fake_llm):
    # The anchor's stored claim is FAITHFUL to the support, but the report
    # SENTENCE that cites it says the opposite. The verifier must judge the
    # sentence as written -> CONTRADICTED (the drift is caught).
    body = "GMV grew 12.4% year over year across the region."
    quote = "GMV grew 12.4% year over year across the region"
    drifted = ClaimAnchor("nA", 0, len(quote), "GMV grew 12.4% YoY.", quote)  # faithful stored claim
    body_b = "Revenue rose by 12.4% over the prior year."
    quote_b = "Revenue rose by 12.4% over the prior year"
    faithful = ClaimAnchor("nB", 0, len(quote_b), "Revenue rose 12.4%.", quote_b)
    store = _store_with([drifted, faithful])
    nli = HypothesisAwareNLI()
    report = (
        # sentence DRIFTS to the opposite of its cited support -> caught
        f"Regional GMV DECLINED that year. [[{drifted.anchor_id}]]\n"
        # sentence stays faithful to its cited support -> supported
        f"Revenue rose by 12.4%. [[{faithful.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body, "nB": body_b})
    by_anchor = {r.anchor_id: r for r in result.findings}
    assert by_anchor[drifted.anchor_id].verdict is VerifyVerdict.CONTRADICTED
    assert by_anchor[faithful.anchor_id].verdict is VerifyVerdict.SUPPORTED
    assert store.get(drifted.anchor_id).verified == 0
    assert store.get(faithful.anchor_id).verified == 1
