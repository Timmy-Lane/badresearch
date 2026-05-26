"""The config→runner bridge: shape-only in unit mode; live behind a key."""

from __future__ import annotations

import pytest

from bad_research.calibrate.runner import default_runner


def test_default_runner_returns_callable():
    runner = default_runner(config=None)  # None → default config
    assert callable(runner)


@pytest.mark.live
def test_default_runner_runs_real_pipeline():
    runner = default_runner(config=None)
    out = runner("What is the capital of France?")
    assert out.report
    assert out.cost.total_usd() >= 0
