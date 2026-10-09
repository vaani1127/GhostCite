"""Command-line interface: ``ghostcite``.

Exit codes: 0 clean, 1 the ``--fail-on`` threshold was reached, 2 usage or input error,
3 SerpApi or network error (including not enough credits).
"""

from __future__ import annotations

import ipaddress
import os
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from ghostcite import __version__
from ghostcite.config import INGEST, SEARCH, WEB
from ghostcite.document import Document, load_document, load_text
from ghostcite.errors import ExitCode, GhostCiteError, InputError
from ghostcite.logs import configure_logging
from ghostcite.models import Report, RunMode, Verdict
from ghostcite.pipeline import Progress as PipelineProgress
from ghostcite.report import OutputFormat, render
from ghostcite.report.summary import VERDICT_LABELS, cited_title, problem_count, score_text
from ghostcite.samples import SAMPLE_BIB, sample_path
from ghostcite.search.cache import SqliteCache
from ghostcite.service import RunOptions, run_check
from ghostcite.settings import load_settings

app = typer.Typer(
    name="ghostcite",
    help="Detect hallucinated and wrong academic citations using live Google Scholar data.",
    no_args_is_help=True,
    add_completion=False,
    # Tracebacks must never print local variables, which could include the API key.
    pretty_exceptions_show_locals=False,
)
cache_app = typer.Typer(help="Inspect or clear the local search cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

_VERDICT_STYLES = {
    Verdict.VERIFIED: "green",
    Verdict.METADATA_MISMATCH: "yellow",
    Verdict.NOT_FOUND: "bold red",
    Verdict.UNPARSEABLE: "magenta",
    Verdict.SKIPPED_BUDGET: "dim",
}
_MAX_TITLE_CHARS = 60
CONTAINER_ENV = "GHOSTCITE_IN_CONTAINER"
"""Set to 1 by the Docker image, where the web UI must bind 0.0.0.0 to be published."""


class Format(StrEnum):
    """Output formats of ``ghostcite check``."""

    TABLE = "table"
    JSON = "json"
    MD = "md"
    HTML = "html"
    SARIF = "sarif"


def _stderr() -> Console:
    return Console(stderr=True)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"ghostcite {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
    verbose: Annotated[
        int, typer.Option("--verbose", "-v", count=True, help="More logging (-v info, -vv debug).")
    ] = 0,
) -> None:
    """Detect hallucinated and wrong academic citations using live Google Scholar data."""
    configure_logging(("WARNING", "INFO", "DEBUG")[min(verbose, 2)])


def _read_input(file: Path | None, demo: bool) -> tuple[Document, str]:
    """Load the document and return it with the path SARIF results should point at."""
    if file is None:
        if not demo:
            raise InputError("Give a file to check, or use --demo to check the bundled sample.")
        path = sample_path(SAMPLE_BIB)
        return load_document(path.read_bytes(), path.name), path.name
    if str(file) == "-":
        return load_text(sys.stdin.read()), "stdin"
    if not file.is_file():
        raise InputError(f"File not found: {file}")
    if file.stat().st_size > INGEST.max_input_bytes:
        raise InputError(
            f"{file.name} is larger than the {INGEST.max_input_bytes // 2**20} MiB limit."
        )
    return load_document(file.read_bytes(), file.name), file.as_posix()


def _resolve_format(output_format: Format, output: Path | None) -> OutputFormat | None:
    """The file format to write, or ``None`` for the terminal table."""
    if output_format is not Format.TABLE:
        return OutputFormat(output_format.value)
    if output is None:
        return None
    suffix = output.suffix.lower().lstrip(".")
    aliases = {"markdown": "md", "htm": "html"}
    try:
        return OutputFormat(aliases.get(suffix, suffix))
    except ValueError:
        raise InputError(
            f"Cannot tell the format from '{output.name}'; pass --format json|md|html|sarif."
        ) from None


def _mode(offline: bool, demo: bool) -> RunMode:
    if offline and demo:
        raise InputError("--offline and --demo cannot be combined.")
    if demo:
        return RunMode.DEMO
    return RunMode.OFFLINE if offline else RunMode.LIVE


def _print_table(report: Report, console: Console) -> None:
    table = Table(title=f"GhostCite: {report.source_name}", show_lines=False, expand=True)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Verdict", no_wrap=True)
    table.add_column("Conf.", justify="right", no_wrap=True)
    table.add_column("Cited title", ratio=2)
    table.add_column("Reason", ratio=3)
    for result in report.results:
        title = cited_title(result)
        if len(title) > _MAX_TITLE_CHARS:
            title = title[: _MAX_TITLE_CHARS - 3] + "..."
        table.add_row(
            str(result.reference.index),
            f"[{_VERDICT_STYLES[result.verdict]}]{VERDICT_LABELS[result.verdict]}[/]",
            f"{result.confidence:.2f}",
            title,
            result.reason,
        )
    console.print(table)
    _print_summary(report, console)


def _print_summary(report: Report, console: Console) -> None:
    summary = report.summary
    counts = ", ".join(
        f"[{_VERDICT_STYLES[v]}]{VERDICT_LABELS[v]} {summary.counts.get(v, 0)}[/]" for v in Verdict
    )
    console.print(
        f"Integrity score [bold]{score_text(report)}[/] | {counts} | "
        f"{summary.credits_used} searches used, {summary.cache_hits} from cache "
        f"({report.mode.value} mode)"
    )
    for warning in report.warnings:
        console.print(f"[yellow]warning:[/] {warning}")


