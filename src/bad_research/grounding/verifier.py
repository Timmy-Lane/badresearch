"""CitationVerifier -- the Stage-11.5 re-grounding pass. Cheapest-first:
Tier A byte-identity ($0) -> Tier B local NLI ($0) -> Tier C triage-LLM judge
(only the NLI-neutral band, batched). Tool-locked [Read]. dossier 08 §2."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from bad_research.llm.base import LLMMessage, LLMProvider

from .anchors import AnchorStore, ClaimAnchor, quote_sha
from .nli import NLILabel, NLIModel, classify_nli
from .render import extract_citations


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


# soft/hard score bands for the disposition table (dossier §2.3).
PARTIAL_LOW, SUPPORTED_FLOOR = 0.40, 0.70


# Confidence-band thresholds (dossier 16 §7 / 08 §4). The band is the prose hedge
# driver; the raw verify_score stays off-band on claim_anchors (Gemini §879).
BAND_HIGH_SCORE = 0.70
BAND_LOW_SCORE = 0.40


def confidence_band(
    verify_score: float, fetcher_confidence: str | None, n_sources: int
) -> str:
    """Combine the verifier's score, the fetcher's self-reported confidence, and
    the independent-source count into a high/medium/low band (dossier 16 §7):

      high   : fetcher=high AND verify_score>=0.70 AND n_sources>=2
      medium : verify_score in [0.40, 0.70) OR n_sources==1
      low    : verify_score<0.40 OR fetcher=low

    Low wins over high (conservative). The patcher hedges medium/low claims."""
    if verify_score < BAND_LOW_SCORE or fetcher_confidence == "low":
        return "low"
    if (
        fetcher_confidence == "high"
        and verify_score >= BAND_HIGH_SCORE
        and n_sources >= 2
    ):
        return "high"
    return "medium"


@dataclass
class CitationFinding:
    anchor_id: str
    sentence: str
    verdict: VerifyVerdict
    score: float
    confidence_band: str | None = None


@dataclass
class VerifyResult:
    findings: list[CitationFinding]


# A piece made up only of citation tokens -- it trails a sentence, not its own.
_CITES_ONLY = re.compile(r"^\s*(?:\[\[[^\]]+\]\]|\[\d+\])(?:\s*(?:\[\[[^\]]+\]\]|\[\d+\]))*\s*[.;,]?\s*$")

# Any citation token (numeric [N] or [[note-id]] wiki-link) -- stripped from the
# report sentence before it is used as the NLI/judge hypothesis so the entailment
# check sees the prose claim, not the citation markup.
_CITE_TOKEN = re.compile(r"\[\[[^\]]+\]\]|\[\d+\]")


def _sentence_text(sent: str) -> str:
    """The report sentence with its citation tokens removed and whitespace
    collapsed -- the hypothesis the verifier checks against the cited support."""
    return re.sub(r"\s+", " ", _CITE_TOKEN.sub("", sent)).strip()


def _split_sentences(text: str) -> list[str]:
    # Shared shape with the gate; deterministic. Split on terminal punctuation
    # followed by whitespace; a trailing citation-only fragment (`. [[note-id]]`)
    # is re-attached to the sentence it trails so the verdict keeps its sentence
    # text. Newline-delimited report lines are each at least one sentence.
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if not piece:
                continue
            if parts and _CITES_ONLY.match(piece):
                parts[-1] = f"{parts[-1]} {piece}"
            else:
                parts.append(piece)
    return parts


class CitationVerifier:
    """Stage-11.5 re-grounding pass. Tool-locked [Read]: reads the report +
    anchors + note bodies; writes only the findings + the verified flag (via the
    AnchorStore DAL) -- it does NOT edit the report. dossier §2.3."""

    def __init__(self, *, nli: NLIModel, llm: LLMProvider) -> None:
        self.nli = nli
        self.llm = llm

    def verify(
        self, report_md: str, store: AnchorStore, note_bodies: dict[str, str]
    ) -> VerifyResult:
        # Pass 1: per cited sentence, run Tier A then Tier B; collect the
        # NLI-neutral band for a single batched Tier-C call.
        pending: list[tuple[CitationFinding, str, str]] = []  # (finding-stub, claim, quote)
        findings: list[CitationFinding] = []

        for sent in _split_sentences(report_md):
            # The hypothesis is the report sentence AS WRITTEN (citation markup
            # stripped), not the stored anchor.claim. This catches a synthesizer
            # sentence that drifted from the claim it cites: the support is judged
            # against what the report actually says (dossier §2.2).
            hypothesis = _sentence_text(sent)
            for token in extract_citations(sent):
                anchor = store.get(token)
                if anchor is None:
                    continue  # dangling cite -- the gate (Task 11) handles it
                body = note_bodies.get(anchor.note_id, "")
                # Tier A -- byte-identity ($0).
                if not tier_a_byte_identity(anchor, body):
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.UNSUPPORTED, 0.0))
                    continue
                # Tier B -- local NLI ($0). premise=quoted_support, hypothesis=report sentence.
                scores = self.nli.predict(anchor.quoted_support, hypothesis)
                label = classify_nli(scores)
                if label is NLILabel.ENTAILMENT:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.SUPPORTED, scores["entailment"]))
                elif label is NLILabel.CONTRADICTION:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.CONTRADICTED, scores["contradiction"]))
                else:
                    stub = CitationFinding(anchor.anchor_id, sent, VerifyVerdict.UNSUPPORTED, 0.0)
                    # Tier C judges the report sentence (claim) vs the quoted support.
                    pending.append((stub, hypothesis, anchor.quoted_support))

        # Pass 2: Tier C -- judge the neutral band only, batched.
        if pending:
            pairs = [(claim, quote) for _, claim, quote in pending]
            judged = tier_c_judge(pairs, self.llm)
            for (stub, _, _), (verdict, score) in zip(pending, judged, strict=True):
                stub.verdict = verdict
                stub.score = score
                findings.append(stub)

        # Persist dispositions (dossier §2.3) + stamp the confidence band (dossier
        # 16 §7). fetcher-confidence + n_independent_sources come from the claims
        # JSON the caller threads via note_bodies' companion data; absent that, the
        # band derives from verify_score alone (conservative). The CLI writes the
        # band into citation-verify-actions.json for the patcher's hedge rule.
        for f in findings:
            f.confidence_band = confidence_band(
                f.score, fetcher_confidence=None, n_sources=1
            )
            if f.verdict is VerifyVerdict.SUPPORTED:
                store.set_verified(f.anchor_id, verified=1, score=f.score)
            else:
                store.set_verified(f.anchor_id, verified=0, score=f.score)

        return VerifyResult(findings=findings)
