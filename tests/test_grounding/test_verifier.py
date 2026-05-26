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
