import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_route_command_classifies(tmp_path):
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": ["what is X"], "entities": [],
                             "response_format": "short", "time_periods": [],
                             "contradiction_terms": [], "domains": ["tech"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["route"] == "agentic-fast"


def test_route_apply_writes_field(tmp_path):
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": [f"q{i}" for i in range(8)],
                             "entities": [], "response_format": "argumentative",
                             "time_periods": [], "contradiction_terms": ["vs"],
                             "domains": ["a"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--apply", "--json"])
    assert res.exit_code == 0
    assert json.loads(d.read_text())["route"] == "full"


def test_route_apply_idempotent_and_reason_present(tmp_path):
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": ["q1", "q2", "q3", "q4"], "entities": [],
                             "response_format": "structured", "time_periods": [],
                             "contradiction_terms": [], "domains": ["tech"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--apply", "--json"])
    out = json.loads(res.stdout)
    assert out["route"] == "light"
    assert out["applied"] is True
    assert out["reason"]


def test_route_command_emits_query_shape(tmp_path):
    # E12: the route CLI also emits query_shape (fan-out shape) + shape_reason,
    # ORTHOGONAL to the route. A single-entity factual is `straightforward`.
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": ["what is the population of Tokyo"],
                             "entities": ["Tokyo"], "response_format": "short",
                             "time_periods": [], "contradiction_terms": [],
                             "domains": ["geo"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--json"])
    assert res.exit_code == 0
    out = json.loads(res.stdout)
    assert out["query_shape"] == "straightforward"
    assert out["shape_reason"]
    # the route field is still the unchanged agentic-fast classification
    assert out["route"] == "agentic-fast"


def test_route_apply_writes_query_shape_field(tmp_path):
    # a multi-entity survey applies a `breadth_first` shape WITHOUT changing route
    d = tmp_path / "decomp.json"
    d.write_text(json.dumps({"sub_questions": [f"metric {i}" for i in range(8)],
                             "entities": ["Norway", "Sweden", "Denmark"],
                             "response_format": "structured", "modality": "compare",
                             "time_periods": [], "contradiction_terms": [],
                             "domains": ["econ"]}))
    res = runner.invoke(app, ["route", "--decomposition", str(d), "--apply", "--json"])
    assert res.exit_code == 0
    written = json.loads(d.read_text())
    assert written["query_shape"] == "breadth_first"
    # route is whatever it was before E12 (the B-5 survey down-route still holds)
    assert written["route"] == "light"


def test_uncited_gate_command_registered():
    res = runner.invoke(app, ["uncited-gate", "--help"])
    assert res.exit_code == 0


# ── A-3: standalone uncited-gate (no pre-populated vault) ────────────────────

def test_uncited_gate_standalone_with_note_bodies_resolves_cites(tmp_path, monkeypatch):
    # Run OUTSIDE Claude Code: a tmp cwd with NO vault. --note-bodies supplies the
    # universe of valid sources; a fully-cited report ships clean (exit 0).
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    report.write_text(
        "Southeast Asian GMV grew 12.4% in 2024 [1].\n"
        "Vietnam led the region at 64% penetration [[src-vn]].\n",
        encoding="utf-8",
    )
    notes = tmp_path / "notes.json"
    notes.write_text(
        json.dumps({"src-sea": "a 12.4% YoY expansion", "src-vn": "Vietnam at 64%"}),
        encoding="utf-8",
    )
    res = runner.invoke(app, ["uncited-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--vault-tag", "x", "--json"])
    assert res.exit_code == 0, res.stdout + (res.stderr or "")
    assert json.loads(res.stdout)["uncited"] == []


def test_uncited_gate_standalone_flags_uncited_factual_sentence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    # one cited line + one genuinely uncited factual sentence
    report.write_text(
        "Southeast Asian GMV grew 12.4% in 2024 [1].\n"
        "Indonesia reportedly led the region at 71% penetration.\n",
        encoding="utf-8",
    )
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"src-sea": "a 12.4% YoY expansion"}), encoding="utf-8")
    res = runner.invoke(app, ["uncited-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--vault-tag", "x", "--json"])
    assert res.exit_code == 1
    uncited = json.loads(res.stdout)["uncited"]
    assert len(uncited) == 1
    assert "Indonesia" in uncited[0]["sentence"]


def test_uncited_gate_missing_db_is_clean_zero_anchors_not_traceback(tmp_path, monkeypatch):
    # No vault, no --note-bodies: the gate must auto-init the schema and report
    # "0 anchors" (every factual sentence uncited) rather than raising
    # OperationalError: no such table: claim_anchors.
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    report.write_text("A neutral framing sentence with no claims at all.\n", encoding="utf-8")
    res = runner.invoke(app, ["uncited-gate", "--report", str(report),
                              "--vault-tag", "x", "--json"])
    # No traceback (the bug was a crash). A no-claim report ships clean.
    assert res.exception is None, res.exception
    assert res.exit_code == 0
    assert json.loads(res.stdout)["uncited"] == []


def test_all_research_subcommands_registered():
    for cmd in ("route", "funnel-gather", "retrieve", "verify-citations", "uncited-gate"):
        res = runner.invoke(app, [cmd, "--help"])
        assert res.exit_code == 0, cmd
