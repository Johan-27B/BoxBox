"""Ablation behavior through tools, transitions, and source deployment."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.agents.terminus_2.terminus_2 import Command
from harbor.llms.base import LLMResponse
from harbor.llms.chat import Chat
from harbor.models.agent.context import AgentContext
from test_terminus_boxbox import FakeRuntime, make_environment

from boxbox.terminus_boxbox import harness
from boxbox.terminus_boxbox.kernel import ReviewResult, RuntimeTrap
from boxbox.terminus_boxbox.seed import materialize
from perfrace.ablations import periodic
from perfrace.ablations.bounded import BoundedKernel, EditableSurface, audit_paths
from perfrace.ablations.periodic import PeriodicKernel, ReviewSchedule
from perfrace.installed.bounded import BoundedTerminusBoxBoxAgent
from perfrace.installed.periodic import PeriodicTerminusBoxBoxAgent
from perfrace.installed.terminus_boxbox import TerminusBoxBoxAgent


def runtime_for(tmp_path, agent_class=BoundedTerminusBoxBoxAgent):
    return agent_class(
        logs_dir=tmp_path, model_name="openai/test", max_turns=2
    )._kernel.active_runtime


def call(name, arguments):
    return {"id": "call-1", "function": {"name": name, "arguments": json.dumps(arguments)}}


def declare(surface="tools_observability", mechanism="Command results omit exit status."):
    return call("select_editable_surface", {"surface": surface, "failure_mechanism": mechanism})


def tool_names(runtime):
    return {tool["function"]["name"] for tool in runtime._get_tool_definitions()}


@pytest.mark.parametrize("surface", list(EditableSurface))
def test_bounded_scope_is_declared_once_per_review(tmp_path, surface):
    runtime = runtime_for(tmp_path)
    runtime.configure_target_phase(boxbox_enabled=True)
    assert "boxbox" in tool_names(runtime)
    assert "select_editable_surface" not in tool_names(runtime)
    assert runtime._parse_tool_calls([declare()])[6] is None

    runtime.configure_review_phase(policy="Inspect the recorded failures.")
    assert "select_editable_surface" in tool_names(runtime)
    assert "boxbox" not in tool_names(runtime)
    parsed = runtime._parse_tool_calls([declare(surface)])
    assert parsed[0] == [] and parsed[1] is None
    assert json.loads(parsed[6])["surface"] == surface
    repeated = runtime._parse_tool_calls([declare()])
    assert repeated[2] and repeated[6] is None

    runtime.configure_review_phase(policy="Inspect a new review.")
    assert json.loads(runtime._parse_tool_calls([declare()])[6])["status"] == "selected"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        [],
        None,
        {"surface": "all", "failure_mechanism": "Failure"},
        {"surface": "runtime_control", "failure_mechanism": ""},
        {"surface": "runtime_control", "failure_mechanism": 7},
        {"surface": "runtime_control", "failure_mechanism": "x" * 4097},
    ],
)
def test_invalid_scope_declaration_does_not_consume_selection(tmp_path, arguments):
    runtime = runtime_for(tmp_path)
    runtime.configure_review_phase(policy="Inspect failures.")
    result = runtime._parse_tool_calls([call("select_editable_surface", arguments)])
    assert result[2] and result[6] is None
    assert runtime._parse_tool_calls([declare()])[6] is not None


def test_scope_declaration_cannot_be_batched_with_edit_commands(tmp_path):
    runtime = runtime_for(tmp_path)
    runtime.configure_review_phase(policy="Inspect failures.")
    result = runtime._parse_tool_calls(
        [
            declare(),
            call("execute_commands", {"commands": [{"keystrokes": "rm agent.py\n"}]}),
        ]
    )
    assert result[0] == [] and result[1] is None and result[2]
    assert runtime._parse_tool_calls([declare()])[6] is not None


@pytest.mark.parametrize(
    ("candidate", "declaration", "accepted"),
    [
        ("a" * 40, None, True),
        ("c" * 40, None, False),
        ("c" * 40, {"surface": "runtime_control", "failure_mechanism": "Lost state"}, True),
    ],
)
async def test_bounded_transition_requires_declaration_only_for_changes(
    tmp_path, monkeypatch, candidate, declaration, accepted
):
    kernel = BoundedKernel(
        runtime_class=FakeRuntime, logs=tmp_path, constructor={"logs_dir": tmp_path / "active"}
    )
    kernel.bind(commit="a" * 40)
    runtime = kernel.active_runtime
    successor = FakeRuntime(tmp_path / "successor")
    successor.session = None
    original_session = runtime.session

    async def review(environment, context, *, reviewer, **kwargs):
        reviewer._scope_decision = declaration
        return ReviewResult()

    runtime.review = AsyncMock(side_effect=review)
    environment = make_environment()
    environment.exec.return_value.stdout = candidate
    monkeypatch.setattr(kernel, "_download_candidate", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(kernel, "_load_candidate", lambda *args: successor)
    await kernel.transition(runtime, environment)
    report = json.loads((tmp_path / "transitions/0001/transition.json").read_text())
    if candidate == "a" * 40:
        assert report["outcome"] == "retained"
    elif accepted:
        assert kernel.active_runtime is successor
        assert successor.session is original_session
        assert report["outcome"] == "provisional"
    else:
        assert kernel.active_runtime is runtime
        assert report["outcome"] == "retained"
        assert report["fault_event_ids"]
    assert report["review_scope"]["declaration"] == declaration


def test_bounded_audit_does_not_claim_python_edits_are_semantically_confined():
    assert (
        audit_paths({"surface": "tools_observability"}, ["agent.py"]) == "semantic_review_required"
    )
    assert audit_paths({"surface": "target_guidance"}, ["agent.py"]) == "cross_surface"
    assert (
        audit_paths({"surface": "target_guidance"}, ["prompt-templates/task.txt"])
        == "path_consistent"
    )


@pytest.fixture
def clock(monkeypatch):
    value = SimpleNamespace(now=0.0)
    monkeypatch.setattr(periodic, "time", SimpleNamespace(monotonic=lambda: value.now))
    return value


@pytest.mark.parametrize("interval", [True, 0, -1, float("inf"), float("nan"), "1800"])
def test_periodic_requires_valid_interval(interval):
    with pytest.raises(ValueError):
        ReviewSchedule(interval)


async def test_periodic_waits_for_tool_result_and_preserves_it(tmp_path, clock):
    runtime = runtime_for(tmp_path, PeriodicTerminusBoxBoxAgent)
    runtime.configure_target_phase(boxbox_enabled=True)
    assert "boxbox" not in tool_names(runtime)
    runtime._enable_summarize = False
    runtime._context = AgentContext()
    runtime._session = SimpleNamespace(is_session_alive=AsyncMock(return_value=True))
    runtime._handle_llm_interaction = AsyncMock(
        return_value=(
            [Command(keystrokes="measure\n", duration_sec=1)],
            None,
            "",
            "",
            "",
            LLMResponse(content="", reasoning_content=None, usage=None),
            None,
            None,
            [],
        )
    )
    finished = []

    async def execute(commands, session):
        clock.now = 1805
        await asyncio.sleep(0)
        assert runtime._runtime_trap is None
        finished.append(True)
        return "", "Measurement completed: 1.3x"

    runtime._execute_commands = AsyncMock(side_effect=execute)
    await runtime._run_agent_loop("Continue.", Chat(runtime._llm))
    assert finished == [True]
    assert runtime._handle_llm_interaction.await_count == 1
    assert runtime._runtime_trap == RuntimeTrap.BOXBOX
    step = runtime._trajectory_steps[-1]
    assert any("1.3x" in result.content for result in step.observation.results)
    assert any(tool.function_name == "periodic_review" for tool in step.tool_calls)


def test_submission_resume_and_final_delivery_obey_periodic_schedule(tmp_path, clock):
    runtime = runtime_for(tmp_path, PeriodicTerminusBoxBoxAgent)
    runtime.configure_target_phase(boxbox_enabled=True)
    clock.now = 1700
    assert runtime._resolve_completion_request(None, "output") == ("output", False)
    runtime.configure_target_phase(boxbox_enabled=True)  # ordinary resume must not reset it
    clock.now = 1810
    assert runtime._resolve_completion_request(RuntimeTrap.COMPLETE, "submit")[1]
    assert runtime._runtime_trap == RuntimeTrap.COMPLETE
    assert runtime._review_schedule.pending is None
    runtime.configure_target_phase(boxbox_enabled=False)  # final delivery
    assert runtime._resolve_completion_request(None, "finalizing") == ("finalizing", False)
    runtime.configure_review_phase(policy="Review.")
    assert runtime._resolve_completion_request(None, "reviewing") == ("reviewing", False)
    runtime.configure_target_phase(boxbox_enabled=True)
    assert runtime._resolve_completion_request(None, "next result")[1]
    assert runtime._runtime_trap == RuntimeTrap.BOXBOX
    assert runtime._review_schedule.pending["safe_point_delay_sec"] == 10


@pytest.mark.parametrize("fault", [False, True])
async def test_periodic_transition_resets_schedule_and_keeps_fault_trigger(tmp_path, clock, fault):
    kernel = PeriodicKernel(
        runtime_class=FakeRuntime, logs=tmp_path, constructor={"logs_dir": tmp_path / "active"}
    )
    kernel.active_runtime._runtime_trap = None
    kernel.bind(commit="a" * 40)
    kernel.schedule.start()
    clock.now = 1810
    kernel.schedule.due()
    environment = make_environment()
    environment.exec.return_value.stdout = "a" * 40
    await kernel.transition(
        kernel.active_runtime,
        environment,
        **({"runtime_fault": RuntimeError("command failed")} if fault else {}),
    )
    payload = json.loads((tmp_path / "transitions/0001/transition.json").read_text())
    assert payload["trigger"] == ("runtime_fault" if fault else "periodic_review")
    if not fault:
        assert payload["trigger_metadata"]["safe_point_delay_sec"] == 10
        assert payload["fault_event_ids"] == []
    assert kernel.schedule.pending is None
    clock.now = 3609
    assert not kernel.schedule.due()
    clock.now = 3610
    assert kernel.schedule.due()


@pytest.mark.parametrize("agent_class", [BoundedTerminusBoxBoxAgent, PeriodicTerminusBoxBoxAgent])
def test_ablation_applies_to_loaded_successors_but_not_ordinary_boxbox(tmp_path, agent_class):
    agent = agent_class(logs_dir=tmp_path / "ablation", model_name="openai/test")
    source = materialize(Path(harness.__file__).parent, tmp_path / "next")
    loaded = agent._kernel._load_candidate(source, "c" * 40)
    loaded.configure_target_phase(boxbox_enabled=True)
    if agent_class is BoundedTerminusBoxBoxAgent:
        loaded.configure_review_phase(policy="Inspect.")
        assert "select_editable_surface" in tool_names(loaded)
    else:
        assert "boxbox" not in tool_names(loaded)
        assert loaded._review_schedule is agent._kernel.schedule

    ordinary = runtime_for(tmp_path / "ordinary", TerminusBoxBoxAgent)
    ordinary.configure_target_phase(boxbox_enabled=True)
    assert "boxbox" in tool_names(ordinary)
    ordinary.configure_review_phase(policy="Inspect.")
    assert "select_editable_surface" not in tool_names(ordinary)
