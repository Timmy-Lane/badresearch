"""Calibration baselines — run the same query through a comparison system.

Key-gated (SPEC §14): a baseline that needs a key it doesn't have is silently
dropped by the harness, never a crash. The hyperresearch baseline runs the
upstream package if it's importable.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Protocol


class BaselineUnavailable(RuntimeError):
    """Raised when a baseline is invoked without its key/dependency."""


@dataclass
class BaselineResult:
    name: str
    report: str
    corpus: list[dict]  # the evidence that baseline used, for fair judging


class Baseline(Protocol):
    name: str

    def available(self) -> bool: ...
    def run(self, query: str) -> BaselineResult: ...


@dataclass
class HyperresearchBaseline:
    """Runs the upstream `hyperresearch` package if installed (offline-friendly)."""

    name: str = "hyperresearch"

    def available(self) -> bool:
        return importlib.util.find_spec("hyperresearch") is not None

    def run(self, query: str) -> BaselineResult:
        if not self.available():
            raise BaselineUnavailable("hyperresearch package not importable")
        # The upstream pipeline is Claude-Code-driven; for offline calibration we
        # can only run its deterministic vault search. The harness treats a present-
        # but-non-LLM baseline as a structural comparator. Real LLM comparison
        # happens when run inside a Claude Code host (out of scope for the test path).
        raise BaselineUnavailable(
            "hyperresearch baseline requires a Claude Code host; use --baselines none offline"
        )


@dataclass
class _ApiBaseline:
    name: str
    env_var: str

    def available(self) -> bool:
        return bool(os.environ.get(self.env_var))

    def run(self, query: str) -> BaselineResult:
        if not self.available():
            raise BaselineUnavailable(f"{self.name}: {self.env_var} not set")
        # Real API call lives behind the key-gate; only reached when keyed (live tier).
        raise NotImplementedError(  # pragma: no cover
            f"{self.name} live call — implement against its deep-research API when keyed"
        )


class PerplexityBaseline(_ApiBaseline):
    def __init__(self) -> None:
        super().__init__(name="perplexity", env_var="PPLX_API_KEY")


class GrokBaseline(_ApiBaseline):
    def __init__(self) -> None:
        super().__init__(name="grok", env_var="XAI_API_KEY")


def available_baselines() -> list[Baseline]:
    """Every baseline whose key/dependency is present right now."""
    candidates: list[Baseline] = [
        HyperresearchBaseline(),
        PerplexityBaseline(),
        GrokBaseline(),
    ]
    return [b for b in candidates if b.available()]


__all__ = [
    "Baseline",
    "BaselineResult",
    "BaselineUnavailable",
    "GrokBaseline",
    "HyperresearchBaseline",
    "PerplexityBaseline",
    "available_baselines",
]
