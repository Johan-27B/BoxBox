from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from harbor.agents.terminus_2.terminus_2 import Command
from harbor.agents.terminus_2.tmux_session import TmuxSession
from harbor.environments.base import ExecResult
from harbor.llms.base import LLMResponse
from harbor.llms.chat import Chat
from harbor.models.agent.context import AgentContext
from harbor.models.metric import UsageInfo
from litellm.exceptions import ContentPolicyViolationError

from perfrace.installed.terminus_boxbox import TerminusBoxBoxAgent
from boxbox.terminus_boxbox.kernel.interfaces import TaskPhase
from boxbox.terminus_boxbox.kernel import (
    Kernel,
    ReviewResult,
    RuntimeState,
    RuntimeTrap,
)
from boxbox.terminus_boxbox.harness import review
from boxbox.terminus_boxbox.harness.agent import (
    REVIEW_COOLDOWN_SEC,
    REVIEW_TRAJECTORY_NAME,
    ReviewContextCapture,
    ReviewContextPhase,
    ReviewContextWindow,
    ToolCallResponse,
    _PERSISTENT_SHELL_PREAMBLE,
)


class FakeRuntime:
    def __init__(
        self,
        logs_dir: Path,
        *,
        conversation: list[str] | None = None,
    ) -> None:
        self.logs_dir = logs_dir
        self.timeout = 0
        self.conversation = conversation or ["target history"]
        self.session = SimpleNamespace(stop=AsyncMock(), start=AsyncMock())
        self.used = False
        self.trap: RuntimeTrap | None = None
        self.reviewers = []
        self.fault_reports = []
        self.review_result = ReviewResult()
        self.accepted_boundaries: list[tuple[int, int]] = []
        self.restart_count = 0
        self.reconcile_count = 0

    async def review(
        self,
        environment,
        context,
        *,
        sequence,
        reviewer,
        fault_report,
    ) -> ReviewResult:
        self.reviewers.append(reviewer)
        self.fault_reports.append(fault_report)
        context.n_input_tokens = 7
        context.n_output_tokens = 3
        context.cost_usd = 0.25
        context.rollout_details = [{"sequence": sequence}]
        return self.review_result

    def export_state(self) -> RuntimeState:
        return RuntimeState.capture({"format": "v1", "conversation": list(self.conversation)})

    def import_state(self, state: RuntimeState) -> None:
        self.conversation = list(state.data["conversation"])

    def release_session(self):
        if self.session is None:
            raise RuntimeError("no session")
        session = self.session
        self.session = None
        return session

    def attach_session(self, session):
        if self.session is not None:
            raise RuntimeError("session already attached")
        self.session = session
        return session

    async def restart_session(self, session):
        self.restart_count += 1
        await session.stop()
        await session.start()
        return session

    def prepare_continuation(self) -> str:
        return "continue target"

    def reconcile_review_trajectory(self) -> None:
        self.reconcile_count += 1

    def mark_harness_context_accepted(
        self,
        through_sequence: int,
        through_offset: int,
    ) -> None:
        self.accepted_boundaries.append((through_sequence, through_offset))

    async def ensure_agent_session(self) -> None:
        return None

    def set_task_instruction(self, instruction: str) -> None:
        self.task_instruction = instruction

    def configure_target_phase(self, *, boxbox_enabled: bool) -> None:
        self.boxbox_enabled = boxbox_enabled

    async def run_until_trap(self, instruction, environment, context) -> RuntimeTrap | None:
        self.used = True
        return self.trap


class MutatingRuntime(FakeRuntime):
    def import_state(self, state: RuntimeState) -> None:
        state.data["conversation"].append("corrupted")
        raise ValueError("migration failed")


class SessionMismatchRuntime(FakeRuntime):
    def attach_session(self, session):
        super().attach_session(session)
        return object()


def make_environment() -> AsyncMock:
    environment = AsyncMock()
    environment.default_user = "root"
    environment.task_env_config.workdir = "/workspace"
    environment.exec.return_value = ExecResult(stdout="", stderr="", return_code=0)
    return environment


def configure_bundle_download(environment: AsyncMock, repository: Path) -> None:
    async def download(*, source_path, target_path):
        subprocess.run(
            ["git", "-C", str(repository), "bundle", "create", str(target_path), "HEAD"],
            check=True,
        )

    environment.download_file.side_effect = download


def make_agent(tmp_path: Path, **kwargs) -> TerminusBoxBoxAgent:
    return TerminusBoxBoxAgent(
        logs_dir=tmp_path,
        model_name="gpt-test",
        extra_env={
            "LLM_BASE_URL": "http://host.docker.internal:4001/v1",
            "LLM_API_KEY": "test-key",
        },
        reasoning_effort="high",
        max_turns=2,
        **kwargs,
    )


def bind_kernel(
    tmp_path: Path,
    *,
    runtime_class: type[FakeRuntime] = FakeRuntime,
    **runtime_kwargs,
) -> Kernel:
    kernel = Kernel(
        runtime_class=runtime_class,
        logs=tmp_path,
        constructor={"logs_dir": tmp_path / "active", **runtime_kwargs},
    )
    kernel.bind(commit="a" * 40)
    return kernel


