"""pipeline.run_query — the headless orchestration entrypoint Plan 09 bridges to.

These tests use a stub cost meter + stub stage functions so the contract
(returns .report/.corpus, populates the cost meter at stage boundaries, threads
the route) is exercised with zero network/LLM/vault dependency.
"""

from __future__ import annotations

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
    monkeypatch.setattr(P, "_route", lambda q, cfg, cm: "agentic-fast")
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
    assert res.route == "agentic-fast"


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
    monkeypatch.setattr(P, "_route", lambda q, cfg, cm: "agentic-fast")
    monkeypatch.setattr(P, "_gather", lambda q, mode, cfg, cm: [])
    monkeypatch.setattr(P, "_retrieve", lambda q, mode, cfg, cm: [])
    monkeypatch.setattr(P, "_synthesize", lambda q, chunks, route, cfg, cm: "x")
    res = run_query("q", BadResearchConfig(), None)
    assert res.cost is not None
    assert res.cost.total_usd() >= 0.0
