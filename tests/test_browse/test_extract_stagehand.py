"""StagehandExtractProvider: wraps a live page.extract; mock the page."""

from __future__ import annotations

from unittest.mock import MagicMock

from bad_research.browse.extract_stagehand import StagehandExtractProvider


SCHEMA = {"type": "object", "properties": {"headline": {"type": "string"}}}


def test_extract_calls_page_extract_with_instruction_and_schema() -> None:
    page = MagicMock()
    page.extract.return_value = {"headline": "Big News"}
    prov = StagehandExtractProvider(page=page)
    out = prov.extract("ignored-when-session-bound", SCHEMA, instruction="get the headline")
    assert out == {"headline": "Big News"}
    args, kwargs = page.extract.call_args
    payload = args[0] if args else kwargs
    # Stagehand extract takes {instruction, schema}.
    assert payload["instruction"] == "get the headline"
    assert payload["schema"] == SCHEMA


def test_extract_no_page_returns_empty_dict() -> None:
    """No live session -> {} (graceful)."""
    prov = StagehandExtractProvider(page=None)
    assert prov.extract("x", SCHEMA) == {}


def test_extract_page_error_returns_empty_dict() -> None:
    page = MagicMock()
    page.extract.side_effect = RuntimeError("session closed")
    prov = StagehandExtractProvider(page=page)
    assert prov.extract("x", SCHEMA) == {}


def test_extract_non_dict_result_coerced_to_empty() -> None:
    page = MagicMock()
    page.extract.return_value = "not a dict"
    prov = StagehandExtractProvider(page=page)
    assert prov.extract("x", SCHEMA) == {}
