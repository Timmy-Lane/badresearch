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
    a = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    b = ["a", "quick", "brown", "fox", "jumps", "over", "the", "river"]
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


def test_stray_unrelated_quote_does_not_launder_verbatim_copy():
    # The carve-out is per-RUN: copying a 13+-word source verbatim OUTSIDE the quotes
    # and tacking on an unrelated "quote" + [N] must STILL flag (closed false-negative).
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = ("Transformers replace recurrence with self attention allowing the model to "
              "weigh every token against every other token in parallel during training, as "
              'the so-called "paper" notes [1].')
    findings = recitation_findings(report, {"note-1": src})
    assert len(findings) == 1  # the verbatim run is outside the "paper" quote -> not exempt
    assert findings[0].failure_mode == "recitation"


def test_sources_section_excluded():
    src = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi."
    report = ("# Title\n\nA short paraphrase here [1].\n\n## Sources\n"
              "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi.\n")
    # the verbatim run is in the Sources block -> ignored
    assert recitation_findings(report, {"note-1": src}) == []


# ── A-9: URL / reference / metadata line exemption ───────────────────────────

def test_url_label_line_is_exempt_from_recitation():
    # q2's 13 false positives were all `**URL:**` label lines that inherently
    # repeat the source string. A bolded URL/metadata label is not prose copying.
    src = "https://example.com/some/very/long/canonical/path?with=query&and=params"
    report = f"**URL:** {src}\n"
    assert recitation_findings(report, {"note-1": src}) == []


def test_source_label_and_bare_url_and_reflist_lines_exempt():
    src = ("The Annual Report on Southeast Asian Digital Commerce covers the full "
           "regional market across every vertical in extensive detail this year.")
    # All three reference/metadata shapes repeat the source verbatim by nature.
    report = (
        f"Source: {src}\n"
        f"https://example.com — {src}\n"
        f"[1]: {src}\n"
    )
    assert recitation_findings(report, {"note-1": src}) == []


def test_genuine_prose_lift_still_flags_when_url_exemption_added():
    # The exemption is a sibling carve-out, NOT a blanket pass: a prose sentence
    # (not a URL/reference line) that lifts a source verbatim must STILL flag.
    src = ("Transformers replace recurrence with self attention allowing the model to "
           "weigh every token against every other token in parallel during training.")
    report = ("Transformers replace recurrence with self attention allowing the model to "
              "weigh every token against every other token in parallel during training [1].")
    findings = recitation_findings(report, {"note-1": src})
    assert len(findings) == 1
    assert findings[0].failure_mode == "recitation"
