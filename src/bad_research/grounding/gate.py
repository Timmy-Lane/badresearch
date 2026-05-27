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

# ── A-2: formatting-line skip set (false-positive guard) ─────────────────────
# A bold-only line is a pseudo-heading (`**Key Findings 2024**`), not a sentence.
_BOLD_ONLY = re.compile(r"^\*\*[^*].*\*\*$")
# A markdown table row / divider: starts (after optional indent) with a pipe.
_TABLE_ROW = re.compile(r"^\s*\|")
# A fenced-code delimiter line: ``` or ~~~ (optionally with a language tag).
_CODE_FENCE = re.compile(r"^\s*(?:`{3,}|~{3,})")
# A line whose entire visible content is one inline code span (`...`).
_CODE_SPAN_ONLY = re.compile(r"^\s*`[^`]+`\s*$")
# A leading list marker: a bullet (`-`/`*`/`+`) or an ordinal (`1.`/`1)`),
# stripped so a numbered item is ONE sentence (not the `1.` fragment + the rest).
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _is_formatting_line(line: str) -> bool:
    """True for structural chrome that carries no factual claim: bold-only
    pseudo-headings, markdown headings, table rows/dividers, and lone inline
    code spans. Code-fence handling is stateful and lives in `split_sentences`."""
    if line.startswith("#"):
        return True
    if _BOLD_ONLY.match(line):
        return True
    if _TABLE_ROW.match(line):
        return True
    return bool(_CODE_SPAN_ONLY.match(line))


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    in_code_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if _CODE_FENCE.match(line):
            # Toggle in/out of a fenced code block; the fence line itself is chrome.
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue  # source code, not prose -- never a factual sentence
        if not line or _is_formatting_line(line):
            continue
        # Strip a leading list marker so `1. Vietnam led ...` is one sentence,
        # not the spurious fragment `1.` split off by the ordinal's period.
        line = _LIST_MARKER.sub("", line, count=1).strip()
        if not line:
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


# ── E9: keyless semantic span support-check — lexical pre-filter ──────────────
# STEAL_LIST #4 (OpenAI `【ref†L42-L58】`): bind a claim to a SPECIFIC supporting
# span, not merely "a citation exists." On the keyless path the no-op NLI passes a
# *paraphrased* claim regardless of whether the cited span supports it. The cheap
# lexical pre-filter below bounds the cost of catching that: claim ≈ quote (overlap
# >= CLAIM_QUOTE_OVERLAP_SKIP) → accept on byte-identity, skip the host judge ($0);
# below it (a genuine paraphrase) → route to the batched host-model entailment judge.

# A claim whose token set is >= this fraction contained in the cited span is treated
# as "≈ the quote" — verbatim/near-verbatim. NOTE: this band is NOT covered by Tier-A:
# Tier-A byte-identity checks span-vs-body integrity (the quoted_support still sits at
# [char_start:char_end] with a matching SHA), NOT report-sentence-vs-span fidelity. The
# residual risk in this band — a >=0.8-overlap report sentence that flipped a number
# ("grew 12%" vs a span saying "grew 21%") — is caught by the `[local]`/keyed entailment
# lane (CrossEncoderNLI / Tier-C judge), not by Tier-A keyless. On the keyless+host
# path we accept this near-verbatim band to bound host-token cost: the host judge adds
# little over the lexical match and the number-flip boundary is a known keyless gap that
# the `[local]`/keyed lane closes when installed/keyed. dossier §2.2.
CLAIM_QUOTE_OVERLAP_SKIP = 0.8

_WORD_RE = re.compile(r"[a-z0-9]+")
# Stop tokens are stripped before overlap so two sentences are not judged "the same"
# merely for sharing "the/of/in"; this makes the ratio track CONTENT overlap.
_OVERLAP_STOP = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "by", "with", "as", "that", "this",
    "these", "those", "it", "its", "from", "into", "over", "under", "than", "then", "so",
})


def _content_tokens(text: str) -> set[str]:
    """Lowercased alphanumeric content tokens (stop words removed) — the unit the
    claim↔quote overlap ratio is computed over."""
    return {t for t in _WORD_RE.findall((text or "").lower()) if t not in _OVERLAP_STOP}


def claim_quote_overlap(claim: str, quote: str) -> float:
    """Fraction of the CLAIM's content tokens that also appear in the cited QUOTE
    (token-containment, asymmetric on purpose: the question is "is the claim covered
    by the span?", not "are the two equal in length?"). 1.0 = every claim word is in
    the quote (verbatim/near-verbatim); ~0.0 = the claim paraphrases something the
    span never says. An empty claim trivially overlaps (nothing to support)."""
    c = _content_tokens(claim)
    if not c:
        return 1.0
    q = _content_tokens(quote)
    return len(c & q) / len(c)
