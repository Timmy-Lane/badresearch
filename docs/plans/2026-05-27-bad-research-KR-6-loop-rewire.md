# Bad Research — KR-6: Loop Levers + Rewire — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 5 net-new keyless loop levers (grader loop, 7-field delegation contract + per-subagent caps, recitation gate, reasoning-effort continuum + token ceiling, confidence-band hedging) and rewire the funnel / pipeline / skill stages to call the KR-2..5 keyless seams (`web/search`, `web/content/fetch_clean`, `browse/AgentBrowserProvider`, FTS-default `RetrievalEngine` + `ClaudeCodeReranker`) instead of the removed paid-provider seams.

**Architecture:** KR-6 is the integration plan: it sits on top of KR-1..5's keyless seams. The loop levers are prompt schemas (skill `.md` edits), frozen constants (`routing_constants.py`), and deterministic Python the host runs (`quality/grader.py` wrapping `calibrate/judge.py::LLMJudge`; `quality/recitation.py`; a `confidence_band` field on `grounding/verifier.py`; an `--effort`→tier/fan-out map in `skills/router.py`). The rewire is confined to the `cli/research.py` builders — because `pipeline.run_query`'s `_gather`/`_retrieve` already delegate to those builders and the funnel takes its providers/fetcher via `FunnelDeps`, swapping the builders rewires the whole pipeline with zero shape change. No removed-provider import (`cohere`/`tavily`/`exa`/`firecrawl`/`browserbase`/`agentql`/`browser-use`/`sonar`) survives.

**Tech Stack:** Python 3.11+, `uv`, pytest (+ FakeLLM stubs, no network), typer CLI, Claude Code skill `.md` prompt files validated by `tests/test_skills/validate.py`.

---

## Preconditions (KR-1..5 must be merged first)

This plan **calls** seams that KR-1..5 create. Before starting, verify they exist (each is a one-line import smoke check):

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
uv run python - <<'PY'
import importlib
# KR-2 search
from bad_research.web.search.base import WebSearchToolProvider, DdgsProvider  # noqa
# KR-3 content
from bad_research.web.content.fetch_clean import fetch_clean  # noqa
# KR-4 browse
from bad_research.browse.base import get_browse_provider  # noqa
from bad_research.browse.agent_browser import AgentBrowserProvider  # noqa
# KR-5 retrieval
from bad_research.retrieval.rerank import ClaudeCodeReranker, get_reranker  # noqa
from bad_research.retrieval.engine import RetrievalEngine  # noqa
# KR-1 config knobs
from bad_research.config import BadResearchConfig
c = BadResearchConfig()
assert hasattr(c, "reranker"), "KR-1 config.reranker missing"
assert hasattr(c, "neural_recall"), "KR-1 config.neural_recall missing"
assert hasattr(c, "effort"), "KR-1 config.effort missing"
assert hasattr(c, "max_tokens"), "KR-1 config.max_tokens missing"
print("KR-1..5 seams present — KR-6 may proceed")
PY
```

If any import fails, STOP — the dependency plan is not merged. Do not stub the missing seam in KR-6.

**Branch + commit discipline.** Work on `main` (the repo's keyless rebuild branch). Commit after each task. Every commit message ends with:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Run the whole suite with `export PATH="$HOME/.local/bin:$PATH"; uv run python -m pytest`. Run a single test with `uv run python -m pytest <path>::<name> -v`.

---

## File Structure

**New source files (Python):**
- `src/bad_research/quality/grader.py` — wraps `LLMJudge` to emit patcher-shaped `Finding`s; the in-pipeline grader (single host-model call per round). Responsibility: judge→findings translation only; the loop counter lives in the skill.
- `src/bad_research/quality/recitation.py` — deterministic 12-gram / 0.50-overlap verbatim-copy gate. Responsibility: pure string ops, $0, returns `Finding`s.

**New source files (skill prompts):**
- `src/bad_research/skills/bad-research-12.5-grader.md` — full-tier grader loop stage (judge→patch→re-judge, cap 3).

**Modified source files (Python):**
- `src/bad_research/skills/routing_constants.py` — add the 5 cap/grader constants + the effort→fan-out table.
- `src/bad_research/skills/router.py` — add `effort_overrides(effort)` (the minimal/low/medium/high continuum) and `degrade_order()`.
- `src/bad_research/grounding/verifier.py` — add `confidence_band()` + emit `confidence_band` on `CitationFinding`.
- `src/bad_research/cli/research.py` — rewire `_build_providers` / `_build_tiered_fetcher` / `_build_embedder` / `_build_reranker` to the keyless seams; plumb `--reasoning-effort` + add `--max-tokens` to `funnel_gather_cmd`; add `grade_report_cmd` + `recitation_gate_cmd`.
- `src/bad_research/cli/__init__.py` — register the two new CLI commands (`grade-report`, `recitation-gate`).

**Modified source files (skill prompts):**
- `src/bad_research/skills/bad-research.md` — extend the spawn contract from 3 to 7 fields; add Stage 12.5 to the full-tier sequence + the recovery artifact map + the degrade-order invariant.
- `src/bad_research/skills/bad-research-2-width-sweep.md` — add `objective`/`output_shape`/`tools_allowed`/`stop_conditions` to the fetcher spawn template.
- `src/bad_research/skills/bad-research-5-depth-investigation.md` — same 4 fields on the investigator spawn template.
- `src/bad_research/skills/bad-research-14-patcher.md` — add the confidence-band hedge rule to the patcher's job + consume `critic-findings-grader.json`.
- `src/bad_research/skills/bad-research-16-readability-audit.md` — add the recitation gate (`bad recitation-gate`) beside the no-uncited gate.

**New test files:**
- `tests/test_quality/test_grader.py`
- `tests/test_quality/test_recitation.py`
- `tests/test_skills/test_grader_skill.py`
- `tests/test_grounding/test_confidence_band.py`
- `tests/test_skills/test_router_effort.py` (lives under test_skills next to router tests; tests `skills/router.py`)
- `tests/test_cli/test_keyless_rewire.py`
- `tests/test_skills/test_delegation_contract.py`

**Modified test files:**
- `tests/test_skills/test_modified_stages.py` — extend with the 12.5 / patcher / step-16 recitation assertions.

---

## Task 1: Frozen loop constants in `routing_constants.py`

**Files:**
- Modify: `src/bad_research/skills/routing_constants.py`
- Test: `tests/test_skills/test_router_effort.py` (constants portion)

- [ ] **Step 1: Write the failing test**

Create `tests/test_skills/test_router_effort.py`:

```python
"""KR-6 — routing_constants loop caps + the effort continuum."""
from __future__ import annotations

from bad_research.skills import routing_constants as R


def test_grader_and_cap_constants_present_and_frozen():
    # dossier 16 §3.2 / §4.1 / INTERFACES_KEYLESS §8 frozen table
    assert R.MAX_GRADER_REVISIONS == 3
    assert R.FETCHER_TOOLCALL_CAP == {"light": 10, "full": 20}
    assert R.FETCHER_TIMEOUT_S == 300
    assert R.INVESTIGATOR_TIMEOUT_S == 900
    assert R.SUBAGENT_SOURCE_KILL == 100


def test_effort_levels_are_the_openai_four():
    assert R.EFFORT_LEVELS == ("minimal", "low", "medium", "high")
    # every level maps to a route + a fetcher fan-out cap (dossier 16 §6.1)
    for lvl in R.EFFORT_LEVELS:
        assert lvl in R.EFFORT_MAP
        row = R.EFFORT_MAP[lvl]
        assert row["route"] in ("light", "full")
        assert isinstance(row["fetchers_max"], int)
        assert isinstance(row["loci_max"], int)
        assert row["tier"] in ("triage", "work", "heavy", "default")


