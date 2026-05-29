"""CLI commands for vault lifecycle and corpus inspection.

Implements the 6 commands the bundled skill depends on but were never wired:
  init          — create a new vault
  vault-tag     — mint a unique <slug>-<6hex> run identifier
  archive-run   — move prior-run scratch files into runs/archive-<tag>-<ts>/
  search        — list/filter notes from vault (by tag / type / query)
  lint          — deterministic file-existence / content checks (4 rules)
  note show     — read a single note by id and emit its body + frontmatter

All commands follow the --json/-j convention established in cli/research.py.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer

from bad_research.cli._output import output


# ── helpers ──────────────────────────────────────────────────────────────────

def _emit(data: dict, *, json_mode: bool) -> None:
    """Emit data as JSON line (json_mode) or a brief human summary."""
    if json_mode:
        print(json.dumps(data, default=str))
    else:
        # Human-readable fallback: just dump key=value pairs
        for k, v in data.items():
            typer.echo(f"{k}: {v}")


def _discover_vault() -> "Vault":  # type: ignore[name-defined]
    from bad_research.core.vault import Vault
    return Vault.discover()


def _parse_note_frontmatter(path: Path) -> dict:
    """Return frontmatter dict for a markdown file, with empty fallback."""
    try:
        from bad_research.core.frontmatter import parse_frontmatter
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        return meta.model_dump(mode="json", exclude_none=True)
    except Exception:
        return {}


# ── init ─────────────────────────────────────────────────────────────────────

def init_cmd(
    path: str = typer.Argument(".", help="Directory to initialise as a vault"),
    name: str = typer.Option("Research Base", "--name", help="Vault display name"),
    research_dir: str = typer.Option("research", "--research-dir"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Initialise a new hyperresearch vault in PATH.

    Creates .hyperresearch/ (config + SQLite DB) and research/ (notes/index/temp).
    No-ops with a clear message when a vault already exists.
    """
    from bad_research.core.vault import Vault, VaultError

    root = Path(path).resolve()
    try:
        vault = Vault.init(root, name=name, research_dir=research_dir)
        data = {
            "ok": True,
            "vault_root": str(vault.root),
            "research_dir": str(vault.research_dir),
            "db": str(vault.db_path),
        }
        _emit(data, json_mode=json_output)
    except VaultError as exc:
        # Already initialized — surface cleanly rather than crashing
        data = {"ok": False, "error": str(exc), "vault_root": str(root)}
        _emit(data, json_mode=json_output)
        raise typer.Exit(code=1)


# ── vault-tag ────────────────────────────────────────────────────────────────

