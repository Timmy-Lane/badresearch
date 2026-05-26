"""BrowserUseProvider — Tier-3 self-host agentic browse (dossier 03 §3).

Wraps browser_use.Agent (indexed-DOM loop, picks actions by integer index -> no selector
hallucination). On `done`, the final result becomes WebResult.content. A replay_key hit
returns a cached page body without running the loop (ActCache, dossier 03 §1.5). The Agent
is async (like crawl4ai's crawler) so we drive it with asyncio.run. Optional browser_use
lib — if absent, the factory never imports this module.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from bad_research.browse.cache import ActCache
from bad_research.web.base import WebResult


class BrowserUseProvider:
    name = "browser-use"

    def __init__(self, llm: Any | None = None, cache: ActCache | None = None) -> None:
        self._llm = llm
        self._cache = cache

    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult:
        # Replay short-circuit: cached script -> zero-cost WebResult.
        if replay_key and self._cache is not None:
            cached = self._cache.get(replay_key)
            if cached is not None:
                return WebResult(
                    url=cached.get("final_url", url),
                    title=cached.get("title", ""),
                    content=cached.get("content", ""),
                    fetched_at=datetime.now(UTC),
                    metadata={"replayed": True, "replay_key": replay_key},
                )

        result = asyncio.run(self._run(url, instruction, max_steps, variables))

        if replay_key and self._cache is not None:
            self._cache.put(replay_key, {"content": result.content,
                                         "final_url": result.url, "title": result.title})
        return result

    async def _run(self, url: str, instruction: str, max_steps: int,
                   variables: dict | None) -> WebResult:
        from browser_use import Agent

        task = f"Go to {url}. {instruction}"
        agent_kwargs: dict[str, Any] = {"task": task, "llm": self._llm}
        if variables:
            agent_kwargs["sensitive_data"] = variables  # %var% redaction (dossier 03 §3.3)
        agent = Agent(**agent_kwargs)
        history = await agent.run(max_steps=max_steps)

        content = ""
        if hasattr(history, "final_result"):
            content = history.final_result() or ""
        elif isinstance(history, str):
            content = history
        return WebResult(url=url, title="", content=content or "",
                         fetched_at=datetime.now(UTC), metadata={"tier": 3})
