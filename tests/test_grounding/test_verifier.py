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


import json

from bad_research.grounding.verifier import JUDGE_BATCH_SIZE, tier_c_judge


def test_tier_c_judge_parses_batched_json(fake_llm):
    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "supported", "score": 0.9, "reason": "exact"},
        {"id": 1, "verdict": "unsupported", "score": 0.2, "reason": "scope add"},
    ])]
    pairs = [
        ("SEA GMV grew 12.4%.", "a 12.4% YoY expansion"),
        ("Vietnam led at 64%.", "Vietnam was mentioned"),
    ]
    results = tier_c_judge(pairs, fake_llm)
    assert results[0] == (VerifyVerdict.SUPPORTED, 0.9)
    assert results[1] == (VerifyVerdict.UNSUPPORTED, 0.2)
    # Used exactly one batched triage call for the two pairs.
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["tier"] == "triage"


def test_tier_c_batches_in_chunks_of_20(fake_llm):
    # 25 pairs -> 2 calls (20 + 5). Script enough empty arrays to satisfy parse.
    fake_llm.script = [
        json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(20)]),
        json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(5)]),
    ]
    pairs = [(f"claim {i}", f"quote {i}") for i in range(25)]
    results = tier_c_judge(pairs, fake_llm)
    assert len(results) == 25
    assert len(fake_llm.calls) == 2
    assert JUDGE_BATCH_SIZE == 20


from bad_research.grounding.anchors import AnchorStore
from bad_research.grounding.verifier import CitationVerifier


class StubNLI:
    """Deterministic NLI: maps a quote substring -> fixed softmax."""

    def __init__(self, table):
        self.table = table  # dict[str, dict[str,float]]

    def predict(self, premise, hypothesis):
        for key, scores in self.table.items():
            if key in premise:
                return scores
        return {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}


