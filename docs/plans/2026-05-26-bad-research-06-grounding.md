# Bad Research — Plan 06: Grounding / No-Hallucination — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bad_research/grounding/` — the forward span-binding (`claim_anchors`) plus the backward CitationVerifier (3-tier: byte-identity → local NLI → triage-LLM judge) and the deterministic `$0` Stage-16 no-uncited-claim gate, so no fabricated quote and no uncited non-trivial claim can ever ship.

**Architecture:** Two forward defenses (DSS span extraction at fetch → `claim_anchors` rows keyed on `quote_sha = sha256(quote)[:8]`; writer-sees-evidence) plus two backward defenses (the per-cited-sentence CitationVerifier and the deterministic gate). The verifier runs cheapest-check-first: Tier A re-`find`+SHA byte-identity (`$0`), Tier B `cross-encoder/nli-deberta-v3-base` entailment (`$0`, CPU), Tier C `triage`-tier `LLMProvider` judge batched ~20/call ONLY for the NLI-neutral band. Dispositions map supported→keep, partial→hedge, unsupported→drop-cite, contradicted→contradiction-graph. The gate is pure string + table lookup against `claim_anchors.verified` — fail ship if any non-trivial claim lacks a verifiable, verified citation. The verifier subagent is tool-locked `[Read]`.

