# Bad Research — KEYLESS Interfaces Contract (FROZEN — single source of truth for the KR rebuild)

> **Status:** FROZEN 2026-05-27. This supersedes the provider/embedder/browse/reranker seams of
> `docs/INTERFACES.md` for the keyless re-architecture. Every KR plan (KR-1…KR-7) MUST use these
> names, signatures, paths, and constants **verbatim**. `docs/INTERFACES.md` remains the authority
> for the seams this file does NOT touch (the LLM seam, grounding API, vault SQLite schema, the
> cost meter, the 16-stage skill graph).
>
> **Two FINAL decisions this contract enforces:**
> 1. **Pure keyless — REMOVE the API-provider code entirely.** No Tavily/Exa/Sonar(Perplexity)/
>    Firecrawl/Cohere/Browserbase/AgentQL/Browser-Use(cloud) anywhere in core. LanceDB leaves core
>    (moves to the optional `[local]` extra).
> 2. **The skill stays a keyless Claude Code skill (the hyperresearch model).** The host model
>    supplies all inference (no `ANTHROPIC_API_KEY` in the skill path — the host provides it); the
>    web is reached keylessly via the Claude Code `WebSearch`/`WebFetch` tools + local OSS/CLIs.
>
> **The keyless rule (absolute):** every seam below works with **zero third-party API key** — only
> the Claude Code host model + local OSS libraries + local CLI tools (`agent-browser`, `lightpanda`,
> `yt-dlp`, `git`). If a seam needs a paid key, it is wrong.
>
> **This is a targeted refactor, not a greenfield rebuild.** The keyless-ready code stays: the
> `llm/` seam, `grounding/`, `quality/`, `core/` (vault/fetcher/similarity/notes), the `skills/`
> graph, the `funnel/` orchestration shape, the retrieval fusion math, the calibration harness.
>
> **Evidence base:** dossiers `docs/investigation/12_KEYLESS_CONTENT.md` (content),
> `13_KEYLESS_SEARCH.md` (search + verticals), `14_KEYLESS_BROWSE.md` (browse),
> `15_KEYLESS_RETRIEVAL.md` (retrieval), `16_KEYLESS_LOOP.md` (loop). Every constant traces to one.

---

## 0. What changes, in one paragraph

The paid web/search/browse/embed/rerank layer is deleted. In its place: **search** runs over the
host `WebSearch` tool + `ddgs` + optional self-hosted SearXNG + 7 keyless scholarly verticals,
fused with RRF k=60 and reranked by the host model. **Content** (`URL → clean markdown`) becomes a
deterministic local pipeline (`httpx` + `crawl4ai` + `trafilatura` + `pymupdf` + the verbatim
Firecrawl strip/metadata ports + 6 source-tier extractors). **Browse** becomes the local
`agent-browser` CLI (Chrome-for-Testing / lightpanda over CDP) driven by Claude Code, replacing
Browserbase/AgentQL/Stagehand/Browser-Use. **Retrieval** keeps the FTS5/BM25 lane + the fusion math
and swaps the Cohere reranker for **host-model LLM-rerank** (default), with LanceDB + local neural
models behind a `[local]` extra. The **loop** gains 5 keyless levers (grader loop, delegation
contract, recitation gate, effort continuum, confidence hedging) — all prompt/constant/deterministic.

---

## 1. REMOVED — modules, seams, tests, deps (exact paths)

### 1.1 Source modules to DELETE

**Web API providers + cascade** (`web/providers/` — the entire dir, plus the two top-level API providers):
- `src/bad_research/web/providers/tavily_provider.py` — DELETE (Tavily key)
- `src/bad_research/web/providers/sonar_provider.py` — DELETE (Perplexity/PPLX key)
- `src/bad_research/web/providers/firecrawl_provider.py` — DELETE (Firecrawl key)
- `src/bad_research/web/providers/searxng_provider.py` — **MOVE/REWRITE** → keyless `SearxngProvider`
  under `web/search/` (self-host JSON, `cost_per_search=0.0`, no env var). The *file* leaves
  `providers/`; the *capability* stays as a keyless T1 source (dossier 13 §1).
- `src/bad_research/web/providers/cascade.py` — DELETE (`CascadeProvider`; the key-gated cascade).
- `src/bad_research/web/providers/__init__.py` — DELETE (dir removed).
- `src/bad_research/web/exa_provider.py` — DELETE (Exa key)
- `web/base.py::_build_cascade()` — DELETE (reads `PERPLEXITY_API_KEY`/`TAVILY_API_KEY`/`EXA_API_KEY`/
  `FIRECRAWL_API_KEY`); `web/base.py::get_provider()` — REWRITE to the keyless registry (§3.1).

**Browse cloud/keyed providers** (`browse/` — the keyed backends + the Stagehand/AgentQL extractors):
- `src/bad_research/browse/browse_browserbase.py` — DELETE (Browserbase key + Stagehand SDK)
- `src/bad_research/browse/browse_browseruse.py` — DELETE (Browser-Use cloud lib)
- `src/bad_research/browse/extract_agentql.py` — DELETE (AgentQL key)
- `src/bad_research/browse/extract_stagehand.py` — DELETE (Stagehand SDK)
- `browse/base.py::get_browse_provider()` — REWRITE to return the keyless `AgentBrowserProvider`
  (§4.3); drop the `browserbase`/`browser-use` branches that read keys.
- `browse/ladder.py::_do_browse()` + the `_browserbase`/`_browseruse` seams — REWRITE: rung-3 is
  now `agent-browser` (chrome) with a lightpanda rung-2.5 (§4.4); no key branches.

**Cohere embedder + reranker:**
- `src/bad_research/embed/cohere.py` — DELETE (`CohereEmbedProvider`; Cohere key). The `embed/`
  package and the `EmbedProvider` Protocol (`embed/base.py`) STAY but become **optional** — only
  materialized under `[local]` (§5.4).
