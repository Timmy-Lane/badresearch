"""Keyless host-judge flow for the head-to-head — emit tasks → host judges → ingest.

The orchestrating model IS the judge (no API key, no provider). These tests cover
the parts that must be reproducible offline and keyless:
  - `emit_judge_tasks` writes one BLINDED task file per entrant + a manifest, and
    blinding strips entrant/tool names BEFORE the task is written (no self-grading);
  - `load_verdicts` ingests host-written `*.verdict.json` rails through the EXISTING
    AxisRails.from_raw → JudgeVerdict.from_rails path and reassembles the harness;
  - `HostJudge` is a true `Judge` drop-in (missing verdict degrades to all-FAIL);
  - the full `bad headtohead --emit-judge-tasks` → hand-written verdicts →
    `--verdicts` CLI round-trip emits a scorecard with NO ANTHROPIC_API_KEY set.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from bad_research.calibrate.headtohead import (
    Entrant,
    HostJudge,
    JudgeVerdict,
    blind_report,
    build_judge_task,
    emit_judge_tasks,
    load_verdicts,
    markers_present,
    run_head_to_head,
)
from bad_research.calibrate.judge import JUDGE_AXES, AxisRails
from bad_research.cli import app

runner = CliRunner()

_ALL = ("factual", "citation", "completeness", "source_quality", "efficiency")


def _entrants():
    return {
        "h2h_01_causal": [
            Entrant(
                name="bad-research",
                report=(
                    "# Exercise and depression\n\n"
                    "Produced by bad-research. A Mendelian-randomization analysis estimates "
                    "~26% lower odds per SD of activity [1].\n"
                ),
                corpus=[{"note_id": "n1", "url": "https://x.edu/a", "text": "MR analysis, 26% lower odds."}],
                cost_usd=0.02,
                latency_s=540,
            ),
            Entrant(
                name="gemini-deep-research",
                report=(
                    "# Exercise and depression\n\n"
                    "Produced by Gemini Deep Research. Many studies show exercise helps; "
                    "most experts agree.\n"
                ),
                cost_usd=0.20,
                latency_s=300,
            ),
        ]
    }


def _qset():
    return [{"id": "h2h_01_causal", "query": "Does aerobic exercise causally reduce depression risk?"}]


# ── emit: blinded task files + manifest ─────────────────────────────────────────
def test_emit_writes_one_task_per_entrant_plus_manifest(tmp_path: Path):
    man = emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    task_files = sorted(p.name for p in tmp_path.glob("*.task.md"))
    assert len(task_files) == 2
    assert (tmp_path / "manifest.json").exists()
    assert len(man["tasks"]) == 2
    assert man["bad_name"] == "bad-research"
    assert man["competitor_name"] == "gemini-deep-research"
    assert man["blinded"] is True


def test_emit_blinds_entrant_and_tool_names_before_writing(tmp_path: Path):
    """The load-bearing anti-self-grading property: the task files the host judges
    from carry NO tool/entrant marker, and neither does the report stored in the
    manifest (blinding happens BEFORE writing, so the result is not self-graded)."""
    emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    for task in tmp_path.glob("*.task.md"):
        assert markers_present(task.read_text(encoding="utf-8")) == [], task.name
    man = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    for t in man["tasks"]:
        # The stored report (what the verdict is ingested against) is blinded too.
        assert markers_present(t["report"]) == []
    # The opaque task ids reveal no entrant identity.
    ids = {t["task_id"] for t in man["tasks"]}
    assert ids == {"h2h_01_causal__entrant-01", "h2h_01_causal__entrant-02"}
    for tid in ids:
        assert "bad" not in tid and "gemini" not in tid


def test_task_file_carries_rubric_axes_and_write_instruction(tmp_path: Path):
    blinded = blind_report("Produced by Gemini. Claim [1].")
    text = build_judge_task("Q?", blinded, [], "h2h_01_causal__entrant-02")
    # Rubric axes + the write-the-verdict instruction are present.
    for axis in JUDGE_AXES:
        assert axis in text
    assert "h2h_01_causal__entrant-02.verdict.json" in text
    assert markers_present(text) == []


# ── ingest: host verdicts through the existing rails path ───────────────────────
def _write_verdict(d: Path, task_id: str, rails: dict[str, str], rationale: str = "host"):
    (d / f"{task_id}.verdict.json").write_text(
        json.dumps({**rails, "rationale": rationale}), encoding="utf-8"
    )


def test_emit_then_verdicts_roundtrip_scorecard(tmp_path: Path):
    emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    # Host hand-writes the rails: bad strong, competitor weak (uncited).
    _write_verdict(tmp_path, "h2h_01_causal__entrant-01", {a: "pass" for a in _ALL})
    _write_verdict(
        tmp_path, "h2h_01_causal__entrant-02",
        {**{a: "borderline" for a in _ALL}, "citation": "fail", "source_quality": "fail"},
    )
    qset, entrants_by_qid, host, bad, comp, blinded = load_verdicts(tmp_path)
    assert bad == "bad-research" and comp == "gemini-deep-research" and blinded is True
    assert isinstance(host, HostJudge)
    card = run_head_to_head(
        qset, entrants_by_qid, bad_name=bad, competitor_name=comp, judge=host, blind=False
    )
    # Host rails flowed through AxisRails.from_raw → JudgeVerdict.from_rails.
    by_name = {s.name: s for s in card.results[0].scores}
    assert by_name["bad-research"].verdict.pass_rate == 1.0
    assert by_name["bad-research"].verdict.passed is True
    assert by_name["gemini-deep-research"].verdict.passed is False
    assert card.results[0].outcome == "win"
    assert card.tally == {"win": 1, "tie": 0, "loss": 0}


def test_verdicts_preserve_rationale_and_cost_metadata(tmp_path: Path):
    emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    _write_verdict(tmp_path, "h2h_01_causal__entrant-01", {a: "pass" for a in _ALL}, "well grounded")
    _write_verdict(tmp_path, "h2h_01_causal__entrant-02", {a: "fail" for a in _ALL}, "no cites")
    qset, entrants_by_qid, host, bad, comp, _ = load_verdicts(tmp_path)
    card = run_head_to_head(
        qset, entrants_by_qid, bad_name=bad, competitor_name=comp, judge=host, blind=False
    )
    by_name = {s.name: s for s in card.results[0].scores}
    assert by_name["bad-research"].verdict.rationale == "well grounded"
    # Operator metadata survives the emit→ingest round-trip.
    assert by_name["bad-research"].cost_usd == 0.02
    assert by_name["bad-research"].latency_s == 540


# ── HostJudge protocol drop-in ──────────────────────────────────────────────────
def test_hostjudge_missing_verdict_degrades_to_all_fail():
    """A position with no host verdict is conservatively all-FAIL — never a crash,
    never a silent pass (the absent-judgment safe default)."""
    host = HostJudge(verdicts=[None])
    v = host.judge("Q?", "some blinded report [1]", [])
    assert v.passed is False
    assert v.pass_rate == 0.0
    assert all(r.value == "fail" for r in v.rails.as_dict().values())
    # Running past the end is also all-FAIL, not an IndexError.
    v2 = host.judge("Q?", "another", [])
    assert v2.passed is False


def test_hostjudge_consumes_verdicts_in_call_order():
    """Two reports that BLIND to identical text still get distinct verdicts because
    the HostJudge is positional, not text-keyed (the collision the design fixes)."""
    strong = JudgeVerdict.from_rails(
        AxisRails.from_raw({a: "pass" for a in _ALL}), rationale="strong"
    )
    weak = JudgeVerdict.from_rails(
        AxisRails.from_raw({a: "fail" for a in _ALL}), rationale="weak"
    )
    host = HostJudge(verdicts=[strong, weak])
    same = "# Heading only\n\n"  # identical blinded text for both calls
    assert host.judge("Q?", same, []).rationale == "strong"
    assert host.judge("Q?", same, []).rationale == "weak"


def test_load_verdicts_missing_file_degrades_not_crashes(tmp_path: Path):
    emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    # Only entrant-01 gets a verdict; entrant-02's verdict file is absent.
    _write_verdict(tmp_path, "h2h_01_causal__entrant-01", {a: "pass" for a in _ALL})
    qset, entrants_by_qid, host, bad, comp, _ = load_verdicts(tmp_path)
    card = run_head_to_head(
        qset, entrants_by_qid, bad_name=bad, competitor_name=comp, judge=host, blind=False
    )
    by_name = {s.name: s for s in card.results[0].scores}
    assert by_name["bad-research"].verdict.passed is True
    assert by_name["gemini-deep-research"].verdict.passed is False  # degraded all-fail


def test_load_verdicts_garbage_rail_coerces_to_fail(tmp_path: Path):
    emit_judge_tasks(
        _qset(), _entrants(), tmp_path,
        bad_name="bad-research", competitor_name="gemini-deep-research",
    )
    # A bogus rail token must coerce to FAIL via AxisRails.from_raw, not crash.
    _write_verdict(
        tmp_path, "h2h_01_causal__entrant-01",
        {**{a: "pass" for a in _ALL}, "factual": "definitely-yes-99"},
    )
    _write_verdict(tmp_path, "h2h_01_causal__entrant-02", {a: "fail" for a in _ALL})
    _, _, host, _, _, _ = load_verdicts(tmp_path)
    # entrant-01's bogus 'factual' token coerced to FAIL via AxisRails.from_raw.
    assert host.verdicts[0] is not None
    assert host.verdicts[0].rails.factual.value == "fail"


def test_load_verdicts_missing_manifest_raises(tmp_path: Path):
    try:
        load_verdicts(tmp_path)
    except FileNotFoundError as exc:
        assert "manifest" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected FileNotFoundError for missing manifest")


# ── CLI keyless round-trip (no ANTHROPIC_API_KEY) ───────────────────────────────
def test_cli_emit_then_verdicts_keyless_roundtrip(tmp_path: Path, monkeypatch):
    """The DoD: emit blinded tasks, hand-write verdicts, ingest → scorecard, all
    with ANTHROPIC_API_KEY UNSET. The scorecard is host-judged (semantic), not the
    RubricJudge proxy."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    starter = (
        Path(__file__).resolve().parents[2]
        / "docs" / "benchmarks" / "queries" / "starter_set.json"
    )
    bad_md = tmp_path / "bad.md"
    comp_md = tmp_path / "comp.md"
    bad_md.write_text(
        "# Exercise\n\nProduced by bad-research. MR analysis: ~26% lower odds [1].\n",
        encoding="utf-8",
    )
    comp_md.write_text(
        "# Exercise\n\nProduced by Gemini Deep Research. Many studies show it helps.\n",
        encoding="utf-8",
    )
    tasks = tmp_path / "tasks"

    # 1) emit
    r1 = runner.invoke(
        app,
        [
            "headtohead",
            "--query-set", str(starter),
            "--query-id", "h2h_01_causal",
            "--bad-report", str(bad_md),
            "--competitor-report", str(comp_md),
            "--bad-name", "bad-research",
            "--competitor-name", "gemini-deep-research",
            "--emit-judge-tasks", str(tasks),
        ],
    )
    assert r1.exit_code == 0, r1.output
    assert (tasks / "manifest.json").exists()
    task_md = sorted(tasks.glob("*.task.md"))
    assert len(task_md) == 2
    # Task files the host reads carry no tool marker.
    for t in task_md:
        assert markers_present(t.read_text(encoding="utf-8")) == []

    # 2) host (this test) hand-writes the verdicts
    _write_verdict(tasks, "h2h_01_causal__entrant-01", {a: "pass" for a in _ALL}, "grounded + cited")
    _write_verdict(
        tasks, "h2h_01_causal__entrant-02",
        {**{a: "borderline" for a in _ALL}, "citation": "fail"}, "no citations",
    )

    # 3) ingest → scorecard
    out = tmp_path / "out"
    r2 = runner.invoke(
        app, ["headtohead", "--verdicts", str(tasks), "--out", str(out), "--json"]
    )
    assert r2.exit_code == 0, r2.output
    assert "ANTHROPIC_API_KEY" not in os.environ
    payload = json.loads(r2.output)
    data = payload["data"]
    assert data["llm_judged"] is True  # host-model semantic judge, not RubricJudge
    assert data["blinded"] is True
    assert data["tally"]["win"] == 1
    assert data["queries"][0]["outcome"] == "win"


def test_cli_verdicts_missing_manifest_clean_exit(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    r = runner.invoke(app, ["headtohead", "--verdicts", str(empty), "--out", str(tmp_path)])
    assert r.exit_code == 2, r.output


def test_imported_judgeverdict_is_the_real_one():
    # HostJudge / JudgeVerdict are re-exported from the harness for convenience but
    # are the SAME objects as in calibrate.judge (no shadow copies).
    from bad_research.calibrate import judge as j

    assert JudgeVerdict is j.JudgeVerdict
    assert HostJudge is j.HostJudge
