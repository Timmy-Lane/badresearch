# Bad Research — Design Spec

> **michael jackson bad** — a deep-research agent that's *bad* (i.e. the best). A fork-and-enhance of
> [`hyperresearch`](https://github.com/jordan-gibbs/hyperresearch), still installed and driven as a
> **Claude Code skill**, rebuilt to be **better than hyperresearch**: no bullshit (it filters garbage
> sources/content), no hallucinations (every claim is grounded + verified), fast, with a great scraper
> pulling lots of sources — and **no overkill** (nothing that bloats context or price).

- **Date:** 2026-05-26
- **Status:** Approved design → ready for implementation plan.
- **Evidence base:** 11 investigation dossiers in `ultimate-research/investigation/` (01_FOUNDATION … 11_CORPUS_SWEEP, ~6,400 lines), themselves synthesized from the `teardowns/` + `core/` RE corpus. Every constant below traces to a dossier.
- **Package:** `bad-research` (import `bad_research`) · **CLI:** `bad` (alias `badr`) · **Skill:** `/bad-research` · **Tagline:** *"michael jackson bad"*.

---

## 0. Scope principle (read first)

**No MVP — launch-complete.** v1 IS the finished product: the full pipeline, the agentic fast-mode, agentic browse for hard pages, the quality + grounding pipelines, eval, docs, and tests all ship at launch.

**No overkill — the Excluded list (§10) is excluded because it bloats context/price for marginal gain, NOT because it's "later."** The dividing line is *enhances-per-cost*, not *phase*.

Three hard invariants the whole design rests on (**quality is the top priority — no shortcuts**):
1. **Disk is memory, context is scratchpad.** All inter-stage state lives on disk (vault + JSON artifacts + a TodoWrite program counter). The model's context only ever holds the current stage's working set. This is hyperresearch's context-rot defense (the V7→V8 lesson: a single 1,200-line prompt failed 100% of runs under compaction) and it is what makes "lots of sources" compatible with "no context bloat."
2. **Still a Claude Code skill.** The orchestrator IS Claude (via Claude Code: `Skill`/`Task`/`TodoWrite`/per-agent tool-allowlist). We do **not** build our own agent loop. We enhance (a) the deterministic Python backend the skill stages call, and (b) the skill prompts themselves.
3. **User-side / user-global by default, no server.** Everything lives in the user's space: the package via `pipx` (user install), the skill + agents + hooks in **`~/.claude/`** (user-global, not project-scoped), and the vault defaults to a user dir **`~/.bad-research/`** (overridable per-project). No backend service, no cloud component — it runs entirely client-side inside the user's Claude Code. A project-local install (`.claude/`, `./research/`) remains available as an opt-in for project-scoped research.

---

## 1. Settled decisions

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | Language / runtime | **Python core, `pip` + `pipx`** — fork hyperresearch in place | Reuses its vault/fetcher/providers/CLI verbatim; every target lib (crawl4ai, exa-py, tavily, cohere, browser-use, playwright) is Python-native; `pipx` = npx-style one-command. |
| 2 | Model provider | **Anthropic-first behind a thin `LLMProvider` seam** | Prompts are Claude-tuned (matches hyperresearch + our calibration); the seam lets other models drop in later without a rewrite. |
| 3 | Retrieval | **Perplexity × NIA hybrid** (BM25 + API-embedder vector + Cohere rerank + three-tier fusion + semantic cache) | Upgrades hyperresearch's FTS-only vault to neural+keyword; biggest single quality lift. |
| 4 | Distribution | **Enhanced Claude Code skill** (hyperresearch's model), `bad-research` package | "Bigger and better hyperresearch" — keep the host that already provides the orchestrator + tool-locks. |
| 5 | Embeddings | **One API embedder** (Cohere embed-v3 / Voyage / OpenAI) behind `EmbedProvider` | Self-hosted Qwen3 GPU doesn't amortize at single-user scale (idles 95%); API embeddings are $0-idle. |

---

## 2. Architecture overview

```
                          ┌─────────────────────────────────────────────┐
   user query  ──▶  /bad-research  (Claude Code skill: Claude = orchestrator)
                          │   loads ONE stage skill at a time (context-rot defense)
                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  PIPELINE (skill stages)   state on disk: research/ vault + *.json + Todo  │
   │                                                                            │
   │  0.5 Clarify+Plan-gate ─▶ Query-router ─▶ { agentic-fast | light | full }  │
   │                                                                            │
   │  full/light:  decompose ─▶ WIDTH-SWEEP(funnel) ─▶ contradiction-graph ─▶   │
   │   loci ─▶ depth ─▶ cross-locus ─▶ source-tensions ─▶ corpus-critic ─▶      │
   │   evidence-digest ─▶ triple-draft ─▶ synthesize ─▶ CITATION-VERIFIER(11.5) │
   │   ─▶ critics ─▶ gap-fetch ─▶ patcher ─▶ polish ─▶ readability ─▶ GATE(16)  │
   │                                                                            │
   │  agentic-fast:  bounded ReAct loop over the same providers+vault+retrieval │
   └──────────────────────────────────────────────────────────────────────────┘
        │ calls (deterministic Python, behind seams)
        ▼
   web/providers (search cascade) · browse/ (Tier 0→3) · retrieval/ (hybrid engine)
   quality/ (garbage filters) · grounding/ (verifier+gate) · llm/ · embed/ · core vault
```

The model never sees raw pages — only reranked top-chunks + `[[note-id]]` pointers (the scraper funnel, §6). Sources scale (45→80 notes) while context stays flat (~5–15k tokens).

---

## 3. Components (modules + responsibilities + seams)

All new code lives behind interfaces so the orchestrator/host and providers are swappable.

- **`llm/` — `LLMProvider` seam.** `complete(messages, model_tier, tools?, cache_control?) -> Response`. Default impl: Anthropic Messages API. Optional: LiteLLM. Model **tiers** (not hardcoded IDs): `triage`→Haiku, `work`→Sonnet, `heavy`→Opus; resolved via config (`--cheap` demotes `heavy`→`work`). KV-cache discipline: byte-identical system+tool prefixes per agent type so Anthropic prompt-cache hits (~10× input-cost cut, Manus pattern).
- **`embed/` — `EmbedProvider` seam.** `embed(texts, input_type=document|query) -> vectors`. Asymmetric doc/query embedding (NIA). API providers only (no GPU). Cohere `embed-v3` default.
- **`web/providers/` — `WebSearchProvider`** (extends hyperresearch's `WebProvider` Protocol; adds `search_ex(SearchQuery)`, `capabilities`, `cost_per_search`, `p50_ms`). Impls: `tavily`, `exa`, `sonar` (Perplexity), `searxng` (zero-key default), `firecrawl`. Plus the **search cascade** (§5).
- **`browse/` — `BrowseProvider` + `ExtractProvider`.** The **Tier 0→3 escalation ladder** hooked at `core/fetcher.fetch()`: Tier 0 HTTP → Tier 1 crawl4ai (JS) → Tier 2 typed extract (AgentQL AQL / Stagehand-extract / LLM-extract) → Tier 3 agentic browse (Browser-Use self-host default; Browserbase opt-in for anti-bot/login). Escalation triggered by `WebResult.looks_like_junk()`/`looks_like_login_wall()`.
- **`retrieval/` — the Perplexity×NIA hybrid engine** (§7). Replaces FTS-only `search/fts.py`; serves both vault search and the cascade's neural-rerank stage.
- **`quality/` — garbage filters** (§8): `seo_farm_score`, `DOMAIN_TIER`, dedup, relevance threshold.
- **`grounding/` — citation verifier + no-uncited-claim gate** (§9).
- **`core/`, `search/`, `mcp/`, `serve/`, `cli/`, `models/`, `skills/`** — hyperresearch base, enhanced. New skill files: `clarify`, `query-router`; modified: `width-sweep`, `depth-investigation`, `synthesize`, `citation`, `polish`.

---

## 4. Pipeline — kept + new stages

**Kept untouched (hyperresearch crown jewels):** skills-as-stages context-rot defense; disk-state-machine + crash-resume; `[Read,Edit]`/`[Read,Write]` tool-locks; triple-draft → synthesize → 4-critics → patcher loop; contradiction-graph + source-tensions + corpus-critic; MinHash/LSH dedup; lint gate; tier gate.

**New / modified for launch (`[+]`):**
- **`[+]` 0.5 Clarify + Plan-gate** — `triage`-tier clarifier (2-method `clarify | proceed`, default-proceed when non-interactive); editable plan (Gemini plan-gate). Skips for `agentic-fast`.
- **`[+]` Query router** — classifies the decompose output → `agentic-fast` (trivial/single-domain) | `light` | `full` (complex/contested/argumentative). Free (reuses decompose). Heuristic from DR-loops §9.
- **`[+]` agentic-fast mode** — a bounded ReAct loop (Perplexity engine: `max_steps ≤ 10`, many queries per step) over the same providers + retrieval + vault, for fast/cheap answers to simple queries. Full launch capability, not a stub.
- **Width-sweep → the scraper funnel (§6):** multi-provider fan-out → dedup → rank-before-read → read top-K (**≤80 ceiling**) → quality filter → chunk → vault. `[+]` `llms.txt`/`llms-full.txt` probe-first fetch tier for docs corpora (Mintlify).
- **Depth (5) / gap-fetch (13):** opt into Tier 2–3 browse per-source.
- **`[+]` 11.5 CitationVerifier (§9).**
- **`[+]` Fresh-context final review** — one bounded fresh-context reviewer pass before polish (catches issues the in-context critics miss; Anthropic/Devin pattern). Single pass, not a loop.
- **`[+]` 16 deterministic no-uncited-claim hard gate** + existing lint.

---

## 5. Web-search cascade

`SearchQuery{query, intent, recency, domains±, max_results}` → normalized `WebResult[]`.

- **Stage 0 — intent route:** `triage`-tier (or rules) picks lane: keyword / neural / deep.
- **Stage 1 — fast keyword:** parallel union of `tavily` (`search_depth`) + `sonar` (`search_mode` web/academic/sec) + `searxng` (zero-key) → dedup. (Seed queries only — not all providers on every query; that's quadratic for marginal recall.)
- **Stage 2 — neural rerank:** fires **only when Stage-1 results are thin** (<30% pass the 0.70 bar) — Exa neural + RRF (`k=60`) merge, reranked by the retrieval engine.
- **Stage 3 — deep extraction:** Firecrawl 19-step / Exa `contents` / crawl4ai, gated by the junk/login-wall checks.
- **Zero-key path:** SearXNG + crawl4ai + BM25 — strictly better than hyperresearch's current `NotImplementedError` search.

---

## 6. Scraper funnel (lots of sources, zero context bloat)

Six narrowing stages; **the model only ever sees the last stage's output.**
```
FAN-OUT (M queries × P providers × K results, parallel) → ~120–1200 raw hits
 → A DEDUP (URL-canonical + content-hash, free)            → candidates
 → B RANK un-read candidates (URL-utility-18 + RRF k=60)   → cheap→expensive gate
 → C READ top-K (batched, Tier 0→3 ladder, browse_page chained-crawl depth 2/5-links)
 → D FILTER junk + >60%-overlap redundancy (free)
 → E CHUNK + STORE in vault (disk/SQLite — NOT the prompt)
 → F RERANK chunks (cross-encoder, 0.70 thresh) → top-chunks the model sees
```
Fan-out constants are indexed by run mode — `light` / `full` / `full@max-effort` (the "deep" column is `full` run at maximum `reasoning_effort`, not a 4th mode; `agentic-fast` does not run the funnel — it does a bounded ReAct loop): `M_QUERIES` 12-20 / 40-100 / 100+; `P_PROVIDERS` 1-2 / 2-4 / 3-4; `READ_TOP_K` 12-20 / 60-80 / 80; read-concurrency 3-5 / 10-12; `TOP_CHUNKS` 8-15 / 10-30 / 20-40. **The ~80-read ceiling is load-bearing** — hyperresearch's own data shows reading past it degrades synthesis. Breadth pattern: many queries *per step* (Perplexity) + `browse_page`-style chained-crawl of next-best links (Grok).

---

## 7. Retrieval engine (Perplexity × NIA)

1. **Index:** AST-header-prepended chunking for code, semantic chunking for prose; embed via `EmbedProvider` (asymmetric doc/query); store vectors in **LanceDB** — embedded, no server, Rust-fast, RE'd in `teardowns/LANCEDB.md` (native HNSW + IVF_PQ ANN, flat-search fallback under 10% selectivity, and a built-in RRF reranker whose default `k=60` matches our cascade). hyperresearch's `embeddings` table is retired in favour of a LanceDB table; the tuned **FTS5/BM25 lane (weights 10/1/5/3) stays as the lexical half** — we fuse the two ourselves (§7.2–3) rather than delegating wholesale to LanceDB hybrid, to keep the `alpha=0.7` + three-tier algebra.
2. **Retrieve (hybrid):** fuse vector + BM25 at **`alpha=0.7`** → top-30; source-type boosts `{repo 1.2, docs 1.0, paper 0.9, hf 0.85}` (+ research-tuned `DOMAIN_TIER`); Sonar-style recency/domain filters.
3. **Progressive rerank:** L1 = hybrid score; **L2 = Cohere `rerank-v3.5`** (or local `bge-reranker-v2-m3` offline); three-tier fusion **`final = w·initial + (1−w)·reranker`, `w = {≤3:0.75, ≤10:0.60, >10:0.40}`**; **0.70** relevance bar + **<30%-pass → re-retrieve** (≤2 rounds) + `expand_symbols`-style follow-up re-query on top-hit entities.
4. **Semantic cache:** 0.92-cosine query-embedding cache (~20–25×) **with the negation-guard** (don't serve a hit when the new query adds a NOT/exclusion the cached one lacked — NIA's documented defect).

---

## 8. Quality / no-bullshit pipeline (cheap-before-expensive)

1. **Pre-fetch source filter** (~free, URL+snippet): canonical-URL collapse → blocklist → **`seo_farm_score ≥ 2`** regex classifier (the headline gap — hyperresearch only judges junk *after* download) → `DOMAIN_TIER` (primary 1.30 → seo 0.50) → query-conditional recency drop → engagement floor.
2. **Post-fetch content filter** (1 fetch): boilerplate/nav/footer strip → hyperresearch's verbatim `looks_like_login_wall` + `looks_like_junk` → paywall + language gates.
3. **Cross-source dedup:** shingle-3-gram Jaccard **0.60** (brute <200 / MinHash 128-perm + 16-band LSH ≥200).
4. **Relevance threshold:** drop chunks < **0.70**; <30%-pass → re-retrieve.
5. **Authority rank:** `reranker_score × DOMAIN_TIER`.
6. **Post-draft backstop** (full tier): corpus-critic + source-tensions.
Plus a **mandatory untrusted-content injection preamble** (Firecrawl-verbatim) on every page-touching LLM call.

---

## 9. Grounding / no-hallucination pipeline

- **Forward — binding at fetch:** every extracted claim is born with a verbatim `quoted_support` + char offsets; a claim with no locatable quote never enters the corpus. Anchors persisted in a new **`claim_anchors`** table (`quote_sha → {note_id, char_start, char_end, claim, quoted_support, verified, verify_score}`), rebuilt by `sync`. **DSS span extraction** (Glean): the extractor returns char-offset spans, not prose.
- **Forward — writer-sees-evidence:** the `[Read,Write]`-locked synthesizer writes only from `evidence-digest.md`, never the orchestrator's reasoning (Perplexity planner→writer split).
- **Backward — CitationVerifier (Stage 11.5):** per cited sentence, cheapest-first: **(A)** byte-identity (re-`find` + SHA, $0, kills fabricated quotes) → **(B)** NLI entailment via local **`nli-deberta-v3-base` ($0)**, with `triage`-tier LLM-judge fallback only for the ~10% NLI-neutral band (batched ~20/call) → **(C)** re-fetch arbitration, gated to contradicted+critical only. Disposition: supported→keep, partial→hedge, unsupported→drop cite, contradicted→into the contradiction-graph. Tool-locked `[Read]`.
- **Backward — Stage-16 gate:** deterministic ($0) ship-block if any non-trivial claim lacks a verifiable citation. Per-sentence single-index `[N]` citation render (Perplexity); no References section in prose; confidence kept off-band (not in prose).
- **Kept:** contradiction-graph + source-tensions + corpus-critic ("what source would overturn this?") — the strongest grounding scaffold of all five RE'd systems.

---

## 10. Cost / speed + the Excluded list

**Speed/cost mechanisms (all in scope):** model-tier routing (§3); KV-cache/prompt-cache discipline; parallel fan-out + parallel subagents (depth-1, default 3, Claude pattern); observation masking (JetBrains, 52% cost cut); the "fire-only-when-thin" cascade gate; semantic cache; the light/full/agentic router. **Budget:** `reasoning_effort` dial + a **`--budget-usd` meter that DOWNGRADES remaining stages rather than aborting** (cut order: redundant tool-calls → optional stages → model tier → tokens-last, per Claude's "tokens explain 80% of variance"). `cost-report.json` 5-component metering.

**Excluded — overkill (would bloat context/price for marginal gain), NOT deferred:**
self-hosted embedding/vector infra (Qwen3 GPU, Exa IVF index, TurboPuffer — don't amortize single-user); whole-pipeline ensembling (Grok N=16–32; multi-call judges tested *worse*); `memento` self-summarization (disk-state already prevents the rot); Daytona sandbox; OpenRouter gateway; a standalone non-skill orchestrator; Glean LambdaMART/PageRank authority (no click corpus/graph); answer-variant ensembles; always-on recency decay (buries foundational sources). Keep the *thresholds* these systems use; drop the *machinery*.

---

## 11. Data model (vault additions)

Keep hyperresearch's schema-v8 DDL. Add:
- **Vectors → LanceDB** (embedded Lance columnar store; replaces the dead `embeddings` table). Schema `{chunk_id, vector, dim, model, note_id, char_start, char_end}`; rebuilt from markdown by `sync`. Per `teardowns/LANCEDB.md`: HNSW (deterministic build) + IVF_PQ, flat-search fallback under ~10% prefilter selectivity, fragment-id row addressing, RRF reranker `k=60`. SQLite remains the metadata/FTS5 + relational store (below).
- **`claim_anchors`** — §9 (`anchor_id = quote_sha`).
- **`sources`** — provenance/dedup (16-char SHA-256 hash, `fetch_provider`, `tier`, `fetched_at`, dual-temporal `{documentDate, eventDate}` for recency).
Markdown stays truth; SQLite is cache (rebuildable by `sync` via the 16-byte frontmatter probe + mtime + SHA-256). Stable chunk IDs `sha1(url#heading)` + Merkle incremental re-index (Cursor/Mintlify).

---

## 12. Packaging, install, config

- **User-global by default** (invariant #3): `pipx install bad-research` (user-side, isolated) → `bad install` drops the enhanced skills/agents/PreToolUse hook into **`~/.claude/skills/bad-research/`**, **`~/.claude/agents/`**, and **`~/.claude/settings.json`**. The 16+ stage step-skills lazy-install on first `/bad-research` invocation (hyperresearch's `--global` pattern, made default) to avoid system-reminder bloat. CLI `bad` / `badr`; skill `/bad-research`. Vault defaults to **`~/.bad-research/`** (`<vault>/research/` + `<vault>/.bad-research/` index dir). `bad install --project` opts into project-local `.claude/` + `./research/` instead. No server is ever started.
- **Keys all optional**, graceful degradation: `ANTHROPIC_API_KEY` (orchestrator, via host); `TAVILY/EXA/PPLX/FIRECRAWL/COHERE/BROWSERBASE/AGENTQL` enable their providers; none → SearXNG + crawl4ai + BM25 + Browser-Use self-host still works. Keys read from env or `~/.config/bad-research/config.toml` (user-side).
- Config dataclass extends hyperresearch's: provider keys, model-tier map, fan-out tier constants, budget caps, thresholds.

---

## 13. Error handling & resilience

- **Crash-resume:** the disk-state-machine resumes from the highest completed artifact (kept from hyperresearch).
- **Provider failover:** cascade ladder + per-provider retry/backoff; a dead provider degrades to the next.
- **Budget exhaustion:** downgrade, never abort (§10).
- **Empty/thin results:** the <30%-pass re-retrieve failsafe; if still thin, the report states the gap honestly (negative provenance, DeepWiki) rather than hallucinating.
- **Tool-lock enforcement:** patcher/polish/verifier physically can't `Write` (Claude Code allowlist).

---

## 14. Testing & calibration

- **Unit:** each seam (LLM/embed/search/browse/retrieval/quality/grounding) tested in isolation against fixtures; reuse hyperresearch's test layout.
- **Retrieval eval:** a small labeled set; measure recall@k and rerank lift vs BM25-only baseline.
- **Grounding eval:** an injected-unsupported-claim set → the verifier must drop them (target ≥95% recall on the injected set); the Stage-16 gate must catch 100% of uncited claims (deterministic, so this is a hard pass/fail).
- **End-to-end:** ~20-query research set (DR-loops eval-set size); offline LLM-as-judge 5-axis rubric (factual/citation/completeness/source-quality/efficiency) for **calibration only** (not an always-on per-run gate — that's the Excluded ensembling cost).
- **Calibration target:** compare a `bad-research` report against hyperresearch and against Perplexity/Grok deep-research output on the same query; iterate prompts to close the gap.

---

## 15. Open questions / risks

1. **Vector store:** ~~sqlite-vec vs LanceDB~~ **RESOLVED → LanceDB** (we have deep RE in `teardowns/LANCEDB.md`; embedded/no-server, native ANN + RRF `k=60` reranker, scales past sqlite-vec's brute-force). Still rebuildable-from-markdown, so the "disk is truth, store is cache" invariant holds. sqlite-vec rejected: no built-in hybrid/rerank, weaker ANN.
2. **Reranker default:** Cohere `rerank-v3.5` (API, best) vs local `bge-reranker-v2-m3` (offline, $0). Ship Cohere default + local fallback.
3. **agentic-fast vs light overlap:** confirm the router heuristic boundaries during calibration.
4. **Browserbase cost:** opt-in only; confirm Browser-Use self-host covers most Tier-3 needs so anti-bot is rare.
5. **Repo home:** lives in gitignored `ultimate-research/`; gets its own public repo at publish time (so the joke tagline + MIT license ship cleanly, separate from the RE repo).
