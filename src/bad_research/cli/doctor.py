"""`bad doctor` — report which providers/keys are active. No network calls."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import typer

from bad_research.cli._output import console, output
from bad_research.models.output import success
from bad_research.providers import provider_status


def doctor(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
) -> None:
    """Report active providers, vault path, and model tiers. Network-free."""
    statuses = provider_status()

    # Vault root + model tiers from config (best-effort; defaults if config absent).
    try:
        from bad_research.config import BadResearchConfig

        cfg = BadResearchConfig()
        vault_root = str(cfg.vault_root)
        model_tiers = dict(cfg.model_tiers)
    except Exception:  # pragma: no cover - config always loads in practice
        vault_root = str(Path.home() / ".bad-research")
        model_tiers = {
            "triage": "claude-haiku-4-5",
            "work": "claude-sonnet-4-6",
            "heavy": "claude-opus-4-7",
        }

    data = {
        "vault_root": vault_root,
        "model_tiers": model_tiers,
        "providers": [asdict(s) for s in statuses],
        "active_count": sum(1 for s in statuses if s.active),
    }

    if json_output:
        output(success(data, vault=vault_root), json_mode=True)
        return

    console.print("[bold]bad doctor[/] — provider status\n")
    console.print(f"[dim]vault:[/] {vault_root}")
    console.print(f"[dim]models:[/] {model_tiers}\n")
    for s in statuses:
        if s.active:
            mark, color = "OK ", "green"
        elif s.requires_key and not s.key_present:
            mark, color = "key", "yellow"
        else:
            mark, color = "off", "dim"
        note = []
        if s.requires_key and not s.key_present:
            note.append("no key")
        if not s.import_present:
            # escape the [extra] brackets so rich doesn't parse them as markup tags
            note.append(rf"pip install 'bad-research\[{s.extra}]'")
        suffix = f"  [dim]({'; '.join(note)})[/]" if note else ""
        console.print(f"  [{color}]{mark}[/] {s.name:<12} [dim]{s.capability}[/]{suffix}")
    console.print(f"\n[bold]{data['active_count']}[/] provider(s) active.")
    if data["active_count"] == 0:
        console.print("[dim]Zero-key fallback (SearXNG + crawl4ai + BM25) still works.[/]")


__all__ = ["doctor"]
