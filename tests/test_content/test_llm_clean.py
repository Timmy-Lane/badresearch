"""llm_clean — host-model seam, verbatim prompt, dirtiness gate (dossier 12 §6)."""

from __future__ import annotations

import importlib

from bad_research.web.content.fetch_clean import FIRECRAWL_CLEAN_PROMPT, llm_clean, looks_dirty

# The package __init__ re-exports the `fetch_clean` *function*, which shadows the
# `content.fetch_clean` submodule attribute; resolve the module explicitly (the same
# way the KR-2 WebResult bridge does) so monkeypatching the module seam works.
fc = importlib.import_module("bad_research.web.content.fetch_clean")


def test_default_host_model_is_passthrough() -> None:
    # No model wired -> deterministic pipeline must not block; returns input unchanged.
    md = "# Title\n\nClean body."
    assert llm_clean(md) == md


def test_llm_clean_dispatches_with_verbatim_prompt(monkeypatch) -> None:
    captured = {}

    def fake_host(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "CLEANED"

    monkeypatch.setattr(fc, "_host_model", fake_host)
    out = llm_clean("dirty markdown with cookie banner")
    assert out == "CLEANED"
    # the EXACT Firecrawl prompt is the system message (injection-defended)
    assert captured["system"] == FIRECRAWL_CLEAN_PROMPT
    # the untrusted page content is delimited so the model treats it as data (§6.2)
    assert "<UNTRUSTED_PAGE>" in captured["user"]
    assert "dirty markdown with cookie banner" in captured["user"]


def test_looks_dirty_detects_chrome() -> None:
    assert looks_dirty("Subscribe to our newsletter for more!")
    assert looks_dirty("We use cookies to improve your experience.")
    assert looks_dirty("© 2024 Acme Corp")
    assert not looks_dirty("# RAG\n\nA clean technical article about retrieval.")
