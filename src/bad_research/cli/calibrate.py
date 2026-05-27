"""`bad calibrate <query>` — OFFLINE calibration harness (SPEC §14; keyless).

Runs a query through bad-research, judges it on the 5-axis rubric, and writes
calibration-report.{json,md}. Calibration, NOT a per-run gate (SPEC §10 Excluded).

`--offline` forces a deterministic stub runner + StubJudge so the command runs
with ZERO keys and ZERO network — this is the tested path.

The live path drives the KEYLESS `pipeline.run_query` (host WebSearch + ddgs +
crawl4ai + FTS5/BM25 + host-model LLM-rerank — no third-party key) and a single
strong-model LLMJudge. It still reads ANTHROPIC_API_KEY for the HEADLESS model
calls (the only path that needs it; the skill path uses the Claude Code host
model and needs no key). The only baseline is the keyless `hyperresearch` one —
the keyed deep-research baselines (Perplexity/Grok) were removed.
"""

from __future__ import annotations

from pathlib import Path

import typer

from bad_research.cli._output import console, output
from bad_research.models.output import success


def calibrate(
    query: str = typer.Argument(..., help="The research query to calibrate on."),
    out: str = typer.Option(".", "--out", "-o", help="Output dir for the calibration report."),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use a deterministic stub runner + stub judge (no keys, no network).",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output."),
) -> None:
    """Score bad-research vs. baselines on QUERY (offline 5-axis judge)."""
    from bad_research.calibrate import (
        CostMeter,
        StubJudge,
        available_baselines,
        run_calibration,
    )
    from bad_research.calibrate.constants import JUDGE_AXES
    from bad_research.calibrate.harness import BadRunOutput

    out_dir = Path(out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if offline:
        # Deterministic, key-free path: a stub runner + stub judge.
        def _stub_runner(q: str) -> BadRunOutput:
            meter = CostMeter()
            meter.record(
                stage="synthesize",
                tier="heavy",
                input_tokens=8000,
                output_tokens=4000,
                citation_tokens=200,
                search_queries=15,
            )
            return BadRunOutput(
                report=f"# {q}\n\nA grounded claim [1].\n",
                corpus=[{"note_id": "n1", "url": "https://example.edu", "text": "evidence"}],
                cost=meter,
            )

        judge = StubJudge(scores={a: 0.85 for a in JUDGE_AXES})
        report = run_calibration(query, runner=_stub_runner, baselines=[], judge=judge)
    else:
        # Live path: real runner + LLM judge + key-gated baselines.
        from bad_research.calibrate.judge import LLMJudge
        from bad_research.calibrate.runner import default_runner

        try:
            from bad_research.llm.base import get_llm_provider

            provider = get_llm_provider()
        except Exception as exc:
            msg = (
                "calibrate needs an Anthropic provider (set ANTHROPIC_API_KEY) "
                f"or use --offline: {exc}"
            )
            if json_output:
                from bad_research.models.output import error

                output(error(msg, "NO_PROVIDER"), json_mode=True)
            else:
                console.print(f"[red]Error:[/] {msg}")
            raise typer.Exit(1)

        report = run_calibration(
            query,
            runner=default_runner(config=None),
            baselines=available_baselines(),
            judge=LLMJudge(provider=provider),
        )

    json_path = out_dir / "calibration-report.json"
    md_path = out_dir / "calibration-report.md"
    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    if json_output:
        output(success(report.to_dict(), vault=str(out_dir)), json_mode=True)
        return

    v = report.bad.verdict
    console.print(f"[bold]Calibration:[/] {query}")
    console.print(
        f"  bad-research overall: [bold]{v.overall:.3f}[/] "
        f"({'[green]PASS[/]' if v.passed else '[red]FAIL[/]'})  "
        f"cost ${report.bad.cost_usd:.4f}"
    )
    for b in report.baselines:
        console.print(f"  {b.name}: {b.verdict.overall:.3f}  (Δ {report.delta_vs(b.name):+.3f})")
    console.print(f"\n[green]Wrote[/] {json_path}\n[green]Wrote[/] {md_path}")


__all__ = ["calibrate"]
