# 15 — Keyless Vault Retrieval & Reranking

**Theme.** Bad Research is a Claude Code skill that runs on the host model with
**no API keys**. The vault is the accumulated research-note corpus (markdown +
code snippets) already indexed in SQLite. This dossier mines the
retrieval/rerank *patterns* from NIA / Perplexity / Exa and reimplements the
QUALITY keylessly — ranking the best chunks for synthesis using only:

- **FTS5/BM25** (SQLite, keyless — hyperresearch's existing lexical lane).
- **Deterministic Python fusion math** (RRF, min-max hybrid, three-tier blend) —
  this is pure arithmetic, no model.
- **The Claude Code host model as a reranker** (LLM-rerank — keyless, token-cost).
- **Local neural models** (`sentence-transformers` bi-encoder / `bge-reranker`
  cross-encoder) — keyless (no network) but heavy deps; shipped ONLY if justified.

**The hard rule (no Cohere/Exa/Voyage).** Every embedding/rerank API in the
upstream products is replaced. NIA's `zembed-1` (Qwen3-4B), NIA's Cohere
`embed-multilingual-v3.0` cache embedder, NIA's Cohere `rerank-v3.5`,
Perplexity's `pplx-embed`, Exa's link-prediction transformer — **none are
callable**. What survives the keyless cut is the *math and the orchestration*,
which is where most of the quality lives.

Cross-refs: `teardowns/NIA.md` §4 (two-embedder) / §5 (hybrid α=0.7, rerank-v3.5,
three-tier `0.75/0.60/0.40`, `expand_symbols`) / §5.5 (semantic cache 0.92);
`docs/investigation/04_NIA_STACK.md` §3.5; `teardowns/PERPLEXITY_DEEP.md`
(progressive L1/L2/L3 rerank, 0.70 gate, <30% re-retrieve);
`teardowns/EXA.md` §4.2 (Matryoshka/binary quant), §6.2 (RRF k=60).
Already-built code: `src/bad_research/retrieval/{fusion,rerank,fts_chunks,cache,engine,store,constants}.py`.

---

## §0. TL;DR — the keyless stack we ship

```
                 query
                   │
        ┌──────────┴───────────┐
        ▼                      ▼
   FTS5/BM25 lane        (OPTIONAL) local bi-encoder
   (keyless, kept)        bge-small/MiniLM cosine
        │  bm25 list           │  vector list
        └──────────┬───────────┘
                   ▼
        RRF k=60  (no score calibration needed — rank-only)
          OR α=0.7 min-max hybrid (if both lanes emit calibrated scores)
                   │  top-30 candidates, with pre_rerank_rank
                   ▼
        ┌──────────────────────────────────────┐
        │ RERANK (the keyless decision)         │
        │  default → Claude-Code LLM-rerank     │
        │            (batched relevance scoring)│
        │  escalate → local bge-reranker-v2-m3  │
        │             cross-encoder (no key)    │
        └──────────────────────────────────────┘
                   │  reranker_score ∈ [0,1] per candidate
                   ▼
        three-tier fuse  w = {≤3:0.75, ≤10:0.60, else:0.40}
        final = max(0, w·initial + (1-w)·rerank − 0.005·(rank-10)⁺)
        × SOURCE_TYPE_WEIGHT[content_type]
                   │
                   ▼
        0.70 relevance gate  →  if <30% survive: expand_symbols
        (call-graph / wiki-link neighbors) + re-retrieve, ≤2 rounds
                   │
                   ▼
        semantic cache (0.92 cosine, negation-guarded) — keyless via a
        local mini-embedder OR a token-set Jaccard fallback (see §6)
                   │
                   ▼
        top_k chunks → synthesis
```

**The one-line verdict (no-overkill):** *Ship FTS5 + Claude-Code LLM-rerank as
the default. Do NOT ship a 400 MB+ local cross-encoder by default.* The
LLM-rerank uses the host model that is **already in the room** (zero marginal
infra, zero download, zero GPU), and it is a strictly more capable reranker than
`bge-reranker-v2-m3` for the research-note domain (long, mixed prose+code chunks
where instruction-following relevance judgement beats a 560 MB MiniLM-class
cross-encoder). The local cross-encoder is the **offline escalation** for users
who run the skill air-gapped or want to spend zero tokens on ranking — it is a
config flag, not the default. The local bi-encoder embedding lane is **optional
recall insurance**, justified only on large vaults (§4 has the threshold).

---

## §1. What the upstream products do — and the keyless residue of each pattern

| Upstream pattern | Source | The KEY-bearing part (cut) | The keyless residue (kept) |
|---|---|---|---|
| Two-embedder split (retrieval vs cache) | NIA §4 | `zembed-1` Qwen3-4B API + Cohere v3 API | The *idea* of separating recall embedding from cache-key embedding; collapses to one tiny local embedder or none |
| α=0.7 hybrid fusion | NIA §5.1 | scores come from TPuf vector+BM25 | the **0.7/0.3 min-max blend math** — pure arithmetic |
| Three-tier weight 0.75/0.60/0.40 | NIA §5.2 | needs `initial_score` + `reranker_score` | the **closed-form blend + deep-rank penalty** — verified to 1e-15, fully keyless |
| Source-type multiplier 1.2/1.0/0.9/0.85 | NIA §5.3 | none — it's a dict lookup | kept verbatim |
| Cohere rerank-v3.5 over top-30 | NIA §5.4 | the Cohere API | replaced by **LLM-rerank or local cross-encoder** |
| Semantic LSH cache 0.92 | NIA §5.5 | Cohere v3 embed → xxhash64 LSH bucket | the **0.92 cosine + negation guard**; embed via local mini-model or hash-sim |
| `expand_symbols` cAST 2nd-pass | NIA §3.5 / 04 §3.5 | none — it's call-graph walking | kept; maps onto the vault's wiki-link graph |
| RRF k=60 | Exa §6.2 | none — rank-only fusion | kept verbatim — **the most keyless-friendly fusion** (no score calibration) |
| Matryoshka + 1-bit binary quant | Exa §4.2 | the link-prediction transformer | the **quant trick** applies to ANY local embedding; cuts vault RAM 16-24× if we ship a local embedder |
| Progressive L1→L2→L3 rerank, 0.70 gate, <30% re-retrieve | Perplexity §4 | XGBoost / cross-encoder models | the **cascade shape + 0.70 threshold + 30% failsafe** — pure orchestration, kept |

The pattern is consistent: **the proprietary part is always a model behind an
API; the reusable part is always the arithmetic that combines model outputs.**
We keep all the arithmetic and substitute keyless scorers for the models.

---

## §2. FTS5/BM25 — the keyless baseline lane (KNOWN, kept verbatim)

This is hyperresearch's existing lexical lane, forked into
`retrieval/fts_chunks.py`. It is 100% keyless (SQLite is compiled in) and is the
**floor** every other lane improves on.

### §2.1 The lane mechanics (KNOWN — `fts_chunks.py`, `search/fts.py`)

- Virtual table `chunk_fts USING fts5(chunk_id UNINDEXED, body, note_id UNINDEXED, tokenize='porter unicode61')`.
- Query preprocessing (`preprocess_query`, forked from hyperresearch verbatim):
  - prefix-match every bare word: `python async` → `"python"* "async"*`
  - split glued alphanumerics: `mamba3` → `mamba 3`, `gpt4o` → `gpt 4 o`,
    `llama3.1` → `llama 3 1` (the `_split_alphanum` regex pair). This matters
    for a research corpus full of model-version tokens.
  - preserve quoted phrases and pass through explicit `AND/OR/NOT/NEAR(`.
- Scoring: `bm25(chunk_fts, 0.0, BM25_BODY_WEIGHT, 0.0)`, `abs()`-ed because
  SQLite's `bm25()` returns negatives (smaller = better). `BM25_BODY_WEIGHT=1.0`.
- For the **note-level** lane (hyperresearch `search_fts`), the column weights
  are richer and we keep them: `title=10.0, body=1.0, tags=5.0, aliases=3.0`,
  plus a status multiplier `{evergreen:1.5, stale:0.7, deprecated:0.3}`
  (constants `BM25_*` in `retrieval/constants.py`). The chunk lane only has a
  body column, so only body is weighted there.

### §2.2 The quality ceiling of BM25-only (the honest assessment)

BM25 is a bag-of-words lexical scorer. On a research-note vault it is **better
than people assume** because:

1. The corpus is technical — exact tokens (`alpha=0.7`, `rerank-v3.5`,
   `IVF_HNSW_PQ`, `bge-reranker-v2-m3`) are high-signal and lexical match nails
   them. Vector search often *blurs* these into nearby-but-wrong neighbors.
2. The `porter` stemmer + alphanumeric splitting recovers most morphological and
   version-token variation.

Where BM25-only **fails** (the recall holes a reranker/embedder fills):

- **Vocabulary mismatch / paraphrase.** Query "how to cut vector RAM" vs a note
  that says "binary quantization reduced memory 16×" — zero token overlap on the
  concept words. BM25 returns nothing useful; this is the canonical dense-recall
  win (Exa §4.2 is literally about this note).
- **Cross-lingual** (NIA §4.1 used Qwen3 multilingual for EN↔FR). Out of scope —
  the vault is English; we drop this requirement entirely. (One fewer reason to
  ship a heavy multilingual embedder.)
- **Ranking the long tail.** BM25 orders by term frequency, which over-rewards
  chunks that *repeat* a keyword vs chunks that *explain* it. This is exactly
  what a reranker fixes — and why the reranker, not the recall lane, is where we
  spend the keyless budget (§5).

**Keyless reimplementation:** already shipped (`fts_chunks.py`). Cost: ~0,
sub-millisecond per query at vault scale (thousands of chunks). Quality: a strong
recall floor; the weak link is *ranking the long tail* and *paraphrase recall*,
both addressed downstream. This lane is **always on** and is the only lane that
is mandatory.

---

## §3. Fusion math — fully keyless (KNOWN, verified)

All fusion is arithmetic over candidate IDs and is already implemented in
`retrieval/fusion.py`. No model, no key. Two fusion modes, picked by whether the
second lane emits *calibrated scores* or only *ranks*.

### §3.1 RRF k=60 — the rank-only fuser (KNOWN — Exa §6.2, `fusion.rrf_merge`)

```
rrf(d) = Σ over each ranked list L:  1 / (k + rank_L(d))      k = 60
```

Implementation (0-based rank, matches `fusion.rrf_merge`):

```python
RRF_K = 60
def rrf_merge(*ranked_lists, k=RRF_K):
    acc = {}
    for lst in ranked_lists:
        for rank0, cid in enumerate(lst):       # 0-based
            acc[cid] = acc.get(cid, 0.0) + 1.0 / (rank0 + k)
    return sorted(acc.items(), key=lambda kv: kv[1], reverse=True)
```

**Why RRF is the *most* keyless-friendly fuser:** it never touches raw scores —
only positions. BM25's `abs(bm25)` and a bi-encoder's cosine live on totally
different scales; RRF sidesteps the calibration problem entirely. `k=60` is the
canonical constant (Exa, the original Cormack 2009 paper, LanceDB) — large enough
that rank-1 (`1/60 ≈ 0.0167`) and rank-2 (`1/61 ≈ 0.0164`) are close, so a doc
that appears mid-pack in *both* lanes can beat a doc that's rank-1 in only one.
This is the desired "agreement beats single-lane confidence" behavior.

**Use RRF when:** fusing BM25 with the local bi-encoder lane (§4) — two
incomparable score scales. RRF is the default fuser whenever a neural lane exists.

### §3.2 α=0.7 min-max hybrid — the calibrated fuser (KNOWN — NIA §5.1, `fusion.hybrid_fuse`)

```python
ALPHA = 0.7   # 70% vector, 30% BM25 (NIA's exact split)
def hybrid_fuse(vec_scores, bm25_scores, *, alpha):
    nv = minmax(vec_scores)      # each lane independently mapped to [0,1]
    nb = minmax(bm25_scores)
    ids = set(nv) | set(nb)
    return {cid: alpha*nv.get(cid,0) + (1-alpha)*nb.get(cid,0) for cid in ids}
```

`minmax_normalize` maps each lane to `[0,1]`; a constant lane → all 1.0 (stays
informative rather than collapsing to 0). A candidate absent from a lane scores 0
from that lane.

**Use α=0.7 when:** both lanes produce meaningful magnitudes you want to weight
(NIA does 70/30 because its embedder is strong). In the keyless world this means
"local bi-encoder cosine + BM25" — and it produces an `initial_score ∈ [0,1]`
that the three-tier blend (§3.3) consumes directly, which RRF does *not* (RRF
scores are tiny and uncalibrated). **So: if there is a neural recall lane, fuse
with α=0.7 to feed the three-tier blend; if recall is BM25-only, there is nothing
to fuse and `initial_score` is just the min-max-normed BM25.**

### §3.3 Three-tier blend + deep-rank penalty (KNOWN — NIA §5.2, verified to 1e-15)

The post-rerank fusion. **This is the single most valuable keyless artifact in
the whole stack** — it's NIA's production-tuned blend, reverse-engineered to
floating-point exactness from 18 live data points, and it's pure arithmetic.

```python
RETRIEVAL_WEIGHT = {3: 0.75, 10: 0.60}; RETRIEVAL_WEIGHT_DEFAULT = 0.40
DEEP_RANK_PENALTY = 0.005
def retrieval_weight(rank):                  # rank is 1-based pre-rerank rank
    if rank <= 3:  return 0.75               # trust RETRIEVAL more (top tier)
    if rank <= 10: return 0.60
    return 0.40                              # trust RERANKER more (tail tier)
def three_tier_fuse(initial, reranker, rank):
    w = retrieval_weight(rank)
    base = w*initial + (1-w)*reranker
    if rank > 10:
        base -= DEEP_RANK_PENALTY * (rank - 10)
    return max(0.0, base)
```

**The counter-intuitive design choice (NIA §5.2, kept verbatim):** the system
trusts the *retrieval* score MORE for top-3 (75% weight on `initial`) and the
*reranker* MORE for the tail (60% on reranker for ranks 4-10, and effectively
60% for 11+ too). Reasoning from the teardown: when stage-1 confidently surfaces
its top-3, those are usually right and the reranker's value is *filtering noise
from the long tail*, not reordering high-confidence hits. The deep-rank penalty
(`−0.005·(rank−10)` for rank>10) was fit from the residual table (residual grows
−0.04 @ rank 11 → −0.09 @ rank 26). **This logic is model-agnostic — it works
identically whether `reranker` came from Cohere, a local cross-encoder, or the
Claude-Code LLM-rerank.** That's why it survives the keyless cut unchanged.

### §3.4 Source-type multiplier (KNOWN — NIA §5.3, `fusion.apply_source_type_weight`)

```python
SOURCE_TYPE_WEIGHT = {"code":1.2,"repository":1.2,"docs":1.0,"documentation":1.0,
  "article":1.0,"blog":1.0,"paper":0.9,"research_paper":0.9,
  "dataset":0.85,"huggingface_dataset":0.85}   # default 1.0
final_score = three_tier_fuse(...) * SOURCE_TYPE_WEIGHT.get(content_type, 1.0)
```

A flat dict lookup, applied after the blend, before the gate. NIA biases toward
code (1.2). For a *research-note* vault we keep the schema but the relevant
`content_type`s are `docs/article/paper`; code chunks (extracted from the notes)
keep the 1.2 boost since they're high-signal. Zero cost, no key.

---

## §4. The keyless neural recall lane — local embeddings OR skip

NIA's recall embedder is `zembed-1` (Qwen3-Embedding-4B, dim 2560, self-hosted
GPU). We cannot call it. The question: **do we ship a local bi-encoder for
neural recall, or run BM25-only recall?** This is a real fork, not a foregone
conclusion. Decide it with the §2.2 failure analysis, not vibes.

