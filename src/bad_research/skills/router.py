"""Query router — classify the Step-1 decompose output into a pipeline mode.

Reuses the existing atomic-item analysis (no new classifier). The decision
tree is verbatim from DR-loops §9.2:

  agentic-fast  if atomic_items <= 2 AND no contradiction terms AND no time_periods
                AND response_format == "short" AND single domain
  light         elif response_format == "structured" OR atomic_items 3-6 OR mild tension
  full          else (multi-domain, contested, argumentative, time_periods, >=7 items)
"""
from __future__ import annotations

from typing import Any, Literal

from bad_research.skills import routing_constants as R  # noqa: N812

Route = Literal["agentic-fast", "light", "full"]
QueryShape = Literal["straightforward", "breadth_first", "depth_first"]

# The 3-way Claude Research fan-out-shape taxonomy (research_lead_agent.md:12-29).
QUERY_SHAPES: tuple[QueryShape, ...] = ("straightforward", "breadth_first", "depth_first")


def _atomic_count(decomp: dict[str, Any]) -> int:
    # atomic items = sub_questions + named entities (the Step-1 taxonomy)
    return len(decomp.get("sub_questions") or []) + len(decomp.get("entities") or [])


def _sub_q_text(decomp: dict[str, Any]) -> str:
    """Lower-cased join of the sub_questions for phrase-marker matching.

    sub_questions entries are usually strings; tolerate non-strings (e.g. the
    effort test passes ``range(7)``) by string-coercing each item."""
    return " ".join(str(q) for q in (decomp.get("sub_questions") or [])).lower()


def detect_modality(decomp: dict[str, Any]) -> str:
    """Classify the query's WORK shape: a BREADTH modality (collect/compare/
    survey — coverage-driven curation) vs ``"deep"`` (analysis-driven, where
    adversarial dialectics earn their cost). B-5.

    Honours an explicit ``modality`` field from the decompose step when present
    and valid; otherwise INFERS from sub_questions phrasing. Conservative: a
    curation modality is only returned on a clear curation cue — the default is
    ``"deep"`` so the existing full-tier behaviour is preserved when no signal
    exists (protects the 7-item structured invariant)."""
    explicit = decomp.get("modality")
    if isinstance(explicit, str) and explicit in R.BREADTH_MODALITIES:
        return explicit
    if isinstance(explicit, str) and explicit == "deep":
        return "deep"

    text = _sub_q_text(decomp)
    if any(m in text for m in R.COMPARE_PHRASE_MARKERS):
        return "compare"
    if any(m in text for m in R.SURVEY_PHRASE_MARKERS):
        return "survey"
    return "deep"


def contestedness_score(decomp: dict[str, Any]) -> float:
    """0..1 score of how source-CONTESTED the query is. >= CONTESTEDNESS_FULL_FLOOR
    means genuine tension that warrants the full adversarial path even for a
    broad query; below the floor a curation/survey query may down-route. B-5.

    Weights (routing_constants): contradiction terms are the strongest signal
    (they ARE the decompose contradiction taxonomy), argumentative format next,
    then dispute phrasing in the sub_questions. The score is the max of the
    individual signals (any single strong signal suffices), not a sum — we never
    want stacking to lower the effective bar."""
    fmt = decomp.get("response_format", "structured")
    contradiction = decomp.get("contradiction_terms") or []
    text = _sub_q_text(decomp)

    signals = [0.0]
    if contradiction:
        signals.append(R.CONTESTEDNESS_W_CONTRADICTION)
    if fmt == "argumentative":
        signals.append(R.CONTESTEDNESS_W_ARGUMENTATIVE)
    if any(m in text for m in R.DISPUTE_PHRASE_MARKERS):
        signals.append(R.CONTESTEDNESS_W_DISPUTE_PHRASE)
    return max(signals)


def _hard_full_triggers(decomp: dict[str, Any]) -> list[str]:
    """The full-tier triggers that are NON-NEGOTIABLE regardless of modality:
    Lens-D primaries (time_periods), explicit argumentative format, contradiction
    terms (source tensions), and multi-domain breadth. These are unchanged by
    B-5 — only the breadth-only (atomic-count) trigger gains the modality gate."""
    fmt = decomp.get("response_format", "structured")
    time_periods = decomp.get("time_periods") or []
    contradiction = decomp.get("contradiction_terms") or []
    domains = decomp.get("domains") or []
    reasons: list[str] = []
    if time_periods:
        reasons.append("time_periods present (Lens D primaries)")
    if fmt == "argumentative":
        reasons.append("argumentative response_format (dialectics)")
    if contradiction:
        reasons.append("contradiction terms present (source tensions)")
    if len(domains) >= 3:
        reasons.append("multi-domain (>=3 domains)")
    return reasons


