"""Stage E — filter junk + redundancy, then STORE survivors to the vault.

1. Plan 05 postfetch_filter: junk/login-wall/paywall/language → drop (returns
   a reason str if junk, None if it passes).
2. Redundancy clustering: pages sharing > redundancy_overlap of their shingled
   content (Jaccard, n=3) are derivative — keep the first (canonical), discount
   the rest (dossier 10 §3.4: "N sources are really 1 source in N outfits").
   Reuses hyperresearch core/similarity.py (shingle/jaccard) verbatim.
3. Store survivors to the vault (disk/SQLite). The raw body lives ON DISK; it
   is what RetrievalEngine.index reads, never what the caller sees.

Returns list[(note_id, body)] for Stage F to index.
"""

from __future__ import annotations

from typing import Any

from bad_research.core.similarity import jaccard, shingle


def filter_and_store(
    pages: list[Any],
    *,
    vault: Any,
    postfetch_filter: Any,
    redundancy_overlap: float,
    shingle_n: int,
) -> list[tuple[str, str]]:
    # 1. Junk filter (Plan 05).
    clean = [p for p in pages if postfetch_filter(p) is None]

    # 2. Redundancy clustering (brute Jaccard over shingles, n=3).
    kept: list[Any] = []
    kept_shingles: list[set[str]] = []
    for p in clean:
        body = getattr(p, "content", "") or ""
        sh = shingle(body, n=shingle_n)
        is_derivative = any(
            jaccard(sh, prev) > redundancy_overlap for prev in kept_shingles
        )
        if is_derivative:
            continue   # discount the derivative; the canonical is already kept
        kept.append(p)
        kept_shingles.append(sh)

    # 3. Store survivors to the vault (raw body -> disk).
    stored: list[tuple[str, str]] = []
    for p in kept:
        body = getattr(p, "content", "") or ""
        note_id = vault.store_note(
            title=getattr(p, "title", "") or p.url,
            body=body,
            url=p.url,
            provider=getattr(p, "serp_provider", "") or "fetch",
        )
        stored.append((note_id, body))
    return stored
