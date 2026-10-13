from __future__ import annotations

from pathlib import Path

from perfrace.curate.lint import lint_cli, lint_instance_format, lint_task_toml

_MINIMAL_WALLCLOCK = """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "no-network"
cpus = 2
memory_mb = 4096
workdir = "/home/user/workspace"
"""


def _write(task_dir: Path, content: str) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(content, encoding="utf-8")
    return task_dir


def _write_format(task_dir: Path) -> Path:
    project = task_dir / "environment" / "workspace" / "project"
    workload = task_dir / "environment" / "workspace" / "workload"
    verifier_workload = task_dir / "tests" / "workload"
    project.mkdir(parents=True)
    workload.mkdir()
    verifier_workload.mkdir(parents=True)
    (project / "source.txt").write_text("source\n")
    (workload / "fixture.txt").write_text("fixture\n")
    (task_dir / "environment" / "Dockerfile").write_text(
        "FROM scratch\nCOPY workspace/ /home/user/workspace/\nWORKDIR /home/user/workspace\n"
    )
    run_script = workload / "run.sh"
    run_script.write_text("#!/bin/sh\nexit 0\n")
    run_script.chmod(0o755)
    (verifier_workload / "fixture.txt").write_text("fixture\n")
    for script_name in ("test.sh", "test_correctness.sh", "test_performance.sh"):
        script = task_dir / "tests" / script_name
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
    (task_dir / "instruction.md").write_text(
        "# Optimize project\n\nBuild the source under `project/`, then run `workload/run.sh`.\n"
    )
    (task_dir / "report.md").write_text(
        "---\n"
        "schema: 1\n"
        "instance: project--workload\n"
        "status: IN_PROGRESS\n"
        "realism: PENDING\n"
        "reliability: PENDING\n"
        "integrity: PENDING\n"
        "updated: 2026-08-29T00:00:00Z\n"
        "---\n"
    )
    return task_dir


def test_minimal_wallclock_instance_passes(tmp_path: Path) -> None:
    task_dir = _write(tmp_path, _MINIMAL_WALLCLOCK)

    assert lint_task_toml(task_dir) == []


def test_invalid_report_front_matter_is_rejected(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))
    report_path = task_dir / "report.md"
    report_path.write_text(
        report_path.read_text().replace(
            "reliability: PENDING",
            "reliability: APPROVED_WITH_LIMITATION",
        )
    )

    errors = lint_instance_format(task_dir)

    assert "invalid report.md reliability: APPROVED_WITH_LIMITATION" in errors


def test_missing_task_toml_reports_not_found(tmp_path: Path) -> None:
    errors = lint_task_toml(tmp_path)

    assert len(errors) == 1
    assert "not found" in errors[0]


def test_invalid_toml_is_reported(tmp_path: Path) -> None:
    task_dir = _write(tmp_path, "not [valid toml")

    errors = lint_task_toml(task_dir)

    assert len(errors) == 1
    assert "invalid TOML" in errors[0]


def test_stray_top_level_table_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK + '\n[metadata]\nname = "some-instance"\n',
    )

    errors = lint_task_toml(task_dir)

    assert any("stray top-level table" in e and "metadata" in e for e in errors)


def test_empty_solution_table_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(tmp_path, _MINIMAL_WALLCLOCK + "\n[solution]\n")

    errors = lint_task_toml(task_dir)

    assert any("[solution] is declared but empty" in e for e in errors)


def test_missing_task_name_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK.replace('name = "perfrace/some-instance"', ""),
    )

    errors = lint_task_toml(task_dir)

    assert any("[task].name is required" in e for e in errors)


def test_missing_perfrace_table_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "no-network"
""",
    )

    errors = lint_task_toml(task_dir)

    assert errors == ["[perfrace] table is required (at minimum, [perfrace.measurement])"]


def test_stray_perfrace_subtable_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK + '\n[perfrace.baseline]\ncommand = "run.sh"\n',
    )

    errors = lint_task_toml(task_dir)

    assert any("stray [perfrace.*] table" in e and "baseline" in e for e in errors)


def test_missing_measurement_table_is_rejected(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[perfrace.llm]
model = "gpt-5.5"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "public"
""",
    )

    errors = lint_task_toml(task_dir)

    assert any("[perfrace.measurement] is required" in e for e in errors)


def test_llm_tokens_measurement_requires_llm_table(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[perfrace.measurement]
measurement = "llm-tokens"
direction = "minimize"
unit = "total_tokens"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "public"
""",
    )

    errors = lint_task_toml(task_dir)

    assert errors == ['[perfrace.llm] is required when measurement == "llm-tokens"']


def test_llm_tokens_measurement_with_llm_table_passes(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[perfrace.measurement]
measurement = "llm-tokens"
direction = "minimize"
unit = "total_tokens"

[perfrace.llm]
model = "gpt-5.5"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "public"
""",
    )

    assert lint_task_toml(task_dir) == []


