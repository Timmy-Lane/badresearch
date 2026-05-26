"""Tests for populating the `sources` provenance table (INTERFACES.md)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from bad_research.quality.sources import build_source_row, source_id, upsert_source
from bad_research.web.base import WebResult


def test_source_id_is_16_char_sha256_of_canonical_url():
    sid = source_id("https://Example.com/Post/?utm_source=x")
    assert len(sid) == 16
    assert all(c in "0123456789abcdef" for c in sid)
    # tracking-param twin canonicalizes to the same id (stable across reposts of same URL)
    assert sid == source_id("https://example.com/post")


def test_build_source_row_fields_match_schema():
    r = WebResult(url="https://www.sec.gov/filing", title="10-K",
                  content="body " * 50, fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    row = build_source_row(r, fetch_provider="tavily", fetch_tier=2)
    assert row["domain"] == "www.sec.gov"
    assert row["domain_tier"] == 1.30          # primary multiplier
    assert row["tier"] == 0                      # primary prefetch_priority
    assert row["fetch_provider"] == "tavily"
    assert row["source_id"] == source_id("https://www.sec.gov/filing")


def test_build_source_row_carries_dual_temporal_dates():
    r = WebResult(url="https://x.example/a", title="t", content="b " * 50,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    r.metadata["document_date"] = "2024-09-28"
    r.metadata["event_date"] = "2024-07-01"
    row = build_source_row(r, fetch_provider="exa", fetch_tier=0)
    assert row["document_date"] == "2024-09-28"
    assert row["event_date"] == "2024-07-01"


def test_upsert_source_writes_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE sources (source_id TEXT PRIMARY KEY, url TEXT, domain TEXT, "
        "domain_tier REAL, fetch_provider TEXT, tier INT, fetched_at TEXT, "
        "document_date TEXT, event_date TEXT)"
    )
    r = WebResult(url="https://www.sec.gov/filing", title="t", content="b " * 50,
                  fetched_at=datetime(2026, 5, 26, tzinfo=UTC))
    upsert_source(conn, r, fetch_provider="tavily", fetch_tier=2)
    upsert_source(conn, r, fetch_provider="tavily", fetch_tier=2)  # again -> no dup
    rows = conn.execute("SELECT source_id, domain_tier, tier FROM sources").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == 1.30
    assert rows[0][2] == 0
