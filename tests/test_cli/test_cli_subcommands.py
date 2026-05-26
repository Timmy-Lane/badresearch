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
    d.write_text(json.dumps({"sub_questions": ["q%d" % i for i in range(8)],
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


def test_uncited_gate_command_registered():
    res = runner.invoke(app, ["uncited-gate", "--help"])
    assert res.exit_code == 0


def test_all_research_subcommands_registered():
    for cmd in ("route", "funnel-gather", "retrieve", "verify-citations", "uncited-gate"):
        res = runner.invoke(app, [cmd, "--help"])
        assert res.exit_code == 0, cmd
