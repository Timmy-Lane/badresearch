"""funnel/ — the six-stage scraper funnel (SPEC §6, dossier 10).

Public API:
    gather(query, *, mode) -> list[Chunk]   # the ONLY entry point callers use
    FunnelConfig                              # tiered constants

Invariant: callers receive reranked Chunk[] + [[note-id]] pointers,
never raw page bodies. Stages A–E run at $0 model cost.
"""

from __future__ import annotations

from bad_research.funnel.config import FunnelConfig
from bad_research.funnel.orchestrator import gather

__all__ = ["FunnelConfig", "gather"]