def _store_with(anchors):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_verify_entailed_claim_supported_non_entailed_unsupported(fake_llm):
    body_a = "Latency dropped to 12.4 ms under load."
    body_b = "The author also enjoys hiking on weekends."
    qa = "Latency dropped to 12.4 ms under load"
    qb = "The author also enjoys hiking on weekends"
    aa = ClaimAnchor("nA", 0, len(qa), "Latency fell to 12.4 ms.", qa)
    ab = ClaimAnchor("nB", 0, len(qb), "Latency fell to 5 ms.", qb)
    store = _store_with([aa, ab])
    nli = StubNLI({
        qa: {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01},
        qb: {"entailment": 0.02, "neutral": 0.05, "contradiction": 0.93},
    })
    report = (
        f"Latency fell to 12.4 ms. [[{aa.anchor_id}]]\n"
        f"Latency fell to 5 ms. [[{ab.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body_a, "nB": body_b})
    by_anchor = {r.anchor_id: r for r in result.findings}
    assert by_anchor[aa.anchor_id].verdict is VerifyVerdict.SUPPORTED
    assert by_anchor[ab.anchor_id].verdict is VerifyVerdict.CONTRADICTED
    # Disposition persisted: supported anchor flagged verified=1.
    assert store.get(aa.anchor_id).verified == 1
    assert store.get(ab.anchor_id).verified == 0


def test_verify_fabricated_quote_tier_a_fails_unsupported(fake_llm):
    # Offsets point at body text that is NOT the quote -> Tier A fails -> unsupported.
    body = "No latency regression was observed in any trial."
    fabricated = "Latency dropped to 12.4 ms under load"
    a = ClaimAnchor("nA", 0, 30, "Latency fell.", fabricated)
    store = _store_with([a])
    nli = StubNLI({})  # never consulted -- Tier A short-circuits
    report = f"Latency fell. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.UNSUPPORTED
    assert len(fake_llm.calls) == 0  # no LLM spent on a fabricated quote


def test_verify_neutral_band_escalates_to_tier_c(fake_llm):
    import json
    body = "Adoption grew over the period across several markets."
    quote = "Adoption grew over the period across several markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption grew 12.4% in SEA.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})  # neutral
    fake_llm.script = [json.dumps([{"id": 0, "verdict": "partial", "score": 0.5}])]
    report = f"Adoption grew 12.4% in SEA. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.PARTIAL
    assert len(fake_llm.calls) == 1  # only the neutral band paid for an LLM call


class HypothesisAwareNLI:
    """NLI stub that decides from the HYPOTHESIS (report sentence), proving the
    verifier checks the sentence as written -- not the stored anchor.claim."""

    def predict(self, premise, hypothesis):
        if "DECLINED" in hypothesis or "fell" in hypothesis:
            return {"entailment": 0.02, "neutral": 0.05, "contradiction": 0.93}
        return {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01}


# ── A-4: NLI auto-on under [local]; citation-present degrade when absent ─────

def test_nli_available_reflects_find_spec():
    import importlib.util

    from bad_research.grounding.verifier import nli_available

    expected = importlib.util.find_spec("sentence_transformers") is not None
    assert nli_available() is expected


def test_default_nli_returns_real_crossencoder_when_local_present(monkeypatch):
    # When [local] is importable, the ship path's default NLI is the real
    # cross-encoder (entailment lane auto-on). We force the available branch.
    import bad_research.grounding.verifier as verifier_mod

    monkeypatch.setattr(verifier_mod, "nli_available", lambda: True)
    from bad_research.grounding.nli import CrossEncoderNLI

    nli = verifier_mod.default_nli()
    assert isinstance(nli, CrossEncoderNLI)


def test_default_nli_is_citation_present_stub_when_local_absent(monkeypatch):
    # With [local] absent, default_nli() must NOT be the cross-encoder; it is a
    # citation-present no-op that treats a byte-identity-passing cite as supported
    # WITHOUT touching torch/sentence-transformers.
    import bad_research.grounding.verifier as verifier_mod
    from bad_research.grounding.nli import CrossEncoderNLI

    monkeypatch.setattr(verifier_mod, "nli_available", lambda: False)
    nli = verifier_mod.default_nli()
    assert not isinstance(nli, CrossEncoderNLI)
    # The no-op marks any premise/hypothesis as entailment (citation present == ok),
    # so the verifier's Tier-B lane reads SUPPORTED for resolved + byte-identity cites.
    scores = nli.predict("any premise", "any hypothesis")
    assert scores["entailment"] >= 0.70


def test_citation_present_degrade_marks_resolved_cite_supported(fake_llm):
    # End-to-end on the degrade path: a byte-identity-passing cited sentence is
    # SUPPORTED via the citation-present stub, with NO LLM call and NO NLI model.
    from bad_research.grounding.verifier import CitationPresentNLI

    body = "Latency dropped to 12.4 ms under load in the benchmark run."
    quote = "Latency dropped to 12.4 ms under load"
    a = ClaimAnchor("nA", 0, len(quote), "Latency fell to 12.4 ms.", quote)
    store = _store_with([a])
    report = f"Latency fell to 12.4 ms. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=CitationPresentNLI(), llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.SUPPORTED
    assert store.get(a.anchor_id).verified == 1
    assert len(fake_llm.calls) == 0  # citation-present never escalates to the judge


def test_keyless_verify_path_imports_no_torch(tmp_path):
    # The degrade path must construct + run WITHOUT importing torch /
    # sentence-transformers (keyless invariant). Run in a subprocess that blocks
    # those imports at the import hook; if any code touches them, this fails.
    import subprocess
    import sys
    import textwrap

    prog = textwrap.dedent(
        """
        import builtins
        _blocked = {"torch", "sentence_transformers", "lancedb", "pyarrow", "FlagEmbedding"}
        _real = builtins.__import__
        def _guard(name, *a, **k):
            if name.split(".")[0] in _blocked:
                raise ImportError("blocked in keyless test: " + name)
            return _real(name, *a, **k)
        builtins.__import__ = _guard

        import sqlite3
        import bad_research.grounding.verifier as V
        from bad_research.grounding.anchors import AnchorStore, ClaimAnchor

        V.nli_available = lambda: False          # force the keyless degrade branch
        nli = V.default_nli()                     # must NOT import torch
        assert "torch" not in __import__("sys").modules
        assert "sentence_transformers" not in __import__("sys").modules

        conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
        store = AnchorStore(conn); store.init_schema()
        body = "Latency dropped to 12.4 ms under load."
        quote = "Latency dropped to 12.4 ms under load"
        a = ClaimAnchor("nA", 0, len(quote), "Latency fell.", quote)
        store.upsert(a)

        class _LLM:
            calls = []
            def complete(self, *a, **k): raise AssertionError("no LLM on keyless path")

        v = V.CitationVerifier(nli=nli, llm=_LLM())
        res = v.verify(f"Latency fell. [[{a.anchor_id}]]\\n", store, {"nA": body})
        assert res.findings[0].verdict.value == "supported"
        assert "torch" not in __import__("sys").modules
        print("OK")
        """
    )
    res = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True)
    assert res.returncode == 0, f"keyless verify path failed:\nSTDOUT={res.stdout}\nSTDERR={res.stderr}"
    assert "OK" in res.stdout


