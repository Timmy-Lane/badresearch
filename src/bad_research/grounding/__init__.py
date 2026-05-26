"""Grounding / no-hallucination layer (Plan 06).

Forward: DSS span extraction + claim_anchors. Backward: CitationVerifier
(byte-identity -> local NLI -> triage-LLM judge) + the deterministic Stage-16
no-uncited-claim gate.
"""
