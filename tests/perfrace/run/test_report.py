from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml
from harbor.models.job.config import JobConfig

from perfrace.run.config import LoadedRun
from perfrace.run.report import NOP_AGENT_NAME, write_run_artifacts
from perfrace.run.verifier import MEASUREMENT_FILENAME


def _loaded_run(
    *,
    submission_path: Path | None = None,
    enable_cache: bool = False,
    note: str | None = None,
    agent_tag: str | None = None,
) -> LoadedRun:
    job = JobConfig.model_validate(
        {
            "jobs_dir": "data/jobs",
            "tasks": [{"path": "instances/harness-v0/demo"}],
            "agents": [],
        }
    )
    return LoadedRun(
        job=job,
        api_gateway=None,
        submission_path=submission_path,
        enable_cache=enable_cache,
        note=note,
        agent_tag=agent_tag,
    )


def _trial_result(
    *,
    task_name: str,
    trial_name: str,
    agent_name: str,
    task_dir: Path,
) -> SimpleNamespace:
    trial_dir = task_dir.parent / f"trial-{trial_name}"
    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        task_name=task_name,
        trial_name=trial_name,
        trial_uri=trial_dir.resolve().as_uri(),
        agent_info=SimpleNamespace(name=agent_name),
        task_id=SimpleNamespace(get_local_path=lambda: task_dir),
    )


def _write_trial_report(
    trial_result: SimpleNamespace, *, value: int, correct: bool = True
) -> None:
    verifier_dir = Path(trial_result.trial_uri.removeprefix("file://")) / "verifier"
    (verifier_dir / MEASUREMENT_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "verdict": "ACCEPTED" if correct else "WRONG_ANSWER",
                "metric": "wall-clock",
                "unit": "seconds",
                "value": value,
                "details": {},
            }
        )
    )


def _task_dir(tmp_path: Path, name: str, *, direction: str = "minimize") -> Path:
    task_dir = tmp_path / name
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        f"""
[perfrace.measurement]
measurement = "wall-clock"
direction = "{direction}"
unit = "seconds"
"""
    )
    return task_dir


def _checkpoint_trial_result(
    *,
    task_name: str,
    trial_name: str,
    agent_name: str,
    task_dir: Path,
    step_names: list[str],
) -> SimpleNamespace:
    """Build a trial result shaped like a multi-checkpoint trial
    (PerfRace's own CheckpointTrial): a step_results list, with each
    checkpoint's own result archived under
    checkpoints/<name>/verifier/measurement.json."""
    trial_dir = task_dir.parent / f"trial-{trial_name}"
    (trial_dir / "verifier").mkdir(parents=True, exist_ok=True)
    step_results = []
    for step_name in step_names:
        (trial_dir / "checkpoints" / step_name / "verifier").mkdir(parents=True, exist_ok=True)
        step_results.append(
            SimpleNamespace(step_name=step_name, verifier_result=SimpleNamespace(rewards=None))
        )
    return SimpleNamespace(
        task_name=task_name,
        trial_name=trial_name,
        trial_uri=trial_dir.resolve().as_uri(),
        agent_info=SimpleNamespace(name=agent_name),
        task_id=SimpleNamespace(get_local_path=lambda: task_dir),
        step_results=step_results,
    )


def _write_checkpoint_trial_report(
    trial_result: SimpleNamespace, *, step_name: str, value: int, correct: bool = True
) -> None:
    verifier_dir = (
        Path(trial_result.trial_uri.removeprefix("file://"))
        / "checkpoints"
        / step_name
        / "verifier"
    )
    (verifier_dir / MEASUREMENT_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "verdict": "ACCEPTED" if correct else "WRONG_ANSWER",
                "metric": "wall-clock",
                "unit": "seconds",
                "value": value,
                "details": {},
            }
        )
    )


def test_write_run_artifacts_selects_best_checkpoint_for_multi_checkpoint_trials(
    tmp_path: Path,
) -> None:
    """A candidate headline uses its best correctness-passing checkpoint."""
    task_dir = _task_dir(tmp_path, "task-multi-checkpoint", direction="minimize")
    baseline = _checkpoint_trial_result(
        task_name="task-multi-checkpoint",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
        step_names=["checkpoint-01", "checkpoint-02"],
    )
    candidate = _checkpoint_trial_result(
        task_name="task-multi-checkpoint",
        trial_name="candidate",
        agent_name="copilot-cli",
        task_dir=task_dir,
        step_names=["checkpoint-01", "checkpoint-02"],
    )
    _write_checkpoint_trial_report(baseline, step_name="checkpoint-01", value=100)
    _write_checkpoint_trial_report(baseline, step_name="checkpoint-02", value=100)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-01", value=90)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-02", value=80)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [task_entry] = summary["tasks"]
    # The baseline retains its last checkpoint, while the minimizing candidate
    # selects its lowest accepted value.
    assert task_entry["baseline"]["perf_trial"]["value"] == 100
    [candidate_entry] = task_entry["candidates"]
    assert candidate_entry["perf_trial"]["value"] == 80
    assert candidate_entry["reward"] == 1.25


