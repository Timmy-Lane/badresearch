"""retrieve_until_good loop termination: early-return / re-retrieve / max_rounds."""

from __future__ import annotations

from bad_research.web.base import WebResult
from bad_research.web.search.base import KeylessSearchConfig
from bad_research.web.search.loop import retrieve_until_good


def _pool(scores):
    out = []
    for i, s in enumerate(scores):
        r = WebResult(url=f"https://x.com/{i}", title=f"t{i}", content="c")
        r.metadata["score"] = s
        out.append(r)
    return out


def test_returns_early_when_30pct_clear_070():
    rounds = []
    cfg = KeylessSearchConfig(max_rounds=3)
    # 2 of 4 (50%) clear 0.70 → return after round 1
    def expand(q, findings=None, gaps=None):
        rounds.append("expand")
        return ["q1"]
    def fan_out(queries):
        rounds.append("fan")
        return _pool([0.9, 0.8, 0.2, 0.1])
    def rerank(question, pool):
        return pool  # scores already on metadata
    passing = retrieve_until_good("question", cfg=cfg, expand=expand,
                                  fan_out=fan_out, rerank=rerank)
    assert len(passing) == 2
    assert all(r.metadata["score"] >= 0.70 for r in passing)
    assert rounds.count("fan") == 1   # only one round


def test_reformulates_when_under_30pct():
    fan_calls = {"n": 0}
    cfg = KeylessSearchConfig(max_rounds=3)
    def expand(q, findings=None, gaps=None):
        return ["q-reformulated"] if findings else ["q-initial"]
    def fan_out(queries):
        fan_calls["n"] += 1
        # round 1: 1/5 (20%) clears; round 2: 3/4 (75%) clears
        return _pool([0.9, 0.1, 0.1, 0.1, 0.1]) if fan_calls["n"] == 1 else _pool([0.9, 0.8, 0.75, 0.1])
    def rerank(question, pool):
        return pool
    passing = retrieve_until_good("question", cfg=cfg, expand=expand,
                                  fan_out=fan_out, rerank=rerank)
    assert fan_calls["n"] == 2
    assert len(passing) == 3


def test_best_effort_after_max_rounds():
    cfg = KeylessSearchConfig(max_rounds=2)
    def expand(q, findings=None, gaps=None):
        return ["q"]
    def fan_out(queries):
        return _pool([0.9, 0.1, 0.1, 0.1, 0.1])  # always 20% < 30%
    def rerank(question, pool):
        return pool
    passing = retrieve_until_good("question", cfg=cfg, expand=expand,
                                  fan_out=fan_out, rerank=rerank)
    # never cleared 30%; returns the best-effort passing set (the 1 that cleared 0.70)
    assert len(passing) == 1


def test_empty_pool_does_not_divide_by_zero():
    cfg = KeylessSearchConfig(max_rounds=1)
    passing = retrieve_until_good("q", cfg=cfg,
                                  expand=lambda q, **kw: ["q"],
                                  fan_out=lambda qs: [],
                                  rerank=lambda question, pool: pool)
    assert passing == []
