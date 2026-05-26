"""ActCache: stable replay keys (names not values) + hit/miss round-trip."""

from __future__ import annotations

from bad_research.browse.cache import ActCache, replay_key_for


def test_replay_key_is_deterministic() -> None:
    k1 = replay_key_for("log in then open billing", "https://x.test/app",
                         variables={"user": "alice", "pw": "secret"})
    k2 = replay_key_for("log in then open billing", "https://x.test/app",
                         variables={"user": "DIFFERENT", "pw": "ALSO-DIFFERENT"})
    # Same instruction+url+variable NAMES -> same key, even though VALUES differ.
    assert k1 == k2


def test_replay_key_changes_with_instruction() -> None:
    a = replay_key_for("open billing", "https://x.test", variables=None)
    b = replay_key_for("open settings", "https://x.test", variables=None)
    assert a != b


def test_replay_key_changes_with_variable_names() -> None:
    a = replay_key_for("go", "https://x.test", variables={"user": "x"})
    b = replay_key_for("go", "https://x.test", variables={"token": "x"})
    assert a != b


def test_cache_put_then_get_round_trips(tmp_path) -> None:
    cache = ActCache(root=tmp_path)
    key = replay_key_for("open page", "https://x.test", variables=None)
    assert cache.get(key) is None
    cache.put(key, {"steps": [{"action": "click", "index": 3}], "final_url": "https://x.test/done"})
    got = cache.get(key)
    assert got == {"steps": [{"action": "click", "index": 3}], "final_url": "https://x.test/done"}


def test_cache_get_missing_returns_none(tmp_path) -> None:
    cache = ActCache(root=tmp_path)
    assert cache.get("nonexistent-key") is None
