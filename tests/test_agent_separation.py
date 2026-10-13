"""Harbor integration and editable Terminus-BOXBOX source handling."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from boxbox.terminus_boxbox import TerminusBoxBox, harness
from boxbox.terminus_boxbox.seed import fingerprint, materialize
from boxbox.terminus_boxbox.kernel.interfaces import RuntimeTrap
from perfrace.installed.terminus_boxbox import TerminusBoxBoxAgent


def tool_names(runtime):
    return {tool["function"]["name"] for tool in runtime._get_tool_definitions()}


def call(name):
    return [{"function": {"name": name, "arguments": "{}"}}]


def test_runtime_and_seed_import_without_perfrace(tmp_path):
    script = """
import importlib.abc
import sys
from pathlib import Path
class BlockPerfRace(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'perfrace' or fullname.startswith('perfrace.'):
            raise AssertionError('BOXBOX imports PerfRace: ' + fullname)
sys.meta_path.insert(0, BlockPerfRace())
from boxbox.terminus_boxbox import TerminusBoxBox
from boxbox.terminus_boxbox.seed import materialize
root = Path(sys.argv[1])
source = root / 'source'
source.mkdir()
(source / 'example.py').write_text('VALUE = 42')
copied = materialize(source, root / 'copy')
runtime = TerminusBoxBox(logs_dir=root / 'logs', model_name='openai/test')
assert (copied / 'example.py').read_text() == 'VALUE = 42'
"""
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


@pytest.mark.parametrize("completion", ["finish", "submit"])
def test_completion_is_supplied_by_integration(tmp_path, completion):
    if completion == "finish":
        runtime = TerminusBoxBox(logs_dir=tmp_path, model_name="openai/test")
    else:
        runtime = TerminusBoxBoxAgent(logs_dir=tmp_path, model_name="openai/test")._kernel.active_runtime
    runtime.configure_target_phase(boxbox_enabled=True)
    assert {completion, "boxbox"} <= tool_names(runtime)
    assert runtime._parse_tool_calls(call(completion))[1] == RuntimeTrap.COMPLETE
    assert runtime._trajectory_action_name(RuntimeTrap.COMPLETE) == completion
    other = "submit" if completion == "finish" else "finish"
    assert runtime._parse_tool_calls(call(other))[1] is None

    # Review completion is independent of the benchmark's submission action.
    runtime.configure_review_phase(policy="Diagnose and revise.")
    assert {"finish", "review_context"} <= tool_names(runtime)
    assert "submit" not in tool_names(runtime)
    assert "boxbox" not in tool_names(runtime)
    assert runtime._parse_tool_calls(call("finish"))[1] == RuntimeTrap.COMPLETE
    assert runtime._parse_tool_calls(call("submit"))[1] is None
    runtime.configure_target_phase(boxbox_enabled=False)
    assert completion in tool_names(runtime)
    assert "boxbox" not in tool_names(runtime)


def test_harness_files_are_independent_copies(tmp_path):
    source = Path(harness.__file__).parent
    before = fingerprint(source)
    a = materialize(source, tmp_path / "a")
    b = materialize(source, tmp_path / "b")
    assert fingerprint(a) == fingerprint(b) == before
    (a / "prompt-templates/task.txt").write_text("changed in one run")
    assert fingerprint(a) != fingerprint(b)
    assert fingerprint(source) == before
    with pytest.raises(FileExistsError):
        materialize(source, tmp_path / "a")


def test_setup_and_successor_review_use_prepared_harness(tmp_path):
    agent = TerminusBoxBoxAgent(logs_dir=tmp_path / "logs", model_name="openai/test")
    # These are caller-supplied inputs, not snapshots of the default wording.
    overlay = tmp_path / "input-files"
    (overlay / "prompt-templates").mkdir(parents=True)
    (overlay / "skills/self_review").mkdir(parents=True)
    task_prompt = overlay / "prompt-templates/task.txt"
    task_prompt.write_text("User task policy: preserve the input records.")
    review_prompt = overlay / "prompt-templates/review.txt"
    review_prompt.write_text("User review policy: examine repeated failed commands.")
    skill = overlay / "skills/self_review/SKILL.md"
    skill.write_text("User skill: prefer evidence from completed actions.")
    source = materialize(
        Path(harness.__file__).parent,
        tmp_path / "source",
        overlay=overlay,
    )
    sha = "a" * 40
    environment = SimpleNamespace(
        exec=AsyncMock(return_value=SimpleNamespace(return_code=0, stdout=sha, stderr="")),
        upload_dir=AsyncMock(),
    )
    asyncio.run(agent._kernel.setup(environment, workdir="/workspace", source=source))
    runtime = agent._kernel.active_runtime
    assert task_prompt.read_text() in runtime.system_prompt()
    assert skill.read_text() in runtime.boxbox_policy()
    reviewer = agent._kernel._create_reviewer(runtime, tmp_path / "review")
    reviewer.configure_review_phase(policy=runtime.boxbox_policy())
    assert review_prompt.read_text() in reviewer.system_prompt()
    assert skill.read_text() in reviewer.system_prompt()

    # Successors read edited policy files, not an override re-applied from the host.
    (source / "skills/self_review/SKILL.md").write_text("new review policy")
    (source / "prompt-templates/review.txt").write_text("new review instructions")
    runtime.set_task_instruction("optimize this task")
    candidate = agent._kernel._load_candidate(source, "b" * 40)
    candidate.import_state(runtime.export_state())
    assert candidate.task_instruction == "optimize this task"
    assert candidate.boxbox_policy() == "new review policy"
    successor_reviewer = agent._kernel._create_reviewer(candidate, tmp_path / "review2")
    successor_reviewer.configure_review_phase(policy=candidate.boxbox_policy())
    assert "new review instructions" in successor_reviewer.system_prompt()
    assert "new review policy" in successor_reviewer.system_prompt()
    assert review_prompt.read_text() not in successor_reviewer.system_prompt()
    assert skill.read_text() not in successor_reviewer.system_prompt()
    candidate.configure_target_phase(boxbox_enabled=True)
    assert "submit" in tool_names(candidate)


@pytest.mark.parametrize("source_kind", ["initial", "directory", "commit"])
def test_adapter_copies_selected_harness_without_replacing_files(
    tmp_path, monkeypatch, source_kind
):
    # Exercise adapter + kernel setup, without starting Docker/tmux.
    monkeypatch.setattr(
        "harbor.agents.terminus_2.terminus_2.Terminus2.setup", AsyncMock()
    )
    kwargs = {}
    original = Path(harness.__file__).parent
    expected = (original / "prompt-templates/task.txt").read_text()
    if source_kind != "initial":
        original = materialize(original, tmp_path / "supplied")
        (original / "prompt-templates/task.txt").write_text("Evolved task instruction.")
        expected = "Evolved task instruction."
        kwargs["harness_source"] = original
        if source_kind == "commit":
            for args in [
                ["init", "-q"],
                ["config", "user.name", "Test"],
                ["config", "user.email", "test@example.invalid"],
                ["add", "-A"],
                ["commit", "-qm", "selected harness"],
            ]:
                subprocess.run(["git", "-C", str(original), *args], check=True)
            kwargs["harness_revision"] = "HEAD"
            (original / "prompt-templates/task.txt").write_text("Uncommitted instruction.")
    before = fingerprint(original)
    agent = TerminusBoxBoxAgent(
        logs_dir=tmp_path / "logs", model_name="openai/test", **kwargs
    )
    environment = SimpleNamespace(
        task_env_config=SimpleNamespace(workdir="/workspace"),
        exec=AsyncMock(
            return_value=SimpleNamespace(return_code=0, stdout=before[:40], stderr="")
        ),
        upload_dir=AsyncMock(),
    )
    asyncio.run(agent.setup(environment))
    copied = environment.upload_dir.await_args.kwargs["source_dir"]
    assert (copied / "prompt-templates/task.txt").read_text() == expected
    assert expected in agent._kernel.active_runtime.system_prompt()
    assert fingerprint(original) == before
    assert not (copied / ".git").exists()


def test_revision_requires_explicit_source(tmp_path):
    with pytest.raises(ValueError):
        TerminusBoxBoxAgent(
            logs_dir=tmp_path, model_name="openai/test", harness_revision="HEAD"
        )


@pytest.mark.parametrize("phase", ["task", "final-delivery", "review"])
def test_missing_tool_call_returns_feedback_without_completing_or_reviewing(tmp_path, phase):
    runtime = TerminusBoxBox(logs_dir=tmp_path, model_name="openai/test")
    if phase == "review":
        runtime.configure_review_phase(policy="Examine the observed behavior.")
    else:
        runtime.configure_target_phase(boxbox_enabled=phase == "task")
    commands, trap, feedback, _, _, image, observation = runtime._parse_tool_calls([])
    assert not commands
    assert trap is None
    assert feedback.strip()
    assert image is None
    assert observation is None


def test_final_delivery_accepts_submission_without_another_review(tmp_path):
    installed = TerminusBoxBoxAgent(logs_dir=tmp_path / "installed", model_name="openai/test")
    runtime = installed._kernel.active_runtime
    runtime.ensure_agent_session = AsyncMock()
    runtime.review = AsyncMock(side_effect=AssertionError("Unexpected review at final delivery"))

    async def deliver(instruction, environment, context):
        assert "Keep the verified candidate" in instruction
        assert "submit" in tool_names(runtime)
        assert "boxbox" not in tool_names(runtime)
        return runtime._parse_tool_calls(call("submit"))[1]

    runtime.run_until_trap = AsyncMock(side_effect=deliver)
    from harbor.models.agent.context import AgentContext

    asyncio.run(installed.finalize("Keep the verified candidate", object(), AgentContext()))
    runtime.run_until_trap.assert_awaited_once()


def test_host_model_endpoint_preserves_container_endpoint(tmp_path):
    endpoint = "http://host.docker.internal:18081/v1"
    agent = TerminusBoxBoxAgent(
        logs_dir=tmp_path,
        model_name="openai/test",
        extra_env={"LLM_BASE_URL": endpoint, "LLM_API_KEY": "test-key"},
    )
    runtime = agent._kernel.active_runtime
    assert runtime._llm._api_base == "http://127.0.0.1:18081/v1"
    assert runtime._extra_env["LLM_BASE_URL"] == endpoint


def test_submission_and_resume_keep_native_runtime(tmp_path):
    from harbor.models.agent.context import AgentContext

    agent = TerminusBoxBoxAgent(logs_dir=tmp_path, model_name="openai/test")
    runtime = agent._kernel.active_runtime
    runtime.ensure_agent_session = AsyncMock()
    environment = object()
    seen = []

    async def execute(instruction, env, context):
        assert env is environment
        assert agent._kernel.active_runtime is runtime
        seen.append(instruction)
        context.n_input_tokens = 7
        return RuntimeTrap.COMPLETE

    runtime.run_until_trap = AsyncMock(side_effect=execute)
    context = AgentContext()

    async def scenario():
        await agent.run("optimize the current project", environment, context)
        await agent.resume("Judge feedback: candidate is correct", environment, context)

    asyncio.run(scenario())
    assert len(seen) == 2
    assert "Judge feedback: candidate is correct" in seen[1]
    assert runtime.task_instruction == "optimize the current project"
    assert context.n_input_tokens == 14


def test_cancellation_keeps_partial_usage_and_allows_final_delivery(tmp_path):
    from harbor.models.agent.context import AgentContext

    agent = TerminusBoxBoxAgent(logs_dir=tmp_path, model_name="openai/test")
    runtime = agent._kernel.active_runtime
    runtime.ensure_agent_session = AsyncMock()
    context = AgentContext()

    async def interrupted(instruction, environment, segment):
        segment.n_input_tokens = 19
        raise asyncio.CancelledError()

    runtime.run_until_trap = AsyncMock(side_effect=interrupted)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await agent.run("optimize", object(), context)
        assert context.n_input_tokens == 19
        assert agent._kernel.active_runtime is runtime
        runtime.run_until_trap = AsyncMock(return_value=RuntimeTrap.COMPLETE)
        await agent.finalize("Deliver the current candidate", object(), context)
        runtime.run_until_trap.assert_awaited_once()
        assert "boxbox" not in tool_names(runtime)

    asyncio.run(scenario())


@pytest.mark.parametrize("after_reload", [False, True])
def test_runtime_preserves_provider_usage_without_pricing(tmp_path, after_reload):
    agent = TerminusBoxBoxAgent(logs_dir=tmp_path, model_name="openai/test")
    runtime = agent._kernel.active_runtime
    if after_reload:
        source = materialize(Path(harness.__file__).parent, tmp_path / "successor")
        runtime = agent._kernel._load_candidate(source, "c" * 40)
    usage = runtime._extract_usage_info(SimpleNamespace(
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 20},
        },
        _hidden_params={"response_cost": 0.125},
    ))
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 10
    assert usage.cache_tokens == 20
    assert usage.cost_usd == 0.125  # Provider-supplied metadata, not locally priced.
