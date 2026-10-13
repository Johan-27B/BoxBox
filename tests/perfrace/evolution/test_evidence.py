from pathlib import Path

from perfrace.evolution.evidence import build_generation_evidence
from perfrace.evolution.types import TrainBatch
from perfrace.run.types import RunSummary


def test_build_generation_evidence_indexes_raw_trial_artifacts(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    run_dir = job_dir / "perfrace"
    selected = run_dir / "trials" / "0001-candidate.measurement.json"
    selected.parent.mkdir(parents=True)
    selected.write_text("{}\n", encoding="utf-8")
    trial_dir = job_dir / "candidate"
    checkpoint = trial_dir / "checkpoints" / "checkpoint-01"
    (checkpoint / "verifier").mkdir(parents=True)
    (checkpoint / "verifier" / "measurement.json").write_text("{}\n", encoding="utf-8")
    (checkpoint / "agent").mkdir()
    (checkpoint / "agent" / "trajectory.json").write_text("{}\n", encoding="utf-8")
    summary = RunSummary.model_validate(
        {
            "job_name": "train",
            "enable_cache": True,
            "used_api_gateway": True,
            "trial_count": 2,
            "tasks": [
                {
                    "task_name": "task-a",
                    "baseline": None,
                    "candidates": [
                        {
                            "trial_name": "candidate",
                            "agent": "offline-harness",
                            "trial_uri": trial_dir.resolve().as_uri(),
                            "artifact": "trials/0001-candidate.measurement.json",
                            "reward": 1.5,
                        }
                    ],
                }
            ],
        }
    )
    run_summary_path = run_dir / "run.json"
    run_summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    evidence = build_generation_evidence(
        run_summary_path,
        batch=TrainBatch(
            generation=2,
            epoch=1,
            batch_index=2,
            task_ids=("task-a",),
        ),
        harness_generation=1,
        train_schedule_sha256="a" * 64,
        expected_attempts=1,
    )

    assert evidence.iteration == 2
    assert evidence.generation == 1
    assert evidence.epoch == 1
    assert evidence.batch_index == 2
    assert evidence.task_ids == ("task-a",)
    [task] = evidence.tasks
    [attempt] = task.attempts
    assert task.task_name == "task-a"
    assert attempt.reward == 1.5
    assert attempt.selected_measurement == selected.resolve()
    assert attempt.checkpoint_measurements == (
        (checkpoint / "verifier" / "measurement.json").resolve(),
    )
    assert attempt.trajectories == ((checkpoint / "agent" / "trajectory.json").resolve(),)