### §4.1 The candidate local embedders (keyless, no API)

All run via `sentence-transformers` (pip, CPU-fine, no key, no network at
inference once downloaded). Specs that matter for a single-user skill:

| Model | Dim | Disk | RAM (fp32) | Encode latency (CPU, 1 chunk) | Quality (MTEB retr. avg) |
|---|---|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 384 | ~130 MB | ~150 MB | ~8-15 ms | ~51.7 |
| `BAAI/bge-base-en-v1.5` | 768 | ~440 MB | ~500 MB | ~25-40 ms | ~53.3 |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | ~90 MB | ~120 MB | ~5-10 ms | ~50.0 |
| `intfloat/e5-small-v2` | 384 | ~130 MB | ~150 MB | ~8-15 ms | ~50.2 |

`bge-small-en-v1.5` is the sweet spot if we ship anything: 130 MB, dim 384,
asymmetric prompts (`"Represent this sentence for searching relevant passages:"`
prefix on queries) so it honors the asymmetric `input_type` seam the codebase
already has (`EmbedProvider.embed(texts, *, input_type)`). dim 384 also divides
cleanly under LanceDB's `num_sub_vectors=16` PQ constraint (384/16=24 — the
`_pq_sub_vectors()` fallback in `store.py` handles it, but 384 is clean).

