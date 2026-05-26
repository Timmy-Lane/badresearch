# Bad Research — KEYLESS REBUILD (KR) Plan-Series Outline

> **Purpose.** This is the hand-off doc for the parallel plan-writers. It defines the KR-1…KR-7
> plan series, each plan's scope, the exact `src/` files it removes/adds/rewires, which dossier it
> implements, its dependencies on other KR plans, and a rough task list. The plan-writers turn each
> KR-N section below into a full `docs/plans/KR-N-<name>.md` implementation plan.
>
> **The frozen contract every KR plan binds to:** `docs/INTERFACES_KEYLESS.md` (signatures, removed
> list, lean deps, frozen constants). The unchanged seams remain in `docs/INTERFACES.md` (LLM seam,
> grounding API, vault SQLite schema, cost meter, 16-stage skill graph).
>
> **The two FINAL decisions all plans enforce:** (1) pure keyless — DELETE the API-provider code
> (no Tavily/Exa/Sonar/Firecrawl/Cohere/Browserbase/AgentQL/Browser-Use; LanceDB out of core);
> (2) the skill stays a keyless Claude Code skill (host model supplies inference; keyless web).
>
> **This is a targeted refactor, not a greenfield rebuild.** The keyless-ready code stays (the
> `llm/`/`grounding/`/`quality/`/`core/`/`skills/` seams, the funnel shape, the fusion math, the
> calibration harness). Plans REMOVE the keyed layer and REWIRE the seams; they do not rewrite the
> kept code.
>
> **Evidence base:** dossiers `docs/investigation/12_KEYLESS_CONTENT.md`, `13_KEYLESS_SEARCH.md`,
> `14_KEYLESS_BROWSE.md`, `15_KEYLESS_RETRIEVAL.md`, `16_KEYLESS_LOOP.md`.

---

## Dependency graph (build order)

```
KR-1 (contract + dep-slim + provider removal)          ← foundation; everything depends on it
   │
   ├─► KR-2 (keyless search + 7 verticals)              ┐
   ├─► KR-3 (content fetch_clean + 6 source tiers)      │  KR-2…KR-5 are mostly PARALLEL
   ├─► KR-4 (agent-browser browse + lightpanda)         │  (each owns a disjoint package)
   └─► KR-5 (keyless retrieval: FTS + LLM-rerank)       ┘
            │
            └─► KR-6 (loop levers + funnel/pipeline/skill REWIRE)   ← needs KR-2..KR-5 seams to wire
                     │
                     └─► KR-7 (packaging + tests + calibration)     ← needs the whole thing green
```

- **KR-1 first, alone.** It deletes the keyed modules + slims deps + rewrites the two factories
  (`web/base.py::get_provider`, `providers.py`) to keyless stubs so KR-2…KR-5 build on clean ground.