def test_capture_review_context_indexes_empty_epoch_and_delta(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime

    capture = runtime.capture_review_context()

    assert (capture.through_sequence, capture.through_offset) == (0, 0)
    assert (capture.accepted_sequence, capture.accepted_offset) == (0, 0)
    assert (capture.presented_sequence, capture.presented_offset) == (0, 0)
    empty_window = ReviewContextWindow(
        first_sequence=None,
        last_sequence=None,
        record_count=0,
        phases=(),
    )
    assert capture.epoch == empty_window
    assert capture.delta == empty_window


def test_review_artifacts_index_the_canonical_trajectory(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path / "active")._kernel.active_runtime
    reviewer = make_agent(tmp_path / "reviewer")._kernel.active_runtime
    environment = make_environment()

    capture = asyncio.run(
        review.prepare_artifacts(
            runtime,
            reviewer,
            environment,
            feedback_enabled=False,
        )
    )

    assert capture.through_sequence == 0
    environment.upload_file.assert_not_awaited()
    source = reviewer._review_context_source
    assert source is not None
    assert source.trajectory == runtime.logs_dir / REVIEW_TRAJECTORY_NAME
    assert source.index == reviewer.logs_dir / "review-trajectory.index.jsonl"
    assert source.index.read_bytes() == b""
    assert (source.accepted_after, source.presented_after, source.through) == (0, 0, 0)


def test_review_context_is_split_by_accepted_harness_epoch(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    journal = runtime.logs_dir / REVIEW_TRAJECTORY_NAME
    journal.parent.mkdir(parents=True, exist_ok=True)
    first_records = [
        {"schema_version": 1, "sequence": 1, "phase": 1, "kind": "step"},
        {"schema_version": 1, "sequence": 2, "phase": 1, "kind": "phase_end"},
    ]
    first_payload = "".join(f"{json.dumps(record)}\n" for record in first_records).encode()
    journal.write_bytes(first_payload)
    runtime._review_trajectory_sequence = 2

    first = runtime.capture_review_context()

    assert (
        first.epoch
        == first.delta
        == ReviewContextWindow(
            first_sequence=1,
            last_sequence=2,
            record_count=2,
            phases=(ReviewContextPhase(phase=1, step_count=1, complete=True),),
        )
    )
    runtime.mark_review_context_presented(first.through_sequence, first.through_offset)

    second_records = [
        {"schema_version": 1, "sequence": 3, "phase": 2, "kind": "step"},
        {"schema_version": 1, "sequence": 4, "phase": 2, "kind": "phase_end"},
    ]
    second_payload = "".join(f"{json.dumps(record)}\n" for record in second_records).encode()
    with journal.open("ab") as stream:
        stream.write(second_payload)
    runtime._review_trajectory_sequence = 4

    retained = runtime.capture_review_context()

    assert retained.epoch.record_count == 4
    assert retained.delta == ReviewContextWindow(
        first_sequence=3,
        last_sequence=4,
        record_count=2,
        phases=(ReviewContextPhase(phase=2, step_count=1, complete=True),),
    )

    runtime.mark_review_context_presented(retained.through_sequence, retained.through_offset)
    runtime.mark_harness_context_accepted(retained.through_sequence, retained.through_offset)
    third_record = {"schema_version": 1, "sequence": 5, "phase": 3, "kind": "step"}
    third_payload = f"{json.dumps(third_record)}\n".encode()
    with journal.open("ab") as stream:
        stream.write(third_payload)
    runtime._review_trajectory_sequence = 5

    after_accept = runtime.capture_review_context()

    assert (
        after_accept.epoch
        == after_accept.delta
        == ReviewContextWindow(
            first_sequence=5,
            last_sequence=5,
            record_count=1,
            phases=(ReviewContextPhase(phase=3, step_count=1, complete=False),),
        )
    )


def test_runtime_reconciles_trajectory_appended_by_provisional_runtime(
    tmp_path: Path,
) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    journal = runtime.logs_dir / REVIEW_TRAJECTORY_NAME
    journal.parent.mkdir(parents=True, exist_ok=True)
    first_records = [
        {"schema_version": 1, "sequence": 1, "phase": 1, "kind": "step"},
        {"schema_version": 1, "sequence": 2, "phase": 1, "kind": "phase_end"},
    ]
    first_payload = "".join(f"{json.dumps(record)}\n" for record in first_records).encode()
    journal.write_bytes(first_payload)
    runtime._review_trajectory_sequence = 2
    runtime._review_trajectory_phase = 1
    runtime._accepted_trajectory_sequence = 0
    runtime._accepted_trajectory_offset = 0
    runtime._last_presented_trajectory_sequence = 2
    runtime._last_presented_trajectory_offset = len(first_payload)

    provisional_records = [
        {"schema_version": 1, "sequence": 3, "phase": 2, "kind": "step"},
        {"schema_version": 1, "sequence": 4, "phase": 2, "kind": "phase_end"},
    ]
    with journal.open("ab") as stream:
        stream.write("".join(f"{json.dumps(record)}\n" for record in provisional_records).encode())

    runtime.reconcile_review_trajectory()
    capture = runtime.capture_review_context()

    assert runtime._review_trajectory_sequence == 4
    assert runtime._review_trajectory_phase == 2
    assert capture.delta == ReviewContextWindow(
        first_sequence=3,
        last_sequence=4,
        record_count=2,
        phases=(ReviewContextPhase(phase=2, step_count=1, complete=True),),
    )


def test_review_context_query_indexes_searches_and_bounds_raw_evidence(tmp_path: Path) -> None:
    records = [
        {
            "schema_version": 1,
            "sequence": 1,
            "phase": 1,
            "kind": "step",
            "step": {
                "timestamp": "2026-09-10T00:00:00+00:00",
                "source": "agent",
                "message": "inspect the parser",
                "tool_calls": [
                    {
                        "function_name": "bash_command",
                        "arguments": {"keystrokes": "cargo test"},
                    }
                ],
                "observation": {"results": [{"content": "ordinary output"}]},
            },
        },
        {
            "schema_version": 1,
            "sequence": 2,
            "phase": 1,
            "kind": "step",
            "step": {
                "timestamp": "2026-09-10T00:01:00+00:00",
                "source": "agent",
                "message": "measure the candidate",
                "tool_calls": [
                    {
                        "function_name": "bash_command",
                        "arguments": {"keystrokes": "./workload/run.sh"},
                    }
                ],
                "observation": {
                    "results": [{"content": f"needle\n{'x' * 20_000}\nfinal evidence"}],
                },
            },
        },
        {
            "schema_version": 1,
            "sequence": 3,
            "phase": 1,
            "kind": "phase_end",
            "final_metrics": {"total_prompt_tokens": 10},
        },
    ]
    payload = "".join(f"{json.dumps(record)}\n" for record in records)
    trajectory = tmp_path / REVIEW_TRAJECTORY_NAME
    trajectory.write_text(payload, encoding="utf-8")
    index = tmp_path / "review-trajectory.index.jsonl"
    assert (
        review.build_context_index(
            trajectory,
            index,
            through_offset=len(payload.encode()),
        )
        == 3
    )
    source = review.ReviewContextSource(
        trajectory=trajectory,
        index=index,
        accepted_after=0,
        presented_after=1,
        through=3,
    )

    index_page = json.loads(
        review.query_context(
            source,
            {
                "action": "list",
                "view": "epoch",
                "limit": 1,
                "max_bytes": 2048,
            },
        )
    )
    assert index_page["events"][0]["seq"] == 1
    assert index_page["events"][0]["tools"] == ["bash_command"]
    assert index_page["next"] == 1
    assert index_page["more"] is True

    delta_page = json.loads(
        review.query_context(
            source,
            {
                "action": "list",
                "view": "delta",
                "limit": 1,
                "max_bytes": 2048,
            },
        )
    )
    assert [event["seq"] for event in delta_page["events"]] == [2]

    search = json.loads(
        review.query_context(
            source,
            {
                "action": "search",
                "view": "epoch",
                "query": "needle",
                "max_bytes": 2048,
            },
        )
    )
    assert [event["seq"] for event in search["events"]] == [2]

    expanded_text = review.query_context(
        source,
        {
            "action": "read",
            "view": "epoch",
            "seq": [2],
            "fields": ["message", "tool_calls", "observation"],
            "max_bytes": 2048,
        },
    )
    expanded = json.loads(expanded_text)
    assert len(expanded_text.encode("utf-8")) <= 2048
    assert expanded["events"][0]["seq"] == 2
    assert expanded["events"][0]["truncated"] is True
    assert "final evidence" in json.dumps(expanded["events"][0])


def test_review_context_native_tool_returns_direct_observation(tmp_path: Path) -> None:
    trajectory = tmp_path / REVIEW_TRAJECTORY_NAME
    payload = (
        '{"schema_version":1,"sequence":1,"phase":1,"kind":"step",'
        '"step":{"source":"agent","message":"evidence"}}\n'
    )
    trajectory.write_text(payload, encoding="utf-8")
    index = tmp_path / "review-trajectory.index.jsonl"
    review.build_context_index(
        trajectory,
        index,
        through_offset=len(payload.encode()),
    )
    runtime = make_agent(tmp_path / "runtime")._kernel.active_runtime
    runtime.configure_review_phase(policy="review policy")
    runtime._review_context_source = review.ReviewContextSource(
        trajectory=trajectory,
        index=index,
        accepted_after=0,
        presented_after=0,
        through=1,
    )

    parsed = runtime._parse_tool_calls(
        [
            {
                "id": "review-call",
                "function": {
                    "name": "review_context",
                    "arguments": json.dumps(
                        {
                            "action": "read",
                            "view": "delta",
                            "seq": [1],
                            "fields": ["message"],
                        }
                    ),
                },
            }
        ]
    )

    assert any(
        tool["function"]["name"] == "review_context" for tool in runtime._get_tool_definitions()
    )
    assert parsed[0] == []
    assert parsed[1] is None
    observation = json.loads(parsed[-1])
    assert observation["events"][0]["message"] == "evidence"


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0.1, 0.1), (1, 1), (60, 60), (300, 60), (900, 60)],
)
def test_command_wait_is_capped_at_sixty_seconds(
    tmp_path: Path, requested: float, expected: float
) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime

    parsed = runtime._parse_tool_calls(
        [
            {
                "id": "commands",
                "function": {
                    "name": "execute_commands",
                    "arguments": json.dumps(
                        {
                            "analysis": "run long operations",
                            "plan": "wait once for each command",
                            "commands": [
                                {"keystrokes": "make\n", "duration": requested},
                            ],
                        }
                    ),
                },
            }
        ]
    )

    assert [command.duration_sec for command in parsed[0]] == [expected]


