"""Baselines are key-gated: no key → unavailable, never a crash."""

from __future__ import annotations

import pytest

from bad_research.calibrate.baselines import (
    BaselineUnavailable,
    GrokBaseline,
    PerplexityBaseline,
    available_baselines,
)


def test_perplexity_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("PPLX_API_KEY", raising=False)
    b = PerplexityBaseline()
    assert b.available() is False
    with pytest.raises(BaselineUnavailable):
        b.run("any query")


def test_grok_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert GrokBaseline().available() is False


def test_available_baselines_filters(monkeypatch):
    monkeypatch.delenv("PPLX_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    names = {b.name for b in available_baselines()}
    # No external keys → only the local hyperresearch baseline is even considered;
    # and it's only present if the upstream package imports.
    assert "perplexity" not in names
    assert "grok" not in names
