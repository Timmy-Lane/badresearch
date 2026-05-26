"""AgentQLExtractProvider: JSON-Schema->AQL translation + mocked HTTP query-data."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bad_research.browse.extract_agentql import AgentQLExtractProvider, json_schema_to_aql
from bad_research.web.base import WebResult


def test_json_schema_to_aql_object_and_types() -> None:
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "integer"},
            "in_stock": {"type": "boolean"},
        },
    }
    aql = json_schema_to_aql(schema)
    assert aql.startswith("{") and aql.endswith("}")
    assert "title" in aql
    assert "price(integer)" in aql
    assert "in_stock(boolean)" in aql


def test_json_schema_to_aql_array_of_objects() -> None:
    schema = {
        "type": "object",
        "properties": {
            "products": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "price": {"type": "integer"}}},
            }
        },
    }
    aql = json_schema_to_aql(schema)
    assert "products[]" in aql
    assert "name" in aql and "price(integer)" in aql


def test_extract_posts_query_and_returns_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"data": {"title": "Hello", "price": 999}}
    resp.raise_for_status.return_value = None
    client.post.return_value = resp
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    src = WebResult(url="https://shop.test/p", title="P", content="...", raw_html="<html>...</html>")
    out = prov.extract(src, "{ title  price(integer) }")
    assert out == {"title": "Hello", "price": 999}
    # Posted to the query-data endpoint with the api key header.
    _, kwargs = client.post.call_args
    assert "X-API-Key" in kwargs["headers"]


def test_extract_string_source_sends_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raw-URL source -> AgentQL navigates itself (body carries `url`)."""
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"data": {"x": 1}}
    resp.raise_for_status.return_value = None
    client.post.return_value = resp
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    prov.extract("https://shop.test/p", "{ x(integer) }")
    _, kwargs = client.post.call_args
    assert kwargs["json"]["url"] == "https://shop.test/p"


def test_extract_http_error_returns_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server error -> {} (graceful — ladder keeps prose), never raises."""
    monkeypatch.setenv("AGENTQL_API_KEY", "test-key")
    client = MagicMock()
    client.post.side_effect = RuntimeError("boom")
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    import httpx
    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=client))

    prov = AgentQLExtractProvider()
    out = prov.extract(WebResult(url="https://x.test", title="x", content="c"), "{ a }")
    assert out == {}
