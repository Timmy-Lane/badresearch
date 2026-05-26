"""fetch_tiered — the Tier 0->3 escalation ladder (dossier 03 §6).

Walk tiers in order; escalate only when a cheaper tier's WebResult trips a gate
(looks_like_junk / looks_like_login_wall — both verbatim from web/base.py). The caller
controls the ceiling with tier_max, and opts into typed output (schema) or interaction
(instruction). Every optional tier degrades gracefully: a missing provider/lib/key means
that rung is skipped and the best lower-tier result is returned. Providers are injectable
for testing (the `_tier0` / `_tier1_factory` / `_extractor` / `_browse` keyword args);
production uses the real factories by default.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bad_research.web.base import WebResult


def _is_empty(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Empty or near-empty")


def _is_bot_wall(result: WebResult) -> bool:
    return (result.looks_like_junk() or "").startswith("Bot detection page")


def fetch_tiered(
    url: str,
    *,
    tier_max: int,
    instruction: str | None = None,
    schema: dict | str | None = None,
    replay_key: str | None = None,
    variables: dict | None = None,
    # ---- injection seams (tests pass mocks; production gets real defaults) ----
    _tier0: Any | None = None,
    _tier1_factory: Callable[[], Any | None] | None = None,
    _extractor: Any | None = None,
    _browse: Any | None = None,
    _llm: Any | None = None,
) -> WebResult:
    # ---------- Tier 0: HTTP ----------
    if _tier0 is None:
        from bad_research.web.base import get_provider

        _tier0 = get_provider("builtin")
    result = _tier0.fetch(url)

    # ---------- Tier 1: crawl4ai JS render ----------
    if tier_max >= 1 and _is_empty(result):
        if _tier1_factory is None:
            def _tier1_factory():
                try:
                    from bad_research.web.base import get_provider
                    return get_provider("crawl4ai")
                except ImportError:
                    return None
        t1 = _tier1_factory()
        if t1 is not None:
            try:
                t1_result = t1.fetch(url)
                if len(t1_result.content.strip()) >= len(result.content.strip()):
                    result = t1_result
            except Exception:
                pass  # keep Tier-0 result

    # ---------- Decide on Tier-3 escalation triggers ----------
    want_anti_bot = tier_max >= 3 and _is_bot_wall(result)
    want_login = tier_max >= 3 and result.looks_like_login_wall(url)
    want_interactive = tier_max >= 3 and bool(instruction)

    if want_anti_bot or want_login or want_interactive:
        browse_result = _do_browse(
            url, instruction or "Read the main content of this page.",
            anti_bot=want_anti_bot, replay_key=replay_key, variables=variables,
            browse=_browse,
        )
        if browse_result is not None and browse_result.content.strip():
            result = browse_result

    # ---------- Tier 2: typed extraction (output-shape request) ----------
    if schema is not None and tier_max >= 2:
        extractor = _extractor
        if extractor is None:
            from bad_research.browse.base import get_extract_provider

            extractor = get_extract_provider("llm")
            if extractor is not None and _llm is not None and hasattr(extractor, "_llm"):
                extractor._llm = _llm
        if extractor is not None:
            try:
                data = extractor.extract(result, schema, instruction or "")
            except Exception:
                data = {}
            if data:  # non-empty -> attach; {} leaves result untouched (graceful)
                result.metadata["extracted"] = data

    return result


def _do_browse(url, instruction, *, anti_bot, replay_key, variables, browse) -> WebResult | None:
    """Resolve the single keyless browse provider (agent-browser, KR-4) and run it.
    Returns None if no provider is available (caller keeps the lower-tier result).
    `anti_bot` is accepted for signature stability but no longer routes to a
    separate cloud backend — the keyless agent-browser handles every case."""
    prov = browse
    if prov is None:
        from bad_research.browse.base import get_browse_provider

        prov = get_browse_provider()
    if prov is None:
        return None
    try:
        return prov.browse(url, instruction, replay_key=replay_key, variables=variables)
    except Exception:
        return None
