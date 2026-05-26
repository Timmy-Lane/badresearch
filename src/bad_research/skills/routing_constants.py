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


# ── KR-6 loop levers (dossier 16; INTERFACES_KEYLESS §8 frozen table) ─────────

# Grader loop — judge -> patch -> re-judge, capped (patch-not-regenerate => 3 is
# enough; NOT Claude's 20 which assumes full regeneration). dossier 16 §4.1.
MAX_GRADER_REVISIONS = 3

# Per-subagent runtime caps (Claude CE.5), keyless host guards. dossier 16 §3.2.
FETCHER_TOOLCALL_CAP = {"light": 10, "full": 20}  # tool calls per fetcher
FETCHER_TIMEOUT_S = 300       # soft-fail, return partial findings
INVESTIGATOR_TIMEOUT_S = 900  # depth stage scaled (Grok 200s x cost)
SUBAGENT_SOURCE_KILL = 100    # hard stop on sources touched (Claude)

# Reasoning-effort continuum — OpenAI's 4-level dial (dossier 16 §6.1) mapped onto
# the existing route + LLM-tier + per-stage fan-out levers. Wiring the stub
# --reasoning-effort flag (research.py) into a real config the router consumes.
EFFORT_LEVELS = ("minimal", "low", "medium", "high")
EFFORT_MAP = {
    "minimal": {"route": "light", "tier": "triage", "fetchers_max": 4,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "low":     {"route": "light", "tier": "work",   "fetchers_max": 8,  "loci_max": 0,
                "extended_thinking": False, "single_draft": True},
    "medium":  {"route": "full",  "tier": "default", "fetchers_max": 12, "loci_max": 4,
                "extended_thinking": True,  "single_draft": False},
    "high":    {"route": "full",  "tier": "heavy",  "fetchers_max": 12, "loci_max": 6,
                "extended_thinking": True,  "single_draft": False},
}

# Token-ceiling degrade order (Claude §12: cut tokens LAST). dossier 16 §6.2.
# Each step names what the orchestrator drops first when approaching --max-tokens.
DEGRADE_ORDER = (
    "tool-call-redundancy",   # 1. skip the redundancy-audit sub-step
    "fan-out-width",          # 2. fewer fetchers / fewer loci
    "model-tier",             # 3. heavy -> light on non-critical stages
    # NEVER cut synthesis/grounding token budget — the 80%-variance core.
)
