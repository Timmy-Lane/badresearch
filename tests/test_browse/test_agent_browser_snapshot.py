"""@eN accessibility-snapshot JSON parse → Snapshot{text, refs}. Pure parse, no subprocess."""

from __future__ import annotations

from bad_research.browse.agent_browser import Snapshot, normalize_ref, parse_snapshot
from tests.test_browse.conftest import EMPTY_SNAPSHOT_JSON, SNAPSHOT_JSON


def test_parse_extracts_refs_and_text() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert isinstance(snap, Snapshot)
    assert set(snap.refs) == {"e1", "e2", "e3", "e4", "e5", "e6"}
    assert snap.refs["e5"]["role"] == "button"
    assert snap.refs["e5"]["name"] == "Continue"
    assert "@e5 [button" in snap.text


def test_parse_extracts_title_and_url() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.title == "Example - Log in"
    assert snap.url == "https://example.com/login"


def test_grounding_has_ref_accepts_eN_and_at_eN_and_bare() -> None:  # noqa: N802
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.has_ref("@e3") is True
    assert snap.has_ref("e3") is True
    assert snap.has_ref("ref=e3") is True
    assert snap.has_ref("@e99") is False


def test_normalize_ref_strips_prefixes() -> None:
    assert normalize_ref("@e3") == "e3"
    assert normalize_ref("ref=e3") == "e3"
    assert normalize_ref("e3") == "e3"


def test_empty_snapshot_is_empty() -> None:
    snap = parse_snapshot(EMPTY_SNAPSHOT_JSON)
    assert snap.refs == {}
    assert snap.is_empty is True


def test_titled_page_with_refs_is_not_empty() -> None:
    snap = parse_snapshot(SNAPSHOT_JSON)
    assert snap.is_empty is False


def test_malformed_json_returns_empty_snapshot_no_raise() -> None:
    snap = parse_snapshot("not json at all <<<")
    assert snap.refs == {}
    assert snap.is_empty is True
    assert snap.text == ""


def test_success_false_returns_empty_snapshot() -> None:
    snap = parse_snapshot('{"success": false, "error": "no session"}')
    assert snap.refs == {}
    assert snap.is_empty is True
