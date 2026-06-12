"""Tests for the 6 vault lifecycle / corpus-inspection CLI commands.

Covers init, vault-tag, archive-run, search (data.results envelope, filters,
--include-body), lint (4 rules, exit-code on error severity), and note show
(single + multi-id, data.notes envelope). All offline, tmp_path vaults.
"""

import json

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


# ── fixtures / helpers ────────────────────────────────────────────────────────

def _init_vault(tmp_path):
    """Create a fresh vault at tmp_path; return the research/notes dir."""
    res = runner.invoke(app, ["init", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.stdout
    return tmp_path / "research" / "notes"


def _write_note(notes_dir, *, note_id, title, tags, note_type="note",
                source=None, body="Some body text."):
    fm = [
        "---",
        f"title: {title}",
        f"id: {note_id}",
        f"tags: [{', '.join(tags)}]",
        f"type: {note_type}",
        "status: draft",
    ]
    if source:
        fm.append(f"source: {source}")
    fm += ["---", "", f"# {title}", "", body, ""]
    (notes_dir / f"{note_id}.md").write_text("\n".join(fm), encoding="utf-8")


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_creates_vault_and_json_shape(tmp_path):
    res = runner.invoke(app, ["init", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert set(out["data"]) >= {"vault_root", "research_dir", "db"}
    assert (tmp_path / ".hyperresearch").is_dir()
    assert (tmp_path / "research" / "notes").is_dir()


def test_init_twice_fails_cleanly(tmp_path):
    runner.invoke(app, ["init", str(tmp_path), "--json"])
    res = runner.invoke(app, ["init", str(tmp_path), "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["ok"] is False
    assert out["error_code"] == "VAULT_EXISTS"


def test_init_human_output(tmp_path):
    res = runner.invoke(app, ["init", str(tmp_path)])
    assert res.exit_code == 0
    assert "vault_root" in res.stdout


# ── vault-tag ───────────────────────────────────────────────────────────────

def test_vault_tag_returns_field_with_suffix(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["vault-tag", "efield-dft-sac", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    vt = out["data"]["vault_tag"]
    assert vt.startswith("efield-dft-sac-")
    suffix = out["data"]["suffix"]
    assert len(suffix) == 6
    assert vt == f"efield-dft-sac-{suffix}"


def test_vault_tag_avoids_existing_query_file(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    # First mint, then materialise the query file so the suffix is "taken".
    first = json.loads(
        runner.invoke(app, ["vault-tag", "topic", "--json"]).stdout
    )["data"]["vault_tag"]
    (tmp_path / "research" / f"query-{first}.md").write_text("x", encoding="utf-8")
    # A second mint must not collide with the taken tag.
    second = json.loads(
        runner.invoke(app, ["vault-tag", "topic", "--json"]).stdout
    )["data"]["vault_tag"]
    assert second != first


# ── archive-run ───────────────────────────────────────────────────────────────

def test_archive_run_noops_on_fresh_vault(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["archive-run", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["archived"] is False
    assert out["data"]["moved_files"] == []


def test_archive_run_moves_scratch_files(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    research = tmp_path / "research"
    (research / "scaffold.md").write_text("scaffold", encoding="utf-8")
    (research / "loci.json").write_text("[]", encoding="utf-8")
    (research / "critic-findings-a.json").write_text("{}", encoding="utf-8")
    (research / "temp" / "scratch.md").write_text("tmp", encoding="utf-8")
    res = runner.invoke(app, ["archive-run", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["archived"] is True
    moved = set(out["data"]["moved_files"])
    assert {"scaffold.md", "loci.json", "critic-findings-a.json", "temp/"} <= moved
    # Originals are gone; temp dir was re-created empty.
    assert not (research / "scaffold.md").exists()
    assert (research / "temp").is_dir()
    assert (research / "runs").is_dir()
    archive_dir = out["data"]["archive_dir"]
    assert archive_dir and (research / "scaffold.md").parent == research


# ── search ────────────────────────────────────────────────────────────────────

def test_search_empty_vault_returns_empty_results(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["search", "", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["results"] == []
    assert out["data"]["count"] == 0


def test_search_data_results_envelope(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["mytag"],
                source="https://example.com/a")
    _write_note(notes, note_id="src-b", title="Beta", tags=["other"])
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["search", "", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    # canonical envelope: data.results (NOT a flat notes/count)
    results = out["data"]["results"]
    assert out["data"]["count"] == 2
    ids = {r["id"] for r in results}
    assert ids == {"src-a", "src-b"}
    a = next(r for r in results if r["id"] == "src-a")
    assert a["url"] == "https://example.com/a"
    # body excluded unless --include-body
    assert "body" not in a


def test_search_tag_filter(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["mytag"])
    _write_note(notes, note_id="src-b", title="Beta", tags=["other"])
    monkeypatch.chdir(tmp_path)
    out = json.loads(
        runner.invoke(app, ["search", "", "--tag", "mytag", "--json"]).stdout
    )
    assert [r["id"] for r in out["data"]["results"]] == ["src-a"]


def test_search_type_filter(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"], note_type="interim")
    _write_note(notes, note_id="src-b", title="Beta", tags=["t"], note_type="note")
    monkeypatch.chdir(tmp_path)
    out = json.loads(
        runner.invoke(app, ["search", "", "--type", "interim", "--json"]).stdout
    )
    assert [r["id"] for r in out["data"]["results"]] == ["src-a"]
    assert out["data"]["results"][0]["type"] == "interim"


def test_search_include_body(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"],
                body="Perovskite tandem cells reached 33.9% efficiency.")
    monkeypatch.chdir(tmp_path)
    out = json.loads(
        runner.invoke(app, ["search", "", "--include-body", "--json"]).stdout
    )
    r = out["data"]["results"][0]
    assert "body" in r
    assert "Perovskite" in r["body"]
    # body is frontmatter-stripped
    assert "title:" not in r["body"]


def test_search_query_scores_body(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"],
                body="quantum computing breakthrough")
    _write_note(notes, note_id="src-b", title="Beta", tags=["t"],
                body="ordinary classical note")
    monkeypatch.chdir(tmp_path)
    out = json.loads(
        runner.invoke(app, ["search", "quantum", "--json"]).stdout
    )
    # the matching note ranks first
    assert out["data"]["results"][0]["id"] == "src-a"


# ── lint ──────────────────────────────────────────────────────────────────────

def test_lint_unknown_rule_exits_nonzero(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "nonsense", "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["error_code"] == "UNKNOWN_RULE"


def test_lint_scaffold_prompt_error_exits_nonzero(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "scaffold-prompt", "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["ok"] is False
    issues = out["data"]["issues"]
    assert any(i["rule"] == "scaffold-prompt" and i["severity"] == "error" for i in issues)


def test_lint_wrapper_report_missing_report_errors(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "wrapper-report", "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert any(i["rule"] == "wrapper-report" for i in out["data"]["issues"])


def test_lint_all_rules_names_present(tmp_path, monkeypatch):
    # On a vault with a clean report present + loci/patch absent (info), all four
    # rule names appear in rules_run and no error fires → exit 0.
    notes = _init_vault(tmp_path)
    (tmp_path / "research" / "scaffold.md").write_text(
        "## User Prompt\n\nResearch the thing.\n", encoding="utf-8"
    )
    (notes / "final_report_topic-abc123.md").write_text(
        "# Report\n\nA claim with a citation [1].\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert out["data"]["rules_run"] == [
        "wrapper-report", "locus-coverage", "scaffold-prompt", "patch-surgery",
    ]


def test_lint_locus_coverage_flags_missing_locus(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    research = tmp_path / "research"
    (research / "scaffold.md").write_text(
        "## User Prompt\n\nResearch.\n", encoding="utf-8"
    )
    (research / "loci.json").write_text(
        json.dumps([{"id": "locus-uncovered"}]), encoding="utf-8"
    )
    (notes / "final_report_t-1.md").write_text(
        "# Report\n\nNothing about that topic [1].\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "locus-coverage", "--json"])
    # warning, not error → exit 0
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert any("locus-uncovered" in i["message"] for i in out["data"]["issues"])


def test_lint_wrapper_report_accepts_wikilink_citations(tmp_path, monkeypatch):
    # #20(1): the DEFAULT citation_style is "wikilink" ([[note-id]], no Sources
    # section). A report carrying only wikilinks must NOT warn "has no citation
    # markers" — the rule has to recognize [[...]] alongside [N]/[^..]/[Source].
    notes = _init_vault(tmp_path)
    (notes / "final_report_topic-abc123.md").write_text(
        "# Report\n\nVietnam led the region at 64% [[src-vn]].\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "wrapper-report", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert not any(
        i["rule"] == "wrapper-report" and "no citation markers" in i["message"]
        for i in out["data"]["issues"]
    ), out["data"]["issues"]


def test_lint_patch_surgery_accepts_canonical_step14_schema(tmp_path, monkeypatch):
    # #20(2): the step-14 skill mandates the schema
    # {total_findings, applied, skipped, conflicts, orchestrator_escalated} and
    # forbids alternate shapes. A spec-conformant patch-log must NOT warn
    # "lacks 'hunks' or 'patches' key".
    _init_vault(tmp_path)
    (tmp_path / "research" / "patch-log.json").write_text(
        json.dumps({
            "total_findings": 3, "applied": [{"id": "f1"}],
            "skipped": [], "conflicts": [], "orchestrator_escalated": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "patch-surgery", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert not any(
        i["rule"] == "patch-surgery" and "lacks" in i["message"]
        for i in out["data"]["issues"]
    ), out["data"]["issues"]


def test_lint_patch_surgery_invalid_json_errors(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    (tmp_path / "research" / "patch-log.json").write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["lint", "--rule", "patch-surgery", "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert any(i["severity"] == "error" for i in out["data"]["issues"])


# ── note show ─────────────────────────────────────────────────────────────────

def test_note_show_single_id(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"],
                body="Body of alpha.")
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "show", "src-a", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    note_list = out["data"]["notes"]
    assert out["data"]["count"] == 1
    assert note_list[0]["id"] == "src-a"
    assert "Body of alpha." in note_list[0]["body"]


def test_note_show_multiple_ids(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"], body="alpha body")
    _write_note(notes, note_id="src-b", title="Beta", tags=["t"], body="beta body")
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "show", "src-a", "src-b", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["count"] == 2
    ids = [n["id"] for n in out["data"]["notes"]]
    assert ids == ["src-a", "src-b"]
    assert all(n["ok"] for n in out["data"]["notes"])


def test_note_show_missing_id_exits_nonzero(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="src-a", title="Alpha", tags=["t"], body="alpha")
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "show", "src-a", "ghost", "--json"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["error_code"] == "NOTE_NOT_FOUND"
    # the present note is still returned alongside the missing one
    by_id = {n["id"]: n for n in out["data"]["notes"]}
    assert by_id["src-a"]["ok"] is True
    assert by_id["ghost"]["ok"] is False


def test_note_show_finds_note_in_temp_dir(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    temp = tmp_path / "research" / "temp"
    (temp / "interim-1.md").write_text(
        "---\ntitle: Interim\nid: interim-1\ntype: interim\n---\n\n# Interim\nbody\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "show", "interim-1", "--json"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["notes"][0]["id"] == "interim-1"


# ── entry points / registration ───────────────────────────────────────────────

def test_all_vault_commands_registered():
    for cmd in ("init", "vault-tag", "archive-run", "search", "lint", "sync", "tags"):
        res = runner.invoke(app, [cmd, "--help"])
        assert res.exit_code == 0, cmd
    for sub in ("show", "create", "list", "update"):
        assert runner.invoke(app, ["note", sub, "--help"]).exit_code == 0, sub


# ── #11/#16: note create/list/update, sync, tags ──────────────────────────────

def test_note_create_writes_file_and_returns_id(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "create", "--title", "Mamba SSM",
                              "--body", "Mamba achieves linear-time sequence modeling.",
                              "--tag", "ml", "--summary", "Linear-time SSM.", "--json"])
    assert res.exit_code == 0, res.stdout
    data = json.loads(res.stdout)["data"]
    nid = data["note_id"]
    assert (tmp_path / "research" / "notes" / f"{nid}.md").exists()


def test_note_list_returns_notes_and_filters_status(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="n1", title="One", tags=["a"])  # status: draft
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "list", "--json"])
    assert res.exit_code == 0, res.stdout
    data = json.loads(res.stdout)["data"]
    assert any(n["id"] == "n1" for n in data["notes"])
    # status filter matches nothing here
    res2 = runner.invoke(app, ["note", "list", "--status", "evergreen", "--json"])
    assert all(n["status"] == "evergreen" for n in json.loads(res2.stdout)["data"]["notes"])


def test_note_update_sets_summary_tags_status(tmp_path, monkeypatch):
    from bad_research.core.frontmatter import parse_frontmatter

    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="n1", title="One", tags=["a"])
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "update", "n1", "--summary", "A precise summary.",
                              "--add-tag", "b", "--status", "evergreen", "--json"])
    assert res.exit_code == 0, res.stdout
    meta, _ = parse_frontmatter((notes / "n1.md").read_text(encoding="utf-8"))
    assert meta.summary == "A precise summary."
    assert set(meta.tags) >= {"a", "b"}
    assert meta.status == "evergreen"


def test_note_update_missing_id_exits_nonzero(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["note", "update", "nope", "--summary", "x", "--json"])
    assert res.exit_code == 1


def test_sync_indexes_disk_notes_into_db(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="n1", title="One", tags=["a"], body="Body about Mamba.")
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["sync", "--json"])
    assert res.exit_code == 0, res.stdout
    data = json.loads(res.stdout)["data"]
    assert data["added"] + data["updated"] >= 1


def test_tags_returns_vocabulary_with_counts(tmp_path, monkeypatch):
    notes = _init_vault(tmp_path)
    _write_note(notes, note_id="n1", title="One", tags=["ml", "ssm"])
    _write_note(notes, note_id="n2", title="Two", tags=["ml"])
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["tags", "--json"])
    assert res.exit_code == 0, res.stdout
    data = json.loads(res.stdout)["data"]
    by_tag = {t["tag"]: t["count"] for t in data["tags"]}
    assert by_tag.get("ml") == 2
    assert "ssm" in by_tag
