"""Lint a PerfRace task package and its Harbor configuration.

Reports schema and workspace violations for task authors and CI. Requires an
explicit task name and measurement protocol, with LLM configuration and pricing
when the chosen metric needs them. Harbor validates its native configuration
fields. Curation notes belong in report.md, not task.toml.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from pydantic import ValidationError

from harbor.models.task.config import TaskConfig
from perfrace.curate.report import read_report
from perfrace.paths import resolve_instance_root
from perfrace.run.types import LlmConfig, MeasurementConfig

ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "task", "verifier", "agent", "environment", "perfrace", "solution"}
)
ALLOWED_PERFRACE_KEYS = frozenset({"measurement", "llm"})
FORBIDDEN_INSTRUCTION_PATTERNS = (
    (re.compile(r"\bperfrace\b", re.IGNORECASE), "must not name PerfRace"),
    (re.compile(r"\bbenchmark\b", re.IGNORECASE), "must not describe itself as a benchmark"),
    (re.compile(r"\bverifier\b", re.IGNORECASE), "must not mention the verifier"),
    (
        re.compile(
            r"\bheld[- ]?out\b|\bhidden (?:case|check|input|test|workload)s?\b", re.IGNORECASE
        ),
        "must not disclose hidden or held-out checks",
    ),
    (
        re.compile(r"(?:^|[\s`'\"])(?:\.\./)*tests?/", re.IGNORECASE | re.MULTILINE),
        "must not disclose test paths",
    ),
    (
        re.compile(r"\bexpected (?:hash|checksum|output)\b", re.IGNORECASE),
        "must not disclose expected-result internals",
    ),
    (
        re.compile(r"\byou are given\b", re.IGNORECASE),
        "must be written as the user's request rather than an evaluator briefing",
    ),
)


def lint_instance_format(task_dir: Path) -> list[str]:
    """Return canonical workspace and instruction violations."""
    errors: list[str] = []
    report_path = task_dir / "report.md"
    if not report_path.is_file():
        errors.append("report.md is required")
    else:
        try:
            read_report(report_path)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    for legacy_name in ("README.md", "report.html"):
        if (task_dir / legacy_name).exists():
            errors.append(f"{legacy_name} must be merged into report.md")

    workspace = task_dir / "environment" / "workspace"
    workload = workspace / "workload"
    run_script = workload / "run.sh"
    verifier_workload = task_dir / "tests" / "workload"

    if not workspace.is_dir():
        errors.append("environment/workspace/ is required")
    else:
        entries = sorted(workspace.iterdir())
        project_dirs = [entry for entry in entries if entry.is_dir() and entry.name != "workload"]
        stray_entries = [
            entry.name for entry in entries if entry.name != "workload" and not entry.is_dir()
        ]
        if len(project_dirs) != 1:
            errors.append(
                "environment/workspace/ must contain exactly one project directory "
                "beside workload/"
            )
        if stray_entries:
            errors.append(
                "environment/workspace/ may contain only the project directory and "
                f"workload/; found {stray_entries}"
            )
        benchmark_owned_paths = [*entries]
        if workload.is_dir():
            benchmark_owned_paths.extend(workload.rglob("*"))
        leaked_paths = sorted(
            path.relative_to(workspace).as_posix()
            for path in benchmark_owned_paths
            if "perfrace" in path.name.casefold()
        )
        if leaked_paths:
            errors.append(f"agent-visible path names must not contain 'perfrace': {leaked_paths}")

    if not workload.is_dir():
        errors.append("environment/workspace/workload/ is required")
    else:
        workload_entries = [path for path in workload.iterdir() if path.name != "run.sh"]
        if not workload_entries:
            errors.append(
                "environment/workspace/workload/ must contain scored workload assets beside run.sh"
            )
    if not run_script.is_file():
        errors.append("environment/workspace/workload/run.sh is required")
    elif run_script.stat().st_mode & 0o111 == 0:
        errors.append("environment/workspace/workload/run.sh must be executable")

    if not verifier_workload.is_dir():
        errors.append("tests/workload/ is required")
    elif not any(verifier_workload.iterdir()):
        errors.append("tests/workload/ must contain the verifier-owned scored workload")

    for script_name in ("test.sh", "test_correctness.sh", "test_performance.sh"):
        script_path = task_dir / "tests" / script_name
        if not script_path.is_file():
            errors.append(f"tests/{script_name} is required")
        elif script_path.stat().st_mode & 0o111 == 0:
            errors.append(f"tests/{script_name} must be executable")

    dockerfile_path = task_dir / "environment" / "Dockerfile"
    if not dockerfile_path.is_file():
        errors.append("environment/Dockerfile is required")
    else:
        try:
            dockerfile = dockerfile_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"environment/Dockerfile is unreadable: {exc}")
        else:
            if not re.search(
                r"(?im)^\s*COPY\s+(?![^\n]*--from(?:=|\s))"
                r"(?:--\S+\s+)*workspace/\s+/home/user/workspace/?\s*$",
                dockerfile,
            ):
                errors.append(
                    "environment/Dockerfile must copy workspace/ to /home/user/workspace/"
                )
            workdirs = re.findall(r"(?im)^\s*WORKDIR\s+(\S+)\s*$", dockerfile)
            if not workdirs or workdirs[-1] != "/home/user/workspace":
                errors.append("environment/Dockerfile final WORKDIR must be /home/user/workspace")

    task_toml_path = task_dir / "task.toml"
    if task_toml_path.is_file():
        try:
            task_data = tomllib.loads(task_toml_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            pass
        else:
            environment = task_data.get("environment")
            if not isinstance(environment, dict) or environment.get("workdir") != (
                "/home/user/workspace"
            ):
                errors.append("[environment].workdir must be /home/user/workspace")

    instruction_path = task_dir / "instruction.md"
    if not instruction_path.is_file():
        errors.append("instruction.md is required")
    else:
        try:
            instruction = instruction_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"instruction.md is unreadable: {exc}")
        else:
            if "/home/user/workspace" in instruction:
                errors.append("instruction.md must use paths relative to /home/user/workspace")
            if "workspace/" in instruction:
                errors.append("instruction.md paths must omit the workspace/ prefix")
            if "workload/run.sh" not in instruction:
                errors.append("instruction.md must document workload/run.sh")
            for pattern, message in FORBIDDEN_INSTRUCTION_PATTERNS:
                if pattern.search(instruction):
                    errors.append(f"instruction.md {message}")

    return errors


def lint_task_toml(task_dir: Path) -> list[str]:
    """Return every schema violation found in ``task_dir/task.toml``.

    An empty list means the file is fully compliant with the minimal schema.
    Never raises -- unreadable/unparsable files are reported as a single
    error, not an exception.
    """
    task_toml_path = task_dir / "task.toml"
    if not task_toml_path.is_file():
        return [f"{task_toml_path}: not found"]

    try:
        raw_text = task_toml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{task_toml_path}: unreadable: {exc}"]

    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        return [f"{task_toml_path}: invalid TOML: {exc}"]

    errors: list[str] = []

    stray_top_level = set(data) - ALLOWED_TOP_LEVEL_KEYS
    if stray_top_level:
        errors.append(
            f"stray top-level table(s) {sorted(stray_top_level)} -- only "
            f"{sorted(ALLOWED_TOP_LEVEL_KEYS)} are allowed; curation-phase "
            f"content (e.g. [metadata]) belongs in report.md"
        )

    if "solution" in data and not data["solution"]:
        errors.append("[solution] is declared but empty -- drop it entirely if unused")

    # Harbor's own schema. Also catches drift like invalid enum values
    # (e.g. network_mode = "egress", never a valid NetworkMode) that a
    # top-level-keys-only check would miss.
    try:
        TaskConfig.model_validate_toml(raw_text)
    except Exception as exc:  # noqa: BLE001 - surface any Harbor-side rejection verbatim
        errors.append(f"fails Harbor's TaskConfig.model_validate_toml(): {exc}")

    task_table = data.get("task")
    if not isinstance(task_table, dict) or not task_table.get("name"):
        errors.append(
            "[task].name is required -- PerfRace instances must declare it "
            "explicitly rather than relying on Harbor's directory-name fallback"
        )

    verifier_table = data.get("verifier")
    if isinstance(verifier_table, dict):
        verifier_timeout = verifier_table.get("timeout_sec")
        if (
            isinstance(verifier_timeout, (int, float))
            and not isinstance(verifier_timeout, bool)
            and verifier_timeout > 1200
        ):
            errors.append("[verifier].timeout_sec must be within 1200 seconds")

    perfrace = data.get("perfrace")
    if not isinstance(perfrace, dict):
        errors.append("[perfrace] table is required (at minimum, [perfrace.measurement])")
        return errors

    stray_perfrace = set(perfrace) - ALLOWED_PERFRACE_KEYS
    if stray_perfrace:
        errors.append(
            f"stray [perfrace.*] table(s) {sorted(stray_perfrace)} -- only "
            f"{sorted(ALLOWED_PERFRACE_KEYS)} are allowed; [perfrace.baseline]/"
            f"[perfrace.correctness]/[perfrace.tags]/[perfrace.source]/"
            f"[perfrace.hardware] etc. belong in report.md"
        )

    measurement_data = perfrace.get("measurement")
    measurement: MeasurementConfig | None = None
    if measurement_data is None:
        errors.append("[perfrace.measurement] is required")
    else:
        try:
            measurement = MeasurementConfig.model_validate(measurement_data)
        except ValidationError as exc:
            errors.append(f"[perfrace.measurement] fails to validate: {exc}")

    llm_data = perfrace.get("llm")
    requires_pricing = measurement is not None and measurement.measurement == "llm-cost"
    llm: LlmConfig | None = None
    if llm_data is None:
        if measurement is not None and measurement.measurement == "llm-tokens":
            errors.append('[perfrace.llm] is required when measurement == "llm-tokens"')
        elif measurement is not None and measurement.measurement == "llm-cost":
            errors.append('[perfrace.llm] is required when measurement == "llm-cost"')
    else:
        try:
            llm = LlmConfig.model_validate(llm_data)
        except ValidationError as exc:
            errors.append(f"[perfrace.llm] fails to validate: {exc}")
    if requires_pricing and (llm is None or llm.pricing is None):
        errors.append('[perfrace.llm.pricing] is required when measurement == "llm-cost"')

    return errors


def lint_cli(paths: list[Path] | None = None) -> int:
    """Lint explicit directories or every task under the resolved instance root.

    Returns the process exit code (0 if every instance passes, 1 otherwise)
    so both the standalone script and the ``perfrace lint`` subcommand can
    share one implementation.
    """
    if paths:
        task_dirs = paths
    else:
        task_dirs = sorted(p.parent for p in resolve_instance_root().glob("**/task.toml"))

    failed = 0
    for task_dir in task_dirs:
        errors = [*lint_task_toml(task_dir), *lint_instance_format(task_dir)]
        if errors:
            failed += 1
            print(f"FAIL {task_dir}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {task_dir}")

    print(f"\n{len(task_dirs) - failed}/{len(task_dirs)} instances pass")
    return 1 if failed else 0
