"""Bad Research CLI — entry-point stub (full CLI lands in later plans)."""

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
