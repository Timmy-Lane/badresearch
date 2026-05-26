"""KR-6 — CLI surface for the grader + recitation gate, and the keyless rewire."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import bad_research.cli.research as RESEARCH
from bad_research.cli import app

runner = CliRunner()


def test_recitation_gate_clean_report_exits_zero(tmp_path: Path):
    report = tmp_path / "r.md"
    report.write_text("# Q\n\nA short paraphrase of the finding here [1].\n", encoding="utf-8")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"n1": "Entirely different wording about the topic at hand."}),
                     encoding="utf-8")
    res = runner.invoke(app, ["recitation-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["recitation"] == []


def test_recitation_gate_flags_verbatim_copy(tmp_path: Path):
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = tmp_path / "r.md"
    report.write_text(f"# Q\n\n{src} [1].\n", encoding="utf-8")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"n1": src}), encoding="utf-8")
    res = runner.invoke(app, ["recitation-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--json"])
    # recitation is a MAJOR finding, not a ship-block: exit 0, but flagged.
    assert res.exit_code == 0
    out = json.loads(res.stdout)
    assert len(out["recitation"]) == 1
    assert out["recitation"][0]["failure_mode"] == "recitation"


# ── the keyless rewire (Task 7) ──────────────────────────────────────────────


def test_build_providers_returns_keyless_providers():
    cfg = type("C", (), {"searxng_endpoint": "", "effort": "medium"})()
    provs = RESEARCH._build_providers(cfg)
    names = {getattr(p, "name", "") for p in provs}
    # the keyless default: the host WebSearch tool adapter + the ddgs lib.
    assert "websearch" in names
    assert "ddgs" in names
    # every provider is keyless: cost_per_search 0.0, no api key attr set true
    for p in provs:
        assert getattr(p, "cost_per_search", 0.0) == 0.0


def test_build_reranker_default_is_claude_code():
    cfg = type("C", (), {"reranker": "host"})()
    r = RESEARCH._build_reranker(cfg)
    assert type(r).__name__ == "ClaudeCodeReranker"


def test_build_embedder_is_none_by_default():
    cfg = type("C", (), {"reranker": "host", "neural_recall": False})()
    assert RESEARCH._build_embedder(cfg) is None


def test_build_tiered_fetcher_uses_agent_browser_ladder():
    cfg = type("C", (), {"browse_engine": "lightpanda"})()
    f = RESEARCH._build_tiered_fetcher(cfg)
    # the keyless 4-rung TieredFetcher (no Browserbase/Browser-Use rungs).
    assert f is not None
    assert hasattr(f, "fetch_tiered")


def test_no_removed_provider_imports_in_research_module():
    # the rewired module must not pull in any paid-provider seam, even lazily.
    src = inspect.getsource(RESEARCH)
    banned = ["cohere", "tavily", "exa_provider", "firecrawl", "sonar_provider",
              "browse_browserbase", "browse_browseruse", "extract_agentql",
              "extract_stagehand", "cascade", 'get_provider("builtin")',
              'get_embed_provider("cohere"']
    for token in banned:
        assert token not in src, f"removed-provider reference survives: {token}"


def test_funnel_gather_cmd_has_max_tokens_and_reasoning_effort():
    sig = inspect.signature(RESEARCH.funnel_gather_cmd)
    assert "reasoning_effort" in sig.parameters
    assert "max_tokens" in sig.parameters