- `retrieval/rerank.py::CohereReranker` — DELETE the class + the Cohere branch of `get_reranker()`.
  The file stays; `BGEReranker` moves behind `[local]`; the new default is `ClaudeCodeReranker` (§5.3).

**LanceDB vector store (leaves core):**
- `src/bad_research/retrieval/store.py` (`LanceChunkStore`) — MOVE behind `[local]` import-guard; it
  is no longer constructed in the default `RetrievalEngine` path. `engine.py` becomes FTS-default
  with an optional vector lane (§5.2). The vault `chunks` LanceDB table (INTERFACES.md vault schema)
  is **removed from the default**; SQLite-FTS5 is the only mandatory index.

### 1.2 Tests to DELETE (mirror the removed modules)

- `tests/test_web/` — delete every test that targets `tavily_provider`, `sonar_provider`,
  `firecrawl_provider`, `exa_provider`, `cascade` (keep/rewrite any `web/base.py::WebResult` +
  keyless-provider tests).
- `tests/test_browse/test_browse_browserbase.py`, `test_browse_browseruse.py`,
  `test_extract_agentql.py`, `test_extract_stagehand.py` — DELETE. Keep `test_base.py`,
  `test_cache.py`, `test_extract_llm.py`, `test_ladder.py`, `test_graceful_degradation.py`,
  `test_fetcher_hook.py` (rewire to the keyless ladder).
- `tests/test_embed/test_cohere.py` — DELETE (or move to `tests/test_local/` under `[local]`).
- `tests/test_retrieval/` — keep fusion/cache/fts tests; move any LanceDB store test behind a
  `local` marker.
- `tests/test_providers.py` — REWRITE: the registry no longer lists keyed providers (§3.3).

### 1.3 Dependencies to REMOVE (from `pyproject.toml`)

- Remove the entire `[project.optional-dependencies] search` extra (`tavily-python`, `exa-py`,
  `cohere`, `firecrawl-py`).
- Remove `browser-use` and `agentql` from the `browse` extra.
- Remove `lancedb` + `pyarrow` from **core** `dependencies` (they move to `[local]`).
- The `all` extra is redefined (§6).

> **Net removal:** 6 web-provider files + cascade + 4 browse files + Cohere embed + Cohere rerank
> class + LanceDB-from-core, and 8 PyPI packages (tavily-python, exa-py, cohere, firecrawl-py,
> browser-use, agentql, + lancedb/pyarrow demoted). **NO `cohere/tavily/exa/firecrawl/browserbase/
> agentql/browser-use` import survives anywhere in core after KR-1.**

---

## 2. KEPT — the keyless-ready seams that DO NOT change

These are correct as built; KR plans must not rewrite them, only call them.

- `llm/base.py` (`LLMProvider`, `LLMMessage`, `LLMResponse`, `get_llm_provider`) + `llm/anthropic.py`
  — the host-model seam. In the skill path the host supplies inference; the seam is the headless
  bridge (`pipeline.run_query`) + the calibration runner. UNCHANGED.
- `grounding/` (all of it: `extract.py`, `anchors.py`, `nli.py`, `verifier.py`, `gate.py`,
  `render.py`) — the no-hallucination spine. NLI model `nli-deberta-v3-base` is a local `[local]`
  download already (dossier 16 §2). UNCHANGED except the §7 confidence-band emit (KR-6).
- `quality/` (all: `prefilter.py`, `content_filter.py`, `dedup.py`, `relevance.py`, `rank.py`,
  `sources.py`, `injection.py`) — SEO-farm score, DOMAIN_TIER, shingle-Jaccard dedup, 0.70 gate,
  the untrusted-content injection preamble. All deterministic/keyless. UNCHANGED. (KR-6 ADDS
  `quality/recitation.py` + `quality/grader.py`.)
- `core/` (`vault.py`, `fetcher.py`, `similarity.py`, `note.py`, `sync.py`, `db.py`, etc.) — the
  vault, markdown-is-truth, MinHash/LSH dedup. `core/fetcher.py` is the Tier-0 HTTP path and is
  keyless already. UNCHANGED.
- `search/fts.py` + `search/filters.py` — the tuned FTS5/BM25 note lane (weights 10/1/5/3, status
  multipliers). Keyless (SQLite compiled in). UNCHANGED — becomes the retrieval default lane.
- `retrieval/{fusion,cache,fts_chunks,chunker,chunker_code,anchors,constants}.py` — the fusion math
  (RRF, α=0.7 hybrid, three-tier blend, source-type weight), the semantic cache (negation guard),
  the FTS chunk lane, the chunkers. All keyless arithmetic. UNCHANGED (cache gains a lexical backend,
  §5.5).
- `funnel/` orchestration shape (`orchestrator.py::gather` 6-stage A→F, `_async.py::acall`,
  `dedup.py`, `rank.py` RRF+utility, `read.py` chained-crawl + JS-cosine, `filter.py`, `store.py`,
  `canonical.py`) — the scraper funnel. UNCHANGED in shape; only `FunnelDeps.providers` now holds
  keyless providers and `FunnelDeps.fetcher` is the keyless tiered fetcher (KR-6 rewires the wiring,
  not the funnel logic).
- `skills/` (the 20 `.md` step skills + `router.py` + `routing_constants.py`) — the Claude Code
  skill graph IS the orchestrator. UNCHANGED except the KR-6 loop-lever edits (delegation contract,
  grader stage 12.5, effort plumbing).
- `calibrate/` + `pipeline.py` + `providers.py` (registry rewritten, §3.3) — the headless bridge +
  offline judge. UNCHANGED except the registry table.
- `config.py` (`BadResearchConfig`) — STAYS; KR-1 removes the dead `embed_model`/`rerank_model`
  Cohere defaults and adds keyless knobs (§3.4).

