"""The keyless default must import with NO torch / lancedb / sentence-transformers
installed. This test asserts the retrieval package + engine + reranker + cache
import without touching any [local] dependency."""
import builtins
import importlib


def test_retrieval_imports_without_local_deps(monkeypatch):
    blocked = {"lancedb", "pyarrow", "torch", "sentence_transformers", "FlagEmbedding"}
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        root = name.split(".")[0]
        if root in blocked:
            raise ImportError(f"blocked in keyless test: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    # Force fresh import of the package + the three reworked modules.
    for mod in ("bad_research.retrieval",
                "bad_research.retrieval.engine",
                "bad_research.retrieval.rerank",
                "bad_research.retrieval.cache"):
        importlib.reload(importlib.import_module(mod))
    from bad_research.retrieval import RetrievalEngine  # noqa: F401
    from bad_research.retrieval.cache import LexicalCacheBackend  # noqa: F401
    from bad_research.retrieval.rerank import (  # noqa: F401
        ClaudeCodeReranker,
        get_reranker,
    )


def test_constructing_default_engine_needs_no_local_dep(tmp_path, monkeypatch):
    blocked = {"lancedb", "pyarrow", "torch", "sentence_transformers", "FlagEmbedding"}
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name.split(".")[0] in blocked:
            raise ImportError(f"blocked: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from bad_research.retrieval.engine import RetrievalEngine
    from bad_research.retrieval.rerank import get_reranker

    class _Cfg:
        reranker = "none"
    eng = RetrievalEngine(cache_db=tmp_path / "c.db", reranker=get_reranker(_Cfg()))
    assert eng.store is None and eng.embedder is None
