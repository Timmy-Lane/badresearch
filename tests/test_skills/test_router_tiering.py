"""Semantic-tiering fix — depth-favoring default + pipeline_tier floor.

The post-B-5 bug: a LEXICALLY-inferred survey (`detect_modality` falling back to
`SURVEY_PHRASE_MARKERS` when the decompose step set no explicit `modality`) bought
the raised survey ceiling (`ROUTER_SURVEY_MAX_ATOMIC = 40`). So ANY query phrased
"best X" / "top X" / "what are the X" got the shallow-survey free pass and stayed
`light` — including DEEP single-subject queries like "best tRPC patterns" (8 facets
of ONE subject). The heuristic cannot tell "best tech *stack*" (enumerate ~17
independent options → genuinely shallow/wide) from "best tRPC *patterns*"
(investigate ~8 facets of ONE subject → deep).

The fix ("semantic floor + depth-favoring default", keyword-free):
  1. The raised survey ceiling requires an EXPLICIT breadth `modality` set by the
     decompose step. A merely lexically-inferred breadth modality no longer buys
     the raised ceiling — it falls back to the deep ceiling ROUTER_LIGHT_MAX_ATOMIC
     (the depth-favoring default). This kills the lexical "best"→light demotion
     while preserving the explicit-survey down-route (the B-5 case).
  2. An explicit `pipeline_tier == "full"` from decompose is a FLOOR: classify_route
     never returns light/agentic-fast under it. A missing / "light" pipeline_tier
     imposes no floor (preserves every fixture that omits it).
"""
from __future__ import annotations

from bad_research.skills import routing_constants as R  # noqa: N812
from bad_research.skills.router import classify_route, route_reason


def _decomp(**kw):
    base = dict(sub_questions=["q1"], entities=[], time_periods=[],
                response_format="structured", contradiction_terms=[], domains=["tech"])
    base.update(kw)
    return base


# ── A: deep single-subject "best X" must route full ──────────────────────────

def test_deep_single_subject_best_x_routes_full():
    # "best tRPC patterns": investigate ~8 FACETS of ONE subject. Phrased "best"
    # (so only a LEXICAL survey pass would infer breadth), NO explicit modality,
    # single domain, not contested. The lexical pass is withdrawn → the deep
    # ceiling (6) applies → 9 atomic items (8 facets + tRPC entity) > 6 → full.
    d = _decomp(
        sub_questions=[
            "best practices for tRPC router composition",
            "tRPC error-handling patterns",
            "tRPC middleware patterns",
            "input validation patterns with zod",
            "tRPC subscriptions / websockets pattern",
            "tRPC with react-query integration patterns",
            "tRPC server-adapter patterns",
            "tRPC end-to-end type-inference patterns",
        ],
        entities=["tRPC"],
        response_format="structured",
        contradiction_terms=[],
        domains=["typescript"],
        # NO explicit modality — only the lexical "best " phrasing would infer one
    )
    assert classify_route(d) == "full"


def test_lexically_inferred_survey_does_not_demote():
    # a deep query whose sub_questions DO contain "best " but with NO explicit
    # modality and > ROUTER_LIGHT_MAX_ATOMIC atomic items → the lexical pass is
    # withdrawn, so breadth count escalates to full as it would for a deep query.
    d = _decomp(
        sub_questions=[f"best approach for facet {i}" for i in range(8)],
        entities=["Kubernetes security"],
        response_format="structured",
        contradiction_terms=[],
        domains=["devops"],
    )
    assert classify_route(d) == "full"


# ── B: an EXPLICIT survey modality still down-routes (B-5 preserved) ──────────

def test_explicit_survey_modality_still_light():
    # 17 items, EXPLICIT modality="survey", not contested → still light. The B-5
    # case: an explicitly-declared survey keeps the raised ceiling (40).
    d = _decomp(
        sub_questions=[f"best tech for use-case {i}" for i in range(17)],
        entities=[],
        response_format="structured",
        contradiction_terms=[],
        domains=["tech"],
        modality="survey",
    )
    assert classify_route(d) == "light"


def test_explicit_compare_modality_still_light():
    d = _decomp(
        sub_questions=[f"compare option {i}" for i in range(12)],
        response_format="structured",
        contradiction_terms=[],
        domains=["tech"],
        modality="compare",
    )
    assert classify_route(d) == "light"


# ── C: pipeline_tier == "full" is a FLOOR ────────────────────────────────────

def test_pipeline_tier_full_is_a_floor():
    # a decomp that would otherwise be light (3 atomic, structured, single domain,
    # not contested) but carries an explicit pipeline_tier="full" → full.
    d = _decomp(
        sub_questions=["q1", "q2", "q3"],
        response_format="structured",
        domains=["tech"],
        pipeline_tier="full",
    )
    assert classify_route(d) == "full"


def test_pipeline_tier_full_floor_over_agentic_fast():
    # a decomp that would otherwise be agentic-fast (2 atomic, short, single
    # domain) but carries pipeline_tier="full" → never agentic-fast under the floor.
    d = _decomp(
        sub_questions=["what is X"],
        entities=["X"],
        response_format="short",
        domains=["tech"],
        pipeline_tier="full",
    )
    assert classify_route(d) == "full"


def test_pipeline_tier_full_floor_beats_explicit_survey():
    # the floor outranks the survey down-route: even an explicit survey modality
    # cannot demote a decompose-declared full.
    d = _decomp(
        sub_questions=[f"best tech for use-case {i}" for i in range(17)],
        response_format="structured",
        modality="survey",
        pipeline_tier="full",
    )
    assert classify_route(d) == "full"


# ── D: an absent / light pipeline_tier imposes NO floor ───────────────────────

def test_pipeline_tier_absent_imposes_no_floor():
    # existing small-light decomp with no pipeline_tier → still light as before.
    d = _decomp(sub_questions=["q1", "q2", "q3", "q4"], response_format="structured")
    assert "pipeline_tier" not in d
    assert classify_route(d) == "light"


def test_pipeline_tier_light_imposes_no_floor():
    # an explicit pipeline_tier="light" must NOT raise the route; the trivial
    # agentic-fast case stays agentic-fast.
    d = _decomp(
        sub_questions=["what is the capital of France"],
        response_format="short",
        pipeline_tier="light",
    )
    assert classify_route(d) == "agentic-fast"


# ── E: route_reason reflects the new logic ────────────────────────────────────

def test_route_reason_mentions_pipeline_tier_floor():
    d = _decomp(
        sub_questions=["q1", "q2", "q3"],
        response_format="structured",
        pipeline_tier="full",
    )
    reason = route_reason(d).lower()
    assert "full" in reason
    assert "pipeline_tier" in reason or "decompose" in reason or "floor" in reason


def test_route_reason_mentions_breadth_for_withdrawn_lexical_survey():
    # the deep "best X" case routes full on breadth count once the lexical-survey
    # pass is withdrawn — the rationale must surface the atomic-count trigger.
    d = _decomp(
        sub_questions=[f"best approach for facet {i}" for i in range(8)],
        entities=["Kubernetes security"],
        response_format="structured",
        domains=["devops"],
    )
    reason = route_reason(d).lower()
    assert "full" in reason
    assert "atomic" in reason