---

## 3. NEW / CHANGED keyless seams — search (KR-2) + verticals

> Source: dossier 13 (§0 three-tier source strategy, §1 SearXNG, §2 fan-out, §3 RRF k=60 ranking,
> §4 keyless rerank ladder, §8 the 7 scholarly verticals). The `WebResult` shape (`web/base.py`)
> and `SearchQuery` (`web/base.py`) are KEPT verbatim — every keyless provider returns `WebResult`.

### 3.1 The keyless provider factory — REWRITE `web/base.py::get_provider`

```python
# web/base.py  (KR-2; replaces the key-gated get_provider + deletes _build_cascade)
def get_provider(name: str | None = None) -> WebProvider:
    """Keyless web provider factory. Default = the host WebSearch tool adapter.
    Every branch is keyless (host tool / local lib / self-host). No env var, no key."""
    # default + "websearch" → the host WebSearch tool (dossier 13 §0)
    # "ddgs"      → DdgsProvider (multi-engine keyless lib, dossier 13 §8.1(7))
    # "searxng"   → SearxngProvider (self-host JSON, default endpoint localhost:8080, no key)
    # "builtin"   → BuiltinProvider (core/fetcher httpx — the Tier-0 fetch path; KEEP)
    # "crawl4ai"  → Crawl4AIProvider (local JS render; KEEP, [browse] extra)
    ...
```

### 3.2 The keyless search layer — `web/search/` (NEW package, KR-2)

```python
# web/search/base.py — KeylessSearch is the orchestration object the funnel/skill drive.
@dataclass
class KeylessSearchConfig:
    rrf_k: int = 60                        # dossier 13 §3.2 (frozen)
    relevance_threshold: float = 0.70      # dossier 13 §3.4 (frozen)
    min_pass_fraction: float = 0.30        # dossier 13 §3.4 (frozen)
    max_rounds: int = 3                    # dossier 13 §3.4 (light=2, full=3)
    rerank_top_n: int = 30                 # LLM-rerank only L1 survivors (§4.4)

class WebSearchToolProvider:               # name="websearch"; cost_per_search=0.0; keyless DEFAULT
    name: str = "websearch"
    capabilities = frozenset({"keyword", "batch_via_loop"})
    cost_per_search: float = 0.0
    p50_ms: int = 0
    def search(self, query: str, max_results: int = 10,
               allowed: list[str] | None = None, blocked: list[str] | None = None) -> list[WebResult]: ...
    def search_ex(self, q: SearchQuery) -> list[WebResult]: ...   # parses host-tool Links: array
    def fetch(self, url: str) -> WebResult: ...                   # delegates to fetch_clean (§4 content)
    # NOTE: the host WebSearch/WebFetch TOOLS are invoked by the orchestrator (Claude Code); this
    # adapter parses the tool's `Links:` array into content-less WebResult rows (dossier 13 §0).

class DdgsProvider:                        # name="ddgs"; keyless multi-engine aggregator lib
    name: str = "ddgs"; cost_per_search: float = 0.0
    def search_ex(self, q: SearchQuery) -> list[WebResult]: ...   # DDGS().text(...) → WebResult[]

class SearxngProvider:                     # name="searxng"; self-host JSON; default localhost:8080
    name: str = "searxng"; cost_per_search: float = 0.0
    def __init__(self, endpoint: str = "http://localhost:8080"): ...
    def search_ex(self, q: SearchQuery) -> list[WebResult]: ...

# web/search/rank.py — the keyless ranking pipeline (dossier 13 §3, §4)
def rrf_fuse(ranked_lists: list[list[WebResult]], *, k: int = 60) -> list[WebResult]: ...
    # rank-based RRF + consensus tie-break (more sources wins at equal RRF). dossier 13 §3.2.
def rrf_fuse_with_verticals(ranked_lists, *, k: int = 60) -> list[WebResult]: ...
    # §8.3: DOI-first dedup identity + metadata-richness tie-break for scholarly rows.

# web/search/rerank.py — host-model-as-reranker (the keyless neural rerank, dossier 13 §4.1)
class HostModelReranker:                   # the DEFAULT reranker for SEARCH candidates
    """Batches L1-survivor candidates (≤30) into ONE host-model call; returns 0..1 relevance
    scores. Uses the verbatim LLM-rerank prompt (§5.3 / dossier 13 §4.1) with the injection
    preamble. Drop-in for the retrieval Reranker Protocol — feeds the 0.70 gate / <30% loop."""
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...

# web/search/loop.py — the retrieve-until-good loop (dossier 13 §3.4)
def retrieve_until_good(question: str, *, cfg: KeylessSearchConfig,
                        expand, fan_out, rerank) -> list[WebResult]: ...
    # ≥30% clear 0.70 → return; else reformulate + re-fan, ≤max_rounds.
```

### 3.3 The 7 keyless scholarly verticals — `web/search/verticals.py` (NEW, KR-2)

All implement the same `WebProvider`/`search_ex` surface and return `WebResult` with rich
`metadata={doi, year, authors, citations, oa_pdf, source, rank}` (dossier 13 §8.1). All keyless
(probed live 2026-05-26, dossier 13 §8.0). Route in by intent (§8.2); fan only on seed queries.

| Class | source tag | endpoint (keyless) | capabilities |
|---|---|---|---|
| `ArxivProvider` | `arxiv` | `export.arxiv.org/api/query` (Atom) | `{"academic","oa_pdf"}` |
| `OpenAlexProvider` | `openalex` | `api.openalex.org/works?...&mailto=` | `{"academic","oa_pdf","citation_graph"}` |
| `CrossrefProvider` | `crossref` | `api.crossref.org/works` (DOI spine) | `{"academic","doi_registry"}` |
| `SemanticScholarProvider` | `s2` | `api.semanticscholar.org/graph/v1` (429-backoff, best-effort) | `{"academic","tldr","oa_pdf"}` |
| `EuropePMCProvider` | `europepmc` | `ebi.ac.uk/europepmc/webservices/rest/search` | `{"medical","academic"}` |
| `PubMedProvider` | `pubmed` | `eutils.ncbi.nlm.nih.gov/entrez/eutils` (esearch+esummary) | `{"medical","academic"}` |
| `WikipediaProvider` | `wikipedia` | `*.wikipedia.org` REST+MediaWiki + Wikidata disambig | `{"grounding","entity_link"}` |

