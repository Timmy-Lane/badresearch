from __future__ import annotations


def _read(skills_dir, name: str) -> str:
    return (skills_dir / name).read_text(encoding="utf-8")


def test_synthesize_skill_has_line_start_line_end_evidence_fields(skills_dir):
    text = _read(skills_dir, "bad-research-11-synthesize.md")
    assert "line_start" in text, "synthesis-evidence.md format must include line_start field"
    assert "line_end" in text, "synthesis-evidence.md format must include line_end field"


def test_synthesize_skill_instructs_line_anchored_token(skills_dir):
    text = _read(skills_dir, "bad-research-11-synthesize.md")
    # The synthesizer spawn instructions must require the [[note-id:Lstart-Lend]] form
    assert "L" in text and ":L" in text, (
        "Step 11.6 spawn instructions must reference the [[note-id:Lstart-Lend]] format"
    )


def test_synthesize_skill_forbids_inventing_line_numbers(skills_dir):
    text = _read(skills_dir, "bad-research-11-synthesize.md")
    assert "Do NOT invent" in text or "do not invent" in text.lower(), (
        "Spawn instructions must tell synthesizer not to invent line numbers"
    )


def test_citation_verifier_skill_mentions_line_span_judge(skills_dir):
    text = _read(skills_dir, "bad-research-11.5-citation-verifier.md")
    assert "LineSpanJudge" in text, (
        "Step 11.5 skill must note that LineSpanJudge is the keyless Tier-B on the line-anchored path"
    )
