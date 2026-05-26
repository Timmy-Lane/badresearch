# Foundation Dossier — hyperresearch as the Base of the Ultimate Research Skill

**Purpose.** This is the skeleton we build on. Every other dossier (web/deep-search RE of frontier products) slots into *extension points* enumerated here. Every claim is reimplementable with a `file:line` cite into `hyperresearch/src/...`. Labels: **KNOWN** (read directly from source), **INFERRED** (deduced from how the pieces connect), **IDEA** (our proposed extension — not in the repo).

Version pinned: `hyperresearch 0.8.6` (`pyproject.toml:7`), DB schema version **8** (`core/db.py:8`).

Source map already digested for cross-reference: `teardowns/HYPERRESEARCH.md` (1,575 L, §0–§28) and `products/HYPERRESEARCH_PRODUCT_CODE.md` (931 L — our headless replica spec). This dossier reads the live clone, not those, and cites the clone.

---

## 0. One-paragraph mental model (KNOWN)

hyperresearch is **not a server and not a model**. It is a *Claude-Code-host harness*: a pip package that (a) ships a deterministic Python **vault** (markdown files + SQLite FTS index + a CLI/MCP/HTTP surface over it), and (b) installs a **prompt-orchestration program** — one entry skill + 16 step-skill files + 16 subagent definitions + a PreToolUse hook — into a project's `.claude/` directory. The "research engine" is *Claude itself* running inside Claude Code, driven step-by-step by those skill files, spawning subagents via the Claude Code `Task` tool, with tool-locks enforced by Claude Code's per-agent allowlist. Remove Claude Code and nothing runs — the package has no LLM client of its own (`grep` for `anthropic`/`openai` in `src/` returns zero hits; the only model references are the `model: opus|sonnet` frontmatter strings inside agent definitions in `core/hooks.py`). **That host-binding is the single biggest thing our product must replace** (the headless orchestrator already spec'd in `products/HYPERRESEARCH_PRODUCT_CODE.md` §6).

---

## 1. The Architectural Skeleton (what we build on)

### 1.1 The 16-stage pipeline orchestration (KNOWN)

The pipeline is defined declaratively in the entry skill `skills/hyperresearch.md`. The orchestrator (Opus, inside Claude Code) reads that file once and then does **only** sequencing — it does no research itself (`skills/hyperresearch.md:15-21`):

> "You are the orchestrator (Opus). Your entire job in this conversation is: 1. Read this file once... 3. Invoke each step skill in sequence via the `Skill` tool... You do NOT do the work of any step yourself."

The 16 steps and their tier gating (`skills/hyperresearch.md:39-67`):

| # | Skill name (`skills/*.md`) | Function | Tiers |
|---|---|---|---|
| 1 | `hyperresearch-1-decompose` | query → scaffold + decomposition + coverage matrix + **tier classification** | all |
| 2 | `hyperresearch-2-width-sweep` | multi-perspective search plan + parallel fetcher waves | all |
| 3 | `hyperresearch-3-contradiction-graph` | pair contradictions into ranked fight clusters | full |
| 4 | `hyperresearch-4-loci-analysis` | 2 loci-analysts → scored `loci.json` w/ source budgets | full |
| 5 | `hyperresearch-5-depth-investigation` | K depth-investigators in parallel → interim notes w/ committed positions | full |
| 6 | `hyperresearch-6-cross-locus-reconcile` | reconcile positions → `comparisons.md` | full |
| 7 | `hyperresearch-7-source-tensions` | expert disagreements → `source-tensions.json` | full |
| 8 | `hyperresearch-8-corpus-critic` | "what source would overturn this?" + targeted gap-fill fetch | full |
| 9 | `hyperresearch-9-evidence-digest` | top claims + verbatim quotes → `evidence-digest.md` | full |
| 10 | `hyperresearch-10-triple-draft` | per-angle source curation + **3 parallel draft-orchestrators** | all |
| 11 | `hyperresearch-11-synthesize` | synthesis plan + outline + spawn synthesizer (two-pass write) → `final_report.md` | full |
| 12 | `hyperresearch-12-critics` | **4 adversarial critics in parallel** → findings JSONs | full |
| 13 | `hyperresearch-13-gap-fetch` | fetch sources for critic-identified vault gaps | full |
| 14 | `hyperresearch-14-patcher` | **surgical Edit hunks** applied to draft | full |
| 15 | `hyperresearch-15-polish` | hygiene + filler pass (Edit-based subagent) | all |
| 16 | `hyperresearch-16-readability-audit` | readability recommender → JSON suggestions → orchestrator applies via Edit | all |

**Tier routing** (`skills/hyperresearch.md:64-67`): `light` = steps 1→2→10(single draft)→15→16 (~$5–15, ~30–40 min); `full` = all 16 (~$60–120, ~1.5–2.5 h). Step 1 writes `pipeline_tier` into `research/prompt-decomposition.json`; the orchestrator reads that file to learn which path to take (`:62`). The tier gate is a hard contract — "Don't add steps 'for thoroughness.' Don't drop steps 'for budget.'" (`:139`).

**Orchestration is a disk-state machine, not in-memory.** The orchestrator holds no inter-stage state in its context; every step reads its inputs from canonical disk artifacts and writes canonical outputs (`skills/hyperresearch.md:162-179` — the full artifact map). This is the recovery mechanism: "Check disk artifacts. Find the highest-numbered step whose artifact exists. Resume from the next step." (`:162-179`). The TodoWrite list carries integer step numbers and "survives context compaction" (`:123`).

### 1.2 Skills-as-pipeline-stages — the context-rot defense (KNOWN, load-bearing)

This is the single most important design decision and the reason we keep this base. **Each step's procedure is its own skill file, loaded fresh into context only at the moment it's needed.** The V7→V8 lesson, verbatim (`skills/hyperresearch.md:35`):

> "**Why this design?** Context compaction. V7 was one 1200-line skill that got compacted away by the time Layer 4 needed its triple-draft procedure. The orchestrator forgot the procedure, wrote a single draft, and produced a flat-scoring report. V8 fixes this at the source: each step's procedure is loaded into context **only at the moment it's needed**, fresh, with no eviction risk."

And the failure-mode forensics (`skills/hyperresearch.md:235-237`):

> "V7 was one 1200-line skill loaded once. By Layer 4 (line ~2200 in a 3000-line conversation), context compaction had evicted the procedure. The orchestrator silently dropped Layer 3.7 (corpus critic), rewrote its todo to replace the triple-draft ensemble with a single draft, and produced a flat-scoring report. This happened in 100% of runs where the orchestrator didn't re-read the skill file. V8 makes re-reading structural."

The trade is explicit: "16 skill files instead of 1, plus 16 invocations of the `Skill` tool... The cost is negligible; the reliability gain is the difference between Q57 (55.9, full pipeline) and Q9 (52.6, single-draft fallback)." (`:239`). The same defense is reinforced inside individual step skills — step 10 carries a "⚠ CRITICAL ANTI-PATTERN: Writing a single draft for `full` tier is a PIPELINE VIOLATION" banner that re-explains the V7 compaction failure (`skills/hyperresearch-10-triple-draft.md:15`).

**Implication for us:** the skill-as-stage decomposition is the durable architectural primitive. Whether the host is Claude Code or our own orchestrator, "fresh procedure per stage, re-read from disk, never accumulate stage logic in working context" is the rule that keeps a 2-hour pipeline from rotting. Our headless replica preserves it literally (`products/HYPERRESEARCH_PRODUCT_CODE.md:184` — "The orchestrator never holds inter-stage state in memory — it re-reads disk artifacts").

### 1.3 The skill-file format + frontmatter (KNOWN — the format for adding a stage)

Two distinct skill shapes ship:

**Entry skill** — `skills/hyperresearch.md:1-11`. Frontmatter is minimal: `name`, `description` (a `>`-folded YAML block). The `name: hyperresearch` is what registers `/hyperresearch` as the slash-command trigger (`core/hooks.py:3400`). Body is pure routing prose + the step table + invariants.

**Step skill** — e.g. `skills/hyperresearch-1-decompose.md:1-11`. Same two-field frontmatter (`name`, `description`). Body convention (consistent across all 16): an `# Step N — title` header, a **`**Tier gate:**`** line (`hyperresearch-5-depth-investigation.md:13` — "SKIP entirely for `light` tier"), a **`**Goal:**`** line, a **`## Recover state`** section, the procedure, and an exit criterion. There is no executable code in skill files — they are instructions to the LLM.

**To add a stage (IDEA):** drop `skills/hyperresearch-N-name.md` with that frontmatter, add its name to `_HYPERRESEARCH_STEP_SKILLS` (`core/hooks.py:3417-3434`, an ordered list), insert it into the entry-skill step table + tier routing (`skills/hyperresearch.md:39-67`), and define its disk artifact in the recovery map (`:162-179`). The installer (`_install_hyperresearch_step_skills`, `core/hooks.py:3437`) auto-discovers any name in that list, copies it to `.claude/skills/hyperresearch-N-name/SKILL.md`, and prunes any `hyperresearch-*` dir not in the list (`:3473-3485`). So a new stage = one new file + one list entry + routing-table edits.

### 1.4 The orchestrator / subagent model (KNOWN)

- **Orchestrator** = Opus, running as the Claude Code session that loaded `/hyperresearch`. Tools available: `Skill`, `Task`, `TodoWrite`, `Bash`, file ops. It sequences; it does not research.
- **Subagents** = 16 Claude Code "agents" registered as `.claude/agents/*.md` files, spawned via the `Task` tool. Each is defined as a Python string constant in `core/hooks.py` and written to disk by an installer function. The install roster (`core/hooks.py:2966-2989`): fetcher, loci-analyst, depth-investigator, source-analyst, dialectic-critic, instruction-critic, depth-critic, width-critic, patcher, polish-auditor, readability-recommender, corpus-critic, draft-orchestrator, synthesizer.
- **Agent frontmatter** carries `name`, `description`, `model`, `tools`, `color` (`core/hooks.py:54-68` for loci-analyst). The `model:` and `tools:` lines are the load-bearing fields.

**Model assignment** (KNOWN, from agent frontmatter in `core/hooks.py`):
- **Sonnet**: loci-analyst (`:65`), fetcher (`:2573`), depth-investigator, source-analyst (1M ctx, `:3168`), corpus-critic, patcher-... — wait, patcher is Opus (`:1207`). Net: fetcher / loci-analyst / depth-investigator / source-analyst / corpus-critic run Sonnet (reading-comprehension + judgment, cheaper).
- **Opus**: the 4 critics (dialectic `:3190`, depth `:3201`, width `:3211`, instruction `:3223`), patcher (`:1207`), synthesizer (`:1876`), draft-orchestrator (`:3302`), readability-recommender (`:3281`).

**The `[Read, Edit]` tool-lock (KNOWN — the core integrity primitive).** Two agents are deliberately denied the `Write` tool so they *physically cannot* regenerate the report:

- **Patcher** — `tools: Read, Edit` (`core/hooks.py:1208`). Prompt (`:1212-1215`): "**You cannot rewrite the document.** You can only apply surgical Edit hunks. This is enforced at the tool level — you do not have Write, you do not have Bash. Your only path to change the draft is the Edit tool with exact `old_string` / `new_string` pairs." Invariant `:1230` REVISE SURGICALLY NEVER REGENERATE; structural findings get *rejected and escalated* to the orchestrator (`:1232-1235`).
- **Polish-auditor** — also `[Read, Edit]` (installer label `core/hooks.py:3255`).
- **Synthesizer** — `tools: Read, Write` (`:1877`). It gets `Write` (it writes the final report once) but is denied `Bash` and `Task` and any vault/web query: "Cannot Bash, cannot spawn subagents" (`:1875`). Because it can't query the vault, the orchestrator must pre-resolve factual conflicts before spawning it.
- **Leaf agents cannot spawn.** The source-analyst prompt (`:2517-2522`) explains why it gets `[Bash, Read, Write]` and NOT `Task`: prevents "recursive cost explosion (analysts spawning analysts spawning analysts)" and pipeline-contract violations.

The four canonical orchestrator rules sit at `skills/hyperresearch.md:131-139`: (1) **never emit bare text while tasks run** (in `-p` mode a text-only response triggers `end_turn` and kills the pipeline — every response while subagents are in flight must include a tool call, ideally appending to `research/temp/orchestrator-notes.md`); (2) **PATCH, NEVER REGENERATE** after step 11; (3) **ARGUE, DON'T JUST REPORT**; (4) **RESPECT THE TIER GATE**.

### 1.5 The vault — markdown + SQLite FTS5 (KNOWN, the full DDL)

The vault is the deterministic, host-independent half. A vault = a `.hyperresearch/` dir (hidden: `config.toml`, `hyperresearch.db`, `templates/`, `exports/`) + one visible `research/` dir (`notes/`, `index/`, `temp/`) (`core/vault.py:11-13, 53-84, 106-115`). Discovery walks up from cwd looking for `.hyperresearch/` (`core/vault.py:146-158`) — same pattern git uses. Markdown files with YAML frontmatter are the source of truth; SQLite is a derived, rebuildable index synced on every vault open via `auto_sync()` (`core/vault.py:160-168`).

**Full DDL** (`core/db.py:10-141`, schema version 8 at `:8`):

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE _meta ( key TEXT PRIMARY KEY, value TEXT NOT NULL );

CREATE TABLE notes (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    path         TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','review','evergreen','stale','deprecated','archive')),
    type         TEXT NOT NULL DEFAULT 'note'
                     CHECK (type IN ('note','raw','index','moc','interim','source-analysis')),
    tier         TEXT CHECK (tier IS NULL OR tier IN
                     ('ground_truth','institutional','practitioner','commentary','unknown')),
    content_type TEXT CHECK (content_type IS NULL OR content_type IN
                     ('paper','docs','article','blog','forum','dataset','policy','code','book','transcript','review','unknown')),
    source       TEXT, parent TEXT,
    deprecated   INTEGER NOT NULL DEFAULT 0,
    reviewed     TEXT, expires TEXT,
    word_count   INTEGER NOT NULL DEFAULT 0,
    summary      TEXT,
    created      TEXT NOT NULL, updated TEXT,
    file_mtime   REAL NOT NULL,
    content_hash TEXT NOT NULL,
    synced_at    TEXT NOT NULL
);
-- 9 indexes on notes: status, type, parent, created, updated, word_count,
--   (status,type), (parent,status), + post-migrate tier & content_type

CREATE TABLE note_content (
    note_id    TEXT PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    body_plain TEXT NOT NULL          -- plain-text projection used by FTS
);

CREATE TABLE tags (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (note_id, tag)
);                                    -- idx_tags_tag

CREATE TABLE aliases (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    alias   TEXT NOT NULL,
    PRIMARY KEY (note_id, alias)
);                                    -- idx_aliases_alias (COLLATE NOCASE)

CREATE TABLE links (
    source_id   TEXT NOT NULL,
    target_ref  TEXT NOT NULL,
    target_id   TEXT,                 -- NULL = broken wiki-link
    line_number INTEGER NOT NULL DEFAULT 0,
    context     TEXT,
    PRIMARY KEY (source_id, target_ref, line_number)
);                                    -- idx_links_target, idx_links_source

CREATE TABLE embeddings (            -- ⚠ VESTIGIAL — created, never written/read
    note_id    TEXT PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    model      TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector     BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE tag_aliases ( alias TEXT PRIMARY KEY, canonical TEXT NOT NULL );

CREATE TABLE sources (
    url          TEXT PRIMARY KEY,
    note_id      TEXT REFERENCES notes(id) ON DELETE SET NULL,
    domain       TEXT, fetched_at TEXT, provider TEXT, content_hash TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','dead','redirected'))
);                                    -- idx_sources_domain, idx_sources_note

CREATE TABLE assets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id      TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    type         TEXT NOT NULL CHECK (type IN ('image','screenshot','pdf','other')),
    filename     TEXT NOT NULL, url TEXT, alt_text TEXT, content_type TEXT,
    size_bytes   INTEGER, created_at TEXT NOT NULL
);                                    -- idx_assets_note, idx_assets_type
```

**FTS5 table** (`core/db.py:132-141`):

```sql
CREATE VIRTUAL TABLE notes_fts USING fts5(
    id UNINDEXED, title, body_plain, tags, aliases,
    tokenize='porter unicode61'
);
```

**Retrieval = BM25 only** (`search/fts.py:84-98`). The query is `notes_fts MATCH ?` ordered by `bm25(notes_fts, 0.0, tw, bw, tgw, aw)` with per-column weights from config — title 10.0, body 1.0, tags 5.0, aliases 3.0 (`config.py:17-23`, `search/fts.py:79-82`). Query preprocessing (`search/fts.py:23-51`): simple words get prefix-matching (`python` → `"python"*`), glued alphanumerics split (`mamba3`→`mamba 3`, `gpt4o`→`gpt 4 o`, `search/fts.py:11-20`), quoted phrases preserved. Post-rank status multipliers: evergreen ×1.5 boost, deprecated ×0.3, stale ×0.7 (`config.py:21-23`, `search/fts.py:128-140`). **There is no vector/neural retrieval anywhere** — the `embeddings` table is created and never touched (see §3.5). Similarity (`core/similarity.py`) is lexical only: shingle-Jaccard + MinHash/LSH, used for dedup, not retrieval.

Schema migrations (`core/migrations.py`): v6 added `tier`+`content_type` columns, v7 added `interim` to the type CHECK (table rebuild — SQLite can't ALTER a CHECK), v8 added `source-analysis` to the type CHECK (`migrations.py:14, 27, 95-161`). `init_schema` is idempotent and runs pending migrations on every vault open (`db.py:161-177`).

### 1.6 The MCP server (KNOWN)

`mcp/server.py` is a `FastMCP("hyperresearch")` thin protocol layer over the vault functions (`mcp/server.py:11-18`). It exposes **12 tools** (the docstring says 8 read-only but the file has grown): read-only — `search_notes`, `read_note`, `read_many`, `list_notes`, `get_backlinks`, `get_hubs`, `vault_status`, `lint_vault`, `check_source`, `list_sources`; write — `fetch_url`, `create_note`, `update_note` (`mcp/server.py:32-405`). Every tool calls `_get_vault()` which discovers + `auto_sync()`s on first call (`:23-29`). `search_notes` wires straight to `search_fts` with the config ranking weights (`:43-62`). Returns JSON strings. Launched via `hyperresearch mcp` (CLI registered at `cli/__init__.py:102`), optional dep `mcp>=1.6` (`pyproject.toml:37`).

### 1.7 Install / distribution mechanism (KNOWN — how it currently requires Claude Code)

Ships as a pip package (`pyproject.toml`). Console entry points: `hyperresearch` and `hpr`, both → `hyperresearch.cli:app` (`pyproject.toml:47-49`). Hard deps include `Crawl4AI>=0.4`, `pymupdf`, `httpx`, `typer`, `pydantic` (`:24-34`); optional extras `mcp`, `exa` (`:36-39`).

`hyperresearch install` (`cli/install.py`) has three modes:
1. **Default** (`install.py:96-176`): init vault (`Vault.init`), inject `CLAUDE.md` blurb (`inject_agent_docs`), then `install_hooks(root, hpr_path)` which drops into the project's `.claude/`: the PreToolUse hook (`.hyperresearch/hook.js` + `.claude/settings.json`), the entry skill, the 16 step skills, and all 16 agent files (`core/hooks.py:2954-2990`). Auto-detects crawl4ai and sets it default (`install.py:179-219`). First interactive run defers to a setup TUI (`install.py:101-105`).
2. **`--global`** (`install.py:64-94` → `install_global_hooks`, `hooks.py:2993`): installs only the entry skill + 16 agents to `~/.claude/` so `/hyperresearch` works in *every* Claude Code session. **Deliberately skips the 16 step skills** to avoid "~3K tokens of system-reminder noise" in unrelated sessions (`hooks.py:3001-3006`); they install per-project lazily.
3. **`--steps-only`** (`install.py:43-57`): lazy per-project install of the 16 step skills, called by the entry-skill bootstrap on first `/hyperresearch` in a project (`skills/hyperresearch.md:79`).

**The PreToolUse hook** is a Node.js script (`HOOK_SCRIPT_TEMPLATE`, `hooks.py:2911-2951`) matched on `Glob|Grep|WebSearch|WebFetch` (`hooks.py:3114`). It walks up for `.hyperresearch/` and, if found, writes a stderr nudge: "BEFORE searching the web, check existing research: `hyperresearch search ...`" and "DO NOT use WebFetch for source pages. Use `hyperresearch fetch` instead" (`:2936-2947`). This is how the vault gets consulted before raw web search — a host-level behavioral nudge, not enforcement.

**The Claude Code dependency is total:** the orchestrator is Claude in a Claude Code session (`Skill`/`Task`/`TodoWrite`/allowlist are Claude Code primitives); the hook is a Claude Code hook; skills + agents live in `.claude/`. The pip package without Claude Code is just an inert vault CLI — it can `fetch`, `search`, `lint`, `serve`, but it cannot *run the research pipeline*.

---

## 2. The Provider Abstraction — THE web-search extension point (KNOWN)

`web/base.py` defines the contract. The **`WebProvider` Protocol signature, verbatim** (`web/base.py:121-137`):

```python
@runtime_checkable
class WebProvider(Protocol):
    """Protocol for web content providers.

    Implementations must support at least fetch(). search() is optional —
    providers that don't support search raise NotImplementedError.
    """

    name: str

    def fetch(self, url: str) -> WebResult:
        """Fetch a single URL and return clean content."""
        ...

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        """Search the web and return results with content."""
        ...
```

The unit of exchange is `WebResult` (`web/base.py:10-24`) — `url, title, content` (clean markdown/text), plus `fetched_at, raw_html, metadata, media, links, screenshot, raw_bytes, raw_content_type`. It carries two pieces of built-in quality logic the pipeline relies on: `looks_like_login_wall()` (title/content/URL signals for auth redirects, `:32-57`) and `looks_like_junk()` (Cloudflare/bot pages, error pages, PDF-binary garbage, cookie walls — returns a reason string, `:59-118`). **Any new provider must return `WebResult` so this logic stays free.**

The factory is `get_provider(name, profile, magic, headless)` (`web/base.py:140-169`): a string-dispatch over `builtin` / `crawl4ai` / `exa`, defaulting to builtin (`:147-150`); unknown name raises `ValueError(... Available: builtin, crawl4ai, exa)` (`:169`).

The three implementations:
- **builtin** (`web/builtin.py`): stdlib + optional httpx/bs4. `fetch()` downloads (httpx → urllib fallback, `:72-89`) and extracts text (bs4 → stdlib `HTMLParser` fallback, `:91-111`). **`search()` raises `NotImplementedError`** (`:66-70`) — builtin is fetch-only.
- **crawl4ai** (`web/crawl4ai_provider.py`): real local headless browser. PDF detection + pymupdf extraction (`:34-90`), arXiv `/abs/`→`/pdf/` rewrite (`:81-84`), `PruningContentFilter`→`fit_markdown`, authenticated crawling via browser profiles (`:1-7`), `magic` anti-bot stealth + `profile` + `headless` constructor args (`base.py:156-160`). This is the default once detected (`install.py:191-193`).
- **exa** (`web/exa_provider.py`): the only provider with real neural `search()`. Wraps `exa_py`. `search()` (`:70-88`): `type="auto"`, `contents={text:{max_characters:8000}, highlights:True}`, optional category/include/exclude domains. `fetch()` → Exa `/contents`. Sets an `x-exa-integration: hyperresearch` tracking header (`:62`). Content cascade text→highlights→summary (`:101-118`).

**How a new provider plugs in (IDEA — the extension recipe):** (1) write a class with `name: str`, `fetch(url)->WebResult`, and optional `search(query,max_results)->list[WebResult]`; (2) lazy-import it inside `get_provider()` under a new `if name == "tavily":` branch (`base.py:140-169`) — keep the import lazy so the optional dep stays optional; (3) add the extra to `pyproject.toml [project.optional-dependencies]`; (4) document `provider = "tavily"` in config. The `@runtime_checkable Protocol` means you don't subclass anything — duck typing on `name`/`fetch`/`search` is the whole contract. **This is the cleanest extension point in the codebase** and the natural insertion site for Tavily / Brave / SearXNG / Browserbase / AgentQL adapters.

**Critical gap this abstraction exposes:** web *search* is barely wired in. Only `exa` implements `search()`; builtin/crawl4ai raise `NotImplementedError`. In Claude-Code-host mode the pipeline leans on the host's native WebSearch tool (fetchers have `tools: ..., WebSearch`, `hooks.py:2574`) and only uses providers for *fetching* URLs. So today's "search" is mostly: Claude's WebSearch yields URLs → `hyperresearch fetch` pulls them via a provider → saved as notes. Standalone, that host WebSearch disappears (see §4 gaps and §5).

---

## 3. Every Extension Point, Enumerated

### 3.1 Add a web-search provider (KNOWN site)
`web/base.py:140-169` `get_provider()` string-dispatch + a new class implementing the `WebProvider` Protocol returning `WebResult`. Optional dep in `pyproject.toml:36-39`. Config key `web.provider` read at `config.py:69`. **Best-quality extension point.** (See §2.)

### 3.2 Add a pipeline stage (KNOWN site)
New `skills/hyperresearch-N-name.md` (frontmatter `name`+`description`; body with `**Tier gate:**` / `**Goal:**` / `## Recover state` / procedure / exit criterion — §1.3). Register name in the ordered list `_HYPERRESEARCH_STEP_SKILLS` (`hooks.py:3417-3434`). Add to entry-skill step table + tier routing (`skills/hyperresearch.md:39-67`) and recovery artifact map (`:162-179`). Installer auto-copies + prunes (`hooks.py:3437-3485`). If the stage spawns a new kind of subagent, also add an agent definition (§3.3).

### 3.3 Add a subagent (KNOWN site)
Define an agent string constant in `core/hooks.py` (frontmatter `name`/`description`/`model`/`tools`/`color`), write an `_install_X_agent` function (`hooks.py:3145-3303` are the templates), and append it to **both** install loops — `install_hooks` (`:2966-2989`) and `install_global_hooks` (`:3021-3043`). The `tools:` line is the tool-lock; the `model:` line picks Opus/Sonnet. The orchestrator spawns it by `Task(subagent_type="hyperresearch-X")` per the spawn contract (`skills/hyperresearch.md:143-153`: must pass verbatim `research_query`, a pipeline-position statement, and the agent's specific inputs).

### 3.4 Add a model backend — THE host-replacement point (IDEA — currently no slot)
**There is no LLM-client abstraction in the package.** It is Anthropic-only *by virtue of running inside Claude Code*; the only model selectors are the `model: opus|sonnet` frontmatter strings in `core/hooks.py` agent definitions, which Claude Code interprets. To make the system provider-agnostic for the LLM, the model client must live in **a new headless orchestrator process** that replaces the Claude Code host. The product code already designs exactly this: a Python orchestrator that calls the Anthropic Messages API directly, with a `spawn(agent_type, prompt)` helper and a per-worker `(model, tool_allowlist)` table (`products/HYPERRESEARCH_PRODUCT_CODE.md:184-205`). The provider-agnostic LLM client would be a thin wrapper inside that orchestrator (e.g. an `LLMClient` interface with Anthropic / OpenAI / local backends), keyed off env like `ORCH_MODEL`/`WORKER_SONNET`/`WORKER_OPUS` (`HYPERRESEARCH_PRODUCT_CODE.md:39, 362`). **Net: the model backend extension point does not exist in hyperresearch today — we create it in the orchestrator we build.**

### 3.5 Add a vault retrieval mode — neural retrieval attaches here (KNOWN gap + IDEA)
Today retrieval is FTS5/BM25 only (`search/fts.py`, §1.5). The `embeddings` table exists (`db.py:88-94`: `note_id, model, dimensions, vector BLOB, created_at`) but is **completely vestigial** — grep across `src/` finds it referenced *only* in its own `CREATE TABLE` and nowhere else (no writer, no reader, no cosine, no rerank). Confirmed: `core/similarity.py` is lexical (shingle-Jaccard + MinHash/LSH), used for dedup not retrieval. **Where neural retrieval would attach (IDEA):** (a) a writer that, on sync (`core/sync.py` execute path), embeds `body_plain` and upserts into `embeddings`; (b) a `search/vector.py` doing cosine over the BLOBs (or a `sqlite-vec`/`faiss` sidecar); (c) a hybrid scorer that fuses BM25 (`search/fts.py`) + vector + an optional cross-encoder rerank, exposed via a new `search` ranking mode and surfaced through `search_notes` MCP tool (`mcp/server.py:32`) and the `hyperresearch search` CLI. The table's schema (model + dimensions + vector) was clearly pre-provisioned for this — it's a designed-in socket nobody soldered.

### 3.6 Add an MCP tool (KNOWN site)
Add a `@server.tool()`-decorated function in `mcp/server.py` (`:32+`); call `_get_vault()` for the synced vault; return a JSON string. No registration beyond the decorator.

### 3.7 Other sockets (KNOWN)
- **CLI command:** register in `cli/__init__.py` (`app.command(...)` at `:78-102`, or `app.add_typer(...)` sub-apps at `:117-135`).
- **Config key:** add a field to `VaultConfig` dataclass (`config.py:11-43`) + load/save (`:58-113`).
- **Note type / status / tier / content_type:** all are CHECK-constrained enums in the DDL (`db.py:23-30`) — extending them requires a migration (table rebuild, see `migrations.py:52-161`).
- **HTTP serve surface:** `serve/server.py` (588 L) renders the vault as a read-only web app — a place to hang a UI/API.

---

## 4. Keep / Replace / Add Ledger

### KEEP (what hyperresearch does well — the durable spine)
- **Skills-as-stages context-rot defense** (§1.2). The V7→V8 lesson is the whole reason this base wins; preserve fresh-procedure-per-stage + disk-state-machine literally.
- **Disk-state-machine orchestration + recovery map** (`skills/hyperresearch.md:162-179`). Stateless orchestrator, resumable, compaction-proof.
- **Tier gating** (light vs full, `:64-69`). Right-sizes cost/time; a binding contract, not a heuristic.
- **The `[Read, Edit]` / `[Read, Write]` tool-locks** (§1.4). "Patch never regenerate" enforced mechanically — the single best integrity primitive in the system.
- **Adversarial structure**: triple-draft ensemble (step 10) → synthesizer (step 11) → 4 parallel critics (step 12) → patcher (step 14). The argue-don't-report engine.
- **The vault** (§1.5): markdown-as-truth + rebuildable SQLite index, git-style discovery, auto-sync, FTS5 BM25 with sane column weights + status multipliers, the `sources`/`assets` provenance tables, dedup via MinHash.
- **`WebProvider` Protocol + `WebResult`** (§2). Clean, duck-typed, with built-in junk/login-wall filtering. The right web extension point.
- **MCP server** (§1.6) and the **structurally-enforced lint gate** (`cli/lint.py`, 1510 L — `wrapper-report`, `locus-coverage`, `scaffold-prompt`, `patch-surgery` rules) as machine-checkable invariants.
- **Provenance discipline**: every fetched URL → `sources` row (url, note_id, domain, provider, content_hash); every note carries frontmatter + tier/content_type taxonomy.

### REPLACE (what binds it to the wrong host / shape)
- **Claude-Code-host binding → standalone headless orchestrator.** The biggest replace. `Skill`/`Task`/`TodoWrite`/allowlist are Claude Code primitives; reproduce their *behavior* (fresh-context-per-stage, disk state, tool-locks via per-worker API tool-lists, todos→stage gates) in our own process (`HYPERRESEARCH_PRODUCT_CODE.md:6-7, 184, 241`).
- **Anthropic-only-by-host → provider-agnostic LLM client** (§3.4). Introduce the model-backend abstraction that doesn't exist today.
- **Host-WebSearch dependency → first-class search providers.** Today only Exa implements `search()`; the pipeline otherwise leans on Claude Code's WebSearch tool. Standalone, we need real search adapters wired into `get_provider`/the orchestrator (`HYPERRESEARCH_PRODUCT_CODE.md:155, 243`).
- **PreToolUse Node hook → in-orchestrator "check vault first" policy.** The behavioral nudge is host-specific; bake the check-before-search rule into the width-sweep stage logic instead.

### ADD (gaps the other dossiers will fill — explicit slots)
- **More web/search providers**: Tavily, Brave, SearXNG, plus agentic-browse (Browserbase / Playwright-driven) and AgentQL structured extraction. Slot: §3.1 / §2.
- **Neural retrieval + rerank**: embed-on-sync writer, vector search, BM25+vector+cross-encoder hybrid, activating the dead `embeddings` table. Slot: §3.5.
- **A clarifier stage** (stage 0): interactive query disambiguation before decompose. Slot: §3.2 (new step 0 / pre-step-1).
- **Parallel-subagent-per-locus at greater fan-out / a parallel-locus scheduler** beyond the current K-investigators. Slot: §3.2/§3.3.
- **LLM-as-judge grader loop**: an automated scorer (RACE-style) closing the critic→patch loop with a numeric gate, vs today's qualitative critics. Slot: new stage §3.2 + new agent §3.3.
- **Provider-agnostic model routing / cost-aware model selection.** Slot: §3.4.
- **Standalone packaging (npx or pip) with a self-contained runtime** so there's no Claude Code requirement. Slot: §5.

---

## 5. Packaging Analysis (factual; language choice deferred)

### How it ships TODAY (KNOWN)
- **pip package**, `hyperresearch 0.8.6`, hatchling build, wheel packages `src/hyperresearch` (`pyproject.toml:1-3, 56-57`). Console scripts `hyperresearch` + `hpr` → `hyperresearch.cli:app` (`:47-49`). Python 3.11–3.13 (`:11`).
- **Distribution of the agent program is a *side effect of a CLI command*, not a package install.** `pip install hyperresearch` gives you the vault CLI; the research pipeline only materializes when you run `hyperresearch install [--global]`, which writes skills/agents/hook into `.claude/` (§1.7). So "install the product" = pip install + run a command that injects files into Claude Code's config dirs.
- **Hard runtime dependency on Claude Code.** Without it, `/hyperresearch` has no host, `Skill`/`Task` don't exist, and the pipeline can't run. The pip package alone is an inert markdown+SQLite vault tool.

### The Claude-Code-skill dependency (KNOWN, precisely)
The orchestrator = Claude in a Claude Code `-p`/interactive session. The pipeline relies on four Claude Code primitives with no package-level substitute: `Skill` (load step procedure fresh), `Task` (spawn subagent), `TodoWrite` (compaction-surviving step memory), and the per-agent **tool allowlist** (which is *how* the `[Read,Edit]` tool-lock is enforced — `hooks.py:1208`). The PreToolUse hook is also a Claude Code hook (`hooks.py:3089-3122`).

### How our product could run standalone (OPTIONS — factual, no decision)
The headless replacement is already designed in `products/HYPERRESEARCH_PRODUCT_CODE.md` §6. Its shape, restated:
- A **Python orchestrator process** (`hpr_orchestrator/run.py`) that replaces the Claude Code host: a tier-conditional sequencer over the disk-state-machine stages, calling the **Anthropic Messages API directly** (`HYPERRESEARCH_PRODUCT_CODE.md:167-184`).
- A **`spawn(agent_type, prompt)`** helper = one fresh Messages API turn-loop per worker, with the worker's system prompt = the ported agent definition and the worker's **tools = the exact allowlist** — this is how the tool-lock is reproduced at the API tool-list level (`:184-205`). Critically: `write_file` is simply *not registered* for patcher/polish/critic workers; `edit_file` is a strict find/replace with a ≤500-char net-expansion cap (`:205, 255-275`).
- Per-worker model table: orchestrator `claude-opus-4-7`, workers Sonnet (`claude-sonnet-4-6`) for fetcher/loci/depth/corpus-critic/source-analyst and Opus for drafter/synth/4 critics/patcher/polish/readability (`:362`, matching the frontmatter in `hooks.py`).
- Web *search* gap filled by Exa `search()` if `EXA_API_KEY` else a pluggable SearXNG/Brave adapter, piping URLs into `/fetch` — "the pipeline only ever sees `WebResult`, so the swap is transparent" (`:155`).
- Packaged as **two Docker images** (`docker-compose up`): the deterministic **vault** (verbatim port of `core/`/`search/`/`web/`/`mcp/`/`serve/`) exposed as a FastAPI service, and the **orchestrator** (`:27-56, 350-355`).

**Packaging options for our npx-or-pip requirement (laid out, not chosen):**
1. **Pip + bundled headless orchestrator** (closest to today): keep the Python vault, ship the orchestrator in the same wheel, expose `hyperresearch research "<query>"` that runs the full pipeline headless (no Claude Code). The product code's orchestrator is the basis.
2. **npx (Node) front-end over a Python core**: an `npx ultimate-research` launcher that shells out to / bundles the Python vault + orchestrator (or reimplements the orchestrator in Node and keeps Python only for the deterministic vault as a subprocess/sidecar). The `WebResult` JSON contract and the disk artifacts make a cross-language split clean.
3. **Single-language rewrite** (Python-only pip, or Node/TS-only npx) — port the vault + orchestrator into one runtime. The vault is small and deterministic (db.py 177 L, fts.py 142 L, web providers ~650 L) and the orchestrator is mostly prompt-pasting + API calls, so either direction is tractable.
4. **Keep the optional Claude-Code-skill mode** as one of several hosts: ship the standalone orchestrator as default, but also keep `hyperresearch install --global` so power users can still drive it from inside Claude Code. The skill files + agent definitions are reusable as-is in both modes (they're just markdown).

The language decision (Python vs Node/TS vs split) is a later user discussion; this dossier only establishes that **the skill files, agent prompts, disk-state contract, vault DDL, and `WebResult`/`WebProvider` contracts are all host-agnostic assets** — the only Claude-Code-specific machinery is the four host primitives in §5, all of which the designed headless orchestrator already reproduces.

---

## 6. Skeleton + Extension-Point Map

```
                         ┌─────────────────────────────────────────────────────────┐
   [EP-D] model backend  │   HOST  (today: Claude Code session · Opus orchestrator) │
   does NOT exist today; │   REPLACE → standalone headless orchestrator process     │
   create in orchestrator│   primitives used: Skill · Task · TodoWrite · allowlist  │
                         └───────────────┬─────────────────────────────────────────┘
                                         │ loads once
                          skills/hyperresearch.md  (ENTRY SKILL — router only)
                          step table · tier routing · 4 rules · recovery map
                                         │ Skill(skill: "hyperresearch-N-...") fresh per stage
                                         ▼
   ┌──────────────────────── 16 STEP SKILLS (skills/hyperresearch-N-*.md) ───────────────────────┐
   │ 1 decompose → 2 width-sweep → [3 contradiction → 4 loci → 5 depth → 6 reconcile →            │
   │ 7 tensions → 8 corpus-critic → 9 evidence-digest →] 10 triple-draft → [11 synthesize →       │
   │ 12 critics → 13 gap-fetch → 14 patcher →] 15 polish → 16 readability    ([..]=full tier only) │
   │ light path: 1→2→10(single)→15→16                                                             │
   │  [EP-A] ADD STAGE: new file + name in _HYPERRESEARCH_STEP_SKILLS (hooks.py:3417)             │
   │         + entry-skill table/routing + recovery artifact.   Slots: clarifier(stage 0),        │
   │         judge/grader loop, parallel-locus scheduler.                                          │
   └───────────────┬───────────────────────────────────────────────┬─────────────────────────────┘
                   │ spawns via Task                                 │ reads/writes
                   ▼                                                 ▼
   ┌── 16 SUBAGENTS (.claude/agents/*.md, defined in core/hooks.py) ─┐   ┌──── DISK STATE MACHINE ────┐
   │ Sonnet: fetcher · loci-analyst · depth-investigator ·           │   │ research/scaffold.md        │
   │         source-analyst(1M) · corpus-critic                      │   │ prompt-decomposition.json   │
   │ Opus:   draft-orchestrator · synthesizer[Read,Write] ·          │   │ loci.json · comparisons.md  │
   │         4 critics · patcher[Read,Edit] · polish[Read,Edit] ·    │   │ temp/* · final_report_*.md  │
   │         readability-recommender                                 │   │ critic-findings-*.json      │
   │  [EP-B] ADD SUBAGENT: const + _install_X + both install loops   │   │ patch-log · polish-log      │
   │  [EP-locks] tool-lock = the integrity primitive (KEEP)          │   │ (orchestrator never holds   │
   └───────────────┬─────────────────────────────────────────────────┘   │  inter-stage state in ctx)  │
                   │ web I/O                                              └─────────────────────────────┘
                   ▼
   ┌──── WEB LAYER (web/) ────────────────────────────┐        ┌──── VAULT (core/ + search/) ─────────┐
   │ WebProvider Protocol (base.py:121) → WebResult    │        │ markdown notes (truth) + SQLite index │
   │   builtin (fetch-only) · crawl4ai (browser,PDF) · │        │ DDL: notes/note_content/tags/aliases/ │
   │   exa (neural search()) · get_provider() dispatch │        │   links/sources/assets/tag_aliases/   │
   │  [EP-C] ADD PROVIDER: new class + get_provider    │        │   embeddings(VESTIGIAL) + notes_fts   │
   │         branch (base.py:140) + optional dep.      │        │ retrieval: FTS5 BM25 only (fts.py)    │
   │  GAP: only exa does search(); host WebSearch dep  │        │  [EP-E] ADD RETRIEVAL MODE: embed-on- │
   │  ADD: Tavily/Brave/SearXNG/Browserbase/AgentQL    │        │   sync writer → vector search →       │
   └───────────────────────────────────────────────────┘        │   BM25+vector+rerank hybrid. Activate │
                                                                 │   the dead embeddings table.          │
   ┌──── SURFACES ────────────────────────────────────┐        │  [EP-F] ADD MCP TOOL: @server.tool()  │
   │ CLI (cli/__init__.py app)  ·  MCP (mcp/server.py, │        │  [EP-CLI] register in cli/__init__.py │
   │   12 tools)  ·  serve/ (read-only web UI)         │        └───────────────────────────────────────┘
   │ INSTALL: hyperresearch install [--global|--steps] │
   │   → drops skills/agents/hook into .claude/        │   PACKAGING (§5): pip today + Claude-Code-host
   │   pyproject scripts: hyperresearch, hpr           │   dependency. Standalone = headless orchestrator
   │  [EP-config] VaultConfig dataclass (config.py)    │   (product code §6); npx-or-pip = later decision.
   └───────────────────────────────────────────────────┘
```

**Extension-point legend (for the synthesis plan to slot other dossiers into):**
- **EP-A** Pipeline stage — `hooks.py:3417` list + `skills/hyperresearch.md` table/routing. (clarifier, judge loop, locus scheduler)
- **EP-B** Subagent — const in `hooks.py` + `_install_X` + both install loops.
- **EP-C** Web/search provider — `web/base.py:140` dispatch + `WebProvider`/`WebResult`. (Tavily, Brave, SearXNG, Browserbase, AgentQL — the web/deep-search dossiers land here)
- **EP-D** Model backend — does NOT exist; create in the headless orchestrator (`HYPERRESEARCH_PRODUCT_CODE.md:184`).
- **EP-E** Vault retrieval mode — activate `embeddings` table (`db.py:88`), add `search/vector.py` + hybrid scorer fusing `search/fts.py` BM25. (neural rerank dossiers land here)
- **EP-F** MCP tool — `@server.tool()` in `mcp/server.py`.
- **EP-config / EP-CLI** — `config.py` dataclass / `cli/__init__.py` registration.
- **EP-locks** — the `[Read,Edit]`/`[Read,Write]` tool-locks: KEEP, reproduce via per-worker API tool-lists when host-replaced.

---

## 7. Bottom line

The base gives us a **proven, compaction-resistant 16-stage research orchestration** (the V7→V8 skills-as-stages lesson is the crown jewel), a **deterministic markdown+SQLite vault** with clean provenance, a **duck-typed web-provider abstraction**, and **mechanical integrity via tool-locks**. The two structural things it lacks for our product are (1) a **standalone host** (it requires Claude Code) and (2) a **model-backend abstraction** (Anthropic-only by host) — both already designed in our headless replica. Everything the other dossiers will bring — more search providers, agentic browse, neural retrieval/rerank, a clarifier, an LLM-judge loop — has a clearly marked socket above (EP-A through EP-F). We are not redesigning; we are extending a sound skeleton at named joints.