```python
# web/search/route.py (dossier 13 §8.2) — intent → extra keyless verticals (besides WebSearch)
VERTICAL_ROUTES = {
    "academic":  ["openalex", "arxiv", "semantic_scholar", "crossref"],
    "medical":   ["europe_pmc", "pubmed", "openalex"],
    "technical": ["arxiv", "openalex", "ddgs"],
    "general":   [],
}
def route_query(question: str, queries: list[str], intent: str) -> list[tuple[str, str]]: ...
    # WebSearch on every query (baseline) + Wikipedia (1 seed grounding) + verticals on ≤2 seeds.
```

### 3.4 `config.py` keyless knobs (KR-1)

```python
# REMOVE the dead Cohere defaults; ADD keyless knobs:
@dataclass
class BadResearchConfig:
    ...
    # rerank_model default flips to the host-model reranker; "local" selects ms-marco MiniLM ([local])
    reranker: Literal["host", "local", "none"] = "host"      # was embed_model/rerank_model="...cohere..."
    neural_recall: bool = False                              # opt-in local bi-encoder lane ([local])
    searxng_endpoint: str = "http://localhost:8080"          # self-host T1; no key
    browse_engine: Literal["lightpanda", "chrome"] = "lightpanda"  # rung-2.5 default (dossier 14 §12.5)
    effort: Literal["minimal", "low", "medium", "high"] = "medium"  # KR-6, wires the stub flag
    max_tokens: int | None = None                            # KR-6 per-run ceiling (opt-in)
```

### 3.5 Provider registry — REWRITE `providers.py::PROVIDERS` (KR-1)

```python
# providers.py — keyless registry only (powers `bad doctor`); NO keyed provider rows.
PROVIDERS = (
    Provider("anthropic-host", None, None, "(base)", "llm"),       # host supplies inference; no key
    Provider("websearch", None, None, "(base)", "search"),         # host WebSearch tool
    Provider("ddgs", None, "ddgs", "(base)", "search"),            # keyless multi-engine lib
    Provider("searxng", None, None, "(base)", "search"),           # self-host, no key
    Provider("crawl4ai", None, "crawl4ai", "browse", "browse"),    # local JS render
    Provider("agent-browser", None, None, "browse", "browse"),     # local CLI (CDP)
    Provider("arxiv", None, None, "(base)", "search"),             # keyless vertical (httpx)
    Provider("openalex", None, None, "(base)", "search"),
    Provider("crossref", None, None, "(base)", "search"),
    Provider("europepmc", None, None, "(base)", "search"),
    Provider("pubmed", None, None, "(base)", "search"),
    Provider("wikipedia", None, None, "(base)", "search"),
    Provider("bge-local", None, "sentence_transformers", "local", "embed"),   # [local] opt-in
    Provider("ms-marco-local", None, "sentence_transformers", "local", "rerank"),
    Provider("nli-deberta", None, "sentence_transformers", "grounding", "nli"),
)
# requires_key is False for every row → `active` reduces to import_present (no key check matters).
```

---

## 4. NEW / CHANGED keyless seams — content (KR-3) + browse (KR-4)

> Content source: dossier 12 (`fetch_clean`, the verbatim Firecrawl ports, PruningContentFilter,
> highlights, the 6 source-tier extractors). Browse source: dossier 14 (agent-browser CLI, the
> 4-rung ladder, the Stagehand/AQL ports, lightpanda, keyless auth).

### 4.1 `web/content/fetch_clean.py` (NEW package `web/content/`, KR-3)

```python
# web/content/fetch_clean.py — keyless URL → model-ready markdown (dossier 12 §0, §11)
def fetch_clean(url: str, query: str | None = None, *, want_llm_clean: bool = False,
                formats: tuple[str, ...] = ("markdown", "metadata", "links")) -> dict:
    """Returns {markdown, metadata, published_date, links, highlights?, url}.
    Pipeline: cache → classify → tiered fetch (httpx→crawl4ai→WebFetch) → charset decode →
    strip_boilerplate → main_content (Pruning|BM25) → html2text+citations → postclean →
    (opt) llm_clean (host model) → (opt) highlights → metadata+freshness → cache. All keyless.
    Deps: httpx, beautifulsoup4, lxml, crawl4ai, trafilatura, pymupdf(+pymupdf4llm), rank_bm25,
    snowballstemmer, dateparser. NO API key."""

# the verbatim Firecrawl ports (dossier 12 §2, §8) — deterministic, $0:
def strip_boilerplate(html: str, base_url: str, only_main: bool = True) -> str: ...   # §2 selector list
def main_content(stripped_html: str, query: str | None = None) -> str: ...            # §3 Pruning|BM25 +trafilatura fallback
def extract_metadata(stripped_html: str, url: str) -> dict: ...                       # §8 extractMetadata.ts port
def extract_published_date(stripped_html: str) -> str | None: ...                     # §8.1 chain + dateparser
def highlights(markdown: str, query: str, k: int = 3) -> list[dict]: ...              # §7 BM25 query-biased passages
def pdf_to_markdown(pdf_bytes: bytes) -> str: ...                                      # §5 pymupdf4llm
def llm_clean(markdown: str) -> str: ...                                              # §6 host model + FIRECRAWL_CLEAN_PROMPT (verbatim)

# the source-type classifier + 6 keyless extractors (dossier 12 §"non-HTML sources")
def classify_source(url: str) -> str: ...
    # → "youtube" | "github" | "arxiv" | "feed" | "sitemap" | "llms_txt" | "html_or_pdf"
# each emits the NORMALIZED VAULT NOTE shape (dossier 12 §"normalized vault note"):
#   {title, source, source_type, fetched_at, published, provenance, markdown}
def youtube_transcript(url: str) -> dict: ...      # A — yt-dlp --skip-download (CLI), VTT clean, host densify
def github_clone_notes(repo_url: str) -> list[dict]: ...  # B — git clone --depth=1 (CLI) | raw.githubusercontent
def arxiv_source_notes(url: str) -> dict: ...      # C — export.arxiv.org/e-print tarball (keyless), de-TeX
def feed_notes(feed_url: str) -> list[dict]: ...   # D — feedparser
def sitemap_urls(host: str) -> list[dict]: ...     # E — robots.txt Sitemap / sitemap.xml (xml.etree)
def llms_txt_notes(host: str) -> dict | list[dict]: ...  # F — /llms-full.txt | /llms.txt
```

