import hashlib
import json
from pathlib import Path

from perfrace.evolution import evolver
from perfrace.evolution.meta import MetaAgentEndpoint
from perfrace.evolution.runtime_repository import RuntimeRepository


def _write_complete_marker(output_dir: Path) -> None:
    result_path = output_dir / "result.md"
    trajectory_path = output_dir / "trajectory.json"
    output_dir.joinpath("complete.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                "trajectory_sha256": hashlib.sha256(trajectory_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )




def test_run_evolver_validates_committed_change_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    (source / "kernel").mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "kernel" / "contract.py").write_text(
        "KERNEL = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "experiment" / "runtime")
    monkeypatch.setattr(evolver, "validate_harness_source", lambda *args, **kwargs: object)
    agent_call = {}

    def fake_run_nexau_agent(**kwargs):
        agent_call.update(kwargs)
        runtime = repository.path / "runtime.py"
        runtime.write_text("VALUE = 2\n", encoding="utf-8")
        manifest = {
            "schema_version": 2,
            "iteration": kwargs["context"]["iteration"],
            "parent_commit": kwargs["context"]["parent_commit"],
            "changes": [
                {
                    "id": "chg-1",
                    "type": "improvement",
                    "description": "Change the runtime value.",
                    "files": ["runtime.py"],
                    "evidence": ["analysis/overview.md"],
                    "behavior_pattern": "Repeated test behavior.",
                    "predicted_benefits": ["Exercise changed runtime handling."],
                    "regression_risks": ["Value may be incorrect."],
                    "component": "control",
                }
            ],
        }
        Path(kwargs["context"]["change_manifest_path"]).write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        kwargs["output_dir"].joinpath("result.md").write_text("changed\n", encoding="utf-8")
        kwargs["output_dir"].joinpath("trajectory.json").write_text(
            "[]\n",
            encoding="utf-8",
        )
        _write_complete_marker(kwargs["output_dir"])
        return "changed"

    monkeypatch.setattr(evolver, "run_nexau_agent", fake_run_nexau_agent)
    endpoint = MetaAgentEndpoint(
        base_url="http://127.0.0.1:4000/v1",
        token_proxy_secret="secret",
        model="test-model",
        reasoning_effort="high",
        session_prefix="demo",
    )
    generation_dir = tmp_path / "experiment" / "generations" / "0000"
    completed_job_dir = tmp_path / "jobs" / "train-i1-h0"
    completed_job_dir.mkdir(parents=True)

    outcome = evolver.run_evolver(
        repository=repository,
        experiment_root=tmp_path / "experiment",
        generation_dir=generation_dir,
        iteration=1,
        parent_generation=0,
        parent_commit=repository.validate_head().commit,
        overview_path=generation_dir / "analysis" / "overview.md",
        detail_dir=generation_dir / "analysis" / "detail",
        endpoint=endpoint,
        extra_read_roots=(completed_job_dir,),
    )

    assert outcome.retained is False
    assert repository.path.joinpath("runtime.py").read_text() == "VALUE = 2\n"
    history = (tmp_path / "experiment" / "evolution_history.md").read_text()
    assert "## Iteration 1: h0 -> h1" in history
    assert "Outcome: `changed`" in history
    assert agent_call["workspace"] == repository.path
    assert (tmp_path / "experiment").resolve() not in agent_call["read_roots"]
    assert repository.path.resolve() in agent_call["read_roots"]
    assert (repository.path / ".git").resolve() not in agent_call["read_roots"]
    assert (repository.path / "kernel").resolve() not in agent_call[
        "read_roots"
    ]
    assert (generation_dir / "evolve").resolve() in agent_call["read_roots"]
    assert completed_job_dir.resolve() in agent_call["read_roots"]


def test_run_evolver_reuses_completed_retained_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    (source / "kernel").mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "kernel" / "contract.py").write_text(
        "KERNEL = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "experiment" / "runtime")
    monkeypatch.setattr(evolver, "validate_harness_source", lambda *args, **kwargs: object)
    parent_commit = repository.validate_head().commit
    calls = 0

    def fake_run_nexau_agent(**kwargs):
        nonlocal calls
        calls += 1
        manifest = {
            "schema_version": 2,
            "iteration": 999,
            "parent_commit": "mistyped",
            "changes": [],
        }
        Path(kwargs["context"]["change_manifest_path"]).write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        kwargs["output_dir"].joinpath("result.md").write_text("retained\n", encoding="utf-8")
        kwargs["output_dir"].joinpath("trajectory.json").write_text(
            "[]\n",
            encoding="utf-8",
        )
        _write_complete_marker(kwargs["output_dir"])
        return "retained"

    monkeypatch.setattr(evolver, "run_nexau_agent", fake_run_nexau_agent)
    endpoint = MetaAgentEndpoint(
        base_url="http://127.0.0.1:4000/v1",
        token_proxy_secret="secret",
        model="test-model",
        reasoning_effort="high",
        session_prefix="demo",
    )
    arguments = {
        "repository": repository,
        "experiment_root": tmp_path / "experiment",
        "generation_dir": tmp_path / "experiment" / "generations" / "0000",
        "iteration": 1,
        "parent_generation": 0,
        "parent_commit": parent_commit,
        "overview_path": tmp_path / "overview.md",
        "detail_dir": tmp_path / "detail",
        "endpoint": endpoint,
    }

    first = evolver.run_evolver(**arguments)
    second = evolver.run_evolver(**arguments)

    assert first.retained is True
    assert second == first
    assert calls == 1
    manifest = json.loads(
        (arguments["generation_dir"] / "evolve" / "change_manifest.json").read_text()
    )
    assert manifest["iteration"] == 1
    assert manifest["parent_commit"] == parent_commit
    assert (tmp_path / "experiment" / "evolution_history.md").read_text().count(
        "## Iteration 1: h0 -> h1"
    ) == 1


def test_run_evolver_finishes_controller_commit_without_outcome_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    (source / "kernel").mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "kernel" / "contract.py").write_text(
        "KERNEL = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "experiment" / "runtime")
    parent_commit = repository.validate_head().commit
    repository.path.joinpath("runtime.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )
    successor = repository.commit_worktree("iteration 1: offline harness evolution")
    generation_dir = tmp_path / "experiment" / "generations" / "0000"
    output_dir = generation_dir / "evolve"
    output_dir.mkdir(parents=True)
    output_dir.joinpath("change_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "iteration": 1,
                "parent_commit": parent_commit,
                "changes": [
                    {
                        "id": "chg-1",
                        "type": "improvement",
                        "description": "Change the runtime value.",
                        "files": ["runtime.py"],
                        "evidence": ["analysis/overview.md"],
                        "behavior_pattern": "Repeated test behavior.",
                        "predicted_benefits": ["Exercise resume handling."],
                        "regression_risks": ["Value may be incorrect."],
                        "component": "control",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir.joinpath("result.md").write_text("changed\n", encoding="utf-8")
    output_dir.joinpath("trajectory.json").write_text("[]\n", encoding="utf-8")
    _write_complete_marker(output_dir)
    monkeypatch.setattr(
        evolver,
        "run_nexau_agent",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("agent reran")),
    )
    monkeypatch.setattr(evolver, "validate_harness_source", lambda *args, **kwargs: object)
    endpoint = MetaAgentEndpoint(
        base_url="http://127.0.0.1:4000/v1",
        token_proxy_secret="secret",
        model="test-model",
        reasoning_effort="high",
        session_prefix="demo",
    )

    outcome = evolver.run_evolver(
        repository=repository,
        experiment_root=tmp_path / "experiment",
        generation_dir=generation_dir,
        iteration=1,
        parent_generation=0,
        parent_commit=parent_commit,
        overview_path=generation_dir / "analysis" / "overview.md",
        detail_dir=generation_dir / "analysis" / "detail",
        endpoint=endpoint,
    )

    assert outcome.snapshot.commit == successor.commit
    assert output_dir.joinpath("outcome.json").is_file()
    history = tmp_path / "experiment" / "evolution_history.md"
    history.unlink()
    resumed = evolver.run_evolver(
        repository=repository,
        experiment_root=tmp_path / "experiment",
        generation_dir=generation_dir,
        iteration=1,
        parent_generation=0,
        parent_commit=parent_commit,
        overview_path=generation_dir / "analysis" / "overview.md",
        detail_dir=generation_dir / "analysis" / "detail",
        endpoint=endpoint,
    )
    assert resumed == outcome
    assert "## Iteration 1: h0 -> h1" in history.read_text()
