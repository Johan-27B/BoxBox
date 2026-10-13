"""CLI for project Discovery datasets."""

from __future__ import annotations

import csv
import json
import logging
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Iterator

import typer

from ..utils.tokens import TokenPool, load_tokens
from ._constants import (
    BOT_ACCOUNTS_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_TOKEN_FILE,
    REPO_ROOT,
)
from .export import export_candidates
from .harvest import (
    bot_config_sha256,
    harvest_projects,
    load_bot_accounts,
    read_harvest_repos,
)
from .metadata import fetch_project_metadata
from .runs import (
    DiscoveryRun,
    load_run,
    open_run,
    run_counts,
    step_status,
    update_step,
)

app = typer.Typer(no_args_is_help=True, help="Discover candidate projects.")


def _parse_utc(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise typer.BadParameter(f"{option} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise typer.BadParameter(f"{option} must use the UTC offset")
    return parsed.astimezone(UTC)


def _token_pool(token_file: Path, polite_per_min: int) -> TokenPool:
    pool = TokenPool(load_tokens(token_file), polite_per_min=polite_per_min)
    valid, total = pool.health_check()
    if valid < max(1, int(0.8 * total)):
        raise RuntimeError(f"too few valid GitHub tokens: {valid}/{total}")
    return pool


@contextmanager
def _step_logging(run_state: DiscoveryRun, step: str) -> Iterator[None]:
    handler = logging.FileHandler(run_state.log_path(step), mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


def _load_current_run(output_root: Path, run_name: str) -> DiscoveryRun:
    run_state = load_run(output_root, run_name)
    current_fingerprint = bot_config_sha256(BOT_ACCOUNTS_PATH)
    if run_state.bot_config_sha256 != current_fingerprint:
        raise ValueError(f"Discovery run {run_name!r} uses a different bot configuration")
    return run_state


def _execute_harvest(run_state: DiscoveryRun) -> int:
    if step_status(run_state, "harvest") == "complete":
        if not run_state.harvest_path.is_file():
            raise RuntimeError("harvest is complete but harvest.jsonl is missing")
        return len(read_harvest_repos(run_state.harvest_path))
    update_step(run_state, "harvest", status="running")
    try:
        with _step_logging(run_state, "harvest"):
            logging.getLogger("perfrace.discovery").info(
                "harvesting projects for %s", run_state.name
            )
            rows = harvest_projects(
                run_state.harvest_path,
                bot_accounts=load_bot_accounts(BOT_ACCOUNTS_PATH),
                start_at=run_state.start_at,
                end_at=run_state.end_at,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        update_step(
            run_state,
            "harvest",
            status="failed",
            details={"error": str(exc)},
        )
        raise
    update_step(
        run_state,
        "harvest",
        status="complete",
        rows=rows,
        details={"counts": {"discovered": rows}},
    )
    return rows


def _execute_metadata(
    run_state: DiscoveryRun,
    *,
    token_file: Path,
    polite_per_min: int,
    batch_size: int,
    pool: TokenPool | None = None,
) -> tuple[int, int]:
    if step_status(run_state, "harvest") != "complete":
        raise RuntimeError("harvest must complete before metadata")
    if not run_state.harvest_path.is_file():
        raise RuntimeError("harvest.jsonl is missing")
    if step_status(run_state, "metadata") == "complete":
        if not run_state.metadata_path.is_file():
            raise RuntimeError("metadata is complete but metadata.jsonl is missing")
        counts = run_counts(run_state)
        return (
            counts.get("metadata_valid", 0),
            counts.get("metadata_unavailable", 0),
        )

    repos = read_harvest_repos(run_state.harvest_path)
    update_step(run_state, "metadata", status="running")
    try:
        with _step_logging(run_state, "metadata"):
            logging.getLogger("perfrace.discovery").info(
                "fetching metadata for %d projects", len(repos)
            )
            valid, unavailable = fetch_project_metadata(
                pool or _token_pool(token_file, polite_per_min),
                repos,
                run_state.metadata_path,
                batch_size=batch_size,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        update_step(
            run_state,
            "metadata",
            status="failed",
            details={"error": str(exc)},
        )
        raise
    update_step(
        run_state,
        "metadata",
        status="complete",
        rows=len(repos),
        details={
            "counts": {
                "metadata_valid": valid,
                "metadata_unavailable": unavailable,
            }
        },
    )
    return valid, unavailable


def _execute_export(run_state: DiscoveryRun) -> tuple[int, int]:
    if step_status(run_state, "metadata") != "complete":
        raise RuntimeError("metadata must complete before export")
    if not run_state.metadata_path.is_file():
        raise RuntimeError("metadata.jsonl is missing")
    if step_status(run_state, "export") == "complete":
        if not run_state.candidates_path.is_file():
            raise RuntimeError("export is complete but candidates.jsonl is missing")
        counts = run_counts(run_state)
        return counts.get("exported", 0), counts.get("export_excluded", 0)

    update_step(run_state, "export", status="running")
    try:
        with _step_logging(run_state, "export"):
            logging.getLogger("perfrace.discovery").info(
                "exporting candidates for %s", run_state.name
            )
            exported, excluded = export_candidates(
                run_state.harvest_path,
                run_state.metadata_path,
                run_state.candidates_path,
                discovered_at=run_state.created_at,
                authorship_start_at=run_state.authorship_start_at,
                authorship_end_at=run_state.authorship_end_at,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        update_step(
            run_state,
            "export",
            status="failed",
            details={"error": str(exc)},
        )
        raise
    update_step(
        run_state,
        "export",
        status="complete",
        rows=exported,
        details={
            "excluded": excluded,
            "counts": {
                "exported": exported,
                "export_excluded": excluded,
            },
        },
    )
    return exported, excluded


@app.command()
def run(
    start_at: Annotated[str, typer.Option("--start-at", help="Inclusive UTC start.")],
    end_at: Annotated[str, typer.Option("--end-at", help="Exclusive UTC end.")],
    run_name: Annotated[
        str | None,
        typer.Option("--run-name", help="Dataset name. Defaults to a UTC timestamp."),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for Discovery datasets."),
    ] = DEFAULT_OUTPUT_ROOT,
    token_file: Annotated[
        Path,
        typer.Option("--token-file", help="GitHub token-pool JSON file."),
    ] = DEFAULT_TOKEN_FILE,
    polite_per_min: Annotated[
        int,
        typer.Option("--polite-per-min", min=1, help="Requests per minute per token."),
    ] = 10,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, max=50, help="Repositories per GraphQL query."),
    ] = 50,
) -> None:
    """Run harvest, metadata, and export for one dataset."""
    try:
        run_state = open_run(
            output_root,
            run_name=run_name,
            start_at=_parse_utc(start_at, "--start-at"),
            end_at=_parse_utc(end_at, "--end-at"),
            bot_config_sha256=bot_config_sha256(BOT_ACCOUNTS_PATH),
        )
        _execute_harvest(run_state)
        _execute_metadata(
            run_state,
            token_file=token_file,
            polite_per_min=polite_per_min,
            batch_size=batch_size,
        )
        exported, excluded = _execute_export(run_state)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"perfrace discover run: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Discovery run: {run_state.name}")
    typer.echo(f"Candidates: {run_state.candidates_path}")
    typer.echo(f"Exported: {exported}; unavailable: {excluded}")


@app.command()
def harvest(
    start_at: Annotated[str, typer.Option("--start-at", help="Inclusive UTC start.")],
    end_at: Annotated[str, typer.Option("--end-at", help="Exclusive UTC end.")],
    run_name: Annotated[
        str | None,
        typer.Option("--run-name", help="Dataset name. Defaults to a UTC timestamp."),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for Discovery datasets."),
    ] = DEFAULT_OUTPUT_ROOT,
) -> None:
    """Discover projects from configured AI coding-bot signals."""
    try:
        run_state = open_run(
            output_root,
            run_name=run_name,
            start_at=_parse_utc(start_at, "--start-at"),
            end_at=_parse_utc(end_at, "--end-at"),
            bot_config_sha256=bot_config_sha256(BOT_ACCOUNTS_PATH),
        )
        rows = _execute_harvest(run_state)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"perfrace discover harvest: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Discovery run: {run_state.name}")
    typer.echo(f"Harvested: {rows}")


@app.command()
def metadata(
    run_name: Annotated[str, typer.Option("--run-name", help="Existing dataset name.")],
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for Discovery datasets."),
    ] = DEFAULT_OUTPUT_ROOT,
    token_file: Annotated[
        Path,
        typer.Option("--token-file", help="GitHub token-pool JSON file."),
    ] = DEFAULT_TOKEN_FILE,
    polite_per_min: Annotated[
        int,
        typer.Option("--polite-per-min", min=1, help="Requests per minute per token."),
    ] = 10,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, max=50, help="Repositories per GraphQL query."),
    ] = 50,
) -> None:
    """Fetch GitHub repository snapshots for one run."""
    try:
        run_state = _load_current_run(output_root, run_name)
        valid, unavailable = _execute_metadata(
            run_state,
            token_file=token_file,
            polite_per_min=polite_per_min,
            batch_size=batch_size,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"perfrace discover metadata: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Metadata valid: {valid}; unavailable: {unavailable}")


