"""Command-line interface: ``ghostcite``."""

from __future__ import annotations

from typing import Annotated

import typer

from ghostcite import __version__

app = typer.Typer(
    name="ghostcite",
    help="Detect hallucinated and wrong academic citations using live Google Scholar data.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"ghostcite {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Detect hallucinated and wrong academic citations using live Google Scholar data."""


def main() -> None:
    """Console-script entry point."""
    app()
