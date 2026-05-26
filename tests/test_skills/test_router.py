from bad_research.skills import routing_constants as R
from bad_research.skills.router import classify_route, route_reason


def _decomp(**kw):
    base = dict(sub_questions=["q1"], entities=[], time_periods=[],
                response_format="short", contradiction_terms=[], domains=["tech"])
    base.update(kw)
    return base


def test_constants_match_interfaces():
    assert R.AGENTIC_FAST_MAX_STEPS == 10
    assert R.AGENTIC_FAST_MAX_CALLS == 15
    assert R.AGENTIC_FAST_TIMEOUT_S == 300
    assert R.SUBAGENT_FANOUT_DEFAULT == 3 and R.SUBAGENT_FANOUT_MAX == 20
    assert R.CLARIFY_MAX_QUESTIONS == 3
    assert R.READ_TOP_K_CEILING == 80
    assert R.ROUTER_AGENTIC_MAX_ATOMIC == 2 and R.ROUTER_LIGHT_MAX_ATOMIC == 6


def test_trivial_single_domain_routes_agentic_fast():
    d = _decomp(sub_questions=["what is the capital of France"], response_format="short")
    assert classify_route(d) == "agentic-fast"


def test_two_atomic_no_tension_routes_agentic_fast():
    d = _decomp(sub_questions=["q1", "q2"], response_format="short")
    assert classify_route(d) == "agentic-fast"


def test_structured_midsize_routes_light():
    d = _decomp(sub_questions=["q1", "q2", "q3", "q4"], response_format="structured")
    assert classify_route(d) == "light"


def test_time_periods_force_full():
    d = _decomp(sub_questions=["q1"], response_format="short",
                time_periods=[{"period": "Q3 2024"}])
    assert classify_route(d) == "full"


def test_contested_argumentative_routes_full():
    d = _decomp(sub_questions=["q%d" % i for i in range(8)],
                response_format="argumentative", contradiction_terms=["versus"])
    assert classify_route(d) == "full"


def test_multi_domain_routes_full():
    d = _decomp(sub_questions=["q1", "q2"], response_format="structured",
                domains=["bio", "finance", "law"])
    assert classify_route(d) == "full"


def test_short_with_three_atomic_routes_light():
    # 3 atomic items, short format, single domain → not agentic (>2), not full → light
    d = _decomp(sub_questions=["q1", "q2", "q3"], response_format="short")
    assert classify_route(d) == "light"


def test_entities_count_toward_atomic():
    # 2 sub_questions + 1 entity = 3 atomic → light, not agentic-fast
    d = _decomp(sub_questions=["q1", "q2"], entities=["X"], response_format="short")
    assert classify_route(d) == "light"


def test_route_reason_is_nonempty_string():
    assert isinstance(route_reason(_decomp()), str)
    assert route_reason(_decomp()) != ""


def test_route_reason_mentions_full_trigger():
    d = _decomp(time_periods=[{"period": "Q3 2024"}])
    assert "time_period" in route_reason(d).lower() or "full" in route_reason(d).lower()