def test_review_feedback_handoff_survives_state_transfer_once(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path / "active")._kernel.active_runtime
    runtime.set_task_instruction("optimize the target")
    runtime._pending_chat_state = {
        "schema_version": 1,
        "messages": [{"role": "system", "content": runtime.system_prompt()}],
    }
    runtime.mark_review_feedback_ready()

    candidate = make_agent(tmp_path / "candidate")._kernel.active_runtime
    candidate.import_state(runtime.export_state())

    first = candidate.prepare_continuation()
    second = candidate.prepare_continuation()

    assert review.FEEDBACK_FILE in first
    assert review.FEEDBACK_FILE not in second


def test_boxbox_schema_is_stable_but_requests_require_new_evidence(
    tmp_path: Path,
) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    runtime.configure_target_phase(boxbox_enabled=True)
    request = [
        {
            "id": "review-request",
            "function": {
                "name": "boxbox",
                "arguments": "{}",
            },
        }
    ]

    assert "boxbox" in {tool["function"]["name"] for tool in runtime._get_tool_definitions()}
    parsed = runtime._parse_tool_calls(request)

    assert parsed[1] is None
    assert parsed[2]  # A rejected request must provide feedback, not fixed wording.

    runtime._review_eligible = True
    assert "boxbox" in {tool["function"]["name"] for tool in runtime._get_tool_definitions()}
    assert runtime._parse_tool_calls(request)[1] == RuntimeTrap.BOXBOX


