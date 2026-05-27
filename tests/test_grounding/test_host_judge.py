"""E9 — keyless semantic span support-check (STEAL_LIST #4).

On the fully-keyless path the verifier's Tier-B NLI is the no-op CitationPresentNLI:
a *paraphrased* claim (its text is not a substring of quoted_support) reads as
entailed regardless of whether the span actually supports it → citation-drift slips
through. HostJudgeNLI closes that gap WITHOUT a new key/$: a cheap lexical overlap
pre-filter accepts claim≈quote on byte-identity (skips the judge, $0), and routes a
genuine paraphrase into the existing batched host-model Tier-C judge.
"""
from __future__ import annotations

import json
import sqlite3

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import CLAIM_QUOTE_OVERLAP_SKIP, claim_quote_overlap
from bad_research.grounding.verifier import (
    CitationPresentNLI,
    CitationVerifier,
    HostJudgeNLI,
    VerifyVerdict,
    default_nli,
)


def _store_with(anchors):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


# ── the lexical pre-filter ───────────────────────────────────────────────────

def test_overlap_skip_constant_is_point_eight():
    assert CLAIM_QUOTE_OVERLAP_SKIP == 0.8


def test_claim_quote_overlap_high_when_claim_is_near_the_quote():
    # claim ≈ quote (it IS the quote, citation markup aside) → overlap >= 0.8
    quote = "Latency dropped to 12.4 ms under load in the benchmark"
    claim = "Latency dropped to 12.4 ms under load"
    assert claim_quote_overlap(claim, quote) >= CLAIM_QUOTE_OVERLAP_SKIP


def test_claim_quote_overlap_low_when_claim_paraphrases_a_different_topic():
    # genuine paraphrase whose words barely overlap the cited span → < 0.8
    quote = "The author also enjoys hiking in the mountains on weekends"
    claim = "Quarterly revenue rose 40 percent year over year"
    assert claim_quote_overlap(claim, quote) < CLAIM_QUOTE_OVERLAP_SKIP


# ── HostJudgeNLI: pre-filter routes, judge catches drift ─────────────────────

def test_host_judge_accepts_when_claim_matches_quote_no_judge_call(fake_llm):
    # claim ≈ quote → entailment without ever calling the host judge ($0).
    nli = HostJudgeNLI(fake_llm)
    quote = "Latency dropped to 12.4 ms under load in the benchmark"
    claim = "Latency dropped to 12.4 ms under load"
    scores = nli.predict(quote, claim)
    assert scores["entailment"] >= 0.70
    assert len(fake_llm.calls) == 0  # high-overlap claim never paid for a judge call


def test_host_judge_routes_paraphrase_to_neutral_so_verifier_escalates(fake_llm):
    # A genuine paraphrase (low overlap) reads NEUTRAL from predict() — this is what
    # makes the verifier's Pass-2 batched Tier-C host judge run on it (the catch).
    nli = HostJudgeNLI(fake_llm)
    quote = "The author also enjoys hiking in the mountains on weekends"
    claim = "Quarterly revenue rose 40 percent year over year"
    scores = nli.predict(quote, claim)
    # NEUTRAL == not >= ENTAILMENT_PASS and not >= CONTRADICTION_FLAG.
    assert scores["entailment"] < 0.70
    assert scores["contradiction"] < 0.50
    # predict() itself does NOT call the host — batching happens in the verifier's Pass 2.
    assert len(fake_llm.calls) == 0


def test_keyless_paraphrase_citing_nonsupporting_span_is_caught(fake_llm):
    # THE POINT OF E9. On the keyless path: a report sentence that PARAPHRASES a
    # claim and cites a span that does NOT support it must be FLAGGED. Today (no-op
    # CitationPresentNLI) it passes as SUPPORTED. With HostJudgeNLI the low-overlap
    # pair escalates to the batched host judge, which returns unsupported.
    body = "The author also enjoys hiking in the mountains on weekends."
    quote = "The author also enjoys hiking in the mountains on weekends"
    # The anchor's quoted_support is the hiking sentence; the report sentence makes a
    # revenue claim citing it — citation drift.
    a = ClaimAnchor("nA", 0, len(quote), "Revenue rose 40%.", quote)
    store = _store_with([a])
    nli = HostJudgeNLI(fake_llm)
    # Host judge (keyless host model) returns unsupported for the drifted pair.
    fake_llm.script = [json.dumps([{"id": 0, "verdict": "unsupported", "score": 0.1}])]
    report = f"Quarterly revenue rose 40 percent year over year. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.UNSUPPORTED
    assert store.get(a.anchor_id).verified == 0
    assert len(fake_llm.calls) == 1  # the paraphrase paid for exactly one batched judge call


