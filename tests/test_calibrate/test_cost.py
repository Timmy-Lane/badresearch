"""5-component cost metering math + cost-report.json shape."""

from __future__ import annotations

import json
from pathlib import Path

from bad_research.calibrate.constants import COST_COMPONENTS
from bad_research.calibrate.cost import CostMeter


def test_components_match_perplexity_five():
    assert COST_COMPONENTS == ("input", "output", "reasoning", "citation", "search_queries")


def test_record_and_total_usd():
    m = CostMeter()
    # 1M input + 1M output tokens at "work" (sonnet 3/15 per Mtok) → $3 + $15 = $18.
    m.record(stage="synthesize", tier="work", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(m.total_usd() - 18.0) < 1e-6


def test_reasoning_priced_as_output():
    m = CostMeter()
    # reasoning tokens bill at the output rate of the tier.
    m.record(stage="draft", tier="heavy", reasoning_tokens=1_000_000)
    assert abs(m.total_usd() - 75.0) < 1e-6  # opus output = $75/Mtok


def test_search_queries_priced_flat():
    m = CostMeter()
    m.record(stage="width-sweep", tier="triage", search_queries=10)
    assert abs(m.total_usd() - 0.05) < 1e-6  # 10 * $0.005


def test_record_response_ingests_usage():
    m = CostMeter()
    m.record_response(
        stage="synthesize",
        tier="work",
        usage={"input_tokens": 1_000_000, "output_tokens": 0},
    )
    assert abs(m.total_usd() - 3.0) < 1e-6


def test_cost_report_shape(tmp_path: Path):
    m = CostMeter()
    m.record(stage="decompose", tier="triage", input_tokens=2000, output_tokens=500)
    m.record(
        stage="synthesize",
        tier="heavy",
        input_tokens=8000,
        output_tokens=4000,
        citation_tokens=300,
        search_queries=12,
    )
    out = tmp_path / "cost-report.json"
    m.write(out)
    data = json.loads(out.read_text())

    assert set(data.keys()) >= {"total_usd", "by_stage", "by_component", "components"}
    assert data["components"] == list(COST_COMPONENTS)
    assert "decompose" in data["by_stage"] and "synthesize" in data["by_stage"]
    # by_component sums every component across stages.
    assert set(data["by_component"].keys()) == set(COST_COMPONENTS)
    assert data["by_stage"]["synthesize"]["search_queries"] == 12
    assert (
        data["total_usd"]
        == data["by_stage"]["decompose"]["usd"] + data["by_stage"]["synthesize"]["usd"]
    )


def test_empty_meter_is_zero():
    m = CostMeter()
    assert m.total_usd() == 0.0
