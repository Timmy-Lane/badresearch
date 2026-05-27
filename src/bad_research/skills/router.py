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
    redundancy, then fan-out width, then model tier — NEVER the synthesis/grounding
    token budget (the 80%-variance core). The orchestrator walks this list when a
    run approaches its --max-tokens ceiling."""
    return R.DEGRADE_ORDER