def test_write_run_artifacts_selects_highest_checkpoint_for_maximize_task(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-maximize", direction="maximize")
    baseline = _trial_result(
        task_name="task-maximize",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _checkpoint_trial_result(
        task_name="task-maximize",
        trial_name="candidate",
        agent_name="terminus-boxbox",
        task_dir=task_dir,
        step_names=["checkpoint-01", "checkpoint-02", "final-delivery"],
    )
    _write_trial_report(baseline, value=100)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-01", value=110)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-02", value=140)
    _write_checkpoint_trial_report(candidate, step_name="final-delivery", value=120)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["value"] == 140
    assert candidate_entry["reward"] == 1.4


def test_write_run_artifacts_keeps_correct_regression_below_one(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-regression", direction="minimize")
    baseline = _trial_result(
        task_name="task-regression",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _checkpoint_trial_result(
        task_name="task-regression",
        trial_name="candidate",
        agent_name="terminus-boxbox",
        task_dir=task_dir,
        step_names=["checkpoint-01", "final-delivery"],
    )
    _write_trial_report(baseline, value=100)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-01", value=125)
    _write_checkpoint_trial_report(candidate, step_name="final-delivery", value=150)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["value"] == 125
    assert candidate_entry["reward"] == 0.8


def test_write_run_artifacts_falls_back_to_last_checkpoint_even_without_verifier_result(
    tmp_path: Path,
) -> None:
    """A checkpoint whose agent phase timed out never gets a
    verifier_result recorded on its StepResult (see
    CheckpointTrial._run()'s except asyncio.TimeoutError branch not
    overwriting an already-set exception_info) even though
    PerfRaceVerifier.verify() still wrote a placeholder measurement.json
    for it (e.g. verdict=TIMEOUT) before being cancelled. The fallback must
    resolve from the file's existence, not verifier_result."""
    task_dir = _task_dir(
        tmp_path, "task-multi-checkpoint-no-verifier-result", direction="minimize"
    )
    candidate = _checkpoint_trial_result(
        task_name="task-multi-checkpoint-no-verifier-result",
        trial_name="candidate",
        agent_name="copilot-cli",
        task_dir=task_dir,
        step_names=["checkpoint-01"],
    )
    candidate.step_results[0].verifier_result = None
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-01", value=None, correct=False)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job-2"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [task_entry] = summary["tasks"]
    [candidate_entry] = task_entry["candidates"]
    assert candidate_entry["perf_trial"]["value"] is None
    assert candidate_entry.get("error") is None


def test_write_run_artifacts_uses_neutral_reward_when_no_checkpoint_is_selectable(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-all-failed-checkpoints", direction="minimize")
    baseline = _trial_result(
        task_name="task-all-failed-checkpoints",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _checkpoint_trial_result(
        task_name="task-all-failed-checkpoints",
        trial_name="candidate",
        agent_name="terminus-boxbox",
        task_dir=task_dir,
        step_names=["checkpoint-01", "final-delivery"],
    )
    _write_trial_report(baseline, value=100)
    _write_checkpoint_trial_report(
        candidate,
        step_name="checkpoint-01",
        value=None,
        correct=False,
    )
    _write_checkpoint_trial_report(
        candidate,
        step_name="final-delivery",
        value=None,
        correct=False,
    )

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["verdict"] == "WRONG_ANSWER"
    assert candidate_entry["reward"] == 1.0


def test_write_run_artifacts_keeps_single_step_wrong_answer_at_zero(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-single-step-failure", direction="minimize")
    baseline = _trial_result(
        task_name="task-single-step-failure",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _trial_result(
        task_name="task-single-step-failure",
        trial_name="candidate",
        agent_name="copilot",
        task_dir=task_dir,
    )
    _write_trial_report(baseline, value=100)
    _write_trial_report(candidate, value=None, correct=False)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["verdict"] == "WRONG_ANSWER"
    assert candidate_entry["reward"] == 0.0


def test_write_run_artifacts_uses_last_valid_measurement_after_later_failure(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-failed-final-checkpoint", direction="minimize")
    baseline = _trial_result(
        task_name="task-failed-final-checkpoint",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _checkpoint_trial_result(
        task_name="task-failed-final-checkpoint",
        trial_name="candidate",
        agent_name="autoresearch-terminus-kira",
        task_dir=task_dir,
        step_names=["transaction-01", "transaction-02", "transaction-03"],
    )
    _write_trial_report(baseline, value=100)
    _write_checkpoint_trial_report(candidate, step_name="transaction-01", value=80)
    _write_checkpoint_trial_report(candidate, step_name="transaction-02", value=50)
    _write_checkpoint_trial_report(
        candidate,
        step_name="transaction-03",
        value=None,
        correct=False,
    )

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=1),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["verdict"] == "ACCEPTED"
    assert candidate_entry["perf_trial"]["value"] == 50
    assert candidate_entry["reward"] == 2.0


def test_write_run_artifacts_uses_earlier_best_when_final_delivery_fails(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-failed-final-delivery", direction="minimize")
    baseline = _trial_result(
        task_name="task-failed-final-delivery",
        trial_name="baseline",
        agent_name=NOP_AGENT_NAME,
        task_dir=task_dir,
    )
    candidate = _checkpoint_trial_result(
        task_name="task-failed-final-delivery",
        trial_name="candidate",
        agent_name="autoresearch-terminus-kira",
        task_dir=task_dir,
        step_names=["checkpoint-01", "final-delivery"],
    )
    _write_trial_report(baseline, value=100)
    _write_checkpoint_trial_report(candidate, step_name="checkpoint-01", value=50)
    _write_checkpoint_trial_report(
        candidate,
        step_name="final-delivery",
        value=None,
        correct=False,
    )

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [candidate_entry] = summary["tasks"][0]["candidates"]
    assert candidate_entry["perf_trial"]["verdict"] == "ACCEPTED"
    assert candidate_entry["perf_trial"]["value"] == 50
    assert candidate_entry["reward"] == 2.0


def test_write_run_artifacts_pairs_baseline_and_candidate_and_computes_reward(
    tmp_path: Path,
) -> None:
    task_dir = _task_dir(tmp_path, "task-a", direction="minimize")
    baseline = _trial_result(
        task_name="task-a", trial_name="baseline", agent_name=NOP_AGENT_NAME, task_dir=task_dir
    )
    candidate = _trial_result(
        task_name="task-a", trial_name="candidate", agent_name="copilot", task_dir=task_dir
    )
    _write_trial_report(baseline, value=100)
    _write_trial_report(candidate, value=80)

    loaded = _loaded_run(note="my note", agent_tag="my-tag")
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[baseline, candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == 2
    assert summary["job_name"] == "demo-job"
    assert summary["note"] == "my note"
    assert summary["agent_tag"] == "my-tag"
    assert summary["enable_cache"] is False
    assert summary["used_api_gateway"] is False
    assert summary["trial_count"] == 2
    assert "git_commit" in summary

    [task_entry] = summary["tasks"]
    assert task_entry["task_name"] == "task-a"
    assert task_entry["baseline"]["perf_trial"]["value"] == 100
    [candidate_entry] = task_entry["candidates"]
    assert candidate_entry["agent"] == "copilot"
    assert candidate_entry["reward"] == 1.25

    job_yaml_data = yaml.safe_load((run_dir / "job.yaml").read_text(encoding="utf-8"))
    assert "verifier" not in job_yaml_data
    assert job_yaml_data["tasks"][0]["path"].endswith("harness-v0/demo")


def test_write_run_artifacts_skips_reward_without_baseline(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path, "task-b")
    candidate = _trial_result(
        task_name="task-b", trial_name="candidate", agent_name="copilot", task_dir=task_dir
    )
    _write_trial_report(candidate, value=80)

    loaded = _loaded_run()
    job = loaded.job.model_copy(update={"jobs_dir": tmp_path / "jobs", "job_name": "demo-job"})
    job_result = SimpleNamespace(
        stats=SimpleNamespace(n_errored_trials=0),
        trial_results=[candidate],
    )

    run_dir = write_run_artifacts(loaded, job, job_result)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    [task_entry] = summary["tasks"]
    assert task_entry["baseline"] is None
    [candidate_entry] = task_entry["candidates"]
    assert candidate_entry["reward"] is None
