"""The 5-axis LLM-judge rubric (dossier 09 §B7; CLAUDE_RESEARCH.md:39; SPEC §14).

A SINGLE strong-model call per report - NOT an ensemble (ensemble tested WORSE,
dossier 09 §B7). Scores five axes 0.0-1.0; PASS iff every axis >= AXIS_PASS_THRESHOLD
AND the mean >= OVERALL_PASS_THRESHOLD. OFFLINE calibration only - never a per-run gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from bad_research.calibrate.constants import (
    AXIS_PASS_THRESHOLD,
    JUDGE_AXES,
    JUDGE_MAX_TOKENS,
    JUDGE_TEMPERATURE,
    JUDGE_TIER,
    OVERALL_PASS_THRESHOLD,
)
from bad_research.llm.base import LLMMessage, LLMProvider


@dataclass
class AxisScores:
    factual: float
    citation: float
    completeness: float
    source_quality: float
    efficiency: float

    def as_dict(self) -> dict[str, float]:
        return {a: getattr(self, a) for a in JUDGE_AXES}

    @staticmethod
    def _clamp(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    @classmethod
    def from_raw(cls, raw: dict) -> AxisScores:
        return cls(**{a: cls._clamp(raw.get(a, 0.0)) for a in JUDGE_AXES})


@dataclass
class JudgeVerdict:
    scores: AxisScores
    overall: float
    passed: bool
    rationale: str

    @classmethod
    def from_scores(cls, scores: AxisScores, *, rationale: str) -> JudgeVerdict:
        vals = list(scores.as_dict().values())
        overall = round(sum(vals) / len(vals), 9)
        passed = (
            all(v >= AXIS_PASS_THRESHOLD for v in vals) and overall >= OVERALL_PASS_THRESHOLD
        )
        return cls(scores=scores, overall=overall, passed=passed, rationale=rationale)

    def to_dict(self) -> dict:
        return {
            "scores": self.scores.as_dict(),
            "overall": self.overall,
            "passed": self.passed,
            "rationale": self.rationale,
        }


class Judge(Protocol):
    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict: ...


@dataclass
class StubJudge:
    """Deterministic judge for tests/offline use. No LLM call."""

    scores: dict[str, float]

    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict:
        s = AxisScores.from_raw(self.scores)
        return JudgeVerdict.from_scores(s, rationale="stub")


JUDGE_SYSTEM = (
    "You are a rigorous, calibrated research-report judge. Score the report on five "
    "axes, each from 0.0 to 1.0. Be strict; reserve >0.9 for excellent work.\n"
    "Axes:\n"
    "- factual: are claims accurate and supported by the provided corpus?\n"
    "- citation: does every non-trivial claim carry a citation that the corpus supports "
    "(no fabricated or mis-attributed cites)?\n"
    "- completeness: does the report cover the question's sub-parts using the corpus?\n"
    "- source_quality: are the cited sources authoritative and on-topic?\n"
    "- efficiency: is the report concise — no padding, no redundancy, right length?\n"
    "Return ONLY a JSON object: "
    '{"factual":0-1,"citation":0-1,"completeness":0-1,"source_quality":0-1,'
    '"efficiency":0-1,"rationale":"<=2 sentences"}. No prose outside the JSON.'
)


@dataclass
class LLMJudge:
    """Single-call 5-axis judge over an LLMProvider (Plan 01 seam)."""

    provider: LLMProvider
    tier: str = JUDGE_TIER

    def judge(self, query: str, report: str, corpus: list[dict]) -> JudgeVerdict:
        corpus_block = "\n".join(
            f"[{c.get('note_id', i)}] {c.get('url', '')}\n{c.get('text', '')[:1200]}"
            for i, c in enumerate(corpus)
        )
        user = (
            f"QUERY:\n{query}\n\n"
            f"CORPUS (the evidence the report had access to):\n{corpus_block}\n\n"
            f"REPORT TO JUDGE:\n{report}\n\n"
            "Score now. JSON only."
        )
        resp = self.provider.complete(
            [
                LLMMessage(role="system", content=JUDGE_SYSTEM),
                LLMMessage(role="user", content=user),
            ],
            tier=self.tier,  # type: ignore[arg-type]
            max_tokens=JUDGE_MAX_TOKENS,
            temperature=JUDGE_TEMPERATURE,
        )
        raw = _extract_json(resp.text)
        scores = AxisScores.from_raw(raw)
        return JudgeVerdict.from_scores(scores, rationale=str(raw.get("rationale", "")))


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction — handles ```json fences and leading/trailing prose."""
    text = text.strip()
    if "```" in text:
        # take the content of the first fenced block that parses
        parts = text.split("```")
        for part in parts:
            part = part.removeprefix("json").strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {a: 0.0 for a in JUDGE_AXES}


__all__ = ["AxisScores", "Judge", "JudgeVerdict", "LLMJudge", "StubJudge"]
