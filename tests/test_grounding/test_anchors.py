from __future__ import annotations

import hashlib

from bad_research.grounding.anchors import ClaimAnchor, quote_sha


def test_quote_sha_is_first_8_chars_of_sha256():
    q = "latency dropped to 12.4 ms under load"
    expected = hashlib.sha256(q.encode("utf-8")).hexdigest()[:8]
    assert quote_sha(q) == expected
    assert len(quote_sha(q)) == 8


def test_claim_anchor_anchor_id_defaults_to_quote_sha():
    a = ClaimAnchor(
        note_id="source-note-12",
        char_start=10,
        char_end=47,
        claim="Latency fell to 12.4 ms.",
        quoted_support="latency dropped to 12.4 ms under load",
    )
    assert a.anchor_id == quote_sha(a.quoted_support)
    assert a.verified == 0
    assert a.verify_score is None
