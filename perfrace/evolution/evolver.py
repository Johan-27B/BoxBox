"""Host-local NexAU evolution step for one linear harness lineage."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from perfrace.evolution.meta import MetaAgentEndpoint, rotate_failed_output
from perfrace.evolution.nexau_runner import (
    run_nexau_agent,
    validate_nexau_output,
)
from perfrace.evolution.runtime_repository import (
    RuntimeRepository,
    RuntimeSnapshot,
)
from perfrace.evolution.state import write_model_atomic, write_text_atomic
from perfrace.evolution.types import ChangeManifest
from perfrace.evolution.loader import validate_harness_source


AGENT_CONFIG = Path(__file__).with_name("agents") / "evolve_agent.yaml"


@dataclass(frozen=True)
class EvolutionOutcome:
    """Validated result of one evolve-agent invocation."""

    snapshot: RuntimeSnapshot
    retained: bool
    manifest_path: Path
    result_path: Path


def _runtime_read_roots(runtime_path: Path) -> tuple[Path, ...]:
    """Expose the harness root; file tools reject controller-owned Git metadata."""
    return (runtime_path.resolve(),)


def _generation_evidence_roots(generation_dir: Path) -> tuple[Path, ...]:
    """Expose train evidence from completed generations, never held-out stages."""
    roots: list[Path] = []
    generations_root = generation_dir.parent
    current_name = generation_dir.name
    for candidate in sorted(generations_root.iterdir()):
        if not candidate.is_dir() or candidate.name > current_name:
            continue
        for name in ("train", "analysis", "evolve"):
            artifact_dir = candidate / name
            if artifact_dir.is_dir():
                roots.append(artifact_dir.resolve())
    return tuple(roots)


def _ensure_history_entry(
    history_path: Path,
    *,
    iteration: int,
    parent_generation: int,
    result_generation: int,
    parent_commit: str,
    snapshot: RuntimeSnapshot,
    overview_path: Path,
    manifest_path: Path,
    history_title: str,
) -> None:
    """Idempotently persist one lineage entry after outcome recovery."""
    heading = f"## Iteration {iteration}: h{parent_generation} -> h{result_generation}"
    text = (
        history_path.read_text(encoding="utf-8")
        if history_path.exists()
        else f"{history_title}\n"
    )
    if heading in text:
        return
    entry = (
        f"\n{heading}\n\n"
        f"- Parent harness: `h{parent_generation}` (`{parent_commit}`)\n"
        f"- Result harness: `h{result_generation}` (`{snapshot.commit}`)\n"
        f"- Outcome: `{'retained' if snapshot.commit == parent_commit else 'changed'}`\n"
        f"- Overview: `{overview_path}`\n"
        f"- Manifest: `{manifest_path}`\n"
    )
    write_text_atomic(history_path, f"{text.rstrip()}\n{entry}")


def run_evolver(
    *,
    repository: RuntimeRepository,
    experiment_root: Path,
    generation_dir: Path,
    iteration: int,
    parent_generation: int,
    parent_commit: str,
    overview_path: Path,
    detail_dir: Path,
    endpoint: MetaAgentEndpoint,
    extra_read_roots: tuple[Path, ...] = (),
    agent_config: Path = AGENT_CONFIG,
    message: str | None = None,
    history_title: str = "# Offline harness evolution history",
    task_id: str | None = None,
) -> EvolutionOutcome:
    """Run one evolve agent and validate its commit and change manifest."""
    head_before = repository.head_commit()
    output_dir = generation_dir / "evolve"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "change_manifest.json"
    result_path = output_dir / "result.md"
    outcome_path = output_dir / "outcome.json"
    completed_artifacts = manifest_path.is_file() and validate_nexau_output(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not completed_artifacts:
        if head_before != parent_commit or repository.worktree_changed_files():
            raise ValueError(f"Incomplete evolve artifacts changed Runtime HEAD: {output_dir}")
        rotate_failed_output(output_dir)
        output_dir.mkdir(parents=True)
        manifest_path = output_dir / "change_manifest.json"
        result_path = output_dir / "result.md"
        outcome_path = output_dir / "outcome.json"
    if not completed_artifacts:
        if head_before != parent_commit:
            raise ValueError("Runtime HEAD changed before the evolve agent started")
        repository.validate_head()
    history_path = experiment_root / "evolution_history.md"
    if not history_path.exists():
        history_path.write_text(f"{history_title}\n", encoding="utf-8")
    if not completed_artifacts:
        session_id = f"{endpoint.session_prefix}-evolve-i{iteration}-h{parent_generation}"
        read_roots = (
            *_runtime_read_roots(repository.path),
            *_generation_evidence_roots(generation_dir),
            history_path.resolve(),
            overview_path.resolve(),
            detail_dir.resolve(),
            output_dir.resolve(),
            *(path.resolve() for path in extra_read_roots),
        )
        run_nexau_agent(
            config_path=agent_config,
            workspace=repository.path,
            output_dir=output_dir,
            model=endpoint.model,
            base_url=endpoint.base_url,
            api_key=endpoint.api_key_for(session_id),
            reasoning_effort=endpoint.reasoning_effort,
            session_id=session_id,
            message=message or (
                f"Run iteration {iteration}: evolve the shared PerfRace harness "
                f"from h{parent_generation} to h{parent_generation + 1}."
            ),
            context={
                "iteration": iteration,
                "parent_generation": parent_generation,
                "result_generation": parent_generation + 1,
                "runtime_path": str(repository.path),
                "generation_dir": str(generation_dir),
                "history_path": str(history_path),
                "overview_path": str(overview_path),
                "detail_dir": str(detail_dir),
                "change_manifest_path": str(manifest_path),
                "parent_commit": parent_commit,
                "task_id": task_id,
            },
            read_roots=tuple(dict.fromkeys(read_roots)),
            write_roots=(repository.path, output_dir),
            shell_root=repository.path,
        )
    if not (manifest_path.is_file() and validate_nexau_output(output_dir)):
        raise ValueError(f"Evolve agent did not leave complete artifacts: {output_dir}")
    if not manifest_path.is_file():
        raise ValueError("Evolve agent did not write change_manifest.json")
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            raise ValueError("manifest root must be a JSON object")
        manifest = ChangeManifest.model_validate_json(
            json.dumps(
                {
                    **manifest_data,
                    "iteration": iteration,
                    "parent_commit": parent_commit,
                }
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid evolve change manifest: {exc}") from exc
    write_model_atomic(manifest_path, manifest)
    if outcome_path.is_file():
        outcome_data = json.loads(outcome_path.read_text(encoding="utf-8"))
        snapshot = repository.validate_head()
        if (
            outcome_data.get("iteration") != iteration
            or outcome_data.get("parent_generation") != parent_generation
            or outcome_data.get("result_generation") != parent_generation + 1
            or outcome_data.get("parent_commit") != parent_commit
            or outcome_data.get("result_commit") != snapshot.commit
            or bool(outcome_data.get("retained")) != (snapshot.commit == parent_commit)
        ):
            raise ValueError("Persisted evolve outcome does not match Runtime HEAD")
        changed_files = repository.changed_files(parent_commit, snapshot.commit)
        committed = True
    else:
        current_commit = repository.head_commit()
        if current_commit == parent_commit:
            changed_files = repository.worktree_changed_files()
            committed = False
        else:
            if repository.worktree_changed_files():
                raise ValueError("Runtime has both committed and uncommitted evolve changes")
            snapshot = repository.validate_head()
            changed_files = repository.changed_files(parent_commit, snapshot.commit)
            committed = True
    invalid_files = tuple(
        path
        for path in changed_files
        if Path(path).is_absolute()
        or any(part in {".git", ".gitattributes", ".."} for part in Path(path).parts)
    )
    if invalid_files:
        raise ValueError(
            "Offline runtime changed files outside the evolvable target harness: "
            f"{invalid_files!r}"
        )
    declared_files = tuple(sorted({file for change in manifest.changes for file in change.files}))
    if not changed_files and manifest.changes:
        raise ValueError("Retained runtime must declare an empty changes list")
    if changed_files and not manifest.changes:
        raise ValueError("Changed runtime must declare at least one manifest change")
    if tuple(sorted(changed_files)) != declared_files:
        raise ValueError(
            "Change manifest files do not match committed runtime diff: "
            f"declared={declared_files!r} actual={tuple(sorted(changed_files))!r}"
        )
    validated = False
    try:
        if committed:
            repository.validate_commit_entries(snapshot.commit)
        else:
            repository.validate_worktree_entries()
        validate_harness_source(
            repository.path,
            identity=(snapshot.commit if committed else f"{parent_commit}-candidate"),
        )
        validated = True
    finally:
        if not validated:
            repository.restore(parent_commit)
            if output_dir.exists():
                rotate_failed_output(output_dir)
    if not outcome_path.is_file():
        if not committed:
            snapshot = (
                repository.commit_worktree(f"iteration {iteration}: offline harness evolution")
                if changed_files
                else repository.validate_head()
            )
        committed_valid = False
        try:
            repository.validate_commit_entries(snapshot.commit)
            with tempfile.TemporaryDirectory(
                prefix="perfrace-runtime-commit-validation-"
            ) as directory:
                materialized = Path(directory) / "runtime"
                repository.materialize(snapshot.commit, materialized)
                validate_harness_source(
                    materialized,
                    identity=snapshot.commit,
                )
            committed_valid = True
        finally:
            if not committed_valid:
                repository.restore(parent_commit)
                if output_dir.exists():
                    rotate_failed_output(output_dir)
        write_text_atomic(
            outcome_path,
            json.dumps(
                {
                    "schema_version": 1,
                    "iteration": iteration,
                    "parent_generation": parent_generation,
                    "result_generation": parent_generation + 1,
                    "parent_commit": parent_commit,
                    "result_commit": snapshot.commit,
                    "retained": snapshot.commit == parent_commit,
                },
                indent=2,
            )
            + "\n",
        )
    _ensure_history_entry(
        history_path,
        iteration=iteration,
        parent_generation=parent_generation,
        result_generation=parent_generation + 1,
        parent_commit=parent_commit,
        snapshot=snapshot,
        overview_path=overview_path,
        manifest_path=manifest_path,
        history_title=history_title,
    )
    return EvolutionOutcome(
        snapshot=snapshot,
        retained=snapshot.commit == parent_commit,
        manifest_path=manifest_path,
        result_path=result_path,
    )
