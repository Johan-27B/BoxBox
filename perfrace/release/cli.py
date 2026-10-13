"""CLI for publishing complete PerfRace instance releases."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from perfrace.paths import resolve_instance_root
from perfrace.paths import PROJECT_ROOT
from perfrace.release.catalog import sync_release_catalog
from perfrace.release.oci import OrasClient
from perfrace.release.publisher import (
    InstancePublisher,
    accepted_instances,
)


def _default_tag() -> str:
    return datetime.now(UTC).strftime("release-%Y%m%d-%H%M%S")


def publish(
    path: Annotated[
        Path | None,
        typer.Argument(help="One instance directory to publish."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option("--image", help="Local image for a new instance release."),
    ] = None,
    repository: Annotated[
        str | None,
        typer.Option("--repository", help="GHCR repository for a new release."),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Temporary image tag used during publication."),
    ] = None,
    all_accepted: Annotated[
        bool,
        typer.Option(
            "--all-accepted",
            help="Publish missing task artifacts for accepted formal instances.",
        ),
    ] = False,
    instance_root: Annotated[
        Path | None,
        typer.Option("--instance-root", help="Formal instance and release-record root."),
    ] = None,
    oras_command: Annotated[
        str,
        typer.Option("--oras-command", help="Pinned ORAS 1.3.3 executable."),
    ] = "oras",
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            min=1,
            help="Maximum missing accepted instances to publish.",
        ),
    ] = 5,
) -> None:
    """Publish an image and task package as one instance release."""
    root = resolve_instance_root(instance_root)
    publisher = InstancePublisher(
        instance_root=root,
        oras=OrasClient(oras_command),
    )
    if all_accepted:
        if path is not None or image is not None or repository is not None:
            raise typer.BadParameter(
                "--all-accepted cannot be combined with a path, --image, or --repository"
            )
        publisher.oras.preflight()
        selected: list[Path] = []
        for instance in accepted_instances(root):
            try:
                current = publisher.current_release(instance)
            except Exception as exc:
                typer.echo(f"FAILED {instance.name}: {exc}", err=True)
                continue
            if current is not None:
                typer.echo(f"SKIPPED {instance.name}: matching release exists")
                continue
            selected.append(instance)
            if len(selected) == batch_size:
                break
        typer.echo(f"Publishing {len(selected)} accepted instances")
        failures = 0
        for instance in selected:
            try:
                record = publisher.publish(instance)
            except Exception as exc:
                failures += 1
                typer.echo(f"FAILED {instance.name}: {exc}", err=True)
            else:
                typer.echo(f"PUBLISHED {instance.name} {record.task_artifact}")
        if failures:
            raise typer.Exit(code=1)
        return

    if path is None:
        raise typer.BadParameter("an instance path is required")
    record = publisher.publish(
        path,
        local_image=image,
        repository=repository,
        tag=tag or _default_tag(),
    )
    typer.echo(json.dumps(asdict(record), indent=2, sort_keys=True))


def export_releases(
    instance_root: Annotated[
        Path | None,
        typer.Option("--instance-root", help="Formal instance and release-record root."),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", help="Release catalog JSON path."),
    ] = PROJECT_ROOT / "releases" / "instance-releases.json",
) -> None:
    """Export release records as a deterministic repository catalog."""
    root = resolve_instance_root(instance_root)
    destination = output.expanduser().resolve()
    instances = sync_release_catalog(root, destination)
    typer.echo(f"Wrote {len(instances)} releases to {destination}")
