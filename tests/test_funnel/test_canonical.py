from __future__ import annotations

from bad_research.funnel.canonical import canonicalize_url


def test_strips_trailing_slash():
    assert canonicalize_url("https://a.com/p") == canonicalize_url("https://a.com/p/")


def test_strips_hash_fragment():
    assert canonicalize_url("https://a.com/p#section") == canonicalize_url("https://a.com/p")


def test_strips_www():
    assert canonicalize_url("https://www.a.com/p") == canonicalize_url("https://a.com/p")


def test_strips_default_port():
    assert canonicalize_url("https://a.com:443/p") == canonicalize_url("https://a.com/p")
    assert canonicalize_url("http://a.com:80/p") == canonicalize_url("http://a.com/p")


def test_strips_index_files():
    assert canonicalize_url("https://a.com/docs/index.html") == canonicalize_url("https://a.com/docs")
    assert canonicalize_url("https://a.com/index.php") == canonicalize_url("https://a.com")


def test_lowercases_scheme_and_host_keeps_path_case():
    assert canonicalize_url("HTTPS://A.COM/Path") == "https://a.com/Path"


def test_preserves_query_string():
    # query is meaningful (e.g. ?id=5); do NOT strip it
    out = canonicalize_url("https://a.com/p?id=5")
    assert "id=5" in out


def test_distinct_paths_stay_distinct():
    assert canonicalize_url("https://a.com/p") != canonicalize_url("https://a.com/q")