**Tech Stack:** Python 3.11+, `sqlite3` (stdlib, matches hyperresearch's `claim_anchors` store), `sentence-transformers` + `torch` (the local NLI cross-encoder — lazy-imported, mock-stubbed in tests), `rapidfuzz` (fuzzy quote-locate fallback), the `LLMProvider`/`ModelTier` seam from Plan 01 (Tier-C judge), pytest. No GPU. No network in the hot path except the gated Tier-C judge.

---

## File Structure

All new code lives under `ultimate-research/bad-research/src/bad_research/grounding/`. Tests mirror it under `ultimate-research/bad-research/tests/test_grounding/`.

| File | Responsibility |
|---|---|
| `grounding/__init__.py` | Public exports: `extract_spans`, `ClaimAnchor`, `AnchorStore`, `CitationVerifier`, `VerifyVerdict`, `no_uncited_claim_gate`, `Finding`, `render_citation`. |
| `grounding/anchors.py` | `ClaimAnchor` dataclass + `quote_sha()` + `AnchorStore` (the `claim_anchors` SQLite table: DDL, `upsert`, `get`, `set_verified`, `build_from_claims`, `rebuild` for `sync`). |
| `grounding/extract.py` | DSS span extraction: `extract_spans(claim, quoted_support, note_body)` → `(char_start, char_end)` via exact `find` then rapidfuzz fallback; `None` when no locatable quote (claim is dropped). |
| `grounding/nli.py` | `NLIModel` wrapper over `cross-encoder/nli-deberta-v3-base` (lazy import, `predict(premise, hypothesis) -> {entailment, neutral, contradiction}`); `NLIStub` protocol so tests inject a deterministic model. |
| `grounding/verifier.py` | `CitationVerifier` — the 3-tier per-cited-sentence pass; `VerifyVerdict`; the disposition table; the `triage`-LLM judge batcher; `verify(report_md, anchors) -> VerifyResult`. Tool-locked `[Read]`. |
| `grounding/render.py` | `render_citation(sentence, anchor_indices)` — the per-sentence single-index `[N]` renderer (no References section in prose). |
| `grounding/gate.py` | `no_uncited_claim_gate(report_md, anchors) -> list[Finding]` + `is_factual_claim`, `split_sentences`, `extract_citations`, `strip_sources_section`, `gate_blocks_ship`. The deterministic Stage-16 hard gate. |
| `tests/test_grounding/test_extract.py` | Span round-trip; fabricated-quote → `None`; fuzzy-locate. |
| `tests/test_grounding/test_anchors.py` | `quote_sha` 8-char; store upsert/get/set_verified; `build_from_claims`. |
| `tests/test_grounding/test_verifier.py` | Tier A SHA-mismatch → unsupported; Tier B entailed→supported / non-entailed→unsupported (NLI stub); Tier C judge fallback for neutral band (mocked LLM); contradicted→flag; disposition table. |
| `tests/test_grounding/test_gate.py` | Uncited claim FAILS; fully-cited PASSES; dangling-cite; unverified-cite; trivia exemption. |
| `tests/test_grounding/test_render.py` | `[N]` render per sentence. |
| `tests/test_grounding/conftest.py` | Shared fixtures: in-memory `AnchorStore`, NLI stub, mock `LLMProvider`, sample note bodies. |

**Reference reading (read-only, do NOT edit):**
- `ultimate-research/INTERFACES.md` — `claim_anchors` DDL, `Chunk`, `LLMProvider`/`ModelTier`, frozen constants (`nli-deberta-v3-base`, `quote_sha` 8-char).
- `ultimate-research/investigation/08_GROUNDING.md` — §1.1 schema, §1.2 DDL, §2.2 three tiers, §2.3 disposition table, §5.1 gate code.
- `hyperresearch/src/hyperresearch/core/hooks.py:2696-2716` — the `claims-<note-id>.json` shape with `quoted_support`.
- `hyperresearch/src/hyperresearch/core/db.py:151-158` — `get_connection` (WAL + `row_factory = sqlite3.Row`); `hyperresearch/src/hyperresearch/cli/lint.py:1126-1133` (R2 density, what R5 extends).

**Dependency note (Plan 01 seam):** `CitationVerifier` depends on `bad_research.llm.base.LLMProvider`, `LLMMessage`, `ModelTier` from Plan 01. Until Plan 01 lands, tests inject a `FakeLLMProvider` defined in `conftest.py` that satisfies the Protocol structurally (it has `name` and `complete(...)`). Task 0 pins a local Protocol stub so this plan is executable standalone; the real import is swapped in Task 12.

---

## Task 0: Package skeleton + LLM seam stub

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/__init__.py`
- Create: `ultimate-research/bad-research/src/bad_research/llm/__init__.py` (empty, namespace)
- Create: `ultimate-research/bad-research/src/bad_research/llm/base.py` (Protocol stub — Plan 01 will replace with the full impl; signature MUST match INTERFACES.md verbatim)
- Create: `ultimate-research/bad-research/tests/test_grounding/__init__.py`
- Create: `ultimate-research/bad-research/tests/test_grounding/conftest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_seam.py`:

```python
from __future__ import annotations

from bad_research.llm.base import LLMMessage, LLMProvider, LLMResponse


def test_llm_seam_protocol_shape(fake_llm):
    # fake_llm is a fixture satisfying the LLMProvider Protocol structurally.
    assert isinstance(fake_llm, LLMProvider)
    resp = fake_llm.complete([LLMMessage(role="user", content="hi")], tier="triage")
    assert isinstance(resp, LLMResponse)
    assert resp.text == "[]"  # fake returns empty JSON list by default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_seam.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.llm'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/llm/__init__.py`:

```python
"""LLM provider seam (Plan 01). Stub for cross-plan dependency."""
```

`src/bad_research/llm/base.py` (verbatim from INTERFACES.md §Seam signatures):

```python
"""LLMProvider seam — frozen signatures from INTERFACES.md. Plan 01 owns the
concrete AnthropicProvider; Plan 06 only depends on this Protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

ModelTier = Literal["triage", "work", "heavy"]  # → Haiku / Sonnet / Opus via config


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: ModelTier,
        tools: list[dict] | None = None,
        cache: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse: ...
```

`src/bad_research/grounding/__init__.py`:

```python
"""Grounding / no-hallucination layer (Plan 06).

Forward: DSS span extraction + claim_anchors. Backward: CitationVerifier
(byte-identity → local NLI → triage-LLM judge) + the deterministic Stage-16
no-uncited-claim gate.
"""
```

`tests/test_grounding/__init__.py`: empty file.

`tests/test_grounding/conftest.py`:

```python
from __future__ import annotations

import pytest

from bad_research.llm.base import LLMMessage, LLMResponse


class FakeLLMProvider:
    """Structural LLMProvider for tests. Returns a scripted JSON body per call.

    Set `.script` to a list of response-text strings (popped FIFO); when empty,
    returns "[]". Records every call in `.calls` so tests can assert batching.
    """

    name = "fake"

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: str,
        tools: list[dict] | None = None,
        cache: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tier": tier})
        text = self.script.pop(0) if self.script else "[]"
        return LLMResponse(text=text, model="fake-haiku")


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_seam.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/llm ultimate-research/bad-research/src/bad_research/grounding/__init__.py ultimate-research/bad-research/tests/test_grounding
git commit -m "feat(grounding): package skeleton + LLMProvider seam stub"
```

---

## Task 1: DSS span extraction — exact `find`

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/extract.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_extract.py`

Per dossier §1.1: the fetcher has the quote and the source text; computing `body.find(quoted_support)` → `(char_start, char_end)` is a deterministic post-step, **not an LLM call**.

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_extract.py`:

```python
from __future__ import annotations

from bad_research.grounding.extract import extract_spans

NOTE_BODY = (
    "# Source note\n\n"
    "The study found that latency dropped to 12.4 ms under load. "
    "A separate trial reported no regression.\n"
)


def test_exact_find_returns_span_that_round_trips():
    quote = "latency dropped to 12.4 ms under load"
    span = extract_spans("Latency fell to 12.4 ms.", quote, NOTE_BODY)
    assert span is not None
    start, end = span
    # The load-bearing invariant: slicing the body by the offsets reproduces the quote.
    assert NOTE_BODY[start:end] == quote
    assert end - start == len(quote)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.extract'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/extract.py`:

```python
"""DSS span extraction (Glean): turn a verbatim quoted_support into char offsets
inside the note body. Deterministic, $0 — no LLM. dossier 08 §1.1."""

from __future__ import annotations


def extract_spans(
    claim: str,
    quoted_support: str,
    note_body: str,
) -> tuple[int, int] | None:
    """Return (char_start, char_end) of quoted_support inside note_body.

    char_end is exclusive: note_body[char_start:char_end] == quoted_support on
    an exact match. Returns None when the quote cannot be located (caller drops
    the claim — a quote that isn't in the body is a hallucinated quote).
    """
    quote = quoted_support.strip()
    if not quote:
        return None
    idx = note_body.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_extract.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/extract.py ultimate-research/bad-research/tests/test_grounding/test_extract.py
git commit -m "feat(grounding): DSS span extraction via exact find"
```

---

## Task 2: Span extraction — fuzzy fallback + drop fabricated quotes

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/extract.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_extract.py`

Per dossier §1.1: if `body.find()` fails (lightly normalized), fall back to rapidfuzz partial-ratio ≥ 95 and store the matched span; if even that fails, **drop the claim**.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grounding/test_extract.py`:

```python
def test_fuzzy_fallback_locates_lightly_normalized_quote():
    # Body has a curly apostrophe / collapsed whitespace the extractor quoted plainly.
    body = "Researchers wrote: the model’s   accuracy reached 91% on the held-out set."
    quote = "the model's accuracy reached 91% on the held-out set"  # straight apostrophe, single spaces
    span = extract_spans("Accuracy hit 91%.", quote, body)
    assert span is not None
    start, end = span
    # Matched span is a real substring of the body covering the same evidence.
    assert "91%" in body[start:end]
    assert start >= 0 and end <= len(body)


def test_fabricated_quote_returns_none():
    body = "The report covered three regions and two time periods."
    quote = "revenue tripled to $4.2B in the fourth quarter"  # never appears
    assert extract_spans("Revenue tripled.", quote, body) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_extract.py -v`
Expected: FAIL — `test_fuzzy_fallback_locates_lightly_normalized_quote` fails (exact `find` returns `None`, current impl gives up).

- [ ] **Step 3: Write minimal implementation**

Replace the body of `extract_spans` in `src/bad_research/grounding/extract.py`:

```python
"""DSS span extraction (Glean): turn a verbatim quoted_support into char offsets
inside the note body. Deterministic, $0 — no LLM. dossier 08 §1.1."""

from __future__ import annotations

# rapidfuzz is the fuzzy-locate fallback for lightly-normalized quotes.
from rapidfuzz import fuzz

FUZZY_RATIO_FLOOR = 95.0  # dossier §1.1: partial-ratio >= 95 to accept a fuzzy locate


def extract_spans(
    claim: str,
    quoted_support: str,
    note_body: str,
) -> tuple[int, int] | None:
    """Return (char_start, char_end) of quoted_support inside note_body.

    1. Exact find (char_end exclusive; body[start:end] == quote).
    2. Fuzzy fallback: slide a window of len(quote) (+/- 20%) over the body,
       accept the best window with rapidfuzz partial-ratio >= 95.
    3. None when neither locates it — the caller drops the claim (a quote that
       isn't in the body is a hallucinated quote; dossier §1.1).
    """
    quote = quoted_support.strip()
    if not quote:
        return None

    idx = note_body.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))

    return _fuzzy_locate(quote, note_body)


def _fuzzy_locate(quote: str, body: str) -> tuple[int, int] | None:
    qlen = len(quote)
    if qlen == 0 or qlen > len(body):
        # Quote longer than the whole body: try whole-body ratio once.
        if qlen > len(body) and fuzz.partial_ratio(quote, body) >= FUZZY_RATIO_FLOOR:
            return (0, len(body))
        return None

    best_score = 0.0
    best_span: tuple[int, int] | None = None
    # Window between 80% and 120% of the quote length, stepped to keep it cheap.
    win_min = max(1, int(qlen * 0.8))
    win_max = min(len(body), int(qlen * 1.2) + 1)
    step = max(1, qlen // 8)
    for start in range(0, len(body) - win_min + 1, step):
        for win in (qlen, win_min, win_max):
            end = min(start + win, len(body))
            score = fuzz.partial_ratio(quote, body[start:end])
            if score > best_score:
                best_score = score
                best_span = (start, end)
        if best_score >= 100.0:
            break

    if best_span is not None and best_score >= FUZZY_RATIO_FLOOR:
        return best_span
    return None
```

Add `rapidfuzz>=3.0` to the package's `pyproject.toml` dependencies (note this in the commit; the engineer adds it to `[project].dependencies`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_extract.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/extract.py ultimate-research/bad-research/tests/test_grounding/test_extract.py ultimate-research/bad-research/pyproject.toml
git commit -m "feat(grounding): fuzzy span fallback (rapidfuzz>=95) + drop fabricated quotes"
```

---

## Task 3: `ClaimAnchor` dataclass + `quote_sha`

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/anchors.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_anchors.py`

`quote_sha = sha256(quote)[:8]` is the frozen byte-identity key (INTERFACES.md frozen constants; dossier §1.1).

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_anchors.py`:

```python
from __future__ import annotations

import hashlib

from bad_research.grounding.anchors import ClaimAnchor, quote_sha


def test_quote_sha_is_first_8_chars_of_sha256():
    q = "latency dropped to 12.4 ms under load"
    expected = hashlib.sha256(q.encode("utf-8")).hexdigest()[:8]
    assert quote_sha(q) == expected
    assert len(quote_sha(q)) == 8


def test_claim_anchor_anchor_id_defaults_to_quote_sha():
    a = ClaimAnchor(
        note_id="source-note-12",
        char_start=10,
        char_end=47,
        claim="Latency fell to 12.4 ms.",
        quoted_support="latency dropped to 12.4 ms under load",
    )
    assert a.anchor_id == quote_sha(a.quoted_support)
    assert a.verified == 0
    assert a.verify_score is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.anchors'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/anchors.py`:

```python
"""claim_anchors — the byte-identity citation-anchor store. dossier 08 §1.2;
schema verbatim from INTERFACES.md (anchor_id = quote_sha 8-char)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def quote_sha(quoted_support: str) -> str:
    """8-char SHA-256 of the verbatim quote — the byte-identity key (frozen)."""
    return hashlib.sha256(quoted_support.encode("utf-8")).hexdigest()[:8]


@dataclass
class ClaimAnchor:
    """One claim→span binding. anchor_id == quote_sha(quoted_support)."""

    note_id: str
    char_start: int
    char_end: int
    claim: str
    quoted_support: str
    verified: int = 0           # 0 = unchecked; 1 = passed the verifier (§2)
    verify_score: float | None = None
    anchor_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.anchor_id:
            self.anchor_id = quote_sha(self.quoted_support)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/anchors.py ultimate-research/bad-research/tests/test_grounding/test_anchors.py
git commit -m "feat(grounding): ClaimAnchor dataclass + 8-char quote_sha key"
```

---

## Task 4: `AnchorStore` — the `claim_anchors` SQLite table

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/anchors.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_anchors.py`

DDL verbatim from INTERFACES.md: `claim_anchors(anchor_id TEXT PK /*=quote_sha 8-char*/, note_id, char_start, char_end, claim, quoted_support, verified INT, verify_score REAL)`. The store opens its own connection (matches `db.py:151-158`: WAL + `row_factory = sqlite3.Row`) so tests run against `:memory:` without the full vault.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grounding/test_anchors.py`:

```python
import sqlite3

from bad_research.grounding.anchors import AnchorStore


def _store() -> AnchorStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    return store


def test_upsert_then_get_round_trips():
    store = _store()
    a = ClaimAnchor("n1", 10, 47, "Latency fell.", "latency dropped to 12.4 ms under load")
    store.upsert(a)
    got = store.get(a.anchor_id)
    assert got is not None
    assert got.note_id == "n1"
    assert got.char_start == 10 and got.char_end == 47
    assert got.quoted_support == a.quoted_support
    assert got.verified == 0


def test_upsert_is_idempotent_on_anchor_id():
    store = _store()
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    store.upsert(a)
    store.upsert(a)  # same quote_sha → no duplicate row
    rows = store.conn.execute("SELECT COUNT(*) AS c FROM claim_anchors").fetchone()
    assert rows["c"] == 1


def test_set_verified_persists_flag_and_score():
    store = _store()
    a = ClaimAnchor("n1", 0, 5, "C.", "abcde")
    store.upsert(a)
    store.set_verified(a.anchor_id, verified=1, score=0.82)
    got = store.get(a.anchor_id)
    assert got.verified == 1
    assert abs(got.verify_score - 0.82) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py -v`
Expected: FAIL with `ImportError: cannot import name 'AnchorStore'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/bad_research/grounding/anchors.py`:

```python
import sqlite3
from collections.abc import Iterable

CLAIM_ANCHORS_DDL = """
CREATE TABLE IF NOT EXISTS claim_anchors (
    anchor_id      TEXT PRIMARY KEY,   -- == quote_sha (8-char SHA-256 of quoted_support)
    note_id        TEXT NOT NULL,
    char_start     INTEGER NOT NULL,
    char_end       INTEGER NOT NULL,
    claim          TEXT NOT NULL,
    quoted_support TEXT NOT NULL,
    verified       INTEGER NOT NULL DEFAULT 0,
    verify_score   REAL
);
CREATE INDEX IF NOT EXISTS idx_claim_anchors_note ON claim_anchors(note_id);
"""


class AnchorStore:
    """Thin DAL over the claim_anchors table. Markdown/claims-*.json is truth;
    this table is a cache rebuilt by sync (dossier §1.2)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def init_schema(self) -> None:
        self.conn.executescript(CLAIM_ANCHORS_DDL)
        self.conn.commit()

    def upsert(self, anchor: ClaimAnchor) -> None:
        self.conn.execute(
            "INSERT INTO claim_anchors "
            "(anchor_id, note_id, char_start, char_end, claim, quoted_support, verified, verify_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(anchor_id) DO UPDATE SET "
            "  note_id=excluded.note_id, char_start=excluded.char_start, "
            "  char_end=excluded.char_end, claim=excluded.claim, "
            "  quoted_support=excluded.quoted_support",
            (
                anchor.anchor_id, anchor.note_id, anchor.char_start, anchor.char_end,
                anchor.claim, anchor.quoted_support, anchor.verified, anchor.verify_score,
            ),
        )
        self.conn.commit()

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
        )

    def all(self) -> Iterable[ClaimAnchor]:
        for row in self.conn.execute("SELECT * FROM claim_anchors"):
            yield ClaimAnchor(
                note_id=row["note_id"], char_start=row["char_start"], char_end=row["char_end"],
                claim=row["claim"], quoted_support=row["quoted_support"],
                verified=row["verified"], verify_score=row["verify_score"],
                anchor_id=row["anchor_id"],
            )

    def set_verified(self, anchor_id: str, *, verified: int, score: float | None) -> None:
        self.conn.execute(
            "UPDATE claim_anchors SET verified = ?, verify_score = ? WHERE anchor_id = ?",
            (verified, score, anchor_id),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/anchors.py ultimate-research/bad-research/tests/test_grounding/test_anchors.py
git commit -m "feat(grounding): AnchorStore — claim_anchors table (DDL verbatim from INTERFACES.md)"
```

---

## Task 5: `build_from_claims` — populate anchors from `claims-*.json`

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/anchors.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_anchors.py`

Per dossier Stage 3 "build claim_anchors": `sync` reads each `claims-<note-id>.json` (shape from `hooks.py:2696-2716` + the three added offset fields), calls `extract_spans` to locate `quoted_support` in the note body, and upserts an anchor. A claim whose quote can't be located is **dropped** (not stored).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grounding/test_anchors.py`:

```python
from bad_research.grounding.anchors import build_from_claims

NOTE_BODIES = {
    "source-note-12": (
        "Southeast Asian e-commerce GMV grew from $89B to $100B between 2023 and 2024, "
        "a 12.4% YoY expansion. Vietnam led the region."
    ),
}


def test_build_from_claims_upserts_located_drops_unlocatable():
    store = _store()
    claims = [
        {
            "claim": "SEA e-commerce GMV grew 12.4% YoY in 2024.",
            "quoted_support": "a 12.4% YoY expansion",
            "source_note_id": "source-note-12",
        },
        {
            "claim": "Revenue tripled to $4.2B.",  # quote not in any body → dropped
            "quoted_support": "revenue tripled to $4.2B in Q4",
            "source_note_id": "source-note-12",
        },
    ]
    n = build_from_claims(store, claims, NOTE_BODIES)
    assert n == 1  # one located, one dropped
    anchors = list(store.all())
    assert len(anchors) == 1
    a = anchors[0]
    # Round-trip: the stored offsets slice the body back to the quote.
    body = NOTE_BODIES[a.note_id]
    assert body[a.char_start:a.char_end] == a.quoted_support
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py::test_build_from_claims_upserts_located_drops_unlocatable -v`
Expected: FAIL with `ImportError: cannot import name 'build_from_claims'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/bad_research/grounding/anchors.py` (add `from .extract import extract_spans` near the top imports):

```python
from .extract import extract_spans


def build_from_claims(
    store: AnchorStore,
    claims: Iterable[dict],
    note_bodies: dict[str, str],
) -> int:
    """Materialize claim_anchors from claims-*.json dicts. Returns the count of
    anchors upserted. A claim whose quoted_support can't be located in its note
    body is DROPPED (dossier §1.1: an unlocatable quote is a hallucinated quote).
    """
    count = 0
    for c in claims:
        quote = (c.get("quoted_support") or "").strip()
        note_id = c.get("source_note_id") or ""
        claim_text = c.get("claim") or ""
        if not quote or not note_id:
            continue
        body = note_bodies.get(note_id)
        if body is None:
            continue
        span = extract_spans(claim_text, quote, body)
        if span is None:
            continue  # drop: hallucinated quote
        start, end = span
        store.upsert(ClaimAnchor(
            note_id=note_id, char_start=start, char_end=end,
            claim=claim_text, quoted_support=quote,
        ))
        count += 1
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_anchors.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/anchors.py ultimate-research/bad-research/tests/test_grounding/test_anchors.py
git commit -m "feat(grounding): build_from_claims — populate anchors, drop unlocatable quotes"
```

---

## Task 6: NLI model wrapper + deterministic stub

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/nli.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_nli.py`

Tier B uses `cross-encoder/nli-deberta-v3-base` (frozen constant). The real model is lazy-imported (heavy: torch + transformers); tests use a deterministic stub. Decision rule (dossier §2.2): `entailment ≥ 0.70` → PASS; `contradiction ≥ 0.50` → FLAG hard; else neutral.

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_nli.py`:

```python
from __future__ import annotations

from bad_research.grounding.nli import NLI_MODEL_NAME, NLILabel, classify_nli


def test_model_name_is_frozen_constant():
    assert NLI_MODEL_NAME == "nli-deberta-v3-base"


def test_classify_entailment_high():
    scores = {"entailment": 0.91, "neutral": 0.07, "contradiction": 0.02}
    assert classify_nli(scores) is NLILabel.ENTAILMENT


def test_classify_contradiction_flag():
    scores = {"entailment": 0.10, "neutral": 0.30, "contradiction": 0.60}
    assert classify_nli(scores) is NLILabel.CONTRADICTION


def test_classify_neutral_band():
    # No label clears its bar → neutral (the band that escalates to Tier C).
    scores = {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}
    assert classify_nli(scores) is NLILabel.NEUTRAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_nli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.nli'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/nli.py`:

```python
"""Tier-B NLI entailment check — cross-encoder/nli-deberta-v3-base (frozen).
Local, $0, CPU-fine. dossier 08 §2.2 option 1."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

# INTERFACES.md frozen constant (the bare HF repo name resolves to
# cross-encoder/nli-deberta-v3-base when loaded).
NLI_MODEL_NAME = "nli-deberta-v3-base"

ENTAILMENT_PASS = 0.70      # dossier §2.2: entailment >= 0.70 → PASS
CONTRADICTION_FLAG = 0.50   # dossier §2.2: contradiction >= 0.50 → FLAG hard


class NLILabel(str, Enum):
    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"
    CONTRADICTION = "contradiction"


def classify_nli(scores: dict[str, float]) -> NLILabel:
    """Map a {entailment, neutral, contradiction} softmax to a decision.

    Contradiction is checked before entailment so a quote that says the OPPOSITE
    is never silently passed (dossier §2.2)."""
    if scores.get("contradiction", 0.0) >= CONTRADICTION_FLAG:
        return NLILabel.CONTRADICTION
    if scores.get("entailment", 0.0) >= ENTAILMENT_PASS:
        return NLILabel.ENTAILMENT
    return NLILabel.NEUTRAL


class NLIModel(Protocol):
    """premise = quoted_support, hypothesis = report sentence → softmax dict."""

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]: ...


class CrossEncoderNLI:
    """Lazy wrapper over the real model. Imported only when actually used so the
    grounding package has no hard torch/transformers dependency at import time."""

    def __init__(self, model_name: str = NLI_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure(self) -> None:
        if self._model is None:
            from sentence_transformers import CrossEncoder  # heavy; lazy

            # The cross-encoder/ prefix is the canonical HF path.
            repo = self.model_name
            if "/" not in repo:
                repo = f"cross-encoder/{repo}"
            self._model = CrossEncoder(repo)

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]:
        self._ensure()
        import numpy as np

        logits = self._model.predict([(premise, hypothesis)])[0]
        # cross-encoder/nli-deberta-v3-base label order: [contradiction, entailment, neutral]
        exp = np.exp(logits - np.max(logits))
        probs = exp / exp.sum()
        return {
            "contradiction": float(probs[0]),
            "entailment": float(probs[1]),
            "neutral": float(probs[2]),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_nli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/nli.py ultimate-research/bad-research/tests/test_grounding/test_nli.py
git commit -m "feat(grounding): NLI Tier-B wrapper (nli-deberta-v3-base) + decision rule"
```

---

## Task 7: `[N]` citation renderer

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/render.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_render.py`

Per SPEC §9 / dossier §1.2: per-sentence single-index `[N]` citation render (Perplexity); no References section in prose.

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_render.py`:

```python
from __future__ import annotations

from bad_research.grounding.render import extract_citations, render_citation


def test_render_appends_single_index_per_sentence():
    out = render_citation("Latency fell to 12.4 ms.", [3])
    assert out == "Latency fell to 12.4 ms. [3]"


def test_render_multiple_indices_collapse_in_order():
    out = render_citation("Two trials agreed on the 91% figure.", [2, 7])
    assert out == "Two trials agreed on the 91% figure. [2] [7]"


def test_render_no_indices_returns_sentence_unchanged():
    assert render_citation("This report covers three regions.", []) == "This report covers three regions."


def test_extract_citations_finds_bracket_and_wikilink_tokens():
    sent = "Growth was 12.4% [4] per the regional digest [[source-note-12]]."
    assert extract_citations(sent) == ["4", "source-note-12"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.render'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/render.py`:

```python
"""Per-sentence single-index [N] citation render (Perplexity; SPEC §9).
No References section in prose — sources live off-band (the anchor map)."""

from __future__ import annotations

import re

# [4] numeric indices, and [[note-id]] wiki-links — both are citation tokens.
_NUMERIC_CITE = re.compile(r"\[(\d+)\]")
_WIKILINK_CITE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def render_citation(sentence: str, anchor_indices: list[int]) -> str:
    """Append ` [N]` per index, in order, after the sentence's terminal text.

    A sentence with no indices is returned unchanged (background/transition
    sentences carry no [N] — dossier §1.3)."""
    base = sentence.rstrip()
    if not anchor_indices:
        return base
    tail = " ".join(f"[{i}]" for i in anchor_indices)
    return f"{base} {tail}"


def extract_citations(sentence: str) -> list[str]:
    """Return the citation tokens in/adjacent to a sentence: numeric [N] indices
    (as strings) and [[note-id]] wiki-link targets (pipe display stripped)."""
    out: list[str] = []
    for m in re.finditer(r"\[(\d+)\]|\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", sentence):
        out.append(m.group(1) if m.group(1) is not None else m.group(2).strip())
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_render.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/render.py ultimate-research/bad-research/tests/test_grounding/test_render.py
git commit -m "feat(grounding): per-sentence [N] citation renderer + citation extractor"
```

---

## Task 8: `VerifyVerdict` + Tier A byte-identity check

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/verifier.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_verifier.py`

Tier A (dossier §2.2): confirm the anchor's `quoted_support` still appears at `[char_start:char_end]` of the live note body AND `quote_sha` matches. Fail → the quote isn't in the source → **unsupported** (drop).

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_verifier.py`:

```python
from __future__ import annotations

from bad_research.grounding.anchors import ClaimAnchor
from bad_research.grounding.verifier import VerifyVerdict, tier_a_byte_identity


def test_tier_a_passes_when_quote_matches_offsets_and_sha():
    body = "Latency dropped to 12.4 ms under load in the benchmark."
    quote = "Latency dropped to 12.4 ms under load"
    start = body.find(quote)
    anchor = ClaimAnchor("n1", start, start + len(quote), "Latency fell.", quote)
    ok = tier_a_byte_identity(anchor, body)
    assert ok is True


def test_tier_a_fails_on_sha_mismatch_fabricated_quote():
    # Anchor claims a quote that is NOT at those offsets in the body → fabricated.
    body = "The benchmark reported no latency regression at all."
    anchor = ClaimAnchor("n1", 0, 30, "Latency fell.", "Latency dropped to 12.4 ms under load")
    ok = tier_a_byte_identity(anchor, body)
    assert ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.verifier'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/verifier.py`:

```python
"""CitationVerifier — the Stage-11.5 re-grounding pass. Cheapest-first:
Tier A byte-identity ($0) → Tier B local NLI ($0) → Tier C triage-LLM judge
(only the NLI-neutral band, batched). Tool-locked [Read]. dossier 08 §2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .anchors import ClaimAnchor, quote_sha


class VerifyVerdict(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


def tier_a_byte_identity(anchor: ClaimAnchor, note_body: str) -> bool:
    """True iff anchor.quoted_support still sits at [char_start:char_end] of the
    live body AND its SHA matches anchor_id. Catches anchor drift + fabricated
    quotes at $0 (dossier §2.2 Tier A)."""
    if quote_sha(anchor.quoted_support) != anchor.anchor_id:
        return False
    sliced = note_body[anchor.char_start:anchor.char_end]
    return sliced == anchor.quoted_support
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/verifier.py ultimate-research/bad-research/tests/test_grounding/test_verifier.py
git commit -m "feat(grounding): VerifyVerdict + Tier-A byte-identity (kills fabricated quotes)"
```

---

## Task 9: Tier C — triage-LLM judge batcher

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/verifier.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_verifier.py`

Tier C (dossier §2.2 option 2): a single `triage`-tier call batched ~20 (CLAIM, QUOTE) pairs per call, returning `[{id, verdict, score, reason}]`. Verbatim judge prompt from the dossier. The LLM is mocked via `FakeLLMProvider`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grounding/test_verifier.py`:

```python
import json

from bad_research.grounding.verifier import JUDGE_BATCH_SIZE, tier_c_judge


def test_tier_c_judge_parses_batched_json(fake_llm):
    fake_llm.script = [json.dumps([
        {"id": 0, "verdict": "supported", "score": 0.9, "reason": "exact"},
        {"id": 1, "verdict": "unsupported", "score": 0.2, "reason": "scope add"},
    ])]
    pairs = [
        ("SEA GMV grew 12.4%.", "a 12.4% YoY expansion"),
        ("Vietnam led at 64%.", "Vietnam was mentioned"),
    ]
    results = tier_c_judge(pairs, fake_llm)
    assert results[0] == (VerifyVerdict.SUPPORTED, 0.9)
    assert results[1] == (VerifyVerdict.UNSUPPORTED, 0.2)
    # Used exactly one batched triage call for the two pairs.
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["tier"] == "triage"


def test_tier_c_batches_in_chunks_of_20(fake_llm):
    # 25 pairs → 2 calls (20 + 5). Script enough empty arrays to satisfy parse.
    fake_llm.script = [json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(20)]),
                       json.dumps([{"id": i, "verdict": "supported", "score": 0.8} for i in range(5)])]
    pairs = [(f"claim {i}", f"quote {i}") for i in range(25)]
    results = tier_c_judge(pairs, fake_llm)
    assert len(results) == 25
    assert len(fake_llm.calls) == 2
    assert JUDGE_BATCH_SIZE == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: FAIL with `ImportError: cannot import name 'tier_c_judge'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/bad_research/grounding/verifier.py` (add `import json` and the LLM seam imports at top):

```python
import json

from bad_research.llm.base import LLMMessage, LLMProvider

JUDGE_BATCH_SIZE = 20  # dossier §2.2: batch ~20 (claim, quote) pairs per call

# Verbatim CitationVerifier judge prompt (dossier 08 §2.2 option 2).
JUDGE_SYSTEM = (
    "You are the CitationVerifier. For each numbered (CLAIM, QUOTE) pair, decide if the\n"
    "QUOTE supports the CLAIM. Output JSON only: [{id, verdict, score, reason}].\n"
    "- verdict in {supported, partial, unsupported, contradicted}\n"
    "- score in 0.0-1.0 (confidence the quote supports the claim AS WRITTEN)\n"
    "- A QUOTE \"supports\" a CLAIM only if a careful reader, seeing ONLY the quote,\n"
    "  would agree the claim follows. Numbers must match exactly. Do NOT use outside\n"
    "  knowledge. If the claim adds a number/entity/scope absent from the quote ->\n"
    "  partial or unsupported. If the quote states the opposite -> contradicted."
)


def _parse_judge_json(text: str, n: int) -> list[tuple[VerifyVerdict, float]]:
    """Parse the judge's JSON array into per-id (verdict, score). Robust to the
    model wrapping the array in prose: extract the first [...] block."""
    start, end = text.find("["), text.rfind("]")
    blob = text[start:end + 1] if start != -1 and end != -1 else "[]"
    try:
        rows = json.loads(blob)
    except json.JSONDecodeError:
        rows = []
    out: list[tuple[VerifyVerdict, float]] = [(VerifyVerdict.UNSUPPORTED, 0.0)] * n
    for r in rows:
        if not isinstance(r, dict):
            continue
        i = r.get("id")
        if not isinstance(i, int) or not (0 <= i < n):
            continue
        try:
            verdict = VerifyVerdict(r.get("verdict", "unsupported"))
        except ValueError:
            verdict = VerifyVerdict.UNSUPPORTED
        score = float(r.get("score", 0.0))
        out[i] = (verdict, score)
    return out


def tier_c_judge(
    pairs: list[tuple[str, str]],
    llm: LLMProvider,
) -> list[tuple[VerifyVerdict, float]]:
    """Run the triage-tier LLM judge over (claim, quote) pairs, batched
    JUDGE_BATCH_SIZE per call. Returns per-pair (verdict, score)."""
    results: list[tuple[VerifyVerdict, float]] = []
    for batch_start in range(0, len(pairs), JUDGE_BATCH_SIZE):
        batch = pairs[batch_start:batch_start + JUDGE_BATCH_SIZE]
        payload = [
            {"id": idx, "claim": claim, "quote": quote}
            for idx, (claim, quote) in enumerate(batch)
        ]
        user = "PAIRS:\n" + json.dumps(payload, ensure_ascii=False)
        resp = llm.complete(
            [LLMMessage(role="system", content=JUDGE_SYSTEM),
             LLMMessage(role="user", content=user)],
            tier="triage",
            max_tokens=2048,
            temperature=0.0,
        )
        results.extend(_parse_judge_json(resp.text, len(batch)))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/verifier.py ultimate-research/bad-research/tests/test_grounding/test_verifier.py
git commit -m "feat(grounding): Tier-C triage-LLM judge batcher (~20/call, verbatim prompt)"
```

---

## Task 10: `CitationVerifier.verify` — full 3-tier orchestration + dispositions

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/verifier.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_verifier.py`

`verify(report_md, anchors, note_bodies)` per cited sentence: resolve anchor → Tier A (fail → unsupported) → Tier B NLI (entailment→supported / contradiction→contradicted / neutral→Tier C) → Tier C judge for the neutral band only. Disposition table (dossier §2.3) sets `claim_anchors.verified` + `verify_score`. The NLI model and LLM are injected (stubs in tests).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grounding/test_verifier.py`:

```python
from bad_research.grounding.anchors import AnchorStore
from bad_research.grounding.nli import NLILabel
from bad_research.grounding.verifier import CitationVerifier


class StubNLI:
    """Deterministic NLI: maps a quote substring → fixed softmax."""

    def __init__(self, table):
        self.table = table  # dict[str, dict[str,float]]

    def predict(self, premise, hypothesis):
        for key, scores in self.table.items():
            if key in premise:
                return scores
        return {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}


def _store_with(anchors):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_verify_entailed_claim_supported_non_entailed_unsupported(fake_llm):
    body_a = "Latency dropped to 12.4 ms under load."
    body_b = "The author also enjoys hiking on weekends."
    qa = "Latency dropped to 12.4 ms under load"
    qb = "The author also enjoys hiking on weekends"
    aa = ClaimAnchor("nA", 0, len(qa), "Latency fell to 12.4 ms.", qa)
    ab = ClaimAnchor("nB", 0, len(qb), "Latency fell to 5 ms.", qb)
    store = _store_with([aa, ab])
    nli = StubNLI({
        qa: {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01},
        qb: {"entailment": 0.02, "neutral": 0.05, "contradiction": 0.93},
    })
    report = (
        f"Latency fell to 12.4 ms. [[{aa.anchor_id}]]\n"
        f"Latency fell to 5 ms. [[{ab.anchor_id}]]\n"
    )
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body_a, "nB": body_b})
    by_anchor = {r.anchor_id: r for r in result.findings}
    assert by_anchor[aa.anchor_id].verdict is VerifyVerdict.SUPPORTED
    assert by_anchor[ab.anchor_id].verdict is VerifyVerdict.CONTRADICTED
    # Disposition persisted: supported anchor flagged verified=1.
    assert store.get(aa.anchor_id).verified == 1
    assert store.get(ab.anchor_id).verified == 0


