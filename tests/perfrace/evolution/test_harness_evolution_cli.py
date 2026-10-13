from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from perfrace.evolution import cli
from perfrace.evolution.types import EvolutionStage


def test_evolve_harness_dry_run_prints_plan_without_preparing_experiment(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    loaded = SimpleNamespace(config=SimpleNamespace(protocol=SimpleNamespace(generations=24)))
    plan = MagicMock()
    plan.model_dump.return_value = {"experiment_name": "demo"}
    prepare = MagicMock()
    monkeypatch.setattr(cli, "load_harness_evolution_config", lambda path: loaded)
    monkeypatch.setattr(cli, "resolve_evolution_plan", lambda value: plan)
    monkeypatch.setattr(cli, "prepare_experiment", prepare)

    exit_code = cli.evolve_harness_command(
        config=tmp_path / "config.yaml",
        dry_run=True,
        resume=False,
        iterations=8,
    )

    assert exit_code == 0
    assert '"requested_iterations": 8' in capsys.readouterr().out
    prepare.assert_not_called()


def test_evolve_harness_completed_resume_does_not_start_gateway(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    loaded = SimpleNamespace(config=SimpleNamespace(protocol=SimpleNamespace(generations=24)))
    prepared = SimpleNamespace(
        plan=SimpleNamespace(generations=24),
        paths=tmp_path,
        state=SimpleNamespace(
            experiment_name="demo",
            stage=EvolutionStage.COMPLETE,
            active_generation=24,
            selection_path=tmp_path / "selection.json",
        ),
    )
    gateway = MagicMock()
    validate = MagicMock()
    usage = MagicMock()
    monkeypatch.setattr(cli, "load_harness_evolution_config", lambda path: loaded)
    monkeypatch.setattr(
        cli,
        "prepare_experiment",
        lambda value, resume: prepared,
    )
    monkeypatch.setattr(cli, "run_gateway", gateway)
    monkeypatch.setattr(cli, "validate_completed_experiment", validate)
    monkeypatch.setattr(cli, "write_usage_report", usage)

    exit_code = cli.evolve_harness_command(
        config=tmp_path / "config.yaml",
        dry_run=False,
        resume=True,
        iterations=24,
    )

    assert exit_code == 0
    assert '"stage": "complete"' in capsys.readouterr().out
    gateway.assert_not_called()
    validate.assert_called_once_with(prepared)
    usage.assert_called_once()


def test_evolve_harness_repeated_iteration_target_does_not_start_gateway(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    loaded = SimpleNamespace(config=SimpleNamespace(protocol=SimpleNamespace(generations=24)))
    prepared = SimpleNamespace(
        plan=SimpleNamespace(generations=24),
        paths=tmp_path,
        state=SimpleNamespace(
            experiment_name="demo",
            stage=EvolutionStage.TRAINING,
            active_generation=8,
            selection_path=None,
        ),
    )
    gateway = MagicMock()
    usage = MagicMock()
    monkeypatch.setattr(cli, "load_harness_evolution_config", lambda path: loaded)
    monkeypatch.setattr(cli, "prepare_experiment", lambda value, resume: prepared)
    monkeypatch.setattr(cli, "run_gateway", gateway)
    monkeypatch.setattr(cli, "write_usage_report", usage)

    exit_code = cli.evolve_harness_command(
        config=tmp_path / "config.yaml",
        dry_run=False,
        resume=True,
        iterations=8,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"current_harness": "h8"' in output
    assert '"next_iteration": 9' in output
    gateway.assert_not_called()
    usage.assert_called_once()


def test_evolve_harness_rejects_backward_target_before_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    loaded = SimpleNamespace(config=SimpleNamespace(protocol=SimpleNamespace(generations=24)))
    prepared = SimpleNamespace(
        plan=SimpleNamespace(generations=24),
        paths=tmp_path,
        state=SimpleNamespace(
            experiment_name="demo",
            stage=EvolutionStage.TRAINING,
            active_generation=8,
            selection_path=None,
        ),
    )
    gateway = MagicMock()
    monkeypatch.setattr(cli, "load_harness_evolution_config", lambda path: loaded)
    monkeypatch.setattr(cli, "prepare_experiment", lambda value, resume: prepared)
    monkeypatch.setattr(cli, "run_gateway", gateway)

    exit_code = cli.evolve_harness_command(
        config=tmp_path / "config.yaml",
        dry_run=False,
        resume=True,
        iterations=7,
    )

    assert exit_code == 2
    gateway.assert_not_called()
