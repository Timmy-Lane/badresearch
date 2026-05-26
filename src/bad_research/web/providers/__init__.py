"""Web search providers (Plan 03) — keyed providers removed in KR-1; dir removed in KR-1 Task 4."""

from bad_research.web.providers.cascade import CascadeProvider, cascade_search
from bad_research.web.providers.searxng_provider import SearxngProvider

__all__ = ["CascadeProvider", "SearxngProvider", "cascade_search"]