def _breadth_forces_full(decomp: dict[str, Any]) -> bool:
    """Whether the atomic-item COUNT escalates to full, AFTER the B-5 modality
    gate. Pure breadth no longer forces full when the query is a low-contested
    broad-curation survey (collect/compare/survey + contestedness below floor):
    such a query is allowed up to ROUTER_SURVEY_MAX_ATOMIC items in `light`.
    A deep-modality query keeps the original ROUTER_LIGHT_MAX_ATOMIC ceiling."""
    n = _atomic_count(decomp)
    modality = detect_modality(decomp)
    contested = contestedness_score(decomp) >= R.CONTESTEDNESS_FULL_FLOOR
    if modality in R.BREADTH_MODALITIES and not contested:
        # broad-but-shallow curation: breadth alone does not buy adversarial depth
        return n > R.ROUTER_SURVEY_MAX_ATOMIC
    return n > R.ROUTER_LIGHT_MAX_ATOMIC


def _full_triggers(decomp: dict[str, Any]) -> list[str]:
    """The reasons (if any) a query MUST route full. Empty list → not forced full."""
    reasons = _hard_full_triggers(decomp)
    if _breadth_forces_full(decomp):
        n = _atomic_count(decomp)
        reasons.append(f"{n} atomic items (>{R.ROUTER_LIGHT_MAX_ATOMIC})")
    return reasons


def classify_route(decomp: dict[str, Any]) -> Route:
    n = _atomic_count(decomp)
    fmt = decomp.get("response_format", "structured")
    time_periods = decomp.get("time_periods") or []
    contradiction = decomp.get("contradiction_terms") or []
    domains = decomp.get("domains") or []
    multi_domain = len(domains) >= 3

    # FULL: Lens-D primaries, dialectics, source tensions, multi-domain breadth,
    # OR a breadth count that survives the B-5 modality gate. A broad-but-shallow
    # curation survey (collect/compare/survey, low contestedness) is NOT forced
    # full by item count alone — that was the q1 over-routing bug.
    if (time_periods or fmt == "argumentative" or contradiction
            or multi_domain or _breadth_forces_full(decomp)):
        return "full"

    # AGENTIC-FAST: trivial, bounded, single-domain, short.
    if (n <= R.ROUTER_AGENTIC_MAX_ATOMIC and not contradiction
            and not time_periods and fmt == "short" and not multi_domain):
        return "agentic-fast"

    # LIGHT: the middle band — structured coverage, 3-6 atomic items, OR a
    # low-contested broad-curation survey that the modality gate spared from full.
    return "light"


def route_reason(decomp: dict[str, Any]) -> str:
    """A one-line, human-readable rationale for the chosen route.

    Used by the router skill to write the `## Route rationale` line and by the
    `bad route` CLI's JSON `reason` field.
    """
    route = classify_route(decomp)
    n = _atomic_count(decomp)
    modality = detect_modality(decomp)
    if route == "full":
        triggers = _full_triggers(decomp)
        return "full: " + ("; ".join(triggers) if triggers else "complex query")
    if route == "agentic-fast":
        return f"agentic-fast: {n} atomic item(s), short, single-domain, no tension"
    # LIGHT: call out when a broad-curation modality spared a high-breadth query
    # from full (the B-5 gate) so the rationale line is auditable.
    if modality in R.BREADTH_MODALITIES and n > R.ROUTER_LIGHT_MAX_ATOMIC:
        return (f"light: {n} atomic item(s) but {modality} modality / low "
                f"contestedness — breadth alone does not force full (B-5)")
    return f"light: {n} atomic item(s) / structured coverage, no full-tier trigger"


