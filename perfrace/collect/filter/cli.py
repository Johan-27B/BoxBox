"""CLI for evidence-based candidate Filter runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Iterator

import typer
from perfrace.settings import configured_model

from ..utils.tokens import TokenPool, load_tokens
from ._constants import (
    COAUTHOR_SIGNATURES_PATH,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TOKEN_FILE,
    MAX_FILE_BYTES,
    MAX_LICENSE_BYTES,
    MAX_README_BYTES,
    MAX_SELECTED_FILES,
    MAX_SNAPSHOT_BYTES,
    MAX_STARGAZER_COUNT,
    MAX_TRACKED_BYTES,
    MAX_TREE_ENTRIES,
    MAX_TREE_PATHS_IN_PROMPT,
    MIN_STARGAZER_COUNT,
    PROMPT_PATH,
)
from .authorship import (
    coauthor_config_sha256,
    load_coauthor_signatures,
    measure_authorship,
)
from .export import (
    append_record,
    error_result,
    judged_result,
    load_latest_records,
    precheck_rejection,
    read_candidates,
    rebuild_exports,
)
from .github import GitHubSnapshotError, RepositoryRejected, fetch_repository_evidence
from .judge import iter_judgments, judgment_schema
from .runs import FilterRun, open_run, update_manifest
from .snapshot import build_snapshot

app = typer.Typer(no_args_is_help=True, help="Filter Discovery candidates.")


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_policy_sha256() -> str:
    implementation = hashlib.sha256()
    for name in ("github.py", "snapshot.py"):
        implementation.update(Path(__file__).with_name(name).read_bytes())
    return _sha256_json(
        {
            "implementation_sha256": implementation.hexdigest(),
            "max_snapshot_bytes": MAX_SNAPSHOT_BYTES,
            "max_stargazer_count": MAX_STARGAZER_COUNT,
            "min_stargazer_count": MIN_STARGAZER_COUNT,
            "max_tree_entries": MAX_TREE_ENTRIES,
            "max_tracked_bytes": MAX_TRACKED_BYTES,
            "max_tree_paths": MAX_TREE_PATHS_IN_PROMPT,
            "max_selected_files": MAX_SELECTED_FILES,
            "max_readme_bytes": MAX_README_BYTES,
            "max_license_bytes": MAX_LICENSE_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
        }
    )


def _authorship_policy_sha256() -> str:
    implementation = hashlib.sha256()
    implementation.update(Path(__file__).with_name("authorship.py").read_bytes())
    return _sha256_json(
        {
            "implementation_sha256": implementation.hexdigest(),
            "coauthor_config_sha256": coauthor_config_sha256(COAUTHOR_SIGNATURES_PATH),
            "candidate_selection": "filter_pass",
        }
    )


def _token_pool(token_file: Path) -> TokenPool:
    pool = TokenPool(load_tokens(token_file), polite_per_min=10)
    valid, total = pool.health_check()
    if valid < max(1, int(0.8 * total)):
        raise RuntimeError(f"too few valid GitHub tokens: {valid}/{total}")
    return pool


@contextmanager
def _run_logging(run_state: FilterRun) -> Iterator[None]:
    handler = logging.FileHandler(run_state.log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


async def _prepare_snapshots(
    run_state: FilterRun,
    candidates: list[dict[str, Any]],
    pool: TokenPool,
) -> list[dict[str, Any]]:
    latest_results = load_latest_records(run_state.results_path)
    snapshots = load_latest_records(run_state.snapshots_path)
    ready: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(run_state.concurrency)

    async def fetch_one(candidate: dict[str, Any]) -> tuple[str, Any]:
        async with semaphore:
            try:
                evidence = await asyncio.to_thread(
                    fetch_repository_evidence,
                    pool,
                    candidate,
                )
                return "snapshot", build_snapshot(candidate, evidence)
            except RepositoryRejected as exc:
                return (
                    "result",
                    precheck_rejection(
                        candidate,
                        gate=exc.gate,
                        reason=exc.reason,
                        evidence=exc.evidence,
                    ),
                )
            except (GitHubSnapshotError, OSError, RuntimeError, ValueError) as exc:
                return (
                    "result",
                    error_result(
                        candidate,
                        error_type=type(exc).__name__,
                        error=str(exc),
                        snapshot_sha256=None,
                    ),
                )

    tasks: list[asyncio.Task[tuple[str, Any]]] = []
    for candidate in candidates:
        repo_url = candidate["repo_url"]
        previous = latest_results.get(repo_url)
        if previous is not None and previous.get("status") in {"PASS", "REJECT"}:
            continue
        if candidate["stargazer_count"] < MIN_STARGAZER_COUNT:
            append_record(
                run_state.results_path,
                precheck_rejection(
                    candidate,
                    gate="minimum_stars",
                    reason=(
                        f"Repository has {candidate['stargazer_count']} stars; "
                        f"Filter requires at least {MIN_STARGAZER_COUNT}."
                    ),
                    evidence=[
                        f"candidate.stargazer_count = {candidate['stargazer_count']}",
                        f"minimum stargazer count = {MIN_STARGAZER_COUNT}",
                    ],
                ),
            )
            continue
        if candidate["stargazer_count"] >= MAX_STARGAZER_COUNT:
            append_record(
                run_state.results_path,
                precheck_rejection(
                    candidate,
                    gate="maximum_stars",
                    reason=(
                        f"Repository has {candidate['stargazer_count']} stars; "
                        f"Filter requires fewer than {MAX_STARGAZER_COUNT}."
                    ),
                    evidence=[
                        f"candidate.stargazer_count = {candidate['stargazer_count']}",
                        f"maximum stargazer count = {MAX_STARGAZER_COUNT}",
                    ],
                ),
            )
            continue
        existing_snapshot = snapshots.get(repo_url)
        if existing_snapshot is not None:
            ready.append(existing_snapshot)
            continue
        task = asyncio.create_task(fetch_one(candidate))
        tasks.append(task)

    for task in asyncio.as_completed(tasks):
        kind, payload = await task
        if kind == "snapshot":
            append_record(run_state.snapshots_path, payload)
            ready.append(payload)
        else:
            append_record(run_state.results_path, payload)
    return ready


def _attach_authorship_to_pass_results(
    run_state: FilterRun,
    candidates: list[dict[str, Any]],
    pool: TokenPool,
) -> tuple[int, int]:
    latest_results = load_latest_records(run_state.results_path)
    passed_candidates = [
        latest_results[candidate["repo_url"]]["candidate"]
        for candidate in candidates
        if candidate["repo_url"] in latest_results
        and latest_results[candidate["repo_url"]].get("status") == "PASS"
    ]
    if not passed_candidates:
        return 0, 0

    projects, ai_commits = measure_authorship(
        pool,
        passed_candidates,
        run_state.authorship_path,
        signatures=load_coauthor_signatures(COAUTHOR_SIGNATURES_PATH),
    )
    metrics = load_latest_records(run_state.authorship_path)
    for candidate in passed_candidates:
        repo_url = candidate["repo_url"]
        metric = metrics.get(repo_url)
        if metric is None:
            raise RuntimeError(f"authorship record is missing for {repo_url}")
        authorship = {
            key: metric.get(key)
            for key in (
                "scope",
                "start_at",
                "end_at",
                "total_commits",
                "ai_commits",
                "ai_ratio",
            )
        }
        result = latest_results[repo_url]
        if result["candidate"].get("authorship") == authorship:
            continue
        updated = json.loads(json.dumps(result))
        updated["candidate"]["authorship"] = authorship
        append_record(run_state.results_path, updated)
    return projects, ai_commits


async def _judge_ready_snapshots(
    run_state: FilterRun,
    snapshots: list[dict[str, Any]],
) -> None:
    candidates = {
        snapshot["candidate"]["repo_url"]: snapshot["candidate"] for snapshot in snapshots
    }
    async for outcome in iter_judgments(
        snapshots,
        model=run_state.model,
        reasoning_effort=run_state.reasoning_effort,
        concurrency=run_state.concurrency,
        timeout_seconds=run_state.timeout_seconds,
        retries=run_state.retries,
        max_output_tokens=run_state.max_output_tokens,
        log_path=run_state.proxy_log_path,
    ):
        candidate = candidates[outcome["repo_url"]]
        if outcome["status"] == "JUDGED":
            result = judged_result(candidate, outcome)
        else:
            result = error_result(
                candidate,
                error_type=outcome["error_type"],
                error=outcome["error"],
                snapshot_sha256=outcome["snapshot_sha256"],
                model=outcome["model"],
                reasoning_effort=outcome["reasoning_effort"],
                attempts=outcome["attempts"],
                usage=outcome["usage"],
                cost_usd=outcome["cost_usd"],
            )
        append_record(run_state.results_path, result)


@app.command()
def run(
    candidate_file: Annotated[
        Path,
        typer.Option("--candidate-file", help="Discovery candidate JSONL."),
    ],
    run_name: Annotated[
        str | None,
        typer.Option("--run-name", help="Filter dataset name."),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for Filter datasets."),
    ] = DEFAULT_OUTPUT_ROOT,
    token_file: Annotated[
        Path,
        typer.Option("--token-file", help="GitHub token-pool JSON file."),
    ] = DEFAULT_TOKEN_FILE,
    model: Annotated[
        str,
        typer.Option("--model", help="Model identifier accepted by the configured endpoint."),
    ] = DEFAULT_MODEL,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", min=1, help="Concurrent snapshots and judgments."),
    ] = DEFAULT_CONCURRENCY,
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", min=1, help="Per-model-call timeout."),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Filter one ranked Discovery candidate dataset."""
    prompt_sha256 = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    schema_sha256 = _sha256_json(judgment_schema())
    model = configured_model("filter", model)
    try:
        run_state = open_run(
            output_root,
            run_name=run_name,
            candidate_file=candidate_file,
            model=model,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            retries=DEFAULT_RETRIES,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
            prompt_sha256=prompt_sha256,
            schema_sha256=schema_sha256,
            snapshot_policy_sha256=_snapshot_policy_sha256(),
            authorship_policy_sha256=_authorship_policy_sha256(),
        )
        candidates = read_candidates(run_state.candidate_file)
        update_manifest(
            run_state,
            status="running",
            counts={
                "input": len(candidates),
                "processed": 0,
                "passed": 0,
                "rejected": 0,
                "errors": 0,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )
        with _run_logging(run_state):
            pool = _token_pool(token_file)
            snapshots = asyncio.run(_prepare_snapshots(run_state, candidates, pool))
            if snapshots:
                asyncio.run(_judge_ready_snapshots(run_state, snapshots))
            authorship_projects, authorship_ai_commits = _attach_authorship_to_pass_results(
                run_state,
                candidates,
                pool,
            )
            update_manifest(
                run_state,
                authorship={
                    "processed": authorship_projects,
                    "ai_commits": authorship_ai_commits,
                },
            )
            summary = rebuild_exports(run_state, candidates)
            cost = summary.pop("cost_usd")
            update_manifest(
                run_state,
                status="complete" if summary["errors"] == 0 else "incomplete",
                counts=summary,
                cost_usd=None if cost < 0 else cost,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        if "run_state" in locals():
            update_manifest(run_state, status="failed", error=str(exc))
        typer.echo(f"perfrace filter run: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Filter run: {run_state.name}")
    typer.echo(f"Passed: {summary['passed']}")
    typer.echo(f"High priority: {summary['high_priority']}")
    typer.echo(f"Rejected: {summary['rejected']}")
    typer.echo(f"Errors: {summary['errors']}")
    typer.echo(f"PASS queue: {run_state.passed_path}")
    typer.echo(f"High-priority queue: {run_state.high_priority_path}")
