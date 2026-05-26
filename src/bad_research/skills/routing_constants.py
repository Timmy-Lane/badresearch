"""Frozen routing + bound constants for the Bad Research pipeline.

Every value cites INTERFACES.md / dossier 05 (DR-loops). DO NOT re-derive."""
from __future__ import annotations

# Agentic-fast ReAct loop bounds (Perplexity max_steps + Claude guards) — DR-loops §3,§5
AGENTIC_FAST_MAX_STEPS = 10
AGENTIC_FAST_MAX_CALLS = 15
AGENTIC_FAST_TIMEOUT_S = 300

# Parallel subagent fan-out (Claude depth-1) — INTERFACES / CLR §CE.5,§CE.10
SUBAGENT_FANOUT_DEFAULT = 3
SUBAGENT_FANOUT_MAX = 20

# Clarifier (OpenAI default-proceed) — DR-loops §1 / ODR §5
CLARIFY_MAX_QUESTIONS = 3

# Funnel + retrieval — INTERFACES
READ_TOP_K_CEILING = 80
RELEVANCE_GATE = 0.70

# Router heuristic boundaries — DR-loops §9.2 (the verbatim decision tree)
ROUTER_AGENTIC_MAX_ATOMIC = 2
ROUTER_LIGHT_MAX_ATOMIC = 6
