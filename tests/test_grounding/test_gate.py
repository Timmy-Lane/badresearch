from __future__ import annotations

import sqlite3

from bad_research.grounding.anchors import AnchorStore, ClaimAnchor
from bad_research.grounding.gate import (
    gate_blocks_ship,
    is_factual_claim,
    no_uncited_claim_gate,
)


def _store_with(anchors):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for a in anchors:
        store.upsert(a)
    return store


def test_is_factual_claim_filters_trivia():
    assert is_factual_claim("Latency dropped to 12.4 ms under load.") is True   # number
    assert is_factual_claim("Vietnam led Southeast Asia in penetration.") is True  # named entity + superlative
    assert is_factual_claim("This report covers three regions.") is False       # meta-sentence
    assert is_factual_claim("What drives adoption?") is False                   # question
    assert is_factual_claim("In general, markets vary.") is False               # hedge-frame opener


def test_is_factual_claim_exempts_verdict_lines():
    # #18: verdict/summary labels (Bottom line:, Key takeaway:, In short:) are
    # synthesis lines whose grounding lives in the cited body (doctrine:
    # triple-draft.md:140 — "executive-summary topic sentence ... non-factual by
    # the gate's own classifier"). They must NOT be flagged as uncited-claim, even
    # when carrying leading markdown bold chrome.
    assert is_factual_claim("**Bottom line:** Vietnam leads at 64% penetration.") is False
    assert is_factual_claim("Bottom line: adoption grew 12.4% in 2024.") is False
    assert is_factual_claim("Key takeaway: Indonesia trails the region.") is False
    assert is_factual_claim("In short: the market doubled.") is False
    # a plain framing opener is non-factual by the classifier (pre-existing stem rule)
    assert is_factual_claim("This section examines the 2024 GMV data.") is False


def test_is_factual_claim_still_flags_real_body_claim_after_exemptions():
    # Guard against over-exemption: an ordinary body claim with a number/entity
    # still flags — the verdict carve-out keys on the OPENING label only.
    assert is_factual_claim("Vietnam's GMV grew 64% in 2024.") is True
    assert is_factual_claim("The bottom line of the chart sits at 64%.") is True  # not an opener
    # Review-hardening: block-level chrome ('>') is NOT stripped for the generic
    # framing stems, so a block-quoted claim can't hide behind a meta opener.
    assert is_factual_claim("> This section recorded a 31% rise in 2024.") is True


def test_gate_fails_report_with_uncited_factual_claim():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024.\n"  # hard number, no [N]
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "uncited-claim" and f.severity == "critical" for f in findings)
    assert gate_blocks_ship(findings) is True


def test_gate_passes_fully_cited_verified_report():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 1
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert findings == []
    assert gate_blocks_ship(findings) is False


def test_gate_flags_dangling_cite():
    store = _store_with([])
    report = "Southeast Asian GMV grew 12.4% in 2024. [[no-such-anchor]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "dangling-cite" and f.severity == "critical" for f in findings)


def test_gate_flags_unverified_cite():
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 0  # resolves but verifier never passed it
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% in 2024. [[{a.anchor_id}]]\n"
    findings = no_uncited_claim_gate(report, store)
    assert any(f.failure_mode == "unverified-cite" and f.severity == "major" for f in findings)
    # major alone does not block ship.
    assert gate_blocks_ship(findings) is False


def test_gate_ignores_sources_section():
    store = _store_with([])
    report = (
        "This report covers three regions.\n"
        "## Sources\n"
        "1. https://example.com  Some uncited claim with a number 42 here.\n"
    )
    findings = no_uncited_claim_gate(report, store)
    assert findings == []


# ── A-2: harden the splitter against formatting false-positives ──────────────

def test_split_skips_bold_only_pseudo_heading():
    # A bold-only line `**Market Size in 2024**` is a pseudo-heading, not a claim.
    from bad_research.grounding.gate import split_sentences

    out = split_sentences("**Market Size in 2024**\n")
    assert out == []


def test_split_skips_markdown_headings_of_every_level():
    from bad_research.grounding.gate import split_sentences

    out = split_sentences("## Regional Trends in 2024\n###### Sub-finding 12.4%\n")
    assert out == []


def test_split_skips_table_rows():
    from bad_research.grounding.gate import split_sentences

    table = (
        "| Region | GMV 2024 | Growth |\n"
        "| --- | --- | --- |\n"
        "| Vietnam | 64% | leading |\n"
    )
    assert split_sentences(table) == []


def test_split_skips_code_fence_and_inline_only_span():
    from bad_research.grounding.gate import split_sentences

    block = (
        "```python\n"
        "x = 12.4  # this is code, not a claim about Vietnam\n"
        "```\n"
        "`SUPPORTED_FLOOR = 0.70`\n"
    )
    assert split_sentences(block) == []