`FIRECRAWL_CLEAN_PROMPT` (dossier 12 §6.1, verbatim) ships as a module constant — the injection-
defended content-cleaning system prompt sent to the **host model** (no key). The SSRF/private-IP
block (dossier 12 §1.3) and the 3-layer charset detect (§1.2) are mandatory in the fetch path.

### 4.2 `WebResult` ⇄ `fetch_clean` bridge (KR-3)

`WebSearchToolProvider.fetch(url)` and the funnel's tiered fetcher call `fetch_clean(url, query=...)`
and map its dict → `WebResult(url, title=metadata.title, content=markdown, links=links,
metadata={**metadata, published_date, highlights})`. The `looks_like_junk()`/
`looks_like_login_wall()` gates on `WebResult` (KEPT) drive ladder escalation.

### 4.3 `browse/base.py` + `browse/agent_browser.py` — REWRITE the browse seam (KR-4)

```python
# browse/base.py — Protocols KEPT verbatim (BrowseProvider.browse, ExtractProvider.extract);
# get_browse_provider rewritten to return the keyless AgentBrowserProvider (no key branches).
def get_browse_provider(name: str | None = None) -> BrowseProvider | None:
    # default → AgentBrowserProvider() if the agent-browser CLI is installed, else None (graceful)
    ...
def get_extract_provider(name: str | None = None) -> ExtractProvider | None:
    # default "llm" → LLMExtractProvider (KEPT, host model); "aql" → AqlExtractProvider (NEW, §6 ports)
    ...

# browse/agent_browser.py (NEW) — drives the local agent-browser CLI via Bash (dossier 14)
class AgentBrowserProvider:                  # name="agent-browser"; keyless (local Chrome/lightpanda over CDP)
    name: str = "agent-browser"
    def __init__(self, engine: Literal["lightpanda", "chrome"] = "lightpanda"): ...
    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult: ...
    # the §4.2 ReAct loop: open → snapshot -i --json → (Claude Code picks @eN) → click/fill/press →
    # wait → re-snapshot → … → extract. Claude Code IS the agent brain (replaces the keyed `chat`).
    def snapshot(self, *, interactive: bool = True) -> dict: ...   # @eN refs + grounding refs map

# the keyless typed-extraction ports (dossier 14 §5, §6):
class AqlExtractProvider:                     # name="aql"; the ported AgentQL parser + host-model resolver
    def extract(self, source, schema, instruction: str = "") -> dict: ...
# Stagehand act/extract/observe prompts ship as verbatim constants (dossier 14 §5.1-§5.3, §10).
```

### 4.4 The 4-rung keyless ladder — REWRITE `browse/ladder.py::fetch_tiered` (KR-4)

```python
# fetch_tiered(url, *, tier_max, instruction=None, schema=None, ...) — KEPT signature, keyless rungs:
#   rung 1  httpx GET (core/fetcher) ............................. $0  static HTML/APIs
#   rung 2  crawl4ai local JS render → fit_markdown .............. $0  clean MD, no interaction
#   rung 2.5 agent-browser --engine lightpanda (snapshot+eval) ... $0  fast keyless JS render (dossier 14 §12.5)
#   rung 3  agent-browser --engine chrome (login/click/typed) .... $0  interaction/auth/screenshot
# Escalation signals: looks_like_junk()/looks_like_login_wall() (KEPT). NO rung that costs money.
# lightpanda fallback: empty/error snapshot → retry same command with --engine chrome (§12.5).
```

---

## 5. NEW / CHANGED keyless seams — retrieval (KR-5)

> Source: dossier 15. Default = **FTS5/BM25 + host-model LLM-rerank + token-set cache, zero local
> model weights.** LanceDB + local neural models behind `[local]`, auto-enabled above a vault-size
> threshold.

### 5.1 `RetrievalEngine` — FTS-default, optional vector lane (KR-5)

```python
# retrieval/engine.py — REWRITE the constructor so the vector lane (LanceDB + EmbedProvider) is
# OPTIONAL. Default keyless path: FTS5/BM25 recall → (optional dense) → fuse → LLM-rerank → blend → gate.
class RetrievalEngine:
    def __init__(self, *, cache_db: Path, reranker: Reranker,
                 embedder: EmbedProvider | None = None,   # None = FTS-only (default keyless)
                 lance_dir: Path | None = None,           # None unless [local] neural recall is on
                 alpha: float = ALPHA, gate: float = RELEVANCE_GATE,
                 top_k_retrieve: int = TOP_K_RETRIEVE): ...
    def index(self, notes: Iterable[Note]) -> None: ...   # FTS index always; LanceDB only if embedder set
    def search(self, query: str, *, mode: Literal["light","full"], top_k: int) -> list[Chunk]: ...
    # FTS-only: initial = min-max(BM25). Dense on: fuse via RRF k=60 (two incomparable scales, §3.1).
```

