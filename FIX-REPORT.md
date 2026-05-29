# Fix Report: Wire the 6 Missing CLI Commands

## What Was Missing

The bundled skill (`bad_research/skills/bad-research.md`) references 6 CLI
commands that were **never implemented** in the `bad`/`badr` binary at any
commit in the fork's history.  The vault infrastructure (SQLite, FTS5, note
I/O) existed in Python but was never exposed on the CLI surface, making the
pipeline **non-runnable from the very first step** (`bad init` → VaultError).

| Command | Status before this PR |
|---|---|
| `bad init <path>` | Missing — vault never created |
| `bad vault-tag <slug>` | Missing — run namespace never minted |
| `bad archive-run` | Missing — prior-run artifacts accumulated |
| `bad search "" --tag X --type Y` | Missing — corpus inspection broken |
| `bad lint --rule <name>` | Missing — integrity gate always failed |
| `bad note show <id>` | Missing — full-tier note reading broken |

## What Was Wired vs Written From Scratch

### Wired to existing Python (3 commands)

| Command | Existing module used |
|---|---|
| `bad init` | `core/vault.py::Vault.init()` — fully implemented, just not registered |
| `bad search` | `core/frontmatter.py::parse_frontmatter()` + disk glob over `research/notes/*.md`; empty-query path is a metadata filter (tag/type), non-empty uses term-frequency scoring (keeps smoke test cheap, no LLM/reranker) |
| `bad note show <id>` | `core/note.py::read_note()` — fully implemented, just not registered; wired as a `note` sub-typer group with a `show` subcommand |

### Written from scratch (3 commands)

| Command | Implementation |
|---|---|
| `bad vault-tag <slug>` | Generates `<slug>-<6hex>` via `secrets.token_hex(3)`, checks uniqueness against `research/query-*.md` and `research/notes/final_report_*.md` globs (matching the skill's contract at line 183), retries up to 32 times |
| `bad archive-run` | Moves a fixed set of known scratch file names (scaffold, loci, comparisons, critic-findings-*, patch-log, polish-log, prompt-decomposition, readability-*, grader-log, clarify) + `research/temp/` into `research/runs/archive-<UTC-ts>/`; no-ops cleanly on a fresh vault |
| `bad lint --rule <name>` | 4 deterministic rules (wrapper-report / locus-coverage / scaffold-prompt / patch-surgery) as file-existence + content checks; emits `{ok, rules_run, issues, issue_count}` with per-issue `{severity, rule, message}`; exits non-zero on any `error`-severity finding |

All commands follow the `--json` / `-j` convention established in `cli/research.py`.

## Files Changed

- `src/bad_research/cli/vault_cmds.py` — **new file**, ~290 lines; all 6 commands
- `src/bad_research/cli/__init__.py` — register the 6 new commands + `note_app` sub-typer

## Smoke Test Results

All 6 commands tested in a fresh temp vault (no LLM calls, no paid APIs):

```
bad init . --json
→ {"ok": true, "vault_root": "...", "research_dir": "...", "db": "..."}

bad vault-tag test-slug --json
→ {"vault_tag": "test-slug-cfc15d", "slug": "test-slug", "suffix": "cfc15d"}

bad archive-run --json          # fresh vault, nothing to move
→ {"archived": false, "reason": "nothing to archive", "moved_files": [], "archive_dir": null}

# After seeding research/notes/my-test-note.md with tags: [vault-test]

bad search "" --tag vault-test --json
→ {"notes": [{"id": "my-test-note", ...}], "count": 1, ...}

bad search "climate" --json     # keyword path
→ {"notes": [{"id": "my-test-note", ...}], "count": 1, ...}

bad note show my-test-note --json
→ {"ok": true, "id": "my-test-note", "title": "Test Note", "body": "...", ...}

bad lint --rule scaffold-prompt --json   # no scaffold yet → expected error
→ {"ok": false, "issues": [{"severity": "error", "message": "research/scaffold.md does not exist"}], ...}
exit=1

bad lint --json                 # all 4 rules on fresh vault
→ info-severity for absent-but-optional files (loci.json, patch-log.json)
→ error-severity for required-but-absent files (final_report, scaffold.md)
exit=1 (correct — pipeline hasn't run yet)
```

Vault-tag uniqueness collision handling also verified: seeding a
`research/query-test-slug-aaaaaa.md` caused the next `vault-tag test-slug`
call to generate a different suffix (`ab6022`).