def vault_tag_cmd(
    slug: str = typer.Argument(..., help="Short topical slug, e.g. efield-dft-sac"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Mint a unique vault tag: <slug>-<6hex>.

    The 6-hex suffix is regenerated until it is unique against all
    research/query-*.md and research/notes/final_report_*.md files in the
    current vault, preventing overwrite of any prior run's artifacts.
    """
    vault = _discover_vault()
    research_dir = vault.research_dir

    def _is_taken(tag: str) -> bool:
        # Check query files and final reports for this tag
        for pattern in (
            f"query-{tag}.md",
            f"notes/final_report_{tag}.md",
        ):
            if (research_dir / pattern).exists():
                return True
        return False

    for _ in range(32):  # practically infinite — 16^6 = 16M possibilities
        suffix = secrets.token_hex(3)  # 3 bytes → 6 hex chars
        vault_tag = f"{slug}-{suffix}"
        if not _is_taken(vault_tag):
            break
    else:
        # Astronomically unlikely, but handle it
        typer.echo("ERROR: could not mint a unique vault tag after 32 attempts", err=True)
        raise typer.Exit(code=1)

    data = {"vault_tag": vault_tag, "slug": slug, "suffix": suffix}
    _emit(data, json_mode=json_output)


# ── archive-run ───────────────────────────────────────────────────────────────

# Files/globs in research/ root that belong to a prior run's scratch set
_SCRATCH_NAMES = {
    "scaffold.md",
    "loci.json",
    "comparisons.md",
    "corpus-critic-gaps.json",
    "patch-log.json",
    "polish-log.json",
    "prompt-decomposition.json",
    "readability-recommendations.json",
    "readability-decisions.json",
    "grader-log.json",
    "clarify.json",
}
_SCRATCH_PREFIXES = (
    "critic-findings-",
)


def archive_run_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Archive prior-run scratch files into research/runs/archive-<ts>/.

    Moves scaffold, loci, comparisons, critic-findings, patch-log, polish-log,
    prompt-decomposition, and research/temp/* into a timestamped archive
    directory so the next run starts from a clean slate without losing history.

    Final reports (research/notes/final_report_*.md) and canonical query files
    (research/query-*.md) are already namespaced and are left in place.

    No-ops cleanly on a fresh vault — safe to run unconditionally.
    """
    vault = _discover_vault()
    research_dir = vault.research_dir

    # Collect scratch files from research/ root
    to_move: list[Path] = []
    if research_dir.exists():
        for item in research_dir.iterdir():
            if not item.is_file():
                continue
            if item.name in _SCRATCH_NAMES:
                to_move.append(item)
                continue
            for prefix in _SCRATCH_PREFIXES:
                if item.name.startswith(prefix) and item.suffix == ".json":
                    to_move.append(item)
                    break

    # Collect research/temp/* scratch directory
    temp_dir = vault.temp_dir
    has_temp = temp_dir.exists() and any(temp_dir.iterdir())

    if not to_move and not has_temp:
        data = {
            "archived": False,
            "reason": "nothing to archive",
            "moved_files": [],
            "archive_dir": None,
        }
        _emit(data, json_mode=json_output)
        return

    # Build archive destination
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = research_dir / "runs" / f"archive-{ts}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    moved: list[str] = []
    for src in to_move:
        dst = archive_dir / src.name
        shutil.move(str(src), str(dst))
        moved.append(src.name)

    if has_temp:
        dst_temp = archive_dir / "temp"
        shutil.move(str(temp_dir), str(dst_temp))
        # Re-create empty temp dir so the vault layout stays intact
        temp_dir.mkdir(exist_ok=True)
        moved.append("temp/")

    data = {
        "archived": True,
        "archive_dir": str(archive_dir),
        "moved_files": moved,
    }
    _emit(data, json_mode=json_output)


# ── search ────────────────────────────────────────────────────────────────────

def search_cmd(
    query: str = typer.Argument("", help="Search query (empty = list/filter)"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter to notes tagged with this value"),
    note_type: Optional[str] = typer.Option(None, "--type", help="Filter by note type (e.g. interim)"),
    top_k: int = typer.Option(20, "--top-k", "-k", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Search or list vault notes.

    Empty QUERY with --tag/--type: plain metadata filter (no FTS, no reranker).
    Non-empty QUERY: FTS5 keyword search, optionally filtered by tag/type.

    Returns a JSON array of note summaries: {id, title, type, tags, path, score}.
    """
    vault = _discover_vault()
    notes_dir = vault.notes_dir

    if not notes_dir.exists():
        data: dict = {"notes": [], "count": 0, "query": query, "tag": tag, "type": note_type}
        _emit(data, json_mode=json_output)
        return

    # ── Phase 1: collect candidate note files ──────────────────────────────
    # Always use disk-glob + frontmatter so results match the filesystem
    # without requiring a DB sync step. This is correct for both the empty-
    # query (list) path and as a pre-filter before FTS scoring.
    candidates: list[dict] = []
    for md_path in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(md_path)
        note_id = fm.get("id") or md_path.stem
        note_tags: list[str] = fm.get("tags") or []
        n_type: str = fm.get("type") or "note"

        # Metadata filters
        if tag and tag not in note_tags:
            continue
        if note_type and n_type != note_type:
            continue

        candidates.append({
            "id": note_id,
            "title": fm.get("title") or md_path.stem,
            "type": n_type,
            "tags": note_tags,
            "path": str(md_path),
            "status": fm.get("status") or "draft",
            "_body_path": md_path,
        })

    # ── Phase 2: FTS scoring for non-empty queries ─────────────────────────
    results: list[dict] = []
    if query.strip():
        q_lower = query.lower()
        scored: list[tuple[float, dict]] = []
        for note in candidates:
            try:
                body = note["_body_path"].read_text(encoding="utf-8").lower()
            except Exception:
                body = ""
            # Simple term-frequency score (no LLM, no reranker — keeps smoke test cheap)
            terms = q_lower.split()
            score = sum(body.count(t) for t in terms) / max(len(body), 1)
            scored.append((score, note))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [n for sc, n in scored[:top_k] if sc > 0]
        # If all scores are 0, include them all (query had no hits but we still list)
        if not results:
            results = [n for _sc, n in scored[:top_k]]
    else:
        results = candidates[:top_k]

    # Strip internal helper key
    clean = [{k: v for k, v in n.items() if k != "_body_path"} for n in results]

    data = {"notes": clean, "count": len(clean), "query": query, "tag": tag, "type": note_type}
    _emit(data, json_mode=json_output)


# ── lint ──────────────────────────────────────────────────────────────────────

_LINT_RULES: dict[str, str] = {
    "wrapper-report": (
        "Final report exists and has at least one citation marker ([^…] or [Source …])"
    ),
    "locus-coverage": (
        "research/loci.json exists and every locus id appears in the final report"
    ),
    "scaffold-prompt": (
        "research/scaffold.md exists and contains a non-empty 'User Prompt' section"
    ),
    "patch-surgery": (
        "research/patch-log.json is valid JSON with a 'hunks' or 'patches' key "
        "(or absent on light tier)"
    ),
}

_ALL_RULES = list(_LINT_RULES)


def _lint_wrapper_report(research_dir: Path) -> list[dict]:
    issues: list[dict] = []
    # Find any final_report file
    reports = list((research_dir / "notes").glob("final_report_*.md")) if (research_dir / "notes").exists() else []
    if not reports:
        issues.append({"severity": "error", "rule": "wrapper-report",
                       "message": "No final_report_<vault_tag>.md found in research/notes/"})
        return issues
    # Check for a citation-like marker
    import re
    citation_re = re.compile(r"\[\^[^\]]+\]|\[Source[^\]]*\]|\[\d+\]", re.IGNORECASE)
    for rpt in reports:
        body = rpt.read_text(encoding="utf-8")
        if not citation_re.search(body):
            issues.append({"severity": "warning", "rule": "wrapper-report",
                           "message": f"{rpt.name} has no citation markers"})
    return issues


def _lint_locus_coverage(research_dir: Path) -> list[dict]:
    issues: list[dict] = []
    loci_path = research_dir / "loci.json"
    if not loci_path.exists():
        # Absence is fine on agentic-fast/light (no step 4)
        return [{"severity": "info", "rule": "locus-coverage",
                 "message": "research/loci.json absent (ok for agentic-fast/light tiers)"}]
    try:
        loci = json.loads(loci_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [{"severity": "error", "rule": "locus-coverage",
                 "message": f"research/loci.json is not valid JSON: {exc}"}]

    # Normalise: list of {id:...} or list of strings
    locus_ids: list[str] = []
    for item in (loci if isinstance(loci, list) else loci.get("loci", [])):
        if isinstance(item, dict):
            lid = item.get("id") or item.get("name") or ""
        else:
            lid = str(item)
        if lid:
            locus_ids.append(lid)

    if not locus_ids:
        return issues

    reports = list((research_dir / "notes").glob("final_report_*.md")) if (research_dir / "notes").exists() else []
    if not reports:
        return [{"severity": "error", "rule": "locus-coverage",
                 "message": "No final report to check locus coverage against"}]

    report_body = reports[0].read_text(encoding="utf-8").lower()
    for lid in locus_ids:
        if lid.lower() not in report_body:
            issues.append({"severity": "warning", "rule": "locus-coverage",
                           "message": f"Locus '{lid}' not found in final report"})
    return issues


def _lint_scaffold_prompt(research_dir: Path) -> list[dict]:
    issues: list[dict] = []
    scaffold = research_dir / "scaffold.md"
    if not scaffold.exists():
        issues.append({"severity": "error", "rule": "scaffold-prompt",
                       "message": "research/scaffold.md does not exist"})
        return issues
    body = scaffold.read_text(encoding="utf-8")
    import re
    # Look for a User Prompt section header followed by non-empty content
    match = re.search(r"#+\s*User Prompt\b.*?\n+(.+)", body, re.IGNORECASE | re.DOTALL)
    if not match or not match.group(1).strip():
        issues.append({"severity": "error", "rule": "scaffold-prompt",
                       "message": "scaffold.md exists but 'User Prompt' section is empty or missing"})
    return issues


def _lint_patch_surgery(research_dir: Path) -> list[dict]:
    issues: list[dict] = []
    patch_log = research_dir / "patch-log.json"
    if not patch_log.exists():
        # Absence is acceptable on light/agentic-fast tiers
        return [{"severity": "info", "rule": "patch-surgery",
                 "message": "research/patch-log.json absent (ok for light/agentic-fast tiers)"}]
    try:
        data = json.loads(patch_log.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [{"severity": "error", "rule": "patch-surgery",
                 "message": f"research/patch-log.json is not valid JSON: {exc}"}]
    if not isinstance(data, dict) or not (data.get("hunks") or data.get("patches")):
        issues.append({"severity": "warning", "rule": "patch-surgery",
                       "message": "patch-log.json lacks 'hunks' or 'patches' key"})
    return issues


_RULE_CHECKERS = {
    "wrapper-report": _lint_wrapper_report,
    "locus-coverage": _lint_locus_coverage,
    "scaffold-prompt": _lint_scaffold_prompt,
    "patch-surgery": _lint_patch_surgery,
}


def lint_cmd(
    rule: Optional[str] = typer.Option(None, "--rule", help=(
        "Run a specific rule: wrapper-report | locus-coverage | scaffold-prompt | patch-surgery. "
        "Omit to run all rules."
    )),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Run deterministic lint rules against the current vault's research artifacts.

    Each rule checks for the presence / content of a canonical pipeline artifact.
    Exits non-zero if any rule produces an 'error'-severity issue.
    """
    vault = _discover_vault()
    research_dir = vault.research_dir

    rules_to_run = [rule] if rule else _ALL_RULES
    unknown = [r for r in rules_to_run if r not in _RULE_CHECKERS]
    if unknown:
        typer.echo(f"ERROR: unknown rule(s): {', '.join(unknown)}. "
                   f"Valid: {', '.join(_ALL_RULES)}", err=True)
        raise typer.Exit(code=1)

    all_issues: list[dict] = []
    for r in rules_to_run:
        all_issues.extend(_RULE_CHECKERS[r](research_dir))

    has_error = any(i["severity"] == "error" for i in all_issues)
    data = {
        "ok": not has_error,
        "rules_run": rules_to_run,
        "issues": all_issues,
        "issue_count": len(all_issues),
    }
    _emit(data, json_mode=json_output)
    if has_error:
        raise typer.Exit(code=1)


# ── note (subgroup with 'show' subcommand) ────────────────────────────────────

note_app = typer.Typer(
    name="note",
    help="Note management commands.",
    no_args_is_help=True,
)


@note_app.command("show")
def note_show_cmd(
    note_id: str = typer.Argument(..., help="Note id (stem of the .md file)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON"),
) -> None:
    """Show a vault note by id.

    Reads research/notes/<id>.md (or research/temp/<id>.md as fallback),
    parses frontmatter, and emits {id, title, tags, type, status, body, path}.
    """
    from bad_research.core.note import read_note
    from bad_research.core.vault import VaultError

    try:
        vault = _discover_vault()
    except VaultError as exc:
        data = {"ok": False, "error": str(exc)}
        _emit(data, json_mode=json_output)
        raise typer.Exit(code=1)

    # Search notes_dir first, then temp_dir
    search_dirs = [vault.notes_dir, vault.temp_dir]
    note_path: Path | None = None
    for d in search_dirs:
        candidate = d / f"{note_id}.md"
        if candidate.exists():
            note_path = candidate
            break

    if note_path is None:
        data = {"ok": False, "error": f"Note '{note_id}' not found", "id": note_id}
        _emit(data, json_mode=json_output)
        raise typer.Exit(code=1)

    try:
        note = read_note(note_path, vault.root)
        meta = note.meta.model_dump(mode="json", exclude_none=True)
        data = {
            "ok": True,
            "id": note.meta.id or note_id,
            "title": note.meta.title,
            "tags": note.meta.tags or [],
            "type": note.meta.type,
            "status": note.meta.status,
            "body": note.body,
            "path": note.path,
            "word_count": note.word_count,
            "meta": meta,
        }
    except Exception as exc:
        data = {"ok": False, "error": str(exc), "id": note_id}
        _emit(data, json_mode=json_output)
        raise typer.Exit(code=1)

    _emit(data, json_mode=json_output)