- **KR-2, KR-3, KR-4, KR-5 in parallel** — each owns a disjoint package (`web/search/`,
  `web/content/`, `browse/`, `retrieval/`). Light cross-refs (KR-2's `WebSearchToolProvider.fetch`
  calls KR-3's `fetch_clean`; KR-4's ladder uses KR-3's `fetch_clean`); resolve via the frozen
  signatures in INTERFACES_KEYLESS — they don't block each other's drafting.
- **KR-6 after KR-2…KR-5** — it rewires `cli/research.py` builders + `funnel`/`pipeline` wiring +
  the skill loop levers, so it needs the new seams to exist.
- **KR-7 last** — packaging, the full test rewrite, the calibration plan; needs everything green.

---

## KR-1 — Contract freeze + dependency slim + keyed-provider removal

**Scope.** The foundation pass: delete every keyed module/test/dep, slim `pyproject.toml` to the
lean keyless base, and rewrite the two factories + the registry + the config to keyless. Leaves the
tree compiling with keyless stubs that KR-2…KR-5 flesh out. NO new behavior — pure removal + rewire.

**Implements:** INTERFACES_KEYLESS §1 (REMOVED), §3.4 (config knobs), §3.5 (registry), §7 (lean deps).

**REMOVES (`src/`):**
- `web/providers/` (entire dir: `tavily_provider.py`, `sonar_provider.py`, `firecrawl_provider.py`,
  `cascade.py`, `__init__.py`); `web/exa_provider.py`.
- `web/base.py::_build_cascade` + the keyed branches of `get_provider`.
- `browse/browse_browserbase.py`, `browse/browse_browseruse.py`, `browse/extract_agentql.py`,
  `browse/extract_stagehand.py`.
- `embed/cohere.py`; `retrieval/rerank.py::CohereReranker` + its `get_reranker` branch.
- LanceDB out of core: demote `retrieval/store.py` import to `[local]`-guarded.

**REMOVES (tests):** `tests/test_web/*` (keyed), `tests/test_browse/{browserbase,browseruse,
agentql,stagehand}`, `tests/test_embed/test_cohere.py`; rewrite `tests/test_providers.py`.

**ADDS / REWRITES:**
- `pyproject.toml` — the lean core deps + `[local]`/`[browse]`/`[mcp]`/`all` extras (§7). Remove
  `search` extra entirely; strip `lancedb`/`pyarrow` from core; strip `browser-use`/`agentql`.
- `web/base.py::get_provider` → keyless registry stub (default `websearch`; branches `ddgs`,
  `searxng`, `builtin`, `crawl4ai`).
- `providers.py::PROVIDERS` → keyless rows only (no keyed providers; `requires_key=False`).
- `config.py` → drop Cohere `embed_model`/`rerank_model` defaults; add `reranker`, `neural_recall`,
  `searxng_endpoint`, `browse_engine`, `effort`, `max_tokens`.
- `embed/base.py::get_embed_provider` → default `bge-local` ([local]); delete cohere branch.
- `retrieval/rerank.py::get_reranker` → `host`/`local`/`none` (default `host`; `ClaudeCodeReranker`
  is a stub here, filled by KR-5).

**Depends on:** nothing (foundation).

**Rough tasks:** (1) delete keyed modules + tests; (2) slim `pyproject.toml`; (3) rewrite
`get_provider` to keyless stub; (4) rewrite `providers.py` registry; (5) config knobs; (6)
`get_embed_provider`/`get_reranker` keyless defaults (stubs OK); (7) `grep` guard:
`cohere|tavily|exa|firecrawl|browserbase|agentql|browser_use` returns zero hits in `src/`; (8)
`ruff`/`mypy`/import-smoke clean.

---

## KR-2 — Keyless search layer + 7 scholarly verticals

**Scope.** Build `web/search/` — the keyless search + ranking + rerank substance: the host
`WebSearch` tool adapter (default), `ddgs`, self-host `SearxngProvider`, RRF k=60 fusion,
host-model-as-reranker, the retrieve-until-good loop, and the 7 keyless scholarly verticals with
intent routing.

**Implements:** dossier 13 (§0 source tiers, §1 SearXNG algorithm, §2 fan-out/expansion, §3 RRF +
ranking + 0.70/<30% loop, §4 keyless rerank ladder A/B/C, §8 verticals + DOI-dedup + intent routing).

**ADDS (`src/`):**
- `web/search/__init__.py`, `base.py` (`WebSearchToolProvider`, `DdgsProvider`, `SearxngProvider`,
  `KeylessSearchConfig`), `rank.py` (`rrf_fuse`, `rrf_fuse_with_verticals`, consensus + DOI tie-break),
  `rerank.py` (`HostModelReranker` + the verbatim LLM-rerank prompt + injection preamble),
  `loop.py` (`retrieve_until_good`), `verticals.py` (the 7 providers), `route.py` (`VERTICAL_ROUTES`,
  `route_query`, intent detection).
- `tests/test_web/test_search_*` (RRF math, vertical mapping, DOI dedup, loop, fixtures-based — no
  live network in unit tests; `live` marker for the keyless API probes).

**REWIRES:** `web/base.py::get_provider` keyless branches resolve to these classes.

**Depends on:** KR-1 (clean factory + registry). Light ref to KR-3 (`fetch` → `fetch_clean`) —
resolve via the frozen signature; don't block.

**Rough tasks:** (1) `WebSearchToolProvider` (parse host `Links:` array → content-less `WebResult`);
(2) `DdgsProvider` + keyless `SearxngProvider` (self-host JSON); (3) `rrf_fuse` k=60 + consensus
tie-break (port `funnel/rank.py::rrf_fuse` semantics, rank-based); (4) `HostModelReranker` + frozen
prompt; (5) `retrieve_until_good` (0.70 / <30% / ≤rounds); (6) the 7 verticals (arXiv Atom,
OpenAlex inverted-abstract reconstruct, Crossref DOI spine, S2 429-backoff, Europe PMC, PubMed
esearch+esummary, Wikipedia+Wikidata); (7) `route_query` intent routing (seed-only verticals);
(8) `rrf_fuse_with_verticals` DOI-first dedup + richness tie-break; (9) tests.

---

## KR-3 — Content extraction: `fetch_clean` + the 6 source-type tiers

**Scope.** Build `web/content/` — the deterministic keyless `URL → clean markdown` pipeline (the
verbatim Firecrawl strip/metadata ports + crawl4ai PruningContentFilter/BM25 + trafilatura fallback
+ pymupdf PDF + the host-model injection-defended LLM-clean + BM25 highlights), and the
`classify_source` router + 6 keyless source-tier extractors (YouTube/GitHub/arXiv-src/feed/sitemap/
llms.txt) that emit the normalized vault note.

**Implements:** dossier 12 (§0-§11 `fetch_clean`, §2 strip ports, §3 readability scorer, §4 md
conversion, §5 PDF, §6 LLM-clean prompt verbatim, §7 highlights, §8 metadata/freshness, §9 the
19-step keyless mapping; §"non-HTML sources" A-F the 6 extractors + the normalized note).

**ADDS (`src/`):**
- `web/content/__init__.py`, `fetch_clean.py` (the pipeline + `strip_boilerplate`, `main_content`,
  `extract_metadata`, `extract_published_date`, `highlights`, `pdf_to_markdown`, `llm_clean`,
  `postclean`, the SSRF/charset guards, the sqlite 14-day cache, `FIRECRAWL_CLEAN_PROMPT` verbatim),
  `sources.py` (`classify_source` + `youtube_transcript`, `github_clone_notes`/`github_file`,
  `arxiv_source_notes`, `feed_notes`, `sitemap_urls`, `llms_txt_notes`; the normalized-note shape).
- `tests/test_content/` (strip-port fixtures, PruningFilter threshold, highlights BM25, metadata
  chain, classify_source routing, VTT clean, normalized-note shape; `live` marker for real fetches).

**REWIRES:** KR-2's `WebSearchToolProvider.fetch` and KR-4's ladder rungs call `fetch_clean`.

**Depends on:** KR-1 (deps: crawl4ai/trafilatura/pymupdf/rank_bm25/dateparser/feedparser in core).

**Rough tasks:** (1) tiered fetch (httpx→crawl4ai→WebFetch) + `needs_js` (200-char floor) + charset
3-layer + SSRF block; (2) `strip_boilerplate` (verbatim selector list + force-include guard +
srcset/absolutify); (3) `main_content` (PruningContentFilter 0.48 dynamic | BM25ContentFilter when
query, trafilatura fallback <200 chars); (4) html2text + citation conversion + postclean (base64
strip, fence fix); (5) `pdf_to_markdown` (pymupdf4llm + Read-tool vision escape); (6) `llm_clean`
(host model + verbatim prompt, gated); (7) `highlights` (BM25 sliding window top-3); (8)
`extract_metadata`/`extract_published_date` (verbatim chain + dateparser); (9) sqlite 14-day cache;
(10) `classify_source` + the 6 extractors emitting the normalized note; (11) tests.

---

## KR-4 — Agentic browse on `agent-browser` (+ lightpanda rung + AQL)

**Scope.** Replace the cloud browse stack with the local `agent-browser` CLI driven by Claude Code:
the `AgentBrowserProvider` (snapshot/@eN/eval ReAct loop), the 4-rung keyless ladder (httpx →
crawl4ai → lightpanda → chrome), the ported Stagehand act/extract/observe prompts, the ported
AgentQL AQL parser + host-model resolver, and the keyless persist-once auth flow.

**Implements:** dossier 14 (§1-§4 agent-browser keyless + snapshot + Claude-Code-as-brain, §5
Stagehand ports, §6 AQL ports, §7 the escalation ladder, §8/§13 keyless auth, §12 lightpanda
rung-2.5).

**ADDS / REWRITES (`src/`):**
- `browse/agent_browser.py` (NEW: `AgentBrowserProvider`, the snapshot/ReAct loop via Bash, the
  Stagehand act/extract/observe prompt constants, the lightpanda↔chrome fallback).
- `browse/aql.py` (NEW: the ported AgentQL recursive-descent parser + AST + host-model resolver +
  grounding against the snapshot refs map).
- `browse/base.py::get_browse_provider`/`get_extract_provider` → keyless (`agent-browser` default;
  `aql` extractor; KEEP `extract_llm.py` LLMExtractProvider).
- `browse/ladder.py::fetch_tiered` + `_do_browse` → the 4-rung keyless ladder (no key branches;
  lightpanda rung-2.5 + chrome rung-3).
- `tests/test_browse/` — rewrite around the keyless ladder (mock the CLI subprocess); keep
  `test_extract_llm.py`, `test_cache.py`; rewrite `test_ladder.py`/`test_graceful_degradation.py`.

**Depends on:** KR-1 (browse base rewired; keys removed). Ref KR-3 (`fetch_clean` for rungs 1-2).
External tool: `agent-browser` + `lightpanda` CLIs (KR-7 packaging bootstraps; KR-4 drives them).

**Rough tasks:** (1) `AgentBrowserProvider.snapshot`/`browse` (Bash `agent-browser open/snapshot -i
--json/click/fill/press/wait`, re-snapshot loop, ref grounding); (2) Stagehand prompt constants +
act/extract/observe mapping; (3) AQL parser port + host-model resolver + grounding; (4) the 4-rung
ladder + lightpanda fallback heuristic (empty/error snapshot → chrome); (5) keyless auth
(`state save`/`--state`/`cookies set --curl`) wiring; (6) tests (subprocess-mocked).

---

## KR-5 — Keyless retrieval: FTS5/BM25 + host-model LLM-rerank (LanceDB/local behind `[local]`)

**Scope.** Make `RetrievalEngine` FTS-default with an optional dense lane; swap the Cohere reranker
for `ClaudeCodeReranker` (host-model LLM-rerank, the default); add the lexical semantic-cache
backend; gate LanceDB + local neural models behind `[local]` with the 25k-chunk auto-enable. Keep
all the fusion math verbatim.

**Implements:** dossier 15 (§2 FTS lane, §3 fusion math, §4 optional local bi-encoder + threshold,
§5 the rerank decision — host-model default, §6 lexical/cosine cache, §7 gate/re-retrieve/
expand_symbols/cascade, §8 the no-overkill wiring).

**ADDS / REWRITES (`src/`):**
- `retrieval/engine.py` → constructor takes `embedder: EmbedProvider | None = None` +
  `lance_dir: Path | None`; FTS-only default path; RRF-fuse when dense lane on; expand_symbols
  upgraded to wiki-link neighbors (links table).
- `retrieval/rerank.py` → `ClaudeCodeReranker` (the verbatim LLM-rerank prompt, pointwise 0..1,
  temp=0, ~800-char truncate, JSON out, graceful 0.0 default); `get_reranker` `host`/`local`/`none`;
  `BGEReranker` stays but `[local]` (ms-marco MiniLM default for `local`).
- `retrieval/cache.py` → `LexicalCacheBackend` (token-set overlap, 0.85), selected when
  `embedder is None`; cosine 0.92 when `[local]` bi-encoder resident.
- `retrieval/constants.py` → add `SEMANTIC_CACHE_THRESHOLD_LEXICAL=0.85`,
  `NEURAL_RECALL_VAULT_THRESHOLD=25_000`, `LLM_RERANK_TRUNC_CHARS=800`, `LLM_RERANK_BATCH=30`.
- `embed/bge_local.py` (NEW, `[local]`: `BgeLocalEmbedProvider` dim 384, query prefix); `embed/
  store.py` LanceDB import-guarded `[local]`.
- `tests/test_retrieval/` — keep fusion/cache/fts; add `ClaudeCodeReranker` (mock host call) +
  lexical-cache tests; move LanceDB store test behind a `local` marker.

**Depends on:** KR-1 (Cohere removed, config knobs). Standalone otherwise (owns `retrieval/`+`embed/`).

**Rough tasks:** (1) FTS-default engine constructor + branch; (2) `ClaudeCodeReranker` + frozen
prompt + parse/graceful-degradation; (3) `get_reranker` host/local/none; (4) `LexicalCacheBackend`
+ selection; (5) constants; (6) `BgeLocalEmbedProvider` ([local]) + 25k auto-enable; (7)
expand_symbols wiki-link upgrade; (8) tests (mock host reranker, no torch in default test run).

---

## KR-6 — Loop levers + funnel/pipeline/skill rewire

**Scope.** Two halves: (a) wire the new keyless seams (KR-2…KR-5) into `cli/research.py` builders +
`funnel`/`pipeline`; (b) ship the 5 keyless loop levers from dossier 16 (grader loop, delegation
contract + caps, recitation gate, effort continuum + token ceiling, confidence-band hedging).

**Implements:** dossier 16 (§3 delegation + caps, §4 grader loop, §5 recitation gate, §6 effort +
ceiling, §7 hedging) + the rewire (INTERFACES_KEYLESS §6.1).

**REWIRES (`src/`):**
- `cli/research.py::_build_providers` → keyless providers (`WebSearchToolProvider` + `DdgsProvider`
  + optional `SearxngProvider` + intent-routed verticals); `_build_tiered_fetcher` → keyless 4-rung;
  `_build_embedder`→None default; `_build_reranker`→`ClaudeCodeReranker`.
- `funnel/fanout.py`/`orchestrator.py` — pick up keyless providers via `FunnelDeps` (no logic change).
- `pipeline.py` — `_gather`/`_retrieve`/`_synthesize` inherit the keyless wiring (no shape change).

**ADDS (`src/` + `skills/`):**
- `quality/grader.py` (wraps `calibrate/judge.py::LLMJudge` to emit patcher-shaped `Finding`s);
  new skill `skills/bad-research-12.5-grader.md` (full-tier, loop ≤3).
- `quality/recitation.py` (`recitation_findings`, n-gram 12 / overlap 0.50) wired into
  `skills/bad-research-16-readability-audit.md`.
- `grounding/verifier.py` → emit `confidence_band`; `skills/bad-research-14-patcher.md` → hedge
  medium/low claims.
- `skills/bad-research.md` spawn contract → 7-field delegation; each step skill's `Task` template
  gets `objective/output_shape/tools_allowed/stop_conditions`.
- `skills/routing_constants.py` → `FETCHER_TOOLCALL_CAP`, `FETCHER_TIMEOUT_S=300`,
  `INVESTIGATOR_TIMEOUT_S=900`, `SUBAGENT_SOURCE_KILL=100`, `MAX_GRADER_REVISIONS=3`.
- `cli/research.py` + `skills/router.py` → wire the stub `--reasoning-effort` (`research.py:118`) +
  add `--max-tokens` → effort continuum + degrade order.
- `tests/test_skills`, `tests/test_grounding`, `tests/test_quality`, `tests/test_pipeline` — add
  the 5 levers + the rewire smoke tests.

**Depends on:** KR-2, KR-3, KR-4, KR-5 (the seams must exist to wire).

**Rough tasks:** (1) rewire `cli/research.py` builders; (2) grader loop (`quality/grader.py` +
12.5 skill + judge findings-extension); (3) delegation contract + caps; (4) `quality/recitation.py`
+ stage-16 wiring; (5) effort continuum + token ceiling + degrade order; (6) confidence-band emit +
patcher hedge; (7) tests.

---

## KR-7 — Packaging, tests, calibration (the keyless launch-complete pass)

**Scope.** Make `pipx install bad-research` + `bad install` keyless-clean: install targets
(`~/.claude/skills/bad-research/`, agents, settings), the external-CLI bootstrap (agent-browser /
lightpanda / yt-dlp / git / optional SearXNG), the `bad doctor` keyless health check, the full test
suite green (80% floor over the keyless surface), and the keyless calibration plan.

**Implements:** INTERFACES_KEYLESS §7 (deps + external CLIs), §8 install target; dossiers' calibration
plans (12 §11, 13 §7.2, 15 §8.4, 14 §11 smoke test).

**ADDS / REWRITES (`src/` + tests):**
- `cli/install.py` → keyless install (drop skills/agents/hook into `~/.claude/`; bootstrap or
  document agent-browser/lightpanda/yt-dlp/git; `agent-browser install` for Chrome-for-Testing).
- `cli/doctor.py` → keyless health check (host tool present, agent-browser/lightpanda/yt-dlp/git
  present, optional SearXNG reachable, NLI/local models if `[local]`). No key checks.
- `calibrate/` → keyless calibration: `fetch_clean` vs (read-only, one-time) Firecrawl free tier
  (dossier 12 §11); keyless search vs Sonar `/search` pass-rate (dossier 13 §7.2); rerank A/B nDCG
  (host vs ms-marco vs none, dossier 15 §8.4); grounding injected-claim recall. The judge stays
  offline-only.
- Full `tests/` pass: rewrite `test_install`, `test_packaging`, `test_providers.py`; the `live`
  marker gates the keyless API probes; `local` marker gates torch tests.

**Depends on:** KR-1…KR-6 (the whole thing green).

**Rough tasks:** (1) keyless `bad install` + external-CLI bootstrap; (2) keyless `bad doctor`; (3)
keyless calibration harness + plan doc; (4) full test-suite rewrite + 80% floor over keyless
surface; (5) the agent-browser live smoke test (dossier 14 §11); (6) `docker-compose`/install-flow
verification ("done" = keyless skill runs end-to-end with zero third-party key).

---

## Cross-plan invariants (every KR plan must honor)

1. **Zero third-party key, anywhere.** Every seam works with only the Claude Code host + local
   OSS/CLIs. `grep cohere|tavily|exa|firecrawl|browserbase|agentql|browser_use src/` → 0 hits after KR-1.
2. **Bind to the frozen contract.** Use the `docs/INTERFACES_KEYLESS.md` signatures + constants
   verbatim; if a plan needs a new shared type, it adds it to INTERFACES_KEYLESS first.
3. **KNOWN / DESIGNED / CALIBRATE labels** on every component (KNOWN = from a dossier's verbatim
   source; DESIGNED = the keyless reimplementation; CALIBRATE = needs the §KR-7 eval).
4. **Don't rewrite the kept seams** (INTERFACES_KEYLESS §2) — call them. This is a refactor.
5. **Incremental write discipline** — one file fully before the next; report actual `wc -l` +
   findings per file (per the parallel-batch workflow).
6. **Resolve the 4 ambiguities** (INTERFACES_KEYLESS §9) with the user before KR-1 deletes the
   `anthropic` core dep or KR-7 designs the agent-browser bootstrap.
