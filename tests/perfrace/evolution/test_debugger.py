import hashlib
import json
import threading
import time
from pathlib import Path

from perfrace.evolution import debugger
from perfrace.evolution.meta import MetaAgentEndpoint
from perfrace.evolution.state import read_model, write_model_atomic
from perfrace.evolution.types import (
    AttemptEvidence,
    DebuggerWorkerSpec,
    GenerationEvidence,
    TaskEvidence,
)
from perfrace.run.services.session_identity import decode_token_proxy_api_key


def test_run_generation_debugger_is_resumable_and_builds_overview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    attempt_a = AttemptEvidence(
        trial_name="trial-a",
        reward=1.0,
        trial_dir=tmp_path / "trial-a",
        selected_measurement=tmp_path / "trial-a" / "measurement.json",
    )
    attempt_b = AttemptEvidence(
        trial_name="trial-b",
        reward=1.0,
        trial_dir=tmp_path / "trial-b",
        selected_measurement=tmp_path / "trial-b" / "measurement.json",
    )
    write_model_atomic(
        evidence_path,
        GenerationEvidence(
            iteration=2,
            generation=1,
            epoch=1,
            batch_index=2,
            task_ids=("instance-a", "instance-b"),
            train_schedule_sha256="a" * 64,
            run_summary_path=tmp_path / "run.json",
            tasks=(
                TaskEvidence(task_name="task-a", attempts=(attempt_a,)),
                TaskEvidence(task_name="task-b", attempts=(attempt_b,)),
            ),
        ),
    )
    calls = []

    def fake_run_nexau_agent(**kwargs):
        calls.append(kwargs)
        kwargs["output_dir"].mkdir(parents=True, exist_ok=True)
        result = f"report-{len(calls)}"
        kwargs["output_dir"].joinpath("result.md").write_text(
            f"{result}\n",
            encoding="utf-8",
        )
        kwargs["output_dir"].joinpath("trajectory.json").write_text(
            "[]\n",
            encoding="utf-8",
        )
        result_path = kwargs["output_dir"] / "result.md"
        trajectory_path = kwargs["output_dir"] / "trajectory.json"
        kwargs["output_dir"].joinpath("complete.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                    "trajectory_sha256": hashlib.sha256(trajectory_path.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        return result

    def fake_run_worker(spec_path, api_key):
        spec = read_model(spec_path, DebuggerWorkerSpec)
        fake_run_nexau_agent(
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

    monkeypatch.setattr(debugger, "_run_worker_process", fake_run_worker)
    monkeypatch.setattr(debugger, "run_nexau_agent", fake_run_nexau_agent)
    endpoint = MetaAgentEndpoint(
        base_url="http://127.0.0.1:4000/v1",
        token_proxy_secret="secret",
        model="test-model",
        reasoning_effort="high",
        session_prefix="demo",
    )

    first = debugger.run_generation_debugger(
        evidence_path=evidence_path,
        score_path=tmp_path / "score.json",
        experiment_root=tmp_path,
        output_dir=tmp_path / "analysis",
        endpoint=endpoint,
        previous_overview_path=None,
        max_workers=2,
    )
    second = debugger.run_generation_debugger(
        evidence_path=evidence_path,
        score_path=tmp_path / "score.json",
        experiment_root=tmp_path,
        output_dir=tmp_path / "analysis",
        endpoint=endpoint,
        previous_overview_path=None,
        max_workers=2,
    )

    assert first == second
    assert first.read_text() == "report-3\n"
    assert len(calls) == 3
    assert calls[-1]["context"]["analysis_mode"] == "overview"
    assert {
        decode_token_proxy_api_key(call["api_key"], secret="secret")[0] for call in calls[:2]
    } == {
        "demo-debug-i2-h1-task-a",
        "demo-debug-i2-h1-task-b",
    }
    specs = sorted((tmp_path / "analysis" / "worker-specs").glob("*.json"))
    assert len(specs) == 2
    assert all("secret" not in path.read_text(encoding="utf-8") for path in specs)
    assert decode_token_proxy_api_key(calls[0]["api_key"], secret="secret")[1] == "test-model"
    task_calls = {
        call["context"]["task_name"]: call
        for call in calls
        if call["context"]["analysis_mode"] == "task"
    }
    for call in task_calls.values():
        assert call["workspace"] == call["output_dir"]
        assert tmp_path.resolve() not in call["read_roots"]
        assert evidence_path.resolve() in call["read_roots"]
        assert call["output_dir"].resolve() in call["read_roots"]
    assert (tmp_path / "trial-a").resolve() in task_calls["task-a"]["read_roots"]
    assert (tmp_path / "trial-b").resolve() not in task_calls["task-a"]["read_roots"]
    assert (tmp_path / "trial-b").resolve() in task_calls["task-b"]["read_roots"]
    assert (tmp_path / "trial-a").resolve() not in task_calls["task-b"]["read_roots"]
    assert calls[-1]["workspace"] == calls[-1]["output_dir"]
    assert tmp_path.resolve() not in calls[-1]["read_roots"]
    assert (tmp_path / "analysis" / "detail").resolve() in calls[-1]["read_roots"]
    assert (tmp_path / "score.json").resolve() in calls[-1]["read_roots"]


def test_historical_overview_inputs_separate_paired_and_unpaired_tasks(
    tmp_path: Path,
) -> None:
    generations_root = tmp_path / "generations"

    def write_evidence(
        generation: int,
        iteration: int,
        task_names: tuple[str, ...],
    ) -> Path:
        path = generations_root / f"{generation:04d}" / "train" / "evidence.json"
        write_model_atomic(
            path,
            GenerationEvidence(
                iteration=iteration,
                generation=generation,
                epoch=1,
                batch_index=iteration,
                task_ids=tuple(f"id-{task_name}" for task_name in task_names),
                train_schedule_sha256="a" * 64,
                run_summary_path=path.with_name("run.json"),
                tasks=tuple(
                    TaskEvidence(task_name=task_name, attempts=()) for task_name in task_names
                ),
            ),
        )
        overview = path.parents[1] / "analysis" / "overview.md"
        overview.parent.mkdir(parents=True)
        overview.write_text("overview\n", encoding="utf-8")
        return path

    first = write_evidence(0, 1, ("task-a", "task-c"))
    second = write_evidence(1, 2, ("task-d",))
    current = GenerationEvidence(
        iteration=3,
        generation=2,
        epoch=2,
        batch_index=1,
        task_ids=("id-task-a", "id-task-b"),
        train_schedule_sha256="a" * 64,
        run_summary_path=tmp_path / "current.json",
        tasks=(
            TaskEvidence(task_name="task-a", attempts=()),
            TaskEvidence(task_name="task-b", attempts=()),
        ),
    )

    roots, same_task_history, different_task_history = debugger._historical_overview_inputs(
        tmp_path, current
    )

    assert first.resolve() in roots
    assert second.resolve() in roots
    assert same_task_history == "task-a:i1"
    assert different_task_history == "i1,i2"


def test_debugger_worker_pool_waits_for_active_workers_and_skips_pending_after_failure(
    tmp_path: Path, monkeypatch
) -> None:
    barrier = threading.Barrier(2)
    started: list[str] = []
    settled: list[str] = []

    def fake_worker(spec_path: Path, api_key: str) -> None:
        started.append(spec_path.name)
        barrier.wait(timeout=2)
        if spec_path.name == "a.json":
            raise RuntimeError("boom")
        time.sleep(0.05)
        settled.append(spec_path.name)

    monkeypatch.setattr(debugger, "_run_worker_process", fake_worker)
    workers = [
        (tmp_path / "a.json", "key-a"),
        (tmp_path / "b.json", "key-b"),
        (tmp_path / "c.json", "key-c"),
    ]

    try:
        debugger._run_worker_pool(workers, max_workers=2)
    except RuntimeError as exc:
        assert "after active workers settled" in str(exc)
    else:
        raise AssertionError("expected debugger pool failure")

    assert set(started) == {"a.json", "b.json"}
    assert settled == ["b.json"]
