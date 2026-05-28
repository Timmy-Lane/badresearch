# Workstream A — Line-anchored, support-checked citations

**Date:** 2026-05-29
**Status:** TDD implementation plan — test-first, each task builds on the last.
**Source spec:** `docs/superpowers/specs/2026-05-29-bad-research-super-skill-design.md §2`
**Mechanism detail:** `docs/superpowers/research/round2-citation.md`

**Engineer context:** zero assumed. Every import path, exact signature, and pytest
command is spelled out. Tasks order: schema/extract helpers → anchors DDL →
render token → verifier → gate → MCP tool → skill prose.

---

## Task A-1: `body_to_lines` and `char_span_to_line_range` in grounding/extract.py

**Files:**
- Modify: `src/bad_research/grounding/extract.py` (append after line 62)
- Test: `tests/test_grounding/test_extract.py` (append)

### Step 1: Write the failing test

```python
# Append to tests/test_grounding/test_extract.py

from bad_research.grounding.extract import body_to_lines, char_span_to_line_range


def test_body_to_lines_basic():
    body = "line one\nline two\nline three\n"
    lines = body_to_lines(body)
    # 3 content lines + trailing newline produces 3 (char_start, char_end) pairs
    assert len(lines) == 3
    # first line: chars 0..8  ("line one")
    assert lines[0] == (0, 8)
    # second line: chars 9..17  ("line two")
    assert lines[1] == (9, 17)
    # third line: chars 18..28 ("line three")
    assert lines[2] == (18, 28)


def test_body_to_lines_crlf():
    body = "alpha\r\nbeta\r\n"
    lines = body_to_lines(body)
    assert len(lines) == 2
    # CRLF pair is treated as one line separator; offsets exclude the CR+LF
    assert body[lines[0][0]:lines[0][1]] == "alpha"
    assert body[lines[1][0]:lines[1][1]] == "beta"


def test_body_to_lines_no_trailing_newline():
    body = "first\nsecond"
    lines = body_to_lines(body)
    assert len(lines) == 2
    assert body[lines[0][0]:lines[0][1]] == "first"
    assert body[lines[1][0]:lines[1][1]] == "second"


def test_body_to_lines_empty():
    assert body_to_lines("") == []


def test_char_span_to_line_range_single_line():
    body = "alpha\nbeta\ngamma\n"
    lines = body_to_lines(body)
    # "beta" is entirely on line 2 (1-based)
    start = body.index("beta")
    end = start + len("beta")
    ls, le = char_span_to_line_range(lines, start, end)
    assert ls == 2 and le == 2


def test_char_span_to_line_range_multi_line():
    body = "alpha\nbeta\ngamma\n"
    lines = body_to_lines(body)
    # span from "beta" through "gamma"
    start = body.index("beta")
    end = body.index("gamma") + len("gamma")
    ls, le = char_span_to_line_range(lines, start, end)
    assert ls == 2 and le == 3


def test_char_span_to_line_range_clamps_to_valid():
    body = "only\n"
    lines = body_to_lines(body)
    # span beyond end clamps to last line
    ls, le = char_span_to_line_range(lines, 0, 9999)
    assert ls == 1 and le == len(lines)
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_extract.py::test_body_to_lines_basic -x
```

Expected: `FAIL — ImportError: cannot import name 'body_to_lines' from 'bad_research.grounding.extract'`

### Step 3: Implement

Append to `src/bad_research/grounding/extract.py` after line 62:

```python
def body_to_lines(body: str) -> list[tuple[int, int]]:
    """Return a list of (char_start, char_end) for each line (0-indexed, exclusive end).

    Handles LF, CRLF, and CR line endings. A trailing newline does NOT produce a
    spurious empty final entry. The slice body[char_start:char_end] reproduces
    the line content WITHOUT its line terminator.
    """
    if not body:
        return []
    result: list[tuple[int, int]] = []
    pos = 0
    n = len(body)
    while pos < n:
        # find the next newline (LF), handling CRLF as one unit
        nl = body.find("\n", pos)
        if nl == -1:
            # last line with no trailing newline
            result.append((pos, n))
            break
        # CRLF: the content ends before the CR
        content_end = nl - 1 if nl > pos and body[nl - 1] == "\r" else nl
        result.append((pos, content_end))
        pos = nl + 1
    # If the body ends with a newline the loop adds an empty-range trailing
    # entry — drop it.
    if result and result[-1][0] == result[-1][1]:
        result.pop()
    return result


def char_span_to_line_range(
    body_lines: list[tuple[int, int]],
    char_start: int,
    char_end: int,
) -> tuple[int, int]:
    """Given precomputed body_lines from body_to_lines(), return 1-based
    (line_start, line_end) covering the char span [char_start, char_end).

    O(n) scan; n is number of lines in the note (typically < 500).
    Clamps to [1, len(body_lines)] on out-of-range input.
    """
    if not body_lines:
        return (1, 1)
    n = len(body_lines)
    line_start: int | None = None
    line_end: int | None = None
    for i, (cs, ce) in enumerate(body_lines):
        # A line overlaps the span if its range intersects [char_start, char_end).
        # Use inclusive overlap: the span touches this line if cs < char_end and ce > char_start.
        # Treat char_end == char_start (empty span) as touching the line that contains char_start.
        span_end = char_end if char_end > char_start else char_start + 1
        if cs < span_end and ce > char_start or (cs <= char_start < ce):
            line_no = i + 1  # 1-based
            if line_start is None:
                line_start = line_no
            line_end = line_no
    if line_start is None:
        # span is before or after all lines — clamp
        if char_start >= body_lines[-1][1]:
            return (n, n)
        return (1, 1)
    return (line_start, line_end)  # type: ignore[return-value]
```

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_extract.py -x
```

Expected: `PASSED` (all existing + new tests green)

### Step 5: Commit

```bash
git add src/bad_research/grounding/extract.py tests/test_grounding/test_extract.py \
&& git commit -m "feat(grounding/extract): add body_to_lines + char_span_to_line_range (A-1)"
```

---

## Task A-2: `body_lines TEXT` column on `note_content`; populate in `write_note`; lazy backfill on read

**Files:**
- Modify: `src/bad_research/core/db.py` (SCHEMA_VERSION 9→10; add column to SCHEMA_SQL; add migration)
- Modify: `src/bad_research/core/migrations.py` (add `_migrate_v10_body_lines`)
- Modify: `src/bad_research/core/note.py` (write_note does not touch the DB — the sync layer does; leave write_note unchanged; see note below)
- Test: `tests/test_core/test_db_body_lines.py` (create)

**Note on architecture:** `write_note` writes a file to disk; the DB is populated by
`bad_research.core.sync.execute_sync`, which calls `_upsert_note_content`. The right
place to compute and store `body_lines` is in the sync content-upsert path, not in
`write_note` itself. The lazy-backfill on read is a `note_content` read helper in `db.py`.

### Step 1: Write the failing test

Create `tests/test_core/test_db_body_lines.py`:

```python
from __future__ import annotations

import json
import sqlite3

import pytest

from bad_research.core.db import SCHEMA_VERSION, get_connection, init_schema