### §4.2 The Matryoshka + binary-quant trick — keyless, and it makes a local lane cheap (Exa §4.2)

Exa's storage trick is model-agnostic and **directly applicable** to a local
bi-encoder, which is the single biggest reason a local lane is even
contemplable on a laptop:

1. **Matryoshka dim truncation** — `bge` and `e5` are NOT natively Matryoshka,
   but the prefix-truncation trick still works approximately; better, just pick
   the small (384-dim) model and skip truncation. (Exa cut 4096→256 for 20×; we
   start small.)
2. **1-bit binary quantization of document vectors** (sign-bit hashing), keep
   the **query vector fp32** → asymmetric dot product (ADC). Exa: "Keep using
   binary document embeddings — but for the query, use uncompressed floats… use
   dot product." 16× memory reduction, empirically near-lossless on rank order
   if the embedder is decent. For a 50k-chunk vault: dim-384 fp32 = 384·4·50k ≈
   **77 MB**; binary = 384/8·50k ≈ **2.4 MB**. Fits in L1-cache-friendly scoring
   (Exa §4.2: 4-bit lookup tables, ~50 ns/doc). At single-user vault scale even
   the fp32 version is trivial, so binary quant is **optional** here — it only
   matters once a vault exceeds ~500k chunks.

**Keyless reimplementation:** if we ship the lane, `bge-small-en-v1.5` via
`sentence-transformers`; store fp32 in LanceDB (`store.py` already does cosine
IVF_HNSW_PMQ, `distance_to_score = 1 - cosine_distance`). Binary quant is a
later optimization, gated on vault size, not shipped day-one (no-overkill).

