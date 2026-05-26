from __future__ import annotations

import time

from bad_research.funnel.fanout import fan_out, plan_queries
from tests.test_funnel.conftest import FakeProvider


def test_plan_queries_caps_at_m():
    qs = plan_queries("impact of AI on jobs", m_queries=12, k_per_query=5)
    assert len(qs) <= 12
    assert all(q.max_results == 5 for q in qs)
    # the verbatim user query is always present as the first seed
    assert qs[0].query == "impact of AI on jobs"


def test_plan_queries_distinct():
    qs = plan_queries("quantum computing error correction", m_queries=8, k_per_query=10)
    texts = [q.query for q in qs]
    assert len(texts) == len(set(texts))  # no duplicate seeds


async def test_fan_out_merges_provider_lists():
    providers = [FakeProvider("sonar"), FakeProvider("exa"), FakeProvider("searxng")]
    queries = plan_queries("topic", m_queries=2, k_per_query=4)
    hits = await fan_out(queries, providers)
    # 2 queries × 3 providers × 4 results = 24 raw hits (distinct URLs per provider)
    assert len(hits) == 24
    domains = {h.serp_provider for h in hits}
    assert domains == {"sonar", "exa", "searxng"}


async def test_fan_out_runs_providers_in_parallel():
    # Each provider sleeps 0.2s. Serial would be 2 queries × 3 providers × 0.2 = 1.2s.
    # Parallel must be ~0.2s (one round). Assert well under the serial floor.
    providers = [FakeProvider(n, latency=0.2) for n in ("sonar", "exa", "searxng")]
    queries = plan_queries("topic", m_queries=2, k_per_query=2)
    start = time.perf_counter()
    await fan_out(queries, providers)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.6, f"fan-out not parallel: took {elapsed:.2f}s (serial would be 1.2s)"


async def test_fan_out_survives_one_provider_failure():
    class Boom(FakeProvider):
        async def search_ex(self, q):
            raise RuntimeError("provider down")

    providers = [FakeProvider("sonar"), Boom("exa")]
    queries = plan_queries("topic", m_queries=1, k_per_query=3)
    hits = await fan_out(queries, providers)
    # sonar's 3 results survive; exa's failure is swallowed (degrade, not abort)
    assert len(hits) == 3
    assert all(h.serp_provider == "sonar" for h in hits)


async def test_fan_out_empty_providers_returns_empty():
    hits = await fan_out(plan_queries("topic", m_queries=2, k_per_query=2), [])
    assert hits == []
