"""REAL builder-path integration tests (KR-1 keyless rewire).

The pipeline/CLI tests monkeypatch the stage SEAMS, so the dependency-construction
lines inside cli/research.py never executed. These exercise the ACTUAL builder
helpers to catch wrong import names / broken keyless wiring.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bad_research.config import BadResearchConfig
from bad_research.llm.base import LLMProvider
from bad_research.retrieval.rerank import ClaudeCodeReranker


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import anthropic

    client = MagicMock()
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=client))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return client


def test_build_embedder_is_none_keyless_default():
    from bad_research.cli.research import _build_embedder

    cfg = BadResearchConfig()  # default: FTS-only, no neural recall
    assert _build_embedder(cfg) is None


def test_build_reranker_default_is_claude_code():
    from bad_research.cli.research import _build_reranker

    cfg = BadResearchConfig()  # default reranker = "host"
    rr = _build_reranker(cfg)
    assert isinstance(rr, ClaudeCodeReranker)


def test_build_engine_constructs_fts_only_engine(tmp_path):
    from bad_research.cli.research import _build_engine
    from bad_research.retrieval.engine import RetrievalEngine

    cfg = BadResearchConfig()
    vault = SimpleNamespace(root=tmp_path)  # _build_engine only reads .root
    engine = _build_engine(cfg, vault)

    assert isinstance(engine, RetrievalEngine)
    assert engine.embedder is None          # keyless FTS-only
    assert engine.store is None             # no LanceDB constructed
    assert isinstance(engine.reranker, ClaudeCodeReranker)
    assert (tmp_path / ".bad-research").is_dir()


def test_verify_report_builds_real_llm_provider(monkeypatch, tmp_path):
    """anthropic stays a CORE dep: the verify-citations LLM builder runs for real."""
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
        def __init__(self, *, nli, llm, effort=None):
            built["llm"] = llm
            built["effort"] = effort

        def verify(self, report_md, store, note_bodies):
            return SimpleNamespace(findings=[])

    monkeypatch.setattr(nli_mod, "CrossEncoderNLI", _FakeNLI)
    monkeypatch.setattr(verifier_mod, "CitationVerifier", _FakeVerifier)
    monkeypatch.setattr(anchors_mod, "AnchorStore", lambda conn: MagicMock())

    vault = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(vault_mod.Vault, "discover", staticmethod(lambda: vault))
    monkeypatch.setattr(config_mod.BadResearchConfig, "load", classmethod(lambda cls: cls()))

    report = tmp_path / "report.md"
    report.write_text("The answer is X [1].", encoding="utf-8")

    out = research._verify_report(str(report), vault_tag="t")
    assert out == []
    assert isinstance(built["llm"], LLMProvider)
    assert built["llm"].name == "anthropic"