### §4.3 The decision: ship the local embedder only above a vault-size threshold

The local bi-encoder buys exactly ONE thing BM25 can't: **paraphrase / vocab-
mismatch recall** (§2.2). Weigh that against the cost:

- **Cost of shipping it:** a 130 MB download (first run), a `sentence-transformers`
  + `torch` dep (~2 GB installed — `torch` is the heavy part), ~10 ms/chunk
  index-time encode, ~10 ms/query encode. For a Claude Code *skill* meant to be
  `pip install`-light, dragging in `torch` is a real tax.
- **Benefit, and when it shows up:** on a *small* vault (≤ a few thousand chunks)
  the reranker (§5) sees most of the corpus anyway after a generous BM25 top-30,
  so dense recall adds little — BM25 + LLM-rerank already surfaces the
  paraphrase match because the reranker reads *meaning*. The dense lane only
  earns its keep when the vault is large enough that a paraphrased query's true
  answer falls *outside* the BM25 top-30 and thus never reaches the reranker.

**Verdict (no-overkill):** **default = BM25-only recall + LLM-rerank.** Ship the
local bi-encoder as an **opt-in lane** (`--neural-recall` / config
`embed_provider="bge-local"`) that activates automatically once the vault
exceeds ~**25k chunks** (the point where BM25 top-30 starts missing paraphrase
hits often enough to matter). Below that threshold the `torch` dep is pure
overkill — the LLM-rerank recovers the same wins by reading the BM25 candidates
semantically. The `EmbedProvider` seam already exists; adding a `BgeLocalEmbed`
provider is ~30 lines and changes nothing downstream (the fusion, blend, gate,
cache all consume vectors abstractly).

**Keyless reimplementation:** `BgeLocalEmbedProvider(name="bge-small-en-v1.5",
dim=384)` implementing the existing `EmbedProvider` Protocol; query prefix
`"Represent this sentence for searching relevant passages: "`, document prefix
none; `sentence_transformers.SentenceTransformer.encode(normalize_embeddings=True)`.
Fuse with BM25 via **RRF k=60** (§3.1 — two incomparable scales) when neural
recall is on. Cost: +2 GB install, +10 ms/op, +130 MB download. Quality: closes
the paraphrase-recall hole on large vaults; negligible benefit on small ones.

---

## §5. The rerank decision — THE central keyless tradeoff

This is where keyless quality is won or lost. The recall lane (BM25 ± dense)
produces top-30 candidates; reranking re-orders them by *true relevance to the
query*, and the three-tier blend (§3.3) trusts it heavily for ranks 4+. Three
keyless options; pick a default and an escalation.

### §5.1 Option A — FTS-only (no rerank). The floor.

Skip reranking entirely; sort by the min-max-normed BM25 (or RRF) score and feed
top_k straight to synthesis. **This is the quality floor and it is not good
enough** for the research-synthesis use case: BM25 over-ranks keyword-dense
chunks over explanatory ones (§2.2), and the whole reason NIA reranks the entire
top-30 (NIA §5.4: every candidate has `reranked:true`) is that re-ordering is
worth more than recall once you have 30 candidates. **Reject as the default.**
Keep it only as a `--no-rerank` speed/zero-token fallback.

### §5.2 Option B — local cross-encoder (`bge-reranker-v2-m3`). The offline escalation.

A cross-encoder reads `(query, doc)` *jointly* and emits one relevance score —
strictly more accurate than a bi-encoder because it attends across the pair.
Already wired in `rerank.py` as `BGEReranker` (FlagEmbedding `FlagReranker`, with
a `sentence-transformers CrossEncoder` fallback, sigmoid-normalized to [0,1]).