def test_completed_review_resets_review_eligibility_across_state_transfer(
    tmp_path: Path,
) -> None:
    runtime = make_agent(tmp_path / "active")._kernel.active_runtime
    runtime._review_eligible = True

    before_review = time.time()
    runtime.mark_review_context_presented(0, 0)
    candidate = make_agent(tmp_path / "candidate")._kernel.active_runtime
    candidate.import_state(runtime.export_state())

    assert runtime._review_eligible is False
    assert candidate._review_eligible is False
    assert runtime._review_cooldown_until is not None
    assert runtime._review_cooldown_until >= before_review + REVIEW_COOLDOWN_SEC
    assert candidate._review_cooldown_until == runtime._review_cooldown_until


def test_post_review_cooldown_rejects_then_allows_boxbox(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    runtime.configure_target_phase(boxbox_enabled=True)
    runtime._review_eligible = True
    runtime._review_cooldown_until = time.time() + REVIEW_COOLDOWN_SEC
    request = [
        {
            "id": "review-request",
            "function": {
                "name": "boxbox",
                "arguments": "{}",
            },
        }
    ]

    blocked = runtime._parse_tool_calls(request)

    assert blocked[1] is None
    assert blocked[2]

    runtime._review_cooldown_until = time.time() - 1

    assert runtime._parse_tool_calls(request)[1] == RuntimeTrap.BOXBOX


@pytest.mark.parametrize(
    ("keystrokes", "expected"),
    [
        ("printf evidence\\n", True),
        ("", False),
    ],
)
def test_target_command_controls_review_eligibility(
    tmp_path: Path,
    keystrokes: str,
    expected: bool,
) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    runtime._enable_summarize = False
    runtime._context = AgentContext()
    runtime._session = SimpleNamespace(
        is_session_alive=AsyncMock(return_value=True),
        send_keys=AsyncMock(),
        capture_pane=AsyncMock(
            side_effect=lambda: runtime._completion_marker(runtime._marker_seq)
        ),
        get_incremental_output=AsyncMock(return_value="observed"),
    )
    response = LLMResponse(content="", reasoning_content=None, usage=None)
    interaction = (
        [Command(keystrokes=keystrokes, duration_sec=0.1)],
        None,
        "",
        "collect evidence",
        "run one target action",
        response,
        None,
        None,
        [],
    )
    runtime._handle_llm_interaction = AsyncMock(side_effect=[interaction, interaction])

    asyncio.run(runtime._run_agent_loop("continue", Chat(runtime._llm)))

    assert runtime._review_eligible is expected


def test_target_submit_enables_later_review_eligibility(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    runtime._enable_summarize = False
    runtime._context = AgentContext()
    runtime._session = SimpleNamespace(
        is_session_alive=AsyncMock(return_value=True),
        get_incremental_output=AsyncMock(return_value=""),
    )
    response = LLMResponse(content="", reasoning_content=None, usage=None)
    runtime._handle_llm_interaction = AsyncMock(
        return_value=(
            [],
            RuntimeTrap.COMPLETE,
            "",
            "submit candidate",
            "request measurement",
            response,
            None,
            None,
            [],
        )
    )

    asyncio.run(runtime._run_agent_loop("continue", Chat(runtime._llm)))

    assert runtime._review_eligible is True


def test_target_image_read_enables_review_eligibility(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    runtime._enable_summarize = False
    runtime._context = AgentContext()
    runtime._session = SimpleNamespace(is_session_alive=AsyncMock(return_value=True))
    runtime._execute_image_read = AsyncMock(return_value="image evidence")
    response = LLMResponse(content="", reasoning_content=None, usage=None)
    image_request = runtime._parse_tool_calls(
        [
            {
                "id": "image-request",
                "function": {
                    "name": "image_read",
                    "arguments": json.dumps(
                        {
                            "file_path": "/tmp/profile.png",
                            "image_read_instruction": "inspect hotspots",
                        }
                    ),
                },
            }
        ]
    )[5]
    interaction = (
        [],
        None,
        "",
        "inspect profile",
        "read image evidence",
        response,
        image_request,
        None,
        [],
    )
    runtime._handle_llm_interaction = AsyncMock(side_effect=[interaction, interaction])

    asyncio.run(runtime._run_agent_loop("continue", Chat(runtime._llm)))

    assert runtime._review_eligible is True
    assert runtime._execute_image_read.await_count == 2


def test_runtime_enables_feedback_only_for_boxbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    run_review = AsyncMock()
    monkeypatch.setattr(review, "run", run_review)

    runtime._runtime_trap = RuntimeTrap.BOXBOX
    asyncio.run(
        runtime.review(
            make_environment(),
            AgentContext(),
            sequence=1,
            reviewer=MagicMock(),
            fault_report=None,
        )
    )
    assert run_review.await_args.kwargs["feedback_enabled"] is True

    runtime._runtime_trap = None
    asyncio.run(
        runtime.review(
            make_environment(),
            AgentContext(),
            sequence=2,
            reviewer=MagicMock(),
            fault_report=MagicMock(),
        )
    )
    assert run_review.await_args.kwargs["feedback_enabled"] is False


@pytest.mark.parametrize("feedback_enabled", [False, True])
def test_review_validates_and_archives_voluntary_feedback(
    tmp_path: Path,
    monkeypatch,
    feedback_enabled: bool,
) -> None:
    runtime = make_agent(tmp_path / "active")._kernel.active_runtime
    runtime.set_task_instruction("optimize the target")
    runtime.mark_review_context_presented = MagicMock()
    reviewer = make_agent(tmp_path / "reviewer")._kernel.active_runtime
    reviewer.run_until_trap = AsyncMock(return_value=RuntimeTrap.COMPLETE)
    environment = make_environment()
    if feedback_enabled:
        environment.exec.return_value = ExecResult(
            stdout="present\n",
            stderr="",
            return_code=0,
        )
    monkeypatch.setattr(
        review,
        "prepare_artifacts",
        AsyncMock(
            return_value=ReviewContextCapture(
                through_sequence=7,
                through_offset=11,
                accepted_sequence=0,
                accepted_offset=0,
                presented_sequence=3,
                presented_offset=5,
                epoch=ReviewContextWindow(
                    first_sequence=1,
                    last_sequence=7,
                    record_count=7,
                    phases=(ReviewContextPhase(phase=1, step_count=2, complete=True),),
                ),
                delta=ReviewContextWindow(
                    first_sequence=4,
                    last_sequence=7,
                    record_count=4,
                    phases=(ReviewContextPhase(phase=2, step_count=3, complete=True),),
                ),
            ),
        ),
    )
    monkeypatch.setattr(review, "prepare_reviewer", AsyncMock())

    result = asyncio.run(
        review.run(
            runtime,
            environment,
            AgentContext(),
            sequence=1,
            reviewer=reviewer,
            fault_report=None,
            feedback_enabled=feedback_enabled,
        )
    )

    assert result == ReviewResult(
        context_through_sequence=7,
        context_through_offset=11,
    )
    runtime.mark_review_context_presented.assert_called_once_with(7, 11)
    if feedback_enabled:
        assert runtime._review_feedback_ready is True
        assert review.FEEDBACK_FILE in environment.exec.await_args.args[0]
        environment.download_file.assert_awaited_once_with(
            source_path=review.FEEDBACK_FILE,
            target_path=reviewer.logs_dir / "review-feedback.txt",
        )
    else:
        assert runtime._review_feedback_ready is False
        environment.exec.assert_not_awaited()
        environment.download_file.assert_not_awaited()


def test_runtime_uses_placeholder_results_for_multiple_tool_calls(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    tool_calls = [
        {
            "id": f"call-{index}",
            "type": "function",
            "function": {
                "name": "execute_commands",
                "arguments": json.dumps(
                    {
                        "analysis": f"analysis {index}",
                        "plan": f"plan {index}",
                        "commands": [{"keystrokes": f"echo {index}\n"}],
                    }
                ),
            },
        }
        for index in (1, 2)
    ]
    runtime._call_llm_with_tools = AsyncMock(
        return_value=ToolCallResponse(content="", tool_calls=tool_calls)
    )
    chat = Chat(runtime._llm)

    commands, trap, feedback, *_ = asyncio.run(
        runtime._handle_llm_interaction(
            chat,
            "target",
            (None, None, None),
        )
    )

    assert [command.keystrokes for command in commands] == ["echo 1\n", "echo 2\n"]
    assert trap is None
    assert feedback == ""
    assert chat.messages[-2:] == [
        {"role": "tool", "tool_call_id": "call-1", "content": "executed"},
        {"role": "tool", "tool_call_id": "call-2", "content": "executed"},
    ]


def test_runtime_recovers_policy_rejection_with_compact_chat(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    chat = Chat(runtime._llm)
    chat.load_state(
        {
            "schema_version": 1,
            "messages": [
                {"role": "system", "content": "system contract"},
                {"role": "user", "content": "original task"},
                {
                    "role": "assistant",
                    "content": "old analysis",
                    "tool_calls": [{"id": "old-call"}],
                },
                {"role": "tool", "tool_call_id": "old-call", "content": "old output"},
            ],
        }
    )
    recovered = ToolCallResponse(
        content="recovered",
        tool_calls=[],
        usage=UsageInfo(
            prompt_tokens=11,
            completion_tokens=3,
            cache_tokens=2,
            cost_usd=0.01,
        ),
    )
    runtime._call_llm_with_tools = AsyncMock(
        side_effect=[
            ContentPolicyViolationError(
                "prompt was flagged",
                model="gpt-test",
                llm_provider="openai",
            ),
            recovered,
        ]
    )

    asyncio.run(
        runtime._handle_llm_interaction(
            chat,
            "rejected current prompt",
            (None, None, None),
        )
    )

    assert runtime._call_llm_with_tools.await_count == 2
    retry_messages = runtime._call_llm_with_tools.await_args_list[1].args[0]
    assert [message["role"] for message in retry_messages] == [
        "system",
        "user",
        "user",
    ]
    assert chat.messages[:2] == [
        {"role": "system", "content": "system contract"},
        {"role": "user", "content": "original task"},
    ]
    assert all("old output" not in str(message) for message in chat.messages)
    assert chat.messages[-1] == {"role": "assistant", "content": "recovered"}
    assert chat._cumulative_input_tokens == 11
    assert chat._cumulative_output_tokens == 3
    assert chat._cumulative_cache_tokens == 2
    assert chat._cumulative_cost == pytest.approx(0.01)


def test_command_execution_filters_runtime_nonce_marker(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    marker = runtime._completion_marker(1)
    session = SimpleNamespace(
        is_session_alive=AsyncMock(return_value=True),
        send_keys=AsyncMock(),
        capture_pane=AsyncMock(return_value=marker),
        get_incremental_output=AsyncMock(return_value=f"before\n{marker}\nafter"),
    )

    result = asyncio.run(
        runtime._execute_commands(
            [Command(keystrokes="echo ok\n", duration_sec=0.1)],
            session,
        )
    )

    assert result == (False, "before\nafter")
    assert session.send_keys.await_args_list[0].args[0].startswith("set +e\n")
    assert "BASH_SUBSHELL" in session.send_keys.await_args_list[0].args[0]


def test_persistent_shell_guard_preserves_top_level_and_subshell_semantics() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"{_PERSISTENT_SHELL_PREAMBLE}"
                "exit 7\n"
                "printf 'TOP=%s\\n' \"$?\"\n"
                "(exit 3)\n"
                "printf 'SUB=%s\\n' \"$?\"\n"
                "printf 'ALIVE\\n'\n"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "TOP=7\nSUB=3\nALIVE\n"


def test_command_execution_rejects_ctrl_d_before_sending_keys(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    session = SimpleNamespace(send_keys=AsyncMock())

    result = asyncio.run(
        runtime._execute_commands(
            [Command(keystrokes="C-d", duration_sec=0.1)],
            session,
        )
    )

    assert result[0] is False
    assert result[1].startswith("REJECTED: C-d")
    session.send_keys.assert_not_awaited()


def test_command_execution_sends_ctrl_c_without_shell_preamble(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    session = SimpleNamespace(
        send_keys=AsyncMock(),
        get_incremental_output=AsyncMock(return_value="interrupted"),
    )

    result = asyncio.run(
        runtime._execute_commands(
            [Command(keystrokes="C-c", duration_sec=1.0)],
            session,
        )
    )

    assert result == (False, "interrupted")
    session.send_keys.assert_awaited_once_with(
        "C-c",
        block=False,
        min_timeout_sec=0.2,
    )


def test_runtime_restart_session_discards_tmux_pane(tmp_path: Path) -> None:
    runtime = make_agent(tmp_path)._kernel.active_runtime
    environment = make_environment()
    session = TmuxSession(
        session_name="target-session",
        environment=environment,
        logging_path=tmp_path / "terminal.log",
        local_asciinema_recording_path=None,
        remote_asciinema_recording_path=None,
        user="agent",
    )
    session._previous_buffer = "old pane"
    session.start = AsyncMock()

    restarted = asyncio.run(runtime.restart_session(session))

    assert restarted is session
    assert session._previous_buffer is None
    assert "tmux kill-session -t target-session" in environment.exec.await_args.kwargs["command"]
    assert environment.exec.await_args.kwargs["user"] == "agent"
    session.start.assert_awaited_once_with()


def test_kernel_selects_successor_as_provisional(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    active = kernel.active_runtime
    active.review_result = ReviewResult(
        context_through_sequence=7,
        context_through_offset=11,
    )
    candidate = FakeRuntime(tmp_path / "candidate")
    candidate.session = None
    environment = make_environment()
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="c" * 40),
    )
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)

    asyncio.run(kernel.transition(active, environment))

    assert kernel.active_runtime is candidate
    assert kernel.confirmed_runtime is active
    assert kernel.has_provisional_runtime is True
    assert candidate.accepted_boundaries == [(7, 11)]
    summary = json.loads((tmp_path / "transitions" / "0001" / "transition.json").read_text())
    assert summary["outcome"] == "provisional"
    assert summary["runtime_selection"] == {
        "confirmed_commit": "a" * 40,
        "active_commit": "c" * 40,
        "provisional": True,
    }
    assert summary["context_boundary"] == {
        "through_sequence": 7,
        "through_offset": 11,
        "accepted": True,
    }


def test_kernel_rolls_back_activation_through_runtime_contract_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    active = kernel.active_runtime
    original_session = active.session
    candidate = SessionMismatchRuntime(tmp_path / "candidate")
    candidate.session = None
    environment = make_environment()
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="c" * 40),
    )
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)
    monkeypatch.setattr(kernel, "_restore_runtime_repo", AsyncMock(return_value=None))

    asyncio.run(kernel.transition(active, environment))

    summary = json.loads((tmp_path / "transitions" / "0001" / "transition.json").read_text())
    event = json.loads((tmp_path / "faults.jsonl").read_text().strip())
    assert summary["outcome"] == "rolled-back"
    assert summary["fault_event_ids"] == [event["event_id"]]
    assert event["stage"] == "activation"
    assert kernel.active_runtime is active
    assert active.session is original_session
    assert candidate.session is None


def test_kernel_preserves_rollback_state_from_candidate_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path, conversation=["original"])
    active = kernel.active_runtime
    candidate = MutatingRuntime(tmp_path / "candidate")
    candidate.session = None
    environment = make_environment()
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="c" * 40),
    )
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)
    monkeypatch.setattr(kernel, "_restore_runtime_repo", AsyncMock(return_value=None))

    asyncio.run(kernel.transition(active, environment))

    summary = json.loads((tmp_path / "transitions" / "0001" / "transition.json").read_text())
    event = json.loads((tmp_path / "faults.jsonl").read_text().strip())
    assert summary["outcome"] == "rolled-back"
    assert summary["fault_event_ids"] == [event["event_id"]]
    assert event["stage"] == "state_import"
    assert active.conversation == ["original"]


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_kernel_downloads_commit_bundle_without_hidden_worktree_changes(
    tmp_path: Path,
    flag: str,
) -> None:
    repository = tmp_path / "runtime"
    shutil.copytree(
        Path("boxbox/terminus_boxbox/harness"),
        repository,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    marker = repository / "marker.py"
    marker.write_text("VALUE = 'committed'\n", encoding="utf-8")
    # Feedback can be committed, but operational files must not become loaded source.
    operational_files = (
        ".runtime/review-feedback.txt",
        ".runtime/session.json",
        "__pycache__/stale.pyc",
    )
    for relative in operational_files:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("operational data", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "candidate"],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repository), "update-index", flag, "marker.py"],
        check=True,
    )
    marker.write_text("VALUE = 'mutable'\n", encoding="utf-8")
    assert (
        subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        == ""
    )

    kernel = Kernel(
        runtime_class=FakeRuntime,
        logs=tmp_path / "logs",
        constructor={"logs_dir": tmp_path / "active"},
    )
    kernel.bind(commit=commit)
    environment = make_environment()
    configure_bundle_download(environment, repository)
    transition = tmp_path / "transition"
    transition.mkdir()

    downloaded = asyncio.run(
        kernel._download_candidate(
            environment,
            commit,
            transition,
        )
    )

    assert (downloaded / "marker.py").read_text(encoding="utf-8") == (
        "VALUE = 'committed'\n"
    )
    assert all(not (downloaded / relative).exists() for relative in operational_files)
    environment.download_file.assert_awaited_once()
    environment.download_dir.assert_not_awaited()


