from tests.test_skills.validate import validate_skill

STAGES = [
    "bad-research-2-width-sweep.md",
    "bad-research-5-depth-investigation.md",
    "bad-research-10-triple-draft.md",
    "bad-research-11-synthesize.md",
    "bad-research-13-gap-fetch.md",
    "bad-research-16-readability-audit.md",
]

# A-1: the generation-time grounding mandate marker. The drafter prompts carry an
# unambiguous "cite as you write — [N] before the terminal period" instruction so
# the downstream uncited-gate runs as a cheap VERIFIER (0-few blocks) rather than a
# heavy block-and-patch rewriter. Asserting the literal anchor keeps the frozen
# wording from silently drifting back to "draft now, ground later".
_GEN_GROUNDING_ANCHOR = "GENERATION-TIME GROUNDING"


def test_all_modified_stages_valid(skills_dir, known_skills):
    for s in STAGES:
        p = skills_dir / s
        assert p.exists(), s
        assert validate_skill(p, known_skills) == [], s


def test_width_sweep_calls_funnel(skills_dir):
    body = (skills_dir / "bad-research-2-width-sweep.md").read_text()
    assert "bad funnel-gather" in body
    assert "top_chunks" in body or "top-chunks" in body


def test_depth_uses_tiered_browse(skills_dir):
    body = (skills_dir / "bad-research-5-depth-investigation.md").read_text()
    assert "--tier-max" in body


def test_synthesize_renders_grounded_citations(skills_dir):
    body = (skills_dir / "bad-research-11-synthesize.md").read_text()
    assert "claim_anchors" in body or "grounded" in body.lower()
    assert "bad retrieve" in body  # synthesizer reads retrieval top-chunks


def test_gap_fetch_uses_tiered_browse(skills_dir):
    body = (skills_dir / "bad-research-13-gap-fetch.md").read_text()
    assert "--tier-max" in body


def test_step16_has_uncited_gate(skills_dir):
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    assert "bad uncited-gate" in body
    assert "ship-block" in body.lower() or "ship block" in body.lower()


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


# ── A-1: generation-time grounding (cite-as-you-write) in the drafter prompts ──

def test_step10_mandates_per_sentence_inline_cite_from_first_draft(skills_dir):
    body = (skills_dir / "bad-research-10-triple-draft.md").read_text()
    assert _GEN_GROUNDING_ANCHOR in body
    low = body.lower()
    # Unambiguous: a [N]/[[note-id]] citation before EVERY factual sentence's
    # terminal period, in the FIRST draft (not deferred to a later grounding pass).
    assert "before" in low and "terminal period" in low
    assert "first draft" in low or "as you write" in low
    assert "every factual sentence" in low


def test_step11_synthesizer_spawn_mandates_inline_cite_as_you_write(skills_dir):
    body = (skills_dir / "bad-research-11-synthesize.md").read_text()
    assert _GEN_GROUNDING_ANCHOR in body
    low = body.lower()
    assert "before" in low and "terminal period" in low
    assert "every factual sentence" in low
    # the gate's role becomes a cheap verifier, not a rewriter
    assert "verifier" in low


def test_gen_grounding_preserves_patch_not_regenerate(skills_dir):
    # The cite-as-you-write change must NOT weaken the patch-not-regenerate invariant.
    body = (skills_dir / "bad-research-11-synthesize.md").read_text()
    assert "patch-not-regenerate" in body or "patch not regenerate" in body.lower() \
        or "do not re-synthesize" in body.lower()


# ── B-8: citation coalescing in step 16 (readability, provenance-preserving) ──

def test_step16_mandates_citation_coalescing(skills_dir):
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    low = body.lower()
    # invokes the deterministic helper (not a hand-edit)
    assert "coalesce_citations" in body
    # the rule: collapse CONSECUTIVE sentences sharing the SAME source set
    assert "coalesc" in low
    assert "consecutive" in low
    assert "same source" in low or "identical source" in low or "same set" in low


def test_step16_coalescing_preserves_provenance_and_never_drops_source(skills_dir):
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    low = body.lower()
    # provenance preserved — explicitly forbids dropping any source
    assert "never drop a source" in low or "never drop" in low or "no source" in low \
        or "no provenance lost" in low
    assert "provenance" in low
    # a DISTINCT source must NOT be merged — keeps its own cite, breaks the run
    assert "distinct source" in low
    assert "never merge" in low or "never merges" in low or "not merge" in low \
        or "breaks the run" in low


def test_step16_coalescing_runs_after_both_gates(skills_dir):
    # must run AFTER uncited + recitation gates (gates validate per-sentence cites
    # first; coalescing only collapses the visual repetition afterwards)
    body = (skills_dir / "bad-research-16-readability-audit.md").read_text()
    low = body.lower()
    assert "after" in low and ("both gate" in low or "gates pass" in low
                               or "after the uncited" in low
                               or "after both gate" in low)
