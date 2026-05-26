"""BrowserbaseProvider — Tier-3b anti-bot/login agentic browse (dossier 03 §1, §3b).

Connects over CDP to connect.browserbase.com with verified stealth + residential proxy +
captcha-solve, then drives a Stagehand agent.execute(instruction). The connection +
Stagehand wiring is isolated in `_make_stagehand` so tests can monkeypatch it (no SDK
needed to test the logic). Key-gated by BROWSERBASE_API_KEY. Same ActCache replay
short-circuit as Browser-Use. Any failure -> empty WebResult (graceful; caller treats it
as junk, never crashes).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from bad_research.browse.cache import ActCache
from bad_research.web.base import WebResult


def _make_stagehand(*, api_key: str, verified: bool = True) -> Any:
    """Create a connected Stagehand client over a verified Browserbase session.

    Isolated for testability. Requires the `stagehand` Python SDK at runtime.
    """
    from stagehand import Stagehand  # optional dep, imported lazily

    return Stagehand(
        env="BROWSERBASE",
        api_key=api_key,
        browserbase_session_create_params={
            "browserSettings": {
                "advancedStealth": True,
                "verified": verified,          # stealth_level 2 (dossier 03 §1.1)
                "solveCaptchas": True,
                "proxies": True,
            }
        },
    )


class BrowserbaseProvider:
    name = "browserbase"

    def __init__(self, cache: ActCache | None = None) -> None:
        self._cache = cache
        self._key = os.environ.get("BROWSERBASE_API_KEY", "")

    def browse(self, url: str, instruction: str, *, max_steps: int = 12,
               variables: dict | None = None, replay_key: str | None = None) -> WebResult:
        if replay_key and self._cache is not None:
            cached = self._cache.get(replay_key)
            if cached is not None:
                return WebResult(url=cached.get("final_url", url), title=cached.get("title", ""),
                                 content=cached.get("content", ""), fetched_at=datetime.now(UTC),
                                 metadata={"replayed": True, "replay_key": replay_key})

        try:
            stagehand = _make_stagehand(api_key=self._key, verified=True)
        except Exception:
            return WebResult(url=url, title="", content="", fetched_at=datetime.now(UTC),
                             metadata={"tier": "3b", "error": "connect_failed"})

        try:
            page = stagehand.page
            page.goto(url) if hasattr(page, "goto") else None
            agent = stagehand.agent({"maxSteps": max_steps})
            agent.execute(instruction)
            # Read the result with the tree (cheap), not a typed extract (dossier 03 §1.4 rule).
            extracted = {}
            if hasattr(page, "extract"):
                extracted = page.extract({"instruction": instruction,
                                          "schema": {"type": "object",
                                                     "properties": {"text": {"type": "string"}}}}) or {}
            content = extracted.get("text") if isinstance(extracted, dict) else ""
            if not content and hasattr(page, "content"):
                content = page.content() or ""
            final_url = getattr(page, "url", url) or url
            result = WebResult(url=final_url, title="", content=content or "",
                               fetched_at=datetime.now(UTC), metadata={"tier": "3b"})
        except Exception:
            result = WebResult(url=url, title="", content="", fetched_at=datetime.now(UTC),
                               metadata={"tier": "3b", "error": "browse_failed"})
        finally:
            try:
                stagehand.close()
            except Exception:
                pass

        if result.content and replay_key and self._cache is not None:
            self._cache.put(replay_key, {"content": result.content,
                                         "final_url": result.url, "title": result.title})
        return result
