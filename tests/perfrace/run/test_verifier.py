from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.trial.paths import TrialPaths

from perfrace.run.verifier import MEASUREMENT_FILENAME, PerfRaceVerifier, PerfRaceVerifierResult
from perfrace.run.verifier.shadow import ShadowRunResult
from perfrace.run.services.session_identity import decode_token_proxy_api_key, token_proxy_api_key


def _environment(session_id: str = "trial-1__env") -> DockerEnvironment:
    environment = AsyncMock(spec=DockerEnvironment)
    environment.session_id = session_id
    return environment


def _task(
    tmp_path: Path,
    *,
    measurement_table: str | None = None,
    llm_table: str | None = None,
    verifier_env: dict[str, str] | None = None,
) -> SimpleNamespace:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    measurement = (
        measurement_table
        if measurement_table is not None
        else """
[perfrace.measurement]
measurement = "llm-tokens"
unit = "total_tokens"
direction = "minimize"
"""
    )
    llm = (
        llm_table
        if llm_table is not None
        else """
[perfrace.llm]
model = "gpt-5.5"
"""
    )
    (task_dir / "task.toml").write_text(
        f"""
{measurement}
{llm}
"""
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    test_script = tests / "test.sh"
    test_script.write_text("#!/usr/bin/env bash\n")
    return SimpleNamespace(
        name="terminus-kira--demo",
        short_name="terminus-kira--demo",
        checksum="task-sha",
        task_dir=task_dir,
        paths=SimpleNamespace(tests_dir=tests, test_path=test_script),
        # Mirrors Harbor's real Task.config: a TaskConfig whose .verifier.env
        # holds the task.toml-declared [verifier].env dict (empty by default).
        config=SimpleNamespace(verifier=SimpleNamespace(env=verifier_env or {})),
    )


def _trial_paths(tmp_path: Path) -> TrialPaths:
    paths = TrialPaths(trial_dir=tmp_path / "trial")
    paths.mkdir()
    return paths


def _repetition(
    *,
    correct: bool = True,
    value: float | None = 80,
    exit_code: int = 0,
    details: dict[str, object] | None = None,
    host_resources: dict[str, object] | None = None,
) -> ShadowRunResult:
    """One repetition's ``ShadowRunResult`` as ``run_measurement`` would
    return it for a repetition that ran to completion and printed the
    ``{"correct": ..., "value": ...}`` contract as its last stdout line."""
    payload: dict[str, object] = {"correct": correct, "value": value}
    if details is not None:
        payload["details"] = details
    stdout = json.dumps(payload)
    return ShadowRunResult(
        exit_code=exit_code,
        oom_killed=False,
        stdout=stdout,
        host_resources=host_resources,
    )


def _mock_shadow(monkeypatch: pytest.MonkeyPatch, *, results: list[ShadowRunResult]) -> AsyncMock:
    """Patch the two shadow.py entry points ``verifier.py`` calls, so tests
    exercise ``PerfRaceVerifier`` without touching real Docker. Returns the
    ``run_measurement`` mock so tests can assert on its call args (e.g. the
    ``env_factory``/``n`` it received)."""
    import perfrace.run.verifier.verifier as verifier_module

    monkeypatch.setattr(verifier_module, "commit_snapshot", AsyncMock())

    @asynccontextmanager
    async def paused_main_container(_environment):
        yield

    monkeypatch.setattr(verifier_module, "paused_main_container", paused_main_container)
    run_measurement = AsyncMock(return_value=results)
    monkeypatch.setattr(verifier_module, "run_measurement", run_measurement)
    return run_measurement


def test_verify_returns_accepted_for_a_correct_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    run_measurement = _mock_shadow(monkeypatch, results=[_repetition(value=80)])
    verifier = PerfRaceVerifier(
        task=_task(tmp_path),
        trial_paths=trial_paths,
        environment=_environment(),
        override_env={"LLM_API_KEY": "sk-test"},
    )

    result = asyncio.run(verifier.verify())

    assert isinstance(result, PerfRaceVerifierResult)
    assert result.measurement is not None
    assert result.measurement.verdict == "ACCEPTED"
    assert result.measurement.value == 80
    env_factory = run_measurement.await_args.kwargs["env_factory"]
    assert env_factory("unused-session") == {"LLM_API_KEY": "sk-test"}
    written = json.loads((trial_paths.verifier_dir / MEASUREMENT_FILENAME).read_text())
    assert written["verdict"] == "ACCEPTED"


def test_measurement_records_host_resource_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allocation = {
        "logical_cpus": [0, 4],
        "physical_cores": [{"socket": 0, "core": 0}, {"socket": 0, "core": 1}],
        "numa_node": 0,
        "wait_seconds": 0.25,
    }
    _mock_shadow(
        monkeypatch,
        results=[_repetition(value=80, host_resources=allocation)],
    )
    verifier = PerfRaceVerifier(
        task=_task(tmp_path),
        trial_paths=_trial_paths(tmp_path),
        environment=_environment(),
    )

    result = asyncio.run(verifier.verify())

    assert result.measurement is not None
    assert result.measurement.details["repetitions"][0]["host_resources"] == allocation


def test_measurement_unpauses_main_when_shadow_run_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import perfrace.run.verifier.verifier as verifier_module

    monkeypatch.setattr(verifier_module, "commit_snapshot", AsyncMock())
    transitions: list[str] = []

    @asynccontextmanager
    async def paused_main_container(_environment):
        transitions.append("pause")
        try:
            yield
        finally:
            transitions.append("unpause")

    monkeypatch.setattr(verifier_module, "paused_main_container", paused_main_container)
    monkeypatch.setattr(
        verifier_module,
        "run_measurement",
        AsyncMock(side_effect=RuntimeError("shadow failed")),
    )
    verifier = PerfRaceVerifier(
        task=_task(tmp_path),
        trial_paths=_trial_paths(tmp_path),
        environment=_environment(),
    )

    with pytest.raises(RuntimeError, match="shadow failed"):
        asyncio.run(verifier.verify())

    assert transitions == ["pause", "unpause"]


def test_verify_calculates_llm_cost_from_token_proxy_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(monkeypatch, results=[_repetition(value=999)])
    task = _task(
        tmp_path,
        measurement_table="""
[perfrace.measurement]
measurement = "llm-cost"
unit = "USD"
direction = "minimize"
""",
        llm_table="""
[perfrace.llm]
model = "gpt-5.5"

[perfrace.llm.pricing]
currency = "USD"
input_usd_per_million_tokens = 5.0
cached_input_usd_per_million_tokens = 0.5
output_usd_per_million_tokens = 30.0
""",
    )
    verifier = PerfRaceVerifier(
        task=task,
        trial_paths=trial_paths,
        environment=_environment(),
        host_token_proxy_base_url="http://127.0.0.1:1234",
    )
    monkeypatch.setattr(
        verifier,
        "_read_token_proxy_summary",
        AsyncMock(
            return_value={
                "model": "gpt-5.5",
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 10,
                "requests": 3,
            }
        ),
    )

    result = asyncio.run(verifier.verify())

    assert result.measurement is not None
    assert result.measurement.value == pytest.approx(0.00062)
    repetition = result.measurement.details["repetitions"][0]
    assert repetition["reported_value"] == 999
    assert repetition["token_usage"] == {
        "cost_usd": pytest.approx(0.00062),
        "input_tokens": 100,
        "cached_input_tokens": 40,
        "uncached_input_tokens": 60,
        "output_tokens": 10,
        "requests": 3,
        "model": "gpt-5.5",
        "pricing": {
            "currency": "USD",
            "input_usd_per_million_tokens": 5.0,
            "cached_input_usd_per_million_tokens": 0.5,
            "output_usd_per_million_tokens": 30.0,
        },
    }


def test_verify_rejects_llm_cost_summary_for_a_different_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(monkeypatch, results=[_repetition()])
    task = _task(
        tmp_path,
        measurement_table="""
[perfrace.measurement]
measurement = "llm-cost"
unit = "USD"
direction = "minimize"
""",
        llm_table="""
[perfrace.llm]
model = "gpt-5.5"

[perfrace.llm.pricing]
input_usd_per_million_tokens = 5.0
cached_input_usd_per_million_tokens = 0.5
output_usd_per_million_tokens = 30.0
""",
    )
    verifier = PerfRaceVerifier(
        task=task,
        trial_paths=trial_paths,
        environment=_environment(),
        host_token_proxy_base_url="http://127.0.0.1:1234",
    )
    monkeypatch.setattr(
        verifier,
        "_read_token_proxy_summary",
        AsyncMock(
            return_value={
                "model": "gpt-5.4",
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 10,
                "requests": 3,
            }
        ),
    )

    with pytest.raises(ValueError, match="model mismatch"):
        asyncio.run(verifier.verify())

    written = json.loads((trial_paths.verifier_dir / MEASUREMENT_FILENAME).read_text())
    assert written["verdict"] == "VERIFIER_ERROR"


def test_verify_returns_wrong_answer_for_an_incorrect_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(monkeypatch, results=[_repetition(correct=False, value=None)])
    verifier = PerfRaceVerifier(
        task=_task(tmp_path), trial_paths=trial_paths, environment=_environment()
    )

    result = asyncio.run(verifier.verify())

    assert isinstance(result, PerfRaceVerifierResult)
    assert result.measurement is not None
    assert result.measurement.verdict == "WRONG_ANSWER"
    assert result.measurement.value is None


def test_verify_treats_a_repetition_that_failed_to_spawn_as_a_failed_repetition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(monkeypatch, results=[ShadowRunResult(exit_code=-1, oom_killed=False)])
    verifier = PerfRaceVerifier(
        task=_task(tmp_path), trial_paths=trial_paths, environment=_environment()
    )

    result = asyncio.run(verifier.verify())

    assert isinstance(result, PerfRaceVerifierResult)
    assert result.measurement is not None
    assert result.measurement.verdict == "WRONG_ANSWER"


def test_verify_runs_a_single_repetition_when_scope_is_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    run_measurement = _mock_shadow(
        monkeypatch,
        results=[_repetition(value=42, details={"values": [41.0, 42.0, 43.0]})],
    )
    task = _task(
        tmp_path,
        measurement_table="""
[perfrace.measurement]
measurement = "wall-clock"
unit = "seconds"
direction = "minimize"
n_repetitions = 3
repetition_scope = "internal"
""",
    )
    verifier = PerfRaceVerifier(task=task, trial_paths=trial_paths, environment=_environment())

    result = asyncio.run(verifier.verify())

    # n_repetitions=3 describes test.sh's own internal loop only --
    # PerfRaceVerifier itself must still only run it once.
    assert run_measurement.await_args.kwargs["n"] == 1
    assert result.measurement is not None
    assert result.measurement.verdict == "ACCEPTED"
    assert result.measurement.value == 42
    assert result.measurement.details["repetitions"][0]["details"] == {
        "values": [41.0, 42.0, 43.0]
    }


def test_verify_rejects_non_object_repetition_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    repetition = ShadowRunResult(
        exit_code=0,
        oom_killed=False,
        stdout='{"correct": true, "value": 42, "details": [41, 42, 43]}',
    )
    _mock_shadow(monkeypatch, results=[repetition])
    verifier = PerfRaceVerifier(
        task=_task(tmp_path), trial_paths=trial_paths, environment=_environment()
    )

    with pytest.raises(ValueError, match="'details' must be an object"):
        asyncio.run(verifier.verify())


def test_verify_aggregates_repetitions_by_pass_rate_and_mean_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(
        monkeypatch,
        results=[
            _repetition(correct=True, value=10),
            _repetition(correct=True, value=20),
            _repetition(correct=False, value=None),
        ],
    )
    task = _task(
        tmp_path,
        measurement_table="""
[perfrace.measurement]
measurement = "llm-tokens"
unit = "total_tokens"
direction = "minimize"
n_repetitions = 3
min_pass_rate = 0.5
""",
    )
    verifier = PerfRaceVerifier(task=task, trial_paths=trial_paths, environment=_environment())

    result = asyncio.run(verifier.verify())

    assert result.measurement is not None
    # pass_rate = 2/3 >= min_pass_rate=0.5 -> ACCEPTED; mean of the two
    # non-null values (the failed repetition's null value is excluded).
    assert result.measurement.verdict == "ACCEPTED"
    assert result.measurement.value == 15
    assert result.measurement.details["pass_rate"] == pytest.approx(2 / 3)


def test_verify_honors_override_n_repetitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    run_measurement = _mock_shadow(monkeypatch, results=[_repetition()])
    task = _task(
        tmp_path,
        measurement_table="""
[perfrace.measurement]
measurement = "llm-tokens"
unit = "total_tokens"
direction = "minimize"
n_repetitions = 5
""",
    )
    verifier = PerfRaceVerifier(
        task=task, trial_paths=trial_paths, environment=_environment(), override_n_repetitions=1
    )

    asyncio.run(verifier.verify())

    assert run_measurement.await_args.kwargs["n"] == 1


def test_verify_merges_task_level_verifier_env_with_job_level_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    run_measurement = _mock_shadow(monkeypatch, results=[_repetition()])
    verifier = PerfRaceVerifier(
        task=_task(
            tmp_path,
            verifier_env={"FROM_TASK": "task-value", "SHARED_KEY": "task-wins-nowhere"},
        ),
        trial_paths=trial_paths,
        environment=_environment(),
        # Job-level override_env must win over the task-level value for a
        # key present in both, mirroring Harbor's own native Verifier's
        # precedence: task.config.verifier.env < verifier_env < override_env.
        override_env={"SHARED_KEY": "job-wins", "FROM_JOB": "job-value"},
    )

    asyncio.run(verifier.verify())

    env_factory = run_measurement.await_args.kwargs["env_factory"]
    assert env_factory("unused-session") == {
        "FROM_TASK": "task-value",
        "SHARED_KEY": "job-wins",
        "FROM_JOB": "job-value",
    }


def test_verify_injects_token_proxy_env_from_task_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    secret = "test-secret"
    run_measurement = _mock_shadow(monkeypatch, results=[_repetition()])
    verifier = PerfRaceVerifier(
        task=_task(tmp_path),
        trial_paths=trial_paths,
        environment=_environment("trial-1"),
        container_token_proxy_base_url="http://host.docker.internal:1234",
        token_proxy_secret=secret,
    )

    asyncio.run(verifier.verify())

    env_factory = run_measurement.await_args.kwargs["env_factory"]
    expected_key = token_proxy_api_key("rep-session", "gpt-5.5", secret=secret)
    assert env_factory("rep-session") == {
        "LLM_BASE_URL": "http://host.docker.internal:1234/v1",
        "LLM_API_KEY": expected_key,
        "LLM_MODEL": "gpt-5.5",
        "PERFRACE_TOKEN_PROXY_RESET_URL": (
            "http://host.docker.internal:1234/sessions/rep-session/reset"
        ),
        "PERFRACE_TOKEN_PROXY_SUMMARY_URL": (
            "http://host.docker.internal:1234/sessions/rep-session/summary"
        ),
    }
    assert decode_token_proxy_api_key(expected_key, secret=secret) == ("rep-session", "gpt-5.5")


def test_verifier_rejects_a_non_docker_environment(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="DockerEnvironment"):
        PerfRaceVerifier(
            task=_task(tmp_path),
            trial_paths=_trial_paths(tmp_path),
            environment=object(),  # type: ignore[arg-type]
        )


def test_verify_raises_when_last_stdout_line_is_not_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(
        monkeypatch,
        results=[ShadowRunResult(exit_code=0, oom_killed=False, stdout="not json\n")],
    )
    verifier = PerfRaceVerifier(
        task=_task(tmp_path), trial_paths=trial_paths, environment=_environment()
    )

    with pytest.raises(ValueError, match="not valid JSON"):
        asyncio.run(verifier.verify())


def test_verify_raises_when_task_toml_has_no_measurement_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trial_paths = _trial_paths(tmp_path)
    _mock_shadow(monkeypatch, results=[_repetition()])
    task = _task(tmp_path, measurement_table="")
    verifier = PerfRaceVerifier(task=task, trial_paths=trial_paths, environment=_environment())

    with pytest.raises(ValueError, match="no usable \\[perfrace.measurement\\] table"):
        asyncio.run(verifier.verify())
