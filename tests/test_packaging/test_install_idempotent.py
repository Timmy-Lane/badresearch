"""`bad install` idempotency: run twice → identical disk state, no second-run mutations.

Holds Plan 08's real `install_global_hooks` to the contract. If this ever fails
against the real installer, that is a Plan 08 idempotency bug to fix there — do
not weaken the test.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bad_research.cli.install import install_global_hooks


def _tree_digest(root: Path) -> str:
    """Order-stable digest of every file path + content under root."""
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def test_install_global_twice_is_idempotent(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()

    first = install_global_hooks(home, hpr_path="bad")
    digest_after_first = _tree_digest(home / ".claude")
    assert first, "first install should report at least one action"

    second = install_global_hooks(home, hpr_path="bad")
    digest_after_second = _tree_digest(home / ".claude")

    # Contract 1: second run mutates nothing on disk.
    assert digest_after_first == digest_after_second
    # Contract 2: second run reports an empty action list (no-op).
    assert second == []


def test_install_creates_skill_dir(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    install_global_hooks(home, hpr_path="bad")
    assert (home / ".claude" / "skills" / "bad-research").is_dir()
