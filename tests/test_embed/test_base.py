"""EmbedProvider seam: Protocol + keyless factory (default bge-local, [local])."""

from __future__ import annotations

import importlib.util

import pytest

from bad_research.embed.base import EmbedProvider, get_embed_provider


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown embed provider"):
        get_embed_provider("does-not-exist")


def test_protocol_is_runtime_checkable() -> None:
    class _Fake:
        name = "fake"
        dim = 8

        def embed(self, texts, *, input_type):
            return [[0.0] * self.dim for _ in texts]

    assert isinstance(_Fake(), EmbedProvider)


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="[local] extra not installed (sentence-transformers / bge_local)",
)
def test_bge_local_is_default() -> None:
    prov = get_embed_provider()  # default -> bge-local
    assert prov.name.startswith("bge")


def test_bge_local_raises_helpful_without_local_extra() -> None:
    """Without [local] (or before KR-5 builds embed/bge_local.py), the default
    raises ImportError with an install hint — never a bare ModuleNotFoundError."""
    if importlib.util.find_spec("bad_research.embed.bge_local") is not None:
        pytest.skip("embed/bge_local.py exists (KR-5 landed)")
    with pytest.raises(ImportError, match=r"local"):
        get_embed_provider("bge-local")
