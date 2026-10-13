"""PerfRace command line entry point."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

import typer

from perfrace.collect.discovery.cli import app as discovery_app
from perfrace.collect.filter.cli import app as filter_app
from perfrace.curate.cli import verify_dashboard
from perfrace.curate.lint import lint_cli
from perfrace.release.cli import export_releases, publish
from perfrace.run.cli import run
from perfrace.plot import plot
from perfrace.collect.discovery.projects import import_projects
from perfrace.evolution.cli import evolve_harness

app = typer.Typer(no_args_is_help=True, help="PerfRace command line tools.")


@app.callback()
def root(
    settings: Annotated[
        Path | None, typer.Option("--settings", help="Local operator settings YAML.")
    ] = None,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Logging verbosity (DEBUG/INFO/WARNING/ERROR). Also settable via "
            "PERFRACE_LOG_LEVEL.",
        ),
    ] = os.environ.get("PERFRACE_LOG_LEVEL", "INFO"),
) -> None:
    """PerfRace command line tools with shared logging configuration."""
    if settings is not None:
        os.environ["PERFRACE_SETTINGS"] = str(settings.expanduser().resolve())
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


app.command()(run)
app.command()(plot)
app.command(name="evolve-harness")(evolve_harness)
app.command()(publish)
app.command(name="export-releases")(export_releases)
app.command(name="verify-dashboard")(verify_dashboard)
discovery_app.command(name="import-projects")(import_projects)
app.add_typer(discovery_app, name="discover")
app.add_typer(filter_app, name="filter")


@app.command()
def lint(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(
            help="Instance directories to lint. Defaults to PERFRACE_INSTANCE_ROOT "
            "or the sibling PerfRace-Bench directory."
        ),
    ] = None,
) -> None:
    """Lint each instance's task.toml against PerfRace's minimal schema."""
    raise typer.Exit(code=lint_cli(paths))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