# ── E4: self-consistency vote on the high-effort lane (wired into the verifier) ─

def test_verifier_default_effort_uses_single_batched_judge_not_the_vote(fake_llm):
    # DEFAULT path (effort != high): the neutral band escalates to the SINGLE batched
    # Tier-C judge — exactly one LLM call, NO N-sample vote. Default behaviour unchanged.
    import json
    body = "Adoption grew over the period across several markets."
    quote = "Adoption grew over the period across several markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption grew 12.4% in SEA.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})
    fake_llm.script = [json.dumps([{"id": 0, "verdict": "partial", "score": 0.5}])]
    report = f"Adoption grew 12.4% in SEA. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)  # no effort -> default
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.PARTIAL
    assert len(fake_llm.calls) == 1  # the single batched judge, not 3 samples


def test_verifier_high_effort_routes_neutral_band_through_self_consistency_vote():
    # effort=high: the neutral high-stakes band is decided by an N-sample self-
    # consistency VOTE (universal self-consistency), not the single judge. A 2/3
    # supported tally accepts the claim, and exactly N samples are drawn.
    import json

    from tests.test_quality.test_consistency import ScriptedLLM

    body = "Adoption grew over the period across several markets."
    quote = "Adoption grew over the period across several markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption grew strongly.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})
    # 3 vote samples: 2 supported, 1 unsupported -> majority supported.
    scripted = ScriptedLLM([
        json.dumps({"verdict": "supported", "score": 0.9}),
        json.dumps({"verdict": "supported", "score": 0.85}),
        json.dumps({"verdict": "unsupported", "score": 0.2}),
    ])
    report = f"Adoption grew strongly. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=scripted, effort="high")
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.SUPPORTED
    # N independent samples were drawn — the keyless vote cost (not one batched call).
    assert len(scripted.calls) == 3


def test_verifier_high_effort_outvotes_single_dissenting_sample():
    import json

    from tests.test_quality.test_consistency import ScriptedLLM

    body = "Adoption was mentioned in passing across markets."
    quote = "Adoption was mentioned in passing across markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption surged 64%.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})
    # 1 supported, 2 unsupported -> the dissenting supported is OUTVOTED -> not supported.
    scripted = ScriptedLLM([
        json.dumps({"verdict": "supported", "score": 0.95}),
        json.dumps({"verdict": "unsupported", "score": 0.3}),
        json.dumps({"verdict": "unsupported", "score": 0.25}),
    ])
    report = f"Adoption surged 64%. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=scripted, effort="high")
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is not VerifyVerdict.SUPPORTED
    assert store.get(a.anchor_id).verified == 0


def test_verify_checks_report_sentence_not_stored_claim(fake_llm):
    # The anchor's stored claim is FAITHFUL to the support, but the report
    # SENTENCE that cites it says the opposite. The verifier must judge the
    # sentence as written -> CONTRADICTED (the drift is caught).
    body = "GMV grew 12.4% year over year across the region."
    quote = "GMV grew 12.4% year over year across the region"
    drifted = ClaimAnchor("nA", 0, len(quote), "GMV grew 12.4% YoY.", quote)  # faithful stored claim
    body_b = "Revenue rose by 12.4% over the prior year."
    quote_b = "Revenue rose by 12.4% over the prior year"
    faithful = ClaimAnchor("nB", 0, len(quote_b), "Revenue rose 12.4%.", quote_b)
    store = _store_with([drifted, faithful])
    nli = HypothesisAwareNLI()
    report = (
        # sentence DRIFTS to the opposite of its cited support -> caught
        f"Regional GMV DECLINED that year. [[{drifted.anchor_id}]]\n"
        # sentence stays faithful to its cited support -> supported
        f"Revenue rose by 12.4%. [[{faithful.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body, "nB": body_b})
    by_anchor = {r.anchor_id: r for r in result.findings}
    assert by_anchor[drifted.anchor_id].verdict is VerifyVerdict.CONTRADICTED
    assert by_anchor[faithful.anchor_id].verdict is VerifyVerdict.SUPPORTED
    assert store.get(drifted.anchor_id).verified == 0
    assert store.get(faithful.anchor_id).verified == 1