### 5.2 Fusion — keep the math, default to FTS-only `initial` (KR-5)

`hybrid_fuse(α=0.7)`, `three_tier_fuse` (weights 0.75/0.60/0.40, deep-rank penalty 0.005),
`apply_source_type_weight`, `rrf_merge(k=60)` — ALL KEPT verbatim (`retrieval/fusion.py`,
unchanged). When `embedder is None`, `initial_score` = min-max(BM25); when the dense lane is on,
RRF-fuse BM25 + bi-encoder ranks (dossier 15 §3.1).

### 5.3 `ClaudeCodeReranker` — the DEFAULT reranker (KR-5)

```python
# retrieval/rerank.py — NEW default; CohereReranker DELETED, BGEReranker behind [local].
class ClaudeCodeReranker:                     # implements Reranker; keyless (host model); the DEFAULT
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...
    # batches ≤30 candidates into ONE host-model call, the verbatim LLM-RERANK PROMPT (dossier 15
    # §5.3): pointwise 0..1 scores, temperature=0, chunk truncated ~800 chars, JSON-array out,
    # injection preamble. Malformed item → 0.0 (graceful, three-tier blend leans on `initial`).
def get_reranker(config) -> Reranker:
    # "host"  → ClaudeCodeReranker (default)
    # "local" → BGEReranker(model="ms-marco-MiniLM-L-6-v2") ([local], dossier 15 §5.2)
    # "none"  → identity (sort by initial; --no-rerank floor, §5.1)
```

The **LLM-rerank prompt** is FROZEN verbatim from dossier 15 §5.3 (the 0.0/0.1/0.4/0.7/1.0 rubric,
JSON `[{"i":n,"s":score}]` out). It is shared with `HostModelReranker` (§3.2) — same prompt, search
vs. vault candidates.

### 5.4 `embed/` — STAYS but OPTIONAL; `BgeLocalEmbedProvider` behind `[local]` (KR-5)

```python
# embed/base.py — EmbedProvider Protocol KEPT. get_embed_provider rewritten:
def get_embed_provider(name: str = "bge-local", **kwargs) -> EmbedProvider:
    # "bge-local" → BgeLocalEmbedProvider (sentence-transformers, dim 384, [local]); cohere branch DELETED.
# embed/bge_local.py (NEW, [local]) — BgeLocalEmbedProvider(name="bge-small-en-v1.5", dim=384):
#   query prefix "Represent this sentence for searching relevant passages: ", normalize_embeddings=True.
# Auto-enabled when vault > NEURAL_RECALL_VAULT_THRESHOLD (25_000 chunks) OR config.neural_recall=True.
```

### 5.5 Semantic cache — lexical default + cosine when local embedder present (KR-5)

```python
# retrieval/cache.py — KEEP SemanticCache + negation guard. ADD:
class LexicalCacheBackend:                    # token-set similarity, threshold 0.85 (dossier 15 §6.2)
    # overlap-coefficient over normalized query tokens; selected when embedder is None (default).
# Cosine 0.92 backend (existing) used only when the [local] bi-encoder is resident (§6.1).
```

### 5.6 Retrieval constants ADDED (`retrieval/constants.py`, KR-5)

```python
SEMANTIC_CACHE_THRESHOLD_LEXICAL = 0.85      # dossier 15 §6.2
NEURAL_RECALL_VAULT_THRESHOLD    = 25_000    # dossier 15 §4.3 (auto-enable the dense lane)
LLM_RERANK_TRUNC_CHARS           = 800       # dossier 15 §5.3
LLM_RERANK_BATCH                 = 30        # full top-30; top-12 cascade is the budget knob (§7.4)
```

---

## 6. NEW / CHANGED keyless seams — loop levers (KR-6)

> Source: dossier 16. All 5 are keyless (prompt schema / frozen constant / deterministic Python the
> host runs). They wire into the existing `skills/` graph + `grounding/`/`quality/`/`calibrate/`.

1. **Grader loop (Stage 12.5)** — NEW `skills/bad-research-12.5-grader.md` (full-tier only) +
   `quality/grader.py` wrapping `calibrate/judge.py::LLMJudge` to emit patcher-shaped
   `Finding{failure_mode, severity, location, recommendation}`. Loop: judge → patch → re-judge,
   `MAX_GRADER_REVISIONS = 3`. Single host-model call per round (dossier 16 §4).
