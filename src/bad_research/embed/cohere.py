"""CohereEmbedProvider — the default API embedder (embed-english-v3.0, dim 1024).

Asymmetric input_type per SPEC §7: "document" at index time, "query" at retrieval
time. Maps to Cohere's search_document / search_query input types. Uses the v2 client
(cohere.ClientV2.embed) with embedding_types=["float"].

[CORRECTION 2026-05-26] Verified against the installed cohere==7.0.0 SDK; two facts
diverge from INTERFACES.md's frozen draft:

  1. Model id. INTERFACES.md froze the default as the bare literal "embed-v3". That
     is NOT a valid Cohere model id — the SDK references only embed-english-v3.0,
     embed-multilingual-v3.0 (+ light variants) and embed-v4.0, and the live API
     400s on "embed-v3". The real v3 English embedder (still dim 1024) is
     "embed-english-v3.0", which is now the default here.
  2. Response accessor. ClientV2.embed(..., embedding_types=["float"]) returns an
     EmbedByTypeResponseEmbeddings whose float vectors live on the Python attribute
     ``.embeddings.float_`` (the "float" JSON key is a pydantic *alias*; attribute
     access via ``.float`` raises AttributeError on the real object). We read
     ``float_`` first, falling back to ``float`` only for forward-compat with SDKs
     that surface the alias as an attribute.

The seam contract is unchanged: ``embed(texts, *, input_type) -> list[list[float]]``,
``name="cohere"``, ``dim=1024``.
"""

from __future__ import annotations

import os
from typing import Any, Literal

# Cohere embed v3 family is 1024-dim (INTERFACES.md frozen constant; dossier 02).
_DIM = 1024

_INPUT_TYPE_MAP = {
    "document": "search_document",
    "query": "search_query",
}


class CohereEmbedProvider:
    """EmbedProvider backed by the Cohere embeddings API."""

    name = "cohere"
    dim = _DIM

    def __init__(self, api_key: str | None = None, model: str = "embed-english-v3.0") -> None:
        try:
            import cohere
        except ImportError as exc:
            raise ImportError(
                'cohere provider requires: pip install "bad-research[cohere]"'
            ) from exc

        key = api_key or os.environ.get("COHERE_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "COHERE_API_KEY is not set. Get a key at "
                "https://dashboard.cohere.com/api-keys and export it."
            )

        self._model = model
        self._client = cohere.ClientV2(api_key=key)

    def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"],
    ) -> list[list[float]]:
        cohere_input_type = _INPUT_TYPE_MAP[input_type]
        resp = self._client.embed(
            texts=texts,
            model=self._model,
            input_type=cohere_input_type,
            embedding_types=["float"],
        )
        return _read_float_vectors(resp)


def _read_float_vectors(resp: Any) -> list[list[float]]:
    """Pull the float vectors off a cohere v2 embed response.

    cohere==7.0.0 exposes them as ``resp.embeddings.float_`` (pydantic field; the
    "float" JSON key is an alias only). We prefer ``float_`` and fall back to
    ``float`` for forward/backward SDK compatibility.
    """
    embeddings = resp.embeddings
    vectors = getattr(embeddings, "float_", None)
    if vectors is None:
        vectors = getattr(embeddings, "float", None)
    if vectors is None:
        raise RuntimeError(
            "Cohere embed response carried no float vectors "
            "(expected .embeddings.float_); did embedding_types include 'float'?"
        )
    return vectors
