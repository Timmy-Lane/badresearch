"""Stage-16 deterministic no-uncited-claim gate. Pure string + table, $0, no LLM.
Hard pass/fail: any non-trivial factual sentence that lacks a verifiable, verified
citation blocks ship. Extends hyperresearch R2 density (hooks.py:1126). dossier §5."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .anchors import AnchorStore
from .render import extract_citations

# Hedge-frame openers that exempt a sentence (dossier §5.1 allowlist).
_HEDGE_OPENERS = ("in general,", "broadly,", "generally,", "overall,")
# Meta / framing sentence stems that carry no [N].
_META_STEMS = ("this report", "this section", "this analysis", "we cover", "the following")
_NAMED_ENTITY = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")
_NUMBER = re.compile(r"\d")
_COMPARATIVE = re.compile(
    r"\b(more|less|fewer|greater|higher|lower|larger|smaller|most|least|best|worst|"
    r"led|leading|highest|lowest|than|fastest|slowest)\b", re.IGNORECASE)
_CAUSAL_TEMPORAL = re.compile(
    r"\b(because|therefore|caused|causes|due to|results? in|since|after|before|"
    r"led to|drove|grew|fell|rose|declined|increased|decreased)\b", re.IGNORECASE)


@dataclass
class Finding:
    failure_mode: str   # uncited-claim | dangling-cite | unverified-cite
    severity: str       # critical | major | minor
    location: str       # the offending sentence
    recommendation: str


def strip_sources_section(report_md: str) -> str:
    """Drop everything from a `## Sources` (or `# References`) heading onward --
    the gate only judges the prose body (matches R2's exclusion)."""
    lines = report_md.splitlines()
    out: list[str] = []
    for line in lines:
        if re.match(r"^\s*#{1,6}\s+(sources|references)\b", line, re.IGNORECASE):
            break
        out.append(line)
    return "\n".join(out)


# A piece made up only of citation tokens (+ trailing punctuation) -- it belongs
# to the sentence it trails, not a sentence of its own.
_CITES_ONLY = re.compile(r"^\s*(?:\[\[[^\]]+\]\]|\[\d+\])(?:\s*(?:\[\[[^\]]+\]\]|\[\d+\]))*\s*[.;,]?\s*$")


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if not piece:
                continue
            # A trailing citation-only fragment (`. [[note-id]]`) is split off the
            # preceding sentence by the terminal period -- re-attach it so the
            # factual sentence keeps its citation (dossier §5.1 "in/adjacent to").
            if parts and _CITES_ONLY.match(piece):
                parts[-1] = f"{parts[-1]} {piece}"
            else:
                parts.append(piece)
    return parts


def is_factual_claim(sentence: str) -> bool:
    """A non-trivial factual claim: has a number, named entity, comparative/
    superlative, or causal/temporal assertion -- and is NOT a question, a
    meta-sentence, or a hedge-frame opener (dossier §5.1)."""
    s = sentence.strip()
    low = s.lower()
    if s.endswith("?"):
        return False
    if any(low.startswith(o) for o in _HEDGE_OPENERS):
        return False
    if any(low.startswith(m) for m in _META_STEMS):
        return False
    # Strip citation tokens before scanning for entities (so [[note-id]] isn't an entity).
    bare = re.sub(r"\[\[[^\]]+\]\]|\[\d+\]", "", s)
    if _NUMBER.search(bare):
        return True
    if _COMPARATIVE.search(bare):
        return True
    if _CAUSAL_TEMPORAL.search(bare):
        return True
    # Named entity that isn't merely the sentence-initial capital.
    ents = [m.group(0) for m in _NAMED_ENTITY.finditer(bare)]
    non_initial = [e for e in ents if not bare.lstrip().startswith(e)]
    return len(non_initial) >= 1


def no_uncited_claim_gate(report_md: str, anchors: AnchorStore) -> list[Finding]:
    findings: list[Finding] = []
    body = strip_sources_section(report_md)
    for sent in split_sentences(body):
        if not is_factual_claim(sent):
            continue
        cites = extract_citations(sent)
        if not cites:
            findings.append(Finding(
                "uncited-claim", "critical", sent,
                "Non-trivial factual sentence carries no citation. Add a vault cite or hedge/cut."))
            continue
        for c in cites:
            anchor = anchors.get(c)
            if anchor is None:
                findings.append(Finding(
                    "dangling-cite", "critical", sent,
                    f"Citation {c} resolves to no claim_anchor -- remove or repoint."))
            elif anchor.verified != 1:
                findings.append(Finding(
                    "unverified-cite", "major", sent,
                    f"Citation {c} was not confirmed by the CitationVerifier -- re-run Tier B or hedge."))
    return findings


def gate_blocks_ship(findings: list[Finding]) -> bool:
    """A run does not ship with any open `critical` finding (dossier §5.2)."""
    return any(f.severity == "critical" for f in findings)
