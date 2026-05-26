"""Base Protocol and factory for the EmbedProvider seam.

API providers only (no self-hosted GPU — SPEC decision #5: an idle GPU doesn't
amortize at single-user scale). Default impl: CohereEmbedProvider (embed-english-v3.0,
dim 1024). Asymmetric input_type: documents embedded at index time, queries at
retrieval time.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class EmbedProvider(Protocol):
    name: str
    dim: int

    def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"],
    ) -> list[list[float]]: ...


def get_embed_provider(name: str = "cohere", **kwargs) -> EmbedProvider:
    """Load an embed provider by name. Defaults to Cohere (the GA embedder)."""
    if name == "cohere":
        from bad_research.embed.cohere import CohereEmbedProvider

        return CohereEmbedProvider(**kwargs)

    raise ValueError(f"Unknown embed provider: {name!r}. Available: cohere")