2. **4-field delegation contract + caps** — edit `skills/bad-research.md` spawn contract to the
   7-field shape (`+objective, output_shape, tools_allowed, stop_conditions`); add to each step
   skill's `Task` template. Constants in `routing_constants.py`: `FETCHER_TOOLCALL_CAP={"light":10,
   "full":20}`, `FETCHER_TIMEOUT_S=300`, `INVESTIGATOR_TIMEOUT_S=900`, `SUBAGENT_SOURCE_KILL=100`
   (dossier 16 §3).
3. **Recitation gate** — NEW `quality/recitation.py::recitation_findings(report_md, note_bodies)`,
   word-level contiguous-run match, `RECITATION_MAX_NGRAM=12`, `RECITATION_MAX_OVERLAP=0.50`, run
   in `bad-research-16-readability-audit` beside the no-uncited gate. `major` (paraphrase), not a
   ship-block. Deterministic $0 (dossier 16 §5).
4. **Effort continuum + token ceiling** — wire the stub `--reasoning-effort`
   (`cli/research.py:118`) + add `--max-tokens` through to `skills/router.py`; the 4-level
   `minimal/low/medium/high` → route + fan-out + tier map (dossier 16 §6.1); degrade order: tool
   redundancy → fan-out width → model tier → tokens-last (dossier 16 §6.2).
5. **Confidence-band hedging** — `grounding/verifier.py` emits `confidence_band` per cited sentence
   (from `verify_score` × fetcher-confidence × consensus count); `bad-research-14-patcher` adds the
   band-appropriate hedge to medium/low claims. Number stays off-band (dossier 16 §7).

### 6.1 Funnel/pipeline/skill rewire (KR-6)

- `cli/research.py::_build_providers` → returns keyless providers (`WebSearchToolProvider`,
  `DdgsProvider`, optional `SearxngProvider`, + intent-routed verticals), not `get_provider("builtin")`.
- `cli/research.py::_build_tiered_fetcher` → the keyless 4-rung `TieredFetcher` (§4.4).
- `cli/research.py::_build_embedder`/`_build_reranker` → reranker defaults to `ClaudeCodeReranker`;
  embedder is `None` unless `[local]`/`neural_recall`.
- `pipeline.run_query` `_gather`/`_retrieve`/`_synthesize` — unchanged in shape; pick up the keyless
  wiring through the rebuilt `cli/research.py` builders.
- The skill `width-sweep`/`depth`/`gap-fetch` step skills call the same `bad funnel-gather`/
  `bad retrieve` CLI — no skill-prompt change needed for the provider swap (the CLI is the seam).

---

## 7. The LEAN keyless dependency set (`pyproject.toml`, KR-1/KR-7)

```toml
# CORE — lean, zero-key, pipx-installable. Confirmed against dossiers 12-16.
dependencies = [
    "anthropic>=0.40",          # the LLM seam (headless bridge / calibration; host supplies inference in skill path)
    "httpx>=0.27",              # keyless fetch + all vertical APIs (arxiv/openalex/crossref/...)
    "crawl4ai>=0.4",            # local JS render + PruningContentFilter/BM25ContentFilter (dossier 12 §3)
    "ddgs>=9.14",               # keyless multi-engine search aggregator (dossier 13 §8.1)
    "pymupdf>=1.24",            # PDF → text (dossier 12 §5); + pymupdf4llm at runtime
    "pymupdf4llm>=0.0.17",      # markdown-aware PDF (dossier 12 §5)
    "trafilatura>=1.8",         # boilerplate-strip fallback (dossier 12 §3.5)
    "beautifulsoup4>=4.12",     # the Firecrawl strip/metadata ports (dossier 12 §2, §8)
    "lxml>=5.0",                # bs4 parser backend
    "rank-bm25>=0.2",           # highlights + BM25ContentFilter (dossier 12 §3.4, §7)
    "snowballstemmer>=2.2",     # BM25 stemming (dossier 12 §7)
    "dateparser>=1.2",          # published-date normalization (dossier 12 §8.1)
    "feedparser>=6.0",          # RSS/Atom + arXiv Atom (dossier 12 §D, dossier 13 §8.1)
    "typer>=0.9.0",             # CLI
    "rich>=13.0",               # CLI output
    "pydantic>=2.0",            # data models
    "pyyaml>=6.0", "jinja2>=3.1", "platformdirs>=4.0",   # vault/config (inherited, keyless)
    "tree-sitter>=0.23", "tree-sitter-language-pack>=0.7",  # code-aware chunking (keyless)
    "rapidfuzz>=3.0",           # span-extract fuzzy fallback (grounding, keyless)
    "langdetect>=1.0.9",        # language gate (quality, keyless)
    # SQLite-FTS5 is compiled into Python's stdlib sqlite3 — no dependency line.
]

