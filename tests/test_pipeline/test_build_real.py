"""REAL builder-path integration tests (Plan-08 recheck).

The existing pipeline/CLI tests monkeypatch the stage SEAMS (`_route`/`_gather`/
`_retrieve`/`_synthesize`), so the dependency-construction lines inside
`cli/research.py` — the `get_llm_provider` / `get_embed_provider` / `get_reranker`
import+call sites — never executed. That hid three wrong import names that broke
real runtime paths (`bad verify-citations`, `bad retrieve`, `bad funnel-gather`,
and silently degraded `pipeline._retrieve` to `[]`).

These tests exercise the ACTUAL builder helpers (`_build_embedder`,
`_build_reranker`, `_build_engine`, and the verify-citations LLM dep builder).
They patch the anthropic/cohere SDK clients at the SDK level (same pattern as the
provider unit tests) and set dummy env keys, then call the builders directly and
assert they return working objects WITHOUT ImportError. Any wrong import name in a
builder helper fails here — the bug class the seam-patching tests could not catch.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.config import BadResearchConfig
from bad_research.embed.base import EmbedProvider
from bad_research.llm.base import LLMProvider
from bad_research.retrieval.rerank import BGEReranker, CohereReranker


def _patch_cohere(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch cohere.ClientV2 at its source module so the lazy provider import
    picks up the mock — no network."""
    import cohere

    client = MagicMock()
    monkeypatch.setattr(cohere, "ClientV2", MagicMock(return_value=client))
    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    return client


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import anthropic

    client = MagicMock()
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=client))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return client


# ── fix #2: _build_embedder runs the REAL get_embed_provider import + call ───
def test_build_embedder_constructs_real_cohere_provider(monkeypatch):
    _patch_cohere(monkeypatch)
    from bad_research.cli.research import _build_embedder

    cfg = BadResearchConfig()  # default embed_model = embed-english-v3.0
    emb = _build_embedder(cfg)

    # Real CohereEmbedProvider satisfying the EmbedProvider Protocol.
    assert isinstance(emb, EmbedProvider)
    assert emb.name == "cohere"
    assert emb.dim == 1024


def test_build_embedder_threads_config_model(monkeypatch):
    _patch_cohere(monkeypatch)
    from bad_research.cli.research import _build_embedder

    cfg = BadResearchConfig()
    cfg.embed_model = "embed-multilingual-v3.0"
    emb = _build_embedder(cfg)
    # The model kwarg must be forwarded from config through get_embed_provider.
    assert emb._model == "embed-multilingual-v3.0"


# ── fix #3: _build_reranker passes the CONFIG object, not a model-name string ─
def test_build_reranker_with_cohere_key(monkeypatch):
    _patch_cohere(monkeypatch)
    from bad_research.cli.research import _build_reranker

    cfg = BadResearchConfig()  # rerank_model = rerank-v3.5 (a 'rerank*' id)
    rr = _build_reranker(cfg)
    # rerank* id + COHERE_API_KEY present -> the Cohere reranker.
    assert isinstance(rr, CohereReranker)
    assert rr.model == "rerank-v3.5"


def test_build_reranker_falls_back_to_bge_offline(monkeypatch):
    # No COHERE_API_KEY and a bge model id -> the offline BGE reranker, with an
    # injected scorer so no heavy FlagEmbedding/torch import happens.
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    import bad_research.retrieval.rerank as RR  # noqa: N812
    from bad_research.cli.research import _build_reranker

    # Force the offline branch deterministically by feeding a bge model id.
    cfg = BadResearchConfig()
    cfg.rerank_model = "bge-reranker-v2-m3"
    monkeypatch.setattr(RR, "_default_bge_scorer", lambda model: (lambda pairs: [0.5] * len(pairs)))
    rr = _build_reranker(cfg)
    assert isinstance(rr, BGEReranker)
    assert rr.model == "bge-reranker-v2-m3"


# ── _build_engine wires both real builders into a RetrievalEngine ────────────
def test_build_engine_constructs_real_engine(monkeypatch, tmp_path):
    _patch_cohere(monkeypatch)
    from bad_research.cli.research import _build_engine
    from bad_research.retrieval.engine import RetrievalEngine

    cfg = BadResearchConfig()
    vault = SimpleNamespace(root=tmp_path)  # _build_engine only reads .root
    engine = _build_engine(cfg, vault)

    assert isinstance(engine, RetrievalEngine)
    # Embedder + reranker are the REAL provider objects (no ImportError on build).
    assert isinstance(engine.embedder, EmbedProvider)
    assert isinstance(engine.reranker, CohereReranker | BGEReranker)
    # The per-vault lance/cache dirs were created under .bad-research/.
    assert (tmp_path / ".bad-research").is_dir()


# ── fix #1: the verify-citations dep builder runs the REAL get_llm_provider ──
def test_verify_report_builds_real_llm_provider(monkeypatch, tmp_path):
    """Exercise `_verify_report`'s dependency construction so the real
    `from bad_research.llm.base import get_llm_provider` + `get_llm_provider(
    "anthropic", config=cfg)` line executes. We stub the NLI model and the
    verifier's verify() (heavy/irrelevant here) at their SOURCE modules — the
    function's local `from X import Y` then picks up the fakes — but let the LLM
    provider be built FOR REAL. That LLM-build line is what fix #1 corrects; a
    wrong import name (the old `get_llm`) raises ImportError and fails this test.
    """
    _patch_anthropic(monkeypatch)

    import bad_research.cli.research as research
    import bad_research.config as config_mod
    import bad_research.core.vault as vault_mod
    import bad_research.grounding.anchors as anchors_mod
    import bad_research.grounding.nli as nli_mod
    import bad_research.grounding.verifier as verifier_mod

    built = {}

    class _FakeNLI:
        def __init__(self, *a, **k):
            pass

    class _FakeVerifier:
        def __init__(self, *, nli, llm):
            built["llm"] = llm  # the object the real get_llm_provider call returned

        def verify(self, report_md, store, note_bodies):
            return SimpleNamespace(findings=[])

    # Patch at the SOURCE modules — `_verify_report` does local `from <mod> import
    # <name>`, which reads the (now patched) module attribute.
    monkeypatch.setattr(nli_mod, "CrossEncoderNLI", _FakeNLI)
    monkeypatch.setattr(verifier_mod, "CitationVerifier", _FakeVerifier)
    monkeypatch.setattr(anchors_mod, "AnchorStore", lambda conn: MagicMock())

    vault = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(vault_mod.Vault, "discover", staticmethod(lambda: vault))
    monkeypatch.setattr(config_mod.BadResearchConfig, "load", classmethod(lambda cls: cls()))

    report = tmp_path / "report.md"
    report.write_text("The answer is X [1].", encoding="utf-8")

    out = research._verify_report(str(report), vault_tag="t")
    assert out == []  # stubbed verify -> no findings
    # The real get_llm_provider("anthropic", config=cfg) returned a working provider.
    assert isinstance(built["llm"], LLMProvider)
    assert built["llm"].name == "anthropic"
