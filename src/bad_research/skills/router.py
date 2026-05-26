"""Query router — classify the Step-1 decompose output into a pipeline mode.

Reuses the existing atomic-item analysis (no new classifier). The decision
tree is verbatim from DR-loops §9.2:

  agentic-fast  if atomic_items <= 2 AND no contradiction terms AND no time_periods
                AND response_format == "short" AND single domain
  light         elif response_format == "structured" OR atomic_items 3-6 OR mild tension
  full          else (multi-domain, contested, argumentative, time_periods, >=7 items)
"""
from __future__ import annotations

from typing import Literal

from bad_research.skills import routing_constants as R

Route = Literal["agentic-fast", "light", "full"]


def _atomic_count(decomp: dict) -> int:
    # atomic items = sub_questions + named entities (the Step-1 taxonomy)
    return len(decomp.get("sub_questions") or []) + len(decomp.get("entities") or [])


def _full_triggers(decomp: dict) -> list[str]:
    """The reasons (if any) a query MUST route full. Empty list → not forced full."""
    n = _atomic_count(decomp)
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
    if n > R.ROUTER_LIGHT_MAX_ATOMIC:
        reasons.append(f"{n} atomic items (>{R.ROUTER_LIGHT_MAX_ATOMIC})")
    return reasons


def classify_route(decomp: dict) -> Route:
    n = _atomic_count(decomp)
    fmt = decomp.get("response_format", "structured")
    time_periods = decomp.get("time_periods") or []
    contradiction = decomp.get("contradiction_terms") or []
    domains = decomp.get("domains") or []
    multi_domain = len(domains) >= 3

    # FULL: anything that needs Lens D primaries, dialectics, or breadth across domains.
    if (time_periods or fmt == "argumentative" or contradiction
            or multi_domain or n > R.ROUTER_LIGHT_MAX_ATOMIC):
        return "full"

    # AGENTIC-FAST: trivial, bounded, single-domain, short.
    if (n <= R.ROUTER_AGENTIC_MAX_ATOMIC and not contradiction
            and not time_periods and fmt == "short" and not multi_domain):
        return "agentic-fast"

    # LIGHT: the middle band — structured coverage or 3-6 atomic items.
    return "light"


def route_reason(decomp: dict) -> str:
    """A one-line, human-readable rationale for the chosen route.

    Used by the router skill to write the `## Route rationale` line and by the
    `bad route` CLI's JSON `reason` field.
    """
    route = classify_route(decomp)
    n = _atomic_count(decomp)
    if route == "full":
        triggers = _full_triggers(decomp)
        return "full: " + ("; ".join(triggers) if triggers else "complex query")
    if route == "agentic-fast":
        return f"agentic-fast: {n} atomic item(s), short, single-domain, no tension"
    return f"light: {n} atomic item(s) / structured coverage, no full-tier trigger"