def plan_gate_fires(
    decomp: dict[str, Any],
    *,
    interactive: bool = False,
    wrapped: bool = False,
    auto: bool = False,
    est_cost: float | None = None,
) -> bool:
    """E11 user-editable plan-gate trigger (Gemini collaborative_planning,
    STEAL_LIST #3). Decides whether step bad-research-1.6-plan-gate should emit a
    plan and pause for "approve / edit / proceed" before step 2 runs.

    **This is a SEPARATE gate step — it does NOT and MUST NOT influence
    classify_route.** It reads the same decomposition only to ask "is this run
    expensive enough to be worth a human approval round-trip?"; the route output is
    untouched (it merely reads `classify_route`'s decision, never mutates it).

    Fires iff ALL of:
      * `interactive` — a human is at the keyboard to approve/edit. The DEFAULT is
        ``False`` so an automated caller (the eval gate, the test suite, any `-p`
        run that doesn't opt in) NEVER gates.
      * not `wrapped` and not `auto` — a wrapped run (`research/wrapper_contract.json`
        present) or an `--auto` run carries a binding GOSPEL query that must not be
        questioned (mirrors exactly how 0.5-clarify skips for wrapper/auto).
      * EXPENSIVE — the route is `full`, OR the atomic-item count exceeds
        `ROUTER_LIGHT_MAX_ATOMIC` (a broad survey the modality gate spared from
        full but which is still wide enough to mis-scope), OR an explicit
        `est_cost` is at/above `PLAN_GATE_COST_THRESHOLD`. A cheap bounded run
        (agentic-fast / small light, no cost over threshold) is below the bar: a
        wrong sub-question there costs less than the approval round-trip.

    The interactivity flags are supplied by the orchestrator at step 1.6 (it knows
    whether the session is interactive and whether wrapper_contract.json exists);
    this keeps the predicate a pure, unit-testable function with no I/O.
    """
    if not interactive or wrapped or auto:
        return False
    route = classify_route(decomp)
    return bool(
        route == "full"
        or _atomic_count(decomp) > R.ROUTER_LIGHT_MAX_ATOMIC
        or (est_cost is not None and est_cost >= R.PLAN_GATE_COST_THRESHOLD)
    )


def _n_independent_subq(decomp: dict[str, Any]) -> int:
    """The count of independent sub-questions the breadth-first parallel fan-out
    can split across. Uses the atomic count (sub_questions + entities) — the same
    taxonomy classify_route uses, so the two stay consistent without coupling."""
    return _atomic_count(decomp)


def classify_query_shape(decomp: dict[str, Any]) -> QueryShape:
    """Classify the query's FAN-OUT SHAPE (E12, Claude Research
    research_lead_agent.md:12-29) — ORTHOGONAL to the cost tier classify_route
    decides. This determines how investigators are ARRANGED (single / parallel /
    sequential), never how many resources the run gets.

    **This function does NOT and MUST NOT influence classify_route.** It reads the
    same decompose signals (modality + contestedness + atomic count) but feeds a
    separate `query_shape` field; the route output is unchanged. (DESIGN classifier
    from STEAL_LIST #2.)

    Decision order:
      1. depth_first  — one contested topic, multiple perspectives. A genuinely
         contested query (contestedness >= floor) on a DEEP modality is depth-first
         regardless of how few atomic items it carries: "going deep" on a singular
         core question (research_lead_agent.md:13). Sequential perspectives.
      2. straightforward — focused/well-defined: <= 2 atomic items / a single
         entity, no curation breadth, not contested. One investigation.
      3. breadth_first — the default for the rest: many independent sub-questions
         / multiple entities (typically a collect/compare/survey modality).
         Parallel, importance-ordered.
    """
    n = _n_independent_subq(decomp)
    modality = detect_modality(decomp)
    contested = contestedness_score(decomp) >= R.CONTESTEDNESS_FULL_FLOOR

    # 1. depth-first: one topic, many perspectives. Contested + a deep (non-
    #    breadth) modality = "go deep" on a singular core question.
    if contested and modality not in R.BREADTH_MODALITIES:
        return "depth_first"

    # 2. straightforward: a focused, bounded single investigation.
    if (n <= R.SHAPE_STRAIGHTFORWARD_MAX_ATOMIC
            and modality not in R.BREADTH_MODALITIES
            and not contested):
        return "straightforward"

    # 3. breadth-first: independent sub-questions / multiple entities → go wide.
    #    This is the natural shape for collect/compare/survey and for any query
    #    that splits into many parallel streams.
    if modality in R.BREADTH_MODALITIES or n > R.SHAPE_STRAIGHTFORWARD_MAX_ATOMIC:
        return "breadth_first"

    # Fallback: a small, deep, uncontested query → single investigation.
    return "straightforward"


