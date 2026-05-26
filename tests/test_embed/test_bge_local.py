import pytest

pytest.importorskip("sentence_transformers")  # [local] extra; skip in keyless CI

from bad_research.embed.base import EmbedProvider
from bad_research.embed.bge_local import BgeLocalEmbedProvider

pytestmark = pytest.mark.local


def test_bge_local_is_an_embed_provider_with_dim_384():
    p = BgeLocalEmbedProvider()
    assert isinstance(p, EmbedProvider)
    assert p.dim == 384


def test_bge_local_query_prefix_changes_the_vector():
    p = BgeLocalEmbedProvider()
    [d] = p.embed(["async runtime"], input_type="document")
    [q] = p.embed(["async runtime"], input_type="query")
    assert len(d) == 384 and len(q) == 384
    # The query prefix perturbs the embedding (asymmetric encoding).
    assert d != q
