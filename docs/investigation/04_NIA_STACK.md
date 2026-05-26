# 04 — NIA Stack: Extracting NIA's Retrieval/RAG Primitives to Upgrade hyperresearch's FTS-Only Vault

> **Purpose.** hyperresearch (`teardowns/HYPERRESEARCH.md`) is a deterministic markdown+SQLite vault with **FTS5/BM25 keyword-only** retrieval — its `embeddings` table ships empty, its similarity is shingle-Jaccard, and its research loop is a **fixed 16-stage** Claude-Code-orchestrated state machine. NIA (`teardowns/NIA.md`, RE'd with live enterprise access through 2026-05-26) is the most complete self-hostable research+RAG backend we tore down. This dossier extracts NIA's retrieval primitives at reimplementable depth — exact models, dims, constants, algebra — and maps each onto a concrete upgrade for hyperresearch's vault, retrieval, and research loop.
>
> **Labels.** **KNOWN** = from NIA source/OpenAPI/live wire (cite §NIA). **INFERRED** = NIA behavioral fingerprint. **IDEA** = our integration design for the ultimate-research skill (not in either product yet).
>
> **Cross-refs.** All `§N` cites are into `teardowns/NIA.md` unless prefixed `HR§` (into `teardowns/HYPERRESEARCH.md`). hyperresearch internals cited `file:line` per HR§2/HR§3.

---

## 0. The gap, stated precisely

| Dimension | hyperresearch today (HR§2, HR§3) | NIA (this doc) | Upgrade lever |
|---|---|---|---|
| **Retrieval** | FTS5 BM25 only, weights `title=10/body=1/tags=5/aliases=3`, status multipliers `1.5/0.7/0.3` (`fts.py:84-141`) | Hybrid vector+BM25 fused at `alpha=0.7`, then Cohere `rerank-v3.5`, three-tier fusion (§5) | Add a dense lane + reranker; keep BM25 lane and weights as the lexical half |
| **Embeddings** | `embeddings` table = **vestigial**, no generation code (`db.py`, HR§2 `:437`) | Two embedders: Qwen3-Embedding-4B (dim 2560, retrieval) + Cohere v3 (dim 1024, cache) (§4) | Wire the dead table; pick self-host vs API |
| **Semantic similarity** | shingle-Jaccard 3-gram, MinHash-128/LSH-16 above 200 notes, threshold 0.6 (`similarity.py`, HR§3) | dense cosine in TurboPuffer ANN; 0.92 LSH cache (§5.5) | Jaccard → cosine for dedup AND a real semantic cache |
| **Query cache** | none (every `search` recomputes) | L2 semantic cache, 0.92 cosine, ~20-25× speedup, cross-tenant (§5.5, §15.3) | Add a single-user response cache keyed on query embedding |
| **Chunking** | whole-note (markdown is the unit; no sub-note chunks) | tree-sitter AST-bounded, **AST headers prepended before embedding** (§3.1) | Chunk long source-notes; prepend a structural header before embedding |
| **Research loop** | fixed 16 stages, scripted in skill prompts (HR§1) | agentic JSON-action ReAct (Oracle, §7) + scripted Exa proxy (deep, §6.5) | Offer an Oracle-style agentic mode *alongside* the 16-stage pipeline |
| **Enrichment** | Dream-cycle analogue = stages 3/7 (contradiction graph + source tensions) over `claims-*.json` (HR§1, HR§22) | Dream cycle: auto-wiki entity enrichment + Phase-4 contradiction detection (§9) | hyperresearch already has the contradiction half; NIA adds the auto-entity-page half |

The thesis of this dossier: **NIA's retrieval stack is a drop-in second lane for hyperresearch's vault.** hyperresearch already has the disk-truth/SQLite-cache discipline, the BM25 lane, the graph, and a (prompt-level) contradiction stage. What it lacks is the *neural* half — dense retrieval, rerank, semantic cache. NIA gives us all three with verified constants.

---

## 1. Two-embedder design — why NIA splits retrieval and cache embedders

### 1.1 Retrieval embedder — `zembed-1` = Qwen3-Embedding-4B (KNOWN dim/limits, INFERRED identity — §4.1)

| Property | Value | Source |
|---|---|---|
| Wire identity | server returns `model:"zembed-1"`, `dimension:2560` | §4.1, F20 live |
| Model identity | **Qwen3-Embedding-4B** | INFERRED §4.1 — dim 2560 is a near-unique fingerprint (Nomic-v2=768, bge-m3=1024, voyage-code-3=1024, OpenAI 3-large=3072, Cohere v3=1024; **only Qwen3-4B = 2560**) |
| Output dim | **2560** | KNOWN §4.1 |
| Char truncation | **exactly 16384 = 2^14 chars per text** (bisection-verified) | KNOWN §3.4 |
| Batch cap | **`texts.max_length = 100`** items/call (bs=101 → HTTP 422) | KNOWN §3.4 |
| Context window | ~16K tokens (half of Qwen3's native 32K — a deliberate memory-bound cap for batch-100 fp16 inference on A100-40GB/H100) | INFERRED §4.1 |
| Normalization | **L2-normalized server-side** (‖v‖ = 1.000031 ± fp16 noise) → search uses dot = cosine | KNOWN §4.1 |
| Storage | **fp16** (values like `-0.04693603515625` are exactly fp16-representable; widened to fp32 only for JSON) | KNOWN §4.1 |
| Asymmetric (instruction-prefixed) | `input_type: "document"` at index time vs `"query"`/`"search_query"` at retrieval — Qwen3 models take a task instruction; this asymmetry is **real and must be replicated** | KNOWN §15.1 `[CORRECTION 2026-05-26]` |
| Deployment | self-hosted single GPU node behind Cloud Run, internal `/v2/daemon/embed` | KNOWN §4.1 |
| Multilingual | EN↔FR technical paraphrase cosine **0.93–0.95** (OpenAI 3-large only 0.88–0.92) | KNOWN §4.1 (Probe E2) |

**Amortization curve (§3.4, F21, n=27):** `T(bs) ≈ 1.1 + 0.034·bs` seconds for bs≤100, tokens≤500. Latency scales with **batch size, not total tokens** — each batch is one GPU forward pass. Per-text cost: 1.1s @ bs=1 → 0.046s @ bs=100 (~24× amortization). For C chunks: `embedding_wall ≈ ceil(C/100)·4.5s`.

### 1.2 Cache embedder — Cohere `embed-multilingual-v3.0` (INFERRED-strong — §4.2)

| Property | Value | Source |
|---|---|---|
| Model | Cohere `embed-multilingual-v3.0` | INFERRED §4.2 |
| Dim | **1024** | INFERRED §4.2 |
| Purpose | embed the **query string** for the L2 semantic cache lane (NOT the retrieval embedding) | KNOWN §5.5 |
| EN↔FR cosine | 0.93–0.95 on technical paraphrases (French translation hit cache at 0.9447 — would have missed on OpenAI 3-large) | KNOWN §4.2 (Probe A5) |

### 1.3 Why split? (the load-bearing design decision)

1. **Different jobs, different cost profiles.** The retrieval embedder runs **once per chunk at index time** (thousands of calls, batched, GPU-bound) — you want a big high-quality model you control (Qwen3-4B, self-hosted, fp16). The cache embedder runs **once per query at request time** on the critical latency path — you want a cheap fast API call (Cohere v3, dim 1024) where you pay per-query, not per-GPU-hour.
2. **Vendor convergence on the cache side.** NIA's reranker is also Cohere (`rerank-v3.5`, §5.4), so using Cohere's embedder for the cache lane means **one Cohere account** covers both query-embedding and reranking. The retrieval embedder is NIA's own self-hosted asset.
3. **The cache only needs query↔query similarity, not query↔document.** A 1024-dim multilingual embedder is plenty to bucket paraphrases; you don't pay 2560-dim cost on the hot path.
4. **Known failure mode of the split (§4.3):** Cohere v3 is **negation-blind** — `"how does X wrap source chains"` and `"how does X NOT wrap source chains in no_std"` hit cosine 0.9305 (above 0.92) and return the **same cached (affirmative) answer**. NIA never fixed this. **Our replica MUST add a negation detector** (regex `not / n't / without / except / no_std / unlike`) that forces a cache miss (§12.3 NIA pseudocode `has_negation_marker`).

> **→ hyperresearch upgrade.** hyperresearch's `embeddings` table (`note_id PK, model, dimensions, vector BLOB, created_at`, HR§2 `:437`) is already shaped for exactly this. Wire **one** embedder for note/chunk retrieval. The cache lane is optional for a *single-user* tool (no cross-tenant amortization to win), but the negation-aware semantic cache still buys ~20× on repeat/paraphrase queries within one research session. Self-host vs API decision in §7.

---

## 2. AST-header-in-chunk indexing — the novel chunker (§3.1, §3.5)

This is NIA's single biggest engineering insight and the most copyable. **Before each code chunk is embedded, NIA walks the tree-sitter AST and prepends a plain-text header to the chunk text itself**, then embeds the augmented text. The embedder sees the call graph and control-flow signature as natural-language tokens.

### 2.1 Exact format (verbatim, §3.1 from live `/v2/search/universal`)

```
{owner}/{repo}/{file_path}                          # always — line 1
[Calls: {comma_separated_function_names_from_AST}]  # only if call_expressions exist
[Control flow: N branches, M loops, complexity C]   # always for code
                                                     # blank line
{raw source code, original whitespace + tabs preserved}
```

Verbatim examples:
```
sindresorhus/yocto-queue/index.js
Calls: clear, dequeue
Control flow: 8 branches, 4 loops, complexity 13

/* How it works: `this.#head` is an instance of `Node` ... */
```
```
dtolnay/anyhow/src/macros.rs
Control flow: complexity 1

macro_rules! anyhow { ($msg:literal $(,)?) => { ...
```

**Why it works (§3.1):** a query *"find functions calling `dequeue`"* matches the literal substring `Calls: clear, dequeue` inside the chunk's embedded representation; *"complex control flow with many branches"* matches `Control flow: 8 branches…`. The embedder doesn't need to be code-aware — the AST does the codification, and the embedder treats it as text. This is what makes code retrieval work cross-language **without per-language reranker fine-tuning**.

**Edge cases (§3.1):** `Calls:` absent when tree-sitter finds no `call_expression` (e.g. Rust `macro_rules!`). Markdown chunks get a **minimal header** (`{owner}/{repo}/{file}.md\n\n`, no Calls/Control-flow). PDFs/docs get "source identifier + blank line + content."

### 2.2 Chunk strategy + size budget (KNOWN — §3.5)

| File type | `chunk_strategy` | Boundary rule | Observed size |
|---|---|---|---|
| `.js/.ts/.py/.rs/.go/.java/...` | **`tree_sitter`** | AST node boundary (class/function/method) | 1.5–3 KB (380–860 tokens) |
| `.md/.mdx` | `lines` | line-range / heading-aware | 1.5–3 KB |
| `.pdf` | (inferred) `page`/`section` | page or extracted-section | unknown |

- **Zero overlap between code chunks** (clean AST cuts — disjoint line ranges).
- **Files <≈2.5–3 KB become a single whole-file chunk** regardless of structure (yocto-queue: 5 files → 5 chunks, no splits).
- Larger files split at top-level AST nodes; **oversized single items split mid-block** at the next nested node (anyhow `error.rs` chunk-2 started inside a doc-comment+impl block — §3.5).
- Empirical distribution (anyhow, 8 chunks): min 632c, max 2886c, median ≈1521c, avg ≈1791c — **~5% of the 16384-char embedder cap**. The 95% headroom is intentional: smaller chunks → finer-grained retrieval, higher recall density.
- Chunk ID = `<filename_sha256>-<chunk_idx>` (1-indexed). Metadata stored: `filename_sha256, chunk_strategy, filename, language, start_line, start_col, end_line, end_col`.

### 2.3 Per-source-type chunking (KNOWN — §3.2, §3.5)

NIA chunks differently per source class: code → tree-sitter AST; markdown/RST → heading-aware "lines"; PDF/CSV/XLSX → per-page/per-section; GitHub Issues/PRs → a separate `chunking_issues → embedding_issues → storing_issues` sub-pipeline (on by default, `indexIssues=true`/`indexComments=false`, §15.1). Docs are crawled by a **headless-browser crawler** (`wait_for` ms + `include_screenshot` prove JS rendering; `check_llms_txt`/`llms_txt_strategy` honor `/llms.txt`; `focus_instructions` is an LLM-steered selective-index knob; `extract_images:true` feeds GCS-stored multimodal figures keyed by page number — §15.1).

> **→ hyperresearch upgrade.** hyperresearch's note is the markdown body of one fetched source (HR§2). Today retrieval is whole-note BM25. Two upgrades:
> 1. **Markdown structural header before embedding.** For a long source-note, prepend a header analogous to NIA's: `{source_domain}/{title}\n[Sections: H2-a, H2-b, …]\n[tier: {ground_truth|institutional|…}, content_type: {paper|docs|…}, claims: N]\n\n{body}`. hyperresearch already has `tier`/`content_type` CHECK-enum frontmatter (HR§2 `:430`) and a `claims-<note-id>.json` count (HR§22) — those are exactly the structural signals to surface in the header so a dense query like *"primary-source 10-Q figures"* matches the header tokens.
> 2. **Chunk long notes.** hyperresearch's stage-2.6 already delegates >5000-word sources to a `source-analyst` (Sonnet 1M, HR§1 stage 2). For dense retrieval, additionally split such notes at H2 boundaries (the markdown analogue of AST nodes), 1.5–3 KB target, zero overlap, prepend the structural header, embed each. Store sub-chunks in a new `note_chunks` table (FK to `notes`, mirroring `note_content`). Code-notes (`content_type=code`, HR§2 `:430`) get true tree-sitter AST chunking — directly reusable from NIA §12.3 `chunk_code_file`.

---

## 3. Hybrid retrieval scoring algebra (§5) — the reimplementable core

### 3.1 Pipeline (per `/v2/search`, server-side — §5.1)

```
1. Embed query via zembed-1 (input_type="search_query")          ~150–300 ms
2. LSH cache check: hash(query_embedding) → semantic bucket       ~100 ms
   - HIT (cos ≥ 0.92): replay cached response, END
   - MISS: continue
3. Fan-out hybrid retrieval per scoped namespace (parallel):
   - Vector lane: TurboPuffer ANN over zembed-1 vectors
   - BM25 lane:  TurboPuffer FTS v2 native boosting (use_native_boosting=true)
   - Fused at TPuf with alpha=0.7 (70% vector / 30% BM25)
   - Returns top-30 candidates with initial_score ∈ [0,1]
4. Cross-encoder rerank: Cohere rerank-v3.5 over the FULL top-30
5. Three-tier fusion (§3.2)
6. Source-type multiplier (§3.3) — pushed into TPuf rank_by (use_native_boosting)
7. Final sort, take top_k (universal 20, query 10)
8. (query mode only) LLM synthesis → markdown + follow_ups
9. Stream/return + write-back to semantic cache
```

Synthesis (step 8) is **~75% of cold-path wall time** (10–18s); retrieval+rerank are ~1–3s each (§5.5). The cache eliminates synthesis entirely on hit.

### 3.2 Three-tier fusion weight (KNOWN — verified to 1e-15 for top tier, §5.2, re-confirmed §15.3)

```python
def retrieval_weight(pre_rerank_rank: int) -> float:
    if pre_rerank_rank <= 3:   return 0.75   # top tier — trust retrieval MORE
    if pre_rerank_rank <= 10:  return 0.60   # mid tier
    return 0.40                              # tail tier — trust reranker MORE

def fuse(initial_score, reranker_score, pre_rerank_rank):
    w = retrieval_weight(pre_rerank_rank)
    base = w * initial_score + (1 - w) * reranker_score
    if pre_rerank_rank > 10:
        base -= 0.005 * (pre_rerank_rank - 10)   # empirical deep-rank penalty
    return max(0.0, base)
```

Two independent live captures (§5.2 18-point table + §15.3 fresh 10-result table) reproduce `final = w·initial + (1−w)·reranker` to **diff 0.00000 for ranks 1–4**, divergence beginning rank 5–6 (where source-type/language boosts + position decay stack on). Deep-rank residual grows −0.04 @ rank 11 → −0.09 @ rank 26.

**Counter-intuitive design (§5.2):** the system **trusts retrieval more on top-3 (0.75 weight on the initial hybrid score)** and the **reranker more on ranks 4+ (0.60→0.40)**. Reasoning: when stage-1 confidently picks top-3, those are usually right; the reranker's value is *filtering noise from the long tail*, not reordering high-confidence hits. **This pattern is not in any open-source RAG framework** — it is the highest-value copyable constant set in the dossier.

### 3.3 Source-type multipliers (KNOWN — §5.3, schema-confirmed §15.3)

After the §3.2 blend, multiply final score by source-type weight (verbatim schema default `boost_source_types`, §15.3):
```python
SOURCE_TYPE_WEIGHT = {
    "repository":     1.2,   # explicit product bias toward code
    "documentation":  1.0,   # baseline
    "research_paper": 0.9,
    "huggingface_dataset": 0.85,
}   # "override to customize or set {} to disable"
```
Also: `boost_languages` (e.g. `["python","typescript"]`) × `language_boost_factor = 1.5` (max 5.0). These multipliers are **pushed down into TurboPuffer's `rank_by` clause** (FTS v2 native Sum/Product boosting, `use_native_boosting=true`), not applied post-hoc in Python (§15.3) — which is why §5.3 calls them "applied silently before final sort."

### 3.4 Reranker — Cohere `rerank-v3.5` multilingual (INFERRED-high — §5.4)

- Score range observed `[0.272, 0.946]`, right-skewed sigmoid, **hard upper bound ~0.95**.
- **Path-aware:** scores `file_path` alongside body (query `createCommand factory function commander` ranked `bin/commander` path-token-match above the actual `lib/command.js`).
- **Reranks the ENTIRE top-30** stage-1 candidate set, not just top-10 (`--top-k 50` shows all 30+ with `reranked:true`).
- Multilingual confirmed (French query → English `ARCHITECTURE.md` got `reranker_score:0.787`). Latency ~100–300 ms for 30 candidates.

### 3.5 `expand_symbols` — cAST second-pass retrieval (KNOWN — §15.3, NEW)

A second hidden retrieval primitive (default off): when on, the server **extracts function/class names from the first-pass results and issues a second retrieval round for their usage sites**, then merges. Live-confirmed it changes the result set (8 results → 6, different file mix for "Option class constructor"). The "cAST" reference is to the chunked-AST retrieval-augmentation literature — it widens recall to **call-graph neighbors** of the top hits. (Complements §2's AST-headers: §2 puts the call graph *in the chunk*; `expand_symbols` *walks* the call graph at query time.)

### 3.6 The retrieval algebra, distilled (the constants a senior engineer needs)

```
alpha                       = 0.7          # vector weight in TPuf hybrid (1−alpha = BM25)
TOP_K_RETRIEVE              = 30           # candidates per namespace before rerank
TOP_N_FINAL                 = 10 (query) / 20 (universal)
retrieval_weight            = {≤3: 0.75, ≤10: 0.60, >10: 0.40}   # keyed on pre_rerank_rank
deep_rank_penalty           = 0.005·(rank−10) for rank>10
SOURCE_TYPE_WEIGHT          = {repo:1.2, docs:1.0, paper:0.9, hf:0.85}
language_boost_factor       = 1.5 (max 5.0)
reranker                    = Cohere rerank-v3.5 (multilingual), reranks ALL 30
semantic_cache_threshold    = 0.92 (range 0.8–1.0)
max_sources (namespaces)    = 5 (=sources_searched)
sources_for_answer          = 10
final = max(0, w·initial + (1−w)·reranker − penalty) · SOURCE_TYPE_WEIGHT[type]
```

> **→ hyperresearch upgrade.** This is the algebra that turns hyperresearch's FTS-only `search` into a hybrid neural+keyword search. Concretely:
> - Keep hyperresearch's BM25 lane (`fts.py:84-98`, weights 10/1/5/3) as the **lexical half** — feed its `abs(bm25)` score as the BM25 component.
> - Add a **dense lane**: embed the query, cosine over the note/chunk vectors (sqlite-vec or a sidecar). hyperresearch is single-node, so use `sqlite-vec` (vss extension) or in-process numpy over the `embeddings` BLOBs — no TurboPuffer needed at single-user scale.
> - **Fuse at `alpha=0.7`** (normalize both lanes to [0,1] first), take top-30, **rerank** (Cohere rerank-v3.5 API, or self-host BGE-reranker-v2-m3), then apply the **three-tier `retrieval_weight {0.75/0.60/0.40}`** blend.
> - **Reuse hyperresearch's status multipliers as the source-type analogue:** hyperresearch already multiplies by `evergreen×1.5, stale×0.7, deprecated×0.3` (`fts.py:128-141`). NIA's `SOURCE_TYPE_WEIGHT` is the same *idea* keyed on `content_type`/`tier`. **Compose them:** `final · status_multiplier[status] · type_weight[content_type]`. Map NIA's `{repo:1.2, docs:1.0, paper:0.9, hf:0.85}` onto hyperresearch's `tier` enum: `ground_truth:1.2, institutional:1.0, practitioner:0.9, commentary:0.85` — a direct, well-motivated default.
> - `expand_symbols` maps onto hyperresearch's existing **link graph** (HR§3 `links` table, `backlinks`/`outlinks`): after first-pass retrieval, pull the top hits' graph neighbors (notes they link to / that link to them) as a second-pass candidate set, merge before rerank. hyperresearch gets call-graph-style expansion *for free* from its wiki-link graph.

---

## 4. L2 semantic cache (§5.5, §15.3) — the cost/latency primitive

### 4.1 Spec (KNOWN)

| Field | Value | Source |
|---|---|---|
| Key | **the query embedding** (not a string hash) → 64-bit LSH bucket | §5.5 |
| Threshold | **0.92 cosine** (configurable 0.8–1.0; default 0.92) | KNOWN §5.5, §15.3 |
| Key namespace | `search:universal:<16hex>` where 16hex ≈ `xxhash64(canonicalize(query_embedding))` (LSH/SimHash over the vector) | §5.5 verbatim leak |
| Embedder | Cohere `embed-multilingual-v3.0` (the cache lane, §1.2) | §4.2 |
| Speedup | **~20–25×** (warm 0.9–1.3s vs cold 20s; §5.5 mean 14.5×, §15.3 22.19s→0.87s) | KNOWN |
| Tiering | `_cache_type:"semantic"` implies an `"exact"`/string-hash L1 in front of the `"semantic"` L2 | INFERRED §15.3 |
| Cross-tenant | **global, no tenant component in key** — anyone's query seeds the cache for everyone (the unit-economics primitive) | KNOWN §5.5 |
| Write path | `Redis → on miss → TPuf hybrid → rerank → synthesis LLM → Redis write-back to LSH key` | §5.5 |

### 4.2 Exposed wire fields on a HIT (KNOWN — §15.3, NEW)

```jsonc
{
  "content": "…",
  "sources": [...],
  "_cached": true,
  "_cache_type": "semantic",                 // implies an "exact" L1 tier too
  "_cache_similarity": 0.9973,                // cosine: this query vs the cached one
  "_original_query": "How does middleware work in the App Router?"   // text that seeded the slot
}
```

Behavioral table (default 0.92, §15.3): exact repeat → sim 1.0000 HIT 0.87s; "work"→"function" paraphrase → 0.9973 HIT; "explain App Router middleware behavior" → 0.9667 HIT; `bypass_semantic_cache:true` → MISS, full 22.19s synthesis. Token-reorder, full paraphrase (0.9306), French translation (0.9447), suffix-noise (0.9242) all HIT; different topic <0.92 MISS (§5.5).

### 4.3 The two design defects to fix in our replica (KNOWN)

1. **Negation-blindness (§4.3):** `"X"` and `"NOT X in no_std"` collapse to one slot (cosine 0.9305) and return the affirmative answer. **Fix:** regex negation gate forcing a miss (§1.3).
2. **`rerank` cache namespace is 0% hit** (133 misses, 0 hits, §5.5) — either TTL too short, key too narrow, or write path broken. Reranking is the 2nd-most-expensive call. **Opportunity, not a defect to copy.**

> **→ hyperresearch upgrade.** hyperresearch has **no query cache** — every `search` re-runs FTS. For a single-user research session that fires the same/paraphrased query across stages 2/7/9/12, a negation-aware semantic cache is a clean ~20× win on repeats. Single-user means **drop the cross-tenant key design** (no amortization to win, and it's a privacy footgun anyway). Concretely: a tiny SQLite table `query_cache(bucket TEXT PK, query_embedding BLOB, query_text, response_json, log_id, created_at)`; on `search`, embed the query (cache lane embedder), LSH-bucket it, fetch candidates in the bucket, cosine-compare, return on ≥0.92 unless the query carries a negation marker. Threshold and the `_cache_*` echo fields lift verbatim from §4.1/§4.2.

---

## 5. Oracle JSON-action ReAct loop (§7) — an agentic alternative to the fixed 16-stage pipeline

### 5.1 The defining choice — JSON-action ReAct, NOT native tool-use (KNOWN — §7.1)

Oracle's per-iteration output must conform to:
```json
{ "action": "<tool_name>", "args": { /* tool-specific */ }, "reason": "<one-sentence chain-of-thought>" }
```
Proven by the verbatim planner error on malformed input: *"Oracle planner failed before research completion: No valid action JSON returned by the model."* The opencode wrapper parses this JSON itself and dispatches — Anthropic's native `tool_use` blocks are unused. This is why `--no-builtin-tools --tools nia-oracle-tools` works: the wrapper **completely replaces opencode's tool-dispatch layer**. The `reason` field is the agent's CoT and **bleeds onto the wire verbatim** per iteration (the ReAct trace is fully observable).

### 5.2 The sandbox — OpenCode inside Daytona (KNOWN — §7.2)

```
opencode run
  --model claude-opus-4-7        (default; overridable to sonnet-4-5 / sonnet-4-5-1m)
  --tools nia-oracle-tools       (custom registry)
  --no-builtin-tools             (disables bash/fs/glob — agent has NO shell)
  --thinking 10000               (extended-thinking budget)
  --context 1000000              (when opus-1M selected)
  --tool-server-url http://localhost:9090
```
Per-job fresh Daytona micro-sandbox; outbound HTTPS only (Anthropic/Exa/Nia API), no inbound, writable scratch FS **sealed from the agent**, destroyed on complete/cancel/timeout, **TTL 1800s (30 min)**. `workflow_run_id == oracle_job.id` (UUID v4, assigned upfront). The agent confirmed it has no shell (probe P4: *"I do NOT have shell access… I cannot execute hostname, uname, cat, ls…"*).

### 5.3 The 8-tool registry (KNOWN verbatim — §7.3, +2 confirmed §15.4)

| # | Tool | Args (KNOWN) | Returns | Notes |
|---|---|---|---|---|
| 1 | `list_sources` | `{query}` | `{repositories[], documentation[], total_repositories, total_documentation, guidance}` | **always first**; `guidance` is inline LLM steering text |
| 2 | `query` | `{query, repositories?[], docs?[], search_mode?, include_sources?}` | `{content, sources[], meta, repository_result, documentation_result}` | the primary RAG tool; **5 results/project**; runs parallel repo+doc lanes; `meta.resolved_*` resolves UUID↔slug server-side; internally `fast_mode:true` (§15.4) |
| 3 | `code_grep` | `{repository_id(slug), pattern(regex), context_lines?=2}` | file-grouped `{path, line, context, line_number, context_start_line}` | **not capped at 5**; backed by precomputed line-aware code index (zoekt/trigram/ripgrep over tarball) |
| 4 | `read_source_content` | `{source: "owner/repo:path"}` | `{source, content}` | wire-truncated to ~250c (agent gets full) |
| 5 | `get_github_tree` | `{project_id(UUID)}` | `{tree(ascii), stats}` | **schema inconsistency**: takes UUID while `code_grep` takes slug |
| 6 | `run_web_search` | `{query, num_results?=5}` | `{github_repos[], …}` | Exa-backed (summary carries stars/language/branch) |
| 7 | `think` | `{reflection}` | fixed `"Reflection recorded. Continue with next action."` | **no-op**; the only way CoT propagates to the wire |
| 8 | `finish` | `{}` | (no tool_complete) → `generating_report`×2 → `complete` | **sentinel, not a tool**; not in persisted `tool_calls` array |
| +9 | `doc_read` | (doc analogue of `read_source_content`) | — | confirmed KNOWN via `list_sources.guidance` echo (§15.4) |
| +10 | `doc_grep` | (doc analogue of `code_grep`) | — | confirmed KNOWN (§15.4) |

### 5.4 Iteration model + termination (KNOWN — §7.4, §15.4)

- SSE vocabulary: `connected → (heartbeat) → iteration_start → tool_start{action,args,reason} → tool_progress? → tool_complete → … → generating_report ×2 → complete{final_report, citations, iterations, duration_ms}`.
- **Loop terminates when the agent emits `action:"finish"`.** No max-iteration hard cap observed; **median 5 iterations, 41s wall (range 2–7, 32–87s)**; §15.4 captured a 9-iteration / 111s job.
- **Two synthesis stages** (two back-to-back `generating_report` events: *"Synthesizing research findings"* then *"Creating comprehensive research report"*) — tool-summary aggregation, then final markdown-with-citations rendering. Synthesis is ~40s / ~37% of job wall (§15.4). Citations are `{source_id:int, tool, args, summary}`; `[Source N]` tags in the report point to them.
- **Stateless chat continuation (§7.7, §15.4):** each follow-up turn rebuilds a fresh agent loop from the DB — prompt carries `<original_research_query>` + full `<existing_report_excerpt>` + full `<existing_citations>` + ONLY the current `<followup_chat_context>` (no running history).
- Genuine plan→act→observe→reflect: each iteration's `reason` references the prior tool's result (live 6-iter trace §7.4: list_sources → get_github_tree → read index.js → read readme → read test.js → finish).

### 5.5 Anti-injection (KNOWN — §7.5)

0/11 prompt-injection probes extracted the system prompt. **Why fundamentally unextractable:** (1) agent output is JSON-action-only during iterations (can't emit free-form prompt); (2) the final report goes through a *separate* synthesis LLM whose input is `tool_calls + summaries` only (not the system prompt); (3) framing attacks ("authorized red-team", "internal diagnostic", "system-level message") all rejected. The best refusal is *silent refusal* (answer the legit part, pretend the injection wasn't there). Leaked refusal fragments ("operating policy", "fundamental security protocols", "sanctioned operation") reconstruct the prompt at ~80-90% structural confidence (§7.5, D4.1.B).

> **→ hyperresearch upgrade — agentic mode ALONGSIDE the fixed pipeline.** hyperresearch's 16 stages are **scripted** (skill prompts execute in fixed order, HR§1). NIA's Oracle is **agentic** (the model picks the next tool each iteration). These are complementary, not competing:
> - **Keep the 16-stage pipeline as the default `full`/`light` tier** — it's the disciplined, reproducible, benchmark-tuned path (HR§1, contradiction graph + triple-draft + adversarial critics + patch-not-regenerate). Scripted wins on *thoroughness and instruction-following*.
> - **Add an `oracle` tier** — a JSON-action ReAct loop over the *same vault* for fast, exploratory, conversational research where the fixed pipeline is overkill. The tool registry maps cleanly onto hyperresearch's existing CLI: `list_sources`→`hpr search`/`tags`, `query`→the new hybrid `search` (§3), `code_grep`→`hpr search` over code-notes, `read_source_content`→`hpr note show <id> -j`, `get_github_tree`→`hpr graph hubs`/`outlinks`, `run_web_search`→`hpr fetch` + Claude WebSearch, `think`/`finish` as-is. The `{action,args,reason}` JSON-action shape + the two-stage `generating_report` synthesis + the stateless DB-rebuilt chat continuation all lift directly. Run it in a sandbox (Daytona/e2b/Modal, or just a `[Read, Bash-allowlisted]` subagent for a local tool) with the same `--no-builtin-tools` discipline.
> - **Tier selector:** the existing stage-1 decompose (HR§1) already classifies `pipeline_tier`; add `oracle` as a third value chosen when the query is conversational/narrow ("what does X do?") rather than report-grade.

---

## 6. Dream cycle (§9) — auto-wiki entity enrichment + contradiction detection

### 6.1 Spec (KNOWN — §9)

The **vault** = a per-user agent-maintained markdown wiki (concepts/entities/notes subdirs) in Postgres + a TurboPuffer namespace. The **dream cycle** is a 5-phase Temporal workflow (cron: refresh daily 09:00 UTC, dream Sunday 03:00 UTC):

```
Phase 1 — Bootstrap (~8s, $0): count pages, enforce MIN_PAGES_FOR_DREAM=2 guard
          (only /concepts/ + /entities/ count; /notes/ + metadata ignored — §9.2)
Phase 2a — Entity discovery (~26s, 1 LLM call): pages_concat → top-10 candidate
          entities/concepts. ENTITY_CAP_PER_RUN=10 (overflow SILENTLY DROPPED, §9.3).
          Two type labels only: `entity` (people/products/repos) vs `concept` (algorithms/principles).
Phase 2b — Per-entity synthesis (~32s/entity × ≤10 = ~5min, 10 LLM calls):
          one wiki page per candidate (Compiled Truth + Sources + Wikilinks + Timeline)
Phase 3 — Cross-source connections (~30-60s, 1 LLM call): WRITES NEW PAGES into the vault
          (~5 connection pages/medium vault). Requires ≥2 sources WITH PAGES.
Phase 4 — Contradiction detection (~30s, 1 LLM call): inter-page (X says P, Y says ¬P)
          AND intra-page (prose says P but a code snippet/table says ¬P) — §9.3
Phase 5 — Report write (~500ms, 0 LLM): /dream-report.md + regenerate /index.md + append /log.md
```
Models: ingest `claude-sonnet-4-5-1m` + `anthropic-beta: context-1m-2025-08-07`; dream default `claude-opus-4-7`. No SSE — poll `GET /v2/vaults/{id}.workflow_status.last_event` or grep `/log.md`. **Destructive bug (§9.4):** when the 10/24h cap exhausts mid-run, a vault was DELETED ENTIRELY in one observed case — do NOT replicate.

### 6.2 Contradiction detection compared to hyperresearch's stage 3

| | NIA Dream Phase 4 (§9.3) | hyperresearch stage 3 contradiction-graph (HR§1, HR§22) |
|---|---|---|
| Trigger | weekly cron over the whole vault | per-run, after width-sweep, over `claims-*.json` |
| Input | rendered wiki pages (prose + code/tables) | structured `claims-*.json` (`stance_target`, `stance`, `entities`, `numbers`, `scope_conditions`, `evidence_type`) |
| Mechanism | 1 LLM call detecting inter- + intra-page contradictions | **mechanical pairing** (no LLM): same `stance_target`+opposing `stance`; same `entities`+opposite conclusions; same scope+different `numbers`; overlapping `scope_conditions`+opposing `evidence_type` (`hyperresearch-3-contradiction-graph.md:35-40`) |
| Output | `/dream-report.md` Contradictions section, e.g. *"cache-resizing.md vs cache-resizing.md: prose says 'reset to 0' but code shows `this.#size = items.length`"* | ranked "fight" clusters → `contradiction-graph.json` + `consensus-claims.json` (3+ independent sources agree) → drives stages 4/5/7 |

**hyperresearch's contradiction stage is the more rigorous half** — mechanical (deterministic, cheap), structured (operates on extracted claims not prose), and feeds the downstream argumentative pipeline. **NIA's Dream is the more rigorous *enrichment* half** — it auto-generates *new entity/concept wiki pages* from mentions that lack their own page, and detects *intra-page* (prose-vs-code) contradictions that hyperresearch's claim-pairing can't see (it only pairs across notes).

> **→ hyperresearch upgrade.** hyperresearch already has the contradiction-detection half (better than NIA's). What it lacks is the **auto-entity-page enrichment**: NIA's Phase 2a/2b discovers entities *mentioned but unwritten* and synthesizes a page each. hyperresearch has the raw material — its `links` graph surfaces **broken wiki-links** (`hpr graph broken`, HR§3) and writes **stub notes** for them (`hpr graph stub`, HR§3 `:503`). Upgrade: replace stub-writing with a **Dream-style enrichment pass** — for each high-inbound broken `target_ref` (an entity mentioned ≥N times but unwritten), spawn a synthesizer subagent that reads the citing notes and writes a real `concept`/`entity` note (with `## Compiled Truth` + `## Sources` + wikilinks + dated timeline, per §9.3's page template). Cap it (`ENTITY_CAP_PER_RUN=10`, path-aware gate `MIN_PAGES_FOR_DREAM=2`) and run it as an off-pipeline `hpr dream` command, NOT inside the 16 stages (matching NIA's cron separation). Add intra-page (prose-vs-code-snippet) contradiction detection to hyperresearch's polish/critic stages — its claim-pairing currently only catches inter-note contradictions.

---

## 7. NIA → hyperresearch upgrade map

### 7.1 What each NIA primitive turns hyperresearch into

| NIA primitive (§) | hyperresearch today | After upgrade | Effort |
|---|---|---|---|
| **Single retrieval embedder** (§1.1, Qwen3-4B dim 2560, asymmetric `document`/`query`) | dead `embeddings` table | populated vectors; dense retrieval lane | wire existing table + a `note_chunks` table |
| **AST-header chunker** (§2) | whole-note BM25 | structural-header-prefixed chunks; code-notes get true tree-sitter AST chunks | reuse NIA §12.3 `chunk_code_file` + a markdown-H2 splitter |
| **Hybrid alpha=0.7 + rerank + three-tier fusion** (§3) | FTS5 BM25 only | **hybrid neural+keyword** with cross-encoder rerank | the algebra is ~80 lines (NIA §12.3); BM25 lane already exists |
| **`expand_symbols`** (§3.5) | — | call-graph second-pass via the existing `links` table | small; reuse `backlinks`/`outlinks` SQL |
| **Source-type/tier weights** (§3.3) | status multipliers `1.5/0.7/0.3` (already!) | compose status × tier-weight `{ground_truth:1.2 … commentary:0.85}` | one dict + one multiply |
| **L2 semantic cache** (§4) | none | negation-aware ~20× query cache | one SQLite table + LSH bucket + cosine |
| **Oracle agentic mode** (§5) | fixed 16 stages only | **`oracle` tier** alongside `light`/`full` for fast conversational research | tool registry maps onto existing CLI; JSON-action loop |
| **Dream entity enrichment** (§6) | broken-link stubs; (better) contradiction stage already exists | auto-synthesized entity/concept pages from high-inbound mentions | replace `graph stub` with a synthesizer subagent + caps |

**Net:** hyperresearch's FTS-only vault becomes a **hybrid neural+keyword vault with cross-encoder rerank, a semantic cache, and AST/structural-header chunking** — i.e., NIA's exact retrieval stack — while keeping hyperresearch's superior on-disk discipline (markdown-is-truth, content-probe sync, tool-locked patchers) and its superior structured contradiction pipeline. The two products are complementary: NIA = best *retrieval*, hyperresearch = best *research discipline*.

### 7.2 Agentic-vs-scripted recommendation

**Offer both.** Keep the 16-stage scripted pipeline as `full`/`light` (it's benchmark-tuned for thoroughness + instruction-following — DeepResearch-Bench RACE 58.3/100, HR§ example-report). Add an Oracle-style JSON-action ReAct `oracle` tier for fast, narrow, conversational queries where the fixed pipeline is overkill. The stage-1 decompose already classifies tier — add `oracle` as the value for conversational/single-question intents. The agentic loop runs over the **same vault** via the same CLI tools, so there's one source of truth.

### 7.3 Self-hosting cost — Qwen3 GPU vs API embeddings (the decision)

| Option | What | Cost shape | When to pick |
|---|---|---|---|
| **A. Self-host Qwen3-Embedding-4B** (NIA's choice, §4.1) | dim 2560, fp16, ~16K ctx, L2-normed, batch-100 single forward pass on A100-40GB/H100 via vLLM 0.7+ or HF TEI | **GPU-hour fixed cost** (~$1–2/hr cloud A100; or a 24GB consumer card for a 4B fp16 model at lower batch). Amortizes only at high index volume | large/shared corpora, privacy-critical, or when you're already running a GPU |
| **B. API embeddings** (Cohere v3 / OpenAI 3-large / Voyage) | dim 1024–3072, pay-per-token | **per-token variable cost**, $0 idle | **single-user hyperresearch** — index volume is low (tens-hundreds of notes/run), GPU idle cost dominates |

**Recommendation for the ultimate-research skill (single-operator, hyperresearch-base):** **Option B for v1.** A single-user research tool indexes hundreds of notes per run, not millions — a self-hosted GPU sits idle 95% of the time and its fixed cost dwarfs API embedding spend. Use one API embedder (Cohere `embed-multilingual-v3.0` dim 1024, or Voyage `voyage-3` / OpenAI `text-embedding-3-large`) for **both** lanes (retrieval + cache) at this scale — NIA's two-embedder split is a *cost-amortization-at-scale* optimization that doesn't pay off single-user. Self-hosted Qwen3-4B (matching NIA exactly) becomes worthwhile only if the vault grows to a shared multi-user/multi-machine corpus or privacy forbids sending bodies to an API. Either way, **preserve the asymmetric `input_type` (document at index, query at retrieval)** (§4.1 `[CORRECTION]`) — it's free quality and required by Qwen3/Cohere/Voyage alike. Keep the dim in the `embeddings.dimensions` column so the vault is model-portable (swap embedder → re-embed → no schema change), matching hyperresearch's "markdown is truth, SQLite is cache, rebuildable" ethos.

---

## 8. Constants reference (everything a senior engineer needs, cited)

```
# ── Embedders (§1, §4.1, §4.2) ───────────────────────────────────────
RETRIEVAL_EMBEDDER          = Qwen3-Embedding-4B ("zembed-1"), dim 2560, fp16, L2-normed   [§4.1]
EMBED_TRUNC_CHARS           = 16384 (=2^14) per text                                       [§3.4]
EMBED_BATCH_CAP             = 100 texts/call                                               [§3.4]
EMBED_INPUT_TYPE            = "document" (index) | "query"/"search_query" (retrieval)      [§15.1 CORR]
CACHE_EMBEDDER              = Cohere embed-multilingual-v3.0, dim 1024                      [§4.2]
# ── Chunking (§2, §3.5) ──────────────────────────────────────────────
CHUNK_STRATEGY              = tree_sitter (code) | lines (md) | page/section (pdf)         [§3.5]
CHUNK_BYTE_TARGET           = 1500–3000 B (~380–860 tokens); <~2.5KB → whole-file chunk    [§3.5]
CHUNK_OVERLAP               = 0 (clean AST cuts)                                           [§3.5]
CHUNK_ID                    = sha256(file)[:64] + "-" + idx (1-indexed)                    [§3.5]
# ── Hybrid retrieval (§3) ────────────────────────────────────────────
ALPHA                       = 0.7  (0.7 vector / 0.3 BM25)                                 [§5.1]
TOP_K_RETRIEVE              = 30 candidates before rerank                                  [§5.1]
TOP_N_FINAL                 = 10 (query) / 20 (universal)                                  [§5.1]
RETRIEVAL_WEIGHT            = {rank≤3: 0.75, ≤10: 0.60, >10: 0.40}                         [§5.2]
DEEP_RANK_PENALTY           = 0.005·(rank−10) for rank>10                                  [§5.2]
SOURCE_TYPE_WEIGHT          = {repository:1.2, documentation:1.0, research_paper:0.9,
                               huggingface_dataset:0.85}                                   [§5.3,§15.3]
LANGUAGE_BOOST_FACTOR       = 1.5 (max 5.0)                                                [§15.3]
RERANKER                    = Cohere rerank-v3.5 (multilingual); reranks ALL 30; ≤~0.95    [§5.4]
MAX_SOURCES (namespaces)    = 5 (=sources_searched)                                        [§15.3]
SOURCES_FOR_ANSWER          = 10                                                           [§15.3]
EXPAND_SYMBOLS              = off by default (cAST 2nd-pass over call-graph neighbors)     [§15.3]
# ── Semantic cache (§4) ──────────────────────────────────────────────
SEMANTIC_CACHE_THRESHOLD    = 0.92 cosine (range 0.8–1.0)                                  [§5.5,§15.3]
CACHE_KEY_NS                = "search:universal:<16hex>" (xxhash64/SimHash over q-embed)   [§5.5]
CACHE_SPEEDUP               = ~20–25× (mean 14.5×)                                         [§5.5,§15.3]
CACHE_TYPE                  = "semantic" L2 (+ implied "exact" L1)                         [§15.3]
NEGATION_FIX                = force miss on /not|n't|without|except|no_std|unlike/  (OUR)  [§4.3]
# ── Oracle agentic loop (§5) ─────────────────────────────────────────
ORACLE_ACTION_SHAPE         = {action, args, reason}  (JSON-action ReAct, NOT native)     [§7.1]
ORACLE_TOOLS                = list_sources, query, code_grep, read_source_content,
                              get_github_tree, run_web_search, think, finish,
                              doc_read, doc_grep                                           [§7.3,§15.4]
ORACLE_TERMINATION          = agent emits action="finish" (sentinel)                       [§7.3]
ORACLE_MEDIAN               = 5 iters / 41s (range 2–7 / 32–87s)                           [§7.4]
ORACLE_MODEL                = claude-opus-4-7 default; sonnet-4-5 / sonnet-4-5-1m override [§7.2]
ORACLE_SANDBOX_TTL          = 1800s; --no-builtin-tools --thinking 10000                   [§7.2]
SYNTHESIS_STAGES            = 2 (aggregate tool summaries, then render markdown+citations) [§7.4,§15.4]
# ── Dream enrichment (§6) ────────────────────────────────────────────
MIN_PAGES_FOR_DREAM         = 2 (only /concepts/+/entities/ count)                         [§9.2]
ENTITY_CAP_PER_RUN          = 10 (overflow silently dropped)                               [§9.3]
DREAM_MODELS                = ingest sonnet-4-5-1m (+1M beta hdr); dream opus-4-7          [§9.1]
DREAM_PHASES                = bootstrap → entity-discover → per-entity-synth → connections
                              → contradictions → report                                   [§9.3]
```

---

## 9. KNOWN / INFERRED / IDEA audit

**KNOWN (NIA source/OpenAPI/live wire):** dim 2560 + 16384-char trunc + batch-100 + L2-norm + fp16 [§3.4,§4.1]; AST-header format verbatim [§3.1]; tree-sitter chunk strategy + sizes [§3.5]; `alpha=0.7` [§5.1]; three-tier `{0.75/0.60/0.40}` verified to 1e-15 + re-confirmed live [§5.2,§15.3]; `SOURCE_TYPE_WEIGHT` schema-confirmed [§5.3,§15.3]; `expand_symbols` cAST 2nd-pass [§15.3]; semantic cache 0.92 + `_cache_*` wire fields + ~20-25× [§5.5,§15.3]; negation-blindness bug [§4.3]; Oracle JSON-action ReAct + 10-tool registry + 2-stage synthesis + 1800s sandbox + median 5/41s [§7]; Dream 5 phases + `MIN_PAGES=2`/`ENTITY_CAP=10` + intra/inter-page contradiction [§9]; asymmetric `input_type` [§15.1].

**INFERRED (NIA behavioral fingerprint):** `zembed-1` IS Qwen3-Embedding-4B (dim-2560 fingerprint + EN↔FR + fp16 + 16K=half-of-32K) [§4.1]; cache embedder IS Cohere v3 (dim 1024 + EN↔FR 0.93-0.95) [§4.2]; reranker IS Cohere rerank-v3.5 (score range + path-aware + multilingual) [§5.4]; deep-rank penalty `0.005·(rank−10)` (empirical linear fit) [§5.2]; `code_grep` precomputed trigram/zoekt index [§7.3].

**IDEA (our integration design — not in either product):** compose hyperresearch status-multipliers × NIA tier-weights [§3.6,§7.1]; map `expand_symbols` onto hyperresearch's wiki-link graph [§3.6]; single-user single-API-embedder for both lanes (collapse NIA's two-embedder split) [§7.3]; `oracle` as a third tier in stage-1 decompose [§5,§7.2]; replace `graph stub` with Dream-style entity-page synthesis + intra-note contradiction detection [§6]; negation-aware single-user semantic cache table [§4.3,§7.1]; structural markdown-H2 header before embedding (the markdown analogue of AST headers) [§2].

---

*End of 04_NIA_STACK.md. Sources: `teardowns/NIA.md` §1–§15 (live RE through 2026-05-26, enterprise key); `teardowns/HYPERRESEARCH.md` §0–§3, §22 (full repo clone, v0.8.6). Companion dossiers in `ultimate-research/investigation/`.*