@app.command()
def export(
    run_name: Annotated[str, typer.Option("--run-name", help="Existing dataset name.")],
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for Discovery datasets."),
    ] = DEFAULT_OUTPUT_ROOT,
) -> None:
    """Export one run as candidate JSONL."""
    try:
        run_state = _load_current_run(output_root, run_name)
        exported, excluded = _execute_export(run_state)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"perfrace discover export: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Candidates: {run_state.candidates_path}")
    typer.echo(f"Exported: {exported}; unavailable: {excluded}")


@app.command("convert-tokens")
def convert_tokens(
    input_path: Annotated[
        Path,
        typer.Option("--input", help="CSV file containing a Token column."),
    ] = REPO_ROOT / "config" / "gh_token.env",
    output_path: Annotated[
        Path,
        typer.Option("--output", help="Token-pool JSON destination."),
    ] = DEFAULT_TOKEN_FILE,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing token file."),
    ] = False,
) -> None:
    """Convert a token CSV to the shared version-1 token-pool schema."""
    if output_path.exists() and not force:
        raise typer.BadParameter(f"output already exists: {output_path}")
    if not input_path.is_file():
        raise typer.BadParameter(f"input file not found: {input_path}")
    tokens: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "Token" not in reader.fieldnames:
            raise typer.BadParameter(f"{input_path} is missing a Token column")
        for row in reader:
            value = (row.get("Token") or "").strip()
            if not value:
                continue
            token: dict[str, str] = {"value": value, "type": "classic_pat"}
            label = (row.get("UserName") or "").strip()
            if label:
                token["label"] = label
            tokens.append(token)
    if not tokens:
        raise typer.BadParameter(f"{input_path} contains no tokens")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps({"version": 1, "tokens": tokens}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    typer.echo(f"Wrote {len(tokens)} tokens to {output_path}")


@app.command("token-status")
def token_status(
    token_file: Annotated[
        Path,
        typer.Option("--token-file", help="GitHub token-pool JSON file."),
    ] = DEFAULT_TOKEN_FILE,
    polite_per_min: Annotated[
        int,
        typer.Option("--polite-per-min", min=1, help="Requests per minute per token."),
    ] = 10,
) -> None:
    """Print rate-limit status for every configured GitHub token."""
    try:
        pool = _token_pool(token_file, polite_per_min)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"perfrace discover token-status: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for row in pool.status_summary():
        typer.echo(json.dumps(row, sort_keys=True))
