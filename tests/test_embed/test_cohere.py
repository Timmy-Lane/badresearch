"""Tests for CohereEmbedProvider — mocks the cohere SDK (ClientV2).

[CORRECTION 2026-05-26] Verified against the installed cohere==7.0.0 SDK:

  1. Response accessor: ClientV2.embed(..., embedding_types=["float"]) returns an
     EmbedByTypeResponseEmbeddings whose float vectors live on the Python attribute
     ``.embeddings.float_`` (pydantic field name; JSON alias is "float"). Attribute
     access via ``.embeddings.float`` raises AttributeError on the real object. The
     mock below therefore shapes the response as ``.embeddings.float_`` to match
     reality; the provider reads ``float_`` first (with a ``.float`` fallback for
     forward-compat with SDKs that expose the alias as an attribute).
  2. Model id: the bare literal "embed-v3" (INTERFACES.md frozen default) is NOT a
     valid Cohere model id — the SDK only references embed-english-v3.0 /
     embed-multilingual-v3.0 / embed-v4.0, and the live API 400s on "embed-v3". The
     real v3 English default is "embed-english-v3.0" (still dim 1024). Tests assert
     the real id reaches client.embed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.embed.base import get_embed_provider


def _make_embed_response(vectors: list[list[float]]) -> SimpleNamespace:
    """Shape a cohere v2 embed response: .embeddings.float_ is a list of vectors.

    cohere==7.0.0 EmbedByTypeResponseEmbeddings exposes the float vectors on the
    Python attribute ``float_`` (the "float" JSON key is a pydantic alias only).
    """
    return SimpleNamespace(embeddings=SimpleNamespace(float_=vectors))


def _patch_sdk(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    import cohere

    factory = MagicMock(return_value=client)
    monkeypatch.setattr(cohere, "ClientV2", factory)


def _provider(monkeypatch: pytest.MonkeyPatch, client: MagicMock):
    from bad_research.embed.cohere import CohereEmbedProvider

    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    _patch_sdk(monkeypatch, client)
    return CohereEmbedProvider()


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from bad_research.embed.cohere import CohereEmbedProvider

    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    _patch_sdk(monkeypatch, MagicMock())
    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        CohereEmbedProvider()


def test_name_and_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = _provider(monkeypatch, MagicMock())
    assert prov.name == "cohere"
    assert prov.dim == 1024


def test_factory_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    _patch_sdk(monkeypatch, MagicMock())
    prov = get_embed_provider("cohere")
    assert prov.name == "cohere"


def test_embed_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.1, 0.2], [0.3, 0.4]])
    prov = _provider(monkeypatch, client)

    out = prov.embed(["a", "b"], input_type="document")
    assert out == [[0.1, 0.2], [0.3, 0.4]]


def test_document_input_type_maps_to_search_document(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.0]])
    prov = _provider(monkeypatch, client)

    prov.embed(["doc"], input_type="document")
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "search_document"
    assert kwargs["model"] == "embed-english-v3.0"
    assert kwargs["texts"] == ["doc"]
    assert kwargs["embedding_types"] == ["float"]


def test_query_input_type_maps_to_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.embed.return_value = _make_embed_response([[0.0]])
    prov = _provider(monkeypatch, client)

    prov.embed(["what is x"], input_type="query")
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "search_query"