def _run_with_progress(document: Document, options: RunOptions, quiet: bool) -> Report:
    settings = load_settings()
    stderr = _stderr()
    if quiet or not stderr.is_terminal:
        return run_check(document, settings, options)
    columns = (
        TextColumn("Checking references"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )
    with Progress(*columns, console=stderr, transient=True) as bar:
        task = bar.add_task("check", total=len(document.references))

        def advance(event: PipelineProgress) -> None:
            bar.update(task, completed=event.done, total=event.total)

        return run_check(document, settings, options, progress=advance)


@app.command()
def check(
    file: Annotated[
        Path | None,
        typer.Argument(
            help="PDF, .bib or text file. Use '-' to read text from stdin. Optional with --demo."
        ),
    ] = None,
    output_format: Annotated[
        Format, typer.Option("--format", "-f", help="Output format.", case_sensitive=False)
    ] = Format.TABLE,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the report to this file.")
    ] = None,
    max_searches: Annotated[
        int, typer.Option(min=0, help="Hard cap on live SerpApi searches for this run.")
    ] = SEARCH.default_max_searches,
    offline: Annotated[
        bool, typer.Option(help="Use only cached results; never call SerpApi.")
    ] = False,
    demo: Annotated[
        bool, typer.Option(help="Use the bundled demo data; no API key needed.")
    ] = False,
    fail_on: Annotated[
        int | None,
        typer.Option(
            min=1, help="Exit with code 1 if at least N references are not found or mismatched."
        ),
    ] = None,
    sarif_uri: Annotated[
        str | None, typer.Option(help="Path recorded in SARIF results (default: FILE as given).")
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="No progress bar or summary.")
    ] = False,
) -> None:
    """Check every reference in FILE against Google Scholar."""
    try:
        mode = _mode(offline, demo)
        target = _resolve_format(output_format, output)
        document, artifact = _read_input(file, demo)
        report = _run_with_progress(
            document, RunOptions(mode=mode, max_searches=max_searches), quiet
        )
    except GhostCiteError as exc:
        _stderr().print(f"[bold red]error:[/] {exc.message}", highlight=False)
        raise typer.Exit(int(exc.exit_code)) from None

    if target is None:
        _print_table(report, Console())
    else:
        text = render(report, target, artifact_uri=sarif_uri or artifact)
        if output is None:
            sys.stdout.write(text)
        else:
            output.write_text(text, encoding="utf-8", newline="\n")
            if not quiet:
                _print_summary(report, _stderr())
                _stderr().print(f"Report written to {output}", highlight=False)

    if fail_on is not None and problem_count(report) >= fail_on:
        raise typer.Exit(int(ExitCode.CITATIONS_FAILED))


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


@app.command()
def web(
    host: Annotated[
        str, typer.Option(help="Interface to listen on. Keep the default unless you know why.")
    ] = WEB.default_host,
    port: Annotated[
        int, typer.Option(min=1, max=65535, help="Port to listen on.")
    ] = WEB.default_port,
) -> None:
    """Start the local web UI (http://127.0.0.1:8000 by default)."""
    import uvicorn

    from ghostcite.web.app import create_app

    stderr = _stderr()
    if not _is_loopback(host) and os.environ.get(CONTAINER_ENV) == "1":
        # Inside the Docker image a non-loopback bind is required for port publishing. The
        # container cannot see how the port is published, so explain instead of warning.
        stderr.print(
            f"note: listening on {host} inside the container. This address is internal to "
            "the container; compose.yaml publishes it on 127.0.0.1 only. Publishing it on "
            "another interface would let others spend your SerpApi credits.",
            highlight=False,
        )
    elif not _is_loopback(host):
        stderr.print(
            f"[bold yellow]warning:[/] listening on {host} makes GhostCite reachable from other "
            "machines. Anyone who can reach it can spend your SerpApi credits (within the web "
            "UI's limits). Use the default 127.0.0.1 unless you need remote access.",
            highlight=False,
        )
    stderr.print(f"GhostCite web UI: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}")  # noqa: S104 - comparison, not a bind
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@cache_app.command("stats")
def cache_stats() -> None:
    """Show where the cache lives and how many responses it holds."""
    settings = load_settings()
    with SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) as cache:
        stats = cache.stats()
    typer.echo(f"Cache file: {stats.path}")
    typer.echo(f"Responses:  {stats.entries} ({stats.expired} expired)")
    typer.echo(f"Size:       {stats.size_bytes / 1024:.1f} KiB")


@cache_app.command("clear")
def cache_clear(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Delete all cached search responses (the next checks will spend credits again)."""
    if not yes:
        typer.confirm("Delete all cached search responses?", abort=True)
    settings = load_settings()
    with SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) as cache:
        removed = cache.clear()
    typer.echo(f"Removed {removed} cached responses.")


def _utf8_streams() -> None:
    """Windows consoles default to a legacy code page; reports contain any Unicode."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    """Console-script entry point."""
    _utf8_streams()
    app()
