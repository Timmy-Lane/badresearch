# Bad Research — KR-7 Keyless Calibration Plan

> The offline `StubJudge` path is the tested, zero-key path (CI). This doc is the
> plan for the LIVE measurement pass — what to measure, against what keyless
> reference, with what metric. The judge (`LLMJudge`) runs against the Claude Code
> host model; calibration is never a per-run gate (SPEC §10 Excluded).

## What we measure (keyless references only)

| Target seam | Reference (keyless / one-time read-only) | Metric | Source |
|---|---|---|---|
| `web/content.fetch_clean` (URL→markdown) | a one-time, read-only fetch via a free public reader (no key, manual, not in CI) | markdown fidelity: % of body text retained vs the raw article; boilerplate-strip precision | dossier 12 §11 |
| keyless search (host WebSearch + ddgs + verticals, RRF k=60) | the offline 20-query calibration set scored by the 5-axis judge | pass-rate @ relevance gate 0.70; mean overall | dossier 13 §7.2 |
| rerank A/B | host-model `ClaudeCodeReranker` vs `[local]` ms-marco-MiniLM vs `none` (identity) | nDCG@10 on the calibration set's labelled relevances | dossier 15 §8.4 |
| grounding | injected-claim recall: seed the corpus with a known-false claim, confirm the gate flags it | injected-claim recall ≥ target; false-anchor rate | dossier 16 §2 / harness deferred items |

## How it runs

`bad calibrate <query>` (live path, ANTHROPIC_API_KEY set for the HEADLESS model):
1. `pipeline.run_query` drives the keyless backend (host WebSearch + ddgs + crawl4ai
   + FTS5/BM25 + host-model LLM-rerank). No third-party key.
2. `LLMJudge` (single strong-model call, 5-axis rubric, temp 0) scores the report.
3. The only baseline is the keyless `hyperresearch` structural comparator (when
   importable). The keyed deep-research baselines (Perplexity/Grok) are REMOVED —
   they need third-party keys, which the keyless rule forbids.
4. Writes `calibration-report.{json,md}`.

## Verified (KR-7 Task 10, base-only fresh install, 2026-05-27)

- `bad --version` → `bad-research v0.1.0` (keyless)
- `bad doctor` → keyless banner + provider rows + external-CLI block, exit 0, no key error
  (run with a fully empty environment via `env -i`, no ANTHROPIC_API_KEY)
- `bad calibrate "does X cause Y?" --offline` → both report files written, exit 0, zero keys
  (overall 0.850 PASS, cost $0.5100 from the deterministic stub runner)
- Fresh base venv: cohere/tavily/exa/firecrawl/browserbase/agentql/browser-use/torch/lancedb/
  sentence-transformers all NOT importable (lean base confirmed). crawl4ai pulls playwright
  transitively (its own dep, keyless) — that is the only "heavy" transitive in base.
- Built wheel `bad_research-0.1.0-py3-none-any.whl`; `Requires-Dist` carries the 23 keyless
  base deps and zero keyed provider.