@pytest.fixture
def mem_conn():
    """Fresh in-memory DB fully migrated to current SCHEMA_VERSION."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        conn = get_connection(Path(d) / "test.db")
        init_schema(conn)
        yield conn
        conn.close()


def test_schema_version_is_10(mem_conn):
    row = mem_conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    assert int(row[0] if isinstance(row, tuple) else row["value"]) == 10


def test_note_content_has_body_lines_column(mem_conn):
    cols = {row[1] for row in mem_conn.execute("PRAGMA table_info(note_content)")}
    assert "body_lines" in cols


def test_body_lines_column_accepts_null_and_json(mem_conn):
    # Insert a stub note row first (FK required).
    mem_conn.execute(
        "INSERT INTO notes (id, title, path, status, type, created, file_mtime, content_hash, synced_at) "
        "VALUES ('n1', 'T', 'n1.md', 'draft', 'note', '2026-01-01T00:00:00Z', 0.0, 'abc', '2026-01-01T00:00:00Z')"
    )
    # NULL (old note without body_lines)
    mem_conn.execute(
        "INSERT INTO note_content (note_id, body, body_plain, body_lines) VALUES ('n1', 'hello\nworld', 'hello world', NULL)"
    )
    row = mem_conn.execute("SELECT body_lines FROM note_content WHERE note_id = 'n1'").fetchone()
    assert row["body_lines"] is None

    # JSON list of [char_start, char_end] pairs
    lines_json = json.dumps([[0, 5], [6, 11]])
    mem_conn.execute("UPDATE note_content SET body_lines = ? WHERE note_id = 'n1'", (lines_json,))
    row = mem_conn.execute("SELECT body_lines FROM note_content WHERE note_id = 'n1'").fetchone()
    parsed = json.loads(row["body_lines"])
    assert parsed == [[0, 5], [6, 11]]


def test_migration_is_idempotent(mem_conn):
    """Running init_schema twice on a fully-migrated DB must not raise."""
    init_schema(mem_conn)  # second call
    row = mem_conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    assert int(row[0] if isinstance(row, tuple) else row["value"]) == 10
```

### Step 2: Run to verify it fails

```
pytest tests/test_core/test_db_body_lines.py::test_schema_version_is_10 -x
```

Expected: `FAIL — AssertionError: assert 9 == 10`

### Step 3: Implement

**3a. `src/bad_research/core/db.py`** — bump version and add column to SCHEMA_SQL.

Change line 8: `SCHEMA_VERSION = 9` → `SCHEMA_VERSION = 10`

Change the `note_content` table block in SCHEMA_SQL (lines 54-58):
```python
# BEFORE (lines 54-58):
CREATE TABLE IF NOT EXISTS note_content (
    note_id    TEXT PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    body_plain TEXT NOT NULL
);

# AFTER:
CREATE TABLE IF NOT EXISTS note_content (
    note_id    TEXT PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    body_plain TEXT NOT NULL,
    body_lines TEXT          -- JSON: [[char_start, char_end], ...]; NULL for legacy rows
);
```

**3b. `src/bad_research/core/migrations.py`** — add the v10 migration and register it.

Add after `_migrate_v9_drop_embeddings` (after line 173):
```python
def _migrate_v10_body_lines(conn: sqlite3.Connection) -> None:
    """Add body_lines TEXT column to note_content (idempotent).

    Stores JSON [[char_start, char_end], ...] for line-anchored citations (A-1).
    Existing rows get NULL; the sync layer backfills on next write/re-sync.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(note_content)")}
    if "body_lines" not in existing:
        conn.execute("ALTER TABLE note_content ADD COLUMN body_lines TEXT")
    conn.commit()
```

Then in the `MIGRATIONS` dict (line 220 area), add the new entry:
```python
    9: _migrate_v9_drop_embeddings,
    10: _migrate_v10_body_lines,
```

**3c. Lazy backfill helper in `src/bad_research/core/db.py`** — append after `POST_MIGRATE_INDEXES_SQL`:

```python
def get_body_lines(conn: sqlite3.Connection, note_id: str) -> list[tuple[int, int]] | None:
    """Return the pre-computed line index for a note body, or None if not stored.

    Callers that need line numbers should call this first; if None is returned,
    they must compute body_to_lines(body) themselves and may optionally store the
    result via store_body_lines().
    """
    row = conn.execute(
        "SELECT body_lines FROM note_content WHERE note_id = ?", (note_id,)
    ).fetchone()
    if row is None or row["body_lines"] is None:
        return None
    import json
    raw = json.loads(row["body_lines"])
    return [(r[0], r[1]) for r in raw]


def store_body_lines(
    conn: sqlite3.Connection,
    note_id: str,
    body_lines: list[tuple[int, int]],
) -> None:
    """Persist a precomputed body_lines index for a note (lazy backfill path)."""
    import json
    conn.execute(
        "UPDATE note_content SET body_lines = ? WHERE note_id = ?",
        (json.dumps(body_lines), note_id),
    )
    conn.commit()
```

### Step 4: Run to verify pass

```
pytest tests/test_core/test_db_body_lines.py -x
```

Expected: `PASSED` (all 4 new tests)

```
pytest tests/test_grounding/ tests/test_core/ -x
```

Expected: no regressions in existing tests.

### Step 5: Commit

```bash
git add src/bad_research/core/db.py src/bad_research/core/migrations.py \
        tests/test_core/test_db_body_lines.py \
&& git commit -m "feat(core/db): body_lines TEXT column on note_content, SCHEMA_VERSION=10 (A-2)"
```

---

## Task A-3: `line_start` / `line_end` nullable fields on `ClaimAnchor` and DDL

**Files:**
- Modify: `src/bad_research/grounding/anchors.py` (ClaimAnchor dataclass + CLAIM_ANCHORS_DDL + upsert + get + all)
- Modify: `src/bad_research/retrieval/anchors.py` (PROVENANCE_DDL claim_anchors block)
- Test: append to `tests/test_grounding/test_anchors.py`

### Step 1: Write the failing test

```python
# Append to tests/test_grounding/test_anchors.py

from bad_research.grounding.anchors import ClaimAnchor, AnchorStore
import sqlite3


def _store_fresh() -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    return store


def test_claim_anchor_has_line_start_line_end_nullable():
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
    )
    assert a.line_start is None
    assert a.line_end is None


def test_claim_anchor_line_fields_accepted():
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
        line_start=42, line_end=44,
    )
    assert a.line_start == 42
    assert a.line_end == 44


def test_anchor_store_upsert_get_round_trips_line_fields():
    store = _store_fresh()
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="quoted text here",
        line_start=42, line_end=44,
    )
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.line_start == 42
    assert got.line_end == 44


def test_anchor_store_upsert_null_line_fields_round_trips():
    store = _store_fresh()
    a = ClaimAnchor(
        note_id="n1", char_start=10, char_end=50,
        claim="C.", quoted_support="legacy quote no lines",
    )
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.line_start is None
    assert got.line_end is None


def test_claim_anchors_ddl_has_line_columns():
    from bad_research.grounding.anchors import CLAIM_ANCHORS_DDL
    assert "line_start" in CLAIM_ANCHORS_DDL
    assert "line_end" in CLAIM_ANCHORS_DDL
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_anchors.py::test_claim_anchor_has_line_start_line_end_nullable -x
```

Expected: `FAIL — TypeError: ClaimAnchor.__init__() got an unexpected keyword argument 'line_start'` (or AttributeError)

### Step 3: Implement

**`src/bad_research/grounding/anchors.py`**

Change the `ClaimAnchor` dataclass (lines 20-34) to add two new nullable fields:
```python
@dataclass
class ClaimAnchor:
    """One claim->span binding. anchor_id == quote_sha(quoted_support)."""

    note_id: str
    char_start: int
    char_end: int
    claim: str
    quoted_support: str
    verified: int = 0           # 0 = unchecked; 1 = passed the verifier (§2)
    verify_score: float | None = None
    anchor_id: str = field(default="")
    line_start: int | None = None   # 1-based line number of span start (nullable for legacy)
    line_end: int | None = None     # 1-based line number of span end (nullable for legacy)

    def __post_init__(self) -> None:
        if not self.anchor_id:
            self.anchor_id = quote_sha(self.quoted_support)