def test_kernel_loads_clean_runtime_candidate(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    shutil.copytree(
        Path("boxbox/terminus_boxbox/harness"),
        source,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source), "config", "user.name", "test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "commit", "-q", "-m", "candidate"],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    agent = make_agent(tmp_path / "agent")
    agent._kernel.bind(commit=commit)

    candidate = agent._kernel._load_candidate(source, commit)
    agent._kernel._validate_candidate(candidate)

    candidate.set_task_instruction("continue from this task")
    state = candidate.export_state()
    successor = agent._kernel._load_candidate(source, commit)
    successor.import_state(state)
    assert successor.task_instruction == "continue from this task"


def test_finalize_uses_kernel_selected_runtime(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._kernel.bind(commit="b" * 40)
    agent._kernel.run_active_runtime = AsyncMock()
    environment = make_environment()
    context = AgentContext()

    asyncio.run(agent.finalize("finish", environment, context))
    agent._kernel.run_active_runtime.assert_awaited_once()
    call = agent._kernel.run_active_runtime.await_args
    assert call.args[1:] == (environment, context)
    assert call.kwargs == {"phase": TaskPhase.NO_REVIEW}


def test_kernel_returns_to_harbor_on_submit_trap(tmp_path: Path) -> None:
    kernel = bind_kernel(tmp_path)
    runtime = kernel.active_runtime
    runtime.trap = RuntimeTrap.COMPLETE
    kernel.transition = AsyncMock()
    context = AgentContext()

    asyncio.run(
        kernel.run_active_runtime(
            "target",
            make_environment(),
            context,
            phase=TaskPhase.TASK,
        )
    )

    assert runtime.used is True
    assert runtime.boxbox_enabled is True
    kernel.transition.assert_not_awaited()


def test_kernel_propagates_runtime_fault_when_review_is_disabled(tmp_path: Path) -> None:
    kernel = bind_kernel(tmp_path)
    runtime = kernel.active_runtime
    runtime.run_until_trap = AsyncMock(side_effect=RuntimeError("runtime crashed"))
    kernel.transition = AsyncMock()

    with pytest.raises(RuntimeError, match="runtime crashed"):
        asyncio.run(
            kernel.run_active_runtime(
                "target",
                make_environment(),
                AgentContext(),
                phase=TaskPhase.NO_REVIEW,
            )
        )

    assert runtime.boxbox_enabled is False
    kernel.transition.assert_not_awaited()


def test_kernel_reviews_runtime_fault_and_continues_selected_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    runtime = kernel.active_runtime
    runtime.run_until_trap = AsyncMock(
        side_effect=[
            RuntimeError("runtime crashed"),
            RuntimeTrap.COMPLETE,
        ]
    )
    runtime.review = AsyncMock(return_value=ReviewResult())
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="a" * 40),
    )
    environment = make_environment()

    asyncio.run(
        kernel.run_active_runtime(
            "target",
            environment,
            AgentContext(),
            phase=TaskPhase.TASK,
        )
    )

    assert runtime.run_until_trap.await_count == 2
    runtime.review.assert_awaited_once()
    events = [json.loads(line) for line in (tmp_path / "faults.jsonl").read_text().splitlines()]
    assert events[0]["source"] == "runtime"
    assert events[0]["stage"] == "runtime_execution"
    assert events[0]["error"]["type"] == "RuntimeError"
    assert events[0]["error"]["message"] == "runtime crashed"
    assert "RuntimeError: runtime crashed" in events[0]["error"]["traceback"]
    transition = json.loads((tmp_path / "transitions" / "0001" / "transition.json").read_text())
    assert transition["trigger"] == "runtime_fault"
    assert transition["fault_event_ids"] == [events[0]["event_id"]]
    assert list((tmp_path / "transitions" / "0001").glob(".fault-*.jsonl")) == []