| Model | Disk | RAM | Latency (CPU, 30 pairs × ~500 tok) | Notes |
|---|---|---|---|---|
| `BAAI/bge-reranker-v2-m3` | ~560 MB | ~2.3 GB | **~3-8 s on CPU**, ~0.3 s on GPU | multilingual, strong; the `rerank.py` default |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~90 MB | ~120 MB | ~0.5-1.5 s on CPU | English-only, lighter, MS-MARCO-tuned |

**The catch:** `bge-reranker-v2-m3` on **CPU** is 3-8 s for 30 long chunks —
that's *slower than NIA's entire cold pipeline minus synthesis*, and it pulls
`torch` (~2 GB). `ms-marco-MiniLM-L-6-v2` is far lighter (~90 MB, sub-second) but
English-only (fine — our vault is English) and weaker on long mixed prose+code
chunks. So the realistic local cross-encoder for a keyless skill is
**`ms-marco-MiniLM-L-6-v2`**, not the heavyweight m3.

**Keyless reimplementation:** `BGEReranker(model="ms-marco-MiniLM-L-6-v2")` (the
`_default_bge_scorer` CrossEncoder path already sigmoid-normalizes logits to
[0,1] for parity with the blend). Cost: +90 MB, +`torch`, ~1 s/query. Quality:
solid, deterministic, **zero tokens**, **runs air-gapped**. This is the
escalation for offline/zero-token operation.

### §5.3 Option C — Claude-Code LLM-rerank. THE DEFAULT.

Use the host model that is *already running the skill* as a listwise/pointwise
reranker. Keyless (no API key — it's the Claude Code session model), costs only
tokens, and is a **more capable judge** than a 90-560 MB cross-encoder for our
domain because:

- It follows the *query intent* (a research question), not just lexical/semantic
  proximity. "Which note explains why they chose α=0.7?" — the LLM ranks the
  *explanatory* chunk over the one that merely mentions `alpha=0.7`. A
  cross-encoder trained on MS-MARCO web-passage relevance does not reliably make
  that distinction.
- It reads mixed prose+code natively (the cross-encoders are tuned on short web
  passages; our chunks are 2400-byte AST-headed or markdown-headed blocks).
- Zero new dependency, zero download, zero GPU, zero cold-start.

**The LLM-rerank prompt (production-ready, batched pointwise scoring):**

```text
SYSTEM:
You are a relevance reranker. Given a research QUERY and a numbered list of
candidate text CHUNKS, score each chunk's relevance to the query on a 0.0–1.0
scale. Relevance means: does this chunk contain information that directly helps
ANSWER or EXPLAIN the query — not merely mention its keywords.

Scoring rubric (be calibrated, use the full range):
  1.0  = directly and completely answers/explains the query
  0.7  = strongly relevant; contains a key part of the answer
  0.4  = tangentially relevant; mentions the topic but not the answer
  0.1  = same general domain, wrong specific subject
  0.0  = unrelated

Output ONLY a JSON array of objects, one per chunk, in input order:
[{"i": <chunk number>, "s": <score 0.0-1.0>}, ...]
No prose, no markdown fence, no explanation.

USER:
QUERY: {query}

CHUNKS:
[1] {chunk_1_text_truncated_to_~800_chars}
[2] {chunk_2_text_truncated_to_~800_chars}
...
[30] {chunk_30_text}
```

Parse the JSON, map `i → s`, feed `s` as `reranker_score` into
`three_tier_fuse(initial, reranker_score, rank)` exactly as Cohere's score was
fed. Implementation notes that make it robust:

- **Batch all 30 candidates in one call** (NIA reranks the full top-30). One
  call ≈ 30 × ~800 chars ≈ ~7-9k input tokens + ~600 output tokens. At Claude
  Code host pricing this is *one cheap call per query* — far less than the
  synthesis call that follows (NIA §5.5: synthesis is ~75% of latency/cost).
- **Truncate each chunk to ~800 chars for ranking** (the lead is the most
  signal; full chunk goes to synthesis later). Keeps the rerank call small.
- **Determinism:** request `temperature=0`. Pointwise (per-chunk score) is more
  stable than listwise (full re-order) because a malformed item degrades one
  score, not the whole ordering.
- **Failure handling:** if the JSON is malformed or a chunk index is missing,
  default that chunk's `reranker_score=0.0` (the three-tier blend then leans on
  `initial`, weighted 0.4-0.75 — graceful degradation, never a crash). If the
  *entire* call fails, fall back to Option A (BM25 order) for that query and log
  it. This mirrors `engine.py`'s `rer.get(rank0, 0.0)` default.
- **Token cost knob:** for very large candidate sets or tight budgets, do a
  **progressive cascade** (the Perplexity L1→L2→L3 shape, §7.2): cheap BM25/RRF
  pre-rank → LLM-rerank only the **top-12** (not all 30) → blend. This is the
  Perplexity "L1 fast scorers → L2 cross-encoder on survivors" idea made
  keyless: the LLM is the expensive L2/L3, so feed it fewer candidates.

**Keyless reimplementation:** a `ClaudeCodeReranker` implementing the existing
`Reranker` Protocol (`rerank(query, docs) -> [(idx, score)]`). It issues the
prompt above to the host model, parses JSON, returns `(idx, score)` desc — a
drop-in for `CohereReranker`/`BGEReranker` in `engine.py`. Cost: one ~8k-token
call/query (≈ a fraction of one synthesis call), no install, no GPU. Quality:
**highest** of the three for research-intent ranking; the only downside is
per-query token spend, which is already dwarfed by synthesis.

### §5.4 The rerank verdict

