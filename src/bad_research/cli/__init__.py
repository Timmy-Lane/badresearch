"""Bad Research CLI — the `bad`/`badr` Typer app.

The single-file `cli.py` was promoted to a package so the research-pipeline
subcommands (`cli/research.py`) and the asset-saver (`cli/fetch.py`, imported
lazily by `core/fetcher.py`) live alongside the app without circular imports.
"""

from __future__ import annotations

import typer

from bad_research import __version__


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bad-research v{__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="bad",
    help="michael jackson bad — deep-research agent.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version",
    ),
) -> None:
    pass


# ── install command (Task 13) ────────────────────────────────────────────────
from bad_research.cli.install import install as _install_cmd

app.command("install")(_install_cmd)

# ── research-pipeline subcommands (Task 12) ──────────────────────────────────
from bad_research.cli.research import (
    funnel_gather_cmd,
    retrieve_cmd,
    route_cmd,
    uncited_gate_cmd,
    verify_citations_cmd,
)

app.command("route")(route_cmd)
app.command("funnel-gather")(funnel_gather_cmd)
app.command("retrieve")(retrieve_cmd)
app.command("verify-citations")(verify_citations_cmd)
app.command("uncited-gate")(uncited_gate_cmd)

# ── doctor + calibrate commands (Plan 09) ────────────────────────────────────
from bad_research.cli.calibrate import calibrate as _calibrate_cmd
from bad_research.cli.doctor import doctor as _doctor_cmd

app.command("doctor")(_doctor_cmd)
app.command("calibrate")(_calibrate_cmd)

__all__ = ["app"]
