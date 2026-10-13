"""Frozen and evolved harness behavior through the ordinary Harbor lifecycle."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.models.agent.context import AgentContext

from boxbox.terminus_boxbox import harness
from boxbox.terminus_boxbox.kernel.interfaces import RuntimeTrap
from boxbox.terminus_boxbox.seed import fingerprint, materialize
from perfrace.installed.evolved import EvolvedHarnessAgent
from perfrace.installed.frozen import FrozenHarnessAgent
from perfrace.installed.terminus_boxbox import TerminusBoxBoxAgent
from perfrace.installed.bounded import BoundedTerminusBoxBoxAgent
from perfrace.installed.periodic import PeriodicTerminusBoxBoxAgent


@pytest.fixture
def environment(monkeypatch):
    # Exercise source deployment and loading, but do not start Docker or tmux.
    monkeypatch.setattr("harbor.agents.terminus_2.terminus_2.Terminus2.setup", AsyncMock())
    return SimpleNamespace(
        task_env_config=SimpleNamespace(workdir="/workspace/project"),
        exec=AsyncMock(
            return_value=SimpleNamespace(return_code=0, stdout="a" * 40, stderr="")
        ),
        upload_dir=AsyncMock(),
    )


async def test_boxbox_variants_and_frozen_deploy_identical_independent_h0(tmp_path, environment):
    source = Path(harness.__file__).parent
    before = fingerprint(source)
    copies = []
    runtimes = []
    for agent_class in (
        TerminusBoxBoxAgent, FrozenHarnessAgent,
        BoundedTerminusBoxBoxAgent, PeriodicTerminusBoxBoxAgent,
    ):
        agent = agent_class(logs_dir=tmp_path / agent_class.name(), model_name="openai/test")
        await agent.setup(environment)
        copied = environment.upload_dir.await_args.kwargs["source_dir"]
        assert fingerprint(copied) == before
        copies.append(copied)
        runtimes.append(agent._kernel.active_runtime)
    assert copies[0] != copies[1]
    (copies[0] / "new-skill.txt").write_text("A skill added during one run.")
    assert not (copies[1] / "new-skill.txt").exists()
    assert fingerprint(source) == before
    # Both environments report the same initial commit. Their policy reads
    # must nevertheless remain attached to their own copies.
    second_policy = runtimes[1].boxbox_policy()
    (copies[0] / "skills/self_review/SKILL.md").write_text("Only the first run changes.")
    assert runtimes[0].boxbox_policy() == "Only the first run changes."
    assert runtimes[1].boxbox_policy() == second_policy


@pytest.mark.parametrize("agent_class", [FrozenHarnessAgent, EvolvedHarnessAgent])
async def test_static_harness_preserves_session_without_reviews(
    tmp_path, environment, agent_class
):
    kwargs = {}
    if agent_class is EvolvedHarnessAgent:
        supplied = materialize(Path(harness.__file__).parent, tmp_path / "selected")
        (supplied / "prompt-templates/task.txt").write_text("Preserve the input records.")
        kwargs = {"harness_source": supplied, "harness_identity": "selected-revision"}
    agent = agent_class(logs_dir=tmp_path / "logs", model_name="openai/test", **kwargs)
    await agent.setup(environment)
    runtime = agent._kernel.active_runtime
    if kwargs:
        assert "Preserve the input records." in runtime.system_prompt()
    runtime.ensure_agent_session = AsyncMock()
    runtime.review = AsyncMock(side_effect=AssertionError("Frozen harness must not review"))
    history = []

    async def submit(instruction, environment, context):
        names = {tool["function"]["name"] for tool in runtime._get_tool_definitions()}
        assert "submit" in names
        assert "boxbox" not in names
        history.append(instruction)
        context.n_input_tokens = 3
        return RuntimeTrap.COMPLETE

    runtime.run_until_trap = AsyncMock(side_effect=submit)
    context = AgentContext()
    await agent.run("Optimize the project.", environment, context)
    await agent.resume("Accepted: score 1.2.", environment, context)
    await agent.finalize("Deliver the best candidate.", environment, context)
    assert agent._kernel.active_runtime is runtime
    assert len(history) == 3
    assert "Accepted: score 1.2." in history[1]
    assert context.n_input_tokens == 9
    runtime.review.assert_not_awaited()


async def test_frozen_propagates_fault_without_harness_repair(tmp_path, environment):
    agent = FrozenHarnessAgent(logs_dir=tmp_path / "logs", model_name="openai/test")
    await agent.setup(environment)
    runtime = agent._kernel.active_runtime
    runtime.ensure_agent_session = AsyncMock()
    runtime.run_until_trap = AsyncMock(side_effect=RuntimeError("target failed"))
    runtime.review = AsyncMock()
    with pytest.raises(RuntimeError, match="target failed"):
        await agent.run("Optimize.", environment, AgentContext())
    runtime.review.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs", [{}, {"harness_source": Path("/selected")}]
)
def test_evolved_harness_requires_explicit_source_and_identity(tmp_path, kwargs):
    with pytest.raises(ValueError):
        EvolvedHarnessAgent(logs_dir=tmp_path, model_name="openai/test", **kwargs)