| | FTS-only | Local cross-encoder | Claude-Code LLM-rerank |
|---|---|---|---|
| Key required | no | no | no |
| New dependency | none | `torch` (~2 GB) + model | **none** |
| Download | 0 | 90-560 MB | 0 |
| Per-query cost | 0 | ~1-8 s CPU, 0 tokens | ~8k tokens, ~1-3 s |
| Air-gapped | yes | yes (after download) | **no (needs the session model)** |
| Intent-aware | no | partial | **yes** |
| Quality for research notes | floor | good | **best** |

**Default → Claude-Code LLM-rerank** (Option C). It's keyless, dependency-free,
intent-aware, and its token cost is negligible next to synthesis.
**Escalation → `ms-marco-MiniLM-L-6-v2` local cross-encoder** (Option B, the
light one — not m3) for air-gapped / zero-token operation, behind a
`reranker="local"` flag. **Floor → `--no-rerank`** (Option A) for max speed.
The `get_reranker()` factory in `rerank.py` already does provider selection;
extend it with the `claude-code` and `local` branches.

---

## §6. Semantic query cache — keyless at 0.92 (NIA §5.5, §4.3)

NIA's cache is its cost primitive: key a stored response on the *embedding of the
query string*, HIT at cosine ≥ 0.92, replay → 14.5× speedup (NIA §5.5 cold mean
20.8 s → warm 1.49 s). The defect (NIA §4.3): the embedder is negation-blind, so
`"X"` and `"NOT X in no_std"` embed at 0.9305 → wrong-answer cache HIT. The fix
NIA never shipped — a regex negation guard — we ship from day one.

Our `cache.py` already implements the full logic: 0.92-cosine over cached query
embeddings, negation guard via `NEGATION_PATTERN`, per-query `SemanticCache.get/put`.
The only keyless question is **what embeds the query string** (currently the
Cohere `EmbedProvider`). Two keyless answers, by tier:

### §6.1 Tier-1 keyless cache embedder — the local mini-embedder (if §4 ships it)

If the local bi-encoder lane (§4.3) is already loaded for recall, reuse it for
the cache key — collapsing NIA's two-embedder split (§4: separate `zembed-1`
recall + Cohere v3 cache) into **one local embedder for both lanes**. This is the
single-user simplification the dossier 04 §7.3 already flagged ("collapse NIA's
two-embedder split"). Cost: 0 marginal (model already resident). Quality: full
semantic cache, 0.92 threshold meaningful. Negation guard still mandatory —
`bge`/MiniLM are just as negation-blind as Cohere v3.

### §6.2 Tier-0 keyless cache (no model at all) — token-set similarity

When NO local embedder is shipped (the default small-vault config, §4.3), we
still want cache hits on token-reorder and suffix-noise (NIA's HIT cases:
"token reorder" 0.9701, "suffix noise +9 tokens" 0.9242) **without** an embedder.
Replace cosine-over-embeddings with a **lexical set similarity** over normalized
query tokens:

```python
def _normalize_tokens(q: str) -> frozenset[str]:
    # lowercase, strip punctuation, porter-stem-lite via the FTS splitter,
    # drop a tiny stopword set ({how,does,the,a,in,of,to,is,what,why})
    toks = preprocess_query(q).replace('"','').replace('*','').split()
    return frozenset(t for t in (w.lower() for w in toks) if t not in _STOP)

def token_sim(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b: return 0.0
    # weighted Jaccard, biased to recall (overlap / smaller set) so that
    # suffix-noise (b ⊃ a) still scores high — matches NIA's +9-token HIT.
    inter = len(a & b)
    return inter / min(len(a), len(b))      # overlap coefficient
```

- **Token reorder** → identical set → 1.0 → HIT (matches NIA 0.9701).
- **Suffix noise (+9 unrelated tokens)** → overlap coefficient ignores the extra
  set on the larger side → ~1.0 → HIT (matches NIA 0.9242 case).
- **Full paraphrase, zero lexical overlap** → ~0.0 → MISS. *This is the one NIA
  HIT case (0.9306, "anyhow" the only shared token) we lose without an embedder.*
  Acceptable: paraphrase cache misses just re-run the pipeline; the cost is a
  cache miss, not a wrong answer.
- **Negation guard still applies** (and is actually *more* robust here, because a
  negation word is a token-set difference, so token-sim already drops on negation
  even before the explicit guard fires — the guard is belt-and-suspenders).

Threshold: token-set similarity HIT at **≥ 0.85** (looser than the 0.92 cosine,
because lexical overlap is a coarser signal than embedding cosine; calibrate
against the vault). Store this as `SEMANTIC_CACHE_THRESHOLD_LEXICAL = 0.85`
alongside the existing `SEMANTIC_CACHE_THRESHOLD = 0.92`.

### §6.3 The cache verdict

**Default (no local model): Tier-0 token-set cache at 0.85** — keyless, zero
deps, catches reorder + suffix-noise (the common repeat-query shapes), misses
only true paraphrase (which just re-runs, never errs). **If the local embedder
is already shipped for recall: Tier-1 cosine cache at 0.92** — full semantic
hits, free ride on the resident model. Both keep the negation guard. The cache
is **single-user, not cross-tenant** — drop NIA's global cross-tenant pool (NIA
§5.5: a privacy footgun anyway) since there's one user.

**Keyless reimplementation:** `cache.py` is structured around an injected
embedder; add a `LexicalCacheBackend` that swaps cosine-over-embeddings for
`token_sim` and the threshold for 0.85, selected when `embed_provider is None`.
Everything else (negation guard, `query_cache` DDL, `put`/`get` flow) is
unchanged. Cost: ~0 (set ops over a small query-cache table). Quality: ~80% of
the embedding cache's hit rate at 0% of its dependency weight.

---

## §7. Orchestration — gate, re-retrieve, expand_symbols, progressive cascade

