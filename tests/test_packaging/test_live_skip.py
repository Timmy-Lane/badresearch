"""Proves the `live` auto-skip hook works: this body must never run in default CI."""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_live_is_skipped_by_default():
    # If this runs without BAD_RUN_LIVE=1 + a key, the skip hook is broken.
    raise AssertionError("live test ran without BAD_RUN_LIVE=1 — skip hook failed")


def test_conftest_live_keys_are_keyless():
    """Only ANTHROPIC_API_KEY marks a live run; no deleted-provider keys remain."""
    import tests.conftest as ct

    assert ct._LIVE_KEYS == ("ANTHROPIC_API_KEY",)
