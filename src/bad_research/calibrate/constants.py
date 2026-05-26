"""Frozen calibration constants — single source of truth (cite, never re-derive).

OFFLINE/reporting only (SPEC §10 Excluded list): these power the calibration
harness (`bad calibrate`), never a per-run gate.
"""

from __future__ import annotations

# --- The 5-axis LLM-judge rubric (dossier 09 §B7, CLAUDE_RESEARCH.md:39; SPEC §14) ---
# Single strong-model call (NOT an ensemble — ensemble tested WORSE, dossier 09 §B7).
# Each axis scored 0.0–1.0; PASS iff every axis ≥ AXIS_PASS_THRESHOLD AND mean ≥ OVERALL_PASS_THRESHOLD.
JUDGE_AXES = ("factual", "citation", "completeness", "source_quality", "efficiency")
AXIS_PASS_THRESHOLD = 0.70  # per-axis floor                          [SPEC §8 0.70 bar reuse]
OVERALL_PASS_THRESHOLD = 0.75  # mean across axes                     [dossier 09 §B7]
JUDGE_TIER = "heavy"  # Opus; Sonnet acceptable (dossier 09 §A4 table L223)
JUDGE_MAX_TOKENS = 2048
JUDGE_TEMPERATURE = 0.0  # deterministic scoring                      [cookbook]

# --- 5-component cost metering (Perplexity, dossier 09 §A4.2 / 05§7) ---
COST_COMPONENTS = ("input", "output", "reasoning", "citation", "search_queries")
# Per-1M-token USD prices for the model tiers (current public Anthropic pricing; behind the seam).
# Used only by the OFFLINE meter to convert token counts → USD; never gates a run.
TIER_PRICE_USD_PER_MTOK = {  # [INTERFACES Models]
    "triage": {"input": 1.00, "output": 5.00},  # claude-haiku-4-5
    "work": {"input": 3.00, "output": 15.00},  # claude-sonnet-4-6
    "heavy": {"input": 15.00, "output": 75.00},  # claude-opus-4-7
}
SEARCH_QUERY_PRICE_USD = 0.005  # per provider search call (Tavily/Exa estimate)  [dossier 02]

# --- Calibration set (dossier 09 §B7, SPEC §14: "~20-query research set") ---
DEFAULT_CALIBRATION_SET_SIZE = 20  # frozen eval set; out-of-pipeline only  [DR-loops eval-set size]
