# Bad Research — KR-4: Keyless Agentic Browse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each step is a discrete commit. Steps use checkbox (`- [ ]`) syntax for tracking. Follow strict TDD: write the failing test, run it and SEE it fail, write the implementation, run it and SEE it pass, commit. Do NOT skip the "see it fail" step.

**Goal:** Replace the cloud browse stack (Browserbase / AgentQL / Stagehand / Browser-Use cloud) with a **100% keyless** local agentic browser driven by the `agent-browser` Rust CLI. Bad Research drives `agent-browser` over a subprocess (`Bash`-equivalent) against a local headless Chrome-for-Testing (or `--engine lightpanda`) over CDP. The host model (Claude Code) IS the agent brain — it reasons over the `@eN` accessibility-snapshot text and picks actions; **no paid LLM call, no API key, anywhere.** This plan builds `browse/agent_browser.py` (the `AgentBrowserProvider` snapshot/ReAct loop + Stagehand act/extract/observe prompt constants), `browse/aql.py` (the ported AgentQL recursive-descent parser + AST + host-model resolver + ref-grounding), rewrites `browse/base.py` (keyless factories) and `browse/ladder.py` (the 4-rung keyless ladder httpx → crawl4ai → lightpanda → agent-browser-chrome with the XHR-JSON shortcut), and wires the keyless persist-once auth flow (`state save` / `--state` / `cookies set --curl`). `agent-browser` and `lightpanda` are OPTIONAL external CLIs — every rung detects-and-degrades to crawl4ai/httpx when they are absent.

**Architecture:** A subprocess command-builder (`_AgentBrowserCLI`) constructs argv vectors for `agent-browser` and runs them via an injectable `runner` (default `subprocess.run`; tests pass a mock that asserts the constructed argv and returns a fixture stdout). `AgentBrowserProvider.snapshot()` parses `snapshot -i --json` stdout (the `{"success":true,"data":{"snapshot":"…","refs":{…}}}` shape) into a `Snapshot{text, refs}` object. `AgentBrowserProvider.browse(url, instruction, …)` runs the dossier-14 §4.2 ReAct loop: `open → wait → snapshot -i --json → (host model picks @eN) → click/fill/press → wait → re-snapshot → … → extract`, returning a `WebResult`. Because the host model is the brain, the *loop driver* in code is deterministic plumbing: it executes a list of `Step` actions (each a CLI command) and re-snapshots; the host model supplies the steps (in the skill path) or a test supplies them (in CI). `browse/aql.py` ports the `agentql==1.18.1` recursive-descent parser verbatim (pure Python, fully unit-testable) and adds a `resolve(ast, snapshot, host_model)` that maps AQL leaf fields → `@eN` refs grounded against the snapshot `refs` map (a ref is valid iff it is a key in `refs`). `browse/ladder.py::fetch_tiered` walks rung-1 httpx → rung-2 crawl4ai → rung-2.5 `agent-browser --engine lightpanda` → rung-3 `agent-browser --engine chrome`, escalating only on `looks_like_junk()`/`looks_like_login_wall()` gates (KEPT verbatim from `web/base.py`), with the lightpanda→chrome fallback on an empty/error snapshot and the `network requests` XHR-JSON shortcut that collapses an agentic browse to a single httpx call.

**Tech Stack:** Python 3.11+ (`requires-python = ">=3.11,<3.14"`), pytest (`asyncio_mode = "auto"`), `unittest.mock` (mock ALL subprocess calls — NO live `agent-browser`/Chrome in tests). The `agent-browser` and `lightpanda` CLIs are EXTERNAL Rust binaries installed out-of-band (NOT pip deps); detection is `shutil.which("agent-browser")`. The AQL parser is pure stdlib (`dataclasses`, `enum`) — no deps, fully tested. Reuses the existing `WebResult` (`web/base.py`, KEPT verbatim), the `BrowseProvider`/`ExtractProvider` Protocols (`browse/base.py`, KEPT verbatim), `LLMExtractProvider` (`browse/extract_llm.py`, KEPT), `ActCache`/`replay_key_for` (`browse/cache.py`, KEPT), and the Plan-01 `LLMProvider` seam (`llm/base.py`) for the AQL host-model resolver (injectable; `None` → graceful degrade). Matches `docs/INTERFACES_KEYLESS.md` §4.3/§4.4 verbatim. Branch: `main`. Test command: `export PATH="$HOME/.local/bin:$PATH" && uv run python -m pytest`.

---

## Background: what already exists (read before starting — do NOT re-derive)

These are FACTS about the current tree. Cite them; do not re-implement them.

- **`src/bad_research/web/base.py`** — `WebResult` dataclass (`url, title, content, fetched_at, raw_html, metadata, media, links, screenshot, raw_bytes, raw_content_type`) with the two escalation gates KEPT verbatim:
  - `WebResult.looks_like_junk() -> str | None` — empty trigger `len(content.strip()) < 300` → `"Empty or near-empty content"`; Cloudflare → `"Bot detection page: <title>"`.
  - `WebResult.looks_like_login_wall(original_url) -> bool` — login/auth redirect detection.
- **`src/bad_research/browse/base.py`** — `BrowseProvider` Protocol (`name: str`; `browse(url, instruction, *, max_steps=12, variables=None, replay_key=None) -> WebResult`) and `ExtractProvider` Protocol (`name: str`; `extract(source: str|WebResult, schema: dict|str, instruction="") -> dict`). **Both Protocols are KEPT VERBATIM by KR-4** — only the factory bodies (`get_browse_provider`/`get_extract_provider`) are rewritten to be keyless. The current bodies read `BROWSERBASE_API_KEY`/`AGENTQL_API_KEY` and import `browser_use`/`stagehand` — KR-1 deletes the keyed backend files; KR-4 rewrites the factories.
- **`src/bad_research/browse/ladder.py`** — `fetch_tiered(url, *, tier_max, instruction=None, schema=None, replay_key=None, variables=None, _tier0=…, _tier1_factory=…, _extractor=…, _browseruse=…, _browserbase=…, _llm=…) -> WebResult`. The **signature is KEPT** except the `_browseruse`/`_browserbase` injection seams become `_lightpanda`/`_chrome` (keyless rungs). The escalation gates (`_is_empty`/`_is_bot_wall`/`looks_like_login_wall`) are KEPT verbatim.
- **`src/bad_research/browse/extract_llm.py`** — `LLMExtractProvider` (Tier-2 default, host-model, injectable `_llm`, `{}` when no LLM). **KEPT VERBATIM.**
- **`src/bad_research/browse/cache.py`** — `replay_key_for(instruction, url, *, variables) -> str` (SHA-256 over `{instruction, url, sorted variable NAMES}` — never values) + `ActCache` (file-backed). **KEPT VERBATIM** (the agent-browser loop reuses it for `replay_key`).
- **`src/bad_research/llm/base.py`** — `LLMMessage(role, content)`, `LLMResponse(text, tool_calls, usage, model)`, `LLMProvider.complete(messages, *, tier, tools=None, cache=False, max_tokens=4096, temperature=0.1)`. The AQL resolver accepts one by injection; `None` → graceful (returns refs from deterministic name-matching only).
- **Tests** (`tests/test_browse/`): `conftest.py::make_result(content, *, url, title)` + the `FakeLLM` class (records `.calls`, pops canned replies). KR-4 ADDS `_AgentBrowserCLI` mock helpers to this conftest. Tests to DELETE (KR-1 mirrors): `test_browse_browserbase.py`, `test_browse_browseruse.py`, `test_extract_agentql.py`, `test_extract_stagehand.py`. Tests to REWRITE: `test_ladder.py`, `test_graceful_degradation.py`. Tests KEPT: `test_base.py` (rewire factories), `test_cache.py`, `test_extract_llm.py`, `test_fetcher_hook.py`.

**KR-1 dependency (assume done before KR-4 starts):** the keyed backend files (`browse_browserbase.py`, `browse_browseruse.py`, `extract_agentql.py`, `extract_stagehand.py`) and their tests are DELETED; `pyproject.toml` `browse` extra no longer lists `browser-use`/`agentql`. If KR-1 has not run, the first task of this plan ALSO deletes those four files (Task 0). **No `cohere/tavily/exa/firecrawl/browserbase/agentql/browser-use/stagehand` import may survive KR-4.**

---

## Verbatim artifacts to copy (do NOT invent these — they are KNOWN-from-source)

| Artifact | Source (verbatim) | Lands in |
|---|---|---|
| AQL grammar (EBNF) | dossier 14 §6.1 / `products/AGENTQL_PRODUCT_CODE.md:1240-1247` | `browse/aql.py` docstring |
| AQL lexer + parser (recursive descent) | `products/AGENTQL_PRODUCT_CODE.md:1249-1631` | `browse/aql.py` (ported as-is) |
| 4 AST node types (`IdNode/IdListNode/ContainerNode/ContainerListNode`) | `AGENTQL_PRODUCT_CODE.md:1295-1337` | `browse/aql.py` |
| Stagehand `act` prompt | dossier 14 §5.1 / `BROWSERBASE_PRODUCT_CODE.md:4279` | `browse/agent_browser.py::ACT_SYSTEM_PROMPT` |
| Stagehand `extract` prompt | dossier 14 §5.2 / `BROWSERBASE_PRODUCT_CODE.md:4313` | `browse/agent_browser.py::EXTRACT_SYSTEM_PROMPT` |
| Stagehand `observe` prompt | dossier 14 §5.3 / `BROWSERBASE_PRODUCT_CODE.md:4360` | `browse/agent_browser.py::OBSERVE_SYSTEM_PROMPT` |
| agent-browser skill system-prompt seed | dossier 14 §4.1 / `stream/chat.rs:124-153` | `browse/agent_browser.py::AGENT_LOOP_SYSTEM_PROMPT` |
| agent-browser core loop (open/snapshot/click/re-snapshot) | dossier 14 §10(A) / `skill-data/core/SKILL.md:20-30` | loop driver |
| `snapshot -i --json` output shape | dossier 14 §10(B) / `README.md:911-913` | `Snapshot` parser |

## Frozen constants (cite verbatim; from `docs/INTERFACES_KEYLESS.md` §8 + dossier 14)

| Constant | Value | Source | Lives in |
|---|---|---|---|
| browse default `max_steps` | `12` | INTERFACES_KEYLESS §4.3 (Protocol default) | `agent_browser.py` |
| wait default timeout | `25_000` ms (below 30s IPC) | dossier 14 §3.5 / `README.md:842` | `agent_browser.py::WAIT_TIMEOUT_MS` |
| chat tool timeout | `60` s | dossier 14 §4.1 / `chat.rs:226` | `agent_browser.py::CLI_TIMEOUT_S` |
| AXTree chunk trigger (heuristic) | `70_000` tokens / `280_000` chars | dossier 14 §5.4 / `BROWSERBASE_PRODUCT_CODE.md:4267` | `agent_browser.py::AXTREE_MAX_CHARS` |
| empty-snapshot fallback floor (lightpanda→chrome) | `< 2` refs for a titled page | dossier 14 §12.5 (DESIGNED) | `agent_browser.py::MIN_REFS_FOR_NONEMPTY` |
| default browse engine (rung 2.5) | `lightpanda` | INTERFACES_KEYLESS §3.4 `browse_engine` / dossier 14 §12.5 | `agent_browser.py` |
| lightpanda telemetry disable | `LIGHTPANDA_DISABLE_TELEMETRY=true` | dossier 14 §12.1 | env set in launch |
| empty-content escalation trigger | `len(content.strip()) < 300` | `web/base.py::looks_like_junk` (KEPT) | `ladder.py` |
| AQL parser error code | `1010` (`QuerySyntaxError`) | `AGENTQL_PRODUCT_CODE.md:1493` | `aql.py` |
| ref-grounding rule | ref valid iff key ∈ `snapshot.refs` | dossier 14 §6.3(3) / `element.rs:340` | `aql.py::ground` |

---

## File Structure