def test_effort_monotonic_fanout():
    # minimal <= low <= medium <= high on fetcher width (the cost knob)
    widths = [R.EFFORT_MAP[l]["fetchers_max"] for l in R.EFFORT_LEVELS]
    assert widths == sorted(widths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_skills/test_router_effort.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'MAX_GRADER_REVISIONS'`

- [ ] **Step 3: Add the constants**

Append to `src/bad_research/skills/routing_constants.py` (after the existing `ROUTER_LIGHT_MAX_ATOMIC` line):

```python

# ── KR-6 loop levers (dossier 16; INTERFACES_KEYLESS §8 frozen table) ─────────

# Grader loop — judge -> patch -> re-judge, capped (patch-not-regenerate => 3 is
# enough; NOT Claude's 20 which assumes full regeneration). dossier 16 §4.1.
MAX_GRADER_REVISIONS = 3

# Per-subagent runtime caps (Claude CE.5), keyless host guards. dossier 16 §3.2.
FETCHER_TOOLCALL_CAP = {"light": 10, "full": 20}  # tool calls per fetcher
FETCHER_TIMEOUT_S = 300       # soft-fail, return partial findings
INVESTIGATOR_TIMEOUT_S = 900  # depth stage scaled (Grok 200s x cost)
SUBAGENT_SOURCE_KILL = 100    # hard stop on sources touched (Claude)

# Reasoning-effort continuum — OpenAI's 4-level dial (dossier 16 §6.1) mapped onto
# the existing route + LLM-tier + per-stage fan-out levers. Wiring the stub
# --reasoning-effort flag (research.py) into a real config the router consumes.
EFFORT_LEVELS = ("minimal", "low", "medium", "high")
EFFORT_MAP = {
    "minimal": {"route": "light", "tier": "triage", "fetchers_max": 4,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "low":     {"route": "light", "tier": "work",   "fetchers_max": 8,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "medium":  {"route": "full",  "tier": "default", "fetchers_max": 12, "loci_max": 4,
                "extended_thinking": True,  "single_draft": False},
    "high":    {"route": "full",  "tier": "heavy",  "fetchers_max": 12, "loci_max": 6,
                "extended_thinking": True,  "single_draft": False},
}

# Token-ceiling degrade order (Claude §12: cut tokens LAST). dossier 16 §6.2.
# Each step names what the orchestrator drops first when approaching --max-tokens.
DEGRADE_ORDER = (
    "tool-call-redundancy",   # 1. skip the redundancy-audit sub-step
    "fan-out-width",          # 2. fewer fetchers / fewer loci
    "model-tier",             # 3. heavy -> light on non-critical stages
    # NEVER cut synthesis/grounding token budget — the 80%-variance core.
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_skills/test_router_effort.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/routing_constants.py tests/test_skills/test_router_effort.py
git commit -m "feat(kr6): freeze grader/cap/effort loop constants in routing_constants

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Effort continuum + degrade order in `router.py`

**Files:**
- Modify: `src/bad_research/skills/router.py`
- Test: `tests/test_skills/test_router_effort.py` (router portion)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills/test_router_effort.py`:

```python
from bad_research.skills.router import classify_route, degrade_order, effort_overrides


def test_effort_overrides_minimal_forces_light_single_draft():
    ov = effort_overrides("minimal")
    assert ov["route"] == "light"
    assert ov["fetchers_max"] == 4
    assert ov["single_draft"] is True


def test_effort_overrides_high_forces_full_opus():
    ov = effort_overrides("high")
    assert ov["route"] == "full"
    assert ov["tier"] == "heavy"
    assert ov["fetchers_max"] == 12
    assert ov["loci_max"] == 6


def test_effort_overrides_unknown_returns_none():
    # an absent/invalid --effort leaves the auto-route untouched
    assert effort_overrides(None) is None
    assert effort_overrides("turbo") is None


def test_effort_can_downgrade_full_to_light():
    # auto-classify would say full (7 atomic items), but --effort minimal pins light
    decomp = {"sub_questions": list(range(7)), "entities": [], "domains": ["x"],
              "response_format": "structured"}
    assert classify_route(decomp) == "full"
    ov = effort_overrides("minimal")
    assert ov["route"] == "light"  # the override is the user's explicit floor/ceiling


def test_degrade_order_is_tokens_last():
    order = degrade_order()
    assert order[0] == "tool-call-redundancy"
    assert order[-1] == "model-tier"  # tokens/synthesis never appear — cut last (never)
    assert "synthesis" not in order and "grounding-tokens" not in order
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_skills/test_router_effort.py -k "effort_overrides or degrade_order or downgrade" -v`
Expected: FAIL with `ImportError: cannot import name 'effort_overrides'`

- [ ] **Step 3: Add the two functions to `router.py`**

Append to `src/bad_research/skills/router.py` (after `route_reason`):

```python

def effort_overrides(effort: str | None) -> dict | None:
    """Translate the `--reasoning-effort` dial (minimal/low/medium/high) into the
    router overrides the orchestrator applies on top of the auto-classified route.

    Returns None for an absent/invalid effort (the auto-route is left untouched).
    The returned dict pins {route, tier, fetchers_max, loci_max, extended_thinking,
    single_draft} — OpenAI's 4-level continuum expressed as a host-side config
    (dossier 16 §6.1). This is the wiring for the stub flag in cli/research.py.
    """
    if effort not in R.EFFORT_MAP:
        return None
    return dict(R.EFFORT_MAP[effort])


def degrade_order() -> tuple[str, ...]:
    """The Claude token-ceiling degrade order (dossier 16 §6.2): cut tool-call
    redundancy, then fan-out width, then model tier — NEVER the synthesis/grounding
    token budget (the 80%-variance core). The orchestrator walks this list when a
    run approaches its --max-tokens ceiling."""
    return R.DEGRADE_ORDER
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_skills/test_router_effort.py -v`
Expected: PASS (all 8 tests in the file)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/skills/router.py tests/test_skills/test_router_effort.py
git commit -m "feat(kr6): effort continuum + token-ceiling degrade order in router

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `quality/recitation.py` — the verbatim-overlap gate

**Files:**
- Create: `src/bad_research/quality/recitation.py`
- Test: `tests/test_quality/test_recitation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_quality/test_recitation.py`:

```python
"""KR-6 — deterministic recitation (verbatim-copy) gate. dossier 16 §5."""
from __future__ import annotations

from bad_research.quality.recitation import (
    RECITATION_MAX_NGRAM,
    RECITATION_MAX_OVERLAP,
    longest_common_contiguous_run,
    recitation_findings,
)


def test_constants_frozen():
    assert RECITATION_MAX_NGRAM == 12
    assert RECITATION_MAX_OVERLAP == 0.50


def test_lcs_run_finds_the_longest_contiguous_word_run():
    a = "the quick brown fox jumps over the lazy dog".split()
    b = "a quick brown fox jumps over the river".split()
    run = longest_common_contiguous_run(a, b)
    assert run == ["quick", "brown", "fox", "jumps", "over", "the"]


def test_long_verbatim_run_flags_recitation():
    # a 13-word verbatim lift (> RECITATION_MAX_NGRAM=12) from the source body
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = ("Transformers replace recurrence with self attention allowing the model to "
              "weigh every token against every other token in parallel during training [1].")
    findings = recitation_findings(report, {"note-1": src})
    assert len(findings) == 1
    f = findings[0]
    assert f.failure_mode == "recitation"
    assert f.severity == "major"  # quality smell, NOT a ship-block (unlike uncited)


def test_paraphrase_does_not_flag():
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = ("Instead of recurrent steps, transformers use attention so each token is "
              "compared with all others at once [1].")
    assert recitation_findings(report, {"note-1": src}) == []


def test_high_overlap_short_sentence_flags():
    # short sentence whose run is > 50% of its tokens (even if < 12 words)
    src = "Quantum supremacy was claimed by Google in two thousand nineteen exactly."
    report = "Quantum supremacy was claimed by Google [1]."  # 6/6 prose words verbatim
    findings = recitation_findings(report, {"note-1": src})
    assert len(findings) == 1


def test_explicit_quotation_with_adjacent_cite_is_exempt():
    # Gemini's carve-out: a sentence whose verbatim run sits inside "..." + [N] is fine.
    src = "The author wrote that the result was completely unexpected and frankly impossible."
    report = '"the result was completely unexpected and frankly impossible" the author wrote [1].'
    assert recitation_findings(report, {"note-1": src}) == []


def test_sources_section_excluded():
    src = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi."
    report = ("# Title\n\nA short paraphrase here [1].\n\n## Sources\n"
              "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi.\n")
    # the verbatim run is in the Sources block -> ignored
    assert recitation_findings(report, {"note-1": src}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_quality/test_recitation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.quality.recitation'`

- [ ] **Step 3: Write the implementation**

Create `src/bad_research/quality/recitation.py`:

```python
"""Stage-16 recitation gate — RECITATION's *output* guarantee (Gemini §R3.9)
without its decoder machinery. Deterministic, $0, no LLM. Flags any report
sentence that reproduces a cited note's body too closely (a long verbatim run
or >50% of the sentence lifted contiguously). A `major` finding routes to the
patcher to paraphrase — it does NOT block ship (copying is a quality/legal smell,
not a correctness failure). dossier 16 §5."""

from __future__ import annotations

import re

from bad_research.grounding.gate import Finding, split_sentences, strip_sources_section

# dossier 16 §5.1 — IDEA defaults; tune on real reports (dossier §11 honest gap).
RECITATION_MAX_NGRAM = 12     # a verbatim run > 12 words = copying
RECITATION_MAX_OVERLAP = 0.50  # >50% of a sentence's tokens are one contiguous source run

_WORD = re.compile(r"[\w']+", re.UNICODE)
_CITE_TOKEN = re.compile(r"\[\[[^\]]+\]\]|\[\d+\]")
# A run that lives inside an explicit "..." quotation adjacent to a [N] is exempt
# (Gemini's public-domain / direct-quote-with-attribution carve-out, dossier §5.1).
_QUOTED_WITH_CITE = re.compile(r'"[^"]+"\s*(?:\[\[[^\]]+\]\]|\[\d+\])')


def words(text: str) -> list[str]:
    """Lowercased word tokens with citation markup stripped."""
    return _WORD.findall(_CITE_TOKEN.sub("", text).lower())


def longest_common_contiguous_run(a: list[str], b: list[str]) -> list[str]:
    """The longest run of words that appears contiguously in BOTH sequences
    (word-level longest-common-substring via the classic DP table). Cheap over
    the small per-run corpus — not a character suffix-array."""
    if not a or not b:
        return []
    # prev/cur rows of the LCS-substring DP; track the best end+length.
    prev = [0] * (len(b) + 1)
    best_len = 0
    best_end = 0  # index in `a` (exclusive) where the best run ends
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len = cur[j]
                    best_end = i
        prev = cur
    return a[best_end - best_len:best_end]


def _is_exempt_quotation(sent: str) -> bool:
    """True iff the sentence carries an explicit "..." quotation adjacent to a
    citation token — the attributed-direct-quote carve-out."""
    return bool(_QUOTED_WITH_CITE.search(sent))


def recitation_findings(report_md: str, note_bodies: dict[str, str]) -> list[Finding]:
    """For each prose sentence (Sources section excluded), flag a `major`
    recitation Finding if its longest contiguous verbatim run against any cited
    note body exceeds RECITATION_MAX_NGRAM words OR > RECITATION_MAX_OVERLAP of
    the sentence's tokens. One finding per sentence (first offending body wins)."""
    findings: list[Finding] = []
    body_words = {nid: words(body) for nid, body in note_bodies.items()}
    for sent in split_sentences(strip_sources_section(report_md)):
        if _is_exempt_quotation(sent):
            continue
        toks = words(sent)
        if not toks:
            continue
        for bw in body_words.values():
            run = longest_common_contiguous_run(toks, bw)
            if len(run) > RECITATION_MAX_NGRAM or len(run) / len(toks) > RECITATION_MAX_OVERLAP:
                findings.append(
                    Finding(
                        failure_mode="recitation",
                        severity="major",
                        location=sent,
                        recommendation=(
                            "Sentence reproduces a source span verbatim "
                            "(longest run %d words) — paraphrase and keep the [N] citation."
                            % len(run)
                        ),
                    )
                )
                break
    return findings


__all__ = [
    "RECITATION_MAX_NGRAM",
    "RECITATION_MAX_OVERLAP",
    "longest_common_contiguous_run",
    "recitation_findings",
    "words",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_quality/test_recitation.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/quality/recitation.py tests/test_quality/test_recitation.py
git commit -m "feat(kr6): deterministic recitation overlap gate (12-gram/0.50)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `quality/grader.py` — judge wrapper emitting patcher-shaped findings

**Files:**
- Create: `src/bad_research/quality/grader.py`
- Test: `tests/test_quality/test_grader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_quality/test_grader.py`:

```python
"""KR-6 — the in-pipeline grader. Wraps LLMJudge to emit patcher-shaped Findings
and provides the judge->findings translation the 12.5 loop runs. dossier 16 §4."""
from __future__ import annotations

import json

from bad_research.llm.base import LLMResponse
from bad_research.quality.grader import GRADER_FINDINGS_CLAUSE, Grader


class FakeLLM:
    """Returns a scripted judge JSON (axes + findings); records messages + calls."""

    name = "fake-llm"

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls = 0
        self.last_messages = None

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1) -> LLMResponse:
        self.calls += 1
        self.last_messages = messages
        return LLMResponse(text=json.dumps(self._payload), usage={}, model="fake")


CORPUS = [{"note_id": "n1", "url": "https://a.edu", "text": "X correlates with Y."}]
REPORT = "# Q\n\nX correlates with Y [1].\n"


def test_grader_passing_verdict_has_no_findings():
    payload = {"factual": 0.9, "citation": 0.9, "completeness": 0.85,
               "source_quality": 0.8, "efficiency": 0.9, "rationale": "good",
               "findings": []}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is True
    assert verdict.findings == []


def test_grader_failing_verdict_emits_patcher_shaped_findings():
    payload = {
        "factual": 0.6, "citation": 0.9, "completeness": 0.5,
        "source_quality": 0.8, "efficiency": 0.9, "rationale": "thin coverage",
        "findings": [
            {"axis": "completeness", "severity": "critical", "failure_mode": "missing",
             "location": "## Limitations", "recommendation": "Add the funding-bias angle."},
            {"axis": "factual", "severity": "major", "failure_mode": "miscited",
             "location": "X correlates with Y [1].", "recommendation": "Soften to 'suggests'."},
        ],
    }
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is False
    assert len(verdict.findings) == 2
    f0 = verdict.findings[0]
    # patcher-shaped: failure_mode / severity / location / recommendation
    assert f0.failure_mode == "missing"
    assert f0.severity == "critical"
    assert f0.location == "## Limitations"
    assert f0.recommendation.startswith("Add")


def test_grade_prompt_appends_the_findings_clause():
    g = Grader(provider=FakeLLM({"factual": 1, "citation": 1, "completeness": 1,
                                 "source_quality": 1, "efficiency": 1, "findings": []}))
    g.grade("Q", REPORT, CORPUS)
    sys_msg = next(m for m in g.provider.last_messages if m.role == "system")
    assert GRADER_FINDINGS_CLAUSE in sys_msg.content


def test_malformed_findings_degrade_to_empty_not_crash():
    payload = {"factual": 0.5, "citation": 0.5, "completeness": 0.5,
               "source_quality": 0.5, "efficiency": 0.5, "findings": "oops-not-a-list"}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    assert verdict.passed is False  # axes fail
    assert verdict.findings == []   # bad findings -> empty, no exception


def test_findings_as_dicts_round_trip_to_json():
    payload = {"factual": 0.6, "citation": 0.9, "completeness": 0.9,
               "source_quality": 0.9, "efficiency": 0.9,
               "findings": [{"axis": "factual", "severity": "major",
                             "failure_mode": "miscited", "location": "s", "recommendation": "r"}]}
    g = Grader(provider=FakeLLM(payload))
    verdict = g.grade("Q", REPORT, CORPUS)
    d = verdict.to_dict()
    assert d["passed"] is False
    assert d["findings"][0]["failure_mode"] == "miscited"
    json.dumps(d)  # serializable for the CLI envelope
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_quality/test_grader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bad_research.quality.grader'`

- [ ] **Step 3: Write the implementation**

Create `src/bad_research/quality/grader.py`:

```python
"""The in-pipeline grader (Stage 12.5) — Claude's `define_outcome` 5-axis judge
turned into a gating loop. Wraps calibrate/judge.py::LLMJudge (the SAME single
strong-model call, NOT an ensemble) and extends its rubric to also emit a
patcher-shaped `findings` array, so the failing-axis defects join the critic +
gate findings the patcher already consumes. Keyless: one host-model call per
round; the loop counter lives in the bad-research-12.5-grader skill. dossier 16 §4."""

from __future__ import annotations

from dataclasses import dataclass

from bad_research.calibrate.constants import JUDGE_MAX_TOKENS, JUDGE_TEMPERATURE, JUDGE_TIER
from bad_research.calibrate.judge import JUDGE_SYSTEM, AxisScores, JudgeVerdict, _extract_json
from bad_research.grounding.gate import Finding
from bad_research.llm.base import LLMMessage, LLMProvider

# The one clause appended to the offline JUDGE_SYSTEM rubric to make the verdict
# patcher-compatible (dossier 16 §4.1). The findings array maps each <0.8 axis
# defect to the {failure_mode, severity, location, recommendation} shape the
# patcher, critics, and gate all share.
GRADER_FINDINGS_CLAUSE = (
    'Also output "findings": a JSON array of the SPECIFIC defects behind any axis < 0.8, '
    'each {"axis","severity":"critical|major|minor","failure_mode":"missing|under-covered|'
    'miscited|misordered","location":"<H2 or sentence>","recommendation":"<surgical fix>"}. '
    "A critical finding is one that, left unfixed, makes an axis fail. Map completeness "
    "misses to the decomposition's required_section_headings + atomic items."
)

GRADER_SYSTEM = JUDGE_SYSTEM + "\n" + GRADER_FINDINGS_CLAUSE


@dataclass
class GraderVerdict:
    """A JudgeVerdict (5 axes + pass) plus the patcher-shaped findings."""

    verdict: JudgeVerdict
    findings: list[Finding]

    @property
    def passed(self) -> bool:
        return self.verdict.passed

    def to_dict(self) -> dict:
        d = self.verdict.to_dict()
        d["findings"] = [
            {
                "failure_mode": f.failure_mode,
                "severity": f.severity,
                "location": f.location,
                "recommendation": f.recommendation,
            }
            for f in self.findings
        ]
        return d


def _parse_findings(raw: dict) -> list[Finding]:
    """Translate the judge's `findings` array into patcher-shaped Finding rows.
    Tolerant: a non-list or a malformed row degrades to fewer/zero findings, never
    an exception (the axes still gate even if findings are unusable)."""
    rows = raw.get("findings")
    if not isinstance(rows, list):
        return []
    out: list[Finding] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        severity = str(r.get("severity", "major"))
        if severity not in ("critical", "major", "minor"):
            severity = "major"
        out.append(
            Finding(
                failure_mode=str(r.get("failure_mode", "under-covered")),
                severity=severity,
                location=str(r.get("location", "")),
                recommendation=str(r.get("recommendation", "")),
            )
        )
    return out


@dataclass
class Grader:
    """In-pipeline grader over an LLMProvider. ONE host-model call per round."""

    provider: LLMProvider
    tier: str = JUDGE_TIER

    def grade(self, query: str, report: str, corpus: list[dict]) -> GraderVerdict:
        corpus_block = "\n".join(
            f"[{c.get('note_id', i)}] {c.get('url', '')}\n{c.get('text', '')[:1200]}"
            for i, c in enumerate(corpus)
        )
        user = (
            f"QUERY:\n{query}\n\n"
            f"CORPUS (the evidence the report had access to):\n{corpus_block}\n\n"
            f"REPORT TO JUDGE:\n{report}\n\n"
            "Score now, then list the defect findings. JSON only."
        )
        resp = self.provider.complete(
            [
                LLMMessage(role="system", content=GRADER_SYSTEM),
                LLMMessage(role="user", content=user),
            ],
            tier=self.tier,  # type: ignore[arg-type]
            max_tokens=JUDGE_MAX_TOKENS,
            temperature=JUDGE_TEMPERATURE,
        )
        raw = _extract_json(resp.text)
        scores = AxisScores.from_raw(raw)
        verdict = JudgeVerdict.from_scores(scores, rationale=str(raw.get("rationale", "")))
        return GraderVerdict(verdict=verdict, findings=_parse_findings(raw))


__all__ = ["GRADER_FINDINGS_CLAUSE", "GRADER_SYSTEM", "Grader", "GraderVerdict"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_quality/test_grader.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/bad_research/quality/grader.py tests/test_quality/test_grader.py
git commit -m "feat(kr6): in-pipeline grader wrapping LLMJudge with patcher-shaped findings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `confidence_band` on the CitationVerifier

**Files:**
- Modify: `src/bad_research/grounding/verifier.py`
- Test: `tests/test_grounding/test_confidence_band.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_grounding/test_confidence_band.py`:

```python
"""KR-6 — confidence-band derivation (dossier 16 §7). verify_score x fetcher-
confidence x n_independent_sources -> high/medium/low -> a hedge word in prose."""
from __future__ import annotations

from bad_research.grounding.verifier import confidence_band


def test_high_band_needs_strong_score_and_consensus():
    assert confidence_band(verify_score=0.85, fetcher_confidence="high", n_sources=3) == "high"


def test_medium_band_on_single_source():
    # verify_score high but only one source -> medium (dossier §7 rule)
    assert confidence_band(verify_score=0.85, fetcher_confidence="high", n_sources=1) == "medium"


def test_medium_band_on_mid_score():
    assert confidence_band(verify_score=0.55, fetcher_confidence="high", n_sources=3) == "medium"


def test_low_band_on_weak_score():
    assert confidence_band(verify_score=0.30, fetcher_confidence="high", n_sources=5) == "low"


def test_low_band_on_low_fetcher_confidence():
    assert confidence_band(verify_score=0.90, fetcher_confidence="low", n_sources=4) == "low"


def test_band_defaults_are_conservative():
    # missing fetcher confidence + single source -> not high
    assert confidence_band(verify_score=0.90, fetcher_confidence=None, n_sources=1) != "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_grounding/test_confidence_band.py -v`
Expected: FAIL with `ImportError: cannot import name 'confidence_band'`

- [ ] **Step 3: Add `confidence_band` + emit it on the finding**

In `src/bad_research/grounding/verifier.py`, after the `PARTIAL_LOW, SUPPORTED_FLOOR` line (line 102), add:

```python

# Confidence-band thresholds (dossier 16 §7 / 08 §4). The band is the prose hedge
# driver; the raw verify_score stays off-band on claim_anchors (Gemini §879).
BAND_HIGH_SCORE = 0.70
BAND_LOW_SCORE = 0.40


def confidence_band(
    verify_score: float, fetcher_confidence: str | None, n_sources: int
) -> str:
    """Combine the verifier's score, the fetcher's self-reported confidence, and
    the independent-source count into a high/medium/low band (dossier 16 §7):

      high   : fetcher=high AND verify_score>=0.70 AND n_sources>=2
      medium : verify_score in [0.40, 0.70) OR n_sources==1
      low    : verify_score<0.40 OR fetcher=low

    Low wins over high (conservative). The patcher hedges medium/low claims."""
    if verify_score < BAND_LOW_SCORE or fetcher_confidence == "low":
        return "low"
    if (
        fetcher_confidence == "high"
        and verify_score >= BAND_HIGH_SCORE
        and n_sources >= 2
    ):
        return "high"
    return "medium"
```

Then extend `CitationFinding` (line 105-110) to carry the band, defaulting to `None` so existing call sites stay valid:

```python
@dataclass
class CitationFinding:
    anchor_id: str
    sentence: str
    verdict: VerifyVerdict
    score: float
    confidence_band: str | None = None
```

And in `CitationVerifier.verify`, set the band on each finding in the persistence loop. Replace the persistence loop (lines 208-213, the `for f in findings:` block) with:

```python
        # Persist dispositions (dossier §2.3) + stamp the confidence band (dossier
        # 16 §7). fetcher-confidence + n_independent_sources come from the claims
        # JSON the caller threads via note_bodies' companion data; absent that, the
        # band derives from verify_score alone (conservative). The CLI writes the
        # band into citation-verify-actions.json for the patcher's hedge rule.
        for f in findings:
            f.confidence_band = confidence_band(
                f.score, fetcher_confidence=None, n_sources=1
            )
            if f.verdict is VerifyVerdict.SUPPORTED:
                store.set_verified(f.anchor_id, verified=1, score=f.score)
            else:
                store.set_verified(f.anchor_id, verified=0, score=f.score)
```

> Note: the verifier knows `verify_score` but not the fetcher-confidence / source count (those live in the claims JSON the orchestrator owns). The deterministic band from `verify_score` alone is the conservative floor; the skill's patcher step (Task 9) is told to upgrade to `high` only when the claims JSON confirms `fetcher=high` AND `n_sources>=2`. `confidence_band()` is exported so the CLI / skill can recompute with the full inputs.

Add `confidence_band` to the module `__all__` if one exists; if not, leave it (the function is importable regardless).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_grounding/test_confidence_band.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the existing verifier tests to confirm no regression**

Run: `uv run python -m pytest tests/test_grounding/ -v`
Expected: PASS (existing grounding tests still green — `CitationFinding`'s new field is defaulted)

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/grounding/verifier.py tests/test_grounding/test_confidence_band.py
git commit -m "feat(kr6): confidence_band derivation + emit on CitationFinding

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: CLI — `grade-report` + `recitation-gate` commands

**Files:**
- Modify: `src/bad_research/cli/research.py`
- Modify: `src/bad_research/cli/__init__.py`
- Test: `tests/test_cli/test_keyless_rewire.py` (grade/recitation portion)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli/test_keyless_rewire.py`:

```python
"""KR-6 — CLI surface for the grader + recitation gate, and the keyless rewire."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


def test_recitation_gate_clean_report_exits_zero(tmp_path: Path):
    report = tmp_path / "r.md"
    report.write_text("# Q\n\nA short paraphrase of the finding here [1].\n", encoding="utf-8")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"n1": "Entirely different wording about the topic at hand."}),
                     encoding="utf-8")
    res = runner.invoke(app, ["recitation-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["recitation"] == []


def test_recitation_gate_flags_verbatim_copy(tmp_path: Path):
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = tmp_path / "r.md"
    report.write_text(f"# Q\n\n{src} [1].\n", encoding="utf-8")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"n1": src}), encoding="utf-8")
    res = runner.invoke(app, ["recitation-gate", "--report", str(report),
                              "--note-bodies", str(notes), "--json"])
    # recitation is a MAJOR finding, not a ship-block: exit 0, but flagged.
    assert res.exit_code == 0
    out = json.loads(res.stdout)
    assert len(out["recitation"]) == 1
    assert out["recitation"][0]["failure_mode"] == "recitation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_cli/test_keyless_rewire.py -k recitation -v`
Expected: FAIL — `recitation-gate` is not a registered command (non-zero exit / "No such command")

- [ ] **Step 3: Add the two commands to `cli/research.py`**

Add to `src/bad_research/cli/research.py` (before the `__all__` block):

```python
# ── grade-report (Stage 12.5) — in-pipeline grader, single host-model call ────
def grade_report_cmd(
    report: str = typer.Option(..., "--report"),
    corpus: str = typer.Option(..., "--corpus"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Grade a report on the 5 axes + emit patcher-shaped findings (Stage 12.5).

    --corpus is a JSON file: a list of {note_id, url, text} dicts (the
    evidence-digest the report had access to). Returns {passed, scores, overall,
    findings:[{failure_mode, severity, location, recommendation}]} for the grader
    loop to feed the patcher. The verdict's findings join critic-findings-grader.json.
    """
    from bad_research.config import BadResearchConfig
    from bad_research.llm.base import get_llm_provider
    from bad_research.quality.grader import Grader

    cfg = BadResearchConfig.load()
    report_md = Path(report).read_text(encoding="utf-8")
    corpus_rows = json.loads(Path(corpus).read_text(encoding="utf-8"))
    grader = Grader(provider=get_llm_provider("anthropic", config=cfg))
    # the query is embedded in the report's H1; the grader reads the report directly.
    query = report_md.splitlines()[0].lstrip("# ").strip() if report_md else ""
    verdict = grader.grade(query, report_md, corpus_rows)
    typer.echo(json.dumps(verdict.to_dict(), default=str))


# ── recitation-gate (Stage 16) — verbatim-copy detector, $0 deterministic ─────
def recitation_gate_cmd(
    report: str = typer.Option(..., "--report"),
    note_bodies: str = typer.Option(..., "--note-bodies"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Deterministic ($0) recitation gate. --note-bodies is a JSON file mapping
    note_id -> body markdown. Flags sentences that copy a source verbatim. A
    `major` finding (NOT a ship-block — unlike uncited-gate); exit 0 always."""
    from bad_research.quality.recitation import recitation_findings

    report_md = Path(report).read_text(encoding="utf-8")
    bodies = json.loads(Path(note_bodies).read_text(encoding="utf-8"))
    findings = recitation_findings(report_md, bodies)
    typer.echo(json.dumps({
        "recitation": [
            {"failure_mode": f.failure_mode, "severity": f.severity,
             "location": f.location, "recommendation": f.recommendation}
            for f in findings
        ]
    }))
```

Then add both to the `__all__` list:

```python
__all__ = [
    "funnel_gather_cmd",
    "grade_report_cmd",
    "recitation_gate_cmd",
    "retrieve_cmd",
    "route_cmd",
    "run_funnel",
    "uncited_gate_cmd",
    "verify_citations_cmd",
]
```

- [ ] **Step 4: Register the commands in `cli/__init__.py`**

First inspect the registration pattern:

Run: `uv run python -m pytest tests/test_cli/test_cli_subcommands.py -v` (to see the existing command names), and read how `uncited_gate_cmd` etc. are wired. Then in `src/bad_research/cli/__init__.py`, find the block that registers the `research.py` commands (look for `from bad_research.cli.research import` and the `app.command(...)` calls for `uncited-gate`). Add the two new ones mirroring the existing pattern. Concretely, alongside the existing import add `grade_report_cmd, recitation_gate_cmd`, and alongside the existing `app.command("uncited-gate")(uncited_gate_cmd)` add:

```python
app.command("grade-report")(grade_report_cmd)
app.command("recitation-gate")(recitation_gate_cmd)
```

(If the file uses a decorator style instead of `app.command(name)(fn)`, match that style — the test only asserts the command name resolves.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_cli/test_keyless_rewire.py -k recitation -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/cli/research.py src/bad_research/cli/__init__.py tests/test_cli/test_keyless_rewire.py
git commit -m "feat(kr6): grade-report + recitation-gate CLI commands

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Rewire the `cli/research.py` builders to the keyless seams

**Files:**
- Modify: `src/bad_research/cli/research.py:38-162` (the four `_build_*` helpers + `funnel_gather_cmd`)
- Test: `tests/test_cli/test_keyless_rewire.py` (rewire portion)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli/test_keyless_rewire.py`:

```python
import inspect

import bad_research.cli.research as RESEARCH


def test_build_providers_returns_keyless_providers():
    cfg = type("C", (), {"searxng_endpoint": "", "effort": "medium"})()
    provs = RESEARCH._build_providers(cfg)
    names = {getattr(p, "name", "") for p in provs}
    # the keyless default: the host WebSearch tool adapter + the ddgs lib.
    assert "websearch" in names
    assert "ddgs" in names
    # every provider is keyless: cost_per_search 0.0, no api key attr set true
    for p in provs:
        assert getattr(p, "cost_per_search", 0.0) == 0.0


def test_build_reranker_default_is_claude_code():
    cfg = type("C", (), {"reranker": "host"})()
    r = RESEARCH._build_reranker(cfg)
    assert type(r).__name__ == "ClaudeCodeReranker"


def test_build_embedder_is_none_by_default():
    cfg = type("C", (), {"reranker": "host", "neural_recall": False})()
    assert RESEARCH._build_embedder(cfg) is None


def test_build_tiered_fetcher_uses_agent_browser_ladder():
    cfg = type("C", (), {"browse_engine": "lightpanda"})()
    f = RESEARCH._build_tiered_fetcher(cfg)
    # the keyless 4-rung TieredFetcher (no Browserbase/Browser-Use rungs).
    assert f is not None
    assert hasattr(f, "fetch_tiered")


def test_no_removed_provider_imports_in_research_module():
    # the rewired module must not pull in any paid-provider seam, even lazily.
    src = inspect.getsource(RESEARCH)
    banned = ["cohere", "tavily", "exa_provider", "firecrawl", "sonar_provider",
              "browse_browserbase", "browse_browseruse", "extract_agentql",
              "extract_stagehand", "cascade", 'get_provider("builtin")',
              'get_embed_provider("cohere"']
    for token in banned:
        assert token not in src, f"removed-provider reference survives: {token}"


def test_funnel_gather_cmd_has_max_tokens_and_reasoning_effort():
    sig = inspect.signature(RESEARCH.funnel_gather_cmd)
    assert "reasoning_effort" in sig.parameters
    assert "max_tokens" in sig.parameters
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_cli/test_keyless_rewire.py -k "build_ or removed_provider or max_tokens" -v`
Expected: FAIL — `_build_providers` returns `get_provider("builtin")`, `_build_embedder` returns a Cohere embedder, `max_tokens` not in the signature, and the banned-token scan finds `get_provider("builtin")` / `get_embed_provider("cohere"`.

- [ ] **Step 3: Rewire the four builders**

In `src/bad_research/cli/research.py`, replace `_build_providers` (lines 38-47) with:

```python
def _build_providers(cfg: object) -> list:
    """Keyless web providers (KR-2). Default = the host WebSearch tool adapter +
    the ddgs multi-engine lib; an optional self-host SearXNG when configured.
    Intent-routed scholarly verticals are added by the skill (route_query), not
    here — this builder supplies the always-on keyless breadth sources. Every
    provider is cost_per_search=0.0, zero key. Degrades to [] on import error."""
    provs: list = []
    try:
        from bad_research.web.search.base import DdgsProvider, WebSearchToolProvider

        provs.append(WebSearchToolProvider())
        provs.append(DdgsProvider())
    except Exception:
        return []
    endpoint = getattr(cfg, "searxng_endpoint", "") or ""
    if endpoint:
        try:
            from bad_research.web.search.base import SearxngProvider

            provs.append(SearxngProvider(endpoint=endpoint))
        except Exception:
            pass
    return provs
```

Replace `_build_tiered_fetcher` (lines 50-57) with:

```python
def _build_tiered_fetcher(cfg: object) -> object | None:
    """Keyless 4-rung browse fetcher (KR-4): httpx -> crawl4ai -> agent-browser
    (lightpanda) -> agent-browser (chrome). No Browserbase/Browser-Use rung.
    The ladder reads the default browse engine from config."""
    try:
        from bad_research.browse.ladder import TieredFetcher

        engine = getattr(cfg, "browse_engine", "lightpanda")
        return TieredFetcher(engine=engine)
    except TypeError:
        # TieredFetcher() may not yet accept engine= on an older KR-4 build.
        from bad_research.browse.ladder import TieredFetcher

        return TieredFetcher()
    except Exception:
        return None
```

Replace `_build_embedder` (lines 149-154) with:

```python
def _build_embedder(cfg: object) -> object | None:
    """Keyless default: NO embedder (FTS5/BM25-only recall, KR-5). The local
    bi-encoder lane is opt-in: only when config.neural_recall is True (the [local]
    extra). Cohere is GONE."""
    if not getattr(cfg, "neural_recall", False):
        return None
    try:
        from bad_research.embed.base import get_embed_provider

        return get_embed_provider("bge-local")
    except Exception:
        return None
```

Replace `_build_reranker` (lines 157-162) with:

```python
def _build_reranker(cfg: object) -> object:
    """Keyless default reranker = ClaudeCodeReranker (host-model LLM-rerank, KR-5).
    config.reranker selects host|local|none; the factory resolves it. Cohere is GONE."""
    from bad_research.retrieval.rerank import get_reranker

    return get_reranker(cfg)
```

Then fix `_build_engine` (lines 132-146): the keyless `RetrievalEngine` is FTS-default, so `lance_dir` is only passed when a local embedder is resident. Replace `_build_engine` with:

```python
def _build_engine(cfg: object, vault: object) -> object:
    """Construct a keyless RetrievalEngine bound to the vault's cache dir. FTS5/BM25
    is the only mandatory index (KR-5); the LanceDB vector lane is wired only when a
    local embedder is present (neural_recall / [local])."""
    from bad_research.retrieval.engine import RetrievalEngine

    root = Path(getattr(vault, "root", Path.cwd()))
    base = root / ".bad-research"
    base.mkdir(parents=True, exist_ok=True)
    embedder = _build_embedder(cfg)
    reranker = _build_reranker(cfg)
    lance_dir = (base / "lance") if embedder is not None else None
    return RetrievalEngine(
        cache_db=base / "semantic_cache.db",
        reranker=reranker,
        embedder=embedder,
        lance_dir=lance_dir,
    )
```

Finally, plumb the effort + token-ceiling flags through `funnel_gather_cmd`. Change its signature (lines 110-120) to add `max_tokens` and wire `reasoning_effort` into the mode. Replace the body's mode resolution — change `funnel_gather_cmd` to:

```python
def funnel_gather_cmd(
    query: str = typer.Argument(None),
    query_file: str = typer.Option(None, "--query-file"),
    search_plan: str = typer.Option(None, "--search-plan"),
    mode: str = typer.Option("light", "--mode"),
    vault_tag: str = typer.Option("", "--vault-tag"),
    max_queries: int = typer.Option(None, "--max-queries"),
    read_top_k: int = typer.Option(None, "--read-top-k"),
    reasoning_effort: str = typer.Option(None, "--reasoning-effort", "--effort"),
    max_tokens: int = typer.Option(None, "--max-tokens"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the scraper funnel: fan-out->dedup->rank->read(rung0-3)->filter->chunk->rerank.

    --reasoning-effort (minimal|low|medium|high) nudges the route + per-stage fan-out
    via skills/router.effort_overrides; --max-tokens sets the per-run ceiling the
    orchestrator degrades against. Both default to the config's tier behaviour.
    """
    from bad_research.skills.router import effort_overrides

    if query_file:
        q = Path(query_file).read_text(encoding="utf-8")
    elif query:
        q = query
    else:
        raise typer.BadParameter("provide a query argument or --query-file")
    # An explicit --reasoning-effort pins the route (the OpenAI continuum); else the
    # caller's --mode stands. This wires the previously-ignored stub flag.
    eff_mode = mode
    ov = effort_overrides(reasoning_effort)
    if ov is not None:
        eff_mode = ov["route"]
    typer.echo(json.dumps(run_funnel(q, mode=eff_mode, vault_tag=vault_tag), default=str))
```

> Note: `run_funnel` already builds `FunnelDeps(providers=_build_providers(cfg), fetcher=_build_tiered_fetcher(cfg), ...)` — because the builders are now keyless, the funnel and `pipeline.run_query._gather`/`_retrieve` (which call `run_funnel` / `_build_engine`) inherit the keyless wiring with zero further edits. The `max_tokens` value is surfaced as a flag the skill reads for the degrade-order invariant; the deterministic funnel itself has no token budget to enforce, so it is accepted-and-recorded, not consumed here.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_cli/test_keyless_rewire.py -v`
Expected: PASS (all rewire + recitation tests)

- [ ] **Step 5: Run the pipeline + funnel tests to confirm the rewire didn't break run_query**

Run: `uv run python -m pytest tests/test_pipeline/ -v`
Expected: PASS — `_gather`/`_retrieve` degrade-on-exception paths keep `run_query` green even with the new builders (the stub-seam tests monkeypatch `_gather`/`_retrieve`/`_synthesize` directly).

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/cli/research.py tests/test_cli/test_keyless_rewire.py
git commit -m "refactor(kr6): rewire research builders to keyless seams (websearch/ddgs/agent-browser/ClaudeCodeReranker/FTS-default)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: The grader-loop skill `bad-research-12.5-grader.md`

**Files:**
- Create: `src/bad_research/skills/bad-research-12.5-grader.md`
- Test: `tests/test_skills/test_grader_skill.py`

- [ ] **Step 1: Write the failing test (structural validator)**

Create `tests/test_skills/test_grader_skill.py`:

```python
"""KR-6 — structural validator for the new grader-loop skill (dossier 16 §4.1)."""
from __future__ import annotations

from tests.test_skills.validate import validate_skill


def test_grader_skill_is_structurally_valid(skills_dir, known_skills):
    p = skills_dir / "bad-research-12.5-grader.md"
    assert p.exists()
    assert validate_skill(p, known_skills) == []


def test_grader_skill_runs_the_loop_with_cap_3(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "MAX_GRADER_REVISIONS" in body
    assert "bad grade-report" in body
    assert "full" in body.lower()  # full-tier only
    # the judge->patch->re-judge loop shape
    assert "re-judge" in body.lower() or "re-grade" in body.lower()
    # it does NOT run on light/agentic-fast (anti-overkill, dossier §4.1)
    assert "agentic-fast" in body and "light" in body


def test_grader_skill_feeds_findings_to_patcher(skills_dir):
    body = (skills_dir / "bad-research-12.5-grader.md").read_text()
    assert "critic-findings-grader.json" in body
    assert "bad-research-14-patcher" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_skills/test_grader_skill.py -v`
Expected: FAIL — the file does not exist.

- [ ] **Step 3: Write the skill file**

Create `src/bad_research/skills/bad-research-12.5-grader.md`:

```markdown
---
name: bad-research-12.5-grader
description: >
  Stage 12.5 of the hyperresearch V8 pipeline (FULL tier only). The in-pipeline
  grader loop: the 5-axis define_outcome judge scores the report, its failing-axis
  defects join the critic findings, the patcher (step 14) applies them, and the
  judge re-grades — up to MAX_GRADER_REVISIONS (3) rounds. We built the offline
  judge (calibrate/judge.py) and never let it gate a run; this stage closes that
  loop. Keyless: a single host-model call per round + a host loop counter. Invoked
  via Skill tool from the entry skill, between critics/gap-fetch (12/13) and the
  patcher's final convergence (14).
---

# Step 12.5 — Grader loop (judge → patch → re-judge)

**Tier gate:** FULL tier ONLY. SKIP entirely for `light` and `agentic-fast` —
their quality contract is the forward binding + the deterministic uncited gate; a
grader loop on a $1–15 fast query is the overkill we explicitly reject. Run only
when the route in `research/prompt-decomposition.json` is `full`.

**Goal:** raise the report's quality on the four non-citation axes (factual,
completeness, source_quality, efficiency) by feeding the judge's defect findings
to the patcher and re-grading, capped at 3 rounds. Patch, never regenerate.

---

## Recover state

Read these inputs:
- `research/scaffold.md` — vault_tag, route
- `research/prompt-decomposition.json` — confirm `route == "full"`; read
  `required_section_headings` + atomic items (the judge maps completeness misses
  to these)
- `research/notes/final_report_<vault_tag>.md` — the report (already citation-
  verified at 11.5, critic-patched once at 12/14)
- `research/temp/evidence-digest.md` — the corpus the report had access to
- `research/query-<vault_tag>.md` — canonical research query

If `route != "full"`, write nothing and return to the entry skill immediately —
this stage does not run.

---

## Step 12.5.1 — Build the corpus JSON for the judge

The grader needs the evidence as a JSON list of `{note_id, url, text}`. Convert
the evidence-digest into that shape (one entry per cited note):

```bash
PYTHONIOENCODING=utf-8 $HPR search "" --tag <vault_tag> --json \
  | python -c "
import sys, json
d = json.load(sys.stdin)
rows = [{'note_id': r.get('id',''), 'url': r.get('url',''), 'text': (r.get('body') or r.get('snippet') or '')[:1200]}
        for r in d.get('data',{}).get('results',[])]
open('research/temp/grader-corpus.json','w').write(json.dumps(rows))
print(f'corpus rows: {len(rows)}')
"
```

---

## Step 12.5.2 — The grader loop (host-run, cap = MAX_GRADER_REVISIONS = 3)

`MAX_GRADER_REVISIONS = 3` (NOT Claude's 20 — we PATCH not REGENERATE, so each
round is a small surgical Edit and convergence is far faster). The loop is:

```
revisions = 0
while revisions < MAX_GRADER_REVISIONS:   # 3
    verdict = bad grade-report --report research/notes/final_report_<vault_tag>.md \
                --corpus research/temp/grader-corpus.json --json
    #   -> {passed, scores{5 axes}, overall, findings:[{failure_mode,severity,location,recommendation}]}
    if verdict.passed:  break             # every axis >= 0.70 AND mean >= 0.75
    # write the failing-axis findings as a patcher-shaped findings file:
    write verdict.findings -> research/critic-findings-grader.json  (shape: {"findings":[...]})
    # run the patcher (step 14) over the grader findings (surgical Edits only):
    Skill(skill: "bad-research-14-patcher")   # the patcher reads critic-findings-grader.json too
    revisions += 1
# PASS or cap reached -> proceed
```

Concretely, each round:

1. Run the grader:
   ```bash
   bad grade-report --report research/notes/final_report_<vault_tag>.md \
       --corpus research/temp/grader-corpus.json --json > research/temp/grade-round-<N>.json
   ```
2. Parse `passed`. If `true`, the loop is done — record it in
   `research/temp/orchestrator-notes.md` and proceed to "Exit criterion."
3. If `false`, extract the `findings` array and write the grader findings file:
   ```bash
   python -c "
   import json, pathlib
   v = json.loads(pathlib.Path('research/temp/grade-round-<N>.json').read_text())
   pathlib.Path('research/critic-findings-grader.json').write_text(
       json.dumps({'findings': v.get('findings', [])}))
   print('grader findings:', len(v.get('findings', [])))
   "
   ```
4. Re-run the patcher: `Skill(skill: "bad-research-14-patcher")`. The patcher
   already globs `research/critic-findings-*.json`, so it picks up
   `critic-findings-grader.json` automatically and applies the grader's surgical
   Edits.
5. Increment the round counter in your TodoWrite note and loop.

**Track the loop counter in `research/temp/orchestrator-notes.md`** (it survives
compaction): write a line `grader-loop round <N>: passed=<bool> overall=<x>` each
round. The cap of 3 is the cost ceiling — never run a 4th round.

**Never emit bare text while the patcher Task is in flight** — append to
`research/temp/orchestrator-notes.md` instead.

---

## Step 12.5.3 — Convergence note

When the loop exits (PASS or cap reached), write `research/grader-log.json`:

```bash
python -c "
import json, pathlib
rounds = sorted(pathlib.Path('research/temp').glob('grade-round-*.json'))
log = {'rounds': len(rounds), 'final_passed': False, 'overall': None}
if rounds:
    v = json.loads(rounds[-1].read_text())
    log['final_passed'] = bool(v.get('passed'))
    log['overall'] = v.get('overall')
pathlib.Path('research/grader-log.json').write_text(json.dumps(log))
print(log)
"
```

If the cap was reached without a PASS, that is acceptable — the report still ships
(the deterministic uncited gate at step 16 is the hard ship-block, not the grader).
Record the non-PASS in the log for the audit trail; do NOT loop a 4th time.

---

## Exit criterion

- `research/grader-log.json` exists with `rounds` set and `final_passed` recorded.
- The grader loop ran ≤ MAX_GRADER_REVISIONS (3) rounds.
- `research/notes/final_report_<vault_tag>.md` reflects any grader-driven patches.
- For a `light` / `agentic-fast` route: this stage was skipped (no `grader-log.json`).

---

## Next step

Return to the entry skill (`bad-research`). The patcher's final convergence (step
14) is complete; invoke step 14.5:

```
Skill(skill: "bad-research-fresh-review")
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_skills/test_grader_skill.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the all-skills validator to confirm the new skill doesn't break cross-references**

Run: `uv run python -m pytest tests/test_skills/test_all_skills_valid.py -v`
Expected: PASS — the new skill is added to `known_skills` (it matches the `bad-research*.md` glob) and all references resolve.

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/skills/bad-research-12.5-grader.md tests/test_skills/test_grader_skill.py
git commit -m "feat(kr6): bad-research-12.5-grader skill (judge->patch->re-judge, cap 3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Wire 12.5 + 7-field contract + recitation into the existing skills

**Files:**
- Modify: `src/bad_research/skills/bad-research.md` (stage map + spawn contract + recovery artifacts + degrade invariant)
- Modify: `src/bad_research/skills/bad-research-2-width-sweep.md` (fetcher spawn 4 fields)
- Modify: `src/bad_research/skills/bad-research-5-depth-investigation.md` (investigator spawn 4 fields)
- Modify: `src/bad_research/skills/bad-research-14-patcher.md` (grader findings + hedge rule)
- Modify: `src/bad_research/skills/bad-research-16-readability-audit.md` (recitation gate)
- Test: `tests/test_skills/test_delegation_contract.py` + extend `tests/test_skills/test_modified_stages.py`

- [ ] **Step 1: Write the failing tests (structural validators)**

Create `tests/test_skills/test_delegation_contract.py`:

```python
"""KR-6 — the 7-field delegation contract + per-subagent caps in the skills."""
from __future__ import annotations

from tests.test_skills.validate import validate_skill

CONTRACT_FIELDS = ("objective", "output_shape", "tools_allowed", "stop_conditions")


def test_entry_skill_mandates_seven_field_contract(skills_dir, known_skills):
    p = skills_dir / "bad-research.md"
    body = p.read_text()
    # the 3 HAVE fields + the 4 NET-NEW fields (dossier 16 §3.1)
    for field in CONTRACT_FIELDS:
        assert field in body, f"entry skill missing contract field: {field}"
    assert validate_skill(p, known_skills) == []


def test_width_sweep_fetcher_carries_the_four_fields(skills_dir):
    body = (skills_dir / "bad-research-2-width-sweep.md").read_text()
    for field in CONTRACT_FIELDS:
        assert field in body, f"width-sweep spawn missing: {field}"
    # the cap is referenced (FETCHER_TOOLCALL_CAP / FETCHER_TIMEOUT_S)
    assert "stop_conditions" in body
    assert "tool call" in body.lower() or "FETCHER_TOOLCALL_CAP" in body


def test_depth_investigation_carries_the_four_fields(skills_dir):
    body = (skills_dir / "bad-research-5-depth-investigation.md").read_text()
    for field in CONTRACT_FIELDS:
        assert field in body, f"depth spawn missing: {field}"


def test_entry_skill_has_grader_stage_and_degrade_invariant(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "bad-research-12.5-grader" in body
    assert "12.5" in body
    # the token-ceiling degrade order (cut tokens last)
    assert "degrade" in body.lower()
    assert "--max-tokens" in body or "max-tokens" in body


def test_entry_skill_has_effort_continuum(skills_dir):
    body = (skills_dir / "bad-research.md").read_text()
    assert "--reasoning-effort" in body or "--effort" in body
    for level in ("minimal", "low", "medium", "high"):
        assert level in body
```

Append to `tests/test_skills/test_modified_stages.py`:

```python


def test_patcher_consumes_grader_findings_and_hedges(skills_dir):
    body = (skills_dir / "bad-research-14-patcher.md").read_text()
    assert "critic-findings-grader.json" in body
    # the confidence-band hedge rule (dossier 16 §7)
    assert "confidence_band" in body
    assert "hedge" in body.lower()


def test_step16_has_recitation_gate(skills_dir):
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    assert "bad recitation-gate" in body
    # it's a major finding, NOT a ship-block (unlike uncited)
    assert "not a ship-block" in body.lower() or "does not block ship" in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_skills/test_delegation_contract.py tests/test_skills/test_modified_stages.py -v`
Expected: FAIL — the contract fields, the 12.5 stage, the degrade invariant, the recitation gate, and the patcher hedge rule are all absent.

- [ ] **Step 3a: Extend the entry-skill spawn contract (`bad-research.md`)**

Replace the "Subagent spawn contract" section body (lines 173-183) so it mandates 7 fields. Replace:

```markdown
When a step skill instructs you to spawn a subagent, the prompt you pass MUST include three pieces near the top:

1. **`research_query` — verbatim, block-quoted** from `research/query-<vault_tag>.md`. Do not paraphrase, do not summarize.

2. **Pipeline position statement.** One sentence naming what step the subagent runs in, what came before, what comes after. Example: *"You are step 5 (depth investigator) of the hyperresearch V8 pipeline. Step 4's loci analysts produced `research/loci.json`; after you return, step 6 will reconcile your committed position against the other investigators'."*

3. **The subagent's specific inputs** (vault_tag, output_path, locus, etc.). Each step skill's spawn template documents the required fields.

Skipping any of these in a Task prompt is a process violation.
```

with:

```markdown
When a step skill instructs you to spawn a subagent, the prompt you pass MUST include **seven** pieces near the top — the 3-piece HAVE contract plus Claude's 4-field delegation contract (dossier 16 §3.1). A fetcher handed a thin sub-topic with no `stop_conditions` burns its whole budget "searching for nonexistent sources" — the exact documented failure mode. The four added fields are cheap insurance:

1. **`research_query` — verbatim, block-quoted** from `research/query-<vault_tag>.md`. Do not paraphrase, do not summarize.

2. **`pipeline_position`** — one sentence naming what step the subagent runs in, what came before, what comes after. Example: *"You are step 5 (depth investigator); step 4's loci analysts produced `research/loci.json`; step 6 reconciles your committed position."*

3. **`inputs`** — the subagent's specific inputs (vault_tag, output_path, locus, etc.). Each step skill's spawn template documents the required fields.

4. **`objective`** — the single self-contained sub-objective the subagent must achieve (one sentence).

5. **`output_shape`** — the exact return format. For fetchers/investigators this is the `claims-*.json` shape: *"JSON array of {claim, note_id, quoted_support, char_start, char_end}"* — pinning this is what makes the downstream Stage-11.5 binding deterministic.

6. **`tools_allowed`** — the explicit tool allowlist, e.g. `["web_search","fetch_url","execute_python"]` for a fetcher, `["Read","Write"]` for a synthesizer.

7. **`stop_conditions`** — the runtime halt rule: *"halt when N primary sources found OR the tool-call cap is reached OR FETCHER_TIMEOUT_S elapses"*. The per-subagent caps live in `skills/routing_constants.py` (`FETCHER_TOOLCALL_CAP={"light":10,"full":20}`, `FETCHER_TIMEOUT_S=300`, `INVESTIGATOR_TIMEOUT_S=900`, `SUBAGENT_SOURCE_KILL=100`). The host cannot hard-interrupt a subagent mid-loop, so the cap is a **prompt-level `stop_conditions` guard + an orchestrator-side per-wave deadline** (you check elapsed wall-clock between batch waves and proceed with returned results if a wave exceeds `FETCHER_TIMEOUT_S`).

Skipping any of these seven in a Task prompt is a process violation.
```

- [ ] **Step 3b: Add Stage 12.5 to the full-tier sequence + the stage map (`bad-research.md`)**

In the stage table (line 71), change the `full` row to insert 12.5 between 12/13 and 14:

Replace:
```markdown
| `full` | 0.5 → 1 → 1.5 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 11.5 → 12 → 13 → 14 → 14.5(fresh-review) → 15 → 16(+gate) | ~$60–120 | ~1.5–2.5 h |
```
with:
```markdown
| `full` | 0.5 → 1 → 1.5 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 11.5 → 12 → 13 → 12.5(grader loop) → 14 → 14.5(fresh-review) → 15 → 16(+gate+recitation) | ~$60–120 | ~1.5–2.5 h |
```

And in the "Where the stage numbers map to" list (after line 78), add:
```markdown
- 12.5 → `Skill(skill: "bad-research-12.5-grader")` (in-pipeline grader loop: judge→patch→re-judge ≤3; full only — slots between critics/gap-fetch and the patcher's final convergence)
```

- [ ] **Step 3c: Add the effort continuum + token-ceiling degrade invariant (`bad-research.md`)**

After the "RESPECT THE ROUTE." paragraph (line 84), add a new subsection:

```markdown

### Reasoning-effort continuum + token ceiling

The `--reasoning-effort` flag (alias `--effort`) is a 4-level dial — `minimal` /
`low` / `medium` / `high` — that nudges the route + per-stage fan-out on top of
the auto-classified route (OpenAI's continuum, dossier 16 §6.1). The mapping lives
in `skills/routing_constants.py::EFFORT_MAP` and is applied by
`skills/router.py::effort_overrides`:

| `--effort` | route | drafters | fetcher fan-out | extended thinking |
|---|---|---|---|---|
| `minimal` | light, single draft | Haiku-tier | ≤4 | off |
| `low` | light | Sonnet-tier | ≤8 | off |
| `medium` (default) | full | default | 10–12, loci ≤4 | on |
| `high` | full, max | Opus-tier | 12, loci ≤6 | on |

When the user passes `--max-tokens <N>`, track the cumulative token total in
`research/temp/orchestrator-notes.md`. As the run approaches the ceiling, degrade
in **Claude's order — cut tokens LAST** (`skills/router.py::degrade_order`):

1. cut tool-call redundancy first (skip the redundancy-audit sub-step)
2. then cut fan-out width (fewer fetchers / fewer loci)
3. then cut model tier (heavy → light on non-critical stages)
4. NEVER cut the synthesis / grounding token budget — that's the 80%-variance core.

The ceiling is opt-in; the default is the existing per-tier budget. We surface a
count, not a billing system.
```

- [ ] **Step 3d: Add the 12.5 + recitation artifacts to the recovery map + integrity gate (`bad-research.md`)**

In the "Recovery" disk-artifacts list (after line 209, the Step 13 line), add:
```markdown
   - Step 12.5: `research/grader-log.json` (grader-loop convergence; full only) + `research/critic-findings-grader.json`
```

In the same list, change the Step 16 line (line 213) to mention recitation:
```markdown
   - Step 16: `research/readability-recommendations.json`, `research/readability-decisions.json`, the `bad uncited-gate` pass + the `bad recitation-gate` pass (and edited final_report.md)
```

- [ ] **Step 3e: Add the 4 fields to the width-sweep fetcher spawn template**

In `src/bad_research/skills/bad-research-2-width-sweep.md`, replace the spawn template block (lines 169-188, "Spawn template (use the standard 3-piece contract):" through the closing fence) with:

```markdown
**Spawn template (the 7-field delegation contract — see entry-skill spawn contract):**
```
subagent_type: bad-research-fetcher
prompt: |
  RESEARCH QUERY (verbatim, gospel):
  > {{paste contents of research/query-<vault_tag>.md}}

  QUERY FILE: research/query-<vault_tag>.md

  PIPELINE POSITION: You are step 2 (width-sweep fetcher) of the
  hyperresearch V8 pipeline. The orchestrator partitioned the URL queue into
  non-overlapping batches; you fetch ONLY the URLs in your batch. After you
  return, the orchestrator runs a coverage check (step 2.5) and may dispatch wave 2.

  INPUTS:
  - vault_tag: <vault_tag>
  - urls: [<batch URLs, exactly as assigned>]
  - batch_id: <number>

  OBJECTIVE: fetch and ground every URL in your batch into vault notes tagged
  <vault_tag>, chasing 3–8 primary sources via citation chains.

  OUTPUT_SHAPE: for each note, emit the claims JSON the binding consumes —
  a JSON array of {claim, note_id, quoted_support, char_start, char_end}.

  TOOLS_ALLOWED: ["fetch_url", "web_search", "execute_python"]

  STOP_CONDITIONS: halt when every assigned URL is fetched OR you reach the
  fetcher tool-call cap (FETCHER_TOOLCALL_CAP: 10 light / 20 full tool calls)
  OR FETCHER_TIMEOUT_S (300s) elapses — then return what you have. Do NOT keep
  searching for nonexistent sources. Hard kill at SUBAGENT_SOURCE_KILL (100 sources).
```

**Orchestrator-side wave deadline.** The host cannot interrupt a fetcher mid-loop.
So between waves, check elapsed wall-clock: if a fetcher wave exceeds
FETCHER_TIMEOUT_S (300s), proceed to step 2.5 with the results that returned —
do not block on a slow fetcher.
```

- [ ] **Step 3f: Add the 4 fields to the depth-investigation spawn template**

Open `src/bad_research/skills/bad-research-5-depth-investigation.md` and find its investigator spawn template (the block starting `subagent_type: bad-research-...` with `RESEARCH QUERY` / `PIPELINE POSITION` / `YOUR INPUTS`). Inside that template, after the `YOUR INPUTS:` block, add the four fields (mirroring the width-sweep edit but for an investigator):

```markdown

  OBJECTIVE: investigate the assigned locus to a committed position, grounding
  every claim in primary sources.

  OUTPUT_SHAPE: an interim note ending in `## Committed position`, plus a claims
  JSON array of {claim, note_id, quoted_support, char_start, char_end}.

  TOOLS_ALLOWED: ["fetch_url", "web_search", "Read", "Write", "execute_python"]

  STOP_CONDITIONS: halt when the locus is investigated to a committed position OR
  you reach the fetcher tool-call cap (FETCHER_TOOLCALL_CAP) OR INVESTIGATOR_TIMEOUT_S
  (900s) elapses — then return your committed position with the evidence gathered so
  far. Do not keep searching for nonexistent sources. Hard kill at SUBAGENT_SOURCE_KILL (100).
```

(If the depth skill has multiple spawn templates, add the four fields to each `prompt: |` block that spawns a `bad-research-*investigator*` subagent.)

- [ ] **Step 3g: Add the grader-findings + hedge rule to the patcher skill**

In `src/bad_research/skills/bad-research-14-patcher.md`, in the "YOUR INPUTS" findings_paths list (lines 84-89), add the grader findings file:

```markdown
  - findings_paths: [
      research/critic-findings-dialectic.json,    (full tier only)
      research/critic-findings-depth.json,        (full tier only)
      research/critic-findings-width.json,
      research/critic-findings-instruction.json,
      research/critic-findings-grader.json        (full tier only; Stage-12.5 grader loop, if present)
    ]
```

Then add a new subsection after "Step 14.2 — Spawn the patcher" (after line 101, before "Step 14.3"):

```markdown
## Step 14.2b — Confidence-band hedging (dossier 16 §7)

The Stage-11.5 CitationVerifier wrote a `confidence_band` (high / medium / low)
per cited sentence into `research/temp/citation-verify-actions.json`, derived from
`verify_score` × the fetcher's self-reported confidence × the independent-source
count (`research/temp/consensus-claims.json`). The patcher MUST add a band-
appropriate hedge to any **medium / low** claim the synthesizer asserted too
confidently — WITHOUT changing the citation or the number:

| `confidence_band` | prose treatment |
|---|---|
| `high` (fetcher=high AND verify_score≥0.70 AND n_sources≥2) | assert plainly, no hedge |
| `medium` (verify_score 0.40–0.70 OR n_sources==1) | "the evidence suggests…" / "one source reports…" |
| `low` (verify_score<0.40 OR fetcher=low) | "preliminary…" / "a single commentary claims…" |

Keep the raw 0.0–1.0 score OFF the page (it lives on `claim_anchors.verify_score`
for the CLI/audit only). The prose carries only the hedge word. This is a patcher
finding like any other — a surgical Edit that prepends the hedge frame; if the
sentence is already hedged at the right band, no edit.

The patcher spawn prompt (Step 14.2) must instruct the subagent: *"For any cited
sentence whose `confidence_band` in citation-verify-actions.json is `medium` or
`low` and which is asserted without a hedge, add the band-appropriate hedge frame
via a surgical Edit. Do not change the citation or any number."*
```

- [ ] **Step 3h: Add the recitation gate to step 16**

In `src/bad_research/skills/bad-research-16-readability-audit.md`, after "Step 16.6 — No-uncited-claim hard gate" (after line 172, before "## Exit criterion"), add:

```markdown
## Step 16.7 — Recitation overlap gate (major finding, NOT a ship-block)

After the uncited gate passes, run the deterministic ($0) recitation gate. It
flags any report sentence that reproduces a cited note's body too closely (a
verbatim run > 12 words, or > 50% of the sentence lifted contiguously) — Gemini's
RECITATION *output* guarantee without its decoder machinery. Unlike the uncited
gate, recitation is a **major** finding, **not a ship-block** (copying is a
quality/legal smell, not a correctness failure) — so it never blocks ship.

First build the note-bodies JSON (note_id → body) the gate needs:

```bash
PYTHONIOENCODING=utf-8 $HPR search "" --tag <vault_tag> --json \
  | python -c "
import sys, json
d = json.load(sys.stdin)
bodies = {r.get('id',''): (r.get('body') or '') for r in d.get('data',{}).get('results',[])}
open('research/temp/recitation-bodies.json','w').write(json.dumps(bodies))
"
bad recitation-gate --report research/notes/final_report_<vault_tag>.md \
    --note-bodies research/temp/recitation-bodies.json --json
```

- Output `{"recitation": []}` → no verbatim copying; done.
- Output `{"recitation": [{"location": "...", "recommendation": "..."}]}` → for each
  flagged sentence, apply a surgical Edit that paraphrases the copied span while
  keeping the `[N]` citation. A sentence whose verbatim run sits inside an explicit
  `"…"` quotation adjacent to a citation is already exempt (the gate does not flag
  it). Re-run the gate after paraphrasing to confirm the flag cleared. The gate
  does not block ship — but a clean report has zero recitation findings.
```

Also update the Exit criterion list (after line 181) to add:
```markdown
- `bad recitation-gate` was run; any flagged sentences were paraphrased (recitation is a major finding, not a ship-block)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_skills/test_delegation_contract.py tests/test_skills/test_modified_stages.py -v`
Expected: PASS (all delegation + modified-stage tests)

- [ ] **Step 5: Run the full skills suite to confirm no structural regression**

Run: `uv run python -m pytest tests/test_skills/ -v`
Expected: PASS — entry skill + all step skills still validate; the new 12.5 reference resolves; the contract edits didn't break any required-section check.

- [ ] **Step 6: Commit**

```bash
git add src/bad_research/skills/bad-research.md \
        src/bad_research/skills/bad-research-2-width-sweep.md \
        src/bad_research/skills/bad-research-5-depth-investigation.md \
        src/bad_research/skills/bad-research-14-patcher.md \
        src/bad_research/skills/bad-research-16-readability-audit.md \
        tests/test_skills/test_delegation_contract.py \
        tests/test_skills/test_modified_stages.py
git commit -m "feat(kr6): wire 12.5 grader, 7-field contract, recitation gate, hedge rule, effort continuum into skills

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Full-suite green + no-removed-provider sweep

**Files:**
- Test: whole suite (no new files; this task verifies the integration)

- [ ] **Step 1: Run the whole suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run python -m pytest`
Expected: PASS (0 failures). If a pre-existing KR-1..5 test fails because it predates this plan, it is out of scope — note it; do NOT fix unrelated failures here. The KR-6 tests (grader, recitation, confidence_band, router_effort, keyless_rewire, grader_skill, delegation_contract, modified_stages) must all pass.

- [ ] **Step 2: Repo-wide removed-provider import sweep**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
cd /Users/seventyleven/Desktop/badresearch
grep -rEn "import (cohere|tavily|exa_py|firecrawl)|from bad_research\.web\.(exa_provider|providers\.(tavily_provider|sonar_provider|firecrawl_provider|cascade))|from bad_research\.browse\.(browse_browserbase|browse_browseruse|extract_agentql|extract_stagehand)|get_provider\(\"builtin\"\)|get_embed_provider\(\"cohere\"" \
  src/bad_research/cli/research.py src/bad_research/pipeline.py src/bad_research/funnel/ src/bad_research/skills/ src/bad_research/quality/ src/bad_research/grounding/verifier.py \
  || echo "CLEAN: no removed-provider reference in the KR-6 rewire surface"
```
Expected: `CLEAN: no removed-provider reference in the KR-6 rewire surface`

> Note: this sweep is scoped to the files KR-6 owns/rewires. A repo-wide sweep of the still-to-be-deleted KR-1 files (`web/providers/`, `embed/cohere.py`, etc.) is KR-1's job, not KR-6's — those files may still exist until KR-1 deletes them, but nothing in the KR-6 rewire surface imports them.

- [ ] **Step 3: Confirm the rewire chain end-to-end (smoke)**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
uv run python - <<'PY'
import bad_research.cli.research as R
cfg = type("C", (), {"searxng_endpoint": "", "neural_recall": False,
                     "reranker": "host", "browse_engine": "lightpanda"})()
provs = R._build_providers(cfg)
print("providers:", [getattr(p, "name", "?") for p in provs])
print("reranker:", type(R._build_reranker(cfg)).__name__)
print("embedder:", R._build_embedder(cfg))
print("fetcher:", type(R._build_tiered_fetcher(cfg)).__name__ if R._build_tiered_fetcher(cfg) else None)
assert {"websearch", "ddgs"} <= {getattr(p, "name", "") for p in provs}
assert type(R._build_reranker(cfg)).__name__ == "ClaudeCodeReranker"
assert R._build_embedder(cfg) is None
print("REWIRE OK: funnel/pipeline now build keyless providers + host reranker + FTS-default")
PY
```
Expected: prints `REWIRE OK: …` with `providers: ['websearch', 'ddgs']`, `reranker: ClaudeCodeReranker`, `embedder: None`.

- [ ] **Step 4: Commit (no-op if nothing changed; otherwise a verification marker)**

```bash
git add -A
git commit -m "test(kr6): full suite green + no-removed-provider sweep clean" --allow-empty
# (append the Co-Authored-By trailer)
```

Use:
```bash
git commit --amend -m "test(kr6): full suite green + no-removed-provider sweep clean

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" --allow-empty
```

---

## Self-Review (run before declaring complete)

**Spec coverage — the 5 levers + the rewire (INTERFACES_KEYLESS §6, dossier 16 §3-7):**

| Spec item | Task |
|---|---|
| Lever 1 — grader loop (12.5, judge→patch→re-judge ≤3) | Task 4 (`quality/grader.py`), Task 8 (12.5 skill), Task 6 (`grade-report` CLI) |
| Lever 2 — 7-field delegation contract + per-subagent caps | Task 1 (caps constants), Task 9 (entry + width-sweep + depth spawn templates) |
| Lever 3 — recitation gate (12-gram / 0.50) | Task 3 (`quality/recitation.py`), Task 6 (`recitation-gate` CLI), Task 9 (step-16 wiring) |
| Lever 4 — reasoning-effort continuum + token ceiling | Task 1 (`EFFORT_MAP`/`DEGRADE_ORDER`), Task 2 (`effort_overrides`/`degrade_order`), Task 7 (CLI flags), Task 9 (entry invariant) |
| Lever 5 — confidence-band hedging | Task 5 (`confidence_band` + emit), Task 9 (patcher hedge rule) |
| Rewire — search cascade → `web/search` | Task 7 (`_build_providers` → `WebSearchToolProvider`+`DdgsProvider`+`SearxngProvider`) |
| Rewire — depth/gap-fetch → agent-browser ladder | Task 7 (`_build_tiered_fetcher` → keyless `TieredFetcher`) |
| Rewire — synthesize → FTS+host-rerank retrieval | Task 7 (`_build_reranker`→`ClaudeCodeReranker`, `_build_embedder`→None, `_build_engine` FTS-default) |
| Rewire — funnel/pipeline inherit keyless wiring | Task 7 note (`run_funnel`/`_gather`/`_retrieve` delegate to the rebuilt builders) |
| No removed-provider import survives | Task 7 (`test_no_removed_provider_imports`), Task 10 (repo sweep) |

**Type consistency:** `Finding` (from `grounding/gate.py`) is the shared shape used by `grader.py`, `recitation.py`, and the patcher — all four fields (`failure_mode`, `severity`, `location`, `recommendation`) match across producers and the patcher consumer. `GraderVerdict.to_dict()` serializes findings to the same dict keys the `grade-report` CLI emits and the 12.5 skill writes to `critic-findings-grader.json` (which the patcher's `critic-findings-*.json` glob already reads). `confidence_band()` signature `(verify_score, fetcher_confidence, n_sources)` is identical in the function, the test, and the patcher-skill table. `effort_overrides`/`degrade_order` consume the `EFFORT_MAP`/`DEGRADE_ORDER` constants from Task 1 verbatim.

**Placeholder scan:** no TBD/TODO; every code step shows full code; every skill edit shows the exact replacement text; every command has an expected output.
