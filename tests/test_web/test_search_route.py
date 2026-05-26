"""Intent detection + vertical routing (seed-only verticals, always-on grounding)."""

from __future__ import annotations

from bad_research.web.search.route import VERTICAL_ROUTES, detect_intent, route_query


def test_routes_table_matches_dossier():
    assert VERTICAL_ROUTES["academic"] == ["openalex", "arxiv", "semantic_scholar", "crossref"]
    assert VERTICAL_ROUTES["medical"] == ["europe_pmc", "pubmed", "openalex"]
    assert VERTICAL_ROUTES["technical"] == ["arxiv", "openalex", "ddgs"]
    assert VERTICAL_ROUTES["general"] == []


def test_detect_intent_regex_fallback():
    assert detect_intent("systematic review of et al. arxiv papers") == "academic"
    assert detect_intent("clinical trial drug dosage mg/kg in vivo") == "medical"
    assert detect_intent("how to implement an API library stack trace") == "technical"
    assert detect_intent("best pizza in town") == "general"


def test_route_query_baseline_websearch_on_every_query():
    tasks = route_query("q", ["a", "b", "c"], "general")
    ws = [(q, p) for (q, p) in tasks if p == "websearch"]
    assert {q for q, _ in ws} == {"a", "b", "c"}     # WebSearch fans every query
    # always-on Wikipedia grounding on 1 seed
    assert ("a", "wikipedia") in tasks
    assert sum(1 for _, p in tasks if p == "wikipedia") == 1


def test_route_query_academic_verticals_seed_only():
    tasks = route_query("q", ["a", "b", "c", "d"], "academic")
    # verticals fan ONLY on the first <=2 seed queries
    oalex = [(q, p) for (q, p) in tasks if p == "openalex"]
    assert {q for q, _ in oalex} == {"a", "b"}        # seeds only, never c/d
    assert ("a", "arxiv") in tasks
    assert ("a", "crossref") in tasks
    assert ("a", "semantic_scholar") in tasks


def test_route_query_medical_intent():
    tasks = route_query("q", ["a", "b"], "medical")
    provs = {p for _, p in tasks}
    assert "europe_pmc" in provs and "pubmed" in provs
    assert "arxiv" not in provs                       # not in the medical route