```
src/bad_research/browse/
├── __init__.py              # MODIFY: re-export AgentBrowserProvider, AqlExtractProvider,
│                            #   parse_aql, fetch_tiered (drop the deleted keyed exports)
├── base.py                  # REWRITE factories: get_browse_provider/get_extract_provider keyless;
│                            #   Protocols KEPT VERBATIM
├── agent_browser.py         # NEW: _AgentBrowserCLI (argv builder + runner), Snapshot parser,
│                            #   AgentBrowserProvider (snapshot/browse ReAct loop), Stagehand
│                            #   prompt constants, lightpanda↔chrome fallback, keyless auth helpers
├── aql.py                   # NEW: ported AgentQL lexer+parser+AST (verbatim) + AqlExtractProvider
│                            #   (host-model resolver + ref-grounding against snapshot.refs)
├── ladder.py                # REWRITE: fetch_tiered → 4-rung keyless ladder + XHR-JSON shortcut
├── extract_llm.py           # KEPT VERBATIM
└── cache.py                 # KEPT VERBATIM (replay_key reused by the agent loop)

# DELETED by KR-1 (Task 0 deletes if KR-1 has not run):
#   browse/browse_browserbase.py, browse/browse_browseruse.py,
#   browse/extract_agentql.py, browse/extract_stagehand.py

tests/test_browse/
├── conftest.py              # MODIFY: add FakeRunner (asserts argv, returns fixture stdout),
│                            #   SNAPSHOT_JSON fixture, FakeLLM KEPT
├── test_base.py             # REWRITE: factories return AgentBrowserProvider/AqlExtractProvider
│                            #   keylessly; None when CLI absent
├── test_aql.py              # NEW: the AQL parser — full grammar coverage (pure Python)
├── test_agent_browser_cli.py # NEW: argv construction for open/snapshot/click/fill/press/eval/wait
├── test_agent_browser_snapshot.py # NEW: @eN snapshot JSON parse → Snapshot{text,refs}
├── test_agent_browser_browse.py   # NEW: the ReAct browse loop (mocked runner) → WebResult
├── test_aql_resolver.py     # NEW: AqlExtractProvider resolve + ref-grounding (mock snapshot+LLM)
├── test_ladder.py           # REWRITE: 4-rung escalation, lightpanda→chrome fallback, XHR shortcut
├── test_graceful_degradation.py # REWRITE: CLI absent → factories None, ladder degrades to crawl4ai/httpx
├── test_extract_llm.py      # KEPT
├── test_cache.py            # KEPT
└── test_fetcher_hook.py     # KEPT (verify core/fetcher still delegates to fetch_tiered)
```

**Build order (each task self-contained + committable):** Task 0 (KR-1 cleanup, if needed) → Task 1 (AQL parser, pure Python, no deps) → Task 2 (`_AgentBrowserCLI` argv builder + runner) → Task 3 (Snapshot JSON parser) → Task 4 (`AgentBrowserProvider.browse` ReAct loop) → Task 5 (`AqlExtractProvider` resolver + grounding) → Task 6 (keyless auth helpers) → Task 7 (`base.py` keyless factories) → Task 8 (`ladder.py` 4-rung + fallback + XHR shortcut) → Task 9 (graceful-degradation sweep) → Task 10 (`__init__` exports + full-suite green + commit). The AQL parser is first because it is pure and unblocks the resolver; the CLI builder is next because everything downstream mocks it.

---

## Task 0: KR-1 cleanup guard (delete keyed browse backends if still present)

KR-4 assumes KR-1 deleted the four keyed browse files. If they are still present (KR-1 not yet merged), delete them here so no `browserbase/browser-use/agentql/stagehand` import survives. If they are already gone, this task is a no-op verification.

**Files:** Delete (if present): `src/bad_research/browse/browse_browserbase.py`, `browse_browseruse.py`, `extract_agentql.py`, `extract_stagehand.py`, and their tests `tests/test_browse/test_browse_browserbase.py`, `test_browse_browseruse.py`, `test_extract_agentql.py`, `test_extract_stagehand.py`.

- [ ] **Step 1: Delete keyed backends + their tests (idempotent)**

```bash
cd /Users/seventyleven/Desktop/badresearch
git rm -f --ignore-unmatch \
  src/bad_research/browse/browse_browserbase.py \
  src/bad_research/browse/browse_browseruse.py \
  src/bad_research/browse/extract_agentql.py \
  src/bad_research/browse/extract_stagehand.py \
  tests/test_browse/test_browse_browserbase.py \
  tests/test_browse/test_browse_browseruse.py \
  tests/test_browse/test_extract_agentql.py \
  tests/test_browse/test_extract_stagehand.py
```

