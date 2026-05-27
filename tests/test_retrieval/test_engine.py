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


class _CountingReranker:
    """Wraps a reranker (or scores all-0.5) and records how many docs were sent to
    the host-model reranker per round, so E6's cascade reduction is observable."""

    def __init__(self, inner=None):
        self._inner = inner
        self.docs_seen: list[int] = []     # one entry per rerank() call
        self.calls = 0

    def rerank(self, query, docs):
        self.calls += 1
        self.docs_seen.append(len(docs))
        if self._inner is not None:
            return self._inner.rerank(query, docs)
        # neutral mid-band scores
        scored = [(i, 0.5) for i in range(len(docs))]
        return scored


def test_e6_cascade_clearly_relevant_doc_skips_reranker(tmp_path):
    # A single, clearly-on-query doc: its min-max-normed BM25 proxy = 1.0 (top of a
    # 1-doc lane) → the cascade auto-KEEPS it without a host-model reranker call.
    rr = _CountingReranker()
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)
    eng.index([_note("a", "# A\n\npython async await concurrency event loop\n")])
    hits = eng.search("python async concurrency", mode="light", top_k=5)
    assert any(h.note_id == "a" for h in hits)            # clearly-relevant kept
    assert rr.calls == 0 or sum(rr.docs_seen) == 0        # reranker never paid for it


def test_e6_cascade_clearly_irrelevant_doc_dropped_without_reranker(tmp_path):
    # An off-query doc with proxy 0.0 (bottom of the normed lane) is auto-DROPPED;
    # it never reaches the host reranker and never appears in results.
    rr = _CountingReranker()
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)
    eng.index([_note("a", "# A\n\npython async await concurrency event loop\n"),
               _note("z", "# Z\n\nzebra xylophone quartz unrelated nonsense\n")])
    hits = eng.search("python async concurrency", mode="light", top_k=10)
    assert all(h.note_id != "z" for h in hits)            # irrelevant dropped
    # The cheap proxy resolved BOTH obvious docs → the reranker saw fewer than the
    # full candidate set (the whole point of the cascade).
    assert sum(rr.docs_seen) < 2


def test_e6_only_uncertain_band_reaches_the_reranker(tmp_path):
    # Build a lane where mid-band candidates exist (graded BM25 overlap) so the proxy
    # leaves an UNCERTAIN middle band that MUST still be reranked. Assert the reranker
    # is called and saw fewer docs than the full candidate count.
    rr = _CountingReranker(inner=ClaudeCodeReranker(llm=_RubricLLM()))
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)
    # All share query tokens (FTS surfaces all four) with GRADED term frequency →
    # graded min-max-normed BM25 proxy: "hi" tops out (proxy 1.0 → auto-KEPT free),
    # the middle docs land in the UNCERTAIN band (MUST be reranked), the weakest is
    # auto-DROPPED (best-case final < gate). Three bands, one live round.
    eng.index([
        _note("hi", "# hi\n\n" + "python async concurrency " * 10 + "\n"),
        _note("m1", "# m1\n\n" + "python async concurrency " * 5 + " filler word here there everywhere now then\n"),
        _note("m2", "# m2\n\n" + "python async concurrency " * 3 + " filler " * 20 + "\n"),
        _note("m3", "# m3\n\npython async concurrency " + " filler " * 40 + "\n"),
    ])
    eng.search("python async concurrency", mode="light", top_k=10)
    # Cascade fired on the LIVE path: the obvious top doc was auto-kept (free) so the
    # reranker paid for STRICTLY FEWER docs than reached the rerank decision, AND the
    # uncertain middle band DID reach the reranker (the cascade isn't all-keep/drop).
    assert eng.last_rerank_candidate_count >= 3
    assert 0 < eng.last_reranked_count < eng.last_rerank_candidate_count
    assert rr.calls > 0                                   # uncertain band was reranked
    assert all(n == eng.last_reranked_count for n in rr.docs_seen)  # only uncertain sent


def test_e6_frozen_gate_unchanged(tmp_path):
    # E6 must NOT move the frozen 0.70 relevance gate / alpha / RRF k.
    from bad_research.retrieval.constants import ALPHA, RELEVANCE_GATE, RRF_K
    assert RELEVANCE_GATE == 0.70
    assert ALPHA == 0.7
    assert RRF_K == 60


