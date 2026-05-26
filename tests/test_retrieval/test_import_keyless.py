"""The keyless default must import + construct with NO torch / lancedb /
sentence-transformers installed.

We run the import in a SUBPROCESS that blocks every [local] dependency at the
import hook. A subprocess (rather than importlib.reload) guarantees the check
cannot pollute this process's module registry — reloading bad_research.retrieval.*
in-process rebinds class objects and breaks isinstance in sibling tests."""
import subprocess
import sys
import textwrap


def _run_blocked(body: str) -> subprocess.CompletedProcess:
    """Execute `body` in a fresh interpreter with all [local] deps import-blocked."""
    prog = textwrap.dedent(
        """
        import builtins
        _blocked = {"lancedb", "pyarrow", "torch", "sentence_transformers", "FlagEmbedding"}
        _real = builtins.__import__
        def _guard(name, *a, **k):
            if name.split(".")[0] in _blocked:
                raise ImportError("blocked in keyless test: " + name)
            return _real(name, *a, **k)
        builtins.__import__ = _guard
        """
    ) + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True)


def test_retrieval_imports_without_local_deps():
    res = _run_blocked(
        """
        from bad_research.retrieval import RetrievalEngine
        from bad_research.retrieval.rerank import ClaudeCodeReranker, get_reranker
        from bad_research.retrieval.cache import LexicalCacheBackend
        import bad_research.retrieval.engine  # noqa: F401
        import bad_research.retrieval.store  # importing the module is OK; constructing needs [local]
        print("OK")
        """
    )
    assert res.returncode == 0, f"keyless import failed:\nSTDOUT={res.stdout}\nSTDERR={res.stderr}"
    assert "OK" in res.stdout


def test_constructing_default_engine_needs_no_local_dep(tmp_path):
    res = _run_blocked(
        f"""
        from bad_research.retrieval.engine import RetrievalEngine
        from bad_research.retrieval.rerank import get_reranker

        class _Cfg:
            reranker = "none"

        eng = RetrievalEngine(cache_db=r"{tmp_path / 'c.db'}", reranker=get_reranker(_Cfg()))
        assert eng.store is None and eng.embedder is None
        print("OK")
        """
    )
    assert res.returncode == 0, f"keyless construct failed:\nSTDOUT={res.stdout}\nSTDERR={res.stderr}"
    assert "OK" in res.stdout
