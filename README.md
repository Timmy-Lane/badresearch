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

Bad Research is a small CLI that registers itself as a Claude Code skill. No API keys. Requires Python 3.11–3.13.

```bash
# Download + install the CLI (pipx or uv — either works)
pipx install git+https://github.com/LeventySeven/badresearch.git
uv tool install git+https://github.com/LeventySeven/badresearch.git

# Register the /bad-research skill into ~/.claude
bad install

# Verify
bad doctor
```

`bad install` writes the entry skill to `~/.claude/skills/bad-research/`; the per-step
skills install lazily on first use. For a project-local install instead of global, run
`bad install --project` inside the project. `bad doctor` shows what's wired (host model,
keyless search/browse, the optional external CLIs it can drive, the `[local]` neural stack).

## Use it in Claude Code

After `bad install`, open Claude Code in any project and either:

- **Invoke it directly** — type the slash command with your question:
  ```
  /bad-research Is open-source AI more dangerous than closed-source for national security?
  ```
- **Let Claude trigger it** — just ask a research-shaped question (*"write me a cited report
  comparing vector databases"*, *"literature review on GLP-1 drugs"*) and Claude loads the
  skill automatically.

It scales to the question: a simple lookup gets a fast cited answer in minutes; a broad or
contested one runs the full adversarially-reviewed pipeline (~1.5–2.5 h). The final report
and every fetched source land in a vault under `./research/` that compounds across sessions.

> Not yet on PyPI — install from GitHub as above. (Once published, `pipx install bad-research` will also work.)

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
[**docs/HOW_IT_WORKS.md**](docs/HOW_IT_WORKS.md).

MIT licensed.
