"""Stage-16 recitation gate — RECITATION's *output* guarantee (Gemini §R3.9)
without its decoder machinery. Deterministic, $0, no LLM. Flags any report
sentence that reproduces a cited note's body too closely (a long verbatim run
or >50% of the sentence lifted contiguously). A `major` finding routes to the
patcher to paraphrase — it does NOT block ship (copying is a quality/legal smell,
not a correctness failure). dossier 16 §5."""

from __future__ import annotations

import re

from bad_research.grounding.gate import Finding, split_sentences, strip_sources_section

# dossier 16 §5.1 — IDEA defaults; tune on real reports (dossier §11 honest gap).
RECITATION_MAX_NGRAM = 12     # a verbatim run > 12 words = copying
RECITATION_MAX_OVERLAP = 0.50  # >50% of a sentence's tokens are one contiguous source run

_WORD = re.compile(r"[\w']+", re.UNICODE)
_CITE_TOKEN = re.compile(r"\[\[[^\]]+\]\]|\[\d+\]")
# A run that lives inside an explicit "..." quotation that also carries a [N]
# citation is exempt (Gemini's public-domain / direct-quote-with-attribution
# carve-out, dossier §5.1). An attributed direct quote is allowed to be verbatim:
# the sentence must contain BOTH a quoted span AND a citation token (the citation
# need not sit immediately after the closing quote — "…" the author wrote [1]).
_QUOTED_SPAN = re.compile(r'"[^"]+"')


def words(text: str) -> list[str]:
    """Lowercased word tokens with citation markup stripped."""
    return _WORD.findall(_CITE_TOKEN.sub("", text).lower())


def longest_common_contiguous_run(a: list[str], b: list[str]) -> list[str]:
    """The longest run of words that appears contiguously in BOTH sequences
    (word-level longest-common-substring via the classic DP table). Cheap over
    the small per-run corpus — not a character suffix-array."""
    if not a or not b:
        return []
    # prev/cur rows of the LCS-substring DP; track the best end+length.
    prev = [0] * (len(b) + 1)
    best_len = 0
    best_end = 0  # index in `a` (exclusive) where the best run ends
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len = cur[j]
                    best_end = i
        prev = cur
    return a[best_end - best_len:best_end]


def _is_exempt_quotation(sent: str) -> bool:
    """True iff the sentence carries BOTH an explicit "..." quotation AND a
    citation token — the attributed-direct-quote carve-out. Either ordering is
    accepted (quote-then-cite or quote ... attribution + cite)."""
    return bool(_QUOTED_SPAN.search(sent)) and bool(_CITE_TOKEN.search(sent))


def recitation_findings(report_md: str, note_bodies: dict[str, str]) -> list[Finding]:
    """For each prose sentence (Sources section excluded), flag a `major`
    recitation Finding if its longest contiguous verbatim run against any cited
    note body exceeds RECITATION_MAX_NGRAM words OR > RECITATION_MAX_OVERLAP of
    the sentence's tokens. One finding per sentence (first offending body wins)."""
    findings: list[Finding] = []
    body_words = {nid: words(body) for nid, body in note_bodies.items()}
    for sent in split_sentences(strip_sources_section(report_md)):
        if _is_exempt_quotation(sent):
            continue
        toks = words(sent)
        if not toks:
            continue
        for bw in body_words.values():
            run = longest_common_contiguous_run(toks, bw)
            if len(run) > RECITATION_MAX_NGRAM or len(run) / len(toks) > RECITATION_MAX_OVERLAP:
                findings.append(
                    Finding(
                        failure_mode="recitation",
                        severity="major",
                        location=sent,
                        recommendation=(
                            "Sentence reproduces a source span verbatim "
                            "(longest run %d words) — paraphrase and keep the [N] citation."
                            % len(run)
                        ),
                    )
                )
                break
    return findings


__all__ = [
    "RECITATION_MAX_NGRAM",
    "RECITATION_MAX_OVERLAP",
    "longest_common_contiguous_run",
    "recitation_findings",
    "words",
]
