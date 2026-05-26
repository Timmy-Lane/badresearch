# Bad Research — Interfaces Contract (canonical, frozen for all plans)

> Every implementation plan (01–09) MUST use these names, signatures, paths, and constants **verbatim**.
> This is the single source of truth for cross-plan type consistency. If a plan needs a new shared
> type, it adds it here first. Source of design: `ultimate-research/SPEC.md` + dossiers `01–11`.

## Package & layout

- PyPI: `bad-research` · import root: `bad_research` · CLI: `bad` (alias `badr`) · skill: `/bad-research`.
- Repo/source root (fork of hyperresearch): `ultimate-research/bad-research/`
  - `src/bad_research/` — the package (fork of `hyperresearch/src/hyperresearch/`, enhanced)
  - `tests/` — pytest suites (mirror hyperresearch's layout)
  - `pyproject.toml` — entry points `bad = "bad_research.cli:app"`, `badr = "bad_research.cli:app"`
- Reference clone to read while planning: `/Users/seventyleven/Desktop/researchfms/hyperresearch/` (read-only).
- Install targets (user-global default, invariant #3): `~/.claude/skills/bad-research/`, `~/.claude/agents/`, `~/.claude/settings.json`; vault `~/.bad-research/` → `research/` (markdown) + `.bad-research/` (SQLite + LanceDB).

## Module map (new dirs added under `src/bad_research/`)

```
llm/         # LLMProvider seam (Plan 01)
embed/       # EmbedProvider seam (Plan 01)
config.py    # BadResearchConfig dataclass (Plan 01, extends hyperresearch config)
retrieval/   # hybrid engine, reranker, semantic cache, anchors (Plan 02)
web/providers/  # WebSearchProvider impls + cascade (Plan 03)  [extends existing web/]
browse/      # BrowseProvider/ExtractProvider + Tier 0→3 ladder (Plan 04)
quality/     # garbage filters (Plan 05)
grounding/   # CitationVerifier + gate (Plan 06)
funnel/      # scraper funnel orchestration (Plan 07)
skills/      # +clarify, +query-router; modified stage skills (Plan 08)
core/ search/ mcp/ serve/ cli/ models/  # hyperresearch base (enhanced across plans)
```

## Seam signatures (Python; Protocols + dataclasses)

```python
# llm/base.py  (Plan 01)
ModelTier = Literal["triage", "work", "heavy"]   # → Haiku / Sonnet / Opus via config

@dataclass
class LLMMessage: role: Literal["system","user","assistant","tool"]; content: str | list[dict]

@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict]          # [] if none
    usage: dict                     # {input_tokens, output_tokens, cache_read, cache_write}
    model: str

class LLMProvider(Protocol):
    name: str
    def complete(self, messages: list[LLMMessage], *, tier: ModelTier,
                 tools: list[dict] | None = None, cache: bool = False,
                 max_tokens: int = 4096, temperature: float = 0.1) -> LLMResponse: ...
# Default impl: AnthropicProvider (llm/anthropic.py). Optional: LiteLLMProvider.
# cache=True → stamp cache_control on the stable system+tools prefix (KV-cache discipline).
# AnthropicProvider(api_key: str | None = None, config: BadResearchConfig | None = None)
#   ._resolve_model(tier) -> str   # heavy→work when config.cheap (--cheap demotion)
def get_llm_provider(name: str = "anthropic", **kwargs) -> LLMProvider: ...   # factory (Plan 01)

# embed/base.py  (Plan 01)
class EmbedProvider(Protocol):
    name: str
    dim: int
    def embed(self, texts: list[str], *, input_type: Literal["document","query"]) -> list[list[float]]: ...
# Default: CohereEmbedProvider (embed-english-v3.0, dim 1024). Optional: Voyage, OpenAI.
# CohereEmbedProvider(api_key: str | None = None, model: str = "embed-english-v3.0")  # name="cohere", dim=1024
def get_embed_provider(name: str = "cohere", **kwargs) -> EmbedProvider: ...  # factory (Plan 01)

# web/base.py  (EXISTS in hyperresearch — extend, do not break)
@dataclass
class WebResult:                    # hyperresearch's existing shape — reuse verbatim
    url: str; title: str; content: str; ...   # + looks_like_junk(), looks_like_login_wall()

@dataclass
class SearchQuery:                  # (Plan 03)
    query: str
    intent: Literal["keyword","neural","deep"] = "keyword"
    recency_days: int | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    max_results: int = 10

class WebSearchProvider(Protocol):  # extends hyperresearch's WebProvider (Plan 03)
    name: str
    capabilities: set[str]          # {"keyword","neural","extract","crawl"}
    cost_per_search: float          # USD estimate
    p50_ms: int
    def fetch(self, url: str) -> WebResult: ...
    def search_ex(self, q: SearchQuery) -> list[WebResult]: ...

# browse/base.py  (Plan 04)
class BrowseProvider(Protocol):
    name: str
    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult: ...
class ExtractProvider(Protocol):
    name: str
    def extract(self, source: str | WebResult, schema: dict, instruction: str = "") -> dict: ...
# fetch_tiered(url, *, tier_max: int, instruction=None, schema=None) -> WebResult  (the 0→3 ladder)

# retrieval/base.py  (Plan 02)
@dataclass
class Chunk:
    chunk_id: str            # sha1(url + "#" + heading)
    note_id: str
    text: str
    char_start: int; char_end: int
    score: float
    source_id: str

class Reranker(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]: ...  # (idx, score) desc
# Default: CohereReranker (rerank-v3.5). Offline: BGEReranker (bge-reranker-v2-m3).

class RetrievalEngine:   # concrete (Plan 02)
    def index(self, notes: Iterable[Note]) -> None: ...
    def search(self, query: str, *, mode: Literal["light","full"], top_k: int) -> list[Chunk]: ...
    # internally: hybrid(alpha=0.7) → rerank → three-tier fusion → 0.70 gate → semantic cache

# quality/  (Plan 05)
@dataclass(frozen=True)
class TierInfo:                       # a DOMAIN_TIER entry
    name: str                         # primary|docs|reference|news_tier1|blog|forum|seo_farm
    multiplier: float                 # 1.30 … 0.50 (authority rank multiplier)
    prefetch_priority: int            # 0 = fetch first … 9 = last/drop  (→ sources.tier)

@dataclass
class Candidate:                      # a pre-fetch SERP candidate (Stage-1 input)
    url: str; snippet: str; title: str = ""
    provider: str = ""                # WebSearchProvider name → sources.fetch_provider
    engagement: int | None = None     # HN points / Reddit upvotes if exposed
    published_days_ago: int | None = None

@dataclass
class RelevanceResult:                # Stage-4 output
    kept: list[WebResult]; pass_fraction: float; should_reretrieve: bool

# Public functions (quality/__init__.py):
seo_farm_score(url, snippet, query="") -> int          # block if >= 2
domain_tier(url) -> TierInfo
DOMAIN_TIER: dict[str, TierInfo]
canonical_url(url) -> str ; is_blocklisted(url) -> bool
prefetch_filter(candidates: list[Candidate], *, query="", max_age_days=None) -> list[Candidate]
postfetch_filter(WebResult, *, query_lang=None, original_url=None) -> WebResult | None
looks_like_paywall(WebResult) -> bool
dedup(results: list[WebResult]) -> list[WebResult]                 # Jaccard 0.60, tier tiebreak
score_and_filter(query, results, reranker: Reranker, *, rounds_remaining=2) -> RelevanceResult
authority_rank(results: list[WebResult]) -> list[WebResult]        # reranker_score × domain_tier
INJECTION_PREAMBLE: str ; wrap_untrusted(content, *, source_url=None) -> str
source_id(url) -> str  # 16-char sha256(canonical_url)
build_source_row(WebResult, *, fetch_provider, fetch_tier) -> dict
upsert_source(conn, WebResult, *, fetch_provider, fetch_tier) -> None

# funnel/orchestrator.py  (Plan 07 — the scraper funnel; SPEC §6)
@dataclass
class FunnelDeps:        # injected cross-plan seams (DI so the funnel is testable in isolation)
    providers: list           # list[WebSearchProvider]  (Plan 03 cascade survivors)
    fetcher: object           # has: async fetch_tiered(url, *, tier_max, instruction, schema)  (Plan 04)
    postfetch_filter: object  # callable(WebResult) -> str | None  (Plan 05)
    vault: object             # has: store_note(*, title, body, url, provider) -> note_id
    retrieval: object         # RetrievalEngine (Plan 02): .index(notes), .search(query, *, mode, top_k)

async def gather(query: str, *, mode: Literal["light","full"],
                 deps: FunnelDeps, queries: list[SearchQuery] | None = None) -> list[Chunk]: ...
# Runs the 6-stage funnel: A FAN-OUT (M×P parallel) → B DEDUP (URL-canonical+content-hash) →
# C RANK un-read (RRF k=60 + 6-dim utility, the cheap→expensive gate) → D READ top-K (≤80 ceiling,
# batched, chained-crawl depth 2/5-links) → E FILTER (postfetch junk + >60% redundancy) + STORE to
# vault → F RERANK via RetrievalEngine. Returns reranked top Chunk[] + [[note-id]] pointers —
# NEVER raw page bodies. Stages A–E are $0 model cost. Funnel constants → funnel/config.FunnelConfig.

# calibrate/cost.py  (Plan 09 — the 5-component cost meter; SPEC §10/§14, dossier 09 §A4.2)
# OFFLINE/reporting only — NOT a per-run gate. Plan 08's pipeline POPULATES it via .record(...)
# at each stage boundary; Plan 09's harness reads .total_usd() for the efficiency axis.
class CostMeter:                 # concrete (Plan 09)
    def record(self, *, stage: str, tier: ModelTier, input_tokens: int = 0, output_tokens: int = 0,
               reasoning_tokens: int = 0, citation_tokens: int = 0, search_queries: int = 0) -> None: ...
    def record_response(self, *, stage: str, tier: ModelTier, usage: dict, search_queries: int = 0) -> None: ...
    def total_usd(self) -> float: ...
    def to_dict(self) -> dict: ...
    def write(self, path: Path) -> None: ...   # → cost-report.json
# 5 components: ("input","output","reasoning","citation","search_queries"). reasoning+citation bill
# at the tier's OUTPUT rate; search_queries flat at $0.005/call.

# calibrate/judge.py + harness.py  (Plan 09 — OFFLINE 5-axis judge + report; never a per-run gate)
JUDGE_AXES = ("factual","citation","completeness","source_quality","efficiency")  # single strong call, no ensemble
@dataclass
class AxisScores: factual: float; citation: float; completeness: float; source_quality: float; efficiency: float
@dataclass
class JudgeVerdict: scores: AxisScores; overall: float; passed: bool; rationale: str
class Judge(Protocol):
    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict: ...
# Impls: StubJudge (deterministic, tests) · LLMJudge(provider: LLMProvider, tier="heavy") (single call).
@dataclass
class BadRunOutput: report: str; corpus: list[dict]; cost: CostMeter   # what a BadRunner returns
BadRunner = Callable[[str], BadRunOutput]
def run_calibration(query: str, *, runner: BadRunner, baselines: list[Baseline], judge: Judge) -> CalibrationReport: ...
# Baseline Protocol: .name, .available()->bool, .run(query)->BaselineResult; key-gated (skip without key).

# providers.py  (Plan 09 — the network-free provider registry; powers `bad doctor`)
@dataclass
class ProviderStatus:            # one per registered provider
    name: str; capability: str; extra: str
    requires_key: bool; key_present: bool; import_present: bool; active: bool
def provider_status() -> list[ProviderStatus]: ...   # no network, no config read
def active_providers() -> list[ProviderStatus]: ...  # key_present AND import_present
```

## Vault schema additions

- **LanceDB** table `chunks`: `{chunk_id: str (pk), vector: fixed_size_list<float, dim>, note_id, char_start, char_end, model, dim}`. Dir: `<vault>/.bad-research/lance/`. (Plan 02; cite `teardowns/LANCEDB.md`.)
- **SQLite** (existing `<vault>/.bad-research/*.db`, hyperresearch schema-v8) + new tables:
  - `claim_anchors(anchor_id TEXT PK /*=quote_sha 8-char*/, note_id, char_start, char_end, claim, quoted_support, verified INT, verify_score REAL)` (Plan 06).
  - `sources(source_id TEXT PK /*16-char sha256*/, url, domain, domain_tier REAL, fetch_provider, tier INT, fetched_at, document_date, event_date)` (Plan 05/07).
- Markdown is truth; both stores are rebuildable by `sync` (16-byte frontmatter probe + mtime + SHA-256). The dead hyperresearch `embeddings` table is removed in favor of LanceDB.

## Config (`config.py`, Plan 01 — extends hyperresearch's dataclass)

```python
@dataclass
class BadResearchConfig:
    vault_root: Path = Path.home() / ".bad-research"
    model_tiers: dict = field(default_factory=lambda: {
        "triage": "claude-haiku-4-5", "work": "claude-sonnet-4-6", "heavy": "claude-opus-4-7"})
    embed_model: str = "embed-english-v3.0"  # Cohere
    rerank_model: str = "rerank-v3.5"      # Cohere; "bge-reranker-v2-m3" offline
    budget_usd: float | None = None        # None = uncapped
    cheap: bool = False                    # demote heavy→work
    # provider keys read from env / ~/.config/bad-research/config.toml
    @classmethod
    def load(cls, config_path: Path | None = None) -> "BadResearchConfig": ...
        # precedence: env > TOML([bad-research] table) > dataclass default
def default_config_path() -> Path: ...     # $XDG_CONFIG_HOME or ~/.config → bad-research/config.toml
# env keys: BAD_RESEARCH_{VAULT_ROOT,EMBED_MODEL,RERANK_MODEL,BUDGET_USD,CHEAP}
```

## Frozen constants (cite these exactly in plans)

| Constant | Value | Source |
|---|---|---|
| hybrid alpha (vector:bm25) | `0.7` | NIA §5 |
| three-tier fusion weights `w` (rank ≤3 / ≤10 / >10) | `0.75 / 0.60 / 0.40` | NIA §5 |
| relevance drop threshold | `0.70` | Perplexity |
| re-retrieve trigger / max rounds | `<30%` pass / `2` | Perplexity |
| semantic cache cosine threshold | `0.92` (+ negation guard) | NIA §5.5 |
| RRF k | `60` | Exa / LanceDB |
| dedup Jaccard / shingle n / MinHash perm / LSH bands / brute-switch | `0.60 / 3 / 128 / 16 / 200` | hyperresearch similarity.py |
| read-top-K ceiling | `80` (degrades past it) | hyperresearch |
| FTS5 BM25 col weights (title/body/tags/aliases) | `10 / 1 / 5 / 3` | hyperresearch search/fts.py |
| BM25 status multipliers (evergreen/stale/deprecated) | `1.5 / 0.7 / 0.3` | hyperresearch |
| DOMAIN_TIER (primary…seo) | `1.30 … 0.50` | dossier 07 |
| seo_farm_score block threshold | `≥2` | dossier 07 |
| patch hunk net-expansion cap | `500` chars | hyperresearch CHANGELOG |
| subagent fan-out default / max | `3 / 20`, depth-1 | Claude Research |
| agentic-fast max_steps | `10` | Perplexity |
| LLM defaults | `max_tokens=4096, temperature=0.1` | cookbook |
| NLI verifier model | `nli-deberta-v3-base` (local, $0) | dossier 08 |
| embed dim (Cohere v3) | `1024` | dossier 02 |
| router agentic-max-atomic / light-max-atomic | `2 / 6` | DR-loops §9.2 (Plan 08) |
| clarifier max questions | `3` | DR-loops §1 / ODR §5 (Plan 08) |
| agentic-fast max_calls / timeout_s | `15 / 300` | DR-loops §5 / CLR §CE.3 (Plan 08) |
| install default target | `~/.claude/` (user-global) | SPEC §12 (Plan 08) |

## Models (current IDs, behind the seam)

`claude-opus-4-7` (heavy) · `claude-sonnet-4-6` (work) · `claude-haiku-4-5` (triage). Embeddings: Cohere `embed-english-v3.0`. Rerank: Cohere `rerank-v3.5` / local `bge-reranker-v2-m3`. NLI: `nli-deberta-v3-base`.

## Cross-plan integration reconciliation (post-review, 2026-05-26)

Findings from the whole-series self-review across plans 01–09 (18,945 lines). The shared seams above are consistent across all plans; these notes resolve the integration edges.

1. **Sync seams, async funnel.** `WebSearchProvider.search_ex` (Plan 03) and `fetch_tiered` (Plan 04) are **synchronous** (blocking httpx / `asyncio.run`-wrapped browse). The funnel (Plan 07) runs them concurrently and therefore wraps each call in `funnel/_async.py::acall(fn, *args)` = `await fn(...)` if `iscoroutinefunction` else `await asyncio.to_thread(fn, ...)`. Do **not** make the providers async. See the reconciliation note at the top of Plan 07.
2. **Two distinct `search()` methods, no conflict.** `WebProvider.search(query, max_results=5) -> list[WebResult]` (hyperresearch legacy, lexical fetch) and `RetrievalEngine.search(query, *, mode, top_k) -> list[Chunk]` (Plan 02) are different methods on different classes. Both are correct.
3. **INTERFACES self-definition rule.** Concurrent edits during planning clobbered some additive type appends here (e.g. `TierInfo`/`RelevanceResult` from Plan 05, the Grounding-API block from Plan 06, the calibration types from Plan 09). Non-fatal: **each plan fully self-defines its own types in its own tasks**, and cross-plan use is by Python module import (`from bad_research.<module> import X`), not by reading this file. Canonical homes: `TierInfo`/`Candidate`/`RelevanceResult` → Plan 05; `FunnelDeps`/`gather` → Plan 07; `CitationVerifier`/`AnchorStore`/anchors → Plan 06; `CostMeter`/judge types/`provider_status` → Plan 09; LLM/Embed/config → Plan 01.
4. **Build-order gotchas (carry into execution):** Plan 01 must create the `ultimate-research/bad-research/` fork dir first (Plans 02–09 assume it) and carry `core/similarity.py` into the fork (Plans 05/07 import it). Plan 08 owns the real installer + the `bad_research.pipeline.run_query(query, config, cost_meter)` entrypoint that Plan 09's `bad calibrate` bridges to. Verify against installed SDK versions at build time: Anthropic `cache_control` + usage field names (use the `claude-api` skill), Cohere v2 `embed`/`rerank` shapes (`cohere>=5`), `lancedb>=0.13` index API, tree-sitter grammar node-type names.

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