```

Change `CLAIM_ANCHORS_DDL` (lines 37-49) to add the two columns:
```python
CLAIM_ANCHORS_DDL = """
CREATE TABLE IF NOT EXISTS claim_anchors (
    anchor_id      TEXT PRIMARY KEY,   -- == quote_sha (8-char SHA-256 of quoted_support)
    note_id        TEXT NOT NULL,
    char_start     INTEGER NOT NULL,
    char_end       INTEGER NOT NULL,
    claim          TEXT NOT NULL,
    quoted_support TEXT NOT NULL,
    verified       INTEGER NOT NULL DEFAULT 0,
    verify_score   REAL,
    line_start     INTEGER,            -- 1-based; NULL for legacy anchors
    line_end       INTEGER             -- 1-based; NULL for legacy anchors
);
CREATE INDEX IF NOT EXISTS idx_claim_anchors_note ON claim_anchors(note_id);
"""
```

Change `AnchorStore.upsert` to include the two new columns in the INSERT and UPDATE:
```python
    def upsert(self, anchor: ClaimAnchor) -> None:
        self.conn.execute(
            "INSERT INTO claim_anchors "
            "(anchor_id, note_id, char_start, char_end, claim, quoted_support, "
            " verified, verify_score, line_start, line_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(anchor_id) DO UPDATE SET "
            "  note_id=excluded.note_id, char_start=excluded.char_start, "
            "  char_end=excluded.char_end, claim=excluded.claim, "
            "  quoted_support=excluded.quoted_support, "
            "  line_start=excluded.line_start, line_end=excluded.line_end",
            (
                anchor.anchor_id, anchor.note_id, anchor.char_start, anchor.char_end,
                anchor.claim, anchor.quoted_support, anchor.verified, anchor.verify_score,
                anchor.line_start, anchor.line_end,
            ),
        )
        self.conn.commit()
```

Change `AnchorStore.get` to read the two new columns (in the `ClaimAnchor(...)` constructor call):
```python
    def get(self, anchor_id: str) -> ClaimAnchor | None:
        row = self.conn.execute(
            "SELECT * FROM claim_anchors WHERE anchor_id = ?", (anchor_id,)
        ).fetchone()
        if row is None:
            return None
        return ClaimAnchor(
            note_id=row["note_id"], char_start=row["char_start"], char_end=row["char_end"],
            claim=row["claim"], quoted_support=row["quoted_support"],
            verified=row["verified"], verify_score=row["verify_score"],
            anchor_id=row["anchor_id"],
            line_start=row["line_start"], line_end=row["line_end"],
        )
```

Change `AnchorStore.all` the same way:
```python
    def all(self) -> Iterable[ClaimAnchor]:
        for row in self.conn.execute("SELECT * FROM claim_anchors"):
            yield ClaimAnchor(
                note_id=row["note_id"], char_start=row["char_start"], char_end=row["char_end"],
                claim=row["claim"], quoted_support=row["quoted_support"],
                verified=row["verified"], verify_score=row["verify_score"],
                anchor_id=row["anchor_id"],
                line_start=row["line_start"], line_end=row["line_end"],
            )
```

**`src/bad_research/retrieval/anchors.py`** — update the `claim_anchors` DDL in `PROVENANCE_DDL` (lines 22-33):
```python
CREATE TABLE IF NOT EXISTS claim_anchors (
    anchor_id      TEXT PRIMARY KEY,   -- = quote_sha (8-char)
    note_id        TEXT,
    char_start     INTEGER,
    char_end       INTEGER,
    claim          TEXT,
    quoted_support TEXT,
    verified       INTEGER,
    verify_score   REAL,
    line_start     INTEGER,
    line_end       INTEGER
);
```

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_anchors.py -x
```

Expected: `PASSED` (all anchors tests, including new)

### Step 5: Commit

```bash
git add src/bad_research/grounding/anchors.py src/bad_research/retrieval/anchors.py \
        tests/test_grounding/test_anchors.py \
&& git commit -m "feat(grounding/anchors): add line_start/line_end nullable fields to ClaimAnchor + DDL (A-3)"
```

---

## Task A-4: `[[note-id:L42-L58]]` token parsing in `grounding/render.py`

**Files:**
- Modify: `src/bad_research/grounding/render.py` (extend `extract_citations`; update `_WIKILINK_CITE` and `_CITE_TOKEN` patterns)
- Test: append to `tests/test_grounding/test_render.py`

**Contract:** `extract_citations` must return just the `note-id` part (without the
`:L42-L58` suffix) so that all existing callers that do `store.get(token)` keep
working. The line range is carried inside the token string as a suffix and is
parsed by a separate helper `parse_line_anchor` used only by the verifier.
The coalescer (`coalesce_citations`) uses set-equality on anchor IDs; two tokens
citing the SAME note at DIFFERENT line ranges (`[[n:L1-L5]]` vs `[[n:L8-L12]]`)
produce DISTINCT sets — they are NOT coalesced (desired behavior per round2-citation §5).

### Step 1: Write the failing test

```python
# Append to tests/test_grounding/test_render.py

from bad_research.grounding.render import extract_citations, parse_line_anchor


def test_extract_citations_parses_line_anchored_token():
    sent = "Growth was 12.4% [[source-note-12:L42-L58]]."
    cites = extract_citations(sent)
    # The anchor ID returned is just "source-note-12:L42-L58" — the full token
    # key; line info is stripped by parse_line_anchor, not by extract_citations.
    assert "source-note-12:L42-L58" in cites


def test_extract_citations_still_parses_legacy_bare_wikilink():
    sent = "Vietnam led [[source-note-12]]."
    assert extract_citations(sent) == ["source-note-12"]


def test_extract_citations_still_parses_alias_wikilink():
    sent = "See [[source-note-12|the regional digest]]."
    assert extract_citations(sent) == ["source-note-12"]


def test_extract_citations_mixed_legacy_and_line_anchored():
    sent = "A claim [[note-a:L1-L10]] and another [[note-b]]."
    cites = extract_citations(sent)
    assert "note-a:L1-L10" in cites
    assert "note-b" in cites


def test_parse_line_anchor_with_line_suffix():
    note_id, ls, le = parse_line_anchor("source-note-12:L42-L58")
    assert note_id == "source-note-12"
    assert ls == 42
    assert le == 58


def test_parse_line_anchor_bare_note_id():
    note_id, ls, le = parse_line_anchor("source-note-12")
    assert note_id == "source-note-12"
    assert ls is None
    assert le is None


def test_parse_line_anchor_single_line():
    note_id, ls, le = parse_line_anchor("n:L7-L7")
    assert note_id == "n"
    assert ls == 7 and le == 7


def test_coalesce_does_not_merge_same_note_different_line_ranges():
    # Two sentences citing the same note at DIFFERENT line ranges must NOT coalesce.
    from bad_research.grounding.render import coalesce_citations
    text = (
        "First claim. [[note-a:L1-L5]] "
        "Second claim. [[note-a:L8-L12]]"
    )
    out = coalesce_citations(text)
    # Both tokens survive distinct
    assert "[[note-a:L1-L5]]" in out
    assert "[[note-a:L8-L12]]" in out
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_render.py::test_extract_citations_parses_line_anchored_token -x
```

Expected: `FAIL — AssertionError` (current regex strips `:L42-L58` as an alias-like suffix, so the returned token would be `source-note-12` not `source-note-12:L42-L58`; also `parse_line_anchor` does not exist yet)

### Step 3: Implement

**`src/bad_research/grounding/render.py`**

Replace the existing `extract_citations` function and add `parse_line_anchor` after it:

```python
_LINE_ANCHOR_RE = re.compile(r":L(\d+)-L(\d+)$")


def extract_citations(sentence: str) -> list[str]:
    """Return the citation tokens in/adjacent to a sentence.

    Returns numeric [N] indices (as strings) and [[note-id]] / [[note-id:L42-L58]]
    wiki-link targets. For wikilinks with a display alias (`[[id|alias]]`) the
    alias is stripped. For line-anchored tokens (`[[id:L42-L58]]`) the full
    `id:L42-L58` key is returned — use parse_line_anchor() to split them.
    Legacy bare `[[note-id]]` tokens are unchanged.
    """
    out: list[str] = []
    # Updated pattern: the (?:\|[^\]]*) alias branch now only matches a pipe,
    # not a colon-prefixed line spec. The colon-line spec is part of the note-id
    # group so it's preserved verbatim in group(2).
    for m in re.finditer(r"\[(\d+)\]|\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", sentence):
        if m.group(1) is not None:
            out.append(m.group(1))
        else:
            out.append(m.group(2).strip())
    return out


def parse_line_anchor(token: str) -> tuple[str, int | None, int | None]:
    """Split a citation token into (note_id, line_start, line_end).

    For a line-anchored token like "source-note-12:L42-L58" returns
    ("source-note-12", 42, 58). For a bare note-id returns (token, None, None).
    """
    m = _LINE_ANCHOR_RE.search(token)
    if m:
        note_id = token[:m.start()]
        return (note_id, int(m.group(1)), int(m.group(2)))
    return (token, None, None)
```

Also update the module-level `_WIKILINK_CITE` and `_CITE_TOKEN` compiled patterns so they
cover the line-anchored form (these are used by the coalescer). Replace lines 10-11:

```python
_NUMERIC_CITE = re.compile(r"\[(\d+)\]")
# Updated: the wikilink body may contain a colon-line-spec (e.g. :L42-L58); it
# is captured as part of the note-id group, not treated as an alias separator.
_WIKILINK_CITE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
```

Replace `_CITE_TOKEN` (line 37) and `_CITE_TAIL` (line 40) and `_UNIT` (lines 46-51) with
versions that keep line-anchored tokens as single tokens:

```python
# A citation TOKEN is either a numeric [N] index or a [[wikilink]] (with optional
# line-anchor suffix :L42-L58 or display alias |alias). Updated to keep the
# colon-line-spec as part of the same token (not split as an alias).
_CITE_TOKEN = re.compile(r"\[\d+\]|\[\[[^\]|]+(?::[^\]|]+)?(?:\|[^\]]*)?\]\]")
# A "cite tail" = one or more whitespace-separated citation tokens at the very
# end of a sentence's run.
_CITE_TAIL = re.compile(
    r"(?:\s*(?:\[\d+\]|\[\[[^\]|]+(?::[^\]|]+)?(?:\|[^\]]*)?\]\]))+\s*$"
)
# Split prose into sentence units keeping each unit's trailing cite tail.
_UNIT = re.compile(
    r".*?[.!?]"
    r"(?=\s|$)"
    r"(?:\s*(?:\[\d+\]|\[\[[^\]|]+(?::[^\]|]+)?(?:\|[^\]]*)?\]\]))*",
    re.DOTALL,
)
```

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_render.py -x
```

Expected: `PASSED` (all render tests, old and new)

```
pytest tests/test_grounding/ -x
```

Expected: no regressions.

### Step 5: Commit

```bash
git add src/bad_research/grounding/render.py tests/test_grounding/test_render.py \
&& git commit -m "feat(grounding/render): parse [[note-id:L42-L58]] line-anchored tokens; add parse_line_anchor (A-4)"
```

---

## Task A-5: `LineSpanJudge` in `grounding/verifier.py` — replaces `CitationPresentNLI` on keyless path

**Files:**
- Modify: `src/bad_research/grounding/verifier.py` (add `LineSpanJudge`; update `default_nli`; update `CitationVerifier.verify` to pass line span as Tier-B/C premise)
- Test: append to `tests/test_grounding/test_verifier.py`

**Key invariant:** same interface as `HostJudgeNLI` and `CitationPresentNLI` (the
`predict(premise, hypothesis) -> dict[str, float]` method). Zero caller change outside
`default_nli`. `CitationPresentNLI` stays as an absolute fallback for the case where
neither `[local]` nor an LLM provider is available.

**Line-span re-read:** `CitationVerifier.verify` now extracts `(line_start, line_end)`
from the anchor after Tier A passes; it calls `get_body_lines` (A-2) or
`body_to_lines` lazily, slices the lines, and passes the line text as the Tier-B/C
`premise` instead of `anchor.quoted_support`. When `anchor.line_start` is None
(legacy anchor), it falls back to `anchor.quoted_support` — today's behavior.

### Step 1: Write the failing test

```python
# Append to tests/test_grounding/test_verifier.py
# (existing conftest.py provides fake_llm fixture with FakeLLMProvider)

from bad_research.grounding.anchors import ClaimAnchor
from bad_research.grounding.verifier import (
    LineSpanJudge,
    VerifyResult,
    VerifyVerdict,
    CitationVerifier,
    default_nli,
)
from bad_research.grounding.anchors import AnchorStore
import sqlite3


def _store_with_anchor(anchor: ClaimAnchor) -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    store.upsert(anchor)
    return store


# --- LineSpanJudge unit tests ---

def test_line_span_judge_verbatim_returns_entailment(fake_llm):
    judge = LineSpanJudge(fake_llm)
    # Near-verbatim overlap >= CLAIM_QUOTE_OVERLAP_SKIP -> entailment, no LLM call
    result = judge.predict(
        premise="Vietnam reached 64% internet penetration in 2024.",
        hypothesis="Vietnam reached 64% internet penetration in 2024.",
    )
    assert result["entailment"] == 1.0
    assert len(fake_llm.calls) == 0  # no LLM call for near-verbatim


def test_line_span_judge_paraphrase_returns_neutral(fake_llm):
    judge = LineSpanJudge(fake_llm)
    # Genuine paraphrase -> NEUTRAL (queued for Tier-C batched judge)
    result = judge.predict(
        premise="Vietnam reached 64% internet penetration in 2024.",
        hypothesis="Online access in Vietnam exceeded half the population by 2024.",
    )
    assert result["neutral"] == 1.0
    assert result["entailment"] == 0.0
    assert len(fake_llm.calls) == 0  # LineSpanJudge is a router; no LLM itself


def test_default_nli_returns_line_span_judge_when_llm_provided(fake_llm):
    from bad_research.grounding.verifier import nli_available
    if nli_available():
        import pytest
        pytest.skip("local NLI installed; skipping keyless path test")
    nli = default_nli(fake_llm)
    assert isinstance(nli, LineSpanJudge)


def test_default_nli_returns_citation_present_when_no_llm():
    from bad_research.grounding.verifier import CitationPresentNLI, nli_available
    if nli_available():
        import pytest
        pytest.skip("local NLI installed; skipping keyless path test")
    nli = default_nli(None)
    assert isinstance(nli, CitationPresentNLI)


# --- CitationVerifier.verify uses line span as Tier-B premise ---

def test_citation_verifier_uses_line_span_premise_when_anchor_has_lines(fake_llm):
    import json
    # Build a note body with known lines
    body = "Line one content.\nThe GDP grew 12.4% annually.\nLine three text.\n"
    # "The GDP grew 12.4% annually." is on line 2, chars 18..46
    quote = "The GDP grew 12.4% annually."
    start = body.index(quote)
    end = start + len(quote)

    from bad_research.grounding.extract import body_to_lines, char_span_to_line_range
    bl = body_to_lines(body)
    ls, le = char_span_to_line_range(bl, start, end)

    from bad_research.grounding.anchors import quote_sha
    anchor = ClaimAnchor(
        note_id="n1",
        char_start=start,
        char_end=end,
        claim="GDP grew 12.4% annually.",
        quoted_support=quote,
        line_start=ls,
        line_end=le,
    )

    store = _store_with_anchor(anchor)

    # The judge returns neutral for a paraphrase -> goes to Tier-C -> fake_llm
    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "supported", "score": 0.92, "reason": "matches"}
    ])]

    from bad_research.grounding.verifier import LineSpanJudge
    nli = LineSpanJudge(fake_llm)
    verifier = CitationVerifier(nli=nli, llm=fake_llm)

    # report sentence is a paraphrase — triggers Tier-C
    report = f"Annual GDP expansion hit 12.4%. [[{anchor.anchor_id}]]"
    result = verifier.verify(report, store, {"n1": body})

    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.verdict == VerifyVerdict.SUPPORTED
    # The Tier-C judge was called with the LINE SPAN text as the quote, not the
    # full quoted_support (they're the same here, but the test confirms the path ran).
    assert len(fake_llm.calls) >= 1


