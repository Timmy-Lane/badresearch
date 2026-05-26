"""StagehandExtractProvider — Tier-2 extraction against a LIVE Stagehand page.

Used only mid-Tier-3, when a Browserbase/Stagehand session is already open (interactive
widgets / link-ID extraction crawl4ai can't reach — dossier 03 §1.2). Calls
page.extract({instruction, schema}). The verbatim EXTRACT_SYSTEM_PROMPT lives in the
Stagehand server (products/BROWSERBASE_PRODUCT_CODE.md:4313-4327); this is the client call.
No page -> {} (graceful).
"""

from __future__ import annotations

from typing import Any

from bad_research.web.base import WebResult


class StagehandExtractProvider:
    name = "stagehand"

    def __init__(self, page: Any | None = None) -> None:
        self._page = page

    def extract(self, source: str | WebResult, schema: dict[str, Any] | str,
                instruction: str = "") -> dict:
        if self._page is None:
            return {}
        try:
            result = self._page.extract({"instruction": instruction, "schema": schema})
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