def test_verify_fabricated_quote_tier_a_fails_unsupported(fake_llm):
    # Offsets point at body text that is NOT the quote → Tier A fails → unsupported.
    body = "No latency regression was observed in any trial."
    fabricated = "Latency dropped to 12.4 ms under load"
    a = ClaimAnchor("nA", 0, 30, "Latency fell.", fabricated)
    store = _store_with([a])
    nli = StubNLI({})  # never consulted — Tier A short-circuits
    report = f"Latency fell. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.UNSUPPORTED
    assert len(fake_llm.calls) == 0  # no LLM spent on a fabricated quote


def test_verify_neutral_band_escalates_to_tier_c(fake_llm):
    import json
    body = "Adoption grew over the period across several markets."
    quote = "Adoption grew over the period across several markets"
    a = ClaimAnchor("nA", 0, len(quote), "Adoption grew 12.4% in SEA.", quote)
    store = _store_with([a])
    nli = StubNLI({quote: {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}})  # neutral
    fake_llm.script = [json.dumps([{"id": 0, "verdict": "partial", "score": 0.5}])]
    report = f"Adoption grew 12.4% in SEA. [[{a.anchor_id}]]\n"
    verifier = CitationVerifier(nli=nli, llm=fake_llm)
    result = verifier.verify(report, store, {"nA": body})
    assert result.findings[0].verdict is VerifyVerdict.PARTIAL
    assert len(fake_llm.calls) == 1  # only the neutral band paid for an LLM call
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: FAIL with `ImportError: cannot import name 'CitationVerifier'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/bad_research/grounding/verifier.py` (add `from .nli import NLILabel, NLIModel, classify_nli` and `from .render import extract_citations` at top; `import re`):