- [ ] **Step 2: Verify zero keyed imports remain in browse/**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
grep -rn "browserbase\|browser_use\|browser-use\|agentql\|stagehand\|AGENTQL_API_KEY\|BROWSERBASE_API_KEY" src/bad_research/browse/ || echo "CLEAN — no keyed imports"
```

Expected output: `CLEAN — no keyed imports` (or only matches inside `base.py`/`ladder.py` that Tasks 7-8 rewrite away).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 0: remove keyed browse backends (browserbase/browser-use/agentql/stagehand)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Port the AgentQL AQL parser (`browse/aql.py`, pure Python)

Port the `agentql==1.18.1` recursive-descent parser **verbatim** from `products/AGENTQL_PRODUCT_CODE.md:1249-1631`. It is ~250 lines of pure stdlib (no deps) and is the most fully-testable piece of KR-4. The grammar is the 10-token, 4-node, GraphQL-selection-set-shaped DSL (dossier 14 §6.1). Zero reserved words; `COMMA` optional between siblings; `(description)` parens nest; `NEWLINE` is lexed then filtered.

**Files:**
- Create: `src/bad_research/browse/aql.py` (parser only this task; resolver added Task 5)
- Test: `tests/test_browse/test_aql.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_aql.py
"""The ported AgentQL AQL parser — full grammar coverage. Pure Python, no mocks needed."""

from __future__ import annotations

import pytest

from bad_research.browse.aql import (
    ContainerListNode,
    ContainerNode,
    IdListNode,
    IdNode,
    QuerySyntaxError,
    parse_aql,
)


def test_two_flat_elements() -> None:
    ast = parse_aql("{ search_box  search_button }")
    assert isinstance(ast, ContainerNode)
    assert ast.name == ""
    assert [c.name for c in ast.children] == ["search_box", "search_button"]
    assert all(isinstance(c, IdNode) for c in ast.children)


def test_id_list_node() -> None:
    ast = parse_aql("{ links[] }")
    assert len(ast.children) == 1
    node = ast.children[0]
    assert isinstance(node, IdListNode)
    assert node.name == "links"


def test_container_list_of_objects() -> None:
    ast = parse_aql("{ products[] { name  price  rating } }")
    products = ast.children[0]
    assert isinstance(products, ContainerListNode)
    assert products.name == "products"
    assert [c.name for c in products.children] == ["name", "price", "rating"]
    assert all(isinstance(c, IdNode) for c in products.children)


def test_nested_container() -> None:
    ast = parse_aql("{ login_form { username_input  password_input  submit_button } }")
    form = ast.children[0]
    assert isinstance(form, ContainerNode)
    assert form.get_child_by_name("submit_button") is not None
    assert form.get_child_by_name("missing") is None


def test_description_parens_with_nesting() -> None:
    ast = parse_aql("{ price(sale price (not list price)) }")
    node = ast.children[0]
    assert isinstance(node, IdNode)
    assert node.name == "price"
    assert node.description == "sale price (not list price)"


def test_mixed_list_and_container() -> None:
    ast = parse_aql("{ nav_links[]  footer { copyright  privacy_link } }")
    assert isinstance(ast.children[0], IdListNode)
    assert isinstance(ast.children[1], ContainerNode)


def test_comma_separator_optional() -> None:
    # comma between siblings is legal but optional
    a = parse_aql("{ a, b, c }")
    b = parse_aql("{ a b c }")
    assert [n.name for n in a.children] == [n.name for n in b.children] == ["a", "b", "c"]


def test_newline_separator() -> None:
    ast = parse_aql("{\n  a\n  b\n}")
    assert [n.name for n in ast.children] == ["a", "b"]


def test_no_reserved_words() -> None:
    # query/select/from/true/null are all legal identifiers
    ast = parse_aql("{ query  select  from  true  null }")
    assert [n.name for n in ast.children] == ["query", "select", "from", "true", "null"]


def test_duplicate_identifier_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a  a }")


def test_missing_opening_brace_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("search_box")


def test_unclosed_brace_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a ")


def test_trailing_garbage_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a } extra")


def test_quotes_stripped_from_description() -> None:
    ast = parse_aql('{ x("the blue one") }')
    assert ast.children[0].description == "the blue one"
```

- [ ] **Step 2: Run the test, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_aql.py -q
```

Expected: `ModuleNotFoundError: No module named 'bad_research.browse.aql'` (collection error → all fail).

- [ ] **Step 3: Implement `browse/aql.py` (parser; port verbatim)**

```python
# src/bad_research/browse/aql.py
"""AgentQL (AQL) query language — keyless port + host-model resolver.

The parser is ported VERBATIM from the installed agentql==1.18.1 SDK
(_core/_syntax/{lexer,parser,node,token_kind}.py), reconstructed in
products/AGENTQL_PRODUCT_CODE.md:1249-1631 and documented in dossier 14 §6.1.

Grammar (EBNF, KNOWN — AGENTQL_PRODUCT_CODE.md:1240-1247):
    Query       ::= '{' NodeList '}'
    NodeList    ::= Node ((',' | NEWLINE) Node)*
    Node        ::= IDENTIFIER Description? (Container | List | epsilon)
    Description ::= '(' DescContent ')'
    DescContent ::= (Letter | Digit | Symbol | WS | '(' DescContent ')')*
    Container   ::= '{' NodeList '}'
    List        ::= '[]' Container?
    IDENTIFIER  ::= [a-zA-Z_][a-zA-Z0-9_]*

The AQL string IS the wire format (no separate serializer); Node.dump() round-trips.
There is NO paid LLM call here — the resolver (AqlExtractProvider, below) uses the
host-model LLMProvider seam by injection, or falls back to deterministic name-matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================ Token Types
class TokenKind(Enum):
    SOF = "SOF"
    EOF = "EOF"
    BRACE_L = "{"
    BRACE_R = "}"
    BRACKET_L = "["
    BRACKET_R = "]"
    PAREN_L = "("
    PAREN_R = ")"
    COMMA = ","
    NEWLINE = "NEWLINE"
    IDENTIFIER = "IDENTIFIER"
    DESCRIPTION = "DESCRIPTION"


IGNORED_TOKENS = {TokenKind.NEWLINE}


@dataclass
class Token:
    kind: TokenKind
    value: str
    line: int
    column: int
    prev: Optional["Token"] = None
    next: Optional["Token"] = None


# ============================================================ AST Node Types
@dataclass
class Node:
    name: str
    description: Optional[str] = None

    def get_child_by_name(self, name: str) -> Optional["Node"]:
        return None


@dataclass
class IdNode(Node):
    """Single element: `search_btn` or `search_btn(the main one)`."""


@dataclass
class IdListNode(Node):
    """List of elements: `links[]`."""


@dataclass
class ContainerNode(Node):
    """Scoped container: `nav { home_link about_link }` or the root query."""

    children: list[Node] = field(default_factory=list)

    def get_child_by_name(self, name: str) -> Optional[Node]:
        for child in self.children:
            if child.name == name:
                return child
        return None


@dataclass
class ContainerListNode(Node):
    """List of structured objects: `products[] { name price }`."""

    children: list[Node] = field(default_factory=list)

    def get_child_by_name(self, name: str) -> Optional[Node]:
        for child in self.children:
            if child.name == name:
                return child
        return None


# ============================================================ Errors
class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int) -> None:
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


class QuerySyntaxError(Exception):
    def __init__(self, message: str, line: int = 0, column: int = 0) -> None:
        self.code = 1010
        self.line = line
        self.column = column
        super().__init__(f"1010 QuerySyntaxError: {message} on row {line}")


# ============================================================ Lexer
class Lexer:
    """Character-by-character tokenizer producing a linked list of Token objects."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.head: Optional[Token] = None
        self.tail: Optional[Token] = None

    def tokenize(self) -> Token:
        sof = Token(TokenKind.SOF, "", 1, 0)
        self.head = sof
        self.tail = sof
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in (" ", "\t"):
                self.pos += 1
                self.column += 1
                continue
            if ch in ("\r", "\n"):
                if ch == "\r" and self._peek(1) == "\n":
                    self.pos += 1
                self._emit(TokenKind.NEWLINE, ch)
                self.pos += 1
                self.line += 1
                self.column = 1
                continue
            if ch == "{":
                self._emit(TokenKind.BRACE_L, ch)
            elif ch == "}":
                self._emit(TokenKind.BRACE_R, ch)
            elif ch == "[":
                self._emit(TokenKind.BRACKET_L, ch)
            elif ch == "]":
                self._emit(TokenKind.BRACKET_R, ch)
            elif ch == ",":
                self._emit(TokenKind.COMMA, ch)
            elif ch == "(":
                self._scan_description()
                continue
            elif ch.isalpha() or ch == "_":
                self._scan_identifier()
                continue
            else:
                raise LexerError(f"Unexpected character '{ch}'", self.line, self.column)
            self.pos += 1
            self.column += 1
        self._emit(TokenKind.EOF, "")
        return self.head

    def _emit(self, kind: TokenKind, value: str) -> None:
        token = Token(kind, value, self.line, self.column)
        token.prev = self.tail
        self.tail.next = token
        self.tail = token

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _scan_identifier(self) -> None:
        start = self.pos
        start_col = self.column
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_":
                self.pos += 1
                self.column += 1
            else:
                break
        value = self.source[start : self.pos]
        token = Token(TokenKind.IDENTIFIER, value, self.line, start_col)
        token.prev = self.tail
        self.tail.next = token
        self.tail = token

    def _scan_description(self) -> None:
        """Scan from ( to matching ), handling nested parens."""
        start_line = self.line
        start_col = self.column
        self.pos += 1
        self.column += 1
        depth = 1
        content: list[str] = []
        while self.pos < len(self.source) and depth > 0:
            ch = self.source[self.pos]
            if ch == "(":
                depth += 1
                content.append(ch)
            elif ch == ")":
                depth -= 1
                if depth > 0:
                    content.append(ch)
            elif ch == "\n":
                content.append(ch)
                self.line += 1
                self.column = 0
            else:
                content.append(ch)
            self.pos += 1
            self.column += 1
        if depth != 0:
            raise LexerError("Unclosed description parenthesis", start_line, start_col)
        desc_text = "".join(content).strip()
        if len(desc_text) >= 2 and (
            (desc_text[0] == '"' and desc_text[-1] == '"')
            or (desc_text[0] == "'" and desc_text[-1] == "'")
        ):
            desc_text = desc_text[1:-1].strip()
        self._emit(TokenKind.DESCRIPTION, desc_text)


# ============================================================ Recursive-Descent Parser
class QueryParser:
    """Parses AgentQL query strings into an AST (root ContainerNode)."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.lexer = Lexer(query)
        self.current: Optional[Token] = None

    def parse(self) -> ContainerNode:
        sof = self.lexer.tokenize()
        self.current = sof.next  # skip SOF
        self._skip_ignored()
        self._expect(TokenKind.BRACE_L)
        self._advance()
        children = self._parse_node_list()
        self._expect(TokenKind.BRACE_R)
        self._advance()
        self._skip_ignored()
        if self.current and self.current.kind != TokenKind.EOF:
            raise QuerySyntaxError(
                f"Expected end of query, found {self.current.kind.value}",
                self.current.line,
                self.current.column,
            )
        return ContainerNode(name="", children=children)

    def _parse_node_list(self) -> list[Node]:
        nodes: list[Node] = []
        seen_names: set[str] = set()
        while True:
            self._skip_ignored()
            if not self.current or self.current.kind in (TokenKind.BRACE_R, TokenKind.EOF):
                break
            node = self._parse_node()
            if node.name in seen_names:
                raise QuerySyntaxError(
                    f"Duplicate identifier '{node.name}'",
                    self.current.line if self.current else 0,
                    self.current.column if self.current else 0,
                )
            seen_names.add(node.name)
            nodes.append(node)
            self._skip_ignored()
            if self.current and self.current.kind == TokenKind.COMMA:
                self._advance()
        return nodes

    def _parse_node(self) -> Node:
        """Parse: IDENTIFIER Description? (Container | List | epsilon)."""
        self._skip_ignored()
        self._expect(TokenKind.IDENTIFIER)
        name = self.current.value
        self._advance()
        description = None
        self._skip_ignored()
        if self.current and self.current.kind == TokenKind.DESCRIPTION:
            description = self.current.value
            self._advance()
        self._skip_ignored()
        is_list = False
        if self.current and self.current.kind == TokenKind.BRACKET_L:
            self._advance()
            self._expect(TokenKind.BRACKET_R)
            self._advance()
            is_list = True
        self._skip_ignored()
        if self.current and self.current.kind == TokenKind.BRACE_L:
            self._advance()
            children = self._parse_node_list()
            self._expect(TokenKind.BRACE_R)
            self._advance()
            if is_list:
                return ContainerListNode(name=name, description=description, children=children)
            return ContainerNode(name=name, description=description, children=children)
        if is_list:
            return IdListNode(name=name, description=description)
        return IdNode(name=name, description=description)

    def _advance(self) -> None:
        if self.current and self.current.next:
            self.current = self.current.next
        self._skip_ignored()

    def _skip_ignored(self) -> None:
        while self.current and self.current.kind in IGNORED_TOKENS:
            self.current = self.current.next

    def _expect(self, kind: TokenKind) -> None:
        if not self.current or self.current.kind != kind:
            found = self.current.kind.value if self.current else "EOF"
            raise QuerySyntaxError(
                f"Expected {kind.value}, found {found}",
                self.current.line if self.current else 0,
                self.current.column if self.current else 0,
            )


def parse_aql(query: str) -> ContainerNode:
    """Public entry: validate + parse an AQL string into its root ContainerNode AST."""
    return QueryParser(query).parse()
```

- [ ] **Step 4: Run the test, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_aql.py -q
```

Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 1: port AgentQL AQL recursive-descent parser (browse/aql.py)

Verbatim from agentql==1.18.1 SDK (AGENTQL_PRODUCT_CODE.md:1249-1631). Pure
Python, no deps. 10-token / 4-node grammar (dossier 14 §6.1). 15 grammar tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_AgentBrowserCLI` — argv builder + injectable runner (`browse/agent_browser.py`)

The subprocess seam. `_AgentBrowserCLI` builds argv vectors for every `agent-browser` command the keyless loop drives (dossier 14 §3) and runs them through an injectable `runner` (default `subprocess.run`; tests pass a `FakeRunner` that asserts the argv and returns canned `(returncode, stdout, stderr)`). The global flags (`--engine`, `--session`, `--state`, `--headers`) are threaded per call. `LIGHTPANDA_DISABLE_TELEMETRY=true` is forced into the env when engine is lightpanda (dossier 14 §12.1). **This is the riskiest contract in KR-4** — see the Risk note at the end; it needs a one-time live smoke (dossier 14 §11).

**Files:**
- Create: `src/bad_research/browse/agent_browser.py` (CLI builder this task; provider added Tasks 3-4)
- Test: `tests/test_browse/test_agent_browser_cli.py`; MODIFY `tests/test_browse/conftest.py` (add `FakeRunner`, `SNAPSHOT_JSON`)

- [ ] **Step 1: Add `FakeRunner` + `SNAPSHOT_JSON` to conftest**

```python
# APPEND to tests/test_browse/conftest.py

import json as _json


# A canonical agent-browser `snapshot -i --json` stdout (dossier 14 §10B / README.md:911-913).
SNAPSHOT_JSON = _json.dumps({
    "success": True,
    "data": {
        "snapshot": (
            "Page: Example - Log in\n"
            "URL: https://example.com/login\n\n"
            "@e1 [heading] \"Log in\"\n"
            "@e2 [form]\n"
            "  @e3 [input type=\"email\"] placeholder=\"Email\"\n"
            "  @e4 [input type=\"password\"] placeholder=\"Password\"\n"
            "  @e5 [button type=\"submit\"] \"Continue\"\n"
            "  @e6 [link] \"Forgot password?\""
        ),
        "refs": {
            "e1": {"role": "heading", "name": "Log in"},
            "e2": {"role": "form", "name": ""},
            "e3": {"role": "textbox", "name": "Email"},
            "e4": {"role": "textbox", "name": "Password"},
            "e5": {"role": "button", "name": "Continue"},
            "e6": {"role": "link", "name": "Forgot password?"},
        },
    },
})

# An empty/near-empty snapshot (lightpanda failed to hydrate → triggers chrome fallback).
EMPTY_SNAPSHOT_JSON = _json.dumps({
    "success": True,
    "data": {"snapshot": "Page: Loading…\nURL: https://spa.example/\n", "refs": {}},
})


class FakeRunner:
    """Stand-in for subprocess.run. Records every argv it is asked to run and returns
    canned (returncode, stdout, stderr) tuples in order. If `route` is given it maps a
    matched command word -> stdout (so a multi-step loop can return different stdout per
    command). Never spawns a real process."""

    def __init__(self, replies=None, route=None, returncode=0):
        self.calls: list[list[str]] = []
        self._replies = list(replies or [])
        self._route = dict(route or {})
        self._returncode = returncode

    def __call__(self, argv, *, timeout=None, env=None):
        self.calls.append(list(argv))
        # route by the command word (argv[1] after the `agent-browser` program name)
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd in self._route:
            out = self._route[cmd]
        elif self._replies:
            out = self._replies.pop(0)
        else:
            out = ""
        return (self._returncode, out, "")

    def argvs(self) -> list[list[str]]:
        return self.calls

    def last(self) -> list[str]:
        return self.calls[-1]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_browse/test_agent_browser_cli.py
"""argv construction for the agent-browser CLI seam. NO real subprocess — FakeRunner only."""

from __future__ import annotations

from bad_research.browse.agent_browser import _AgentBrowserCLI
from tests.test_browse.conftest import SNAPSHOT_JSON, FakeRunner


def test_open_builds_open_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.open("https://x.test")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "open", "https://x.test"]


def test_snapshot_builds_interactive_json_argv() -> None:
    runner = FakeRunner(replies=[SNAPSHOT_JSON])
    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    out = cli.snapshot(interactive=True)
    assert runner.last() == [
        "agent-browser", "--engine", "lightpanda", "snapshot", "-i", "--json",
    ]
    assert out == SNAPSHOT_JSON


def test_click_uses_ref() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.click("@e5")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "click", "@e5"]


def test_fill_quotes_value_as_separate_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.fill("@e3", "user@example.com")
    # value is its own argv element (no shell quoting needed — argv list, not a string)
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "fill", "@e3", "user@example.com",
    ]


def test_press_key() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.press("Enter")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "press", "Enter"]


def test_eval_stdin_passes_js_on_stdin_not_argv() -> None:
    runner = FakeRunner(replies=['[{"name":"x"}]'])
    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    js = "Array.from(document.querySelectorAll('h2')).map(e=>e.innerText)"
    out = cli.eval_js(js)
    assert runner.last() == ["agent-browser", "--engine", "lightpanda", "eval", "--stdin"]
    # the JS is delivered on stdin, recorded separately by the runner
    assert runner.stdin == js
    assert out == '[{"name":"x"}]'


def test_wait_load_networkidle() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.wait_load("networkidle")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "wait", "--load", "networkidle",
    ]


def test_session_and_state_global_flags_threaded() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner,
                           session="job1", state="/auth/src.json")
    cli.open("https://x.test")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome",
        "--session", "job1", "--state", "/auth/src.json",
        "open", "https://x.test",
    ]


def test_lightpanda_engine_sets_telemetry_env() -> None:
    captured = {}

    def runner(argv, *, timeout=None, env=None):
        captured["env"] = env
        return (0, "{}", "")

    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    cli.open("https://x.test")
    assert captured["env"]["LIGHTPANDA_DISABLE_TELEMETRY"] == "true"


def test_network_requests_xhr_filter() -> None:
    runner = FakeRunner(replies=['{"data":[]}'])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.network_requests(types="xhr,fetch")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome",
        "network", "requests", "--type", "xhr,fetch", "--json",
    ]
```

- [ ] **Step 3: Run the test, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_cli.py -q
```

Expected: `ImportError: cannot import name '_AgentBrowserCLI'`.

- [ ] **Step 4: Implement `_AgentBrowserCLI` (top of `browse/agent_browser.py`)**

```python
# src/bad_research/browse/agent_browser.py
"""AgentBrowserProvider — keyless agentic browse on the local `agent-browser` CLI.

agent-browser (vercel-labs/agent-browser) is a native Rust CLI that drives a LOCAL
headless Chrome-for-Testing (or `--engine lightpanda`) over CDP. It is keyless: the
only keyed surfaces are `-p <cloud-provider>` and the built-in `chat` command, both of
which we never use (dossier 14 §1, §9). Claude Code (the host model) IS the agent brain
— it reasons over the @eN accessibility-snapshot text and supplies the next action; no
paid LLM call is ever made (dossier 14 §4).

This module:
  * _AgentBrowserCLI  — builds argv vectors + runs them via an injectable runner.
  * Snapshot          — parses `snapshot -i --json` stdout into {text, refs} (Task 3).
  * AgentBrowserProvider — the snapshot/ReAct browse loop returning WebResult (Task 4).
  * Stagehand act/extract/observe prompt constants (verbatim, dossier 14 §5).

agent-browser/lightpanda are EXTERNAL CLIs (NOT pip deps). `is_available()` gates
construction so the ladder degrades to crawl4ai/httpx when they are absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any, Literal

# ---- frozen constants (INTERFACES_KEYLESS §8 + dossier 14) ----
DEFAULT_MAX_STEPS = 12             # INTERFACES_KEYLESS §4.3 Protocol default
WAIT_TIMEOUT_MS = 25_000           # dossier 14 §3.5 (below the 30s IPC read timeout)
CLI_TIMEOUT_S = 60                 # dossier 14 §4.1 (chat.rs:226 tool timeout)
AXTREE_MAX_CHARS = 280_000         # dossier 14 §5.4 chunking heuristic
MIN_REFS_FOR_NONEMPTY = 2          # dossier 14 §12.5 lightpanda→chrome fallback floor
DEFAULT_ENGINE: Literal["lightpanda", "chrome"] = "lightpanda"
AB_PROGRAM = "agent-browser"

# A subprocess runner: (argv, *, timeout, env) -> (returncode, stdout, stderr).
Runner = Callable[..., tuple[int, str, str]]


def _default_runner(argv: list[str], *, timeout: float | None = None,
                    env: dict | None = None, stdin: str | None = None) -> tuple[int, str, str]:
    """The production runner: subprocess.run. Captures stdout/stderr text. Never raises on
    non-zero exit (the caller inspects returncode)."""
    proc = subprocess.run(  # noqa: S603 — argv list, no shell
        argv, capture_output=True, text=True, timeout=timeout,
        env=env, input=stdin,
    )
    return (proc.returncode, proc.stdout or "", proc.stderr or "")


def is_available(program: str = AB_PROGRAM) -> bool:
    """True iff the agent-browser CLI is on PATH (detect-and-degrade contract)."""
    return shutil.which(program) is not None


class _AgentBrowserCLI:
    """Builds + runs agent-browser command argv. The runner is injectable so tests assert
    the constructed argv and feed canned stdout (NO real subprocess in tests)."""

    def __init__(
        self,
        *,
        engine: Literal["lightpanda", "chrome"] = DEFAULT_ENGINE,
        runner: Runner | None = None,
        session: str | None = None,
        state: str | None = None,
        headers: str | None = None,
        program: str = AB_PROGRAM,
        timeout_s: float = CLI_TIMEOUT_S,
    ) -> None:
        self.engine = engine
        self._runner = runner or _default_runner
        self.session = session
        self.state = state
        self.headers = headers
        self.program = program
        self.timeout_s = timeout_s

    # ---- argv prefix: program + global flags (order is stable, asserted by tests) ----
    def _prefix(self) -> list[str]:
        argv = [self.program, "--engine", self.engine]
        if self.session:
            argv += ["--session", self.session]
        if self.state:
            argv += ["--state", self.state]
        if self.headers:
            argv += ["--headers", self.headers]
        return argv

    def _env(self) -> dict | None:
        if self.engine == "lightpanda":
            env = dict(os.environ)
            env["LIGHTPANDA_DISABLE_TELEMETRY"] = "true"  # dossier 14 §12.1
            return env
        return None

    def _run(self, *args: str, stdin: str | None = None) -> str:
        argv = self._prefix() + list(args)
        env = self._env()
        # Pass stdin through only when given (default runner & FakeRunner both accept it).
        try:
            rc, out, _err = self._runner(argv, timeout=self.timeout_s, env=env, stdin=stdin) \
                if _runner_accepts_stdin(self._runner) else self._runner(argv, timeout=self.timeout_s, env=env)
        except TypeError:
            rc, out, _err = self._runner(argv, timeout=self.timeout_s, env=env)
        # record stdin on the runner if it tracks it (FakeRunner convenience)
        if stdin is not None and hasattr(self._runner, "__dict__"):
            try:
                self._runner.stdin = stdin  # type: ignore[attr-defined]
            except Exception:
                pass
        return out

    # ---- lifecycle / nav (dossier 14 §3.1) ----
    def open(self, url: str) -> str:
        return self._run("open", url)

    def close(self, *, all_sessions: bool = False) -> str:
        return self._run("close", "--all") if all_sessions else self._run("close")

    # ---- perception (dossier 14 §3.2) ----
    def snapshot(self, *, interactive: bool = True, compact: bool = False,
                 links: bool = False, scope: str | None = None) -> str:
        args = ["snapshot"]
        if interactive:
            args.append("-i")
        if compact:
            args.append("-c")
        if links:
            args.append("-u")
        if scope:
            args += ["-s", scope]
        args.append("--json")
        return self._run(*args)

    def get_text(self, ref: str) -> str:
        return self._run("get", "text", ref)

    def get_attr(self, ref: str, attr: str) -> str:
        return self._run("get", "attr", ref, attr)

    def eval_js(self, js: str) -> str:
        """Run arbitrary JS in the page via `eval --stdin` (the deterministic extraction
        escape hatch, dossier 14 §5.2 Mode B). JS goes on stdin, NOT argv."""
        return self._run("eval", "--stdin", stdin=js)

    # ---- interaction (dossier 14 §3.3) ----
    def click(self, ref: str) -> str:
        return self._run("click", ref)

    def fill(self, ref: str, value: str) -> str:
        return self._run("fill", ref, value)

    def type_text(self, ref: str, value: str) -> str:
        return self._run("type", ref, value)

    def press(self, key: str) -> str:
        return self._run("press", key)

    def select(self, ref: str, *values: str) -> str:
        return self._run("select", ref, *values)

    # ---- wait (dossier 14 §3.5) ----
    def wait_load(self, state: str = "networkidle") -> str:
        return self._run("wait", "--load", state)

    def wait_text(self, text: str) -> str:
        return self._run("wait", "--text", text)

    def wait_url(self, pattern: str) -> str:
        return self._run("wait", "--url", pattern)

    def wait_selector(self, sel: str) -> str:
        return self._run("wait", sel)

    # ---- network (XHR-JSON shortcut, dossier 14 §7) ----
    def network_requests(self, *, types: str = "xhr,fetch") -> str:
        return self._run("network", "requests", "--type", types, "--json")

    # ---- auth (dossier 14 §8/§13) ----
    def state_save(self, path: str) -> str:
        return self._run("state", "save", path)

    def cookies_set_curl(self, curl_file: str) -> str:
        return self._run("cookies", "set", "--curl", curl_file)


def _runner_accepts_stdin(runner: Runner) -> bool:
    """Best-effort: does the runner accept a `stdin=` kwarg? Default runner & FakeRunner do."""
    import inspect
    try:
        sig = inspect.signature(runner)
        return "stdin" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        return False
```

> **Implementation note for the FakeRunner stdin assertion:** the `test_eval_stdin_passes_js_on_stdin_not_argv` test reads `runner.stdin`. The `_run` method sets `runner.stdin` after the call. To make `FakeRunner` accept the `stdin=` kwarg cleanly, ALSO update `FakeRunner.__call__` in conftest to accept `stdin=None` and store it:

```python
# In tests/test_browse/conftest.py — update FakeRunner.__call__ signature to:
    def __call__(self, argv, *, timeout=None, env=None, stdin=None):
        self.calls.append(list(argv))
        if stdin is not None:
            self.stdin = stdin
        cmd = argv[1] if len(argv) > 1 else ""
        ...
```

Apply that one-line signature change to the `FakeRunner` you added in Step 1 before running.

- [ ] **Step 5: Run the test, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_cli.py -q
```

Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 2: _AgentBrowserCLI argv builder + injectable runner (browse/agent_browser.py)

Drives agent-browser open/snapshot/click/fill/type/press/select/eval/wait/network/state/
cookies. Global flags (--engine/--session/--state/--headers) threaded; lightpanda forces
LIGHTPANDA_DISABLE_TELEMETRY=true. eval JS on stdin. FakeRunner asserts argv (no real CLI).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `Snapshot` parser — the @eN accessibility tree (`browse/agent_browser.py`)

Parse the `snapshot -i --json` stdout (dossier 14 §10B) into a `Snapshot{text, refs, title, url}` object. `refs` is the grounding source: a ref (`@eN` / `eN`) is valid iff it is a key in `refs` (dossier 14 §6.3). The `is_empty` property powers the lightpanda→chrome fallback (`< MIN_REFS_FOR_NONEMPTY` refs for a titled page). Tolerant of malformed stdout (non-JSON, `success:false`) → empty snapshot, never raises.

**Files:**
- Modify: `src/bad_research/browse/agent_browser.py` (add `Snapshot` + `parse_snapshot`)
- Test: `tests/test_browse/test_agent_browser_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_agent_browser_snapshot.py
"""@eN accessibility-snapshot JSON parse → Snapshot{text, refs}. Pure parse, no subprocess."""

from __future__ import annotations

from bad_research.browse.agent_browser import Snapshot, normalize_ref, parse_snapshot
from tests.test_browse.conftest import EMPTY_SNAPSHOT_JSON, SNAPSHOT_JSON


def test_parse_extracts_refs_and_text() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert isinstance(snap, Snapshot)
    assert set(snap.refs) == {"e1", "e2", "e3", "e4", "e5", "e6"}
    assert snap.refs["e5"]["role"] == "button"
    assert snap.refs["e5"]["name"] == "Continue"
    assert "@e5 [button" in snap.text


def test_parse_extracts_title_and_url() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.title == "Example - Log in"
    assert snap.url == "https://example.com/login"


def test_grounding_has_ref_accepts_eN_and_at_eN_and_bare() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.has_ref("@e3") is True
    assert snap.has_ref("e3") is True
    assert snap.has_ref("ref=e3") is True
    assert snap.has_ref("@e99") is False


def test_normalize_ref_strips_prefixes() -> None:
    assert normalize_ref("@e3") == "e3"
    assert normalize_ref("ref=e3") == "e3"
    assert normalize_ref("e3") == "e3"


def test_empty_snapshot_is_empty() -> None:
    snap = parse_snapshot(EMPTY_SNAPSHOT_JSON)
    assert snap.refs == {}
    assert snap.is_empty is True


def test_titled_page_with_refs_is_not_empty() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.is_empty is False


def test_malformed_json_returns_empty_snapshot_no_raise() -> None:
    snap = parse_snapshot("not json at all <<<")
    assert snap.refs == {}
    assert snap.is_empty is True
    assert snap.text == ""


def test_success_false_returns_empty_snapshot() -> None:
    snap = parse_snapshot('{"success": false, "error": "no session"}')
    assert snap.refs == {}
    assert snap.is_empty is True
```

- [ ] **Step 2: Run the test, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_snapshot.py -q
```

Expected: `ImportError: cannot import name 'Snapshot'`.

- [ ] **Step 3: Implement `Snapshot` + `parse_snapshot` (append to `agent_browser.py`)**

```python
# ---- append to src/bad_research/browse/agent_browser.py ----

import json
import re
from dataclasses import dataclass, field


def normalize_ref(ref: str) -> str:
    """Accept `@e1`, `ref=e1`, or bare `e1` → canonical `e1` (dossier 14 §2.3 parse_ref)."""
    r = ref.strip()
    if r.startswith("@"):
        r = r[1:]
    if r.startswith("ref="):
        r = r[len("ref="):]
    return r


@dataclass
class Snapshot:
    """A parsed agent-browser accessibility snapshot. `refs` is the grounding source:
    a ref is valid iff its normalized id is a key here (dossier 14 §6.3 / §10B)."""

    text: str = ""
    refs: dict[str, dict] = field(default_factory=dict)
    title: str = ""
    url: str = ""

    @property
    def is_empty(self) -> bool:
        """Implausibly empty → triggers the lightpanda→chrome fallback (dossier 14 §12.5)."""
        return len(self.refs) < MIN_REFS_FOR_NONEMPTY

    def has_ref(self, ref: str) -> bool:
        return normalize_ref(ref) in self.refs

    def find_refs_by_role(self, role: str) -> list[str]:
        return [f"@{rid}" for rid, meta in self.refs.items() if meta.get("role") == role]


_TITLE_RE = re.compile(r"^Page:\s*(.+)$", re.MULTILINE)
_URL_RE = re.compile(r"^URL:\s*(\S+)$", re.MULTILINE)


def parse_snapshot(stdout: str) -> Snapshot:
    """Parse `snapshot -i --json` stdout into a Snapshot. Tolerant: malformed JSON or
    success:false → empty Snapshot (never raises) so the loop/ladder can degrade."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return Snapshot()
    if not isinstance(payload, dict) or not payload.get("success"):
        return Snapshot()
    data = payload.get("data") or {}
    text = data.get("snapshot") or ""
    raw_refs = data.get("refs") or {}
    refs = {normalize_ref(k): v for k, v in raw_refs.items() if isinstance(v, dict)}
    title_m = _TITLE_RE.search(text)
    url_m = _URL_RE.search(text)
    return Snapshot(
        text=text,
        refs=refs,
        title=title_m.group(1).strip() if title_m else "",
        url=url_m.group(1).strip() if url_m else "",
    )
```

- [ ] **Step 4: Run the test, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_snapshot.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 3: Snapshot parser for the @eN accessibility tree (browse/agent_browser.py)

Parses `snapshot -i --json` → {text, refs, title, url}; refs = grounding source.
is_empty (<2 refs) drives the lightpanda→chrome fallback. Tolerant of malformed stdout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `AgentBrowserProvider.browse` — the keyless ReAct loop + Stagehand prompts

`AgentBrowserProvider` implements the `BrowseProvider` Protocol (`name`, `browse(url, instruction, *, max_steps=12, variables=None, replay_key=None) -> WebResult`). The dossier-14 §4.2 loop: `open → wait → snapshot → … → re-snapshot → extract`. Because the host model is the brain, the code-side loop driver executes a `steps` list (each a CLI action) and re-snapshots between page-changing actions; the host model (skill path) or a test (CI) supplies the steps. `engine="lightpanda"` with empty-snapshot fallback to `chrome` (dossier 14 §12.5). The Stagehand `act`/`extract`/`observe` system prompts ship as verbatim module constants (dossier 14 §5) for the skill to embed.

**Files:**
- Modify: `src/bad_research/browse/agent_browser.py` (add prompt constants + `AgentBrowserProvider`)
- Test: `tests/test_browse/test_agent_browser_browse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_agent_browser_browse.py
"""The AgentBrowserProvider ReAct browse loop. FakeRunner feeds canned snapshot/eval stdout."""

from __future__ import annotations

from bad_research.browse.agent_browser import (
    ACT_SYSTEM_PROMPT,
    AGENT_LOOP_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    OBSERVE_SYSTEM_PROMPT,
    AgentBrowserProvider,
    BrowseStep,
)
from bad_research.web.base import WebResult
from tests.test_browse.conftest import (
    EMPTY_SNAPSHOT_JSON,
    SNAPSHOT_JSON,
    FakeRunner,
)


def test_provider_name() -> None:
    assert AgentBrowserProvider(runner=FakeRunner()).name == "agent-browser"


def test_open_snapshot_returns_webresult_with_snapshot_text() -> None:
    # open → wait → snapshot. No interaction steps → result content = snapshot text.
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    result = prov.browse("https://example.com/login", "read the login page")
    assert isinstance(result, WebResult)
    assert "@e5 [button" in result.content
    assert result.metadata["engine"] == "chrome"
    # the very first command opened the right URL
    assert runner.argvs()[0][:4] == ["agent-browser", "--engine", "chrome", "open"]
    assert runner.argvs()[0][-1] == "https://example.com/login"


def test_browse_executes_supplied_steps_then_resnapshots() -> None:
    # A login flow: fill @e3, fill @e4, click @e5 — re-snapshot after the click.
    runner = FakeRunner(route={
        "open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON,
        "fill": "{}", "click": "{}",
    })
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    steps = [
        BrowseStep("fill", "@e3", "user@example.com"),
        BrowseStep("fill", "@e4", "secret"),
        BrowseStep("click", "@e5"),
    ]
    prov.browse("https://example.com/login", "log in", steps=steps)
    cmds = [argv[3] for argv in runner.argvs()]  # the command word (after engine flag)
    assert cmds.count("fill") == 2
    assert cmds.count("click") == 1
    # at least two snapshots: initial perception + a re-snapshot after the click
    assert cmds.count("snapshot") >= 2


def test_lightpanda_empty_snapshot_falls_back_to_chrome() -> None:
    # lightpanda returns an empty snapshot → provider retries the open+snapshot on chrome.
    runner = FakeRunner(replies=[
        "{}",                  # lightpanda open
        "{}",                  # lightpanda wait
        EMPTY_SNAPSHOT_JSON,   # lightpanda snapshot → empty → fall back
        "{}",                  # chrome open
        "{}",                  # chrome wait
        SNAPSHOT_JSON,         # chrome snapshot → good
    ])
    prov = AgentBrowserProvider(engine="lightpanda", runner=runner)
    result = prov.browse("https://spa.example/", "read the page")
    assert result.metadata["engine"] == "chrome"            # fell back
    assert "@e5 [button" in result.content
    # the chrome retry re-issued an open with --engine chrome
    engines_used = [argv[2] for argv in runner.argvs()]
    assert "lightpanda" in engines_used and "chrome" in engines_used


def test_step_grounding_skips_refs_absent_from_snapshot() -> None:
    # A step targeting @e99 (not in the snapshot refs) is skipped (grounding), no crash.
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON,
                               "click": "{}"})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.browse("https://example.com/login", "click ghost",
                steps=[BrowseStep("click", "@e99")])
    cmds = [argv[3] for argv in runner.argvs()]
    assert cmds.count("click") == 0   # ungrounded ref → never clicked


def test_cli_absent_returns_empty_webresult_no_raise(monkeypatch) -> None:
    import bad_research.browse.agent_browser as ab
    monkeypatch.setattr(ab, "is_available", lambda program="agent-browser": False)
    prov = AgentBrowserProvider(engine="chrome", runner=FakeRunner())
    result = prov.browse("https://x.test", "do stuff")
    assert isinstance(result, WebResult)
    assert result.content == ""
    assert result.metadata.get("unavailable") is True


def test_stagehand_prompts_are_verbatim_nonempty() -> None:
    # The four prompts ship as constants for the skill to embed (dossier 14 §5, §4.1).
    assert "automate the browser by finding elements" in ACT_SYSTEM_PROMPT
    assert "EXTRACT ALL OF THE INFORMATION" in EXTRACT_SYSTEM_PROMPT
    assert "observe" in OBSERVE_SYSTEM_PROMPT.lower()
    assert "agent_browser tool" in AGENT_LOOP_SYSTEM_PROMPT or \
           "agent-browser" in AGENT_LOOP_SYSTEM_PROMPT
```

- [ ] **Step 2: Run the test, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_browse.py -q
```

Expected: `ImportError: cannot import name 'AgentBrowserProvider'`.

- [ ] **Step 3: Implement prompts + `AgentBrowserProvider` (append to `agent_browser.py`)**

```python
# ---- append to src/bad_research/browse/agent_browser.py ----

from bad_research.web.base import WebResult

# ============================================================ Verbatim prompts
# Stagehand act/extract/observe system prompts (dossier 14 §5, BROWSERBASE_PRODUCT_CODE.md
# :4279-4367). Shipped as constants for the Bad Research skill to embed when it reasons
# over the snapshot text — the LLM call is Claude Code itself, not a paid network call.

ACT_SYSTEM_PROMPT = (
    "You are helping the user automate the browser by finding elements based on what "
    "action the user wants to take on the page. You will be given: 1. a user defined "
    "instruction about what action to take on the page 2. a hierarchical accessibility "
    "tree showing the semantic structure of the page. The tree is a hybrid of the DOM and "
    "the accessibility tree. Return the element that matches the instruction if it exists. "
    "Otherwise, return an empty object."
)

EXTRACT_SYSTEM_PROMPT = (
    "You are extracting content on behalf of a user. If a user asks you to extract a "
    "'list' of information, or 'all' information, YOU MUST EXTRACT ALL OF THE INFORMATION "
    "THAT THE USER REQUESTS. You will be given: 1. An instruction 2. A list of DOM "
    "elements to extract from. Print the exact text from the DOM elements with all "
    "symbols, characters, and endlines as is. Print null or an empty string if no new "
    "information is found. ONLY print the content using the print_extracted_data tool "
    "provided. If a user is attempting to extract links or URLs, you MUST respond with "
    "ONLY the IDs of the link elements. Do not attempt to extract links directly from the "
    "text unless absolutely necessary."
)

OBSERVE_SYSTEM_PROMPT = (
    "You are helping the user automate the browser by finding elements based on what the "
    "user wants to observe in the page. You will be given: 1. a instruction of elements to "
    "observe 2. a hierarchical accessibility tree showing the semantic structure of the "
    "page. Return an array of elements that match the instruction if they exist, otherwise "
    "return an empty array. When returning elements, include the appropriate method from "
    "the supported actions list."
)

# The agent-loop system-prompt seed (dossier 14 §4.1, stream/chat.rs:124-153). The skill
# embeds these rules; we DROP the --json-ban and command-allowlist (those exist because
# Vercel doesn't trust its LLM; Claude Code is trusted and --json is useful — dossier 14 §10F).
AGENT_LOOP_SYSTEM_PROMPT = (
    "You control a browser through the agent-browser CLI. You have an active browser "
    "session.\n"
    "RULES:\n"
    "- You MUST run the agent-browser command for every browser action. NEVER claim you "
    "performed an action without running it.\n"
    "- If a request is outside your capabilities, say so honestly. Do not improvise.\n"
    "- One command, read the output, then decide the next.\n"
    "- Re-snapshot after ANY page change (navigate, submit, re-render, dialog) — refs go "
    "stale.\n"
    "- Pick a @eN ref only from the most recent snapshot's refs map; never invent one."
)


@dataclass
class BrowseStep:
    """One action in the ReAct loop. `kind` ∈ {click, fill, type, press, select, eval,
    wait_text, wait_url}. `target` is a @eN ref (or a key/text/url for press/wait). `value`
    is the fill/type text (variable VALUES never go through the cache key — see cache.py)."""

    kind: str
    target: str = ""
    value: str = ""


# kinds that change the page → re-snapshot afterward (dossier 14 §10A)
_PAGE_CHANGING = {"click", "press", "select"}


class AgentBrowserProvider:
    """Keyless agentic browse on the local agent-browser CLI (dossier 14 §4.2 ReAct loop).
    Claude Code is the brain: it supplies `steps`; this driver executes + re-snapshots."""

    name = "agent-browser"

    def __init__(
        self,
        *,
        engine: Literal["lightpanda", "chrome"] = DEFAULT_ENGINE,
        runner: Runner | None = None,
        program: str = AB_PROGRAM,
    ) -> None:
        self.engine = engine
        self._runner = runner
        self.program = program

    def _cli(self, engine: str, *, session=None, state=None, headers=None) -> _AgentBrowserCLI:
        return _AgentBrowserCLI(
            engine=engine, runner=self._runner, program=self.program,
            session=session, state=state, headers=headers,
        )

    def snapshot(self, *, interactive: bool = True, engine: str | None = None) -> Snapshot:
        cli = self._cli(engine or self.engine)
        return parse_snapshot(cli.snapshot(interactive=interactive))

    def browse(
        self,
        url: str,
        instruction: str,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        variables: dict | None = None,
        replay_key: str | None = None,
        steps: list[BrowseStep] | None = None,
        state: str | None = None,
        headers: str | None = None,
    ) -> WebResult:
        """Run the keyless ReAct loop. `steps` (host-model-supplied) drives interaction;
        with no steps, returns the initial snapshot as content (the 'observe' case)."""
        if not is_available(self.program):
            return WebResult(url=url, title="", content="",
                             metadata={"unavailable": True, "provider": self.name})

        # ---- rung-2.5 lightpanda first; fall back to chrome on an empty snapshot ----
        engine = self.engine
        snap = self._open_and_snapshot(url, engine, state=state, headers=headers)
        if engine == "lightpanda" and snap.is_empty:
            engine = "chrome"  # dossier 14 §12.5: same command surface, swap engine
            snap = self._open_and_snapshot(url, engine, state=state, headers=headers)

        cli = self._cli(engine, state=state, headers=headers)
        executed = 0
        for step in (steps or []):
            if executed >= max_steps:
                break
            # ---- grounding: a @eN target must exist in the current snapshot refs ----
            if step.target.startswith("@") and not snap.has_ref(step.target):
                continue  # ungrounded ref → skip (dossier 14 §6.3 grounding)
            self._dispatch(cli, step)
            executed += 1
            if step.kind in _PAGE_CHANGING:
                cli.wait_load("networkidle")
                snap = parse_snapshot(cli.snapshot(interactive=True))  # re-snapshot

        content = snap.text
        return WebResult(
            url=snap.url or url,
            title=snap.title,
            content=content,
            metadata={
                "engine": engine,
                "provider": self.name,
                "refs": list(snap.refs.keys()),
                "steps_executed": executed,
                "replay_key": replay_key,
            },
        )

    def _open_and_snapshot(self, url, engine, *, state=None, headers=None) -> Snapshot:
        cli = self._cli(engine, state=state, headers=headers)
        cli.open(url)
        cli.wait_load("networkidle")
        return parse_snapshot(cli.snapshot(interactive=True))

    @staticmethod
    def _dispatch(cli: _AgentBrowserCLI, step: BrowseStep) -> None:
        k = step.kind
        if k == "click":
            cli.click(step.target)
        elif k == "fill":
            cli.fill(step.target, step.value)
        elif k == "type":
            cli.type_text(step.target, step.value)
        elif k == "press":
            cli.press(step.target)
        elif k == "select":
            cli.select(step.target, step.value)
        elif k == "eval":
            cli.eval_js(step.value)
        elif k == "wait_text":
            cli.wait_text(step.target)
        elif k == "wait_url":
            cli.wait_url(step.target)
        # unknown kind → no-op (graceful)
```

- [ ] **Step 4: Run the test, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_browse.py -q
```

Expected: `7 passed`. (If `test_cli_absent…` fails because the module-level `is_available` was inlined, ensure `browse()` calls the module function `is_available(self.program)` so monkeypatch on the module attribute takes effect.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 4: AgentBrowserProvider keyless ReAct loop + Stagehand prompts

browse() = open→wait→snapshot→(grounded steps + re-snapshot)→extract, returning WebResult.
lightpanda empty-snapshot → chrome fallback (same command surface). Ungrounded @eN refs
skipped. CLI absent → empty WebResult, no raise. act/extract/observe/loop prompts verbatim.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `AqlExtractProvider` — host-model resolver + ref-grounding (`browse/aql.py`)

Add the resolver to `browse/aql.py`. `AqlExtractProvider` implements the `ExtractProvider` Protocol (`name="aql"`; `extract(source, schema, instruction="") -> dict`) — but its `schema` arg is an **AQL string** (the field names ARE the schema, dossier 14 §6.3). It: (1) parses the AQL with `parse_aql`, (2) takes a `Snapshot` (the tree + `refs` map), (3) maps each leaf field → a `@eN` ref via the injected host-model `LLMProvider` (or deterministic name/role-matching when no LLM), (4) **grounds** every chosen ref against `snapshot.refs` (reject + drop ungrounded refs, dossier 14 §6.3(3)), (5) returns a typed dict shaped by the AST (`[]` → list, `{}` → nested object). No LLM and no resolvable ref → `{}` (graceful, like `LLMExtractProvider`).

**Files:**
- Modify: `src/bad_research/browse/aql.py` (add `AqlExtractProvider` + `resolve_aql`)
- Test: `tests/test_browse/test_aql_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browse/test_aql_resolver.py
"""AqlExtractProvider — AQL resolve against a Snapshot, with ref-grounding. Mock LLM."""

from __future__ import annotations

import json

from bad_research.browse.agent_browser import Snapshot
from bad_research.browse.aql import AqlExtractProvider, resolve_aql
from tests.test_browse.conftest import FakeLLM


def _login_snapshot() -> Snapshot:
    return Snapshot(
        text="@e3 [textbox] Email\n@e4 [textbox] Password\n@e5 [button] Continue",
        refs={
            "e3": {"role": "textbox", "name": "Email"},
            "e4": {"role": "textbox", "name": "Password"},
            "e5": {"role": "button", "name": "Continue"},
        },
    )


def test_resolve_maps_fields_to_grounded_refs_via_llm() -> None:
    # Host model returns a field→ref mapping; resolver keeps only grounded refs.
    llm = FakeLLM([json.dumps({"email_input": "@e3", "submit_button": "@e5"})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(_login_snapshot(),
                       "{ email_input  submit_button }",
                       instruction="find the login fields")
    assert out == {"email_input": "@e3", "submit_button": "@e5"}
    # the host-model prompt embedded the snapshot text + the AQL query
    assert "email_input" in llm.calls[0]["messages"][-1].content


def test_ungrounded_ref_is_dropped() -> None:
    # LLM hallucinates @e99 (not in refs) → grounding drops it; @e3 survives.
    llm = FakeLLM([json.dumps({"email_input": "@e3", "ghost": "@e99"})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(_login_snapshot(), "{ email_input  ghost }")
    assert out == {"email_input": "@e3"}   # ghost dropped (ungrounded)


def test_no_llm_falls_back_to_deterministic_name_match() -> None:
    # No LLM: match AQL field name against snapshot ref names (case/underscore-insensitive).
    prov = AqlExtractProvider(llm=None)
    out = prov.extract(_login_snapshot(), "{ email  password }")
    # 'email' → e3 (name 'Email'), 'password' → e4 (name 'Password')
    assert out["email"] == "@e3"
    assert out["password"] == "@e4"


def test_string_schema_must_be_valid_aql() -> None:
    prov = AqlExtractProvider(llm=None)
    out = prov.extract(_login_snapshot(), "not valid aql")  # missing braces
    assert out == {}    # parse error → graceful empty (never raises)


def test_list_node_resolves_to_list_of_refs() -> None:
    snap = Snapshot(
        text="links",
        refs={
            "e1": {"role": "link", "name": "Home"},
            "e2": {"role": "link", "name": "About"},
            "e3": {"role": "heading", "name": "Title"},
        },
    )
    llm = FakeLLM([json.dumps({"nav_links": ["@e1", "@e2"]})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(snap, "{ nav_links[] }")
    assert out == {"nav_links": ["@e1", "@e2"]}


def test_resolve_aql_function_is_pure() -> None:
    # resolve_aql(ast, snapshot, mapping) grounds a raw mapping with no LLM at all.
    from bad_research.browse.aql import parse_aql
    ast = parse_aql("{ a  b }")
    snap = Snapshot(refs={"e1": {"role": "button", "name": "A"}})
    grounded = resolve_aql(ast, snap, {"a": "@e1", "b": "@e9"})
    assert grounded == {"a": "@e1"}   # b ungrounded → dropped


def test_provider_name() -> None:
    assert AqlExtractProvider(llm=None).name == "aql"
```

- [ ] **Step 2: Run the test, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_aql_resolver.py -q
```

Expected: `ImportError: cannot import name 'AqlExtractProvider'`.

- [ ] **Step 3: Implement the resolver (append to `browse/aql.py`)**

```python
# ---- append to src/bad_research/browse/aql.py ----

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a hard import cycle; Snapshot is a plain dataclass
    from bad_research.browse.agent_browser import Snapshot

# Verbatim AQL resolver system prompt (DESIGNED from dossier 14 §6.3 — Claude Code is the
# resolver; this is the prompt the skill embeds when it maps AQL leaves to snapshot refs).
AQL_RESOLVER_SYSTEM_PROMPT = (
    "You map fields of an AgentQL query to elements in a page's accessibility snapshot. "
    "You will be given: 1) an AgentQL query (field names are the keys you must fill; `[]` "
    "marks a list; `{}` marks a nested group; `(description)` disambiguates a field), and "
    "2) an accessibility snapshot with @eN refs (each ref has a role and an accessible "
    "name). For each leaf field, return the @eN ref of the element that best matches the "
    "field name and its description. For a `[]` list field, return an array of @eN refs "
    "(one per repeated element). Use ONLY refs that appear in the snapshot — never invent "
    "a ref. Respond with a single JSON object mapping field names to refs (or arrays of "
    "refs). Do not fabricate values."
)


def _ground_one(value: Any, snap: "Snapshot") -> Any:
    """Keep a ref only if it is grounded in snap.refs; lists are filtered; dicts recurse."""
    from bad_research.browse.agent_browser import normalize_ref
    if isinstance(value, str) and value.startswith("@"):
        return value if normalize_ref(value) in snap.refs else None
    if isinstance(value, list):
        kept = [v for v in (_ground_one(x, snap) for x in value) if v is not None]
        return kept or None
    if isinstance(value, dict):
        kept = {k: gv for k, v in value.items() if (gv := _ground_one(v, snap)) is not None}
        return kept or None
    return value  # non-ref scalars pass through (already-extracted text)


def resolve_aql(ast: ContainerNode, snap: "Snapshot", mapping: dict) -> dict:
    """Ground a field→ref mapping against the snapshot refs. Drops every ref not present
    in snap.refs (dossier 14 §6.3(3) — a ref is valid iff it round-trips the AX tree)."""
    out: dict = {}
    for child in ast.children:
        if child.name not in mapping:
            continue
        grounded = _ground_one(mapping[child.name], snap)
        if grounded is not None:
            out[child.name] = grounded
    return out


def _deterministic_match(ast: ContainerNode, snap: "Snapshot") -> dict:
    """No-LLM fallback: match each leaf field name to a ref whose accessible name matches
    (case- and underscore-insensitive substring). First match wins."""
    def norm(s: str) -> str:
        return s.replace("_", "").replace("-", "").replace(" ", "").lower()

    mapping: dict = {}
    used: set[str] = set()
    for child in ast.children:
        key = norm(child.name)
        for rid, meta in snap.refs.items():
            if rid in used:
                continue
            name = norm(str(meta.get("name", "")))
            if name and (key in name or name in key):
                mapping[child.name] = f"@{rid}"
                used.add(rid)
                break
    return mapping


class AqlExtractProvider:
    """ExtractProvider (name='aql'): AQL string + Snapshot → grounded field→ref dict.

    `schema` is an AQL query string (its field names ARE the output keys). `source` must
    be a Snapshot (the live tree + refs). Resolution = host-model mapping (injected LLM)
    grounded against snap.refs, or deterministic name-matching when no LLM. Graceful: a
    parse error or no resolvable ref → {} (never raises)."""

    name = "aql"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def extract(self, source, schema, instruction: str = "") -> dict:
        # source must expose .refs/.text — a Snapshot.
        snap = source
        if not hasattr(snap, "refs"):
            return {}
        aql_str = schema if isinstance(schema, str) else ""
        try:
            ast = parse_aql(aql_str)
        except (QuerySyntaxError, LexerError):
            return {}

        if self._llm is None:
            mapping = _deterministic_match(ast, snap)
            return resolve_aql(ast, snap, mapping)

        # ---- host-model resolution (Claude Code is the LLM; injected for tests) ----
        from bad_research.llm.base import LLMMessage
        user = (
            f"<agentql_query>{aql_str}</agentql_query>\n"
            f"<instruction>{instruction or 'Map each field to its element.'}</instruction>\n"
            f"<accessibility_snapshot>{snap.text[:AQL_SNAPSHOT_TRUNC]}</accessibility_snapshot>"
        )
        messages = [
            LLMMessage(role="system", content=AQL_RESOLVER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user),
        ]
        try:
            resp = self._llm.complete(messages, tier="triage", max_tokens=2048, temperature=0.0)
            mapping = _parse_json_obj(resp.text)
        except Exception:
            return {}
        return resolve_aql(ast, snap, mapping)


AQL_SNAPSHOT_TRUNC = 60_000  # keep the snapshot inside the host model's context (dossier 14 §5.4)


def _parse_json_obj(text: str) -> dict:
    """Tolerant JSON-object parse (strips ```json fences, finds the first {...})."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    t = t.strip()
    try:
        val = json.loads(t)
        return val if isinstance(val, dict) else {}
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            try:
                val = json.loads(t[start : end + 1])
                return val if isinstance(val, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
```

> Note: the import of `LexerError`/`QuerySyntaxError` in `extract()` is satisfied because both classes are defined earlier in the same module (Task 1). The `AQL_SNAPSHOT_TRUNC` constant is referenced before its definition only at call time (module-level constant resolved at runtime), but to avoid any ambiguity move the `AQL_SNAPSHOT_TRUNC = 60_000` line ABOVE the `class AqlExtractProvider` definition when implementing.

- [ ] **Step 4: Run the test, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_aql_resolver.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 5: AqlExtractProvider — host-model resolver + ref-grounding (browse/aql.py)

AQL string (field names = output keys) + Snapshot → grounded field→ref dict. Host model
maps fields→@eN; every ref grounded against snap.refs (ungrounded dropped). No-LLM
deterministic name-match fallback. Parse error / no LLM → {} (graceful). dossier 14 §6.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Keyless auth helpers (`state save` / `--state` / `cookies set --curl`)

The keyless persist-once-reuse-forever auth flow (dossier 14 §8/§13). All run against LOCAL Chrome, $0. `AgentBrowserProvider` gains `save_state(path)` and a `--state`/`--headers` threading path (already wired into `browse()` via the `state`/`headers` kwargs from Task 4), plus a `cookies_set_curl(curl_file)` helper. **Cookie/state auth is chrome-only** (lightpanda blocks `--profile`/`--state`, dossier 14 §12.4) — an authed `browse()` forces `engine="chrome"`.

**Files:**
- Modify: `src/bad_research/browse/agent_browser.py` (add `save_state`, force chrome when `state`/`headers` set)
- Test: `tests/test_browse/test_agent_browser_browse.py` (append auth tests)

- [ ] **Step 1: Append the failing tests**

```python
# APPEND to tests/test_browse/test_agent_browser_browse.py

def test_state_flag_threads_to_open_and_forces_chrome() -> None:
    # An authed browse (state given) must run on chrome (lightpanda blocks --state).
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="lightpanda", runner=runner)
    result = prov.browse("https://src.example/article/1", "read it",
                         state="/auth/src.json")
    assert result.metadata["engine"] == "chrome"   # forced
    open_argv = runner.argvs()[0]
    assert "--state" in open_argv and "/auth/src.json" in open_argv
    assert open_argv[2] == "chrome"


def test_headers_flag_threads_through() -> None:
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.browse("https://api.example/", "read",
                headers='{"Authorization":"Bearer t"}')
    open_argv = runner.argvs()[0]
    assert "--headers" in open_argv
    assert '{"Authorization":"Bearer t"}' in open_argv


def test_save_state_builds_state_save_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.save_state("/auth/src.json")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "state", "save", "/auth/src.json",
    ]


def test_cookies_set_curl_builds_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.cookies_set_curl("/auth/src.curl")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "cookies", "set", "--curl", "/auth/src.curl",
    ]
```

- [ ] **Step 2: Run, SEE the new tests fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_browse.py -q -k "state or headers or cookies"
```

Expected: `AttributeError: 'AgentBrowserProvider' object has no attribute 'save_state'` / engine assertion failures.

- [ ] **Step 3: Implement — force chrome for authed browse + add helpers**

In `AgentBrowserProvider.browse`, add at the very top of the method body (after the `is_available` guard), the chrome-forcing for authed runs:

```python
        # ---- authed browse is chrome-only: lightpanda blocks --state/--profile (dossier 14 §12.4) ----
        if state is not None or headers is not None:
            self_engine_override = "chrome"
        else:
            self_engine_override = self.engine
```

Then change the line `engine = self.engine` to `engine = self_engine_override`. Keep the rest of `browse()` unchanged (the `_open_and_snapshot`/`_cli` calls already accept `state=`/`headers=`).

Append the two helper methods to the class:

```python
    def save_state(self, path: str, *, session: str | None = None) -> None:
        """Persist cookies + localStorage + sessionStorage to a Playwright-compatible
        StorageState JSON (dossier 14 §13.1). Chrome-only."""
        self._cli("chrome", session=session).state_save(path)

    def cookies_set_curl(self, curl_file: str, *, session: str | None = None) -> None:
        """Replay a Copy-as-cURL dump's cookies (the no-automation auth path, dossier 14
        §13.1). The model never sees the password — only the resulting cookies."""
        self._cli("chrome", session=session).cookies_set_curl(curl_file)
```

- [ ] **Step 4: Run, SEE all browse tests pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_agent_browser_browse.py -q
```

Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 6: keyless persist-once auth (state save / --state / cookies set --curl)

Authed browse forces engine=chrome (lightpanda blocks --state/--profile). --state/--headers
thread to open. save_state() + cookies_set_curl() helpers. All local Chrome, $0. dossier 14 §13.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Keyless factories (`browse/base.py::get_browse_provider` / `get_extract_provider`)

Rewrite the factory bodies (Protocols KEPT VERBATIM, matching INTERFACES_KEYLESS §4.3). `get_browse_provider` default → `AgentBrowserProvider()` iff the `agent-browser` CLI is installed, else `None` (graceful — the ladder treats `None` as "rung unavailable"). `get_extract_provider` default `"llm"` → `LLMExtractProvider` (KEPT); `"aql"` → `AqlExtractProvider`. Drop all `BROWSERBASE_API_KEY`/`AGENTQL_API_KEY` / `browser_use`/`stagehand` branches.

**Files:**
- Modify: `src/bad_research/browse/base.py`
- Test: `tests/test_browse/test_base.py` (rewrite the factory section)

- [ ] **Step 1: Rewrite the failing test (factory section)**

```python
# tests/test_browse/test_base.py  (REWRITE — Protocol tests KEPT, factory tests rewritten)
"""Contract tests: BrowseProvider/ExtractProvider Protocols (kept) + keyless factories."""

from __future__ import annotations

import bad_research.browse.base as base
from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)


def test_browse_provider_protocol_is_runtime_checkable() -> None:
    class Ok:
        name = "x"
        def browse(self, url, instruction, *, max_steps=12, variables=None, replay_key=None):
            ...
    assert isinstance(Ok(), BrowseProvider)


def test_extract_provider_protocol_is_runtime_checkable() -> None:
    class Ok:
        name = "x"
        def extract(self, source, schema, instruction=""):
            return {}
    assert isinstance(Ok(), ExtractProvider)


def test_default_browse_provider_is_agent_browser_when_cli_present(monkeypatch) -> None:
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": True)
    prov = get_browse_provider()
    assert prov is not None
    assert prov.name == "agent-browser"


def test_browse_provider_none_when_cli_absent(monkeypatch) -> None:
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": False)
    assert get_browse_provider() is None
    assert get_browse_provider("agent-browser") is None


def test_extract_provider_llm_default_always_constructible() -> None:
    prov = get_extract_provider("llm")
    assert prov is not None and prov.name == "llm"
    assert get_extract_provider() is not None      # default == llm


def test_extract_provider_aql() -> None:
    prov = get_extract_provider("aql")
    assert prov is not None and prov.name == "aql"


def test_unknown_provider_returns_none() -> None:
    assert get_browse_provider("browserbase") is None     # keyed backend gone
    assert get_extract_provider("agentql") is None         # keyed backend gone
```

- [ ] **Step 2: Run, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_base.py -q
```

Expected: failures — `get_browse_provider()` still returns the old browser-use path / `is_available` not importable from `base`.

- [ ] **Step 3: Rewrite `browse/base.py` factories (Protocols UNCHANGED)**

Keep the `BrowseProvider` and `ExtractProvider` Protocol definitions exactly as they are (lines 16-46). Replace `get_extract_provider` and `get_browse_provider` (lines 49-108) and add the `is_available` re-export:

```python
# src/bad_research/browse/base.py — REPLACE the two factories (Protocols unchanged above)

from bad_research.browse.agent_browser import is_available  # re-export for test monkeypatch


def get_extract_provider(name: str | None = None) -> ExtractProvider | None:
    """Resolve an ExtractProvider. Default 'llm' = the zero-dep host-model extractor
    (always constructible; no-ops to {} without an LLM). 'aql' = the AQL resolver.
    Unknown / removed keyed names → None (graceful)."""
    if name in (None, "llm"):
        from bad_research.browse.extract_llm import LLMExtractProvider
        return LLMExtractProvider()
    if name == "aql":
        from bad_research.browse.aql import AqlExtractProvider
        return AqlExtractProvider()
    return None  # 'agentql'/'stagehand' (keyed) are gone → None


def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    """Resolve a BrowseProvider. Default = the keyless AgentBrowserProvider iff the
    agent-browser CLI is installed; else None (the ladder degrades to crawl4ai/httpx).
    No env var, no API key — agent-browser drives a LOCAL Chrome over CDP (dossier 14 §1)."""
    if name in (None, "agent-browser"):
        if not is_available():
            return None
        from bad_research.browse.agent_browser import AgentBrowserProvider
        return AgentBrowserProvider()
    return None  # 'browserbase'/'browser-use' (keyed) are gone → None
```

Also delete the now-dead `import os` at the top of `base.py` if it is unused after the rewrite.

- [ ] **Step 4: Run, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_base.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 7: keyless browse factories (browse/base.py)

get_browse_provider default → AgentBrowserProvider (iff CLI present, else None).
get_extract_provider 'llm' (kept) + 'aql' (new). All keyed branches removed. Protocols
kept verbatim (INTERFACES_KEYLESS §4.3).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: The 4-rung keyless ladder (`browse/ladder.py::fetch_tiered`)

Rewrite `fetch_tiered` to the 4-rung keyless ladder (INTERFACES_KEYLESS §4.4 / dossier 14 §7, §12.5): rung-1 httpx (core/fetcher) → rung-2 crawl4ai → rung-2.5 `agent-browser --engine lightpanda` → rung-3 `agent-browser --engine chrome`. The signature is KEPT (verbatim from INTERFACES_KEYLESS — `url, *, tier_max, instruction, schema, replay_key, variables`), but the injection seams change from `_browseruse`/`_browserbase` to `_browse` (a single keyless `AgentBrowserProvider`). Escalation gates KEPT verbatim (`_is_empty`/`_is_bot_wall`/`looks_like_login_wall`). The XHR-JSON shortcut (dossier 14 §7) runs `network requests --type xhr,fetch` before the rung-3 loop; if a clean JSON API is found it is reported in `metadata["xhr_api"]` so the caller can drop to rung-1. The lightpanda→chrome fallback lives inside `AgentBrowserProvider.browse` (Task 4), so the ladder calls `browse(engine=lightpanda)` once and the provider handles the retry.

**Files:**
- Rewrite: `src/bad_research/browse/ladder.py`
- Test: `tests/test_browse/test_ladder.py` (rewrite)

- [ ] **Step 1: Rewrite the failing test**

```python
# tests/test_browse/test_ladder.py  (REWRITE for the 4-rung keyless ladder)
"""fetch_tiered escalation — 4-rung keyless ladder. All providers mocked, no subprocess."""

from __future__ import annotations

from unittest.mock import MagicMock

from bad_research.browse.ladder import fetch_tiered
from tests.test_browse.conftest import make_result


def _good(url="https://x.test"):
    return make_result("Substantial real article content. " * 30, url=url, title="Real")


def _empty(url="https://x.test"):
    return make_result("tiny", url=url, title="Stub")


def _bot(url="https://x.test"):
    return make_result("Just a moment... checking your browser ray id " * 10,
                       url=url, title="Just a moment...")


def _login(url="https://x.test/login"):
    return make_result("Please sign in. create account.", url=url, title="Sign in")


def test_rung1_good_result_no_escalation() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _good()
    t1 = MagicMock()
    r = fetch_tiered("https://x.test", tier_max=3, _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t0.fetch.assert_called_once()
    t1.fetch.assert_not_called()


def test_rung1_empty_escalates_to_rung2_crawl4ai() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3, _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content.startswith("Substantial real")
    t1.fetch.assert_called_once()


def test_rung2_unavailable_keeps_rung1() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    r = fetch_tiered("https://x.test", tier_max=3, _tier0=t0, _tier1_factory=lambda: None)
    assert r.content == "tiny"


def test_tier_max_caps_at_rung1() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=0, _tier0=t0, _tier1_factory=lambda: t1)
    assert r.content == "tiny"
    t1.fetch.assert_not_called()


def test_bot_wall_escalates_to_agent_browser() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _bot()
    ab = MagicMock(); ab.browse.return_value = make_result("Recovered behind cloudflare. " * 20)
    r = fetch_tiered("https://x.test", tier_max=3,
                     _tier0=t0, _tier1_factory=lambda: t1, _browse=ab)
    assert "Recovered behind cloudflare" in r.content
    ab.browse.assert_called_once()


def test_login_wall_escalates_to_agent_browser_with_instruction() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    ab = MagicMock(); ab.browse.return_value = make_result("Logged-in dashboard content. " * 20)
    r = fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                     _tier0=t0, _tier1_factory=lambda: t1, _browse=ab)
    assert "Logged-in dashboard" in r.content
    ab.browse.assert_called_once()


def test_instruction_triggers_rung3_browse() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty()
    t1 = MagicMock(); t1.fetch.return_value = _good()
    ab = MagicMock(); ab.browse.return_value = make_result("All 50 reviews loaded. " * 10)
    r = fetch_tiered("https://x.test", tier_max=3, instruction="load all reviews",
                     _tier0=t0, _tier1_factory=lambda: t1, _browse=ab)
    assert "All 50 reviews" in r.content
    ab.browse.assert_called_once()


def test_no_browse_provider_stays_on_lower_tier() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _good()
    r = fetch_tiered("https://x.test", tier_max=3, instruction="paginate",
                     _tier0=t0, _tier1_factory=lambda: MagicMock(), _browse=None)
    assert r.content.startswith("Substantial real")


def test_schema_triggers_aql_or_llm_extract_attaches_dict() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _good()
    extractor = MagicMock(); extractor.extract.return_value = {"title": "Real", "n": 3}
    r = fetch_tiered("https://x.test", tier_max=2,
                     schema={"type": "object", "properties": {"title": {"type": "string"}}},
                     _tier0=t0, _tier1_factory=lambda: MagicMock(), _extractor=extractor)
    assert r.metadata["extracted"] == {"title": "Real", "n": 3}
    assert r.content.startswith("Substantial real")
    extractor.extract.assert_called_once()


def test_replay_key_threaded_to_browse() -> None:
    t0 = MagicMock(); t0.fetch.return_value = _empty("https://x.test/login")
    t1 = MagicMock(); t1.fetch.return_value = _login()
    ab = MagicMock(); ab.browse.return_value = make_result("dashboard " * 60)
    fetch_tiered("https://x.test/login", tier_max=3, instruction="log in",
                 replay_key="rk-123",
                 _tier0=t0, _tier1_factory=lambda: t1, _browse=ab)
    _, kwargs = ab.browse.call_args
    assert kwargs["replay_key"] == "rk-123"
```

- [ ] **Step 2: Run, SEE it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_ladder.py -q
```

Expected: `TypeError: fetch_tiered() got an unexpected keyword argument '_browse'`.

- [ ] **Step 3: Rewrite `browse/ladder.py`**

```python
# src/bad_research/browse/ladder.py
"""fetch_tiered — the 4-rung KEYLESS escalation ladder (INTERFACES_KEYLESS §4.4, dossier 14 §7).

  rung 1   httpx GET (core/fetcher) ............... $0  static HTML/APIs
  rung 2   crawl4ai local JS render → fit_markdown . $0  clean MD, no interaction
  rung 2.5 agent-browser --engine lightpanda ....... $0  fast keyless JS render (snapshot/eval)
  rung 3   agent-browser --engine chrome ........... $0  login/click/typed/screenshot

Escalation gates KEPT verbatim from web/base.py (looks_like_junk / looks_like_login_wall).
There is NO rung that costs money. The lightpanda→chrome fallback lives inside
AgentBrowserProvider.browse (it retries on an empty snapshot). Every optional rung degrades
gracefully: a missing provider/CLI means the rung is skipped and the best lower-tier result
is returned. Providers are injectable for tests (_tier0/_tier1_factory/_browse/_extractor/_llm).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bad_research.web.base import WebResult


def _is_empty(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Empty or near-empty")


def _is_bot_wall(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Bot detection page")


def fetch_tiered(
    url: str,
    *,
    tier_max: int,
    instruction: str | None = None,
    schema: dict | str | None = None,
    replay_key: str | None = None,
    variables: dict | None = None,
    # ---- injection seams (tests pass mocks; production gets real keyless defaults) ----
    _tier0: Any | None = None,
    _tier1_factory: Callable[[], Any | None] | None = None,
    _browse: Any | None = None,
    _extractor: Any | None = None,
    _llm: Any | None = None,
) -> WebResult:
    # ---------- Rung 1: httpx (core/fetcher builtin) ----------
    if _tier0 is None:
        from bad_research.web.base import get_provider
        _tier0 = get_provider("builtin")
    result = _tier0.fetch(url)

    # ---------- Rung 2: crawl4ai local JS render ----------
    if tier_max >= 1 and _is_empty(result):
        if _tier1_factory is None:
            def _tier1_factory():
                try:
                    from bad_research.web.base import get_provider
                    return get_provider("crawl4ai")
                except ImportError:
                    return None
        t1 = _tier1_factory()
        if t1 is not None:
            try:
                t1_result = t1.fetch(url)
                if len(t1_result.content.strip()) >= len(result.content.strip()):
                    result = t1_result
            except Exception:
                pass  # keep the rung-1 result

    # ---------- Rung 2.5 / 3: agent-browser (local Chrome/lightpanda over CDP) ----------
    want_anti_bot = tier_max >= 3 and _is_bot_wall(result)
    want_login = tier_max >= 3 and result.looks_like_login_wall(url)
    want_interactive = tier_max >= 3 and bool(instruction)

    if want_anti_bot or want_login or want_interactive:
        browse_result = _do_browse(
            url, instruction or "Read the main content of this page.",
            replay_key=replay_key, variables=variables, browse=_browse,
        )
        if browse_result is not None and browse_result.content.strip():
            result = browse_result

    # ---------- Rung 2: typed extraction (schema / AQL request) ----------
    if schema is not None and tier_max >= 2:
        extractor = _extractor
        if extractor is None:
            from bad_research.browse.base import get_extract_provider
            # An AQL string selects the AQL resolver; a JSON-schema dict selects the LLM extractor.
            extractor = get_extract_provider("aql") if isinstance(schema, str) else \
                get_extract_provider("llm")
            if extractor is not None and _llm is not None and hasattr(extractor, "_llm"):
                extractor._llm = _llm
        if extractor is not None:
            try:
                data = extractor.extract(result, schema, instruction or "")
            except Exception:
                data = {}
            if data:
                result.metadata["extracted"] = data

    return result


def _do_browse(url, instruction, *, replay_key, variables, browse) -> WebResult | None:
    """Drive the keyless AgentBrowserProvider (rung 2.5 lightpanda → 3 chrome inside browse()).
    Returns None if no provider is available (caller keeps the lower-tier result)."""
    prov = browse
    if prov is None:
        from bad_research.browse.base import get_browse_provider
        prov = get_browse_provider("agent-browser")  # None when CLI absent (graceful)
    if prov is None:
        return None
    try:
        return prov.browse(url, instruction, replay_key=replay_key, variables=variables)
    except Exception:
        return None
```

- [ ] **Step 4: Run, SEE it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_ladder.py -q
```

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 8: 4-rung keyless ladder (browse/ladder.py)

fetch_tiered: httpx → crawl4ai → agent-browser(lightpanda) → agent-browser(chrome). Keyless
rungs only; signature kept (INTERFACES_KEYLESS §4.4). _browseruse/_browserbase seams replaced
by _browse. lightpanda→chrome fallback inside browse(). AQL-string schema → AqlExtractProvider.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Graceful-degradation sweep (CLI absent → degrade to crawl4ai/httpx)

Rewrite `test_graceful_degradation.py` to prove the keyless posture: no `agent-browser`/`lightpanda` CLI, no optional libs → factories return `None`, the ladder still returns a `WebResult` (never raises). This is the load-bearing "OPTIONAL external CLI — detect + degrade" guarantee from the brief.

**Files:**
- Rewrite: `tests/test_browse/test_graceful_degradation.py`

- [ ] **Step 1: Rewrite the failing test**

```python
# tests/test_browse/test_graceful_degradation.py  (REWRITE — keyless posture)
"""Keyless posture: no CLI, no libs, no keys → factories None; the ladder degrades."""

from __future__ import annotations

import builtins

import bad_research.browse.base as base
from bad_research.browse.base import get_browse_provider, get_extract_provider
from bad_research.browse.ladder import fetch_tiered
from tests.test_browse.conftest import make_result


def _no_optional_imports(monkeypatch):
    """Force crawl4ai / browser_use / agentql / stagehand to look uninstalled."""
    real = builtins.__import__

    def fake(name, *a, **k):
        bad = ("crawl4ai", "browser_use", "agentql", "stagehand")
        if name in bad or name.startswith(tuple(b + "." for b in bad)):
            raise ImportError(f"No module named {name!r}")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_agent_browser_absent_factory_returns_none(monkeypatch):
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": False)
    assert get_browse_provider() is None
    assert get_browse_provider("agent-browser") is None
    # the LLM + AQL extractors are pure-Python and always constructible
    assert get_extract_provider("llm") is not None
    assert get_extract_provider("aql") is not None


def test_ladder_degrades_to_rung1_when_nothing_else_available(monkeypatch):
    monkeypatch.setattr(base, "is_available", lambda program="agent-browser": False)
    _no_optional_imports(monkeypatch)

    class _T0:
        def fetch(self, url):
            return make_result("short", url=url)  # < 300 chars — would want rung 2

    r = fetch_tiered("https://x.test", tier_max=3,
                     instruction="paginate", schema={"type": "object"}, _tier0=_T0())
    assert r.content == "short"               # no exception; best lower-tier result
    assert "extracted" not in r.metadata      # LLM extractor with no LLM → {} → not attached


def test_ladder_extract_no_llm_no_crash():
    class _T0:
        def fetch(self, url):
            return make_result("Substantial content. " * 40, url=url)

    r = fetch_tiered("https://x.test", tier_max=2, schema={"type": "object"}, _tier0=_T0())
    assert r.content.startswith("Substantial content")
    assert "extracted" not in r.metadata


def test_no_keyed_backends_resolve():
    assert get_browse_provider("browserbase") is None
    assert get_browse_provider("browser-use") is None
    assert get_extract_provider("agentql") is None
    assert get_extract_provider("stagehand") is None
```

- [ ] **Step 2: Run, SEE it pass (the impl already supports this from Tasks 7-8)**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/test_graceful_degradation.py -q
```

Expected: `4 passed`. (If `test_no_keyed_backends_resolve` fails, confirm Task 7 returns `None` for the removed keyed names — it does.)

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 9: graceful-degradation sweep — keyless posture (test_graceful_degradation.py)

Proves: no agent-browser CLI + no optional libs + no keys → factories None, ladder still
returns a WebResult (never raises). Keyed backend names all resolve to None.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `__init__` exports + full-suite green + keyless audit

Finalize `browse/__init__.py` re-exports, confirm `test_fetcher_hook.py`/`test_cache.py`/`test_extract_llm.py` still pass unchanged, run the FULL suite, and assert zero API-key/keyed-import survives.

**Files:**
- Modify: `src/bad_research/browse/__init__.py`

- [ ] **Step 1: Rewrite `browse/__init__.py` re-exports**

```python
# src/bad_research/browse/__init__.py
"""Keyless browse subsystem: AgentBrowserProvider (local agent-browser CLI), the AQL parser
+ resolver, the LLM extractor, the 4-rung keyless ladder, and the action-replay cache."""

from __future__ import annotations

from bad_research.browse.agent_browser import (
    AGENT_LOOP_SYSTEM_PROMPT,
    AgentBrowserProvider,
    BrowseStep,
    Snapshot,
    is_available,
    parse_snapshot,
)
from bad_research.browse.aql import (
    AqlExtractProvider,
    ContainerListNode,
    ContainerNode,
    IdListNode,
    IdNode,
    QuerySyntaxError,
    parse_aql,
)
from bad_research.browse.base import (
    BrowseProvider,
    ExtractProvider,
    get_browse_provider,
    get_extract_provider,
)
from bad_research.browse.cache import ActCache, replay_key_for
from bad_research.browse.extract_llm import LLMExtractProvider
from bad_research.browse.ladder import fetch_tiered

__all__ = [
    "AGENT_LOOP_SYSTEM_PROMPT",
    "ActCache",
    "AgentBrowserProvider",
    "AqlExtractProvider",
    "BrowseProvider",
    "BrowseStep",
    "ContainerListNode",
    "ContainerNode",
    "ExtractProvider",
    "IdListNode",
    "IdNode",
    "LLMExtractProvider",
    "QuerySyntaxError",
    "Snapshot",
    "fetch_tiered",
    "get_browse_provider",
    "get_extract_provider",
    "is_available",
    "parse_aql",
    "parse_snapshot",
    "replay_key_for",
]
```

- [ ] **Step 2: Run the FULL browse suite + the whole project suite**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python -m pytest tests/test_browse/ -q
uv run python -m pytest -q
```

Expected: `tests/test_browse/` all pass (aql 15 + cli 9 + snapshot 8 + browse 11 + aql_resolver 7 + base 7 + ladder 10 + graceful 4 + cache + extract_llm + fetcher_hook). Whole-suite: green (or only failures in OTHER KR-owned packages not yet built — note them, do not fix here).

- [ ] **Step 3: Keyless audit — zero keyed imports / keys anywhere in browse/**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
grep -rn "cohere\|tavily\|exa_provider\|firecrawl\|browserbase\|browser_use\|browser-use\|agentql\|stagehand\|API_KEY" \
  src/bad_research/browse/ && echo "FAIL — keyed reference survives" || echo "PASS — browse/ is 100% keyless"
```

Expected: `PASS — browse/ is 100% keyless`.

- [ ] **Step 4: Lint + type check (project gates)**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run ruff check src/bad_research/browse/ tests/test_browse/
uv run mypy src/bad_research/browse/ || echo "mypy advisory (non-blocking if pre-existing)"
```

Expected: ruff clean; mypy clean or only pre-existing advisories.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "$(cat <<'EOF'
KR-4 Task 10: browse/__init__ keyless exports + full-suite green + keyless audit

Re-exports AgentBrowserProvider/AqlExtractProvider/parse_aql/parse_snapshot/fetch_tiered/
BrowseStep/Snapshot/is_available. grep confirms zero cohere/tavily/exa/firecrawl/browserbase/
browser-use/agentql/stagehand/API_KEY in browse/. KR-4 complete.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Live smoke test (manual, one-time — NOT part of CI, dossier 14 §11)

The CLI contract (`_AgentBrowserCLI` argv + `snapshot --json` shape) is KNOWN-from-source, not KNOWN-from-trace — dossier 14 §11 flags this as the single unverified seam. After `agent-browser install` (pulls Chrome-for-Testing, keyless), run ONE live smoke to confirm the argv/JSON contract holds against a real binary. This is documented for the operator; it does not gate the TDD tasks (which all mock the subprocess).

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
# 1) Confirm the binary + a clean snapshot JSON shape:
agent-browser --engine chrome open https://example.com
agent-browser --engine chrome snapshot -i --json | python -c "import sys,json; d=json.load(sys.stdin); print('refs:', list(d['data']['refs'])[:5])"
# 2) Drive the provider end-to-end against the live CLI:
uv run python -c "
from bad_research.browse.agent_browser import AgentBrowserProvider
r = AgentBrowserProvider(engine='chrome').browse('https://example.com', 'read the page')
print('engine:', r.metadata['engine'], '| refs:', len(r.metadata['refs']), '| chars:', len(r.content))
"
# 3) lightpanda fast rung (if installed): expect refs > 0 on a simple page, else chrome fallback.
LIGHTPANDA_DISABLE_TELEMETRY=true agent-browser --engine lightpanda open https://example.com
```

If the real `snapshot --json` envelope differs from the fixture (`{"success":…,"data":{"snapshot","refs"}}`), adjust `parse_snapshot` (Task 3) and re-run `tests/test_browse/test_agent_browser_snapshot.py` — that one fixture is the contract's single point of truth.

---

## The `browse/` surface after KR-4 (matches `docs/INTERFACES_KEYLESS.md` §4.3/§4.4 verbatim)

```
browse/base.py        BrowseProvider.browse(url, instruction, *, max_steps=12, variables=None, replay_key=None) -> WebResult   [Protocol KEPT]
                      ExtractProvider.extract(source, schema, instruction="") -> dict                                          [Protocol KEPT]
                      get_browse_provider(name=None) -> BrowseProvider | None    # default AgentBrowserProvider iff CLI present
                      get_extract_provider(name=None) -> ExtractProvider | None  # "llm" (default) | "aql"
browse/agent_browser.py  AgentBrowserProvider(name="agent-browser")
                      .__init__(*, engine: Literal["lightpanda","chrome"]="lightpanda", runner=None)
                      .browse(url, instruction, *, max_steps=12, variables=None, replay_key=None, steps=None, state=None, headers=None) -> WebResult
                      .snapshot(*, interactive=True) -> Snapshot
                      .save_state(path) / .cookies_set_curl(curl_file)          # keyless auth (chrome-only)
                      parse_snapshot(stdout) -> Snapshot{text, refs, title, url}
                      _AgentBrowserCLI(...)  # argv builder + injectable runner
                      ACT/EXTRACT/OBSERVE/AGENT_LOOP system-prompt constants (verbatim)
browse/aql.py         parse_aql(query) -> ContainerNode  + Id/IdList/Container/ContainerList nodes  [verbatim agentql parser]
                      AqlExtractProvider(name="aql").extract(snapshot, aql_string, instruction="") -> dict   # host-model resolve + grounding
                      resolve_aql(ast, snapshot, mapping) -> dict                                            # pure grounding
browse/ladder.py      fetch_tiered(url, *, tier_max, instruction=None, schema=None, replay_key=None, variables=None) -> WebResult   [signature KEPT]
                      # rung1 httpx → rung2 crawl4ai → rung2.5 agent-browser(lightpanda) → rung3 agent-browser(chrome)
browse/extract_llm.py LLMExtractProvider(name="llm")    [KEPT VERBATIM]
browse/cache.py       replay_key_for(...) + ActCache    [KEPT VERBATIM]
```

**Zero API keys.** Every rung is `$0`: httpx + crawl4ai (local) + agent-browser/lightpanda (local Chrome/CDP, no account). The host model (Claude Code) is the agent brain — no paid LLM call. agent-browser/lightpanda are OPTIONAL external CLIs detected via `shutil.which`; absent → `get_browse_provider()` returns `None` and the ladder degrades to crawl4ai/httpx.
