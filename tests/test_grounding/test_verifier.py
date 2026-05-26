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
