"""CitationVerifier -- the Stage-11.5 re-grounding pass. Cheapest-first:
Tier A byte-identity ($0) -> Tier B local NLI ($0) -> Tier C triage-LLM judge
(only the NLI-neutral band, batched). Tool-locked [Read]. dossier 08 §2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from bad_research.llm.base import LLMMessage, LLMProvider

from .anchors import ClaimAnchor, quote_sha


class VerifyVerdict(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


def tier_a_byte_identity(anchor: ClaimAnchor, note_body: str) -> bool:
    """True iff anchor.quoted_support still sits at [char_start:char_end] of the
    live body AND its SHA matches anchor_id. Catches anchor drift + fabricated
    quotes at $0 (dossier §2.2 Tier A)."""
    if quote_sha(anchor.quoted_support) != anchor.anchor_id:
        return False
    sliced = note_body[anchor.char_start:anchor.char_end]
    return sliced == anchor.quoted_support


JUDGE_BATCH_SIZE = 20  # dossier §2.2: batch ~20 (claim, quote) pairs per call

# Verbatim CitationVerifier judge prompt (dossier 08 §2.2 option 2).
JUDGE_SYSTEM = (
    "You are the CitationVerifier. For each numbered (CLAIM, QUOTE) pair, decide if the\n"
    "QUOTE supports the CLAIM. Output JSON only: [{id, verdict, score, reason}].\n"
    "- verdict in {supported, partial, unsupported, contradicted}\n"
    "- score in 0.0-1.0 (confidence the quote supports the claim AS WRITTEN)\n"
    "- A QUOTE \"supports\" a CLAIM only if a careful reader, seeing ONLY the quote,\n"
    "  would agree the claim follows. Numbers must match exactly. Do NOT use outside\n"
    "  knowledge. If the claim adds a number/entity/scope absent from the quote ->\n"
    "  partial or unsupported. If the quote states the opposite -> contradicted."
)


def _parse_judge_json(text: str, n: int) -> list[tuple[VerifyVerdict, float]]:
    """Parse the judge's JSON array into per-id (verdict, score). Robust to the
    model wrapping the array in prose: extract the first [...] block."""
    start, end = text.find("["), text.rfind("]")
    blob = text[start:end + 1] if start != -1 and end != -1 else "[]"
    try:
        rows = json.loads(blob)
    except json.JSONDecodeError:
        rows = []
    out: list[tuple[VerifyVerdict, float]] = [(VerifyVerdict.UNSUPPORTED, 0.0)] * n
    for r in rows:
        if not isinstance(r, dict):
            continue
        i = r.get("id")
        if not isinstance(i, int) or not (0 <= i < n):
            continue
        try:
            verdict = VerifyVerdict(r.get("verdict", "unsupported"))
        except ValueError:
            verdict = VerifyVerdict.UNSUPPORTED
        score = float(r.get("score", 0.0))
        out[i] = (verdict, score)
    return out


def tier_c_judge(
    pairs: list[tuple[str, str]],
    llm: LLMProvider,
) -> list[tuple[VerifyVerdict, float]]:
    """Run the triage-tier LLM judge over (claim, quote) pairs, batched
    JUDGE_BATCH_SIZE per call. Returns per-pair (verdict, score)."""
    results: list[tuple[VerifyVerdict, float]] = []
    for batch_start in range(0, len(pairs), JUDGE_BATCH_SIZE):
        batch = pairs[batch_start:batch_start + JUDGE_BATCH_SIZE]
        payload = [
            {"id": idx, "claim": claim, "quote": quote}
            for idx, (claim, quote) in enumerate(batch)
        ]
        user = "PAIRS:\n" + json.dumps(payload, ensure_ascii=False)
        resp = llm.complete(
            [LLMMessage(role="system", content=JUDGE_SYSTEM),
             LLMMessage(role="user", content=user)],
            tier="triage",
            max_tokens=2048,
            temperature=0.0,
        )
        results.extend(_parse_judge_json(resp.text, len(batch)))
    return results
