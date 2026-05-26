"""Tier-B NLI entailment check -- cross-encoder/nli-deberta-v3-base (frozen).
Local, $0, CPU-fine. dossier 08 §2.2 option 1."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

# INTERFACES.md frozen constant (the bare HF repo name resolves to
# cross-encoder/nli-deberta-v3-base when loaded).
NLI_MODEL_NAME = "nli-deberta-v3-base"

ENTAILMENT_PASS = 0.70  # dossier §2.2: entailment >= 0.70 -> PASS
CONTRADICTION_FLAG = 0.50  # dossier §2.2: contradiction >= 0.50 -> FLAG hard


class NLILabel(str, Enum):
    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"
    CONTRADICTION = "contradiction"


def classify_nli(scores: dict[str, float]) -> NLILabel:
    """Map a {entailment, neutral, contradiction} softmax to a decision.

    Contradiction is checked before entailment so a quote that says the OPPOSITE
    is never silently passed (dossier §2.2)."""
    if scores.get("contradiction", 0.0) >= CONTRADICTION_FLAG:
        return NLILabel.CONTRADICTION
    if scores.get("entailment", 0.0) >= ENTAILMENT_PASS:
        return NLILabel.ENTAILMENT
    return NLILabel.NEUTRAL


class NLIModel(Protocol):
    """premise = quoted_support, hypothesis = report sentence -> softmax dict."""

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]: ...


class CrossEncoderNLI:
    """Lazy wrapper over the real model. Imported only when actually used so the
    grounding package has no hard torch/transformers dependency at import time."""

    def __init__(self, model_name: str = NLI_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure(self) -> None:
        if self._model is None:
            from sentence_transformers import CrossEncoder  # heavy; lazy

            # The cross-encoder/ prefix is the canonical HF path.
            repo = self.model_name
            if "/" not in repo:
                repo = f"cross-encoder/{repo}"
            self._model = CrossEncoder(repo)

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]:
        self._ensure()
        import numpy as np

        logits = self._model.predict([(premise, hypothesis)])[0]
        # cross-encoder/nli-deberta-v3-base label order: [contradiction, entailment, neutral].
        # NEEDS-LIVE-VERIFICATION: this index mapping is taken from the model card's
        # documented order; it was NOT verified against a live model load here (torch +
        # the ~400MB checkpoint are intentionally not installed for tests). If a live
        # check ever shows a different order, fix the three indices below (the rest of
        # the pipeline keys off the {entailment,contradiction,neutral} dict, not the order).
        exp = np.exp(logits - np.max(logits))
        probs = exp / exp.sum()
        return {
            "contradiction": float(probs[0]),
            "entailment": float(probs[1]),
            "neutral": float(probs[2]),
        }