def test_keyless_exact_quote_claim_skips_the_judge_no_token_cost(fake_llm):
    # A byte-identity-exact claim (claim ≈ quote) must SKIP the judge entirely:
    # no token cost regression vs the old no-op path.
    body = "Latency dropped to 12.4 ms under load in the benchmark run."
    quote = "Latency dropped to 12.4 ms under load"
    a = ClaimAnchor("nA", 0, len(quote), "Latency fell to 12.4 ms.", quote)
    store = _store_with([a])
    nli = HostJudgeNLI(fake_llm)
    report = f"Latency dropped to 12.4 ms under load. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.SUPPORTED
    assert store.get(a.anchor_id).verified == 1
    assert len(fake_llm.calls) == 0  # exact-quote claim never escalates to the judge


def test_host_judge_batches_all_paraphrase_pairs_into_one_call(fake_llm):
    # Two paraphrase claims → ONE batched judge call (not one per claim).
    body1 = "The committee met in Geneva to discuss trade policy frameworks."
    q1 = "The committee met in Geneva to discuss trade policy frameworks"
    body2 = "Rainfall in the valley peaked during the monsoon months."
    q2 = "Rainfall in the valley peaked during the monsoon months"
    a1 = ClaimAnchor("n1", 0, len(q1), "GDP grew 5%.", q1)
    a2 = ClaimAnchor("n2", 0, len(q2), "Exports fell 3%.", q2)
    store = _store_with([a1, a2])
    nli = HostJudgeNLI(fake_llm)
    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "unsupported", "score": 0.1},
        {"id": 1, "verdict": "unsupported", "score": 0.1},
    ])]
    report = (
        f"National GDP expanded 5 percent over the year. [[{a1.anchor_id}]]\n"
        f"Total exports declined by 3 percent. [[{a2.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"n1": body1, "n2": body2})
    verdicts = {f.anchor_id: f.verdict for f in result.findings}
    assert verdicts[a1.anchor_id] is VerifyVerdict.UNSUPPORTED
    assert verdicts[a2.anchor_id] is VerifyVerdict.UNSUPPORTED
    assert len(fake_llm.calls) == 1  # both paraphrases share ONE batched judge call


# ── default_nli() wiring ─────────────────────────────────────────────────────

def test_default_nli_keyless_with_host_judge_is_host_judge(monkeypatch, fake_llm):
    # Keyless ([local] absent) AND a host judge available → HostJudgeNLI, not the no-op.
    import bad_research.grounding.verifier as verifier_mod

    monkeypatch.setattr(verifier_mod, "nli_available", lambda: False)
    nli = default_nli(llm=fake_llm)
    assert isinstance(nli, HostJudgeNLI)


def test_default_nli_keyless_no_host_judge_falls_back_to_citation_present(monkeypatch):
    # Keyless AND no host judge (llm=None) → the absolute fallback is the no-op.
    import bad_research.grounding.verifier as verifier_mod

    monkeypatch.setattr(verifier_mod, "nli_available", lambda: False)
    nli = default_nli(llm=None)
    assert isinstance(nli, CitationPresentNLI)
    assert not isinstance(nli, HostJudgeNLI)


def test_default_nli_local_present_is_crossencoder_unchanged(monkeypatch, fake_llm):
    # [local] present → the real cross-encoder, REGARDLESS of a host judge (the
    # [local] lane is unchanged by E9).
    import bad_research.grounding.verifier as verifier_mod
    from bad_research.grounding.nli import CrossEncoderNLI

    monkeypatch.setattr(verifier_mod, "nli_available", lambda: True)
    nli = default_nli(llm=fake_llm)
    assert isinstance(nli, CrossEncoderNLI)