The control flow around the scorers (`engine.py`). All keyless — it's
orchestration, no model except the rerank call in §5.

### §7.1 The 0.70 relevance gate (KNOWN — Perplexity §4 "L3 ~0.7 threshold"; `RELEVANCE_GATE=0.70`)

After three-tier fusion + source-type weight, **drop any chunk with
`final_score < 0.70`**. Perplexity's progressive reranker ends with an "XGBoost
final, ~0.7 quality threshold." We keep the threshold, drop the XGBoost (that's
the model we can't have) — the gate is just a `>=` comparison on the
already-computed `final_score`. `engine.py` applies it in `_one_round`:
`if fused >= self.gate: survivors.append(...)`. Keyless, free.

### §7.2 The <30% re-retrieve failsafe (KNOWN — Perplexity §4; `RERETRIEVE_PASS_FRACTION=0.30`, `RERETRIEVE_MAX_ROUNDS=2`)

Perplexity §4: "Failsafe: if <30% pass, discard and re-retrieve." Compute
`pass_fraction = survivors / candidates`; if `< 0.30` and rounds remain, widen
and re-run. `engine.py` already does exactly this loop
(`for round_idx in range(1 + RERETRIEVE_MAX_ROUNDS): ... if pass_fraction >=
RERETRIEVE_PASS_FRACTION or last_round: break`). The widening step is
`expand_symbols` (§7.3). Keyless — it's a fraction comparison + a re-query.

### §7.3 `expand_symbols` → wiki-link/call-graph neighbor expansion (KNOWN — NIA §3.5, 04 §3.5)

NIA's `expand_symbols` (default off): extract function/class names from
first-pass results, issue a **second retrieval for their usage sites**, merge
(cAST-inspired call-graph widening). The vault's analogue is the **wiki-link
graph** (hyperresearch's `links` table — `backlinks`/`outlinks`), per dossier 04
§3.5: "after first-pass retrieval, pull the top hits' graph neighbors (notes they
link to / that link to them) as a second-pass candidate set, merge before
rerank." `engine.py` already does the chunk-neighbor version (pull same-`note_id`
neighbor chunks of the top note into `extra_ids`); the link-graph version is the
upgrade:

```python
# widening step inside the re-retrieve loop (engine._one_round caller):
neighbor_notes = backlinks(top_note) | outlinks(top_note)   # links table SQL
extra_ids |= {cid for cid,m in self._meta.items()
              if m.chunk.note_id in neighbor_notes}
# then re-fuse with these forced into the candidate set (vec_scores.setdefault(cid,0))
```

This is pure SQL over the existing `links` table + a set union — **no model,
keyless**, and it's the recall-widening lever that lets the <30%-pass failsafe
actually find new candidates instead of re-ranking the same 30. Cost: one SQL
query per re-retrieve round; only runs on the (rare) <30% path.

### §7.4 The progressive cascade — making LLM-rerank cheap (Perplexity §4 L1→L2→L3)

Perplexity reranks in cascade: L1 cheap lexical+embedding scorers → L2 expensive
cross-encoder on survivors → L3 final. Keyless mapping, **to cap token spend on
the LLM-rerank (§5.3)**:

- **L1 (free):** BM25 ± dense recall → RRF/α-fuse → top-30 by `initial_score`.
  This is the cheap pre-rank; no model.
- **L2 (cheap tokens):** LLM-rerank only the **top-12** of those 30 (not all 30)
  when token budget is tight — the bottom 18 rarely survive the 0.70 gate anyway
  (NIA §5.2 residual table: ranks 11+ already carry the deep-rank penalty). Cuts
  the rerank prompt from ~8k → ~3.5k input tokens.
- **L3 (free):** three-tier blend + gate on the L2 scores; the un-reranked 13-30
  keep `reranker_score=0.0` and fall to the tail via the 0.4 weight.

Default ships **L2 = full top-30** (matches NIA's "rerank the entire top-30",
quality-max); the **top-12 cascade** is the budget knob for token-constrained
runs. Either way it's the same `three_tier_fuse` math downstream.

---

## §8. The no-overkill verdict & wiring

### §8.1 Should we ship ANY local model? — the explicit no-overkill ruling

**No, not by default.** Reasoning, head-on:

- A 400-560 MB local cross-encoder (`bge-reranker-v2-m3`) or a 130 MB bi-encoder
  + the ~2 GB `torch` dep is a large tax on a `pip install` skill. It only pays
  off if it beats the alternative, and the alternative — **the Claude Code host
  model, already running, already paid for in the session** — is a *better*
  reranker for research-intent ranking (§5.3) at zero install cost.
- The local bi-encoder's only unique win (paraphrase recall, §4.3) is **recovered
  by the LLM-rerank** on small vaults, because a generous BM25 top-30 already
  contains the paraphrase match and the LLM reads it semantically. The bi-encoder
  only matters when the vault is big enough that the true answer falls outside the
  BM25 top-30 — i.e., above ~25k chunks.
- The semantic cache works keylessly without any model via token-set similarity
  (§6.2) at ~80% of the hit rate.

So: **default config has zero local model weights.** FTS5 (compiled into SQLite)
+ deterministic fusion math + Claude-Code LLM-rerank + token-set cache. The
`torch`/`sentence-transformers` deps go in an **optional extra**
(`pip install bad-research[local]`) and the models are lazy-downloaded only when
a user opts into `--neural-recall` or `--reranker local`. This is the
no-overkill line: ship the math and the host-model reranker; make the 400 MB
model a deliberate opt-in, never a default download.

### §8.2 Default vs escalation matrix

