"""Tests for the EmbedProvider seam types and factory."""

from __future__ import annotations

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
