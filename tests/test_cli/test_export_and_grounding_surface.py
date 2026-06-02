"""CLI tests for `bad export`, `bad grounding-surface`, and `bad grounding-recall`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()

_SOURCES = {
    "solar-note": '---\ntitle: "IEA Renewables 2023"\nsource: "https://iea.org/r"\n---\n\nbody',
    "wind-note": '---\ntitle: "GWEC Wind Report"\nsource: "https://gwec.net/w"\n---\n\nbody',
}

_REPORT = (
    "# Energy Report\n\n"
    "Solar grew 24 percent [[solar-note]].\n"
    "Wind grew 15 percent [[wind-note]].\n"
    "Projections continue [1].\n"
)


def _write(tmp_path) -> tuple[Path, Path]:
    rep = tmp_path / "report.md"
    rep.write_text(_REPORT, encoding="utf-8")
    src = tmp_path / "sources.json"
    src.write_text(json.dumps(_SOURCES), encoding="utf-8")
    return rep, src


# ── bad export ───────────────────────────────────────────────────────────────
def test_export_resolves_references_no_bare_brackets(tmp_path):
    rep, src = _write(tmp_path)
    res = runner.invoke(app, ["export", str(rep), "--sources", str(src), "--json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.stdout)
    assert out["markers"] == 3
    assert out["resolved"] == 3
    assert out["dangling"] == 0
    html = Path(out["html"]).read_text(encoding="utf-8")
    # Body markers became clickable superscript anchors; references resolved.
    assert "[[solar-note]]" not in html
    assert 'href="#ref-1"' in html
    assert "IEA Renewables 2023" in html


def test_export_dangling_marker_disclosed(tmp_path):
    rep = tmp_path / "r.md"
    rep.write_text("# T\n\nClaim [[ghost]].\n", encoding="utf-8")
    src = tmp_path / "s.json"
    src.write_text(json.dumps(_SOURCES), encoding="utf-8")
    res = runner.invoke(app, ["export", str(rep), "--sources", str(src), "--json"])
    assert res.exit_code == 0
    out = json.loads(res.stdout)
    assert out["dangling"] == 1
    assert Path(out["html"]).read_text(encoding="utf-8").count("unresolved citation") == 1


def test_export_pdf_flag(tmp_path):
    import importlib.util

    rep, src = _write(tmp_path)
    res = runner.invoke(app, ["export", str(rep), "--sources", str(src), "--pdf", "--json"])
    assert res.exit_code == 0
    out = json.loads(res.stdout)
    if importlib.util.find_spec("fitz") is not None:
        assert out["pdf"] is not None
        assert Path(out["pdf"]).read_bytes()[:4] == b"%PDF"
    else:
        assert out["pdf"] is None  # HTML-only degrade, no new dep


# ── bad grounding-surface ──────────────────────────────────────────────────────
def _seed_vault(tmp_path) -> Path:
    """A minimal vault: a notes dir + a seeded anchors.db, so the verifier produces
    a finding. Returns the vault root."""
    from bad_research.grounding.anchors import AnchorStore, build_from_claims

    root = tmp_path / "vault"
    (root / ".hyperresearch").mkdir(parents=True)
    notes = root / "research" / "notes"
    notes.mkdir(parents=True)
    body = "Global solar capacity grew 24 percent in 2023."
    note_raw = '---\ntitle: "IEA"\nsource: "https://iea.org"\n---\n\n' + body
    (notes / "solar-note.md").write_text(note_raw, encoding="utf-8")

    dbdir = root / ".bad-research"
    dbdir.mkdir()
    conn = sqlite3.connect(str(dbdir / "anchors.db"))
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    build_from_claims(
        store,
        [{"claim": "solar grew 24 percent",
          "quoted_support": "Global solar capacity grew 24 percent in 2023.",
          "source_note_id": "solar-note"}],
        {"solar-note": note_raw},
    )
    anchor_id = next(iter(store.all())).anchor_id
    conn.close()
    rep = root / "research" / "report.md"
    rep.write_text(
        f"# Solar\n\nGlobal solar capacity grew 24 percent in 2023 [[{anchor_id}]].\n",
        encoding="utf-8",
    )
    return root


def test_grounding_surface_emits_per_claim_ledger(tmp_path, monkeypatch):
    root = _seed_vault(tmp_path)
    monkeypatch.chdir(root)
    rep = root / "research" / "report.md"
    res = runner.invoke(app, ["grounding-surface", "--report", str(rep), "--json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.stdout)
    assert out["n_claims"] == 1
    finding = out["ledger"][0]
    assert finding["verdict"] == "supported"
    assert finding["confidence_band"] in ("high", "medium", "low")


def test_grounding_surface_markdown_table(tmp_path, monkeypatch):
    root = _seed_vault(tmp_path)
    monkeypatch.chdir(root)
    rep = root / "research" / "report.md"
    res = runner.invoke(app, ["grounding-surface", "--report", str(rep)])
    assert res.exit_code == 0
    assert "## Grounding ledger" in res.stdout
    assert "| Verdict | Band | Score | Host-judged | Claim |" in res.stdout
    assert "supported" in res.stdout


def test_grounding_surface_empty_when_no_cites(tmp_path, monkeypatch):
    root = tmp_path / "v"
    (root / ".hyperresearch").mkdir(parents=True)
    (root / "research").mkdir()
    monkeypatch.chdir(root)
    rep = root / "research" / "r.md"
    rep.write_text("# T\n\nNo citations here at all in this prose.\n", encoding="utf-8")
    res = runner.invoke(app, ["grounding-surface", "--report", str(rep)])
    assert res.exit_code == 0
    assert "No cited claims" in res.stdout


# ── bad grounding-recall ────────────────────────────────────────────────────────
def test_grounding_recall_prints_per_mutation_rates_and_passes():
    res = runner.invoke(app, ["grounding-recall", "--json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.stdout)
    assert out["regression_pass"] is True
    assert out["deterministic_catch_rate"] == 1.0
    rows = {r["mutation"]: r for r in out["per_mutation"]}
    assert rows["number_flip"]["affirmed_catch_rate"] == 1.0
    assert rows["negation_flip"]["affirmed_catch_rate"] == 1.0
    assert rows["antonym_flip"]["affirmed_catch_rate"] == 1.0
    assert rows["unsupported_append"]["affirmed_catch_rate"] == 1.0
    # The disclosed uncaught band.
    assert rows["paraphrase_contradiction"]["affirmed_catch_rate"] == 0.0
    assert "DISCLOSED UNCAUGHT BAND" in out["disclosure"]


def test_grounding_recall_text_mentions_disclosure():
    res = runner.invoke(app, ["grounding-recall"])
    assert res.exit_code == 0
    assert "paraphrase_contradiction" in res.stdout
    assert "PASS" in res.stdout


def test_grounding_recall_custom_floor_can_fail():
    # An impossible floor (1.01) forces a non-zero exit even though guards are fine.
    res = runner.invoke(app, ["grounding-recall", "--floor", "1.01"])
    assert res.exit_code == 1
