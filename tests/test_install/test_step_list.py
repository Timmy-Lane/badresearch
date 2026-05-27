from bad_research.core.hooks import _BAD_RESEARCH_STEP_SKILLS


def test_step_list_has_new_stages():
    s = set(_BAD_RESEARCH_STEP_SKILLS)
    assert "bad-research-0.5-clarify" in s
    assert "bad-research-query-router" in s
    assert "bad-research-agentic-fast" in s
    assert "bad-research-11.5-citation-verifier" in s
    assert "bad-research-fresh-review" in s
    # the original 16 kept (renamed)
    assert "bad-research-1-decompose" in s
    assert "bad-research-16-readability-audit" in s
    # ordering: clarify before decompose, router after decompose
    assert _BAD_RESEARCH_STEP_SKILLS.index("bad-research-0.5-clarify") < \
        _BAD_RESEARCH_STEP_SKILLS.index("bad-research-1-decompose")
    assert _BAD_RESEARCH_STEP_SKILLS.index("bad-research-1-decompose") < \
        _BAD_RESEARCH_STEP_SKILLS.index("bad-research-query-router")


def test_step_list_has_22_entries():
    # 16 kept + 5 prior new + 1 E11 plan-gate (bad-research-1.6-plan-gate)
    assert len(_BAD_RESEARCH_STEP_SKILLS) == 22
    assert len(set(_BAD_RESEARCH_STEP_SKILLS)) == 22  # no dupes
    assert "bad-research-1.6-plan-gate" in _BAD_RESEARCH_STEP_SKILLS
