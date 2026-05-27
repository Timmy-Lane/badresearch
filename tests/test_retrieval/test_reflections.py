"""E5 — Distilled-reflection memory (Tavily).

The reflections artifact (`research/temp/reflections.md`) is the compact,
append-only short-term memory that carries between width-sweep rounds INSTEAD of
the raw corpus: one record per round/locus holding ≤3 distilled claim bullets +
open gaps + the `cited_note_ids` that point back to the vault. Keeping only the
distilled reflections (not the raw note bodies) is what makes inter-round token
growth linear (n·m) instead of quadratic — the raw bodies stay on disk in the
vault and are re-injected ONLY at synthesis for the note_ids actually cited.

These tests cover the `retrieval/reflections.py` helper: a round-trip of
append → read, the ≤3-bullet cap, the ≤10K-token synthesis-context ceiling
(Chroma context-rot), and compaction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bad_research.retrieval.reflections import (
    REFLECTION_BULLET_CAP,
    SYNTHESIS_CONTEXT_TOKEN_CEILING,
    Reflection,
    ReflectionLog,
)


def test_constants_pin_tavily_chroma_values():
    # ≤3 distilled claim bullets per source/round (Tavily distilled-reflection)
    assert REFLECTION_BULLET_CAP == 3
    # ≤10K-token synthesis-context ceiling (Chroma context-rot)
    assert SYNTHESIS_CONTEXT_TOKEN_CEILING == 10_000


def test_append_then_read_round_trips(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    rec = Reflection(
        round=1,
        sub_question="what drives X?",
        key_findings=["X is driven by A", "B amplifies X"],
        open_gaps=["does C matter?"],
        cited_note_ids=["note-aaa", "note-bbb"],
    )
    log.append(rec)

    got = log.read()
    assert len(got) == 1
    r = got[0]
    assert r.round == 1
    assert r.sub_question == "what drives X?"
    assert r.key_findings == ["X is driven by A", "B amplifies X"]
    assert r.open_gaps == ["does C matter?"]
    assert r.cited_note_ids == ["note-aaa", "note-bbb"]


def test_append_is_append_only_across_rounds(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(round=1, sub_question="q1", key_findings=["f1"],
                           open_gaps=[], cited_note_ids=["n1"]))
    log.append(Reflection(round=2, sub_question="q2", key_findings=["f2"],
                           open_gaps=["g2"], cited_note_ids=["n2"]))
    got = log.read()
    assert [r.round for r in got] == [1, 2]
    assert [r.sub_question for r in got] == ["q1", "q2"]
    # round 1's record is NOT overwritten by round 2 (linear growth, not replace)
    assert got[0].key_findings == ["f1"]


def test_bullet_cap_truncates_to_three(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(
        round=1, sub_question="q",
        key_findings=["b1", "b2", "b3", "b4", "b5"],
        open_gaps=[], cited_note_ids=["n1"],
    ))
    got = log.read()
    # ≤3 distilled bullets — the over-cap bullets are dropped (distilled, not raw)
    assert got[0].key_findings == ["b1", "b2", "b3"]


def test_open_gaps_aggregate_across_rounds(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(round=1, sub_question="q1", key_findings=["f"],
                           open_gaps=["gap-a", "gap-b"], cited_note_ids=["n1"]))
    log.append(Reflection(round=2, sub_question="q2", key_findings=["f"],
                           open_gaps=["gap-c"], cited_note_ids=["n2"]))
    # the next-round query planner reads open_gaps, NOT the raw corpus
    assert log.open_gaps() == ["gap-a", "gap-b", "gap-c"]


def test_cited_note_ids_union_points_back_to_vault(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(round=1, sub_question="q1", key_findings=["f"],
                           open_gaps=[], cited_note_ids=["n1", "n2"]))
    log.append(Reflection(round=2, sub_question="q2", key_findings=["f"],
                           open_gaps=[], cited_note_ids=["n2", "n3"]))
    # synthesis re-injects raw bodies ONLY for these ids (de-duplicated, ordered)
    assert log.cited_note_ids() == ["n1", "n2", "n3"]


def test_read_missing_file_is_empty(tmp_path: Path):
    log = ReflectionLog(tmp_path / "does-not-exist.md")
    assert log.read() == []
    assert log.open_gaps() == []
    assert log.cited_note_ids() == []


def test_token_budget_estimate_is_monotonic(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(round=1, sub_question="q1", key_findings=["a"],
                           open_gaps=[], cited_note_ids=["n1"]))
    small = log.estimated_tokens()
    log.append(Reflection(round=2, sub_question="q2",
                           key_findings=["a" * 400, "b" * 400, "c" * 400],
                           open_gaps=["g" * 400], cited_note_ids=["n2"]))
    assert log.estimated_tokens() > small


def test_within_synthesis_ceiling_true_when_small(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    log.append(Reflection(round=1, sub_question="q", key_findings=["f"],
                           open_gaps=[], cited_note_ids=["n1"]))
    assert log.within_synthesis_ceiling() is True


def test_compact_drops_oldest_until_under_ceiling(tmp_path: Path):
    log = ReflectionLog(tmp_path / "reflections.md")
    # Each record ~1.6K chars => ~400 tokens; 40 of them ≈ 16K tokens > 10K ceiling
    big = "x" * 1600
    for i in range(40):
        log.append(Reflection(round=i, sub_question=f"q{i}",
                               key_findings=[big], open_gaps=[],
                               cited_note_ids=[f"n{i}"]))
    assert log.estimated_tokens() > SYNTHESIS_CONTEXT_TOKEN_CEILING
    kept = log.compact()
    # compaction keeps the MOST RECENT records and re-reads under the ceiling
    assert log.estimated_tokens() <= SYNTHESIS_CONTEXT_TOKEN_CEILING
    assert log.within_synthesis_ceiling() is True
    # the newest round survives; the oldest was dropped
    rounds = [r.round for r in kept]
    assert 39 in rounds
    assert 0 not in rounds


def test_reflection_rejects_negative_round():
    with pytest.raises(ValueError):
        Reflection(round=-1, sub_question="q", key_findings=[],
                   open_gaps=[], cited_note_ids=[])
