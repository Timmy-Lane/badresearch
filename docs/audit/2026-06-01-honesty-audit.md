# Bad Research — Honest Multi-Agent Audit

**Date:** 2026-06-01
**Method:** 6 independent audit lenses (pipeline-value, competitor-reality, quality-evidence,
skill-craft, operator-ux, codex-portability), each forced to a frank verdict with file-level
evidence; each lens's strongest claims then re-checked by an independent skeptic against the
real code; one lead-auditor synthesis. 25 agents, ~1.57M tokens.
**Raw data:** `docs/audit/2026-06-01-honesty-audit-RAW.json`

> The three load-bearing findings (grader install gap, the 55.9/52.6 over-claim, the
> "keyless" verify/grade CLI requiring `ANTHROPIC_API_KEY`) were *independently re-verified
> by hand* against the current `main` tree and all confirmed. Per-lens scores: 5.5–6.5.

---

## Lead Auditor Verdict

**Mixed — roughly two-thirds genuine engineering, one-third theater, and the theater is
concentrated exactly where the marketing shouts loudest.** Real-value score over a naive
"Claude + WebSearch + one good prompt" baseline: **6 / 10.**

bad-research is not bullshit as a whole: the adversarial scaffold (tool-locked Read+Edit
critics querying a separate on-disk corpus, patch-never-regenerate, coverage-matrix
decomposition, a $0 byte-identity quote check, a clean 85-test routing engine) is real,
inspectable, and structurally impossible for a one-shot prompt to replicate. But three
load-bearing public claims are materially overstated or circular, and one bug breaks the
flagship route.

---

## What's genuinely good (verified)

1. **Adversarial critics do real work a single prompt can't** — they query a *separate
   on-disk corpus* for counter-evidence missing from the draft (`hooks.py:590-595`,
   `:701-706`; `search` is a real store query, `vault_cmds.py:241-318`).
2. **Patch-never-regenerate is enforced at the tool level** — patcher is `Read,Edit` only;
   orchestrator pre-stubs `patch-log.json` because the patcher can't Write (`patcher.md:50`).
3. **Tier-A byte-identity quote check** — deterministic, $0, kills fabricated quotes with
   zero LLM calls (`verifier.py:144-151`, `test_verifier.py:41-46`).
4. **Deterministic uncited-claim ship-gate has teeth** (`gate.py:145-185`). No hosted DR
   tool exposes an auditable, deterministic uncited-claim block.
5. **Routing engine is clean, pure, orthogonal, 85 tests** (`router.py`, `routing_constants.py`).
6. **Keyless scholarly breadth is real** — 7 live keyless academic APIs, `cost_per_search=0.0`.
7. **The team is honest in the source** — the code itself documents these limits
   (`golden.py:130-137`, `gate.py:196-205`); the marketing/eval surface is what contradicts it.

---

## What's weak or bullshit (verified, ranked)

1. **CRITICAL — ship-breaking install gap.** `bad-research-12.5-grader` is invoked on every
   full run (`bad-research.md:63,126,94`) but is **not** in `_BAD_RESEARCH_STEP_SKILLS` (20
   entries), and the installer prunes non-roster dirs. A full run hits an unresolvable skill;
   the judge→patch→re-judge loop never runs. *Fix: add the roster line + a guard test diffing
   entry-skill `Skill()` targets vs the roster.*
2. **CRITICAL — keyless faithfulness is a near-no-op in the high-stakes band, and the verify
   CLI requires a key anyway.** `LineSpanJudge` returns `entailment:1.0` with no model call
   when overlap ≥0.8 (`verifier.py:106-113`); the code admits the number-flip residual
   (`gate.py:196-205`). Worse: `bad verify-citations`/`grade-report` call
   `get_llm_provider("anthropic")` → `RuntimeError` without `ANTHROPIC_API_KEY`
   (`research.py:391,546`; `anthropic.py:48-53`) — so on a truly keyless box they error out.
   *Nuance: sub-0.8 paraphrases DO escalate to a host judge; the cited number-flip worked
   examples don't reproduce (overlap ~0.67). The flaw is real but phrasing-dependent.*
   *Fix: route numeric/negation sentences to the host judge regardless of overlap; implement
   a real host-model `LLMProvider` so verify runs keyless.*
3. **MAJOR — `pass_rate: 1.0` is circular self-grading with the hard cases removed.** 8 cases,
   every rationale the literal string "deterministic offline rubric"; rubric is presence checks
   (cite regex, ≥20% word overlap, ≥1 body line, URL contains "//"); the 2 adversarial
   fixtures are `requires_llm:true` and skipped on the keyless path (`golden.py:289`); the only
   real comparator always raises `BaselineUnavailable`. *4 of 6 lenses landed this
   independently.* *Fix: relabel as a determinism/regression smoke gate; wire a host judge into
   the adversarial fixtures; run a real head-to-head.*
4. **MAJOR — `55.9 vs 52.6` has no reproducible provenance.** Appears only at
   `bad-research.md:373` + internal docs; traces to upstream hyperresearch Q57/Q9 IDs. *Fix:
   delete from the user-facing skill or reproduce it; defend the design on compaction-resistance.*
