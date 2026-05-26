import math

from bad_research.retrieval.fusion import (
    apply_source_type_weight,
    hybrid_fuse,
    minmax_normalize,
    retrieval_weight,
    rrf_merge,
    three_tier_fuse,
)


def test_minmax_normalize_basic():
    assert minmax_normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_minmax_normalize_constant_returns_ones():
    # A lane where every score is equal must not collapse to all-zeros.
    assert minmax_normalize([3.0, 3.0, 3.0]) == [1.0, 1.0, 1.0]


def test_minmax_normalize_empty():
    assert minmax_normalize([]) == []


def test_hybrid_fuse_alpha_blend_exact():
    # vec normalized: [1.0, 0.0]; bm25 normalized: [0.0, 1.0]; alpha=0.7
    # id A: 0.7*1.0 + 0.3*0.0 = 0.70 ; id B: 0.7*0.0 + 0.3*1.0 = 0.30
    vec = {"A": 10.0, "B": 0.0}
    bm = {"A": 0.0, "B": 4.0}
    fused = hybrid_fuse(vec, bm, alpha=0.7)
    assert math.isclose(fused["A"], 0.70, abs_tol=1e-9)
    assert math.isclose(fused["B"], 0.30, abs_tol=1e-9)


def test_hybrid_fuse_vector_only_id_uses_zero_for_missing_lane():
    # id present only in vector lane → bm25 contribution 0.
    vec = {"A": 10.0, "B": 5.0}
    bm = {"A": 10.0}  # B absent from bm25
    fused = hybrid_fuse(vec, bm, alpha=0.7)
    # vec norm: A=1.0,B=0.0 ; bm norm: A=1.0 (constant→1.0), B missing→0.0
    assert math.isclose(fused["A"], 0.7 * 1.0 + 0.3 * 1.0, abs_tol=1e-9)  # 1.0
    assert math.isclose(fused["B"], 0.7 * 0.0 + 0.3 * 0.0, abs_tol=1e-9)  # 0.0


def test_retrieval_weight_three_tiers():
    assert retrieval_weight(1) == 0.75
    assert retrieval_weight(3) == 0.75
    assert retrieval_weight(4) == 0.60
    assert retrieval_weight(10) == 0.60
    assert retrieval_weight(11) == 0.40
    assert retrieval_weight(26) == 0.40


def test_three_tier_fuse_exact_top_tier():
    # rank<=3 → w=0.75 ; initial=0.8, reranker=0.4 → 0.75*0.8 + 0.25*0.4 = 0.70
    assert math.isclose(three_tier_fuse(0.8, 0.4, 1), 0.70, abs_tol=1e-12)


def test_three_tier_fuse_exact_mid_tier():
    # rank<=10 → w=0.60 ; initial=0.5, reranker=0.9 → 0.6*0.5 + 0.4*0.9 = 0.66
    assert math.isclose(three_tier_fuse(0.5, 0.9, 7), 0.66, abs_tol=1e-12)


def test_three_tier_fuse_exact_tail_tier_with_penalty():
    # rank=11 → w=0.40 ; initial=0.5, reranker=0.5 → 0.4*0.5 + 0.6*0.5 = 0.50
    # penalty = 0.005*(11-10) = 0.005 → 0.495
    assert math.isclose(three_tier_fuse(0.5, 0.5, 11), 0.495, abs_tol=1e-12)


def test_three_tier_fuse_clamps_to_zero():
    # rank=26 penalty=0.005*16=0.08 ; tiny scores → clamp at 0.0
    assert three_tier_fuse(0.0, 0.0, 26) == 0.0


def test_apply_source_type_weight():
    assert math.isclose(apply_source_type_weight(0.5, "code"), 0.60, abs_tol=1e-12)     # ×1.2
    assert math.isclose(apply_source_type_weight(0.5, "paper"), 0.45, abs_tol=1e-12)    # ×0.9
    assert math.isclose(apply_source_type_weight(0.5, "docs"), 0.50, abs_tol=1e-12)     # ×1.0
    assert math.isclose(apply_source_type_weight(0.5, None), 0.50, abs_tol=1e-12)       # default 1.0


def test_rrf_merge_ranks_not_scores():
    # doc X ranked #1 in list1 (idx0) and #5 in list2 (idx4):
    # 1/(0+60) + 1/(4+60) = 0.0166667 + 0.015625 = 0.0322917
    list1 = ["X", "A", "B", "C", "D"]
    list2 = ["A", "B", "C", "D", "X"]
    merged = rrf_merge(list1, list2, k=60)
    score_x = dict(merged)["X"]
    assert math.isclose(score_x, 1 / 60 + 1 / 64, abs_tol=1e-9)
    # merged is sorted descending by score.
    scores = [s for _, s in merged]
    assert scores == sorted(scores, reverse=True)
