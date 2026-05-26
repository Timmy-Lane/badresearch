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
