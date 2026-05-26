from tests.test_skills.validate import validate_skill

STAGES = [
    "bad-research-2-width-sweep.md",
    "bad-research-5-depth-investigation.md",
    "bad-research-11-synthesize.md",
    "bad-research-13-gap-fetch.md",
    "bad-research-16-readability-audit.md",
]


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
