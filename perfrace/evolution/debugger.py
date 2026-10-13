"""Progressive-disclosure debugger and generation overview."""

from __future__ import annotations
import argparse
import os
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from pathlib import Path

from perfrace.evolution.meta import MetaAgentEndpoint, rotate_failed_output
from perfrace.evolution.nexau_runner import (
    run_nexau_agent,
    validate_nexau_output,
)
from perfrace.evolution.state import (
    read_model,
    write_model_atomic,
    write_text_atomic,
)
from perfrace.evolution.types import (
    DebuggerWorkerSpec,
    GenerationEvidence,
    TaskEvidence,
)


AGENT_CONFIG = Path(__file__).with_name("agents") / "debugger_agent.yaml"
_WORKER_API_KEY_ENV = "PERFRACE_DEBUGGER_API_KEY"


def _unique_resolved_paths(paths: list[Path]) -> tuple[Path, ...]:
    """Resolve paths while preserving their first-seen order."""
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return tuple(unique)


def _task_read_roots(
    *,
    evidence_path: Path,
    task: TaskEvidence,
    task_output: Path,
) -> tuple[Path, ...]:
    """Expose only one train task's indexed artifacts to its debugger."""
    roots = [evidence_path, task_output]
    for attempt in task.attempts:
        roots.extend(
            [
                attempt.trial_dir,
                attempt.selected_measurement,
                *attempt.checkpoint_measurements,
                *attempt.trajectories,
            ]
        )
    return _unique_resolved_paths(roots)


def _run_worker_process(spec_path: Path, api_key: str) -> None:
    """Launch one debugger in an isolated Python subprocess."""
    environment = {**os.environ, _WORKER_API_KEY_ENV: api_key}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "perfrace.evolution.debugger",
            "--worker-spec",
            str(spec_path),
        ],
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Debugger worker failed with exit code {completed.returncode}: {spec_path}"
        )
    spec = read_model(spec_path, DebuggerWorkerSpec)
    if not validate_nexau_output(spec.output_dir):
        raise RuntimeError(f"Debugger worker did not complete atomically: {spec.output_dir}")