```python
import re

from .nli import NLILabel, NLIModel, classify_nli
from .render import extract_citations

# soft/hard score bands for the disposition table (dossier §2.3).
PARTIAL_LOW, SUPPORTED_FLOOR = 0.40, 0.70


@dataclass
class CitationFinding:
    anchor_id: str
    sentence: str
    verdict: VerifyVerdict
    score: float


@dataclass
class VerifyResult:
    findings: list[CitationFinding]


def _split_sentences(text: str) -> list[str]:
    # Shared with the gate; kept simple + deterministic. Split on terminal
    # punctuation followed by whitespace/newline. Newline-delimited report lines
    # are each at least one sentence.
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if piece:
                parts.append(piece)
    return parts


class CitationVerifier:
    """Stage-11.5 re-grounding pass. Tool-locked [Read]: reads the report +
    anchors + note bodies; writes only the findings + the verified flag (via the
    AnchorStore DAL) — it does NOT edit the report. dossier §2.3."""

    def __init__(self, *, nli: NLIModel, llm: LLMProvider) -> None:
        self.nli = nli
        self.llm = llm

    def verify(self, report_md, store, note_bodies: dict[str, str]) -> VerifyResult:
        # Pass 1: per cited sentence, run Tier A then Tier B; collect the
        # NLI-neutral band for a single batched Tier-C call.
        pending: list[tuple[CitationFinding, str, str]] = []  # (finding-stub, claim, quote)
        findings: list[CitationFinding] = []

        for sent in _split_sentences(report_md):
            for token in extract_citations(sent):
                anchor = store.get(token)
                if anchor is None:
                    continue  # dangling cite — the gate (Task 11) handles it
                body = note_bodies.get(anchor.note_id, "")
                # Tier A — byte-identity ($0).
                if not tier_a_byte_identity(anchor, body):
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.UNSUPPORTED, 0.0))
                    continue
                # Tier B — local NLI ($0). premise=quote, hypothesis=claim sentence.
                scores = self.nli.predict(anchor.quoted_support, anchor.claim)
                label = classify_nli(scores)
                if label is NLILabel.ENTAILMENT:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.SUPPORTED, scores["entailment"]))
                elif label is NLILabel.CONTRADICTION:
                    findings.append(CitationFinding(anchor.anchor_id, sent, VerifyVerdict.CONTRADICTED, scores["contradiction"]))
                else:
                    stub = CitationFinding(anchor.anchor_id, sent, VerifyVerdict.UNSUPPORTED, 0.0)
                    pending.append((stub, anchor.claim, anchor.quoted_support))

        # Pass 2: Tier C — judge the neutral band only, batched.
        if pending:
            pairs = [(claim, quote) for _, claim, quote in pending]
            judged = tier_c_judge(pairs, self.llm)
            for (stub, _, _), (verdict, score) in zip(pending, judged, strict=True):
                stub.verdict = verdict
                stub.score = score
                findings.append(stub)

        # Persist dispositions (dossier §2.3): supported→verified=1; partial→keep
        # but unverified (hedge); unsupported→0; contradicted→0 (flag).
        for f in findings:
            if f.verdict is VerifyVerdict.SUPPORTED:
                store.set_verified(f.anchor_id, verified=1, score=f.score)
            else:
                store.set_verified(f.anchor_id, verified=0, score=f.score)

        return VerifyResult(findings=findings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_verifier.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/verifier.py ultimate-research/bad-research/tests/test_grounding/test_verifier.py
git commit -m "feat(grounding): CitationVerifier.verify — 3-tier cascade + disposition persistence"
```

