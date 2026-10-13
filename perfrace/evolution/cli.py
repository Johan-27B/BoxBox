"""Typer command for native offline harness evolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from perfrace.evolution.config import (
    HarnessEvolutionConfigError,
    load_harness_evolution_config,
)
from perfrace.evolution.meta import MetaAgentEndpoint
from perfrace.evolution.orchestrator import (
    prepare_experiment,
    run_evolution,
    validate_iteration_target,
    validate_completed_experiment,
)
from perfrace.evolution.planning import resolve_evolution_plan
from perfrace.evolution.types import EvolutionStage
from perfrace.evolution.usage import write_usage_report
from perfrace.run.config import RunConfigError, load_run
from perfrace.run.services.gateway import run_gateway


def evolve_harness(
    config: Annotated[
        Path,
        typer.Option("-c", "--config", help="Offline harness-evolution YAML path."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Resolve inputs and budget without side effects."),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option("--resume", help="Resume the checksum-matching durable experiment."),
    ] = False,
    iterations: Annotated[
        int | None,
        typer.Option(
            "--iterations",
            min=1,
            help="Cumulative Train iteration target; defaults to the configured maximum.",
        ),
    ] = None,
    stop_after_training: Annotated[
        bool,
        typer.Option(
            "--stop-after-training",
            help="Stop after the requested Train iteration instead of starting Validation.",
        ),
    ] = False,
) -> None:
    """Evolve one shared harness across PerfRace training tasks."""
    raise typer.Exit(
        evolve_harness_command(
            config=config,
            dry_run=dry_run,
            resume=resume,
            iterations=iterations,
            stop_after_training=stop_after_training,
        )
    )


def evolve_harness_command(
    *,
    config: Path,
    dry_run: bool,
    resume: bool,
    iterations: int | None,
    stop_after_training: bool = False,
) -> int:
    """Run the CLI operation and return a process exit code."""
    try:
        loaded = load_harness_evolution_config(config)
        target_iterations = iterations or loaded.config.protocol.generations
        if target_iterations < 1 or target_iterations > loaded.config.protocol.generations:
            raise ValueError(
                "Iteration target must be between 1 and "
                f"{loaded.config.protocol.generations}: {target_iterations}"
            )
        if dry_run:
            plan = resolve_evolution_plan(loaded)
            typer.echo(
                json.dumps(
                    {
                        **plan.model_dump(mode="json"),
                        "requested_iterations": target_iterations,
                    },
                    indent=2,
                )
            )
            return 0
        prepared = prepare_experiment(loaded, resume=resume)
        validate_iteration_target(prepared, target_iterations)
        if prepared.state.stage in {EvolutionStage.TEST_READY, EvolutionStage.COMPLETE}:
            validate_completed_experiment(prepared)
            write_usage_report(
                prepared.paths,
                experiment_name=prepared.state.experiment_name,
                completed_iterations=prepared.state.active_generation,
            )
            typer.echo(
                json.dumps(
                    {
                        "experiment": prepared.state.experiment_name,
                        "stage": prepared.state.stage,
                        "current_harness": f"h{prepared.state.active_generation}",
                        "completed_iterations": prepared.state.active_generation,
                        "next_iteration": None,
                        "selection": (
                            str(prepared.state.selection_path)
                            if prepared.state.selection_path is not None
                            else None
                        ),
                    },
                    indent=2,
                )
            )
            return 0
        if (
            prepared.state.stage == EvolutionStage.TRAINING
            and prepared.state.active_generation == target_iterations
            and target_iterations < prepared.plan.generations
        ):
            write_usage_report(
                prepared.paths,
                experiment_name=prepared.state.experiment_name,
                completed_iterations=prepared.state.active_generation,
            )
            typer.echo(
                json.dumps(
                    {
                        "experiment": prepared.state.experiment_name,
                        "stage": prepared.state.stage,
                        "current_harness": f"h{prepared.state.active_generation}",
                        "completed_iterations": prepared.state.active_generation,
                        "next_iteration": prepared.state.active_generation + 1,
                        "selection": None,
                    },
                    indent=2,
                )
            )
            return 0
        base_run = load_run(loaded.config.base_run_config)
        gateway = base_run.api_gateway
        if gateway is None or gateway.base_url is None:
            raise ValueError("Harness evolution base run config requires an api_gateway")
        gateway = gateway.model_copy(update={"log_dir": prepared.paths.root / "gateway"})
        with run_gateway(gateway) as verifier_kwargs:
            host_token_proxy = verifier_kwargs.get("host_token_proxy_base_url")
            token_proxy_secret = verifier_kwargs.get("token_proxy_secret")
            if not isinstance(host_token_proxy, str) or not isinstance(token_proxy_secret, str):
                raise RuntimeError("Experiment gateway did not start its token proxy")
            endpoint = MetaAgentEndpoint(
                base_url=f"{host_token_proxy.rstrip('/')}/v1",
                token_proxy_secret=token_proxy_secret,
                model=loaded.config.model_name,
                reasoning_effort=loaded.config.protocol.reasoning_effort,
                session_prefix=loaded.config.experiment_name,
            )
            completed = run_evolution(
                prepared,
                iterations=target_iterations,
                endpoint=endpoint,
                verifier_kwargs=verifier_kwargs,
                stop_after_training=stop_after_training,
            )
        write_usage_report(
            completed.paths,
            experiment_name=completed.state.experiment_name,
            completed_iterations=completed.state.active_generation,
        )
        typer.echo(
            json.dumps(
                {
                    "experiment": completed.state.experiment_name,
                    "stage": completed.state.stage,
                    "current_harness": f"h{completed.state.active_generation}",
                    "completed_iterations": completed.state.active_generation,
                    "next_iteration": (
                        completed.state.active_generation + 1
                        if completed.state.stage == EvolutionStage.TRAINING
                        else None
                    ),
                    "selection": (
                        str(completed.state.selection_path)
                        if completed.state.selection_path is not None
                        else None
                    ),
                },
                indent=2,
            )
        )
        return 0
    except (
        HarnessEvolutionConfigError,
        RunConfigError,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        typer.echo(f"perfrace evolve-harness: {exc}", err=True)
        return 2