def _run_worker_pool(
    workers: list[tuple[Path, str]],
    *,
    max_workers: int,
) -> None:
    """Run bounded subprocess workers and stop submitting after a failure."""
    if max_workers < 1:
        raise ValueError("debugger max_workers must be positive")
    pending = iter(workers)
    active: dict[Future[None], Path] = {}
    failures: list[tuple[Path, Exception]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in range(min(max_workers, len(workers))):
            spec_path, api_key = next(pending)
            active[executor.submit(_run_worker_process, spec_path, api_key)] = spec_path
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                spec_path = active.pop(future)
                try:
                    future.result()
                except Exception as exc:
                    failures.append((spec_path, exc))
            if failures:
                for future, spec_path in tuple(active.items()):
                    try:
                        future.result()
                    except Exception as exc:
                        failures.append((spec_path, exc))
                active.clear()
                break
            for _ in range(len(done)):
                try:
                    spec_path, api_key = next(pending)
                except StopIteration:
                    break
                active[executor.submit(_run_worker_process, spec_path, api_key)] = spec_path
    if failures:
        detail = "; ".join(f"{path}: {error}" for path, error in failures)
        raise RuntimeError(f"Debugger worker pool failed after active workers settled: {detail}")


def run_debugger_worker(spec_path: Path) -> None:
    """Execute one secret-free worker spec using a process-local API key."""
    spec = read_model(spec_path, DebuggerWorkerSpec)
    api_key = os.environ.pop(_WORKER_API_KEY_ENV, None)
    if not api_key:
        raise RuntimeError(f"Missing {_WORKER_API_KEY_ENV} for debugger worker")
    if validate_nexau_output(spec.output_dir):
        return
    run_nexau_agent(
        config_path=spec.config_path,
        workspace=spec.workspace,
        output_dir=spec.output_dir,
        model=spec.model,
        base_url=spec.base_url,
        api_key=api_key,
        reasoning_effort=spec.reasoning_effort,
        session_id=spec.session_id,
        message=spec.message,
        context=spec.context,
        read_roots=spec.read_roots,
        write_roots=spec.write_roots,
        shell_root=spec.shell_root,
    )
    if not validate_nexau_output(spec.output_dir):
        raise RuntimeError(f"Debugger worker output is incomplete: {spec.output_dir}")


def _historical_overview_inputs(
    experiment_root: Path,
    evidence: GenerationEvidence,
) -> tuple[tuple[Path, ...], str, str]:
    """Index prior Train evidence as paired same-task or unpaired history."""
    roots: list[Path] = []
    same_task_iterations: dict[str, list[int]] = {task.task_name: [] for task in evidence.tasks}
    different_task_iterations: list[int] = []
    generations_root = experiment_root / "generations"
    for generation_dir in sorted(generations_root.glob("[0-9][0-9][0-9][0-9]")):
        prior_evidence_path = generation_dir / "train" / "evidence.json"
        if not prior_evidence_path.is_file():
            continue
        prior = read_model(prior_evidence_path, GenerationEvidence)
        if prior.iteration >= evidence.iteration:
            continue
        roots.append(prior_evidence_path)
        for path in (
            generation_dir / "train" / "score.json",
            generation_dir / "analysis" / "overview.md",
            generation_dir / "analysis" / "detail",
        ):
            if path.exists():
                roots.append(path)
        prior_names = {task.task_name for task in prior.tasks}
        overlap = prior_names & set(same_task_iterations)
        for task_name in overlap:
            same_task_iterations[task_name].append(prior.iteration)
        if prior_names - overlap:
            different_task_iterations.append(prior.iteration)
    same_task_text = "; ".join(
        f"{task_name}:i{','.join(str(item) for item in iterations)}"
        for task_name, iterations in sorted(same_task_iterations.items())
        if iterations
    )
    different_task_text = ",".join(
        f"i{iteration}" for iteration in sorted(set(different_task_iterations))
    )
    return _unique_resolved_paths(roots), same_task_text, different_task_text


def run_generation_debugger(
    *,
    evidence_path: Path,
    score_path: Path,
    experiment_root: Path,
    output_dir: Path,
    endpoint: MetaAgentEndpoint,
    previous_overview_path: Path | None,
    max_workers: int,
) -> Path:
    """Create resumable per-task reports and one cross-task overview."""
    evidence = read_model(evidence_path, GenerationEvidence)
    detail_dir = output_dir / "detail"
    detail_dir.mkdir(parents=True, exist_ok=True)
    worker_spec_dir = output_dir / "worker-specs"
    worker_spec_dir.mkdir(parents=True, exist_ok=True)
    workers: list[tuple[Path, str]] = []
    for task in evidence.tasks:
        slug = "".join(
            character if character.isalnum() or character in "._-" else "_"
            for character in task.task_name
        )
        task_output = detail_dir / slug
        if validate_nexau_output(task_output):
            continue
        if task_output.exists():
            rotate_failed_output(task_output)
        session_id = (
            f"{endpoint.session_prefix}-debug-i{evidence.iteration}-h{evidence.generation}-{slug}"
        )
        spec = DebuggerWorkerSpec(
            config_path=AGENT_CONFIG.resolve(),
            workspace=task_output.resolve(),
            output_dir=task_output.resolve(),
            model=endpoint.model,
            base_url=endpoint.base_url,
            reasoning_effort=endpoint.reasoning_effort,
            session_id=session_id,
            message=(
                f"Analyze task {task.task_name} for iteration {evidence.iteration} "
                f"under harness h{evidence.generation}."
            ),
            context={
                "analysis_mode": "task",
                "iteration": evidence.iteration,
                "generation": evidence.generation,
                "epoch": evidence.epoch,
                "batch_index": evidence.batch_index,
                "task_name": task.task_name,
                "evidence_path": str(evidence_path.resolve()),
            },
            read_roots=_task_read_roots(
                evidence_path=evidence_path,
                task=task,
                task_output=task_output,
            ),
            write_roots=(task_output.resolve(),),
            shell_root=task_output.resolve(),
        )
        spec_path = worker_spec_dir / f"{slug}.json"
        if spec_path.is_file():
            if read_model(spec_path, DebuggerWorkerSpec) != spec:
                raise ValueError(f"Debugger worker spec changed on resume: {spec_path}")
        else:
            write_model_atomic(spec_path, spec)
        workers.append((spec_path, endpoint.api_key_for(session_id)))
    _run_worker_pool(workers, max_workers=max_workers)
    overview_output = output_dir / "overview"
    overview_result = overview_output / "result.md"
    overview_path = output_dir / "overview.md"
    overview_complete = validate_nexau_output(overview_output)
    if overview_path.is_file():
        if not overview_complete:
            raise ValueError(
                f"Overview exists without complete source artifacts: {overview_output}"
            )
        expected = f"{overview_result.read_text(encoding='utf-8').rstrip()}\n"
        if overview_path.read_text(encoding="utf-8") == expected:
            return overview_path
        rotate_failed_output(overview_path)
        write_text_atomic(overview_path, expected)
        return overview_path
    if overview_complete:
        result = overview_result.read_text(encoding="utf-8")
    else:
        if overview_output.exists():
            rotate_failed_output(overview_output)
        session_id = (
            f"{endpoint.session_prefix}-overview-i{evidence.iteration}-h{evidence.generation}"
        )
        overview_read_roots = [detail_dir, score_path, overview_output]
        historical_roots, same_task_history, different_task_history = _historical_overview_inputs(
            experiment_root, evidence
        )
        overview_read_roots.extend(historical_roots)
        if previous_overview_path is not None and previous_overview_path.is_file():
            overview_read_roots.append(previous_overview_path)
        result = run_nexau_agent(
            config_path=AGENT_CONFIG,
            workspace=overview_output,
            output_dir=overview_output,
            model=endpoint.model,
            base_url=endpoint.base_url,
            api_key=endpoint.api_key_for(session_id),
            reasoning_effort=endpoint.reasoning_effort,
            session_id=session_id,
            message=(
                f"Summarize iteration {evidence.iteration} evidence collected "
                f"under harness h{evidence.generation}."
            ),
            context={
                "analysis_mode": "overview",
                "iteration": evidence.iteration,
                "generation": evidence.generation,
                "epoch": evidence.epoch,
                "batch_index": evidence.batch_index,
                "batch_task_ids": ",".join(evidence.task_ids),
                "detail_dir": str(detail_dir),
                "score_path": str(score_path),
                "same_task_history": same_task_history,
                "different_task_history": different_task_history,
                "previous_overview_path": (
                    str(previous_overview_path) if previous_overview_path is not None else ""
                ),
            },
            read_roots=_unique_resolved_paths(overview_read_roots),
            write_roots=(overview_output,),
            shell_root=overview_output,
        )
    write_text_atomic(overview_path, f"{result.rstrip()}\n")
    return overview_path


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run one isolated debugger worker.")
    parser.add_argument("--worker-spec", type=Path, required=True)
    args = parser.parse_args()
    run_debugger_worker(args.worker_spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
