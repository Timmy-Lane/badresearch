from __future__ import annotations

import types

from bad_research.grounding.nli import (
    NLI_MODEL_NAME,
    CrossEncoderNLI,
    NLILabel,
    classify_nli,
)


def test_model_name_is_frozen_constant():
    assert NLI_MODEL_NAME == "nli-deberta-v3-base"


def test_nlilabel_str_subclass_contract():
    """Pin the str-subclass behaviors the code actually relies on, so the
    `(str, Enum)` -> `StrEnum` migration is provably behavior-preserving.
    The code uses: identity (`is`), construction-from-value, `.value`, string
    equality, and JSON serialization — all identical across both bases. It never
    relies on `str(member)` (the one form that differs)."""
    import json

    # str subclass — every member IS a str.
    assert isinstance(NLILabel.ENTAILMENT, str)
    # construction from the value (classify_nli returns these; model id2label is
    # matched by the plain value elsewhere).
    assert NLILabel("entailment") is NLILabel.ENTAILMENT
    # value + string equality (the funnel/gate compare against the bare value).
    assert NLILabel.ENTAILMENT.value == "entailment"
    assert NLILabel.ENTAILMENT == "entailment"
    # JSON serializes to the bare value (str content), not "NLILabel.ENTAILMENT".
    assert json.dumps(NLILabel.NEUTRAL) == '"neutral"'


class _StubCrossEncoder:
    """A fake CrossEncoder whose logit order is given by `id2label`. predict()
    emits a one-hot-ish logit vector chosen by which premise/hypothesis pair it
    sees, placed at the position `id2label` assigns to that label name."""

    def __init__(self, id2label: dict[int, str]) -> None:
        self.config = types.SimpleNamespace(id2label=id2label)
        self._name_to_idx = {v.lower(): k for k, v in id2label.items()}

    def _logits_for(self, label_name: str):
        n = len(self._name_to_idx)
        logits = [0.0] * n
        logits[self._name_to_idx[label_name]] = 5.0  # dominate the softmax
        return logits

    def predict(self, pairs):
        out = []
        for _premise, hypothesis in pairs:
            # "same" pair -> entailment, "opposite" pair -> contradiction.
            if "OPPOSITE" in hypothesis:
                out.append(self._logits_for("contradiction"))
            else:
                out.append(self._logits_for("entailment"))
        return out


def _nli_with(id2label: dict[int, str]) -> CrossEncoderNLI:
    nli = CrossEncoderNLI()
    nli._model = _StubCrossEncoder(id2label)  # inject -> _ensure() is a no-op
    return nli


def test_predict_keys_by_label_name_not_position():
    # Canonical order documented on the model card.
    canonical = {0: "contradiction", 1: "entailment", 2: "neutral"}
    nli = _nli_with(canonical)
    entailed = nli.predict("the sky is blue", "the sky is blue")
    assert entailed["entailment"] > 0.9
    opposed = nli.predict("the sky is blue", "OPPOSITE: the sky is not blue")
    assert opposed["contradiction"] > 0.9


def test_predict_robust_to_a_different_label_order():
    # A checkpoint that orders its logits differently. Indexing by POSITION would
    # silently invert every verdict; indexing by NAME keeps the dict correct.
    reordered = {0: "entailment", 1: "neutral", 2: "contradiction"}
    nli = _nli_with(reordered)
    entailed = nli.predict("the sky is blue", "the sky is blue")
    # The entailed pair still reads as entailment (not contradiction).
    assert entailed["entailment"] > 0.9
    assert entailed["contradiction"] < 0.1
    opposed = nli.predict("the sky is blue", "OPPOSITE: the sky is not blue")
    assert opposed["contradiction"] > 0.9
    assert opposed["entailment"] < 0.1


def test_predict_handles_uppercase_label_names_from_config():
    # HF configs commonly store labels uppercased (e.g. "CONTRADICTION").
    upper = {0: "CONTRADICTION", 1: "ENTAILMENT", 2: "NEUTRAL"}
    nli = _nli_with(upper)
    entailed = nli.predict("x", "x")
    assert entailed["entailment"] > 0.9


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
