from __future__ import annotations

from bad_research.grounding.nli import NLI_MODEL_NAME, NLILabel, classify_nli


def test_model_name_is_frozen_constant():
    assert NLI_MODEL_NAME == "nli-deberta-v3-base"


def test_classify_entailment_high():
    scores = {"entailment": 0.91, "neutral": 0.07, "contradiction": 0.02}
    assert classify_nli(scores) is NLILabel.ENTAILMENT


def test_classify_contradiction_flag():
    scores = {"entailment": 0.10, "neutral": 0.30, "contradiction": 0.60}
    assert classify_nli(scores) is NLILabel.CONTRADICTION


def test_classify_neutral_band():
    # No label clears its bar -> neutral (the band that escalates to Tier C).
    scores = {"entailment": 0.55, "neutral": 0.40, "contradiction": 0.05}
    assert classify_nli(scores) is NLILabel.NEUTRAL
