"""web/content/__init__ must NOT shadow the fetch_clean submodule (FIX 3).

Re-exporting the `fetch_clean` FUNCTION shadowed the `content.fetch_clean` SUBMODULE
attribute, so `from bad_research.web.content import fetch_clean; fetch_clean.cache_get(...)`
silently grabbed the function -> AttributeError — a footgun for KR-4/5/6. The function
is reachable via the bridge's importlib.import_module(...).fetch_clean path (unaffected).
"""

from __future__ import annotations


def test_fetch_clean_attr_is_the_module() -> None:
    from bad_research.web.content import fetch_clean

    # It must be the MODULE (has module-level seams like cache_get / classify), not the
    # function (which would AttributeError on these).
    assert hasattr(fetch_clean, "cache_get")
    assert hasattr(fetch_clean, "cache_put")
    assert hasattr(fetch_clean, "needs_js")
    # the function itself still lives inside the module
    assert callable(fetch_clean.fetch_clean)


def test_bridge_still_reaches_the_function() -> None:
    # The production WebResult bridge resolves the function via importlib; that path is
    # unaffected by dropping the bare re-export.
    import importlib

    mod = importlib.import_module("bad_research.web.content.fetch_clean")
    assert callable(mod.fetch_clean)