def test_citation_verifier_falls_back_to_quoted_support_when_no_line_info(fake_llm):
    import json
    body = "Legacy note body. Old quote text. More text."
    quote = "Old quote text."
    start = body.index(quote)
    end = start + len(quote)
    from bad_research.grounding.anchors import quote_sha
    anchor = ClaimAnchor(
        note_id="n1", char_start=start, char_end=end,
        claim="Legacy claim.", quoted_support=quote,
        # No line_start / line_end -> NULL (legacy anchor)
    )
    store = _store_with_anchor(anchor)

    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "supported", "score": 0.85, "reason": "ok"}
    ])]
    nli = LineSpanJudge(fake_llm)
    verifier = CitationVerifier(nli=nli, llm=fake_llm)

    # paraphrase to force Tier-C
    report = f"An archival passage confirms this. [[{anchor.anchor_id}]]"
    result = verifier.verify(report, store, {"n1": body})
    assert len(result.findings) == 1
    assert result.findings[0].verdict == VerifyVerdict.SUPPORTED
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_verifier.py::test_line_span_judge_verbatim_returns_entailment -x
```

Expected: `FAIL — ImportError: cannot import name 'LineSpanJudge' from 'bad_research.grounding.verifier'`

### Step 3: Implement

**`src/bad_research/grounding/verifier.py`**

Add `LineSpanJudge` class after `HostJudgeNLI` (after line 81). It is architecturally
identical to `HostJudgeNLI` — it is the same lexical router — so it can delegate to it,
or duplicate the 10-line logic. The distinction is that callers of `default_nli` now get
`LineSpanJudge` instead of `HostJudgeNLI`; the verify loop passes the line span text as
the premise (handled in `CitationVerifier.verify`, not in the judge class itself):

```python
class LineSpanJudge:
    """Keyless Tier-B judge for the line-anchored citation path (A-layer 5).

    Replaces CitationPresentNLI on the keyless path. Identical interface to
    HostJudgeNLI: near-verbatim pairs (overlap >= CLAIM_QUOTE_OVERLAP_SKIP)
    return ENTAILMENT immediately ($0); genuine paraphrases return NEUTRAL so
    CitationVerifier escalates them to the batched Tier-C judge.

    The KEY difference from HostJudgeNLI is semantic: the *premise* passed in
    by CitationVerifier.verify is the specific cited LINE SPAN text (re-read
    from the note body via body_to_lines), not the opaque stored quoted_support.
    This class is still a pure lexical router — it makes no LLM call itself.
    CitationPresentNLI stays as the absolute fallback when llm is None.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]:
        # Same routing logic as HostJudgeNLI: lexical overlap decides tier.
        from .gate import CLAIM_QUOTE_OVERLAP_SKIP, claim_quote_overlap

        if claim_quote_overlap(hypothesis, premise) >= CLAIM_QUOTE_OVERLAP_SKIP:
            return {"entailment": 1.0, "neutral": 0.0, "contradiction": 0.0}
        return {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}
```

Update `default_nli` to return `LineSpanJudge` instead of `HostJudgeNLI` on the
keyless+host path (lines 84-100):

```python
def default_nli(llm: LLMProvider | None = None) -> NLIModel:
    """The ship-path NLI factory. Resolution order:

      1. `[local]` installed -> the real cross-encoder (CrossEncoderNLI). UNCHANGED.
      2. keyless + a host judge available (`llm` provided) -> LineSpanJudge: the
         lexical pre-filter routes the paraphrase band into the batched host judge
         (same routing as HostJudgeNLI, but the premise passed by CitationVerifier
         is now the specific line span text, not the full quoted_support — closes G4).
      3. keyless + NO host judge -> CitationPresentNLI, the absolute fallback no-op.
    """
    if nli_available():
        from .nli import CrossEncoderNLI
        return CrossEncoderNLI()
    if llm is not None:
        return LineSpanJudge(llm)
    return CitationPresentNLI()
```

Update `CitationVerifier.verify` to extract the line span and pass it as the Tier-B/C
premise when `anchor.line_start` is not None. Replace the Tier-B block (currently around
lines 309-323) — specifically the block after `tier_a_byte_identity`:

```python
                # Tier B — local NLI ($0).
                # premise = specific cited line span (if anchor has line info) or
                # full quoted_support (legacy fallback). This is the G4 fix: the
                # judge now sees exactly what lines L42-L58 say, not the opaque
                # stored quote from fetch time.
                if anchor.line_start is not None:
                    from bad_research.core.db import store_body_lines
                    from bad_research.grounding.extract import body_to_lines, char_span_to_line_range
                    bl = body_to_lines(body) if body else []
                    if bl:
                        ls = anchor.line_start - 1   # 0-indexed slice into bl
                        le = anchor.line_end          # exclusive
                        # Collect the text of lines line_start..line_end (1-based inclusive)
                        line_texts = [
                            body[bl[i][0]:bl[i][1]]
                            for i in range(max(0, ls), min(len(bl), le))
                        ]
                        premise = " ".join(line_texts).strip() or anchor.quoted_support
                    else:
                        premise = anchor.quoted_support
                else:
                    premise = anchor.quoted_support

                scores = self.nli.predict(premise, hypothesis)
                label = classify_nli(scores)
                if label is NLILabel.ENTAILMENT:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.SUPPORTED, scores["entailment"]))
                elif label is NLILabel.CONTRADICTION:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.CONTRADICTED, scores["contradiction"]))
                else:
                    stub = CitationFinding(anchor.anchor_id, sent, VerifyVerdict.UNSUPPORTED, 0.0)
                    pending.append((stub, hypothesis, premise))
```

Note: also remove the now-duplicate `scores = self.nli.predict(anchor.quoted_support, hypothesis)` line that was there before and replace with the block above.

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_verifier.py -x
```

Expected: `PASSED`

```
pytest tests/test_grounding/ -x
```

Expected: no regressions.

### Step 5: Commit

```bash
git add src/bad_research/grounding/verifier.py tests/test_grounding/test_verifier.py \
&& git commit -m "feat(grounding/verifier): add LineSpanJudge; CitationVerifier uses line-span premise (A-5, closes G4)"
```

---

## Task A-6: `gate.py` — promote `verify_score < PARTIAL_LOW` to critical; add `_BOLD_SPAN_ONLY` guard

**Files:**
- Modify: `src/bad_research/grounding/gate.py` (two changes: `_is_formatting_line` + `no_uncited_claim_gate`)
- Test: append to `tests/test_grounding/test_gate.py`

### Step 1: Write the failing test

```python
# Append to tests/test_grounding/test_gate.py

from bad_research.grounding.gate import _is_formatting_line, no_uncited_claim_gate, Finding
from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
import sqlite3


def _store_with_anchor(anchor: ClaimAnchor) -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    store.upsert(anchor)
    return store


def test_is_formatting_line_bold_span_only():
    # A line that is entirely bold prose (but NOT a bold heading) should be
    # detected as formatting by the new _BOLD_SPAN_ONLY guard.
    # Note: existing _BOLD_ONLY catches `**...**` whole-line; this guard catches
    # lines like "**some mid-sentence bold fragment**" that aren't headings.
    assert _is_formatting_line("**Important finding:**") is True
    assert _is_formatting_line("**Key Findings 2024**") is True  # already caught


def test_is_formatting_line_does_not_flag_partial_bold():
    # A line that has bold inside a real sentence is NOT a formatting line.
    assert _is_formatting_line("The study found **12.4%** growth in 2024.") is False


def test_gate_promotes_unsupported_anchor_below_partial_low_to_critical():
    # An anchor with verify_score < PARTIAL_LOW (0.40) and verified=0 should
    # produce a CRITICAL finding (not just major "unverified-cite").
    from bad_research.grounding.anchors import quote_sha
    body = "GDP grew 12.4% annually in the region."
    quote = "GDP grew 12.4% annually in the region."
    start = body.index(quote)
    anchor = ClaimAnchor(
        note_id="n1", char_start=start, char_end=start + len(quote),
        claim="GDP grew 12.4%.", quoted_support=quote,
        verified=0, verify_score=0.15,  # explicitly below PARTIAL_LOW=0.40
    )
    store = _store_with_anchor(anchor)

    # Sentence cites the anchor but it has a low verify_score -> critical
    report = f"GDP grew 12.4% annually. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    critical = [f for f in findings if f.severity == "critical"]
    assert any("unsupported" in f.failure_mode or "verify_score" in f.recommendation.lower()
               for f in critical), f"Expected critical finding, got: {findings}"


def test_gate_keeps_partial_verdict_as_major():
    # An anchor with verify_score in [PARTIAL_LOW, SUPPORTED_FLOOR) stays major.
    from bad_research.grounding.anchors import quote_sha
    body = "GDP grew 12.4% annually in the region."
    quote = "GDP grew 12.4% annually in the region."
    start = body.index(quote)
    anchor = ClaimAnchor(
        note_id="n1", char_start=start, char_end=start + len(quote),
        claim="GDP grew 12.4%.", quoted_support=quote,
        verified=0, verify_score=0.55,  # in the "partial" band
    )
    store = _store_with_anchor(anchor)

    report = f"GDP grew 12.4% annually. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    # verify_score=0.55 is above PARTIAL_LOW -> major, not critical
    unverified = [f for f in findings if f.failure_mode == "unverified-cite"]
    assert unverified
    assert all(f.severity == "major" for f in unverified)
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_gate.py::test_gate_promotes_unsupported_anchor_below_partial_low_to_critical -x
```

Expected: `FAIL — AssertionError: Expected critical finding` (current gate emits "major" for all unverified-cites regardless of score)

### Step 3: Implement

**`src/bad_research/grounding/gate.py`**

Change 1: update `_is_formatting_line` (lines 65-75) to add `_BOLD_SPAN_ONLY` guard.

Add a new compiled pattern after `_CODE_SPAN_ONLY` (after line 59):
```python
# A line whose ENTIRE visible content is one or more bold spans (with optional
# punctuation) — a formatting pseudo-heading fragment, not a factual sentence.
# Catches `**Important:**` and `**Key Findings 2024**` (which _BOLD_ONLY also
# catches via the `^\*\*[^*].*\*\*$` pattern, but this is an explicit complement).
_BOLD_SPAN_ONLY = re.compile(r"^\s*(?:\*\*[^*]+\*\*[.:]?\s*)+$")
```

Update `_is_formatting_line` (lines 65-75) to check `_BOLD_SPAN_ONLY`:
```python
def _is_formatting_line(line: str) -> bool:
    """True for structural chrome that carries no factual claim: bold-only
    pseudo-headings, markdown headings, table rows/dividers, lone inline
    code spans, and lines whose entire content is bold spans (G1 belt-and-suspenders)."""
    if line.startswith("#"):
        return True
    if _BOLD_ONLY.match(line):
        return True
    if _BOLD_SPAN_ONLY.match(line):
        return True
    if _TABLE_ROW.match(line):
        return True
    return bool(_CODE_SPAN_ONLY.match(line))
```

Change 2: update `no_uncited_claim_gate` (lines 136-158) to promote low-score anchors
to critical. Replace the `elif anchor.verified != 1:` branch:

```python
            elif anchor.verified != 1:
                # Determine severity based on verify_score if available.
                # A span that explicitly does NOT support the claim (score < PARTIAL_LOW)
                # blocks ship as critical (G4 gate tightening, round2-citation §4).
                from .verifier import PARTIAL_LOW
                if anchor.verify_score is not None and anchor.verify_score < PARTIAL_LOW:
                    severity = "critical"
                    rec = (
                        f"Citation {c} verify_score={anchor.verify_score:.2f} < {PARTIAL_LOW} "
                        f"— span explicitly does not support the claim. Drop or reground."
                    )
                else:
                    severity = "major"
                    rec = (
                        f"Citation {c} was not confirmed by the CitationVerifier "
                        f"— re-run Tier B or hedge."
                    )
                findings.append(Finding("unverified-cite", severity, sent, rec))
```

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_gate.py -x
```

Expected: `PASSED`

```
pytest tests/test_grounding/ -x
```

Expected: no regressions.

### Step 5: Commit

```bash
git add src/bad_research/grounding/gate.py tests/test_grounding/test_gate.py \
&& git commit -m "feat(grounding/gate): promote verify_score<PARTIAL_LOW to critical; add _BOLD_SPAN_ONLY guard (A-6, closes G1/G4 gate layer)"
```

---

## Task A-7: `note_find` MCP tool in `mcp/server.py`

**Files:**
- Modify: `src/bad_research/mcp/server.py` (append new tool after `verify_citations`)
- Test: `tests/test_mcp/test_note_find.py` (create)

### Step 1: Write the failing test

Create `tests/test_mcp/test_note_find.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_vault(tmp_path: Path, note_id: str, body: str):
    """Return a minimal mock vault wired to an in-memory DB with one note."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS note_content "
        "(note_id TEXT PRIMARY KEY, body TEXT NOT NULL, body_plain TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO note_content (note_id, body, body_plain) VALUES (?, ?, ?)",
        (note_id, body, body),
    )
    conn.commit()

    vault = MagicMock()
    vault.db = conn
    return vault


