<p align="center">
  <img src="assets/banner.png" alt="BAD — michael jackson bad" width="520">
</p>

<h1 align="center">Bad Research</h1>

<p align="center"><em>michael jackson bad</em></p>

A **keyless** deep-research agent that runs as a Claude Code skill — a
fork-and-enhance of [hyperresearch](https://github.com/jordan-gibbs/hyperresearch).
It searches wide, filters garbage, grounds every claim to a source, and needs
**zero API keys**: the Claude Code host model supplies all inference, exactly like
hyperresearch. Optional local CLIs and a `[local]` neural extra are enhancements,
never requirements.

## Install

```bash
pipx install bad-research        # or: pip install bad-research
bad doctor                       # keyless capability report — no key needed
```

`bad install` registers the `/bad-research` skill into `~/.claude/`. Run
`bad doctor` any time to see what's wired (host model, keyless search/browse, the
optional external CLIs it can drive, and whether the `[local]` neural stack is present).

## What it does

A tier-adaptive pipeline turns a question into an audited, fully-cited report, and
every fetched source lands in a persistent, searchable vault that compounds across
sessions. Keyless by design:

- **Search** — the host `WebSearch` tool + DuckDuckGo + 7 scholarly APIs, fused and reranked by the host model.
- **Content** — a native fetch-and-clean pipeline (readability → markdown → optional LLM clean), SSRF-guarded.
- **Browse** — an agentic observe → act → extract loop driven by a local, keyless headless browser.
- **Retrieve** — SQLite FTS5/BM25 by default (no model required), with an optional local neural lane.
- **Ground** — every report sentence is checked against its source; uncited claims are blocked.

## How it works & where the patterns came from

Bad Research takes hyperresearch as its base and enhances each stage with patterns
drawn from the best deep-research systems — Perplexity, Gemini, Firecrawl, Stagehand,
AgentQL, and others — reimplemented to run **keyless** on the host model. The full
write-up, stage by stage with provenance, is in
[**docs/HOW_IT_WORKS.md**](docs/HOW_IT_WORKS.md). The design spec is in
[`docs/SPEC.md`](docs/SPEC.md).

MIT licensed.
