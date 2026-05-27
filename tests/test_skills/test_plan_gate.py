"""E11 — User-editable plan-gate predicate (Gemini collaborative_planning,
STEAL_LIST #3).

Gemini emits a structured plan → the user approves/edits → execute, so an
ambiguous/expensive query doesn't research the wrong sub-questions. bad-research
already has a triage CLARIFIER (`0.5-clarify`, default-proceed) but NO plan-approval
gate. E11 adds step `bad-research-1.6-plan-gate` plus the `plan_gate_fires`
predicate here in `router.py`.

The predicate is a SEPARATE gate step — it MUST NOT influence `classify_route`.
It fires ONLY when the run is interactive AND not `--auto`/wrapped AND the run is
expensive (route == full OR atomic_items > ROUTER_LIGHT_MAX_ATOMIC OR est_cost
over a threshold). A non-interactive / wrapped / `--auto` / test run NEVER gates —
the eval gate + the whole test suite must flow straight through.
"""

from __future__ import annotations

from bad_research.skills import routing_constants as R  # noqa: N812
from bad_research.skills.router import classify_route, plan_gate_fires


def _decomp(**kw):
    base = dict(
        sub_questions=["q1"],
        entities=[],
        time_periods=[],
        response_format="short",
        contradiction_terms=[],
        domains=["tech"],
    )
    base.update(kw)
    return base


# ── It FIRES: interactive + expensive ────────────────────────────────────────


def test_full_route_interactive_fires():
    # A contested argumentative full-tier query in an interactive run → show a plan.
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(8)],
        response_format="argumentative",
        contradiction_terms=["versus"],
    )
    assert classify_route(d) == "full"
    assert plan_gate_fires(d, interactive=True, wrapped=False, auto=False) is True


def test_breadth_over_light_max_interactive_fires():
    # > ROUTER_LIGHT_MAX_ATOMIC atomic items, interactive → fires even if it routed
    # light (the broad-survey case the modality gate spared from full).
    d = _decomp(
        sub_questions=[f"opt {i}" for i in range(R.ROUTER_LIGHT_MAX_ATOMIC + 2)],
        response_format="structured",
        modality="survey",
    )
    assert plan_gate_fires(d, interactive=True, wrapped=False, auto=False) is True


def test_high_est_cost_interactive_fires():
    # Even a small-item structured query fires when the explicit cost estimate is
    # above the threshold (the "expensive" arm of the predicate).
    d = _decomp(sub_questions=["q1", "q2", "q3"], response_format="structured")
    assert (
        plan_gate_fires(
            d, interactive=True, wrapped=False, auto=False,
            est_cost=R.PLAN_GATE_COST_THRESHOLD + 1.0,
        )
        is True
    )


# ── It does NOT fire: non-interactive / wrapped / --auto / trivial ────────────


def test_wrapped_run_never_fires():
    # A wrapped run (wrapper_contract.json present) is binding GOSPEL → no gate,
    # exactly mirroring how 0.5-clarify skips. Even a full-tier query passes through.
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(8)],
        response_format="argumentative",
        contradiction_terms=["versus"],
    )
    assert classify_route(d) == "full"
    assert plan_gate_fires(d, interactive=True, wrapped=True, auto=False) is False


def test_auto_run_never_fires():
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(8)],
        response_format="argumentative",
        contradiction_terms=["versus"],
    )
    assert plan_gate_fires(d, interactive=True, wrapped=False, auto=True) is False


def test_non_interactive_run_never_fires():
    # The default for an automated run (incl. the eval gate + the test suite): not
    # interactive → never gates, regardless of how expensive the query is.
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(8)],
        response_format="argumentative",
        contradiction_terms=["versus"],
    )
    assert plan_gate_fires(d, interactive=False, wrapped=False, auto=False) is False


def test_default_kwargs_are_non_interactive_so_it_never_fires():
    # The default-safe contract: calling with NO interactivity kwargs (what a test
    # / automated caller does) must NOT gate. This is what keeps the suite + eval
    # gate flowing straight through.
    d = _decomp(
        sub_questions=[f"q{i}" for i in range(8)],
        response_format="argumentative",
        contradiction_terms=["versus"],
    )
    assert plan_gate_fires(d) is False


def test_trivial_interactive_query_does_not_fire():
    # Interactive but cheap (agentic-fast, <= 2 atomic, no cost over threshold) →
    # no plan gate; the gate is only for expensive runs.
    d = _decomp(sub_questions=["what is the capital of France"], response_format="short")
    assert classify_route(d) == "agentic-fast"
    assert plan_gate_fires(d, interactive=True, wrapped=False, auto=False) is False


def test_light_under_max_interactive_does_not_fire():
    # A light-tier query within ROUTER_LIGHT_MAX_ATOMIC, low cost → not expensive →
    # no gate even though interactive.
    d = _decomp(sub_questions=["q1", "q2", "q3", "q4"], response_format="structured")
    assert classify_route(d) == "light"
    assert plan_gate_fires(d, interactive=True, wrapped=False, auto=False) is False


# ── It must NOT change classify_route ─────────────────────────────────────────


def test_predicate_does_not_change_classify_route():
    # Calling the gate predicate for every fixture must leave classify_route's
    # output byte-identical (the gate is a separate step, never a route input).
    cases = [
        _decomp(sub_questions=["one"], response_format="short"),
        _decomp(sub_questions=["q1", "q2", "q3", "q4"], response_format="structured"),
        _decomp(sub_questions=[f"q{i}" for i in range(8)],
                response_format="argumentative", contradiction_terms=["versus"]),
        _decomp(sub_questions=["q1", "q2"], domains=["bio", "finance", "law"]),
    ]
    for d in cases:
        before = classify_route(d)
        # Exercise the predicate in every interactivity combination.
        for interactive in (True, False):
            for wrapped in (True, False):
                for auto in (True, False):
                    plan_gate_fires(d, interactive=interactive, wrapped=wrapped, auto=auto)
        assert classify_route(d) == before


def test_cost_threshold_constant_exists():
    assert isinstance(R.PLAN_GATE_COST_THRESHOLD, (int, float))
    assert R.PLAN_GATE_COST_THRESHOLD > 0