[project.optional-dependencies]
# Heavy local browser (Chromium via crawl4ai is in core for render; this adds Playwright extras
# only if a user wants the python-playwright path). agent-browser + lightpanda + yt-dlp + git are
# EXTERNAL CLI tools the skill drives — installed out-of-band, NOT pip deps (see §7.1).
browse = ["playwright>=1.40"]            # optional; crawl4ai pulls its own Chromium otherwise
# Offline neural stack — opt-in, lazy-downloaded. The ONLY place torch/lancedb live.
local = [
    "torch>=2.0",
    "sentence-transformers>=3.0",        # bge-small bi-encoder + ms-marco/bge-reranker + nli-deberta
    "lancedb>=0.13",                     # vector store (only when neural_recall is on)
    "pyarrow>=15.0",                     # lancedb dep
]
mcp = ["mcp>=1.6"]                       # the MCP face (keyless)
all = ["bad-research[browse,local,mcp]"]
dev = ["pytest>=7.4","pytest-cov>=4.1","pytest-asyncio>=0.23","ruff>=0.3","mypy>=1.8","respx>=0.21","mcp>=1.6"]
```

### 7.1 External keyless CLI tools the skill drives (NOT pip deps)

These are installed out-of-band (documented in `bad install` / `bad doctor`), each keyless:
- **`agent-browser`** — the native Rust CLI (local Chrome-for-Testing / lightpanda over CDP). `bad
  install` runs `agent-browser install` (pulls Chrome-for-Testing, no account). Browse rung 2.5/3.
- **`lightpanda`** — the fast keyless JS engine (GitHub-release `curl` / `brew`); rung-2.5 default.
  Set `LIGHTPANDA_DISABLE_TELEMETRY=true` (dossier 14 §12.1).
- **`yt-dlp`** — caption-track puller for the YouTube/video source tier (`--skip-download`,
  keyless; dossier 12 §A).
- **`git`** — shallow clone for the GitHub source-code tier (`git clone --depth=1`; dossier 12 §B).
- **SearXNG** (optional) — `docker run searxng/searxng` with `search.formats:[json]` for the T1
  multi-engine breadth source (dossier 13 §1.4). Not required; `ddgs` covers the no-self-host path.

> **NO `cohere`, `tavily-python`, `exa-py`, `firecrawl-py`, `browser-use`, `agentql`, `browserbase`,
> `stagehand` ANYWHERE** — not in core, not in any extra. Verified against all 5 dossiers.

---

## 8. Frozen constants that carry over (cite these verbatim in KR plans)

| Constant | Value | Source (dossier) | Lives in |
|---|---|---|---|
| RRF k | `60` | 13 §3.2 / 15 §3.1 | `retrieval/constants.py::RRF_K`, `web/search` |
| hybrid α (vector:bm25) | `0.7` | 15 §3.2 | `retrieval/constants.py::ALPHA` |
| three-tier fusion weights (≤3/≤10/>10) | `0.75 / 0.60 / 0.40` | 15 §3.3 | `RETRIEVAL_WEIGHT` |
| deep-rank penalty | `0.005·(rank−10)` | 15 §3.3 | `DEEP_RANK_PENALTY` |
| source-type weights (code/docs/paper/dataset) | `1.2 / 1.0 / 0.9 / 0.85` | 15 §3.4 | `SOURCE_TYPE_WEIGHT` |
| relevance gate | `0.70` | 13 §3.4 / 15 §7.1 | `RELEVANCE_GATE` |
| re-retrieve pass-fraction / max rounds | `<30%` / `2` (light) `3` (full) | 13 §3.4 / 15 §7.2 | `RERETRIEVE_*` |
| semantic cache cosine / lexical threshold | `0.92` / `0.85` | 15 §6 | `SEMANTIC_CACHE_THRESHOLD(_LEXICAL)` |
| neural-recall auto-enable | `25_000` chunks | 15 §4.3 | `NEURAL_RECALL_VAULT_THRESHOLD` |
| LLM-rerank truncate / batch | `800` chars / `30` | 15 §5.3 / §7.4 | `LLM_RERANK_*` |
| PruningContentFilter threshold | `0.48` (dynamic) | 12 §3.3 | `web/content` |
| `needs_js` visible-text floor | `200` chars | 12 §1.1 | `web/content` |
| content cache TTL | `14 days` | 12 §9 | `web/content` |
| highlights window / step / top-k | `120` / `60` / `3` | 12 §7 | `web/content` |
| read-top-K ceiling | `80` | funnel (kept) | `funnel/config.READ_CEILING` |
| FTS5 BM25 col weights (title/body/tags/aliases) | `10 / 1 / 5 / 3` | 15 §2.1 (kept) | `retrieval/constants.py` |
| dedup Jaccard / shingle-n / MinHash / LSH / brute | `0.60 / 3 / 128 / 16 / 200` | kept | `core/similarity.py` |
| agentic-fast max_steps / max_calls / timeout | `10 / 15 / 300s` | 16 §1 (kept) | `routing_constants.py` |
| grader-loop max revisions | `3` | 16 §4.1 | `MAX_GRADER_REVISIONS` |
| recitation max n-gram / overlap | `12` / `0.50` | 16 §5.1 | `quality/recitation.py` |
| fetcher tool-call cap / timeout / source-kill | `10/20 / 300s / 100` | 16 §3.2 | `routing_constants.py` |
| NLI verifier model | `nli-deberta-v3-base` (local, $0) | 16 §2 (kept) | `[grounding]` extra |
| local bi-encoder / reranker (opt-in) | `bge-small-en-v1.5` / `ms-marco-MiniLM-L-6-v2` | 15 §4.1, §5.2 | `[local]` extra |
| install default target | `~/.claude/` (user-global) | INTERFACES.md (kept) | KR-7 |

---

## 9. Decisions resolved here (no further input needed) + the genuinely ambiguous ones

**Resolved by the dossiers + the two FINAL decisions (KR plans take these as given):**
- Default reranker = **host-model LLM-rerank** (dossier 15 §5.4); local cross-encoder is `[local]`.
- Default retrieval recall = **FTS5/BM25 only** (no LanceDB in core); dense lane auto-on >25k chunks.
- Default browse rung-2.5 engine = **lightpanda**, falling back to chrome on empty/error snapshot.
- Semantic cache default = **token-set lexical at 0.85** (no embedder); cosine 0.92 only under `[local]`.
- `SearxngProvider` ships keyless (self-host), but **`ddgs` is the no-self-host default** breadth
  source — SearXNG is opt-in via `searxng_endpoint`.
- Verticals fire **only on intent-routed seed queries** (≤2), never on every expansion (politeness).

**Genuinely ambiguous — flag for the user to resolve before KR plan-writing:**
1. **Does the skill ever need a programmatic `anthropic` SDK call, or is it 100% host-model in the
   skill path?** The dossiers say the skill path is pure host model (no key). But the headless
   `pipeline.run_query` + `calibrate` harness currently call `get_llm_provider("anthropic")` which
   needs `ANTHROPIC_API_KEY`. **Question:** keep `anthropic` as a core dep solely for the
   *calibration/headless* bridge (not the skill), or move it to a `[calibrate]` extra so the pure-
   skill install is truly keyless-dep-free? (I assumed core; it's the only `anthropic`-needing path.)
2. **agent-browser distribution.** It's a Rust binary (needs `cargo build` or a release download),
   not pip-installable. **Question:** does `bad install` bootstrap it (download + `agent-browser
   install`), or is it a documented prerequisite the user installs first? Affects KR-7 packaging
   and the `bad doctor` checks.
3. **SearXNG in the default `bad doctor` health check.** Since SearXNG is self-host-optional and
   `ddgs` covers breadth, should `bad doctor` warn when SearXNG is absent (treat as degraded) or
   stay silent (treat as a pure opt-in)? (I leaned silent/opt-in in §3.5.)
4. **The `[local]` auto-enable at 25k chunks** pulls `torch` (~2GB) on first cross of the threshold.
   **Question:** auto-pip-install `[local]` on threshold cross, or hard-require the user to have
   `pip install bad-research[local]` already and just *use* it when present (erroring helpfully if
   not)? (Dossier 15 implies the latter; confirm.)
