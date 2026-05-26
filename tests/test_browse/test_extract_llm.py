"""LLMExtractProvider: schema-shaped dict from mocked LLM; null-on-missing; chunking."""

from __future__ import annotations

import json

from bad_research.browse.extract_llm import LLMExtractProvider
from bad_research.web.base import WebResult
from tests.test_browse.conftest import FakeLLM, make_result


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "price": {"type": "integer"},
        "in_stock": {"type": "boolean"},
    },
}


def test_extract_returns_schema_shaped_dict() -> None:
    llm = FakeLLM([json.dumps({"title": "iPhone 15 Pro", "price": 999, "in_stock": True})])
    prov = LLMExtractProvider(llm=llm)
    src = make_result("iPhone 15 Pro — $999 — In stock. " * 30)
    out = prov.extract(src, SCHEMA, instruction="extract the product")
    assert out == {"title": "iPhone 15 Pro", "price": 999, "in_stock": True}
    # Used the cheap triage tier + extract temperature 0.1.
    assert llm.calls[0]["tier"] == "triage"
    assert llm.calls[0]["temperature"] == 0.1


def test_extract_null_on_missing_field() -> None:
    """LLM that cannot find a field returns null — provider passes it through, no fabrication."""
    llm = FakeLLM([json.dumps({"title": "Mystery", "price": None, "in_stock": None})])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("Mystery item, details unknown. " * 30), SCHEMA)
    assert out["price"] is None
    assert out["in_stock"] is None


def test_extract_accepts_raw_string_source() -> None:
    llm = FakeLLM([json.dumps({"title": "Doc", "price": 0, "in_stock": False})])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract("raw markdown content here, plenty of it. " * 30, SCHEMA)
    assert out["title"] == "Doc"


def test_extract_strips_markdown_code_fences() -> None:
    """Model wraps JSON in ```json fences — provider must still parse it."""
    fenced = "```json\n" + json.dumps({"title": "Fenced", "price": 1, "in_stock": True}) + "\n```"
    llm = FakeLLM([fenced])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out["title"] == "Fenced"


def test_extract_no_llm_returns_empty_dict() -> None:
    """No LLM provider wired -> graceful empty dict, never raises."""
    prov = LLMExtractProvider(llm=None)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out == {}


def test_extract_bad_json_returns_empty_dict() -> None:
    """Model returns non-JSON garbage -> {} (never crash the pipeline)."""
    llm = FakeLLM(["I could not extract anything, sorry!"])
    prov = LLMExtractProvider(llm=llm)
    out = prov.extract(make_result("content " * 100), SCHEMA)
    assert out == {}


def test_extract_chunks_long_content_and_merges() -> None:
    """Content > 100k chars -> multiple chunks; results merge (list fields concatenate)."""
    schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    chunk1 = json.dumps({"items": ["a", "b"]})
    chunk2 = json.dumps({"items": ["c", "d"]})
    llm = FakeLLM([chunk1, chunk2])
    prov = LLMExtractProvider(llm=llm)
    big = "x" * 150_000  # forces 2 chunks at 100k
    out = prov.extract(make_result(big), schema)
    assert out["items"] == ["a", "b", "c", "d"]
    assert len(llm.calls) == 2  # one LLM call per chunk
