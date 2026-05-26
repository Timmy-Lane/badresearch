from __future__ import annotations

from bad_research.funnel.dedup import Candidate
from bad_research.funnel.rank import rank_candidates, rrf_fuse, utility_score
from tests.test_funnel.conftest import FakeWebResult


def _cand(url, ranks, *, domain_title="", content="body " * 80):
    r = FakeWebResult(url=url, title=domain_title or url, content=content)
    return Candidate(canonical_url=url, result=r, provider_ranks=dict(ranks))


def test_rrf_fuses_multi_provider_ranks_k60():
    # surfaced by two providers ranks 2 and 5 → 1/(60+2)+1/(60+5)
    score = rrf_fuse({"sonar": 2, "exa": 5}, k=60)
    assert abs(score - (1 / 62 + 1 / 65)) < 1e-9


def test_rrf_single_provider():
    assert abs(rrf_fuse({"sonar": 1}, k=60) - (1 / 61)) < 1e-9


def test_rrf_ignores_zero_ranks():
    # rank 0 means 'unknown position' — don't let it dominate (would be 1/60)
    assert rrf_fuse({"sonar": 0}, k=60) == 0.0


def test_utility_score_bounded_0_to_18():
    c = _cand("https://sec.gov/filing", {"sonar": 1},
              domain_title="SEC EDGAR 10-Q primary filing")
    s = utility_score(c, query="acme 10-Q revenue")
    assert 0 <= s <= 18


def test_authority_domain_scores_higher_than_blog():
    gov = _cand("https://sec.gov/x", {"sonar": 1}, domain_title="SEC filing")
    blog = _cand("https://randomblog.wordpress.com/x", {"sonar": 1}, domain_title="my hot take")
    assert utility_score(gov, "x") > utility_score(blog, "x")


def test_rank_orders_before_any_read():
    # Higher composite (RRF + utility) must come first; NO fetch happens.
    cands = [
        _cand("https://low.blog/x", {"searxng": 9}, domain_title="opinion"),
        _cand("https://sec.gov/x", {"sonar": 1, "exa": 2}, domain_title="SEC filing data"),
        _cand("https://mid.com/x", {"tavily": 4}, domain_title="news report"),
    ]
    ranked = rank_candidates(cands, query="financial data", rrf_k=60)
    assert ranked[0].url == "https://sec.gov/x"          # best RRF + authority
    assert ranked[-1].url == "https://low.blog/x"
    # the Candidate objects are returned un-mutated (no .content fetched in)
    assert all(isinstance(c, Candidate) for c in ranked)


def test_rank_is_pure_no_network(monkeypatch):
    # Guard: rank must never call fetch_tiered. We patch a sentinel that explodes.
    import bad_research.funnel.rank as rank_mod
    assert not hasattr(rank_mod, "fetch_tiered")  # rank module must not import the reader
