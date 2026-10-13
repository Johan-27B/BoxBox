"""Typer-facing adapter for ``perfrace run``."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from harbor.models.job.config import DatasetConfig
from harbor.models.task.task import Task
from harbor.models.trial.config import TaskConfig

from perfrace.run.config import LoadedRun, RunConfigError, load_run

logger = logging.getLogger(__name__)


def run(
    path: Annotated[
        Path | None,
        typer.Option(
            "-p",
            "--path",
            help="Local Harbor task or dataset directory. Replaces job.tasks and job.datasets.",
        ),
    ] = None,
    include_task_names: Annotated[
        list[str] | None,
        typer.Option(
            "-i",
            "--include-task-name",
            help="Task-name glob to include from the --path dataset. Repeatable.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Run config YAML/JSON path."),
    ] = None,
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            help="Candidate agent: a registered Harbor agent name, or an "
            "import_path (module.path:ClassName) if it contains ':'.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name passed to the candidate agent."),
    ] = None,
    n_attempts: Annotated[
        int | None,
        typer.Option("--n-attempts", help="Override Harbor job.n_attempts."),
    ] = None,
    enable_cache: Annotated[
        bool | None,
        typer.Option(
            "--enable-cache/--no-enable-cache",
            help="Reuse cached baseline trials when available. Defaults to "
            "disabled unless a run config's own top-level enable_cache field "
            "is set (an explicit flag always wins over that field).",
        ),
    ] = None,
    patch: Annotated[
        Path | None,
        typer.Option("--patch", help="Local submission directory (predictions.jsonl)."),
    ] = None,
    job_name: Annotated[
        str | None,
        typer.Option("--job-name", help="Override job name."),
    ] = None,
    jobs_dir: Annotated[
        Path | None,
        typer.Option("--jobs-dir", help="Override jobs directory."),
    ] = None,
    note: Annotated[
        str | None,
        typer.Option("--note", help="Free-form note recorded in run.json."),
    ] = None,
    agent_tag: Annotated[
        str | None,
        typer.Option("--agent-tag", help="Free-form agent tag recorded in run.json."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print resolved config without executing."),
    ] = False,
) -> None:
    """Run PerfRace instances."""
    raise typer.Exit(
        run_command(
            path=path,
            include_task_names=include_task_names or [],
            config=config,
            agent=agent,
            model=model,
            n_attempts=n_attempts,
            enable_cache=enable_cache,
            patch=patch,
            job_name=job_name,
            jobs_dir=jobs_dir,
            note=note,
            agent_tag=agent_tag,
            dry_run=dry_run,
        )
    )


def run_command(
    *,
    path: Path | None,
    include_task_names: list[str],
    config: Path | None,
    agent: str | None,
    model: str | None,
    n_attempts: int | None,
    enable_cache: bool | None,
    patch: Path | None,
    job_name: str | None,
    jobs_dir: Path | None,
    note: str | None,
    agent_tag: str | None,
    dry_run: bool,
) -> int:
    try:
        resolved = _apply_cli_task_selection(
            load_run(
                config,
                agent=agent,
                model=model,
                n_attempts=n_attempts,
                job_name=job_name,
                jobs_dir=jobs_dir,
                enable_cache=enable_cache,
                patch=patch,
                note=note,
                agent_tag=agent_tag,
            ),
            path=path,
            include_task_names=include_task_names,
        )
        logger.info(
            "Resolved run config: config=%s job_name=%s jobs_dir=%s tasks=%d datasets=%d "
            "candidate_agents=%d enable_cache=%s api_gateway=%s submission_path=%s",
            config if config is not None else "(none, CLI-only)",
            resolved.job.job_name,
            resolved.job.jobs_dir,
            len(resolved.job.tasks),
            len(resolved.job.datasets),
            len(resolved.job.agents),
            resolved.enable_cache,
            resolved.api_gateway.base_url if resolved.api_gateway is not None else None,
            resolved.submission_path,
        )
        if dry_run:
            typer.echo(json.dumps(resolved.to_json_dict(), indent=2, sort_keys=True))
            return 0
        from perfrace.run.runner import run as run_job

        return run_job(resolved)
    except RunConfigError as exc:
        typer.echo(f"perfrace run: {exc}", err=True)
        return 2


def _apply_cli_task_selection(
    loaded: LoadedRun,
    *,
    path: Path | None,
    include_task_names: list[str],
) -> LoadedRun:
    """Apply Harbor-compatible task selection to a loaded run config."""
    if path is None:
        if include_task_names:
            raise RunConfigError("--include-task-name requires --path")
        selected = loaded
    else:
        # Resolve relative CLI paths from the caller's current directory,
        # exactly as Harbor's --path option does.
        selected_path = path.expanduser().resolve()
        if Task.is_valid_dir(
            selected_path,
            disable_verification=loaded.job.verifier.disable,
        ):
            job = loaded.job.model_copy(
                update={"tasks": [TaskConfig(path=selected_path)], "datasets": []}
            )
        else:
            job = loaded.job.model_copy(
                update={
                    "tasks": [],
                    "datasets": [
                        DatasetConfig(
                            path=selected_path,
                            task_names=include_task_names or None,
                        )
                    ],
                }
            )
        selected = replace(loaded, job=job)

    if not selected.job.tasks and not selected.job.datasets:
        raise RunConfigError("Specify a task or dataset in the run config or with --path")
    return selected