def shape_reason(decomp: dict[str, Any]) -> str:
    """A one-line rationale for the chosen query_shape (the router skill writes it
    next to the route rationale; the `bad route` CLI carries it as `shape_reason`)."""
    shape = classify_query_shape(decomp)
    n = _n_independent_subq(decomp)
    modality = detect_modality(decomp)
    if shape == "depth_first":
        return (f"depth_first: one contested topic ({modality} modality), "
                f"{R.SHAPE_DEPTH_MIN_PERSPECTIVES}-{R.SHAPE_DEPTH_MAX_PERSPECTIVES} "
                "sequential perspectives on one locus")
    if shape == "breadth_first":
        k = min(n, R.SHAPE_BREADTH_K_CAP)
        return (f"breadth_first: {n} independent sub-question(s) ({modality}), "
                f"K={k} parallel investigators, importance-ordered")
    return (f"straightforward: {n} atomic item(s), single focused investigation "
            "(1 investigator)")


def shape_fanout(decomp: dict[str, Any]) -> dict[str, Any]:
    """Resolve SHAPE_FANOUT for this decomposition: the arrangement + the concrete
    investigator count K. For breadth_first, K = min(n_independent_subq, cap)."""
    shape = classify_query_shape(decomp)
    spec = dict(R.SHAPE_FANOUT[shape])
    if shape == "breadth_first":
        spec["k"] = min(_n_independent_subq(decomp), R.SHAPE_BREADTH_K_CAP)
    spec["shape"] = shape
    return spec


def effort_overrides(effort: str | None) -> dict[str, Any] | None:
    """Translate the `--reasoning-effort` dial (minimal/low/medium/high) into the
    router overrides the orchestrator applies on top of the auto-classified route.

    Returns None for an absent/invalid effort (the auto-route is left untouched).
    The returned dict pins {route, tier, fetchers_max, loci_max, extended_thinking,
    single_draft} — OpenAI's 4-level continuum expressed as a host-side config
    (dossier 16 §6.1). This is the wiring for the stub flag in cli/research.py.
    """
    if effort not in R.EFFORT_MAP:
        return None
    return dict(R.EFFORT_MAP[effort])


def degrade_order() -> tuple[str, ...]:
    """The Claude token-ceiling degrade order (dossier 16 §6.2): cut tool-call
    redundancy, then fan-out width, then model tier, then — as the TERMINAL action
    (E10 / STEAL_LIST #6c) — short_circuit_to_synthesis. NEVER the synthesis/grounding
    token budget itself (the 80%-variance core). The orchestrator walks this list when
    a run approaches its --max-tokens ceiling; the terminal step is taken when
    should_short_circuit() fires."""
    return R.DEGRADE_ORDER


def should_short_circuit(cumulative_tokens: int, ceiling: int | None) -> bool:
    """E10 / STEAL_LIST #6c — the per-step short-circuit-to-synthesis predicate
    (Perplexity "reserve budget for synthesis", PERPLEXITY_COMPUTER.md:434).

    After each retrieval/critic ROUND the orchestrator calls this with the running
    `cumulative_tokens` and the opt-in `--max-tokens` `ceiling`. It returns True when
    the budget left for the rest of the run has fallen BELOW the reserved synthesis +
    grounding budget — i.e. ``ceiling - cumulative < RESERVE_FOR_SYNTHESIS``. On True,
    the orchestrator stops stepping (skips remaining retrieval/critic stages), takes
    the terminal ``short_circuit_to_synthesis`` step of `degrade_order`, and jumps to
    step 10/11 with whatever's been gathered — shipping a smaller-corpus grounded
    report instead of dying mid-pipeline.

    Inert when there is no ceiling (the `--max-tokens` cap is opt-in; ``None``/``0`` →
    nothing to reserve → never short-circuit). The comparison is STRICT: a remaining
    budget exactly equal to the reserve is still enough, so it does not fire."""
    if not ceiling:   # None or 0 → no opt-in ceiling, never short-circuit
        return False
    return (ceiling - cumulative_tokens) < R.RESERVE_FOR_SYNTHESIS