| Vault size / mode | Recall | Fuse | Rerank | Cache | Local model? |
|---|---|---|---|---|---|
| **Default (≤25k chunks)** | BM25 only | min-max BM25 → initial | **Claude-Code LLM-rerank (top-30)** | token-set 0.85 | **none** |
| Large vault (>25k) | BM25 + `bge-small` bi-encoder | **RRF k=60** | Claude-Code LLM-rerank | cosine 0.92 (reuse bi-encoder) | bge-small (130 MB) |
| Air-gapped / zero-token | BM25 (+ bi-encoder if installed) | RRF / α=0.7 | **`ms-marco-MiniLM-L-6-v2` cross-encoder** | token-set 0.85 | MiniLM (90 MB) |
| Max-quality offline | BM25 + bi-encoder | RRF | `bge-reranker-v2-m3` cross-encoder | cosine 0.92 | bge-small + bge-reranker (~700 MB) |
| Budget-token | BM25 | min-max | LLM-rerank **top-12 cascade** (§7.4) | token-set 0.85 | none |

### §8.3 Wiring into the existing code (minimal diff)

Everything downstream of the scorer is already built and keyless. The only new
code:

1. `embed/bge_local.py` — `BgeLocalEmbedProvider(EmbedProvider)` (dim 384,
   query prefix, normalized cosine). ~30 lines. Register in
   `get_embed_provider("bge-local")`.
2. `retrieval/rerank.py` — add `ClaudeCodeReranker(Reranker)` (the §5.3 prompt +
   JSON parse) and extend `get_reranker()` with `claude-code` (default) and
   `local`→`ms-marco-MiniLM-L-6-v2` branches. ~50 lines.
3. `retrieval/cache.py` — add `LexicalCacheBackend` (token-set sim, threshold
   0.85), selected when `embed_provider is None`. ~25 lines.
4. `retrieval/constants.py` — add `SEMANTIC_CACHE_THRESHOLD_LEXICAL = 0.85`,
   `NEURAL_RECALL_VAULT_THRESHOLD = 25_000`.
5. `retrieval/engine.py` — `expand_symbols` already does chunk-neighbor widening;
   upgrade the widening step to union wiki-link neighbors (§7.3) via the `links`
   table. ~10 lines. Everything else (`hybrid_fuse`, `three_tier_fuse`,
   `apply_source_type_weight`, the gate, the re-retrieve loop, RRF) is unchanged.

`pyproject.toml`: move `cohere`/`lancedb`/`sentence-transformers`/`torch`/
`FlagEmbedding` out of core deps into `[project.optional-dependencies] local`.
Core stays `pip`-light (SQLite-FTS + the host model do the work).

### §8.4 Calibration plan (keyless quality vs the upstream behavior)

We can't call NIA/Cohere, but we can self-calibrate the keyless stack:

- **Gate/threshold sweep:** build a tiny labeled set of (query → correct chunk)
  pairs from the vault; sweep `RELEVANCE_GATE` around 0.70 and the cache
  threshold around 0.85/0.92 to confirm the NIA-derived constants transfer.
- **Rerank A/B:** run the same 20 queries through (A) `--no-rerank`, (B) local
  MiniLM, (C) Claude-Code LLM-rerank; score nDCG@10 against the labels. Expect
  C ≥ B > A; if C ≈ B, the local model is confirmed overkill (the §8.1 thesis).
- **Three-tier blend regression:** unit-test `three_tier_fuse` against NIA's 18
  residual data points (NIA §5.2 table) — ranks 1-5 must reproduce to 1e-4
  (already the contract in `fusion.py`).
- **Cache hit-rate:** replay the NIA cache-mutation table (reorder / suffix /
  paraphrase / negation, NIA §5.5) through the token-set cache; assert HIT on
  reorder+suffix, MISS on paraphrase+negation.

---

## §9. Gaps & honest limits

- **Paraphrase cache misses (token-set tier).** Without a local embedder, the
  token-set cache (§6.2) misses true-paraphrase repeats (NIA's 0.9306 "anyhow"
  case). Consequence is a redundant pipeline run, never a wrong answer. Closed
  only by opting into the local embedder. Acceptable per no-overkill.
- **LLM-rerank determinism.** Even at `temperature=0`, the host model can drift
  run-to-run across model versions; scores are not bit-reproducible the way a
  cross-encoder's are. Mitigation: pointwise scoring (one bad item ≠ whole
  re-order), the 0.0-default on parse failure, and the three-tier blend's 0.4-0.75
  weight on the deterministic `initial` score anchoring the result.
- **LLM-rerank token cost on huge candidate sets.** Bounded by the top-12 cascade
  (§7.4); above that the cost is real but still << synthesis. Not a quality gap,
  a budget knob.
- **No cross-lingual.** Dropped on purpose (vault is English) — removes NIA's
  whole reason for a 2560-dim multilingual embedder. If the vault ever ingests
  non-English sources, revisit with `bge-m3` (multilingual) as the local lane.
- **Binary-quant lane unbuilt.** Exa's 1-bit ADC trick (§4.2) is specced but not
  shipped — unnecessary below ~500k chunks. Documented so it's a known lever, not
  a surprise.
- **`initial_score` saturation rule.** NIA clamps `initial_score=1.0` when all
  query tokens are present OR cosine > ~0.95 (NIA §5.1). Our min-max norm
  approximates this (the top BM25 hit normalizes to 1.0) but isn't identical;
  calibrate if the blend's top-tier diverges from NIA's residual table.
- **expand_symbols code extraction.** NIA extracts *function/class names* from
  results; our wiki-link version uses note links instead. For code chunks with
  AST headers (dossier 04 §3.1) we could also parse symbol names from the header
  and FTS-search them — a future upgrade, keyless (regex + FTS), unbuilt.