---

## Task 11: The deterministic Stage-16 no-uncited-claim gate

**Files:**
- Create: `ultimate-research/bad-research/src/bad_research/grounding/gate.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_gate.py`

Per dossier §5.1: a pure string + table gate (`$0`, no LLM) run last before ship. Fails if any **non-trivial factual** sentence lacks a verifiable, verified citation. `is_factual_claim` is the trivia filter (number / named entity / comparative / causal-temporal; exempt transitions, definitions, questions, meta-sentences). Three failure modes: `uncited-claim` (critical), `dangling-cite` (critical), `unverified-cite` (major). Any open `critical` blocks ship.

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_gate.py`:

```python
from __future__ import annotations

import sqlite3

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import (
    Finding,
    gate_blocks_ship,
    is_factual_claim,
    no_uncited_claim_gate,
)


def _store_with(anchors):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_is_factual_claim_filters_trivia():
    assert is_factual_claim("Latency dropped to 12.4 ms under load.") is True   # number
    assert is_factual_claim("Vietnam led Southeast Asia in penetration.") is True  # named entity + superlative
    assert is_factual_claim("This report covers three regions.") is False       # meta-sentence
    assert is_factual_claim("What drives adoption?") is False                   # question
    assert is_factual_claim("In general, markets vary.") is False               # hedge-frame opener