def test_note_find_returns_matching_lines(tmp_path):
    from bad_research.mcp.server import note_find

    body = (
        "Introduction paragraph here.\n"
        "Vietnam reached 64.3% internet penetration in 2024.\n"
        "This exceeded the regional average by 8 percentage points.\n"
        "Further details in appendix.\n"
    )
    vault = _make_vault(tmp_path, "source-note-19", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("source-note-19", r"64\.3%", context_lines=0)

    result = json.loads(result_json)
    assert result["ok"] is True
    matches = result["matches"]
    assert len(matches) >= 1
    m = matches[0]
    assert m["line_start"] == 2
    assert m["line_end"] == 2
    assert "64.3%" in m["text"]
    assert "char_start" in m
    assert "char_end" in m


def test_note_find_with_context_lines(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Line A.\nLine B with 42%.\nLine C.\nLine D.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"42%", context_lines=1)

    result = json.loads(result_json)
    assert result["ok"] is True
    m = result["matches"][0]
    # context_lines=1 means the returned line range expands ±1
    assert m["line_start"] <= 2
    assert m["line_end"] >= 2


def test_note_find_no_match(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Nothing special here.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"xyzzy_absent_pattern_123")

    result = json.loads(result_json)
    assert result["ok"] is True
    assert result["matches"] == []


def test_note_find_note_not_found(tmp_path):
    from bad_research.mcp.server import note_find

    body = "Some body.\n"
    vault = _make_vault(tmp_path, "n1", body)

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("nonexistent-note", r"anything")

    result = json.loads(result_json)
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_note_find_invalid_regex(tmp_path):
    from bad_research.mcp.server import note_find

    vault = _make_vault(tmp_path, "n1", "body\n")

    with patch("bad_research.mcp.server._get_vault", return_value=vault):
        result_json = note_find("n1", r"[invalid(regex")

    result = json.loads(result_json)
    assert result["ok"] is False
    assert "regex" in result["error"].lower() or "invalid" in result["error"].lower()
```

### Step 2: Run to verify it fails

```
pytest tests/test_mcp/test_note_find.py::test_note_find_returns_matching_lines -x
```

Expected: `FAIL — ImportError` or `FAIL — TypeError: note_find() is not defined`

### Step 3: Implement

Append to `src/bad_research/mcp/server.py` after the `verify_citations` tool:

```python
@server.tool()
def note_find(note_id: str, pattern: str, context_lines: int = 3) -> str:
    """Regex grep within a stored note body. Returns matching line ranges.

    Analogous to OpenAI web.find: searches for `pattern` (Python regex) in the
    body of note `note_id` and returns each match's line numbers, matched text,
    and char offsets. No LLM — pure string search, ~$0. Used by synthesizer and
    verifier agents to locate the exact line span for a claim.

    Args:
        note_id: The vault note ID to search within.
        pattern: Python regex pattern to search for.
        context_lines: Number of lines of surrounding context to include in the
            returned line range (default 3). Set to 0 for match-only.

    Returns JSON:
        {"ok": true, "matches": [
          {"line_start": 42, "line_end": 44, "text": "...", "char_start": 1247, "char_end": 1402}
        ]}
    or {"ok": false, "error": "..."}
    """
    import re as _re

    from bad_research.grounding.extract import body_to_lines

    vault = _get_vault()
    row = vault.db.execute(
        "SELECT body FROM note_content WHERE note_id = ?", (note_id,)
    ).fetchone()
    if row is None:
        return json.dumps({"ok": False, "error": f"Note not found: {note_id}"})

    body: str = row["body"]

    try:
        compiled = _re.compile(pattern, _re.IGNORECASE)
    except _re.error as exc:
        return json.dumps({"ok": False, "error": f"Invalid regex pattern: {exc}"})

    lines = body_to_lines(body)
    n_lines = len(lines)
    matches: list[dict] = []

    for m in compiled.finditer(body):
        char_start = m.start()
        char_end = m.end()

        # find which line the match starts/ends on (1-based)
        match_ls = 1
        match_le = n_lines
        for i, (cs, ce) in enumerate(lines):
            if cs <= char_start < ce or (i == n_lines - 1 and char_start >= cs):
                match_ls = i + 1
            if cs <= char_end <= ce or (i == n_lines - 1 and char_end >= cs):
                match_le = i + 1
                break

        # expand by context_lines
        ctx_ls = max(1, match_ls - context_lines)
        ctx_le = min(n_lines, match_le + context_lines)

        # slice the text for the context window
        if lines:
            text_start = lines[ctx_ls - 1][0]
            text_end = lines[ctx_le - 1][1]
            text_slice = body[text_start:text_end]
        else:
            text_slice = m.group(0)

        matches.append({
            "line_start": ctx_ls,
            "line_end": ctx_le,
            "text": text_slice,
            "char_start": char_start,
            "char_end": char_end,
        })

    return json.dumps({"ok": True, "matches": matches})
```

### Step 4: Run to verify pass

```
pytest tests/test_mcp/test_note_find.py -x
```

Expected: `PASSED`

```
pytest tests/test_mcp/ tests/test_grounding/ -x
```

Expected: no regressions.

### Step 5: Commit

```bash
git add src/bad_research/mcp/server.py tests/test_mcp/test_note_find.py \
&& git commit -m "feat(mcp): add note_find tool — regex line-range search in note body (A-7)"
```

---

## Task A-8: Skill prose edits — `bad-research-11-synthesize.md` and `bad-research-11.5-citation-verifier.md`

**Files:**
- Modify: `src/bad_research/skills/bad-research-11-synthesize.md` (Step 11.4b evidence format; Step 11.6 citation token instruction)
- Modify: `src/bad_research/skills/bad-research-11.5-citation-verifier.md` (note that `LineSpanJudge` is now the keyless Tier-B)
- Test: `tests/test_skills/` (check what structural skill tests exist, then append or create a targeted test)

### Step 1: Write the failing test

```python
# Create tests/test_skills/test_skill_a_prose.py

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent.parent / "src" / "bad_research" / "skills"


def _read(name: str) -> str:
    return (SKILLS_DIR / name).read_text(encoding="utf-8")


def test_synthesize_skill_has_line_start_line_end_evidence_fields():
    text = _read("bad-research-11-synthesize.md")
    assert "line_start" in text, "synthesis-evidence.md format must include line_start field"
    assert "line_end" in text, "synthesis-evidence.md format must include line_end field"


def test_synthesize_skill_instructs_line_anchored_token():
    text = _read("bad-research-11-synthesize.md")
    # The synthesizer spawn instructions must require the [[note-id:Lstart-Lend]] form
    assert "L" in text and ":L" in text, (
        "Step 11.6 spawn instructions must reference the [[note-id:Lstart-Lend]] format"
    )


def test_synthesize_skill_forbids_inventing_line_numbers():
    text = _read("bad-research-11-synthesize.md")
    assert "Do NOT invent" in text or "do not invent" in text.lower(), (
        "Spawn instructions must tell synthesizer not to invent line numbers"
    )


def test_citation_verifier_skill_mentions_line_span_judge():
    text = _read("bad-research-11.5-citation-verifier.md")
    assert "LineSpanJudge" in text, (
        "Step 11.5 skill must note that LineSpanJudge is the keyless Tier-B on the line-anchored path"
    )
```

### Step 2: Run to verify it fails

```
pytest tests/test_skills/test_skill_a_prose.py -x
```

Expected: `FAIL — AssertionError: synthesis-evidence.md format must include line_start field`

### Step 3: Implement

**`src/bad_research/skills/bad-research-11-synthesize.md`** — make two prose changes:

**Change 1:** In Step 11.4b (the synthesis-evidence.md format block around line 152-159), extend the chunk format to include `line_start` and `line_end` fields. Change the evidence format block from:

```markdown
   For each returned chunk, the `note_id` + `char_start`/`char_end` are the
   citation anchor; its `quoted_support` is the verbatim span. Write the
   section→chunks map to `research/temp/synthesis-evidence.md`; pass its path to
   the synthesizer.
```

to:

```markdown
   For each returned chunk, the `note_id` + `char_start`/`char_end` are the
   citation anchor; its `quoted_support` is the verbatim span. Compute
   `(line_start, line_end)` from `char_start`/`char_end` using
   `char_span_to_line_range` (available via `bad_research.grounding.extract`).
   Write the section→chunks map to `research/temp/synthesis-evidence.md`:

   ```markdown
   - chunk: "Vietnam reached 64%..."
     note_id: source-note-19
     char_start: 1247
     char_end: 1402
     line_start: 42          # 1-based line in the note body
     line_end: 44            # 1-based line in the note body
     quoted_support: "..."
   ` ` `

   Pass its path to the synthesizer.
```

**Change 2:** In Step 11.6 spawn template GENERATION-TIME GROUNDING block (around line 239-255), add a line-anchored citation instruction. Change:

```
  GENERATION-TIME GROUNDING (non-negotiable): cite as you write, in
  pass 1. Every factual sentence — anything with a number, named entity,
  comparative/superlative, or causal/temporal claim — MUST end with its
  citation token BEFORE the terminal period
  (`… grew 12.4% in 2024 [[note-id]].` or `… [3].`).
```

to:

```
  GENERATION-TIME GROUNDING (non-negotiable): cite as you write, in
  pass 1. Every factual sentence — anything with a number, named entity,
  comparative/superlative, or causal/temporal claim — MUST end with its
  citation token BEFORE the terminal period. Use the LINE-ANCHORED form:
  `… grew 12.4% in 2024 [[note-id:Lstart-Lend]].` where `Lstart-Lend`
  comes directly from the chunk's `(line_start, line_end)` in
  synthesis-evidence.md. Do NOT invent line numbers — copy them from the
  evidence file. If citation_style == "inline", render `[N:Lstart-Lend]`
  and add `(L<start>-L<end>)` after the URL in the Sources section.
```

**`src/bad_research/skills/bad-research-11.5-citation-verifier.md`** — in the Procedure section (step 1), update the Tier-B description from:

```
   - **(B) NLI entailment** — does the note text entail the sentence? Checked by
     a local natural-language-inference model, `nli-deberta-v3-base` ($0). For
     the ~10% neutral band (neither entailed nor contradicted), a `triage`-tier
     LLM-judge fallback (batched ~20/call).
```

to:

```
   - **(B) NLI entailment** — does the note text entail the sentence? Checked by
     a local natural-language-inference model, `nli-deberta-v3-base` ($0) when
     `[local]` is installed. On the keyless path, `LineSpanJudge` (the Tier-B
     replacement for `CitationPresentNLI`) routes near-verbatim pairs to accept
     and genuine paraphrases to the batched Tier-C judge — using the specific
     cited line span (L42-L58) as the premise, not the full `quoted_support`.
     For the ~10% neutral band (neither entailed nor contradicted), a `triage`-tier
     LLM-judge fallback (batched ~20/call).
```

### Step 4: Run to verify pass

```
pytest tests/test_skills/test_skill_a_prose.py -x
```

Expected: `PASSED`

### Step 5: Commit

```bash
git add "src/bad_research/skills/bad-research-11-synthesize.md" \
        "src/bad_research/skills/bad-research-11.5-citation-verifier.md" \
        tests/test_skills/test_skill_a_prose.py \
&& git commit -m "docs(skills): add line_start/line_end to synthesis-evidence; line-anchored token instruction; LineSpanJudge note (A-8)"
```

---

## Task A-9: Regression fixture note — cited-but-contradicting claim dependency on E1

**Files:**
- Test: `tests/test_grounding/test_regression_a9.py` (create)

**Scope:** This task documents the semantic guard requirement and adds a deterministic
in-process fixture that exercises the new `LineSpanJudge` + gate path with a
contradicting span. The full LLM-evaluated golden fixture (`09_cited_contradiction`)
lives in Workstream E1 (`bad-research-E1-eval-harness-design.md`) and is gated by
`requires_llm: true` — do NOT build the `LLMJudge` routing or golden JSON here.

### Step 1: Write the failing test

Create `tests/test_grounding/test_regression_a9.py`:

```python
"""Regression fixture A-9: a cited-but-contradicting claim must be caught
by the LineSpanJudge + gate path.

This is the deterministic (no-LLM) in-process half of the regression guard.
The full offline golden fixture (09_cited_contradiction, requires_llm: true)
lives in Workstream E1 — see docs/superpowers/plans/sections/E1-eval-harness.md.
Dependency: E1 builds LLMJudge routing; this test exercises the Tier-C path only.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import gate_blocks_ship, no_uncited_claim_gate
from bad_research.grounding.verifier import (
    CitationVerifier,
    LineSpanJudge,
    VerifyVerdict,
)
from tests.test_grounding.conftest import FakeLLMProvider


def _store_with_anchor(anchor: ClaimAnchor) -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    store.upsert(anchor)
    return store


@pytest.fixture
def contradicting_fixture():
    """A note that says 'GDP declined 2.1%'; a report sentence that claims
    'GDP grew 2.1%'. The cited span is a contradiction."""
    body = (
        "Economic indicators for Q4 2024:\n"
        "GDP declined 2.1% year-over-year due to trade disruptions.\n"
        "Unemployment rose to 8.3% in the same period.\n"
    )
    quote = "GDP declined 2.1% year-over-year due to trade disruptions."
    start = body.index(quote)
    end = start + len(quote)

    from bad_research.grounding.extract import body_to_lines, char_span_to_line_range
    bl = body_to_lines(body)
    ls, le = char_span_to_line_range(bl, start, end)

    anchor = ClaimAnchor(
        note_id="n1",
        char_start=start,
        char_end=end,
        claim="GDP grew 2.1% year-over-year.",
        quoted_support=quote,
        line_start=ls,
        line_end=le,
    )
    return body, anchor


def test_contradicting_claim_reaches_tier_c(contradicting_fixture):
    """The report sentence asserts growth; the cited span says decline.
    LineSpanJudge should route it to Tier-C (paraphrase band -> neutral)."""
    body, anchor = contradicting_fixture
    store = _store_with_anchor(anchor)

    # Fake LLM returns "contradicted" for this pair
    fake_llm = FakeLLMProvider(script=[json.dumps([
        {"id": 0, "verdict": "contradicted", "score": 0.05, "reason": "span says declined, claim says grew"}
    ])])

    nli = LineSpanJudge(fake_llm)
    verifier = CitationVerifier(nli=nli, llm=fake_llm)

    report = f"GDP grew 2.1% year-over-year. [[{anchor.anchor_id}]]"
    result = verifier.verify(report, store, {"n1": body})

    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.verdict == VerifyVerdict.CONTRADICTED, (
        f"Expected CONTRADICTED for a span-vs-claim mismatch, got {f.verdict}"
    )
    assert f.score < 0.40  # well below PARTIAL_LOW


def test_gate_blocks_ship_on_contradicted_low_score_cite(contradicting_fixture):
    """After the verifier stamps verify_score < PARTIAL_LOW, the gate must
    emit a CRITICAL finding that blocks ship (gate_blocks_ship returns True)."""
    body, anchor = contradicting_fixture
    # Stamp the anchor as failed with a low score (simulating post-verify state)
    anchor.verified = 0
    anchor.verify_score = 0.05  # below PARTIAL_LOW=0.40

    store = _store_with_anchor(anchor)

    report = f"GDP grew 2.1% year-over-year. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    assert gate_blocks_ship(findings), (
        "A cited-but-contradicting claim with verify_score < PARTIAL_LOW must block ship"
    )
    critical = [f for f in findings if f.severity == "critical"]
    assert critical, f"Expected at least one critical finding, got: {findings}"


# Dependency note: E1 builds the golden fixture 09_cited_contradiction with
# requires_llm: true. That fixture exercises LLMJudge routing end-to-end.
# The tests above cover the deterministic in-process path (Tier-C fake LLM).
```

### Step 2: Run to verify it fails

```
pytest tests/test_grounding/test_regression_a9.py::test_contradicting_claim_reaches_tier_c -x
```

Expected: `FAIL — ImportError` or `FAIL — AssertionError` (depends on whether A-5/A-6 are complete; if A-5 and A-6 are done, the test may pass; if not, it fails confirming the dependency)

### Step 3: Implement

No new production code in this task — A-5 and A-6 provide all the required functionality.
If this test fails after A-5 and A-6 are merged, investigate the `verify_score` stamping
path in `CitationVerifier.verify` (the `store.set_verified` call at the end of the method
must write `score=f.score` for CONTRADICTED findings, which it already does by line 374).

### Step 4: Run to verify pass

```
pytest tests/test_grounding/test_regression_a9.py -x
```

Expected: `PASSED` (both tests, after A-5 and A-6 are in place)

```
pytest tests/test_grounding/ tests/test_core/ tests/test_mcp/ tests/test_skills/ -x
```

Expected: full green, `pass_rate` of existing golden eval unchanged.

### Step 5: Commit

```bash
git add tests/test_grounding/test_regression_a9.py \
&& git commit -m "test(grounding): regression fixture A-9 — cited-but-contradicting claim blocked by LineSpanJudge + gate (depends on E1 for golden fixture)"
```

---

## Full workstream verification

After all A-1..A-9 tasks are committed, run the complete test suite:

```
pytest tests/test_grounding/ tests/test_core/test_db_body_lines.py \
       tests/test_mcp/test_note_find.py tests/test_skills/test_skill_a_prose.py \
       --tb=short -q
```

Expected: all green, zero regressions in pre-existing tests.

```
bad gate <path-to-golden-report> 2>&1 | grep pass_rate
```

Expected: `pass_rate=1.0` (existing golden eval harness unaffected).
