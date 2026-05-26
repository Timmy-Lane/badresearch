"""Web search providers + the search cascade (Plan 03)."""

from bad_research.web.providers.cascade import CascadeProvider, cascade_search
from bad_research.web.providers.firecrawl_provider import FirecrawlProvider
from bad_research.web.providers.searxng_provider import SearxngProvider
from bad_research.web.providers.sonar_provider import SonarProvider
from bad_research.web.providers.tavily_provider import TavilyProvider

__all__ = [
    "CascadeProvider",
    "FirecrawlProvider",
    "SearxngProvider",
    "SonarProvider",
    "TavilyProvider",
    "cascade_search",
]