def test_kernel_propagates_fault_journal_failure(tmp_path: Path, monkeypatch) -> None:
    kernel = bind_kernel(tmp_path)
    active = kernel.active_runtime
    monkeypatch.setattr(
        kernel,
        "_append_fault",
        AsyncMock(side_effect=OSError("journal unavailable")),
    )

    with pytest.raises(RuntimeError, match="Failed to append runtime fault"):
        asyncio.run(
            kernel.transition(
                active,
                make_environment(),
                runtime_fault=RuntimeError("runtime crashed"),
            )
        )

    assert active.reviewers == []


def test_kernel_merges_usage_before_reviewing_runtime_fault(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agent = make_agent(tmp_path)
    agent._kernel.bind(commit="b" * 40)
    runtime = agent._kernel.active_runtime
    runtime.ensure_agent_session = AsyncMock()

    async def fail(self, instruction, environment, segment):
        segment.n_input_tokens = 9
        segment.n_output_tokens = 4
        raise RuntimeError("model failed")

    monkeypatch.setattr(
        "boxbox.terminus_boxbox.harness.agent.Terminus2.run",
        fail,
    )
    agent._kernel.transition = AsyncMock(side_effect=RuntimeError("review failed"))
    context = AgentContext()

    with pytest.raises(RuntimeError, match="review failed"):
        asyncio.run(
            agent._kernel.run_active_runtime(
                "target",
                make_environment(),
                context,
                phase=TaskPhase.TASK,
            )
        )

    assert context.n_input_tokens == 9
    assert context.n_output_tokens == 4
    runtime_fault = agent._kernel.transition.await_args.kwargs["runtime_fault"]
    assert str(runtime_fault) == "model failed"


def test_kernel_keeps_successor_provisional_across_submit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    confirmed = kernel.active_runtime
    candidate = FakeRuntime(tmp_path / "candidate")
    candidate.session = None
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="c" * 40),
    )
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)
    asyncio.run(kernel.transition(confirmed, make_environment()))
    candidate.trap = RuntimeTrap.COMPLETE

    trap = asyncio.run(
        kernel.run_active_runtime(
            "continue",
            make_environment(),
            AgentContext(),
            phase=TaskPhase.TASK,
        )
    )

    assert trap == RuntimeTrap.COMPLETE
    assert kernel.active_runtime is candidate
    assert kernel.confirmed_runtime is confirmed
    assert kernel.has_provisional_runtime is True