def test_e6_cascade_preserves_gate_quality(tmp_path):
    # Survivors must still clear the frozen 0.70 gate after the cascade — auto-kept
    # docs are not exempt from quality, they are just spared the reranker call.
    rr = _CountingReranker(inner=ClaudeCodeReranker(llm=_RubricLLM()))
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)
    eng.index([_note("a", "# A\n\npython async await\n"),
               _note("z", "# Z\n\ntotally unrelated zebra xylophone\n")])
    hits = eng.search("python async", mode="light", top_k=10)
    assert all(h.score >= 0.70 for h in hits)


class _OutOfRangeReranker:
    """A reranker whose raw scores can EXCEED 1.0 (like IdentityReranker's `n-i`
    pseudo-scores). The E6 cascade bound is `best = fuse(initial, 1.0, rank)` — it
    is only an upper bound (hence lossless) if the engine treats the reranker score
    as living in [0,1]. If the engine fed a raw >1 score straight into the blend,
    the cascade could auto-DROP a doc the uncertain path would then KEEP — a
    losslessness violation. This double makes that gap observable."""

    def __init__(self) -> None:
        self.docs_seen: list[int] = []

    def rerank(self, query, docs):
        self.docs_seen.append(len(docs))
        n = len(docs)
        # descending pseudo-scores well above 1.0 (n-i), exactly IdentityReranker's shape.
        return [(i, float(n - i)) for i in range(n)]


def test_e6_cascade_is_lossless_for_out_of_range_reranker_scores(tmp_path):
    # Regression for the `reranker="none"` / IdentityReranker path. The E6 cascade's
    # auto-DROP bound pins the reranker at 1.0 (`best = fuse(initial, 1.0, rank)`), so
    # the bound is only a valid UPPER bound — and the cascade only lossless — if the
    # reranker score the engine actually fuses lives in [0,1]. IdentityReranker
    # returns `n-i` pseudo-scores (> 1.0 for all but the last doc). Without an engine
    # clamp, the uncertain/kept bands would fuse those raw > 1.0 scores, producing
    # impossible final scores and (worse) letting a doc the cascade auto-DROPPED at
    # the bound have survived in the OLD all-rerank path — a real losslessness break.
    # The fix: clamp the reranker score to [0,1] at the single fusion site, which is
    # a no-op for the host (already clamps) and BGE (sigmoid) rerankers, and makes the
    # bound EXACT for every reranker. Then every survivor's score is a valid [0,1]
    # blend (<= the source-type ceiling) and clears the frozen 0.70 gate.
    rr = _OutOfRangeReranker()
    eng = RetrievalEngine(cache_db=tmp_path / "cache.db", reranker=rr)
    # 6 graded docs → the proxy leaves >=2 in the uncertain band, so the top uncertain
    # doc would receive an n-i pseudo-score of 2.0 (the leak vector pre-clamp).
    eng.index([
        _note("d0", "# d0\n\n" + "python async concurrency " * 12 + "\n"),
        _note("d1", "# d1\n\n" + "python async concurrency " * 8 + " filler " * 4 + "\n"),
        _note("d2", "# d2\n\n" + "python async concurrency " * 5 + " filler " * 15 + "\n"),
        _note("d3", "# d3\n\n" + "python async concurrency " * 3 + " filler " * 30 + "\n"),
        _note("d4", "# d4\n\n" + "python async concurrency " * 2 + " filler " * 45 + "\n"),
        _note("d5", "# d5\n\npython async concurrency " + " filler " * 70 + "\n"),
    ])
    hits = eng.search("python async concurrency", mode="light", top_k=10)
    # No survivor may carry an impossible score: a valid [0,1] blend scaled by the
    # source-type weight maxes at DEFAULT_SOURCE_TYPE_WEIGHT (1.0 for "docs"). A score
    # > 1.0 here is direct proof a raw n-i (> 1.0) reranker score leaked into the blend.
    assert all(h.score <= 1.0 + 1e-9 for h in hits), \
        f"raw out-of-range reranker score leaked into the fused result: {[(h.note_id, h.score) for h in hits]}"
    # And every survivor still clears the frozen gate.
    assert all(h.score >= 0.70 for h in hits)


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
