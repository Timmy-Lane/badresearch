"""Bad Research top-level configuration.

Distinct from hyperresearch's per-vault `core/config.py:VaultConfig` (kept verbatim
in the fork). This holds the cross-cutting knobs: provider keys (read lazily from
env), the model-tier map, budget caps, and thresholds. Precedence: env > TOML > default.

Default TOML location: ~/.config/bad-research/config.toml (XDG user config).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def default_config_path() -> Path:
    """The user-side config file location (~/.config/bad-research/config.toml)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "bad-research" / "config.toml"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BadResearchConfig:
    vault_root: Path = field(default_factory=lambda: Path.home() / ".bad-research")
    model_tiers: dict = field(
        default_factory=lambda: {
            "triage": "claude-haiku-4-5",
            "work": "claude-sonnet-4-6",
            "heavy": "claude-opus-4-7",
        }
    )
    embed_model: str = "embed-english-v3.0"  # Cohere
    rerank_model: str = "rerank-v3.5"      # Cohere; "bge-reranker-v2-m3" offline
    budget_usd: float | None = None        # None = uncapped
    cheap: bool = False                    # demote heavy->work
    # Retrieval knobs (Plan 02; default to the frozen constants). The engine
    # reads these (not the constants module directly) so config overrides apply.
    retrieval_alpha: float = 0.7
    relevance_gate: float = 0.70
    semantic_cache_threshold: float = 0.92
    top_k_retrieve: int = 30
    # provider keys read from env / ~/.config/bad-research/config.toml at call sites

    @classmethod
    def load(cls, config_path: Path | None = None) -> BadResearchConfig:
        """Build a config with precedence env > TOML > dataclass default."""
        if config_path is None:
            config_path = default_config_path()

        cfg = cls()

        # --- TOML layer (overrides defaults) ---
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            section = data.get("bad-research", {})
            if "vault_root" in section:
                cfg.vault_root = Path(section["vault_root"])
            if "model_tiers" in section:
                cfg.model_tiers = dict(section["model_tiers"])
            if "embed_model" in section:
                cfg.embed_model = section["embed_model"]
            if "rerank_model" in section:
                cfg.rerank_model = section["rerank_model"]
            if "budget_usd" in section:
                cfg.budget_usd = float(section["budget_usd"])
            if "cheap" in section:
                cfg.cheap = bool(section["cheap"])

        # --- env layer (overrides TOML) ---
        if (v := os.environ.get("BAD_RESEARCH_VAULT_ROOT")) is not None:
            cfg.vault_root = Path(v)
        if (v := os.environ.get("BAD_RESEARCH_EMBED_MODEL")) is not None:
            cfg.embed_model = v
        if (v := os.environ.get("BAD_RESEARCH_RERANK_MODEL")) is not None:
            cfg.rerank_model = v
        if (v := os.environ.get("BAD_RESEARCH_BUDGET_USD")) is not None:
            cfg.budget_usd = float(v)
        if (v := os.environ.get("BAD_RESEARCH_CHEAP")) is not None:
            cfg.cheap = _parse_bool(v)

        return cfg