def test_kernel_rejects_nested_transition_from_provisional_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    confirmed = kernel.active_runtime
    candidate = FakeRuntime(tmp_path / "candidate")
    candidate.session = None
    monkeypatch.setattr(
        kernel,
        "_read_candidate_commit",
        AsyncMock(return_value="c" * 40),
    )
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)
    asyncio.run(kernel.transition(confirmed, make_environment()))

    with pytest.raises(RuntimeError, match="Only the confirmed TerminusBoxBox"):
        asyncio.run(kernel.transition(candidate, make_environment()))


def test_kernel_rolls_back_faulting_provisional_before_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kernel = bind_kernel(tmp_path)
    confirmed = kernel.active_runtime
    original_session = confirmed.session
    candidate = FakeRuntime(tmp_path / "candidate")
    candidate.session = None
    read_commit = AsyncMock(side_effect=["c" * 40, "a" * 40])
    monkeypatch.setattr(kernel, "_read_candidate_commit", read_commit)
    monkeypatch.setattr(
        kernel,
        "_download_candidate",
        AsyncMock(return_value=tmp_path / "source"),
    )
    monkeypatch.setattr(kernel, "_load_candidate", lambda source, commit: candidate)
    environment = make_environment()
    asyncio.run(kernel.transition(confirmed, environment))

    candidate.run_until_trap = AsyncMock(side_effect=ValueError("expected 8, got 7"))
    confirmed.run_until_trap = AsyncMock(return_value=RuntimeTrap.COMPLETE)
    context = AgentContext()

    asyncio.run(
        kernel.run_active_runtime(
            "continue",
            environment,
            context,
            phase=TaskPhase.TASK,
        )
    )

    assert kernel.active_runtime is confirmed
    assert kernel.confirmed_runtime is confirmed
    assert kernel.has_provisional_runtime is False
    assert confirmed.session is original_session
    assert candidate.session is None
    assert confirmed.restart_count == 1
    assert confirmed.reconcile_count == 1
    original_session.stop.assert_awaited_once()
    original_session.start.assert_awaited_once()
    assert len(confirmed.reviewers) == 2
    assert candidate.reviewers == []
    faults = [json.loads(line) for line in (tmp_path / "faults.jsonl").read_text().splitlines()]
    assert len(faults) == 1
    assert faults[0]["active_commit"] == "c" * 40
    assert faults[0]["error"]["message"] == "expected 8, got 7"
    rollback = json.loads((tmp_path / "transitions" / "0002" / "transition.json").read_text())
    assert rollback["outcome"] == "retained"
    assert rollback["runtime_selection"] == {
        "confirmed_commit": "a" * 40,
        "active_commit": "a" * 40,
        "provisional": False,
    }
    assert len(list((tmp_path / "transitions").glob("*/transition.json"))) == 2


def test_review_uses_continuing_chat_and_unprivileged_terminal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agent = make_agent(tmp_path)
    agent._kernel.bind(commit="b" * 40)
    runtime = agent._kernel.active_runtime
    runtime.set_task_instruction("optimize the target")
    runtime.review_chat_state = {
        "schema_version": 1,
        "messages": [
            {"role": "system", "content": "old review prompt"},
            {"role": "assistant", "content": "retained diagnosis"},
        ],
    }
    runtime.override_boxbox_policy("custom replay policy")
    session = SimpleNamespace(start=AsyncMock())
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(review, "TmuxSession", factory)

    reviewer = agent._kernel._create_reviewer(runtime, tmp_path / "transitions" / "0001")
    asyncio.run(
        review.prepare_reviewer(
            runtime,
            reviewer,
            make_environment(),
            sequence=1,
        )
    )

    assert reviewer._pending_chat_state["messages"][1] == {
        "role": "user",
        "content": "Original target task:\noptimize the target",
    }
    assert reviewer._pending_chat_state["messages"][2] == {
        "role": "assistant",
        "content": "retained diagnosis",
    }
    assert factory.call_args.kwargs["user"] == 65534
    factory.assert_called_once()
    session.start.assert_awaited_once()
