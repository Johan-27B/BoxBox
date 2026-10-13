"""Normalize user-selected GitHub projects into the same Filter input schema."""

from __future__ import annotations
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
import typer
from .metadata import fetch_project_metadata
from .export import validate_candidate
from ..utils.tokens import TokenPool, load_tokens
from ..utils._constants import DEFAULT_TOKEN_FILE


def repository_names(text: str) -> list[str]:
    names = set()
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        value = value.removeprefix("https://github.com/").removesuffix("/").removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError(f"Expected owner/repository or a GitHub repository URL: {line}")
        names.add(value)
    if not names:
        raise ValueError("Project list is empty")
    return sorted(names)


def import_projects(
    projects: Annotated[Path, typer.Argument(help="One GitHub repository per line.")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    token_file: Annotated[Path, typer.Option("--token-file")] = DEFAULT_TOKEN_FILE,
) -> None:
    """Resolve revisions and metadata; send these candidates through normal Filter."""
    repos = repository_names(projects.read_text())
    pool = TokenPool(load_tokens(token_file))
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / "metadata.jsonl"
    fetch_project_metadata(pool, repos, metadata)
    now = datetime.now(UTC)
    timestamp = lambda t: t.isoformat().replace("+00:00", "Z")
    candidates = []
    for line in metadata.read_text().splitlines():
        row = json.loads(line)
        data = row.get("metadata")
        if not data or not data.get("observed_revision") or not data.get("default_branch"):
            continue
        candidate = dict(data)
        candidate.update(
            discovery_channel="project-list",
            discovered_at=timestamp(now),
            signal_kind="branch",
            signal_url=f"{data['repo_url']}/tree/{data['default_branch']}",
            signal_actors=["user-selected"],
            authorship_window={
                "start_at": timestamp(now - timedelta(days=180)),
                "end_at": timestamp(now),
            },
        )
        validate_candidate(candidate)
        candidates.append(candidate)
    path = output / "candidates.jsonl"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in candidates))
    typer.echo(f"{len(candidates)} candidates: {path}")
