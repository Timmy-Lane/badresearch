# 08 — Grounding / Anti-Hallucination / Verification / Citation Faithfulness

**Theme:** the no-hallucination pipeline for the enhanced hyperresearch fork. Every
sentence in a shipped report must trace to a **real retrieved chunk** by
`source_id + offset`, and a **re-grounding pass** must verify the span actually
supports the claim before the report finalizes. This dossier specifies the
claim→evidence binding, the verifier mechanism + model, contradiction handling,
per-claim confidence, and the no-uncited-claim lint gate — then orders them into
a single grounding pipeline mapped onto the existing 16-stage flow.

**Scope guard (don't re-derive what 01–06 settled).** Dossier 05 §4 + 06 §A1
already chose the *render* standard (Perplexity per-sentence single-index `[N]`
prose + OpenAI L-range grain + a CitationAgent pass) and the *on-disk* provenance
model (one note per source, `sources` table, SHA-256 content hash). This dossier
goes **one level deeper than render**: the *binding* (claim→span at character
granularity), the *verifier* (the actual entailment check + which cheap model),
the *contradiction surfacing* mechanics, the *confidence* numbers, and the
*lint gate code*. Where 05/06 said "add a re-grounding pass," this file is that
pass, spec'd to reimplementable depth.

Labels: **KNOWN** (from source/teardown), **INFERRED** (from probing/blogs),
**IDEA** (our design). Every mechanism ends **ADOPT** (where it plugs in) or
**CUT** (why it's verification-theater).

---

## 0. The five-source map — what each system contributes to grounding

| System | Binding grain | Verification | Confidence | Contradiction | Source |
|---|---|---|---|---|---|
| **Claude Research** | inline `[N]` → URL | **dedicated CitationAgent re-grounds every claim post-synthesis** (Haiku-class, INFERRED) | none (emits "claims requiring verification" appendix) | Synthesizer surfaces (failure-mode #7) | `CLAUDE_RESEARCH.md:280-302, §13-14` |
| **Gemini DR** | **byte-span `Segment{startIndex,endIndex}`** | `groundingSupports` binds each output segment to chunks; **RECITATION** decode-time tripwire blocks verbatim copying | **`confidenceScores[]`** per support (0.92, 0.88…) | not explicit | `GEMINI_DEEP_RESEARCH.md:836-894, R3.9` |
| **OpenAI DR** | **line-range `【cursor†L42-L58】`** (ChatGPT) / **char-offset `AnnotationURLCitation{start_index,end_index}`** (API) | RL-trained citation-grounding sub-task (offline) + "never cite a ref you didn't open" + "no URL extrapolation" | none | not explicit | `OPENAI_DEEP_RESEARCH.md:359-392, 766-772` |
| **Perplexity DR** | **char-span `Annotation{start_index,end_index,url}`** + per-sentence `[N]` | planner→writer split: **writer sees evidence (`search_results`), NOT planner CoT** | none | not explicit | `PERPLEXITY_DEEP.md:R3.6, R3.7, R3.8` |
| **hyperresearch** | `[[note-id]]` / `[N]` → vault note; **`claims-*.json` with verbatim `quoted_support`** | none in-pipeline (critics are adversarial, not entailment); R2 lint = density only | `confidence: high\|med\|low` per claim (claims JSON) | **contradiction-graph + source-tensions (surfaced, not averaged)** | `hooks.py:2696-2716`; skills `-3`, `-7`, `-8`, `-9` |

**The synthesis.** hyperresearch already has (a) the on-disk provenance store,
(b) per-claim confidence, and (c) the best contradiction-surfacing of all five.
It is **missing two things**: char-offset binding (it binds to a *note*, not a
*span* — Gemini/OpenAI/Perplexity all bind to a span) and an **entailment
verifier** (Claude's CitationAgent — the single highest-value import). This
dossier supplies both.

---

# 1. Claim→Evidence Binding

**The principle (KNOWN, OpenAI `ODR §20`, verbatim):** *"line-level citations
are not optional… any replica that cites at paragraph/article level will
hallucinate at the rate of pre-2025 browse models."* Coarse binding =
hallucination. Every shipped sentence must resolve to a **span**, not a document.

## 1.1 The binding substrate already exists — extend it to offsets (KNOWN→IDEA)

hyperresearch's fetcher already produces the right substrate. `claims-<note-id>.json`
(`hooks.py:2696-2716`, KNOWN) per source carries:

```json
{
  "claim": "one-sentence falsifiable statement",
  "stance": "supports|refutes|neutral",
  "stance_target": "what position this supports/refutes",
  "evidence_type": "empirical|theoretical|anecdotal|expert-opinion|statistical|legal|historical",
  "quoted_support": "verbatim quote from source, max 2 sentences — THIS IS THE MOST IMPORTANT FIELD",
  "numbers": ["specific numbers, thresholds, percentages"],
  "confidence": "high|medium|low",
  "source_note_id": "<note-id>"
}
```

The fetcher prompt already calls `quoted_support` *"the MOST IMPORTANT field …
a claim without a quoted passage is invisible downstream"* (`hooks.py:2705`,
verbatim KNOWN). **This verbatim quote is the load-bearing artifact** — it is the
half-built version of a span anchor. What's missing is the **offset of that quote
inside the note body**.

**IDEA — add three fields to the claims schema (the minimal change that buys
span-level binding):**

```json
{
  ...existing fields...,
  "char_start": 4192,            // byte/char offset of quoted_support in note body
  "char_end":   4317,            // exclusive end; char_end - char_start == len(quoted_support)
  "quote_sha":  "a3f9c1e2"       // 8-char SHA-256 of quoted_support — the byte-identity key
}
```

The fetcher already *has* the quote and the source text in context when it writes
`quoted_support`; computing `body.find(quoted_support)` → `(char_start, char_end)`
and `sha256(quoted_support)[:8]` is a deterministic post-step, **not an LLM call**.
If `body.find()` fails (quote was lightly normalized), fall back to a fuzzy locate
(rapidfuzz partial-ratio ≥ 95) and store the matched span; if even that fails, drop
the claim — *a claim whose quote isn't in the body is a hallucinated quote* and
must not enter the digest.

> **ADOPT.** Stage 2 (width-sweep fetcher) + Stage 5 (depth investigator). Both
> already emit `claims-*.json`; the offset-computation is a deterministic
> append. Zero extra LLM cost. This is the single change that turns hyperresearch
> from note-level to span-level binding, matching Gemini/OpenAI/Perplexity.

## 1.2 The on-disk citation anchor representation (IDEA, extends 06 §A1)

06 §A1 stores provenance in the `sources` table + note frontmatter. Add a
**citation-anchor index** keyed on the byte-identity of the quote, so the verifier
and the lint gate can resolve any `[N]`/`[[note-id]]` to its supporting span in O(1):

```sql
-- NEW table; sits beside sources(url PK, note_id, content_hash) from 06 §A1
CREATE TABLE claim_anchors (
  anchor_id   TEXT PRIMARY KEY,   -- == quote_sha (8-char SHA-256 of quoted_support)
  note_id     TEXT NOT NULL REFERENCES sources(note_id),
  char_start  INTEGER NOT NULL,
  char_end    INTEGER NOT NULL,
  claim       TEXT NOT NULL,      -- the falsifiable claim text
  quoted_support TEXT NOT NULL,   -- the verbatim span (the byte-identity payload)
  confidence  TEXT CHECK(confidence IN ('high','medium','low')),
  verified    INTEGER DEFAULT 0,  -- set 1 by the verifier (§2); 0 = unchecked
  verify_score REAL               -- entailment score 0.0-1.0 from §2
);
```

**Markdown remains truth (06 §A1 invariant).** `claim_anchors` is a *cache* rebuilt
from the `claims-*.json` files by `sync`. The report body cites `[[note-id]]`
(human render); the structured anchor `[N] → {note_id, char_start, char_end,
quote_sha}` is the verifiable map (the Perplexity `Annotation` / OpenAI
`AnnotationURLCitation` / Gemini `Segment` equivalent), stored out-of-band and
rendered into a clickable `[N]→span` map by the CLI/client (06 §A1 "Sources out of
band" rule).

> **ADOPT.** Materializes the 05 §4 "anchor (structured)" layer that was specified
> but had no storage. Reuses the existing `sources` table + `sync` rebuild
> discipline — no new infra.

## 1.3 The synthesizer constraint — writer-sees-evidence, not raw corpus (KNOWN, Perplexity)

**The Perplexity pattern (KNOWN, `PERPLEXITY_DEEP.md:R3.8`, verbatim-confirmed
across three dated leaked prompts):** Deep Research is a **two-system
planner→writer split**. The writer *"receives the planner's accumulated
`search_results` … NOT the planner's raw CoT"* and is *"explicitly told the user
hasn't seen the planner's work and the answer must be self-contained."* The writer
can only write what's in the evidence set it was handed — it never sees the loop's
reasoning, so it cannot launder an unsupported planner-thought into a "fact."

**How hyperresearch already mirrors this (KNOWN).** The synthesizer (Stage 11,
`-11-synthesize.md:146-199`) is a **fresh Opus session tool-locked to
`[Read, Write]`** — it *cannot* Bash the vault, *cannot* spawn fetchers, *cannot*
go re-search. Its inputs are a closed set: the 3 drafts, `comparisons.md`,
`source-tensions.json`, and crucially **`evidence-digest.md`** (the
`quoted_support` quotes grouped by atomic item, `-9-evidence-digest.md`). The
digest is described as *"primary evidence — higher-fidelity than fetcher
summaries"* (`-9:7`). This is exactly the Perplexity contract: **the writer's
ground truth is the curated evidence set, not the open web and not the
orchestrator's reasoning.**

**IDEA — tighten the constraint to "only-write-what's-in-evidence":** add one
clause to the synthesizer prompt (`-11:185`, after "synthesize in your own voice"):

```
EVIDENCE DISCIPLINE (hard rule):
Every factual sentence you write MUST be supported by a quoted_support passage
present in evidence-digest.md or a [[note-id]] in the vault. If you want to
assert something the evidence does not contain, you have two options ONLY:
(a) mark it as your synthesis/inference with an explicit hedge ("the evidence
    suggests", "no source directly states, but X and Y imply"), OR
(b) drop the sentence.
You may NOT assert a bare fact you cannot point to. Background/common-knowledge
framing sentences (definitions, transitions) are exempt — they carry no [N].
```

> **ADOPT.** Stage 11 synthesizer prompt. This is the *forward* defense (write
> grounded in the first place); §2 is the *backward* defense (verify after).
> Both are needed — the writer-sees-evidence constraint reduces the verifier's
> drop-rate, which keeps the verifier cheap.

## 1.4 Quote-budget / copyright discipline (KNOWN, multi-source)

Three systems converge on a verbatim-length cap to avoid reproducing copyrighted
text wholesale (and, incidentally, to force *paraphrase-with-citation* rather than
*paste*):

- **hyperresearch (KNOWN):** `quoted_support` is *"max 2 sentences"* (`hooks.py:2705`).
- **Perplexity (KNOWN):** writer prompt — *"do not produce copyrighted material
  verbatim"* (`PERPLEXITY_DEEP.md:R3.6`).
- **Gemini (KNOWN):** **RECITATION** is a *decode-time tripwire* — the model is
  blocked from emitting verbatim source text except for public-domain / direct
  user-input transcription / common phrases (`GEMINI §R3.9`, verbatim from the
  leaked `gemini-3.1-pro` prompt). Browse results carry a `paywall`/`unsafe`
  status the agent *"never quotes their text (RECITATION)"* (`GEMINI:2043-2045`).

**IDEA — adopt the cap as a binding rule, not the runtime tripwire.** Keep
`quoted_support ≤ 2 sentences AND ≤ 50 words` (hyperresearch + a hard word cap).
The report body never reproduces a `quoted_support` span verbatim — it paraphrases
and cites `[N]`; the verbatim quote lives only in the off-band anchor for the
verifier. This gives RECITATION's protection (no verbatim copying into output)
without RECITATION's machinery (a decode-time logit filter on Google's stack we
can't replicate).

> **ADOPT** the ≤2-sentence/≤50-word `quoted_support` cap (cheap, deterministic).
> **CUT** Gemini's runtime RECITATION decode-time tripwire — it requires
> training-time/decoder-level control we don't have on a hosted API. The
> length-cap + "paraphrase don't paste" synthesizer rule (§1.3) achieves
> the same output guarantee structurally.

---

# 2. Re-Grounding / Verification Pass (the CitationAgent)

**The single highest-value import.** Claude Research's verdict (KNOWN,
`CLAUDE_RESEARCH.md` failure-mode #8 + `§24 #6`): *"A dedicated CitationAgent is
non-negotiable; citation hallucination is the single largest correctness risk."*
hyperresearch has **no entailment verifier** — its critics (Stage 12) are
adversarial reviewers, not span-checkers. This is the gap §2 closes.

## 2.1 What the CitationAgent does (KNOWN structure, Claude Research §8)

A **separate, late-stage agent** reads `(draft_report, source_corpus)` and
*"produces a final report where every factual claim is followed by a citation
linking to the source's URL … if no source supports a claim, emit a `[???]`
marker and add a 'Claims requiring verification' appendix"* (`CLAUDE_RESEARCH.md:284-302`,
inferred structural template). It runs **AFTER synthesis, as a pure
grounding/verification pass** — not during drafting. Model: **Haiku-class** —
*"citation attribution is high-volume, low-reasoning"* (`:302`, INFERRED).

## 2.2 The exact mechanism — three-tier verification per claim (IDEA, reimplementable)

For each cited sentence in the final report (`[N]` or `[[note-id]]`), resolve its
anchor (`§1.2`) to get `(quoted_support, char_start, char_end, note_id)`, then run
the **cheapest check that can pass; escalate only on failure:**

**Tier A — byte-identity check (free, no LLM).** Confirm the anchor's
`quoted_support` still appears at `[char_start:char_end]` of the live note body
(re-`find` + SHA match `quote_sha`). This catches anchor drift / fabricated quotes.
Pass → tier B; fail → the quote isn't in the source → **drop the claim** (it's a
hallucinated quote). This is the Gemini/OpenAI rule *"never cite a ref you didn't
open / no URL extrapolation"* (`ODR §9`, `GEMINI:890`) made executable.

**Tier B — NLI entailment check (cheap model).** Does the `quoted_support` span
**entail** the claim sentence as written in the report? This is the substantive
faithfulness check — the quote exists, but does it actually *support what the
report says*? Two implementation options:

- **Option 1 — local NLI model (CHEAPEST, recommended default).** A cross-encoder
  NLI model — `cross-encoder/nli-deberta-v3-base` (or `MoritzLaurer/
  deberta-v3-base-mnli-fever-anli`) — run locally, ~80MB, CPU-fine, **$0/claim**.
  Input `premise = quoted_support`, `hypothesis = report_sentence`; output
  `{entailment, neutral, contradiction}` softmax. Decision:
  `entailment ≥ 0.70` → PASS; `contradiction ≥ 0.50` → **FLAG hard** (the source
  says the *opposite*); else `neutral` → soft-flag (unsupported).
- **Option 2 — LLM-judge (when no GPU/local model, or for nuanced claims).**
  A single Haiku-class call (`claude-haiku` / `gpt-4.1-mini` / `gemini-flash`)
  batched ~20 claims per call:

```
You are the CitationVerifier. For each numbered (CLAIM, QUOTE) pair, decide if the
QUOTE supports the CLAIM. Output JSON only: [{id, verdict, score, reason}].
- verdict ∈ {supported, partial, unsupported, contradicted}
- score ∈ 0.0-1.0 (confidence the quote supports the claim AS WRITTEN)
- A QUOTE "supports" a CLAIM only if a careful reader, seeing ONLY the quote,
  would agree the claim follows. Numbers must match exactly. Do NOT use outside
  knowledge. If the claim adds a number/entity/scope absent from the quote →
  partial or unsupported. If the quote states the opposite → contradicted.

PAIRS:
[{id:1, claim:"<report sentence>", quote:"<quoted_support>"}, ...]
```

**Tier C — re-fetch arbitration (rare, expensive).** Only when tier B returns
`contradicted` on a `severity:critical` claim: re-fetch the source span fresh
(the page may have changed) and re-run tier B. If still contradicted → the
report is wrong; route to the patcher (§5) with the contradicting evidence.

## 2.3 Drop / flag / keep — the disposition (IDEA)

| Tier B verdict | score | Disposition before final |
|---|---|---|
| `supported` | ≥ 0.70 | KEEP; set `claim_anchors.verified=1`, `verify_score=score` |
| `partial` | 0.40–0.70 | **soft-flag**: keep the sentence but downgrade its confidence (§4) and emit an inline uncertainty marker if non-trivial |
| `unsupported` | < 0.40 | **DROP the citation**; if the sentence is non-trivial and now uncited, route to patcher to (a) find a real cite in vault or (b) hedge/cut |
| `contradicted` | any | **HARD-flag → contradiction handling (§3)** + patcher; never silently keep |

**Model choice (KNOWN+IDEA):** Claude Research uses **Haiku-class** for the
CitationAgent (`:302`). Our default is **local NLI (tier B option 1) = $0**, with
the **Haiku/Flash LLM-judge as the fallback** for pairs the NLI model scores in
the `neutral` band (it's the ambiguous middle where a tiny LLM beats a base NLI
model). This is the cost-correct split: 90%+ of claims resolve on the free local
model; only the ambiguous ~10% pay for an LLM call. A 5,000-word report has
~150–250 cited sentences → at most ~25 LLM-judge calls, batched into ~2 Haiku
requests. **Total verification cost: cents.**

> **ADOPT.** New **Stage 11.5 — CitationVerifier**, runs immediately after the
> synthesizer (Stage 11) and BEFORE the critics (Stage 12). Why before critics:
> a dropped/flagged claim should be *visible to the critics* so the dialectic/
> depth critics can react to "this got flagged unsupported," and the patcher
> (Stage 14) fixes verifier-flags and critic-findings in one pass. Tool-lock the
> verifier subagent to `[Read]` (it reads the report + anchors, writes a findings
> JSON via the orchestrator) — it must not edit the report directly (patch-not-
> regenerate invariant, 06 §A1).

## 2.4 Why this is NOT verification-theater

The cheap-first cascade is the discipline. The failure mode to avoid is "run a
big LLM over the whole report asking 'are the citations right?'" — that's
expensive, non-deterministic, and gives a vibe not a verdict. Tier A (free,
deterministic byte-identity) catches *fabricated quotes* — the most dangerous
hallucination — at zero cost. Tier B (local NLI, $0) catches the *quote-exists-
but-doesn't-support* case. Only the genuinely ambiguous middle escalates to a
paid model. The per-claim disposition table makes the output **actionable** (drop/
flag/keep with a patcher route), not a scalar "82% grounded" that nobody can act
on.

---

# 3. Contradiction Handling — surface, don't average

**The anti-pattern (IDEA, from 05 §11):** averaging two contradicting sources into
a mushy middle ("estimates range from 3% to 15%") destroys the signal. The
frontier-DR approach and hyperresearch's approach both **surface the fork
explicitly** and **commit to a reading**.

## 3.1 hyperresearch already wins this dimension (KNOWN — keep it)

hyperresearch has the **best contradiction machinery of all five systems**, via
three skills that the other DR products lack entirely:

- **Stage 3 — contradiction-graph (`-3-contradiction-graph.md`, KNOWN).** Pairs
  contradicting claims across sources by `stance_target`+opposite `stance`, same
  `entities`+opposite conclusions, same scope+different `numbers`. Clusters them
  into **"fights"** with `{side_a, side_b, evidence_quality_delta, scope_overlap,
  decision_relevance}`. Loci then *"emerge from where the evidence actually forks,
  not from agent intuition"* (`-3:16`). Also emits **`consensus-claims.json`** —
  claims where **3+ independent sources agree** = *"settled ground the draft can
  assert confidently without hedging"* (`-3:58`).
- **Stage 7 — source-tensions (`-7-source-tensions.md`, KNOWN).** Reads the **full
  bodies** of the top 8–12 sources (not summaries — *"tensions hide in nuance that
  summaries flatten"*, `-7:37`), extracts 3–7 expert disagreements, and for each
  **pre-commits to a resolution** with a load-bearing reason. Becomes a
  **mandatory Source Tensions section** in the report (`-7:84`).
- **Stage 8 — corpus-critic (`-8-corpus-critic.md`, KNOWN).** Asks *"what source,
  if found, would overturn the current direction?"* (`-8:16`) and runs a targeted
  fetch wave. If counter-evidence is found → downgrade the position's confidence;
  if the adversarial search returns nothing → *"the committed position gains
  confidence"* (`-8:112`). This is **falsification-driven grounding** — exactly
  the "what would overturn this?" discipline.

## 3.2 Wire contradictions into the verifier and confidence (IDEA)

The new piece: when the CitationVerifier (§2) returns `contradicted` on a claim,
it must **cross-reference the contradiction-graph** rather than just dropping. The
flag carries the `cluster_id` if the contradicted claim is part of a known fight.
This connects the post-synthesis verifier to the pre-draft contradiction analysis:

```
On verifier verdict == "contradicted":
  1. Look up the claim in contradiction-graph.json by stance_target/entities.
  2. If it's a known fight cluster → the draft picked a side that a source
     contradicts. Route to patcher with BOTH sides' quoted_support; the patcher
     either (a) re-commits to the better-evidenced side per evidence_quality_delta,
     or (b) converts the assertion into an explicit "sources disagree" sentence
     citing both [N].
  3. If it's NOT a known fight → a new contradiction the pre-draft analysis missed.
     Append it to contradiction-graph.json and surface it in the report.
```

> **ADOPT.** Keep Stages 3/7/8 verbatim — they are the strongest part of the
> existing pipeline and need no change. **ADD** the verifier→contradiction-graph
> back-reference (§3.2) so post-synthesis contradiction discovery feeds the same
> surface-don't-average machinery. The rule throughout: **a contradiction is a
> finding to present, never a number to average.**

---

# 4. Confidence Scoring — per-claim, propagated to the report

**The model (KNOWN, Gemini):** `groundingSupports[].confidenceScores: [0.92, 0.88]`
— a parallel-length array binding each segment to a confidence per supporting
chunk (`GEMINI:879`). hyperresearch already has a **3-level** confidence on every
claim (`confidence: high|medium|low`, `hooks.py:2710`). We combine them: the
fetcher's *source-asserted* confidence × the verifier's *entailment* score = a
**propagated per-claim confidence** that drives hedging language in the report.

## 4.1 The confidence function (IDEA)

```
final_confidence(claim) =
    f(fetcher_confidence ∈ {high:1.0, medium:0.6, low:0.3},
      verify_score      ∈ [0,1]        # from §2 tier B
      n_independent_sources)            # from consensus-claims.json (§3.1)

# rule of thumb:
high   : fetcher=high AND verify_score≥0.70 AND n_sources≥2   → assert plainly, no hedge
medium : verify_score 0.40-0.70 OR n_sources==1               → "evidence suggests / one source reports"
low    : verify_score<0.40 OR fetcher=low                     → "preliminary / unverified / a single commentary claims"
```

## 4.2 How confidence shows in the output (IDEA, calibrated to Perplexity hedging)

- **high** → bare assertion + `[N]`. (Matches hyperresearch's *"settled ground,
  assert without hedging"* for 3+ source consensus, `-3:58`.)
- **medium** → hedged assertion ("the evidence suggests…", "one analysis finds…")
  + `[N]`.
- **low** → explicit uncertainty marker + `[N]`; collected into an optional
  **"Lower-confidence / single-source claims"** note (the structured analog of
  Claude Research's *"Claims requiring verification" appendix*, `CLAUDE_RESEARCH.md:299`).

**Store it.** `claim_anchors.verify_score` (§1.2) + a derived `confidence_band`
column persist this. The CLI can render a confidence chip per `[N]` (Gemini's UI
pattern) without putting noise in the prose.

> **ADOPT.** Compute `final_confidence` in the CitationVerifier (§2 already has
> `verify_score` and reads the claims' fetcher-confidence + consensus count).
> Feed the band into the patcher so it can *add hedges to medium/low claims that
> the synthesizer asserted too confidently* — this is a concrete, evidence-driven
> patcher finding, not a vibe. **CUT** any attempt to surface raw 0.0–1.0 scores
> in the prose body — readers want the hedge word, not the number; keep the number
> off-band for the CLI/audit only (Gemini keeps confidenceScores in metadata, not
> prose — follow that).

---

# 5. The No-Uncited-Claim Gate (final lint)

**Extend hyperresearch's existing lint.** The pipeline already has **R2 — citation
density** (`hooks.py:1126-1133`, KNOWN): *"Count inline `[N]` citations in the body
… if the ratio is below **1.5 citations per 1000 characters**, emit
`low-citation-density`."* This is a *density* check — it catches a section that's
under-cited on average. It does **not** catch a specific non-trivial sentence that
makes a hard factual claim with **zero** citation. That's the gap the gate closes.

## 5.1 The gate spec (IDEA — a hard pass/fail, extends R2)

A **deterministic lint** (Python, no LLM) run as the **final step before ship**,
after polish (Stage 15/16). It fails the report if any **non-trivial claim**
lacks a **verifiable** citation:

```python
def no_uncited_claim_gate(report_md, claim_anchors) -> list[Finding]:
    findings = []
    for sent in split_sentences(strip_sources_section(report_md)):
        if not is_factual_claim(sent):        # skip transitions, definitions, questions
            continue
        cites = extract_citations(sent)        # [[note-id]] or [N] tokens in/adjacent to sentence
        if not cites:
            findings.append(Finding("uncited-claim", "critical", sent,
                "Non-trivial factual sentence carries no citation."))
            continue
        for c in cites:
            anchor = claim_anchors.get(resolve(c))
            if anchor is None:
                findings.append(Finding("dangling-cite", "critical", sent,
                    f"Citation {c} resolves to no claim_anchor."))
            elif anchor.verified != 1:
                findings.append(Finding("unverified-cite", "major", sent,
                    f"Citation {c} was not confirmed by the CitationVerifier."))
    return findings
```

**`is_factual_claim` (the trivia filter — what makes the gate sane).** A sentence
is a *non-trivial factual claim* if it contains a number, a named entity, a
comparative/superlative, a causal/temporal assertion, or a quantified claim — and
is NOT a section transition, a definition the report itself introduces, a question,
or a meta-sentence ("This report covers…"). Heuristic + a tiny allowlist of
hedge-frame openers ("In general,", "Broadly,") that are exempt. This mirrors
OpenAI's *"Line-level citations: `【ref†L{start}-L{end}】` after each **non-trivial**
claim"* (`ODR §inner prompt`, verbatim) — the word *non-trivial* is load-bearing;
a gate that demands a cite on *every* sentence is unusable (transitions, framing).

## 5.2 The gate's three failure modes (IDEA)

| Failure | Severity | Meaning | Fix route |
|---|---|---|---|
| `uncited-claim` | critical | factual sentence, no `[N]` at all | patcher: find a vault cite or hedge/cut |
| `dangling-cite` | critical | `[N]` points at no anchor (fabricated index) | patcher: remove or repoint to real anchor |
| `unverified-cite` | major | `[N]` resolves but `verified≠1` (verifier never passed it) | patcher: re-run §2 tier B on it, or hedge |

A run **does not ship** with any `critical` finding open. This is the belt to the
R2 density check's suspenders: **density** ensures broad coverage; **the gate**
ensures no specific hard claim slips through uncited or with a fabricated/unverified
index.

## 5.3 Why a deterministic gate (not an LLM)

The gate is pure string + table work: sentence-split, citation-token extract,
anchor lookup, `verified` flag check. **No LLM, $0, fully reproducible.** The
*judgment* (does the quote support the claim?) was already spent in §2's verifier;
the gate just enforces that every shippable claim *went through* the verifier and
*passed*. Putting an LLM in the final gate would be theater — it would re-litigate
what §2 already decided, non-deterministically.

> **ADOPT.** New **R5 lint check** in `hooks.py` (sibling to R1–R4), run in the
> readability-audit/polish phase (Stage 16). Wire it as a hard gate: any open
> `critical` blocks `ship`. Extends the existing lint architecture — same
> `Finding{failure_mode, severity, location, recommendation}` shape the patcher
> already consumes.

---

# 6. The Ordered Grounding Pipeline (where each step sits in the stage flow)

Mapping every grounding mechanism onto the existing 16-stage hyperresearch flow
(stage numbers from dossier 01 §1.1). **New stages/checks marked ★.**

```
STAGE                         GROUNDING MECHANISM                              §    KNOWN/IDEA
─────────────────────────────────────────────────────────────────────────────────────────
1  decompose                  citation_style chosen; required headings         06   KNOWN
2  width-sweep (fetchers)  ★  claims-*.json + quoted_support + ADD char_start/  1.1  KNOWN+IDEA
                               char_end/quote_sha (offset binding); ≤2-sent cap 1.4
3  contradiction-graph        fight clusters + consensus-claims.json           3.1  KNOWN
   (build claim_anchors    ★  sync claims-*.json → claim_anchors table)        1.2  IDEA
5  depth-investigation     ★  same offset binding on depth claims              1.1  KNOWN+IDEA
7  source-tensions            expert disagreements, committed resolution       3.1  KNOWN
8  corpus-critic              "what would overturn this?" falsification         3.1  KNOWN
9  evidence-digest            quoted_support grouped by atomic item (writer's   1.3  KNOWN
                               ground truth — the writer-sees-evidence input)
10 triple-draft               drafts cite [[note-id]] per sentence             —    KNOWN
11 synthesize             ★  evidence-discipline clause: only-write-what's-in- 1.3  KNOWN+IDEA
                               evidence (writer sees digest, not orchestrator CoT)
11.5 CitationVerifier     ★★ THE re-grounding pass:                            2    IDEA
                               A byte-identity (free) → B NLI entailment (local,
                               $0; Haiku fallback for neutral band) → C re-fetch
                               arbitrate. Drop/flag/keep per claim. Sets
                               claim_anchors.verified + verify_score.
                               Compute final_confidence + band.                4
   (contradiction back-ref ★  verifier "contradicted" → contradiction-graph)   3.2  IDEA
12 critics (×4)               adversarial; now also react to verifier flags    —    KNOWN
13 gap-fetch                  fetch sources for flagged-unsupported claims     —    KNOWN
14 patcher                ★  fixes critic findings + verifier flags + adds     2.3  KNOWN+IDEA
                               hedges to medium/low-confidence claims          4.2
15 polish                     paraphrase-not-paste; quote-cap enforced         1.4  KNOWN
16 readability-audit      ★  R2 density (KNOWN) + R5 no-uncited-claim gate     5    KNOWN+IDEA
                               (hard pass/fail; critical blocks ship)
─────────────────────────────────────────────────────────────────────────────────────────
```

**The two forward defenses + two backward defenses (the spine):**

1. **Forward — binding at fetch (Stage 2/5):** every claim is born with a verbatim
   quote + offset. A claim with no locatable quote never enters the corpus.
2. **Forward — writer-sees-evidence (Stage 11):** the synthesizer can only write
   from the evidence digest, never from the orchestrator's reasoning. Reduces
   hallucination at the source.
3. **Backward — entailment verifier (Stage 11.5):** every cited claim is checked
   (free byte-identity → free local NLI → paid Haiku only for the ambiguous middle).
   Drops fabricated quotes, flags unsupported claims, surfaces contradictions.
4. **Backward — deterministic gate (Stage 16):** no non-trivial claim ships
   uncited, dangling, or unverified. $0, reproducible, hard pass/fail.

Forward defenses *reduce* what the backward defenses must catch (keeping them
cheap); backward defenses *guarantee* what forward defenses can't (catching the
residual). Neither alone is sufficient — together they are the no-hallucination
contract.

---

# 7. ADOPT / CUT Ledger (every mechanism, one line)

| # | Mechanism | Source | Verdict | Where it plugs in |
|---|---|---|---|---|
| 1 | Offset binding (`char_start/end`, `quote_sha`) on claims | IDEA (extends hooks.py:2696) | **ADOPT** | Stage 2/5 fetcher — deterministic, $0 |
| 2 | `claim_anchors` SQLite table (rebuilt by sync) | IDEA (extends 06 §A1) | **ADOPT** | Stage 3, beside `sources` table |
| 3 | Writer-sees-evidence-not-CoT | KNOWN Perplexity R3.8 + hyperresearch S11 | **ADOPT** | Stage 11 (already true; tighten prompt) |
| 4 | "Only-write-what's-in-evidence" clause | IDEA | **ADOPT** | Stage 11 synthesizer prompt |
| 5 | `quoted_support` ≤2-sentence/≤50-word cap | KNOWN hyperresearch + Perplexity | **ADOPT** | Stage 2 fetcher + Stage 15 polish |
| 6 | RECITATION decode-time tripwire | KNOWN Gemini R3.9 | **CUT** | needs decoder-level control we lack; §1.4 length-cap + paraphrase rule achieves the output guarantee |
| 7 | CitationVerifier tier A (byte-identity) | IDEA (executes ODR §9 / GEMINI:890) | **ADOPT** | Stage 11.5 — free, catches fabricated quotes |
| 8 | CitationVerifier tier B (local NLI default) | IDEA (executes Claude CitationAgent) | **ADOPT** | Stage 11.5 — $0, cross-encoder NLI |
| 9 | CitationVerifier tier B fallback (Haiku/Flash LLM-judge) | KNOWN Claude (Haiku-class) | **ADOPT** | Stage 11.5 — only for NLI-neutral band, ~cents/report |
| 10 | CitationVerifier tier C (re-fetch arbitration) | IDEA | **ADOPT (gated)** | Stage 11.5 — only `contradicted`+`critical`; rare |
| 11 | Drop/flag/keep disposition table | IDEA (extends Claude `[???]` appendix) | **ADOPT** | Stage 11.5 → feeds patcher |
| 12 | contradiction-graph + consensus-claims | KNOWN hyperresearch S3 | **ADOPT (keep)** | Stage 3 — best of all five; no change |
| 13 | source-tensions (full-body, committed resolution) | KNOWN hyperresearch S7 | **ADOPT (keep)** | Stage 7 — no change |
| 14 | corpus-critic "what would overturn this?" | KNOWN hyperresearch S8 | **ADOPT (keep)** | Stage 8 — no change |
| 15 | verifier→contradiction-graph back-reference | IDEA | **ADOPT** | Stage 11.5 → Stage 14 |
| 16 | Per-claim `final_confidence` (fetcher × verify × n_sources) | IDEA (Gemini confidenceScores) | **ADOPT** | Stage 11.5 computes; Stage 14 hedges |
| 17 | Confidence as hedge-word (not raw number) in prose | KNOWN Gemini (meta not prose) | **ADOPT** | Stage 14; number off-band only |
| 18 | R5 no-uncited-claim gate (deterministic) | IDEA (extends R2 hooks.py:1126) | **ADOPT** | Stage 16 — hard ship gate, $0 |
| 19 | LLM in the final gate | — | **CUT** | re-litigates §2 non-deterministically = theater |
| 20 | "Claims requiring verification" appendix | KNOWN Claude `:299` | **ADOPT (as note)** | low-confidence claims collected off-band |

**Net cost of the whole grounding layer per report:** offset binding $0 (fetcher
post-step), tier A $0 (string ops), tier B $0 (local NLI) + ~cents (Haiku fallback
on ~10% of claims), gate $0 (string ops). The only paid component is the Haiku
fallback on the NLI-neutral band — **single-digit cents on a multi-dollar research
run.** The faithfulness gain (no fabricated quotes can ship, every hard claim
verified-or-dropped) is the entire point of the product; this is the cheapest place
in the pipeline to buy it.

---

# 8. Honest gaps / open items

- **NLI model choice is INFERRED-best, not benchmarked here.** `nli-deberta-v3-base`
  vs `deberta-v3-base-mnli-fever-anli` vs a small fine-tuned judge should be
  calibrated against a frozen set of (claim, quote, human-label) triples before
  committing the 0.70/0.40 thresholds. The thresholds are starting points.
- **`is_factual_claim` heuristic** (§5.1) is the gate's weakest link — too strict
  → false-fail on framing sentences; too loose → misses bare claims. Needs tuning
  on real reports; a tiny LLM classifier is the escape hatch if the heuristic
  proves brittle (but keep it OUT of the hot gate — run it once to label, cache).
- **Claude's CitationAgent prompt is INFERRED** (`CLAUDE_RESEARCH.md:284`, blog
  doesn't give it). Our §2 verifier is a reconstruction of its *function*, not its
  exact prompt. The function (re-ground every claim, emit `[???]` for unsupported)
  is KNOWN; the implementation is ours.
- **Gemini's `confidenceScores` semantics are opaque** — Google doesn't document
  what the 0.92 *means* (P(relevant)? P(authoritative)?). We use our own
  `verify_score` (entailment) instead of trying to replicate Google's signal.
- **Perplexity planner prompt** (the system that decides what to fetch) only leaked
  Oct-2025 (`PERPLEXITY_DEEP.md:R4.1`); not load-bearing for grounding (the
  *writer* prompt is, and that's KNOWN).
