from __future__ import annotations

import bad_research.grounding as g


def test_public_api_surface():
    for name in (
        "extract_spans", "ClaimAnchor", "quote_sha", "AnchorStore", "build_from_claims",
        "CitationVerifier", "VerifyVerdict", "VerifyResult", "CitationFinding",
        "no_uncited_claim_gate", "Finding", "gate_blocks_ship",
        "render_citation", "extract_citations", "coalesce_citations", "NLI_MODEL_NAME",
    ):
        assert hasattr(g, name), f"missing public export: {name}"