def test_gate_fails_report_with_uncited_factual_claim():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024.\n"  # hard number, no [N]
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "uncited-claim" and f.severity == "critical" for f in findings)
    assert gate_blocks_ship(findings) is True


def test_gate_passes_fully_cited_verified_report():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 1
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert findings == []
    assert gate_blocks_ship(findings) is False


def test_gate_flags_dangling_cite():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024. [[no-such-anchor]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "dangling-cite" and f.severity == "critical" for f in findings)


def test_gate_flags_unverified_cite():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 0  # resolves but verifier never passed it
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "unverified-cite" and f.severity == "major" for f in findings)
    # major alone does not block ship.
    assert gate_blocks_ship(findings) is False


def test_gate_ignores_sources_section():
    store = _store_with([])
    report = (
        "This report covers three regions.\n"
        "## Sources\n"
        "1. https://example.com  Some uncited claim with a number 42 here.\n"
    )
    findings = no_uncited_claim_gate(report, store)
    assert findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.grounding.gate'`

- [ ] **Step 3: Write minimal implementation**

`src/bad_research/grounding/gate.py`:

```python
"""Stage-16 deterministic no-uncited-claim gate. Pure string + table, $0, no LLM.
Hard pass/fail: any non-trivial factual sentence that lacks a verifiable, verified
citation blocks ship. Extends hyperresearch R2 density (hooks.py:1126). dossier §5."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .anchors import AnchorStore
from .render import extract_citations

# Hedge-frame openers that exempt a sentence (dossier §5.1 allowlist).
_HEDGE_OPENERS = ("in general,", "broadly,", "generally,", "overall,")
# Meta / framing sentence stems that carry no [N].
_META_STEMS = ("this report", "this section", "this analysis", "we cover", "the following")
_NAMED_ENTITY = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")
_NUMBER = re.compile(r"\d")
_COMPARATIVE = re.compile(
    r"\b(more|less|fewer|greater|higher|lower|larger|smaller|most|least|best|worst|"
    r"led|leading|highest|lowest|than|fastest|slowest)\b", re.IGNORECASE)
_CAUSAL_TEMPORAL = re.compile(
    r"\b(because|therefore|caused|causes|due to|results? in|since|after|before|"
    r"led to|drove|grew|fell|rose|declined|increased|decreased)\b", re.IGNORECASE)


@dataclass
class Finding:
    failure_mode: str   # uncited-claim | dangling-cite | unverified-cite
    severity: str       # critical | major | minor
    location: str       # the offending sentence
    recommendation: str


def strip_sources_section(report_md: str) -> str:
    """Drop everything from a `## Sources` (or `# References`) heading onward —
    the gate only judges the prose body (matches R2's exclusion)."""
    lines = report_md.splitlines()
    out: list[str] = []
    for line in lines:
        if re.match(r"^\s*#{1,6}\s+(sources|references)\b", line, re.IGNORECASE):
            break
        out.append(line)
    return "\n".join(out)


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if piece:
                parts.append(piece)
    return parts


def is_factual_claim(sentence: str) -> bool:
    """A non-trivial factual claim: has a number, named entity, comparative/
    superlative, or causal/temporal assertion — and is NOT a question, a
    meta-sentence, or a hedge-frame opener (dossier §5.1)."""
    s = sentence.strip()
    low = s.lower()
    if s.endswith("?"):
        return False
    if any(low.startswith(o) for o in _HEDGE_OPENERS):
        return False
    if any(low.startswith(m) for m in _META_STEMS):
        return False
    # Strip citation tokens before scanning for entities (so [[note-id]] isn't an entity).
    bare = re.sub(r"\[\[[^\]]+\]\]|\[\d+\]", "", s)
    if _NUMBER.search(bare):
        return True
    if _COMPARATIVE.search(bare):
        return True
    if _CAUSAL_TEMPORAL.search(bare):
        return True
    # Named entity that isn't merely the sentence-initial capital.
    ents = [m.group(0) for m in _NAMED_ENTITY.finditer(bare)]
    non_initial = [e for e in ents if not bare.lstrip().startswith(e)]
    return len(non_initial) >= 1


def no_uncited_claim_gate(report_md: str, anchors: AnchorStore) -> list[Finding]:
    findings: list[Finding] = []
    body = strip_sources_section(report_md)
    for sent in split_sentences(body):
        if not is_factual_claim(sent):
            continue
        cites = extract_citations(sent)
        if not cites:
            findings.append(Finding(
                "uncited-claim", "critical", sent,
                "Non-trivial factual sentence carries no citation. Add a vault cite or hedge/cut."))
            continue
        for c in cites:
            anchor = anchors.get(c)
            if anchor is None:
                findings.append(Finding(
                    "dangling-cite", "critical", sent,
                    f"Citation {c} resolves to no claim_anchor — remove or repoint."))
            elif anchor.verified != 1:
                findings.append(Finding(
                    "unverified-cite", "major", sent,
                    f"Citation {c} was not confirmed by the CitationVerifier — re-run Tier B or hedge."))
    return findings


def gate_blocks_ship(findings: list[Finding]) -> bool:
    """A run does not ship with any open `critical` finding (dossier §5.2)."""
    return any(f.severity == "critical" for f in findings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_gate.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/gate.py ultimate-research/bad-research/tests/test_grounding/test_gate.py
git commit -m "feat(grounding): deterministic Stage-16 no-uncited-claim gate ($0 hard pass/fail)"
```

---

## Task 12: Public API exports + full-suite green

**Files:**
- Modify: `ultimate-research/bad-research/src/bad_research/grounding/__init__.py`
- Test: `ultimate-research/bad-research/tests/test_grounding/test_public_api.py`

Lock the public surface the rest of the pipeline imports (Stage 11.5 + Stage 16 wiring in Plan 08, and `sync`'s anchor rebuild).

- [ ] **Step 1: Write the failing test**

`tests/test_grounding/test_public_api.py`:

```python
from __future__ import annotations

import bad_research.grounding as g


def test_public_api_surface():
    for name in (
        "extract_spans", "ClaimAnchor", "quote_sha", "AnchorStore", "build_from_claims",
        "CitationVerifier", "VerifyVerdict", "VerifyResult", "CitationFinding",
        "no_uncited_claim_gate", "Finding", "gate_blocks_ship",
        "render_citation", "extract_citations", "NLI_MODEL_NAME",
    ):
        assert hasattr(g, name), f"missing public export: {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/test_public_api.py -v`
Expected: FAIL with `AssertionError: missing public export: extract_spans`

- [ ] **Step 3: Write minimal implementation**

Replace `src/bad_research/grounding/__init__.py`:

```python
"""Grounding / no-hallucination layer (Plan 06).

Forward: DSS span extraction + claim_anchors. Backward: CitationVerifier
(byte-identity → local NLI → triage-LLM judge) + the deterministic Stage-16
no-uncited-claim gate.
"""

from .anchors import AnchorStore, ClaimAnchor, build_from_claims, quote_sha
from .extract import extract_spans
from .gate import Finding, gate_blocks_ship, is_factual_claim, no_uncited_claim_gate
from .nli import NLI_MODEL_NAME, CrossEncoderNLI, NLILabel, classify_nli
from .render import extract_citations, render_citation
from .verifier import (
    CitationFinding,
    CitationVerifier,
    VerifyResult,
    VerifyVerdict,
    tier_a_byte_identity,
    tier_c_judge,
)

__all__ = [
    "AnchorStore", "ClaimAnchor", "build_from_claims", "quote_sha",
    "extract_spans",
    "Finding", "gate_blocks_ship", "is_factual_claim", "no_uncited_claim_gate",
    "NLI_MODEL_NAME", "CrossEncoderNLI", "NLILabel", "classify_nli",
    "extract_citations", "render_citation",
    "CitationFinding", "CitationVerifier", "VerifyResult", "VerifyVerdict",
    "tier_a_byte_identity", "tier_c_judge",
]
```

- [ ] **Step 4: Run the FULL grounding suite to verify everything passes together**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/ -v`
Expected: PASS — all tests green (test_seam 1, test_extract 4, test_anchors 6, test_nli 4, test_render 4, test_verifier 7, test_gate 6, test_public_api 1 = 33 passed)

- [ ] **Step 5: Commit**

```bash
git add ultimate-research/bad-research/src/bad_research/grounding/__init__.py ultimate-research/bad-research/tests/test_grounding/test_public_api.py
git commit -m "feat(grounding): lock public API surface; full grounding suite green"
```

---

## Task 13: Wiring documentation — Stage 11.5 + Stage 16 hooks (no code, contract note)

**Files:**
- Modify: `ultimate-research/INTERFACES.md` (add the grounding public-API block under a new `## Grounding API (Plan 06)` section so Plans 02/07/08 import the frozen names)

This is a documentation task (no test) — it records the cross-plan contract the orchestrator skills (Plan 08) and `sync` (Plan 02) consume. The verifier runs **after synthesize (Stage 11), before critics (Stage 12)**; the gate runs **at Stage 16, after polish**, and `gate_blocks_ship` is the hard ship-block.

- [ ] **Step 1: Append the contract block to `ultimate-research/INTERFACES.md`**

Add at the end of the file:

```markdown
## Grounding API (Plan 06 — frozen)

```python
# grounding/__init__.py
def extract_spans(claim: str, quoted_support: str, note_body: str) -> tuple[int, int] | None: ...
def quote_sha(quoted_support: str) -> str: ...   # sha256(quote)[:8]

@dataclass
class ClaimAnchor:
    note_id: str; char_start: int; char_end: int; claim: str; quoted_support: str
    verified: int = 0; verify_score: float | None = None; anchor_id: str = ""  # == quote_sha

class AnchorStore:   # claim_anchors table DAL (DDL per INTERFACES vault-schema section)
    def __init__(self, conn): ...
    def init_schema(self) -> None: ...
    def upsert(self, a: ClaimAnchor) -> None: ...
    def get(self, anchor_id: str) -> ClaimAnchor | None: ...
    def all(self) -> Iterable[ClaimAnchor]: ...
    def set_verified(self, anchor_id, *, verified: int, score: float | None) -> None: ...
def build_from_claims(store, claims: Iterable[dict], note_bodies: dict[str,str]) -> int: ...

class VerifyVerdict(str, Enum): SUPPORTED; PARTIAL; UNSUPPORTED; CONTRADICTED
@dataclass
class CitationFinding: anchor_id; sentence; verdict: VerifyVerdict; score: float
@dataclass
class VerifyResult: findings: list[CitationFinding]
class CitationVerifier:                 # Stage 11.5, tool-locked [Read]
    def __init__(self, *, nli, llm): ...  # nli: NLIModel; llm: LLMProvider (triage tier)
    def verify(self, report_md, store: AnchorStore, note_bodies: dict[str,str]) -> VerifyResult: ...

@dataclass
class Finding: failure_mode; severity; location; recommendation
def no_uncited_claim_gate(report_md: str, anchors: AnchorStore) -> list[Finding]: ...   # Stage 16, $0
def gate_blocks_ship(findings: list[Finding]) -> bool: ...   # any critical → True (block ship)
def render_citation(sentence: str, anchor_indices: list[int]) -> str: ...
```

Pipeline position: verifier after Stage 11 synthesize, before Stage 12 critics; gate at Stage 16 after polish (hard ship-block). NLI model: `nli-deberta-v3-base` (frozen). LLM judge: `triage` tier, batched 20/call.
```

- [ ] **Step 2: Verify the file is valid markdown and the suite still green**

Run: `cd ultimate-research/bad-research && python -m pytest tests/test_grounding/ -q`
Expected: PASS (33 passed)

- [ ] **Step 3: Commit**

```bash
git add ultimate-research/INTERFACES.md
git commit -m "docs(interfaces): freeze the grounding public API (Plan 06)"
```

---

## Self-Review

**Spec coverage (SPEC §9 + dossier 08):**
- Forward binding at fetch (char-offset spans) → Task 1/2 (`extract_spans`) + Task 5 (`build_from_claims`). ✓
- `claim_anchors` table, `quote_sha=sha256(quote)[:8]` → Task 3/4, DDL verbatim from INTERFACES.md. ✓
- 3-tier CitationVerifier: A byte-identity ($0) → B NLI `nli-deberta-v3-base` ($0) → C triage-LLM judge batched ~20/call for neutral band only → Task 8/9/10. ✓
- Dispositions supported→keep(verified=1) / partial→hedge / unsupported→drop / contradicted→flag → Task 10 + disposition persistence. ✓ (contradiction-graph back-reference is a Plan 08 wiring concern — noted, the verdict surfaces `CONTRADICTED` for it to consume.)
- Per-sentence `[N]` renderer → Task 7. ✓
- Deterministic Stage-16 gate ($0, fail-ship on uncited non-trivial claim) → Task 11 (`no_uncited_claim_gate` + `gate_blocks_ship`). ✓
- Tool-locked `[Read]` → documented on `CitationVerifier` (writes only via the AnchorStore DAL + findings, never edits the report). ✓

**Placeholder scan:** No TBD/TODO; every code step is complete and runnable.

**Type consistency:** `ClaimAnchor`, `AnchorStore`, `VerifyVerdict`, `CitationFinding`, `VerifyResult`, `Finding`, `NLILabel` are defined once and reused with identical signatures across tasks and in the INTERFACES export. `quote_sha` 8-char and `nli-deberta-v3-base` match the frozen constants. The `LLMProvider`/`ModelTier`/`LLMMessage`/`LLMResponse` stub (Task 0) matches INTERFACES.md verbatim so Plan 01's real impl drops in without a signature change.

**Real tests confirmed:** byte-identity catches a fabricated quote (Task 8 + Task 10 `test_verify_fabricated_quote_tier_a_fails_unsupported`); NLI marks entailed→supported / non-entailed→contradicted via deterministic stub (Task 10); the gate FAILS an uncited report and PASSES a fully-cited verified one (Task 11); anchor offsets round-trip — `body[start:end] == quoted_support` (Task 1 + Task 5); the LLM fallback is mocked (`FakeLLMProvider`, Task 0/9/10).

## Execution Handoff

Plan complete and saved to `ultimate-research/plans/2026-05-26-bad-research-06-grounding.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