def test_split_strips_list_marker_keeps_item_as_one_sentence():
    # `1. Vietnam led at 64%.` must be ONE sentence, not the fragment `1.` + rest.
    from bad_research.grounding.gate import split_sentences

    out = split_sentences("1. Vietnam led Southeast Asia at 64% penetration.\n")
    assert len(out) == 1
    assert out[0].startswith("Vietnam")
    # bullet markers too
    assert split_sentences("- Indonesia grew 12.4% in 2024.\n")[0].startswith("Indonesia")
    assert split_sentences("* Thailand fell 3% that year.\n")[0].startswith("Thailand")


def test_gate_ignores_formatting_chrome_but_flags_real_uncited():
    # A formatting-heavy report: bold heading + heading + table + a cited list item
    # whose [N] PRECEDES the period -> all clean; ONE genuinely uncited list item flags.
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 1
    store = _store_with([a])
    report = (
        "**Key Findings for 2024**\n"
        "## Regional Breakdown\n"
        "| Region | Growth |\n"
        "| --- | --- |\n"
        "| Vietnam | 64% |\n"
        f"- Southeast Asian GMV grew 12.4% [[{a.anchor_id}]] in 2024.\n"  # cite BEFORE period
        "- Indonesia reportedly led the region at 71% penetration.\n"     # genuinely uncited
    )
    findings = no_uncited_claim_gate(report, store)
    # Exactly one block: the Indonesia line (everything else is chrome or cited).
    assert len(findings) == 1
    assert findings[0].failure_mode == "uncited-claim"
    assert "Indonesia" in findings[0].location


def test_gate_accepts_citation_before_terminal_period():
    # `... grew 12.4% [[anchor]] in 2024.` — the [N] precedes the period.
    quote = "a 12.4% YoY expansion"
    a = ClaimAnchor("n12", 0, len(quote), "SEA GMV grew 12.4%.", quote)
    a.verified = 1
    store = _store_with([a])
    report = f"Southeast Asian GMV grew 12.4% [[{a.anchor_id}]] in 2024.\n"
    findings = no_uncited_claim_gate(report, store)
    assert findings == []


# ── A-6: _BOLD_SPAN_ONLY guard + verify_score<PARTIAL_LOW promotion ──────────

from bad_research.grounding.gate import _is_formatting_line


def test_is_formatting_line_bold_span_only():
    # A line that is entirely bold prose (but NOT a bold heading) should be
    # detected as formatting by the new _BOLD_SPAN_ONLY guard.
    # Note: existing _BOLD_ONLY catches `**...**` whole-line; this guard catches
    # lines like "**some mid-sentence bold fragment**" that aren't headings.
    assert _is_formatting_line("**Important finding:**") is True
    assert _is_formatting_line("**Key Findings 2024**") is True  # already caught


def test_is_formatting_line_does_not_flag_partial_bold():
    # A line that has bold inside a real sentence is NOT a formatting line.
    assert _is_formatting_line("The study found **12.4%** growth in 2024.") is False


def test_gate_promotes_unsupported_anchor_below_partial_low_to_critical():
    # An anchor with verify_score < PARTIAL_LOW (0.40) and verified=0 should
    # produce a CRITICAL finding (not just major "unverified-cite").
    body = "GDP grew 12.4% annually in the region."
    quote = "GDP grew 12.4% annually in the region."
    start = body.index(quote)
    anchor = ClaimAnchor(
        note_id="n1", char_start=start, char_end=start + len(quote),
        claim="GDP grew 12.4%.", quoted_support=quote,
        verified=0, verify_score=0.15,  # explicitly below PARTIAL_LOW=0.40
    )
    store = _store_with([anchor])

    # Sentence cites the anchor but it has a low verify_score -> critical
    report = f"GDP grew 12.4% annually. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    critical = [f for f in findings if f.severity == "critical"]
    assert any("unsupported" in f.failure_mode or "verify_score" in f.recommendation.lower()
               for f in critical), f"Expected critical finding, got: {findings}"


def test_gate_keeps_partial_verdict_as_major():
    # An anchor with verify_score in [PARTIAL_LOW, SUPPORTED_FLOOR) stays major.
    body = "GDP grew 12.4% annually in the region."
    quote = "GDP grew 12.4% annually in the region."
    start = body.index(quote)
    anchor = ClaimAnchor(
        note_id="n1", char_start=start, char_end=start + len(quote),
        claim="GDP grew 12.4%.", quoted_support=quote,
        verified=0, verify_score=0.55,  # in the "partial" band
    )
    store = _store_with([anchor])

    report = f"GDP grew 12.4% annually. [[{anchor.anchor_id}]]"
    findings = no_uncited_claim_gate(report, store)
    # verify_score=0.55 is above PARTIAL_LOW -> major, not critical
    unverified = [f for f in findings if f.failure_mode == "unverified-cite"]
    assert unverified
    assert all(f.severity == "major" for f in unverified)
