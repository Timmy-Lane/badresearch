"""pipeline.run_query — the headless orchestration entrypoint Plan 09 bridges to.

These tests use a stub cost meter + stub stage functions so the contract
(returns .report/.corpus, populates the cost meter at stage boundaries, threads
the route) is exercised with zero network/LLM/vault dependency.
"""

from __future__ import annotations

import logging

import bad_research.pipeline as P  # noqa: N812
from bad_research.config import BadResearchConfig
from bad_research.pipeline import RunResult, SimpleCostMeter, run_query


def test_simple_cost_meter_records_and_totals():
    m = SimpleCostMeter()
    assert m.total_usd() == 0.0
    m.record(stage="route", tier="triage", search_queries=2)
    m.record(stage="synthesize", tier="heavy", input_tokens=1000, output_tokens=500)
    assert m.total_usd() > 0.0
    d = m.to_dict()
    assert "total_usd" in d and "stages" in d


def test_run_query_returns_report_and_corpus(monkeypatch):
    # Stub the stage seams so no network/LLM/vault is touched.
    monkeypatch.setattr(P, "_route", lambda q, cfg, cm: "fast")
    monkeypatch.setattr(
        P, "_gather", lambda q, mode, cfg, cm: [{"note_id": "n1", "text": "evidence one"}]
    )
    monkeypatch.setattr(
        P, "_retrieve", lambda q, mode, cfg, cm: [{"note_id": "n1", "text": "evidence one"}]
    )
    monkeypatch.setattr(
        P, "_synthesize", lambda q, chunks, route, cfg, cm: "The answer is X [1]."
    )

    cm = SimpleCostMeter()
    res = run_query("what is X", BadResearchConfig(), cm)
    assert isinstance(res, RunResult)
    assert res.report == "The answer is X [1]."
    assert isinstance(res.corpus, list) and res.corpus[0]["note_id"] == "n1"
    assert res.route == "fast"


def test_run_query_populates_cost_meter_at_stage_boundaries(monkeypatch):
    recorded = []

    class RecordingMeter:
        def record(self, **kw):
            recorded.append(kw["stage"])

        def total_usd(self):
            return 0.0

    monkeypatch.setattr(P, "_route", lambda q, cfg, cm: "full")
    monkeypatch.setattr(P, "_gather", lambda q, mode, cfg, cm: [{"note_id": "n1", "text": "e"}])
    monkeypatch.setattr(P, "_retrieve", lambda q, mode, cfg, cm: [{"note_id": "n1", "text": "e"}])
    monkeypatch.setattr(P, "_synthesize", lambda q, chunks, route, cfg, cm: "report [1]")

    cm = RecordingMeter()
    run_query("contested question", BadResearchConfig(), cm)
    # the boundaries the orchestrator must mark
    for stage in ("route", "gather", "retrieve", "synthesize"):
        assert stage in recorded, stage


def test_run_query_default_cost_meter(monkeypatch):
    # run_query mints a SimpleCostMeter when None is passed.
    monkeypatch.setattr(P, "_route", lambda q, cfg, cm: "fast")
    monkeypatch.setattr(P, "_gather", lambda q, mode, cfg, cm: [])
    monkeypatch.setattr(P, "_retrieve", lambda q, mode, cfg, cm: [])
    monkeypatch.setattr(P, "_synthesize", lambda q, chunks, route, cfg, cm: "x")
    res = run_query("q", BadResearchConfig(), None)
    assert res.cost is not None
    assert res.cost.total_usd() >= 0.0


# ── FIX 2: a swallowed wiring crash is LOGGED, never silent ───────────────────


def test_gather_logs_swallowed_wiring_crash_but_still_degrades(monkeypatch, caplog):
    """A wiring break inside the funnel (run_funnel raising) must NOT be silent: the
    exception is logged at WARNING with a traceback, AND _gather still degrades to an
    empty corpus (no crash) so the honest no-evidence report can still be emitted."""
    from bad_research.cli import research as research_mod

    def _boom(query, *, mode, vault_tag):
        raise RuntimeError("seam wiring break: index got a tuple")

    monkeypatch.setattr(research_mod, "run_funnel", _boom)
    with caplog.at_level(logging.WARNING, logger="bad_research.pipeline"):
        out = P._gather("q", "light", BadResearchConfig(), SimpleCostMeter())
    assert out == []                                   # graceful degradation intact
    assert any("gather failed" in r.message for r in caplog.records), \
        "the swallowed wiring crash was not logged — it is silent again"
    # the traceback is attached (exc_info) so the break is diagnosable from logs.
    assert any(r.exc_info for r in caplog.records if "gather failed" in r.message)


def test_retrieve_logs_swallowed_wiring_crash_but_still_degrades(monkeypatch, caplog):
    """Same observability contract for _retrieve: a broken engine build is logged at
    WARNING (with traceback) yet degrades to [] rather than crashing the pipeline."""
    from bad_research.cli import research as research_mod

    def _boom(cfg, vault):
        raise RuntimeError("engine build wiring break")

    monkeypatch.setattr(research_mod, "_build_engine", _boom)
    with caplog.at_level(logging.WARNING, logger="bad_research.pipeline"):
        out = P._retrieve("q", "light", BadResearchConfig(), SimpleCostMeter())
    assert out == []
    assert any("retrieve failed" in r.message for r in caplog.records), \
        "the swallowed retrieve crash was not logged — it is silent again"


def test_genuine_no_providers_still_degrades_to_honest_no_evidence_report(monkeypatch):
    """The degradation MUST survive FIX 2: a real no-providers run (empty funnel,
    empty rerank, no key) still produces the honest no-evidence report, not a crash
    and not a fabrication. Only the LOGGING was added; the behaviour is unchanged."""
    from bad_research.cli import research as research_mod

    # A genuine empty funnel (no providers) → empty envelope, no exception raised.
    monkeypatch.setattr(research_mod, "run_funnel",
                        lambda q, *, mode, vault_tag: {"note_ids": [], "top_chunks": [],
                                                       "n_read": 0})
    # _retrieve finds no vault → its own degradation returns [].
    monkeypatch.setattr(P, "_retrieve", lambda q, mode, cfg, cm: [])

    res = run_query("a question with no sources", BadResearchConfig())
    assert res.corpus == []
    assert "No evidence was gathered" in res.report   # honest gap, never fabricated