5. **MAJOR — entry-skill drift: "4 critics" vs actual 5, "13 steps" vs 20/18.** Integrity gate
   checks only 4 critic-findings files (`:328-331`); step-12 spawns 5 (assumption critic,
   `hooks.py:1195`). No test pins the counts. *Fix: single-source the counts from one constant + test.*
6. **MINOR–MAJOR — README steers users into the slow path.** Zero hits for
   `--effort`/`--fast`/`--ultrafast`; names "~1.5–2.5h" as the automatic outcome; no
   progress/ETA UI anywhere. *(Refuted sub-claim: "effort=medium defaults to full" — route is
   set by `classify_route` + model-chosen `pipeline_tier`.)* *Fix: document the route levers;
   surface route + ETA before a long run.*
7. **MINOR — eyeball-scored 6-dimension utility table is dead scaffolding on the funnel path**
   (`width-sweep.md:144-159`); stale "7-phase/Layer/comparisons.md" prose in `hooks.py` agent
   text points at a renamed artifact (`tensions.md`).
8. **MINOR — Codex portability is 0% built and the spec has correctness bugs** (stale
   routes/roster, `Task(subagent_type=` literal matches zero real syntax, agent roster
   miscount, 3 CLI subcommands hard-require `ANTHROPIC_API_KEY` vs the "keyless" framing).

---

## Honest competitor positioning

**Genuinely wins (narrow, defensible slice):** keyless cost (no third-party metered key),
persistent/auditable/owned vault, deterministic uncited-claim ship-gate, keyless scholarly
recall, controllability (editable decomposition, plan-gate, route override).

**Loses:** speed (1.5–2.5h vs minutes; the competitive 5–15min `ultrafast` tier is
explicit-flag-only and undocumented in the README); live freshness/real-time breadth (no own
crawler); multimodal (hard lose — zero vision/figures/OCR); **proof** (the only numbers are a
self-graded `pass_rate 1.0` and an inherited 55.9/52.6).

**"Better than competitors" is defensible only on that narrow slice.** On the axes those
products are sold on — freshness, multimodal, speed, scale, *proof* — it ties at best and
usually loses. There is **no measurement anywhere in the repo** proving a win on any axis
against any named competitor.

---

## Prioritized roadmap

| # | Improvement | Impact | Effort | Track |
|---|---|---|---|---|
| 1 | Add `bad-research-12.5-grader` to the install roster + guard test (entry-skill `Skill()` targets vs roster) | High | Low | OPTIMIZE |
| 2 | Single-source critic count (5) + step count + integrity-gate file list; add a test | High | Low | OPTIMIZE |
| 3 | Document `--effort`/`--fast`/`--ultrafast` in README; recommend `ultrafast` as the try-it tier; surface route + ETA | High | Low | BEAT-COMPETITORS |
| 4 | Stop publishing `pass_rate 1.0` as a quality headline; relabel as a regression smoke gate | High | Low | OPTIMIZE |
| 5 | Remove the 55.9/52.6 line from the entry skill (or reproduce it) | High | Low | OPTIMIZE |
| 6 | Route numeric/date/negation sentences to the host judge regardless of ≥0.8 overlap | High | Med | OPTIMIZE |
| 7 | Implement a real host-model `LLMProvider` so verify/grade/calibrate run truly keyless | High | Med | OPTIMIZE |
| 8 | Build the injected-unsupported-claim recall harness; publish real recall/precision | High | Med | BEAT-COMPETITORS |
| 9 | Soften README/SPEC absolutes ("every claim verified", "no hallucinations") to match keyless reality | High | Low | OPTIMIZE |
| 10 | Wire the host LLMJudge into the 2 adversarial golden fixtures (un-skip `requires_llm`) | Med | Med | OPTIMIZE |
| 11 | Run ONE real head-to-head vs a commercial DR tool on 8–12 shared queries, blind/LLM-judged | High | High | BEAT-COMPETITORS |
| 12 | Replace hardcoded-fail StubLLM "semantic guard" tests with a recorded real-model cassette | Med | Low | OPTIMIZE |
| 13 | Cut/gate the eyeball-scored utility table; regenerate stale "7-phase/Layer/comparisons.md" agent prose | Med | Low | OPTIMIZE |
| 14 | Spike unverified Codex primitives (`spawn_agent` signature, `~/.codex/skills/` discovery, `multi_agent` flag) | High | Low | CODEX |
| 15 | Fix Codex dispatch (colon-form `subagent_type:`), roster (add assumption-critic), strip the `.claude/` bootstrap gate | High | Med | CODEX |
| 16 | Execute Codex plan Tasks 1–10 (translation → installer → leak-lint/idempotency tests → manual smoke) | High | Med | CODEX |

**Recommended sequencing:** (1) stop the bleeding + stop the over-claims (rows 1–5, 9 — all
low-effort, high-impact); (2) make the grounding claim true and the evidence non-circular (rows
6, 7, 8, 10); (3) prove it (row 11) and port to Codex (rows 14–16, spike primitives first).