def test_llm_cost_measurement_requires_pricing(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        """
schema_version = "1.3"

[task]
name = "perfrace/some-instance"

[perfrace.measurement]
measurement = "llm-cost"
direction = "minimize"
unit = "USD"

[perfrace.llm]
model = "gpt-5.5"

[agent]
timeout_sec = 3600

[verifier]
timeout_sec = 900

[environment]
network_mode = "public"
""",
    )

    assert lint_task_toml(task_dir) == [
        '[perfrace.llm.pricing] is required when measurement == "llm-cost"'
    ]


def test_wallclock_measurement_does_not_require_llm_table(tmp_path: Path) -> None:
    task_dir = _write(tmp_path, _MINIMAL_WALLCLOCK)

    assert lint_task_toml(task_dir) == []


def test_invalid_network_mode_is_caught_via_harbor_schema(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK.replace('network_mode = "no-network"', 'network_mode = "egress"'),
    )

    errors = lint_task_toml(task_dir)

    assert any("fails Harbor's TaskConfig" in e for e in errors)


def test_verifier_timeout_is_capped_at_twenty_minutes(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK.replace("timeout_sec = 900", "timeout_sec = 1201"),
    )

    errors = lint_task_toml(task_dir)

    assert "[verifier].timeout_sec must be within 1200 seconds" in errors


def test_fractional_verifier_timeout_is_capped_at_twenty_minutes(tmp_path: Path) -> None:
    task_dir = _write(
        tmp_path,
        _MINIMAL_WALLCLOCK.replace("timeout_sec = 900", "timeout_sec = 1200.5"),
    )

    errors = lint_task_toml(task_dir)

    assert "[verifier].timeout_sec must be within 1200 seconds" in errors


def test_canonical_instance_format_passes(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))

    assert lint_instance_format(task_dir) == []


def test_instance_format_requires_project_workload_and_verifier_copy(tmp_path: Path) -> None:
    task_dir = _write(tmp_path, _MINIMAL_WALLCLOCK)

    errors = lint_instance_format(task_dir)

    assert "environment/workspace/ is required" in errors
    assert "environment/workspace/workload/ is required" in errors
    assert "tests/workload/ is required" in errors


def test_instance_format_requires_executable_verifier_scripts(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))
    (task_dir / "tests" / "test_correctness.sh").unlink()
    (task_dir / "tests" / "test_performance.sh").chmod(0o644)

    errors = lint_instance_format(task_dir)

    assert "tests/test_correctness.sh is required" in errors
    assert "tests/test_performance.sh must be executable" in errors


def test_instance_format_rejects_agent_visible_perfrace_path(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))
    leaked = task_dir / "environment" / "workspace" / "workload" / "perfrace-driver"
    leaked.mkdir()

    errors = lint_instance_format(task_dir)

    assert any("path names must not contain 'perfrace'" in error for error in errors)


def test_instance_format_rejects_workspace_copy_from_build_stage(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))
    (task_dir / "environment" / "Dockerfile").write_text(
        "FROM scratch AS builder\n"
        "FROM scratch\n"
        "COPY --from=builder workspace/ /home/user/workspace/\n"
        "WORKDIR /home/user/workspace\n"
    )

    errors = lint_instance_format(task_dir)

    assert any("must copy workspace/" in error for error in errors)


def test_instance_format_rejects_instruction_internals(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))
    (task_dir / "instruction.md").write_text(
        "You are given a benchmark. Run workspace/workload/run.sh. "
        "The PerfRace verifier also checks held-out tests."
    )

    errors = lint_instance_format(task_dir)

    assert any("omit the workspace/ prefix" in error for error in errors)
    assert any("must not name PerfRace" in error for error in errors)
    assert any("must not mention the verifier" in error for error in errors)
    assert any("must not disclose hidden or held-out checks" in error for error in errors)
    assert any("must be written as the user's request" in error for error in errors)


def test_lint_cli_returns_zero_when_all_pass(tmp_path: Path) -> None:
    task_dir = _write_format(_write(tmp_path, _MINIMAL_WALLCLOCK))

    exit_code = lint_cli([task_dir])

    assert exit_code == 0


def test_lint_cli_returns_one_when_any_fails(tmp_path: Path) -> None:
    good = _write_format(_write(tmp_path / "good", _MINIMAL_WALLCLOCK))
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad = _write_format(_write(bad_dir, _MINIMAL_WALLCLOCK + "\n[metadata]\n"))

    exit_code = lint_cli([good, bad])

    assert exit_code == 1


def test_lint_cli_defaults_to_configured_instance_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    instance_root = tmp_path / "external-instances"
    task_dir = _write_format(_write(instance_root / "example", _MINIMAL_WALLCLOCK))
    monkeypatch.setenv("PERFRACE_INSTANCE_ROOT", str(instance_root))

    exit_code = lint_cli()

    assert exit_code == 0
    assert f"PASS {task_dir}" in capsys.readouterr().out
