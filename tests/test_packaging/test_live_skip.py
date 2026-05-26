"""Proves the `live` auto-skip hook works: this body must never run in default CI."""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_live_is_skipped_by_default():
    # If this runs without BAD_RUN_LIVE=1 + a key, the skip hook is broken.
    raise AssertionError("live test ran without BAD_RUN_LIVE=1 — skip hook failed")
