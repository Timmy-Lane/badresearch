"""Cross-plan invariant (KEYLESS_REBUILD_PLAN_OUTLINE §1): zero third-party key,
no mandatory local model in the retrieval surface.

The invariant is about IMPORTS and PROVIDERS, not prose: a docstring saying
"Cohere is removed" is fine; an `import cohere` is not. So the scan targets
import statements (matching the brief's keyless grep-guard), and separately
asserts the default engine constructs with no env key and no [local] dep."""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "bad_research"

# Banned keyed/paid backends — no import of these may survive in core retrieval/embed.
_BANNED = ("cohere", "tavily", "exa", "firecrawl", "browserbase", "agentql",
           "browser_use", "stagehand", "jina", "voyage")

_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+\S*(?:" + "|".join(_BANNED) + r")",
    re.MULTILINE,
)


def test_no_keyed_or_api_embedder_import_in_retrieval_or_embed():
    for pkg in ("retrieval", "embed"):
        for py in (SRC / pkg).rglob("*.py"):
            text = py.read_text()
            hit = _IMPORT_RE.search(text)
            assert hit is None, f"{py}: banned keyed import survives → {hit.group(0)!r}"


def test_default_engine_constructs_with_no_local_dep_and_no_env_key(tmp_path, monkeypatch):
    # No ANTHROPIC_API_KEY, no COHERE_API_KEY — the FTS-default + none-reranker
    # engine must still construct (the host model is only called at rerank time,
    # and "none" avoids even that).
    for k in ("ANTHROPIC_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    from bad_research.retrieval.engine import RetrievalEngine
    from bad_research.retrieval.rerank import get_reranker

    class _Cfg:
        reranker = "none"
    eng = RetrievalEngine(cache_db=tmp_path / "c.db", reranker=get_reranker(_Cfg()))
    assert eng.embedder is None and eng.store is None
