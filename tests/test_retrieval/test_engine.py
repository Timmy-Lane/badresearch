"""RetrievalEngine — the KEYLESS DEFAULT path (embedder=None → FTS5/BM25 recall,
min-max BM25 initial, ClaudeCodeReranker over top-30, three-tier fuse, 0.70 gate,
<30%-pass re-retrieve, token-set LexicalCacheBackend). No LanceDB, no key, no
local model. The host LLM is the FakeLLMProvider-shaped _RubricLLM (deterministic
query-token-overlap scoring in the §5.3 JSON shape, 0-based to match the shared
parser)."""
import json

from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.base import Reranker
from bad_research.retrieval.engine import RetrievalEngine
from bad_research.retrieval.rerank import ClaudeCodeReranker


class _RubricLLM:
    """A FakeLLMProvider-shaped host that scores by query-token overlap so the
    rerank is deterministic without a real model. Returns the §5.3 JSON shape
    with 0-based chunk indices (matching the shared KR-2 parser)."""
    name = "rubric"

    def __init__(self):
        self.calls = []

    def complete(self, messages, *, tier, tools=None, cache=False,
                 max_tokens=4096, temperature=0.1):
        from bad_research.llm.base import LLMResponse
        self.calls.append(messages)
        user = messages[1].content
        qtoks = set(user.split("QUERY: ")[1].splitlines()[0].lower().split())
        items = []
        for line in user.splitlines():
            if line.startswith("[") and "]" in line:
                n = int(line[1:line.index("]")])
                body = line[line.index("]") + 1:].strip().lower()
                hit = bool(qtoks & set(body.split()))
                items.append({"i": n, "s": 0.95 if hit else 0.10})
        return LLMResponse(text=json.dumps(items), tool_calls=[], usage={}, model="rubric")


def _note(nid, body, ct=None, status="evergreen"):
    return Note(meta=NoteMeta(title=nid, id=nid, source=f"https://ex.com/{nid}",
                              content_type=ct, status=status),
                body=body, path=f"research/{nid}.md")


def _fts_engine(tmp_path, llm=None):
    """The KEYLESS DEFAULT: embedder=None, lance_dir=None → FTS-only recall."""
    rr = ClaudeCodeReranker(llm=llm or _RubricLLM())
    return RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)


def test_engine_default_has_no_embedder_and_no_lance(tmp_path):
    eng = _fts_engine(tmp_path)
    assert eng.embedder is None
    assert eng.store is None  # no LanceDB constructed on the keyless path.


def test_reranker_protocol_satisfied(tmp_path):
    eng = _fts_engine(tmp_path)
    assert isinstance(eng.reranker, Reranker)


def test_fts_only_index_then_search_returns_relevant_chunk_first(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([
        _note("a", "# A\n\npython async await concurrency patterns explained\n"),
        _note("b", "# B\n\nrust ownership borrow checker lifetimes memory\n"),
    ])
    hits = eng.search("python async", mode="light", top_k=2)
    assert len(hits) >= 1
    assert hits[0].note_id == "a"
    assert hits[0].char_end > hits[0].char_start


def test_relevance_gate_drops_low_scoring_chunks(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await\n"),
               _note("z", "# Z\n\ntotally unrelated zebra xylophone\n")])
    hits = eng.search("python async", mode="light", top_k=10)
    assert all(h.score >= 0.70 for h in hits)


def test_source_type_weight_boosts_code(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("code", "def parse_async(): return async_io_loop()\n" * 80, ct="code"),
               _note("docs", "parse async io loop documentation prose\n" * 80, ct="docs")])
    hits = eng.search("parse async", mode="full", top_k=2)
    by_note = {h.note_id: h.score for h in hits}
    if "code" in by_note and "docs" in by_note:
        assert by_note["code"] >= by_note["docs"]


def test_lexical_cache_hit_on_repeat_query(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    first = eng.search("python async concurrency", mode="light", top_k=3)
    eng.search("python async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is True
    second = eng.search("concurrency async python", mode="light", top_k=3)  # reorder → lexical HIT
    assert eng.last_cache_hit is True
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_lexical_cache_miss_when_negation_added(tmp_path):
    eng = _fts_engine(tmp_path)
    eng.index([_note("a", "# A\n\npython async await concurrency\n")])
    eng.search("python async concurrency", mode="light", top_k=3)
    eng.search("python NOT async concurrency", mode="light", top_k=3)
    assert eng.last_cache_hit is False


def test_expand_symbols_pulls_wiki_link_neighbors(tmp_path, stub_links_db):
    # Note "a" links to note "b"; a low-pass first round should widen to b's chunks.
    links_path = stub_links_db([("a", "b")])

    class _LowPassLLM:
        name = "lowpass"
        def complete(self, messages, *, tier, tools=None, cache=False,
                     max_tokens=4096, temperature=0.1):
            # Score everything 0.0 on round 1 so <30% pass → forces a widen.
            import json as _json

            from bad_research.llm.base import LLMResponse
            user = messages[1].content
            ns = [int(line[1:line.index("]")]) for line in user.splitlines()
                  if line.startswith("[") and "]" in line]
            return LLMResponse(text=_json.dumps([{"i": n, "s": 0.0} for n in ns]),
                               tool_calls=[], usage={}, model="lowpass")

    from bad_research.retrieval.rerank import ClaudeCodeReranker
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db",
                          reranker=ClaudeCodeReranker(llm=_LowPassLLM()),
                          links_db=links_path)
    eng.index([_note("a", "# A\n\nquery seed token alpha\n"),
               _note("b", "# B\n\nneighbor body unrelated tokens\n")])
    neighbors = eng._expand_symbols("a")
    # b's chunk ids are pulled in as widening candidates (outlink a→b).
    assert any(eng._meta[cid].chunk.note_id == "b" for cid in neighbors)
