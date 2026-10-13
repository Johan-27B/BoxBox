"""Self-rewriting TerminusBoxBox agent with native tool calling.

TerminusBoxBox preserves one logical target agent session across task continuations
and dynamically loaded runtime versions. A boxbox request yields control
to an isolated review session before target execution resumes under the
retained or successor runtime selected by the fixed Kernel.
"""

import asyncio
import copy
import json
import shlex
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
from litellm.exceptions import (
    AuthenticationError as LiteLLMAuthenticationError,
    BadRequestError,
    ContentPolicyViolationError,
    ContextWindowExceededError as LiteLLMContextWindowExceededError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from harbor.agents.terminus_2 import Terminus2
from harbor.agents.terminus_2.terminus_2 import Command
from harbor.agents.terminus_2.tmux_session import TmuxSession
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.llms.base import (
    ContextLengthExceededError,
    LLMResponse,
    OutputLengthExceededError,
)
from harbor.llms.chat import Chat

from .caching import add_anthropic_caching
from harbor.models.metric import UsageInfo
from harbor.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
)

from boxbox.terminus_boxbox.kernel.interfaces import (
    FaultReport,
    ReviewResult,
    RuntimeState,
    RuntimeTrap,
)

from . import review

CONTINUATION_PROMPT = (
    "The independent TerminusBoxBox review is complete. Continue task work "
    "from the existing conversation and terminal state."
)
REVIEW_TRAJECTORY_NAME = "review-trajectory.jsonl"


@dataclass(frozen=True)
class ReviewContextPhase:
    """Mechanical index entry for one phase in an incremental review context."""

    phase: int
    step_count: int
    complete: bool


@dataclass(frozen=True)
class ReviewContextWindow:
    """Authoritative bounds for the target records exposed to one review."""

    first_sequence: int | None
    last_sequence: int | None
    record_count: int
    phases: tuple[ReviewContextPhase, ...]


@dataclass(frozen=True)
class ReviewContextCapture:
    """Accepted-harness epoch and newly presented delta for one review."""

    through_sequence: int
    through_offset: int
    accepted_sequence: int
    accepted_offset: int
    presented_sequence: int
    presented_offset: int
    epoch: ReviewContextWindow
    delta: ReviewContextWindow


class BlockError(Exception):
    """Raised when infrastructure API call blocks for too long."""

    pass


BLOCK_TIMEOUT_SEC = 600  # 10 minutes
# Prevent repeated review transitions from consuming the shared research budget.
REVIEW_COOLDOWN_SEC = 30 * 60
_MARKER_PREFIX = "__CMDEND__"  # Marker prefix for command completion detection
_PERSISTENT_SHELL_PREAMBLE = (
    'set +e\nexit() { if ((BASH_SUBSHELL)); then builtin exit "$@"; '
    'else return "${1:-0}"; fi; }; '
    'logout() { if ((BASH_SUBSHELL)); then builtin logout "$@"; '
    'else return "${1:-0}"; fi; }\n'
)


@dataclass
class ToolCallResponse:
    """Extended response that includes tool calls."""

    content: str | None
    tool_calls: list[dict[str, Any]]
    reasoning_content: str | None = None
    usage: UsageInfo | None = None


@dataclass
class ImageReadRequest:
    """Request to read and analyze an image file."""

    file_path: str
    image_read_instruction: str


# Tool description strings
_EXECUTE_COMMANDS_DESC = (
    "Call this to execute commands in the terminal with your analysis and plan."
)

_ANALYSIS_DESC = (
    "Analyze the current state based on the terminal output provided. "
    "What do you see? What has been accomplished? What still needs to be done?"
)

_PLAN_DESC = (
    "Describe your plan for the next steps. "
    "What commands will you run and why? "
    "Be specific about what you expect each command to accomplish."
)

_COMMANDS_DESC = "The commands array can be empty if you want to wait without taking action."

_KEYSTROKES_DESC = (
    "String containing the exact keystrokes to send to the terminal. "
    "Write commands exactly as you want them sent to the terminal. "
    "Most bash commands should end with a newline (\\n) to cause them to execute. "
    "The terminal is a persistent shell. Use tmux-style `C-c` to interrupt foreground "
    "work; `C-d` is rejected because it would terminate the shell. Other keystrokes are "
    "sent exactly as written. "
    "Do not include extra whitespace before or after the keystrokes unless it's part of the intended command. "
    "Top-level `exit` and `logout` are guarded. Scope fail-fast behavior to a subshell "
    "such as `(set -e; commands...)`; when a child scope must return a status, use "
    '`(command; rc=$?; printf \'COMMAND_RC=%s\\n\' "$rc"; exit "$rc")`.'
)

_DURATION_DESC = (
    "Number of seconds to wait for the command to complete (default: 1.0) "
    "before the next command will be executed. "
    "On immediate tasks (e.g., cd, ls, echo, cat) set a duration of 0.1 seconds. "
    "On commands (e.g., gcc, find, rustc) set a duration of 1.0 seconds. "
    "On slow commands (e.g., make, python3 [long running script], wget [file]) set an appropriate duration as you determine necessary. "
    "It is better to set a smaller duration than a longer duration. "
    "It is always possible to wait again if the prior output has not finished, "
    "by running empty keystrokes with a duration on subsequent requests to wait longer. "
    "Never wait longer than 60 seconds; prefer to poll to see intermediate result status."
)

_FINISH_DESC = "Finish the current task and return control to the caller."
_BOXBOX_DESC = (
    "Pause target work and request an independent review once enough trajectory evidence "
    "has accumulated. The review may retain the current harness or activate a successor "
    "while preserving the target conversation, terminal session, and workspace."
)
_IMAGE_READ_DESC = (
    "Read and analyze an image file. "
    "Use this ONLY for image files that you need to visually analyze. "
    "Do NOT use this for text files — use shell commands (cat, head, etc.) instead. "
    "The image will be sent to the model for visual analysis "
    "and you will receive a text description in the next turn."
)

_FILE_PATH_DESC = "Absolute path to the image file. Supported formats: PNG, JPG, JPEG, GIF, WEBP."

_IMAGE_READ_INSTRUCTION_DESC = (
    "A text instruction describing what you want to learn from the image. "
    "Be specific about what information to extract."
)

# Tool definitions for native tool use
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_commands",
            "description": _EXECUTE_COMMANDS_DESC,
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis": {
                        "type": "string",
                        "description": _ANALYSIS_DESC,
                    },
                    "plan": {
                        "type": "string",
                        "description": _PLAN_DESC,
                    },
                    "commands": {
                        "type": "array",
                        "description": _COMMANDS_DESC,
                        "items": {
                            "type": "object",
                            "properties": {
                                "keystrokes": {
                                    "type": "string",
                                    "description": _KEYSTROKES_DESC,
                                },
                                "duration": {
                                    "type": "number",
                                    "description": _DURATION_DESC,
                                },
                            },
                            "required": ["keystrokes"],
                        },
                    },
                },
                "required": ["analysis", "plan", "commands"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": _FINISH_DESC,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "boxbox",
            "description": _BOXBOX_DESC,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_read",
            "description": _IMAGE_READ_DESC,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": _FILE_PATH_DESC,
                    },
                    "image_read_instruction": {
                        "type": "string",
                        "description": _IMAGE_READ_INSTRUCTION_DESC,
                    },
                },
                "required": ["file_path", "image_read_instruction"],
            },
        },
    },
]


class TerminusBoxBox(Terminus2):
    """Terminus-based agent implementing BOXBOX with native tool calling."""

    def __init__(self, *args, **kwargs):
        self._target_completion_name = kwargs.pop("completion_name", "finish")
        self._target_completion_description = kwargs.pop("completion_description", _FINISH_DESC)
        if not self._target_completion_name or self._target_completion_name in {
            "execute_commands", "image_read", "boxbox", "review_context"
        }:
            raise ValueError("Completion tool must have a non-empty, distinct name")
        super().__init__(*args, **kwargs)
        self._marker_seq = 0
        self._marker_nonce = uuid.uuid4().hex[:12]
        self._completion_tool_name = self._target_completion_name
        self._completion_tool_description = self._target_completion_description
        self._boxbox_enabled = False
        self._review_eligible = False
        self._review_cooldown_until: float | None = None
        self._runtime_trap: RuntimeTrap | None = None
        self._task_instruction: str | None = None
        self._base_system_prompt = self._prompt_template
        self._boxbox_system_prompt = (
            Path(__file__).parent / "prompt-templates" / "self-review.txt"
        ).read_text(encoding="utf-8")
        self._review_system_prompt = (
            Path(__file__).parent / "prompt-templates" / "review.txt"
        ).read_text(encoding="utf-8")
        self._review_policy_override: str | None = None
        self._system_prompt = self._base_system_prompt
        self._prompt_template = (
            "Task Description:\n{instruction}\n\nCurrent terminal state:\n{terminal_state}"
        )
        self._review_chat_state: dict[str, Any] | None = None
        self._review_feedback_ready = False
        self._review_trajectory_sequence = 0
        self._review_trajectory_phase = 0
        self._accepted_trajectory_sequence = 0
        self._accepted_trajectory_offset = 0
        self._last_presented_trajectory_sequence = 0
        self._last_presented_trajectory_offset = 0
        self._review_context_source: review.ReviewContextSource | None = None
        self._review_phase = False

    async def _with_block_timeout(self, coro, timeout_sec: int = BLOCK_TIMEOUT_SEC):
        """Wrap coroutine with block detection timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout_sec)
        except asyncio.TimeoutError:
            raise BlockError(f"Infrastructure API blocked for {timeout_sec}s")

    async def _recover_dead_session(
        self,
        session: TmuxSession,
        *,
        command: str,
        error: Exception | None = None,
    ) -> str:
        """Start a fresh shell and report that the interrupted command is ambiguous."""
        session._previous_buffer = None
        await session.start()
        detail = f" Terminal error: {error}" if error is not None else ""
        return (
            "ERROR: The persistent terminal shell exited while executing the "
            "previous command. A fresh shell was started, but the command may "
            "have partially completed and shell-local state such as the working "
            "directory, exported variables, and shell options was lost. Inspect "
            "the workspace before continuing; the command was not replayed."
            f"{detail}\nInterrupted command:\n{command}"
        )

    def _completion_marker(self, sequence: int) -> str:
        """Return one runtime-scoped shell completion marker."""
        return f"{_MARKER_PREFIX}{self._marker_nonce}_{sequence}__"

    def _completion_marker_command(self, sequence: int) -> str:
        """Print the marker without embedding its complete text in terminal input."""
        return (
            "printf '\\n%s%s%s%s\\n' "
            f"'{_MARKER_PREFIX}' '{self._marker_nonce}' '_{sequence}' '__'\n"
        )

    async def _execute_commands(
        self,
        commands: list[Command],
        session: TmuxSession,
    ) -> tuple[bool, str]:
        """Execute commands with marker-based polling for early completion detection.

        Sends a unique echo marker after each command and returns when the marker
        appears or duration_sec elapses.
        """
        for command in commands:
            if command.keystrokes.strip() == "C-c":
                try:
                    await session.send_keys(
                        "C-c",
                        block=False,
                        min_timeout_sec=min(0.2, command.duration_sec),
                    )
                except RuntimeError as exc:
                    if await session.is_session_alive():
                        raise
                    recovered = await self._recover_dead_session(
                        session,
                        command=command.keystrokes,
                        error=exc,
                    )
                    return False, recovered
                continue
            if command.keystrokes.strip() == "C-d":
                return (
                    False,
                    "REJECTED: C-d would send EOF to the persistent shell and "
                    "terminate it. Use C-c to interrupt foreground work, or run "
                    "exit inside an explicit subshell when only a child process "
                    "should terminate.",
                )
            self._marker_seq += 1
            marker = self._completion_marker(self._marker_seq)
            start = time.monotonic()

            try:
                await session.send_keys(
                    _PERSISTENT_SHELL_PREAMBLE,
                    block=False,
                    min_timeout_sec=0.0,
                )
                await session.send_keys(
                    command.keystrokes,
                    block=False,
                    min_timeout_sec=0.0,
                )
                marker_command = self._completion_marker_command(self._marker_seq)
                if command.keystrokes and not command.keystrokes.endswith("\n"):
                    marker_command = f"\n{marker_command}"
                # Send marker: will execute when shell returns after command
                await session.send_keys(
                    marker_command,
                    block=False,
                    min_timeout_sec=0.0,
                )
            except RuntimeError as exc:
                if await session.is_session_alive():
                    raise
                recovered = await self._recover_dead_session(
                    session,
                    command=command.keystrokes,
                    error=exc,
                )
                return False, recovered

            # Poll for marker, exit early if found before duration
            await asyncio.sleep(min(0.3, command.duration_sec))
            while time.monotonic() - start < command.duration_sec:
                try:
                    pane_content = await session.capture_pane()
                except RuntimeError as exc:
                    if await session.is_session_alive():
                        raise
                    recovered = await self._recover_dead_session(
                        session,
                        command=command.keystrokes,
                        error=exc,
                    )
                    return False, recovered
                if marker in pane_content:
                    break
                if not pane_content and not await session.is_session_alive():
                    recovered = await self._recover_dead_session(
                        session,
                        command=command.keystrokes,
                    )
                    return False, recovered
                await asyncio.sleep(0.5)

            saved = command.duration_sec - (time.monotonic() - start)
            if saved > 0.1:
                self.logger.debug(
                    f"[polling] saved {saved:.1f}s "
                    f"(duration={command.duration_sec:.1f}s) "
                    f"cmd={command.keystrokes!r}"
                )

        # Filter out marker lines from output so LLM sees clean output
        output = await session.get_incremental_output()
        markers = {self._completion_marker(seq) for seq in range(1, self._marker_seq + 1)}
        lines = output.split("\n")
        lines = [line for line in lines if not any(marker in line for marker in markers)]
        output = "\n".join(lines)
        return False, self._limit_output_length(output)

    @staticmethod
    def name() -> str:
        return "terminus-boxbox"

    def version(self) -> str | None:
        return "1.0.0"

    def system_prompt(self) -> str:
        """Return the system prompt installed during agent-session restoration."""
        return self._system_prompt

    @property
    def review_chat_state(self) -> dict[str, Any] | None:
        """Return the continuing review Chat state."""
        return self._review_chat_state

    @review_chat_state.setter
    def review_chat_state(self, state: dict[str, Any] | None) -> None:
        self._review_chat_state = copy.deepcopy(state)

    async def ensure_agent_session(self) -> None:
        """Restart the active terminal if its persistent shell exited."""
        if self._session is None:
            raise RuntimeError("Active TerminusBoxBox has no target session")
        if not await self._session.is_session_alive():
            await self._session.start()

    async def review(
        self,
        environment: BaseEnvironment,
        context: AgentContext,
        *,
        sequence: int,
        reviewer: Any,
        fault_report: FaultReport | None,
    ) -> ReviewResult:
        """Run evolvable review policy and candidate preparation."""
        return await review.run(
            self,
            environment,
            context,
            sequence=sequence,
            reviewer=reviewer,
            fault_report=fault_report,
            feedback_enabled=(fault_report is None and self._runtime_trap == RuntimeTrap.BOXBOX),
        )

    # === Runtime context switch ===

    def export_state(self) -> RuntimeState:
        """Export target/review continuity without exposing schema to Kernel."""
        target = self._pending_chat_state
        if target is None:
            target = {
                "schema_version": 1,
                "messages": [{"role": "system", "content": self.system_prompt()}],
            }
        return RuntimeState.capture(
            {
                "target": target,
                "review": self._review_chat_state,
                "review_trajectory": {
                    "sequence": self._review_trajectory_sequence,
                    "phase": self._review_trajectory_phase,
                    "accepted_sequence": self._accepted_trajectory_sequence,
                    "accepted_offset": self._accepted_trajectory_offset,
                    "last_presented_sequence": self._last_presented_trajectory_sequence,
                    "last_presented_offset": self._last_presented_trajectory_offset,
                },
                "review_feedback_ready": self._review_feedback_ready,
                "review_eligible": self._review_eligible,
                "review_cooldown_until": self._review_cooldown_until,
                "task": self._task_instruction,
            }
        )

    def import_state(self, state: RuntimeState) -> None:
        """Import predecessor runtime state."""
        data = state.data
        target = data.get("target")
        if not isinstance(target, dict):
            raise TypeError("RuntimeState target must be a Chat state dictionary")
        messages = target.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("RuntimeState target Chat has no messages")
        messages[0] = {"role": "system", "content": self.system_prompt()}
        self._pending_chat_state = target
        self._chat = None
        review_state = data.get("review")
        if review_state is not None and not isinstance(review_state, dict):
            raise TypeError("RuntimeState review must be a Chat state dictionary")
        self._review_chat_state = review_state
        review_trajectory = data.get("review_trajectory", {})
        if not isinstance(review_trajectory, dict):
            raise TypeError("RuntimeState review trajectory must be a dictionary")
        sequence = review_trajectory.get("sequence", 0)
        phase = review_trajectory.get("phase", 0)
        legacy_sequence = review_trajectory.get("last_reviewed_sequence", 0)
        legacy_offset = review_trajectory.get("last_reviewed_offset", 0)
        accepted = review_trajectory.get("accepted_sequence", legacy_sequence)
        accepted_offset = review_trajectory.get("accepted_offset", legacy_offset)
        last_presented = review_trajectory.get("last_presented_sequence", legacy_sequence)
        last_presented_offset = review_trajectory.get(
            "last_presented_offset",
            legacy_offset,
        )
        if any(
            type(value) is not int or value < 0
            for value in (
                sequence,
                phase,
                accepted,
                accepted_offset,
                last_presented,
                last_presented_offset,
            )
        ):
            raise ValueError("RuntimeState review trajectory values must be non-negative integers")
        if accepted > last_presented or last_presented > sequence:
            raise ValueError("RuntimeState review trajectory cursors are out of order")
        if accepted_offset > last_presented_offset:
            raise ValueError("RuntimeState review trajectory offsets are out of order")
        self._review_trajectory_sequence = sequence
        self._review_trajectory_phase = phase
        self._accepted_trajectory_sequence = accepted
        self._accepted_trajectory_offset = accepted_offset
        self._last_presented_trajectory_sequence = last_presented
        self._last_presented_trajectory_offset = last_presented_offset
        review_feedback_ready = data.get("review_feedback_ready", False)
        if type(review_feedback_ready) is not bool:
            raise ValueError("RuntimeState review feedback flag must be a boolean")
        self._review_feedback_ready = review_feedback_ready
        review_eligible = data.get("review_eligible", False)
        if type(review_eligible) is not bool:
            raise ValueError("RuntimeState review eligibility flag must be a boolean")
        self._review_eligible = review_eligible
        review_cooldown_until = data.get("review_cooldown_until")
        if review_cooldown_until is not None and (
            type(review_cooldown_until) not in (int, float)
            or not 0 <= float(review_cooldown_until) < 1e20
        ):
            raise ValueError("RuntimeState review cooldown deadline must be non-negative")
        self._review_cooldown_until = (
            float(review_cooldown_until) if review_cooldown_until is not None else None
        )
        self._task_instruction = data.get("task")

    def release_session(self) -> Any:
        """Release the live target session for Kernel-controlled activation."""
        if self._session is None:
            raise RuntimeError("Active TerminusBoxBox has no live target session")
        session = self._session
        self._session = None
        return session

    def attach_session(self, session: Any) -> Any:
        """Attach the live target session after state validation."""
        if self._session is not None:
            raise RuntimeError("Candidate TerminusBoxBox already owns a target session")
        self._session = session
        return session

    async def restart_session(self, session: Any) -> Any:
        """Discard a faulting pane and start a fresh shell with the same session."""
        if not isinstance(session, TmuxSession):
            raise TypeError("TerminusBoxBox can restart only a TmuxSession")
        session_name = getattr(session, "_session_name", None)
        user = getattr(session, "_user", None)
        if not isinstance(session_name, str) or not session_name:
            raise RuntimeError("Target TmuxSession has no session name")
        killed = await session.environment.exec(
            command=f"tmux kill-session -t {shlex.quote(session_name)} 2>/dev/null || true",
            user=user,
        )
        if killed.return_code != 0:
            raise RuntimeError(
                killed.stdout or killed.stderr or "failed to discard target tmux session"
            )
        session._previous_buffer = None
        await session.start()
        return session

    def prepare_continuation(self) -> str:
        """Pin the selected system prompt and prepare the next target segment."""
        if self._pending_chat_state is None:
            raise RuntimeError("Selected TerminusBoxBox has no target Chat state")
        messages = self._pending_chat_state.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("Selected TerminusBoxBox target Chat has no messages")
        messages[0] = {"role": "system", "content": self.system_prompt()}
        if self._review_feedback_ready:
            self._review_feedback_ready = False
            return (
                f"Read {review.FEEDBACK_FILE}. Use that review feedback as evidence, "
                "then continue the original task."
            )
        return CONTINUATION_PROMPT

    # === End runtime context switch ===

    def configure_target_phase(
        self,
        *,
        boxbox_enabled: bool,
    ) -> None:
        """Configure target completion and optional internal self-review traps."""
        self._completion_tool_name = self._target_completion_name
        self._completion_tool_description = self._target_completion_description
        self._review_phase = False
        self._review_context_source = None
        self._boxbox_enabled = boxbox_enabled
        self._system_prompt = self._base_system_prompt
        if boxbox_enabled:
            self._system_prompt = f"{self._base_system_prompt}\n\n{self._boxbox_system_prompt}"
        if self._pending_chat_state is not None:
            messages = self._pending_chat_state.get("messages")
            if not isinstance(messages, list) or not messages:
                raise RuntimeError("TerminusBoxBox target Chat has no messages")
            messages[0] = {"role": "system", "content": self._system_prompt}

    def configure_review_phase(
        self,
        *,
        policy: str,
    ) -> None:
        """Configure a fresh runtime instance for harness review."""
        self._review_phase = True
        self._system_prompt = f"{self._review_system_prompt}\n\n{policy}"
        self._completion_tool_name = "finish"
        self._completion_tool_description = "Call this when self-review is complete."
        self._boxbox_enabled = False

    def boxbox_policy(self) -> str:
        """Return the policy selected for the next independent review."""
        if self._review_policy_override is not None:
            return self._review_policy_override
        return (Path(__file__).parent / "skills" / "self_review" / "SKILL.md").read_text(
            encoding="utf-8"
        )

    def override_boxbox_policy(self, policy: str) -> None:
        """Select the configured initial review policy."""
        if not policy.strip():
            raise ValueError("Self-review policy override must be non-empty")
        self._review_policy_override = policy

    def override_target_system_prompt(self, prompt: str) -> None:
        """Select the configured initial task prompt."""
        if not prompt.strip():
            raise ValueError("Target system prompt override must be non-empty")
        self._base_system_prompt = prompt
        self._system_prompt = prompt

    def set_task_instruction(self, instruction: str) -> None:
        """Set the task retained across continuation prompts."""
        if not instruction.strip():
            raise ValueError("Task instruction must be non-empty")
        self._task_instruction = instruction

    @property
    def task_instruction(self) -> str:
        """Return the original target task for task-grounded review."""
        if self._task_instruction is None:
            raise RuntimeError("TerminusBoxBox target task is unavailable")
        return self._task_instruction

    def mark_review_feedback_ready(self) -> None:
        """Mark the latest voluntary review feedback for Agent handoff."""
        self._review_feedback_ready = True

    def _append_review_trajectory(self, context: AgentContext) -> None:
        """Append one target phase to the cross-run review trajectory."""
        self._review_trajectory_phase += 1
        phase = self._review_trajectory_phase
        records: list[dict[str, Any]] = []
        for step in self._trajectory_steps:
            self._review_trajectory_sequence += 1
            records.append(
                {
                    "schema_version": 1,
                    "sequence": self._review_trajectory_sequence,
                    "phase": phase,
                    "kind": "step",
                    "step": step.model_dump(exclude_none=True, mode="json"),
                }
            )
        self._review_trajectory_sequence += 1
        records.append(
            {
                "schema_version": 1,
                "sequence": self._review_trajectory_sequence,
                "phase": phase,
                "kind": "phase_end",
                "final_metrics": {
                    "total_prompt_tokens": context.n_input_tokens,
                    "total_completion_tokens": context.n_output_tokens,
                    "total_cached_tokens": context.n_cache_tokens,
                    "total_cost_usd": context.cost_usd,
                },
            }
        )
        journal = self.logs_dir / REVIEW_TRAJECTORY_NAME
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as stream:
            for record in records:
                stream.write(f"{json.dumps(record, ensure_ascii=True, separators=(',', ':'))}\n")

    def _review_window(
        self,
        *,
        from_sequence: int,
        from_offset: int,
        through_sequence: int,
        through_offset: int,
    ) -> ReviewContextWindow:
        """Index one bounded slice of the target trajectory journal."""
        journal = self.logs_dir / REVIEW_TRAJECTORY_NAME
        if not journal.is_file():
            if through_sequence or through_offset:
                raise RuntimeError("Review trajectory journal is missing")
            return ReviewContextWindow(
                first_sequence=None,
                last_sequence=None,
                record_count=0,
                phases=(),
            )
        journal_size = journal.stat().st_size
        if (
            from_offset > through_offset
            or through_offset > journal_size
            or from_sequence > through_sequence
        ):
            raise RuntimeError("Review trajectory cursor exceeds the journal size")
        with journal.open("rb") as stream:
            stream.seek(from_offset)
            payload = stream.read(through_offset - from_offset)
        if payload and not payload.endswith(b"\n"):
            raise ValueError("Review trajectory ends with an incomplete record")
        latest_sequence = from_sequence
        first_sequence: int | None = None
        record_count = 0
        phase_steps: dict[int, int] = {}
        completed_phases: set[int] = set()
        for line_number, raw_line in enumerate(payload.splitlines(), start=1):
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"Review trajectory delta line {line_number} is invalid JSON"
                ) from error
            sequence = record.get("sequence")
            if type(sequence) is not int or sequence <= latest_sequence:
                raise ValueError("Review trajectory sequences must increase")
            phase = record.get("phase")
            if type(phase) is not int or phase <= 0:
                raise ValueError("Review trajectory phases must be positive integers")
            kind = record.get("kind")
            if kind == "step":
                phase_steps[phase] = phase_steps.get(phase, 0) + 1
            elif kind == "phase_end":
                completed_phases.add(phase)
                phase_steps.setdefault(phase, 0)
            else:
                raise ValueError("Review trajectory record kind is invalid")
            if first_sequence is None:
                first_sequence = sequence
            latest_sequence = sequence
            record_count += 1
        if latest_sequence != through_sequence:
            raise RuntimeError("Review trajectory journal and runtime state disagree")
        return ReviewContextWindow(
            first_sequence=first_sequence,
            last_sequence=latest_sequence if record_count else None,
            record_count=record_count,
            phases=tuple(
                ReviewContextPhase(
                    phase=phase,
                    step_count=step_count,
                    complete=phase in completed_phases,
                )
                for phase, step_count in sorted(phase_steps.items())
            ),
        )

    def capture_review_context(self) -> ReviewContextCapture:
        """Capture boundaries for two logical views of the canonical trajectory."""
        through_sequence = self._review_trajectory_sequence
        journal = self.logs_dir / REVIEW_TRAJECTORY_NAME
        through_offset = journal.stat().st_size if journal.is_file() else 0
        epoch = self._review_window(
            from_sequence=self._accepted_trajectory_sequence,
            from_offset=self._accepted_trajectory_offset,
            through_sequence=through_sequence,
            through_offset=through_offset,
        )
        delta = self._review_window(
            from_sequence=self._last_presented_trajectory_sequence,
            from_offset=self._last_presented_trajectory_offset,
            through_sequence=through_sequence,
            through_offset=through_offset,
        )
        return ReviewContextCapture(
            through_sequence=through_sequence,
            through_offset=through_offset,
            accepted_sequence=self._accepted_trajectory_sequence,
            accepted_offset=self._accepted_trajectory_offset,
            presented_sequence=self._last_presented_trajectory_sequence,
            presented_offset=self._last_presented_trajectory_offset,
            epoch=epoch,
            delta=delta,
        )

    def reconcile_review_trajectory(self) -> None:
        """Adopt records appended by a failed provisional runtime."""
        journal = self.logs_dir / REVIEW_TRAJECTORY_NAME
        if not journal.is_file():
            if self._review_trajectory_sequence or self._review_trajectory_phase:
                raise RuntimeError("Review trajectory journal is missing")
            return
        payload = journal.read_bytes()
        if payload and not payload.endswith(b"\n"):
            raise ValueError("Review trajectory ends with an incomplete record")

        latest_sequence = 0
        latest_phase = 0
        for line_number, raw_line in enumerate(payload.splitlines(), start=1):
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"Review trajectory line {line_number} is invalid JSON"
                ) from error
            sequence = record.get("sequence")
            phase = record.get("phase")
            if type(sequence) is not int or sequence <= latest_sequence:
                raise ValueError("Review trajectory sequences must increase")
            if type(phase) is not int or phase <= 0 or phase < latest_phase:
                raise ValueError("Review trajectory phases must be positive and ordered")
            if record.get("kind") not in {"step", "phase_end"}:
                raise ValueError("Review trajectory record kind is invalid")
            latest_sequence = sequence
            latest_phase = phase

        if (
            self._accepted_trajectory_sequence > latest_sequence
            or self._last_presented_trajectory_sequence > latest_sequence
            or self._accepted_trajectory_offset > len(payload)
            or self._last_presented_trajectory_offset > len(payload)
        ):
            raise RuntimeError("Review trajectory rollback cursor exceeds the journal")
        self._review_trajectory_sequence = latest_sequence
        self._review_trajectory_phase = latest_phase

    def _validate_review_context_cursor(
        self,
        through_sequence: int,
        through_offset: int,
    ) -> None:
        """Validate a captured target-trajectory position."""
        if (
            type(through_sequence) is not int
            or through_sequence < 0
            or through_sequence > self._review_trajectory_sequence
            or type(through_offset) is not int
            or through_offset < 0
        ):
            raise ValueError("Invalid review trajectory cursor")
        journal = self.logs_dir / REVIEW_TRAJECTORY_NAME
        journal_size = journal.stat().st_size if journal.is_file() else 0
        if through_offset > journal_size:
            raise ValueError("Invalid review trajectory offset")

    def _review_cooldown_remaining_sec(self) -> float:
        """Return wall-clock time remaining before another voluntary review."""
        if self._review_cooldown_until is None:
            return 0.0
        return max(0.0, self._review_cooldown_until - time.time())

    def mark_review_context_presented(
        self,
        through_sequence: int,
        through_offset: int,
    ) -> None:
        """Advance only the delta cursor after a completed reviewer judgment."""
        self._validate_review_context_cursor(through_sequence, through_offset)
        if (
            through_sequence < self._last_presented_trajectory_sequence
            or through_offset < self._last_presented_trajectory_offset
        ):
            raise ValueError("Review context presentation cursor cannot move backwards")
        self._last_presented_trajectory_sequence = through_sequence
        self._last_presented_trajectory_offset = through_offset
        self._review_eligible = False
        self._review_cooldown_until = time.time() + REVIEW_COOLDOWN_SEC

    def mark_harness_context_accepted(
        self,
        through_sequence: int,
        through_offset: int,
    ) -> None:
        """Start a new trajectory epoch after Kernel accepts this harness."""
        self._validate_review_context_cursor(through_sequence, through_offset)
        if (
            through_sequence > self._last_presented_trajectory_sequence
            or through_offset > self._last_presented_trajectory_offset
        ):
            raise ValueError("Accepted harness boundary was not presented to review")
        self._accepted_trajectory_sequence = through_sequence
        self._accepted_trajectory_offset = through_offset
        self._last_presented_trajectory_sequence = through_sequence
        self._last_presented_trajectory_offset = through_offset

    async def run_until_trap(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> RuntimeTrap | None:
        """Run one runtime phase and return any synchronous Kernel trap."""
        self._runtime_trap = None
        if self._pending_chat_state is None:
            self._pending_chat_state = {
                "schema_version": 1,
                "messages": [{"role": "system", "content": self.system_prompt()}],
            }
        try:
            await super().run(instruction, environment, context)
        finally:
            if self._chat is not None:
                self._pending_chat_state = self._chat.dump_state()
            self._append_review_trajectory(context)
        return self._runtime_trap

    def _get_parser(self):
        """Return None since we use native tool calling instead of parsing."""
        return None

    def _get_prompt_template_path(self) -> Path:
        """Return the path to the prompt template for native tool use."""
        return Path(__file__).parent / "prompt-templates" / "task.txt"

    def _get_error_response_type(self) -> str:
        """Return error response type for native tool use."""
        return "response with valid tool calls"

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions with this runtime's phase-ending action."""
        tools = []
        for tool in TOOLS:
            name = tool["function"]["name"]
            if name == "boxbox":
                if self._boxbox_enabled:
                    tools.append(tool)
            elif name != "finish":
                tools.append(tool)
            else:
                tools.append(
                    {
                        **tool,
                        "function": {
                            **tool["function"],
                            "name": self._completion_tool_name,
                            "description": self._completion_tool_description,
                        },
                    }
                )
        if self._review_phase:
            tools.append(review.REVIEW_CONTEXT_TOOL)
        return tools

    def _setup_episode_logging(
        self, logging_dir: Path | None, episode: int
    ) -> tuple[Path | None, Path | None, Path | None]:
        """Create the episode directory and return its debug, prompt, and response paths."""
        if logging_dir is None:
            return None, None, None
        episode_logging_dir = logging_dir / f"episode-{episode}"
        episode_logging_dir.mkdir(parents=True, exist_ok=True)
        return (
            episode_logging_dir / "debug.json",
            episode_logging_dir / "prompt.txt",
            episode_logging_dir / "response.txt",
        )

    def _resolve_completion_request(
        self,
        trap: RuntimeTrap | None,
        output: str,
    ) -> tuple[str, bool]:
        """Resolve a trap request and report whether the runtime should return."""
        if trap is None:
            return output, False
        self._runtime_trap = trap
        return output, True

    def _trajectory_action_name(self, trap: RuntimeTrap) -> str:
        """Return the stable trajectory name for a handled runtime trap."""
        if trap == RuntimeTrap.COMPLETE:
            return self._completion_tool_name
        return trap.value

    def _limit_output_length(self, output: str, max_bytes: int = 30000) -> str:
        return super()._limit_output_length(output, max_bytes)

    def _extract_tool_calls(self, response) -> list[dict[str, Any]]:
        """Extract tool calls from litellm response."""
        tool_calls = []
        try:
            message = response.choices[0].message
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    )
        except (AttributeError, IndexError):
            pass
        return tool_calls

    def _extract_usage_info(self, response) -> UsageInfo | None:
        """Extract usage info from litellm response."""
        try:
            usage = response.usage
            if usage:
                usage_data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
                details = (
                    usage_data.get("prompt_tokens_details")
                    or usage_data.get("input_tokens_details") or {}
                )
                hidden = getattr(response, "_hidden_params", {}) or {}
                return UsageInfo(
                    prompt_tokens=int(usage_data.get("prompt_tokens") or usage_data.get("input_tokens") or 0),
                    completion_tokens=int(usage_data.get("completion_tokens") or usage_data.get("output_tokens") or 0),
                    cache_tokens=int(details.get("cached_tokens") or 0),
                    cost_usd=hidden.get("response_cost") or 0.0,
                )
        except (AttributeError, TypeError, ValueError):
            pass
        return None

    def _parse_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> tuple[
        list[Command],
        RuntimeTrap | None,
        str,
        str,
        str,
        ImageReadRequest | None,
        str | None,
    ]:
        """Parse tool calls into commands.

        Returns:
            Commands, runtime trap, feedback, analysis, plan, image request,
            and direct tool observation.
        """
        commands = []
        trap = None
        feedback = ""
        analysis = ""
        plan = ""
        image_read = None
        direct_observation = None

        if not tool_calls:
            feedback = (
                "WARNINGS: Your response contained no tool calls. "
                "Please use execute_commands to run commands"
            )
            feedback += (
                ", or boxbox to review your trajectories and harness."
                if self._boxbox_enabled else "."
            )
            return commands, trap, feedback, analysis, plan, image_read, direct_observation

        if len(tool_calls) > 1 and any(
            tool_call.get("function", {}).get("name") == "review_context"
            for tool_call in tool_calls
        ):
            feedback = (
                "WARNINGS: Call review_context by itself. "
                "Use its result before choosing another tool."
            )
            return commands, trap, feedback, analysis, plan, image_read, direct_observation

        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name", "")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")

            try:
                if isinstance(arguments_str, str):
                    arguments = json.loads(arguments_str)
                else:
                    arguments = arguments_str
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse tool arguments: {arguments_str}")
                continue

            if function_name == "execute_commands":
                # Extract analysis and plan
                analysis = arguments.get("analysis", "")
                plan = arguments.get("plan", "")

                # Extract commands array
                cmds = arguments.get("commands", [])
                for cmd in cmds:
                    keystrokes = cmd.get("keystrokes", "")
                    duration = cmd.get("duration", 1.0)
                    commands.append(
                        Command(
                            keystrokes=keystrokes,
                            duration_sec=min(duration, 60),
                        )
                    )
            elif function_name == self._completion_tool_name:
                trap = RuntimeTrap.COMPLETE
            elif function_name == "boxbox" and self._boxbox_enabled:
                cooldown_remaining = self._review_cooldown_remaining_sec()
                if cooldown_remaining > 0:
                    remaining_minutes = max(1, int((cooldown_remaining + 59) // 60))
                    feedback = (
                        "WARNINGS: Another harness review is available after the "
                        f"30-minute post-review cooldown. About {remaining_minutes} "
                        "minute(s) remain. Continue substantive target work and use the "
                        "active harness capability before requesting another review."
                    )
                elif self._review_eligible:
                    trap = RuntimeTrap.BOXBOX
                else:
                    feedback = (
                        "WARNINGS: The recent Target trajectory does not yet support "
                        "another harness review. Continue substantive target work until "
                        "new evidence reveals a useful adaptation opportunity."
                    )
            elif function_name == "review_context" and self._review_phase:
                direct_observation = review.handle_context_tool(
                    self._review_context_source,
                    arguments,
                )
            elif function_name == "image_read":
                # Extract image read request
                file_path = arguments.get("file_path", "")
                instruction = arguments.get("image_read_instruction", "")
                if file_path and instruction:
                    image_read = ImageReadRequest(
                        file_path=file_path,
                        image_read_instruction=instruction,
                    )
                else:
                    feedback = (
                        "WARNINGS: image_read requires both file_path and "
                        "image_read_instruction arguments."
                    )
            else:
                # Unknown function name - provide feedback
                available = ["execute_commands", "image_read", self._completion_tool_name]
                if self._boxbox_enabled:
                    available.append("boxbox")
                if self._review_phase:
                    available.append("review_context")
                feedback = (
                    f"WARNINGS: Unknown function '{function_name}'. "
                    f"Please use one of: {', '.join(available)}."
                )
                self.logger.warning(f"Unknown function called: {function_name}")

        return (
            commands,
            trap,
            feedback,
            analysis,
            plan,
            image_read,
            direct_observation,
        )

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=5, min=5, max=60),
        retry=(
            retry_if_exception_type(Exception)
            & retry_if_not_exception_type(
                (
                    BadRequestError,
                    LiteLLMAuthenticationError,
                    ContextLengthExceededError,
                    OutputLengthExceededError,
                )
            )
        ),
        reraise=True,
    )
    async def _call_llm_for_image(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> object:
        """Call litellm.acompletion with retry for transient errors.

        Retries on rate limit, network, and server errors.
        Does NOT retry on BadRequestError (e.g. image too large).
        """
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": 900,  # 15 minutes timeout, retry on timeout
            "drop_params": True,
        }
        api_base = getattr(self._llm, "_api_base", None)
        if api_base:
            kwargs["api_base"] = api_base
        kwargs.update(getattr(self._llm, "_llm_kwargs", {}))
        # Use the provider's default reasoning effort for image analysis.
        return await litellm.acompletion(**kwargs)

    async def _execute_image_read(
        self,
        image_read: ImageReadRequest,
        chat: Chat,
        original_instruction: str = "",
    ) -> str:
        """Execute a file read command to analyze an image file.

        Reads the file from the container via base64, sends it as a multimodal
        message to the LLM, and returns the analysis result.
        """
        if self._session is None:
            raise RuntimeError("Session is not set")

        file_path = image_read.file_path

        # Read image from container as base64 via harbor environment exec
        result = await self._with_block_timeout(
            self._session.environment.exec(command=f"base64 {file_path}")
        )
        if result.return_code != 0:
            error_output = result.stderr or ""
            return f"ERROR: Failed to read file '{file_path}': {error_output}"

        b64 = (result.stdout or "").replace("\n", "")

        # Determine MIME type from file extension
        ext = Path(file_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(ext)
        if mime is None:
            return (
                f"ERROR: Unsupported image format '{ext}'. "
                f"Convert to PNG first (e.g. convert image{ext} to image.png), "
                f"then use `image_read` on the PNG file."
            )

        # Construct multimodal user message
        multimodal_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": image_read.image_read_instruction},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            },
        ]

        messages = add_anthropic_caching(multimodal_messages, self._model_name)

        # Call LLM with retry logic
        try:
            response = await self._call_llm_for_image(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
                max_tokens=self._llm.get_model_output_limit(),
            )
        except Exception as e:
            return f"ERROR: {e}"

        response_text = response["choices"][0]["message"]["content"]

        # Manually update token counts from litellm response
        usage = response.get("usage", {})
        if usage:
            chat._cumulative_input_tokens += usage.get("prompt_tokens", 0)
            chat._cumulative_output_tokens += usage.get("completion_tokens", 0)
            prompt_details = usage.get("prompt_tokens_details")
            cached = getattr(prompt_details, "cached_tokens", 0) if prompt_details else 0
            chat._cumulative_cache_tokens += cached or 0

        return f"File Read Result for '{file_path}':\n{response_text}"

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=5, min=5, max=60),
        retry=(
            retry_if_exception_type(Exception)
            & retry_if_not_exception_type(
                (
                    BadRequestError,
                    LiteLLMAuthenticationError,
                    ContextLengthExceededError,
                    OutputLengthExceededError,
                )
            )
        ),
        reraise=True,
    )
    async def _call_llm_with_tools(
        self,
        messages: list[dict],
    ) -> ToolCallResponse:
        """Call LLM directly with tools parameter.

        This bypasses harbor's Chat class to get access to tool_calls.
        """
        # Apply Anthropic caching
        messages = add_anthropic_caching(messages, self._model_name)

        # Build completion kwargs
        completion_kwargs = {
            "model": self._model_name,
            "messages": messages,
            "temperature": self._temperature,
            "tools": self._get_tool_definitions(),
            "timeout": 900,  # 15 minutes timeout, retry on timeout
            "drop_params": True,
        }

        api_base = getattr(self._llm, "_api_base", None)
        if api_base:
            completion_kwargs["api_base"] = api_base
        completion_kwargs.update(getattr(self._llm, "_llm_kwargs", {}))
        if getattr(self._llm, "_use_responses_api", False):
            completion_kwargs["use_responses_api"] = True

        # Add reasoning effort if available
        # When reasoning_effort is set, temperature MUST be 1 (API requirement)
        if self._reasoning_effort:
            completion_kwargs["reasoning_effort"] = self._reasoning_effort
            completion_kwargs["temperature"] = 1

        try:
            response = await litellm.acompletion(**completion_kwargs)
        except LiteLLMContextWindowExceededError:
            raise ContextLengthExceededError()

        # Extract response data
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = self._extract_tool_calls(response)
        usage_info = self._extract_usage_info(response)

        # Check for truncation
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            raise OutputLengthExceededError(
                "Response was truncated due to max tokens limit",
                truncated_response=content,
            )

        # Extract reasoning content (for models that support it)
        reasoning_content = None
        if hasattr(message, "reasoning_content"):
            reasoning_content = message.reasoning_content

        return ToolCallResponse(
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
            usage=usage_info,
        )

    @staticmethod
    def _compact_chat_after_policy_rejection(chat: Chat) -> None:
        """Keep task grounding while dropping potentially flagged tool history."""
        messages = chat.messages
        compact: list[dict[str, Any]] = []
        system = next(
            (message for message in messages if message.get("role") == "system"),
            None,
        )
        first_user = next(
            (message for message in messages if message.get("role") == "user"),
            None,
        )
        for message in (system, first_user):
            if message is not None:
                compact.append(copy.deepcopy(message))
        if not compact:
            raise RuntimeError("Cannot recover policy-rejected Chat without task context")
        chat._messages = compact
        chat.reset_response_chain()

    async def _handle_llm_interaction(
        self,
        chat: Chat,
        prompt: str,
        logging_paths: tuple[Path | None, Path | None, Path | None],
        original_instruction: str = "",
        session: TmuxSession | None = None,
    ) -> tuple[
        list[Command],
        RuntimeTrap | None,
        str,
        str,
        str,
        LLMResponse,
        ImageReadRequest | None,
        str | None,
        list[dict[str, Any]],
    ]:
        """Handle LLM interaction using native tool calling.

        This overrides the parent's _handle_llm_interaction to use native tools
        instead of JSON/XML parsing.
        """
        _, prompt_path, response_path = logging_paths

        if prompt_path is not None:
            prompt_path.write_text(prompt)

        # Build messages from chat history + new prompt
        messages = chat.messages.copy()
        messages.append({"role": "user", "content": prompt})

        try:
            start_time = time.time()
            tool_response = await self._call_llm_with_tools(messages)
            end_time = time.time()
            request_time_ms = (end_time - start_time) * 1000
            self._api_request_times.append(request_time_ms)

            # Update chat history
            assistant_message = {"role": "assistant", "content": tool_response.content}
            if tool_response.tool_calls:
                assistant_message["tool_calls"] = tool_response.tool_calls

            chat._messages.append({"role": "user", "content": prompt})
            chat._messages.append(assistant_message)

            if tool_response.tool_calls:
                for tool_call in tool_response.tool_calls:
                    chat._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": "executed",
                        }
                    )
                chat.reset_response_chain()

            # Update cumulative metrics
            if tool_response.usage:
                chat._cumulative_input_tokens += tool_response.usage.prompt_tokens
                chat._cumulative_output_tokens += tool_response.usage.completion_tokens
                chat._cumulative_cache_tokens += tool_response.usage.cache_tokens
                chat._cumulative_cost += tool_response.usage.cost_usd

        except ContentPolicyViolationError:
            self.logger.warning("Content-policy rejection; retrying from compact task context")
            self._compact_chat_after_policy_rejection(chat)
            recovery_prompt = (
                "Continue the original task from the current terminal state. "
                "Use the available tools to inspect the workspace and take the "
                "next evidence-backed action without repeating earlier transcript."
            )
            messages = chat.messages.copy()
            messages.append({"role": "user", "content": recovery_prompt})

            start_time = time.time()
            tool_response = await self._call_llm_with_tools(messages)
            end_time = time.time()
            self._api_request_times.append((end_time - start_time) * 1000)

            assistant_message = {
                "role": "assistant",
                "content": tool_response.content,
            }
            if tool_response.tool_calls:
                assistant_message["tool_calls"] = tool_response.tool_calls
            chat._messages.append({"role": "user", "content": recovery_prompt})
            chat._messages.append(assistant_message)

            if tool_response.tool_calls:
                for tool_call in tool_response.tool_calls:
                    chat._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": "executed",
                        }
                    )
                chat.reset_response_chain()

            if tool_response.usage:
                chat._cumulative_input_tokens += tool_response.usage.prompt_tokens
                chat._cumulative_output_tokens += tool_response.usage.completion_tokens
                chat._cumulative_cache_tokens += tool_response.usage.cache_tokens
                chat._cumulative_cost += tool_response.usage.cost_usd

        except ContextLengthExceededError:
            if not self._enable_summarize:
                self.logger.debug("Context length exceeded and summarization is OFF.")
                raise

            self.logger.debug("Context length exceeded. Using fallback summarization.")

            if session is None:
                raise RuntimeError("Cannot handle context length error without session")

            self._unwind_messages_to_free_tokens(chat, target_free_tokens=4000)

            summary_prompt = None
            try:
                summary_prompt, subagent_refs = await self._with_block_timeout(
                    self._summarize(chat, original_instruction, session)
                )
                self._pending_subagent_refs = subagent_refs
                self._pending_handoff_prompt = summary_prompt
            except Exception as e:
                self.logger.debug(f"SUMMARIZATION failed: {e}")

            if summary_prompt is None:
                current_screen = await self._with_block_timeout(
                    session.capture_pane(capture_entire=False)
                )
                limited_screen = current_screen[-1000:] if current_screen else ""
                summary_prompt = f"{original_instruction}\n\nCurrent state: {limited_screen}"

            # Retry with summarized context
            messages = chat.messages.copy()
            messages.append({"role": "user", "content": summary_prompt})

            start_time = time.time()
            tool_response = await self._call_llm_with_tools(messages)
            end_time = time.time()
            request_time_ms = (end_time - start_time) * 1000
            self._api_request_times.append(request_time_ms)

            # Update chat history
            assistant_message = {"role": "assistant", "content": tool_response.content}
            if tool_response.tool_calls:
                assistant_message["tool_calls"] = tool_response.tool_calls

            chat._messages.append({"role": "user", "content": summary_prompt})
            chat._messages.append(assistant_message)

            if tool_response.tool_calls:
                for tool_call in tool_response.tool_calls:
                    chat._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": "executed",
                        }
                    )
                chat.reset_response_chain()

            # Update cumulative metrics
            if tool_response.usage:
                chat._cumulative_input_tokens += tool_response.usage.prompt_tokens
                chat._cumulative_output_tokens += tool_response.usage.completion_tokens
                chat._cumulative_cache_tokens += tool_response.usage.cache_tokens
                chat._cumulative_cost += tool_response.usage.cost_usd

        except OutputLengthExceededError as e:
            self.logger.debug(f"Output length exceeded: {e}")

            error_msg = (
                "ERROR!! Your response was truncated. "
                "Please provide a shorter response with fewer commands."
            )

            chat._messages.extend(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "[truncated]"},
                    {"role": "user", "content": error_msg},
                ]
            )
            chat.reset_response_chain()

            # Retry
            messages = chat.messages.copy()
            start_time = time.time()
            tool_response = await self._call_llm_with_tools(messages)
            end_time = time.time()
            self._api_request_times.append((end_time - start_time) * 1000)

            assistant_message = {"role": "assistant", "content": tool_response.content}
            if tool_response.tool_calls:
                assistant_message["tool_calls"] = tool_response.tool_calls
            chat._messages.append(assistant_message)

            if tool_response.tool_calls:
                for tool_call in tool_response.tool_calls:
                    chat._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": "executed",
                        }
                    )
                chat.reset_response_chain()

            # Update cumulative metrics
            if tool_response.usage:
                chat._cumulative_input_tokens += tool_response.usage.prompt_tokens
                chat._cumulative_output_tokens += tool_response.usage.completion_tokens
                chat._cumulative_cache_tokens += tool_response.usage.cache_tokens
                chat._cumulative_cost += tool_response.usage.cost_usd

        # Log response
        if response_path is not None:
            response_text = (
                f"Content: {tool_response.content or ''}\n\n"
                f"Tool Calls: {json.dumps(tool_response.tool_calls, indent=2)}"
            )
            response_path.write_text(response_text)

        # Parse tool calls into commands
        (
            commands,
            trap,
            feedback,
            analysis,
            plan,
            image_read,
            direct_observation,
        ) = self._parse_tool_calls(tool_response.tool_calls)

        # Wrap the response in the parent agent's LLMResponse interface.
        llm_response = LLMResponse(
            content=tool_response.content or "",
            reasoning_content=tool_response.reasoning_content,
            usage=tool_response.usage,
        )

        return (
            commands,
            trap,
            feedback,
            analysis,
            plan,
            llm_response,
            image_read,
            direct_observation,
            tool_response.tool_calls,
        )

    async def _run_agent_loop(
        self,
        initial_prompt: str,
        chat: Chat,
        logging_dir: Path | None = None,
        original_instruction: str = "",
    ) -> int:
        """Run the agent loop with support for image_read tool."""
        original_instruction = self._task_instruction or original_instruction
        if self._context is None:
            raise RuntimeError("Agent context is not set. This should never happen.")

        if self._session is None:
            raise RuntimeError("Session is not set. This should never happen.")

        prompt = initial_prompt

        self._context.n_input_tokens = 0
        self._context.n_output_tokens = 0
        self._context.n_cache_tokens = 0
        self._context.cost_usd = None

        for episode in range(self._max_episodes):
            self._n_episodes = episode + 1
            if not await self._with_block_timeout(self._session.is_session_alive()):
                raise RuntimeError("The persistent terminal shell exited")

            if original_instruction and self._enable_summarize:
                proactive_summary_result = await self._with_block_timeout(
                    self._check_proactive_summarization(
                        chat,
                        original_instruction,
                        self._session,
                    )
                )
                if proactive_summary_result:
                    prompt, subagent_refs = proactive_summary_result
                    self._pending_subagent_refs = subagent_refs
                    self._pending_handoff_prompt = prompt

            logging_paths = self._setup_episode_logging(logging_dir, episode)

            # Track token counts and cost before this step
            tokens_before_input = chat.total_input_tokens
            tokens_before_output = chat.total_output_tokens
            tokens_before_cache = chat.total_cache_tokens
            cost_before = chat.total_cost

            (
                commands,
                trap,
                feedback,
                analysis,
                plan,
                llm_response,
                image_read,
                direct_observation,
                native_tool_calls,
            ) = await self._handle_llm_interaction(
                chat, prompt, logging_paths, original_instruction, self._session
            )

            # If we have pending subagent refs, add a system step
            if self._pending_subagent_refs:
                self._trajectory_steps.append(
                    Step(
                        step_id=len(self._trajectory_steps) + 1,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        source="system",
                        message="Performed context summarization and handoff to continue task.",
                        observation=Observation(
                            results=[
                                ObservationResult(
                                    subagent_trajectory_ref=self._pending_subagent_refs
                                )
                            ]
                        ),
                    )
                )
                self._pending_subagent_refs = None

            if self._pending_handoff_prompt:
                if self._linear_history:
                    self._split_trajectory_on_summarization(self._pending_handoff_prompt)
                else:
                    self._trajectory_steps.append(
                        Step(
                            step_id=len(self._trajectory_steps) + 1,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            source="user",
                            message=self._pending_handoff_prompt,
                        )
                    )
                self._pending_handoff_prompt = None

            # Create message content
            if self._save_raw_content_in_trajectory:
                message_content = llm_response.content
            else:
                message_parts = []
                if analysis:
                    message_parts.append(f"Analysis: {analysis}")
                if plan:
                    message_parts.append(f"Plan: {plan}")
                message_content = "\n".join(message_parts) if message_parts else ""

            self._context.n_input_tokens = chat.total_input_tokens
            self._context.n_output_tokens = chat.total_output_tokens
            self._context.n_cache_tokens = chat.total_cache_tokens
            self._context.cost_usd = chat.total_cost if chat.total_cost > 0 else None

            if feedback and "ERROR:" in feedback:
                error_prompt = (
                    f"Previous response had parsing errors:\n{feedback}\n\n"
                    f"Please fix these issues and provide a proper "
                    f"{self._get_error_response_type()}."
                )
                prompt = error_prompt
                cache_tokens_used = chat.total_cache_tokens - tokens_before_cache
                step_cost = chat.total_cost - cost_before
                self._trajectory_steps.append(
                    Step(
                        step_id=len(self._trajectory_steps) + 1,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        source="agent",
                        model_name=self._model_name,
                        message=llm_response.content,
                        reasoning_content=llm_response.reasoning_content,
                        observation=Observation(results=[ObservationResult(content=error_prompt)]),
                        metrics=Metrics(
                            prompt_tokens=chat.total_input_tokens - tokens_before_input,
                            completion_tokens=chat.total_output_tokens - tokens_before_output,
                            cached_tokens=cache_tokens_used if cache_tokens_used > 0 else None,
                            cost_usd=step_cost if step_cost > 0 else None,
                            prompt_token_ids=llm_response.prompt_token_ids,
                            completion_token_ids=llm_response.completion_token_ids,
                            logprobs=llm_response.logprobs,
                        ),
                    )
                )
                continue

            if image_read is not None:
                # File read path
                image_read_result = await self._execute_image_read(
                    image_read, chat, original_instruction
                )
                if not self._review_phase:
                    self._review_eligible = True

                observation, completion_confirmed = self._resolve_completion_request(
                    trap,
                    image_read_result,
                )
                if trap is None and feedback and "WARNINGS:" in feedback:
                    observation = (
                        f"Previous response had warnings:\n{feedback}\n\n{image_read_result}"
                    )
                # Build tool_calls for image_read
                tool_calls_list: list[ToolCall] = []
                observation_results: list[ObservationResult] = []

                if not self._save_raw_content_in_trajectory:
                    tool_calls_list.append(
                        ToolCall(
                            tool_call_id=f"call_{episode}_image_read",
                            function_name="image_read",
                            arguments={
                                "file_path": image_read.file_path,
                                "image_read_instruction": image_read.image_read_instruction,
                            },
                        )
                    )
                    observation_results.append(ObservationResult(content=observation))
                    if trap is not None:
                        tool_calls_list.append(
                            ToolCall(
                                tool_call_id=f"call_{episode}_{trap.value}",
                                function_name=self._trajectory_action_name(trap),
                                arguments={},
                            )
                        )
                else:
                    observation_results.append(ObservationResult(content=observation))

                cache_tokens_used = chat.total_cache_tokens - tokens_before_cache
                step_cost = chat.total_cost - cost_before
                self._trajectory_steps.append(
                    Step(
                        step_id=len(self._trajectory_steps) + 1,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        source="agent",
                        model_name=self._model_name,
                        message=message_content,
                        reasoning_content=llm_response.reasoning_content,
                        tool_calls=tool_calls_list or None,
                        observation=Observation(results=observation_results),
                        metrics=Metrics(
                            prompt_tokens=chat.total_input_tokens - tokens_before_input,
                            completion_tokens=chat.total_output_tokens - tokens_before_output,
                            cached_tokens=cache_tokens_used if cache_tokens_used > 0 else None,
                            cost_usd=step_cost if step_cost > 0 else None,
                            prompt_token_ids=llm_response.prompt_token_ids,
                            completion_token_ids=llm_response.completion_token_ids,
                            logprobs=llm_response.logprobs,
                        ),
                    )
                )
                self._dump_trajectory()

                if completion_confirmed:
                    return episode + 1

                prompt = observation
            else:
                # Execute terminal commands.
                if direct_observation is None:
                    _, terminal_output = await self._with_block_timeout(
                        self._execute_commands(
                            commands,
                            self._session,
                        ),
                    )
                else:
                    terminal_output = direct_observation
                if not self._review_phase and (
                    any(command.keystrokes.strip() for command in commands)
                    or trap == RuntimeTrap.COMPLETE
                ):
                    self._review_eligible = True

                limited_output = self._limit_output_length(terminal_output)
                observation, completion_confirmed = self._resolve_completion_request(
                    trap,
                    limited_output,
                )
                if trap is None and feedback and "WARNINGS:" in feedback:
                    observation = (
                        f"Previous response had warnings:\n{feedback}\n\n{limited_output}"
                    )
                # Record trajectory step
                cache_tokens_used = chat.total_cache_tokens - tokens_before_cache
                step_cost = chat.total_cost - cost_before

                tool_calls: list[ToolCall] | None = None
                observation_results: list[ObservationResult] = []

                if not self._save_raw_content_in_trajectory:
                    tool_calls_list: list[ToolCall] = []
                    if commands:
                        for i, cmd in enumerate(commands):
                            tool_calls_list.append(
                                ToolCall(
                                    tool_call_id=f"call_{episode}_{i + 1}",
                                    function_name="bash_command",
                                    arguments={
                                        "keystrokes": cmd.keystrokes,
                                        "duration": cmd.duration_sec,
                                    },
                                )
                            )
                        observation_results.append(ObservationResult(content=observation))
                    elif direct_observation is not None and native_tool_calls:
                        native_call = native_tool_calls[0]
                        raw_arguments = native_call.get("function", {}).get(
                            "arguments",
                            "{}",
                        )
                        try:
                            arguments = (
                                json.loads(raw_arguments)
                                if isinstance(raw_arguments, str)
                                else raw_arguments
                            )
                        except json.JSONDecodeError:
                            arguments = {}
                        tool_calls_list.append(
                            ToolCall(
                                tool_call_id=native_call.get(
                                    "id",
                                    f"call_{episode}_review_context",
                                ),
                                function_name="review_context",
                                arguments=arguments if isinstance(arguments, dict) else {},
                            )
                        )
                        observation_results.append(ObservationResult(content=observation))
                    if trap is not None:
                        tool_calls_list.append(
                            ToolCall(
                                tool_call_id=f"call_{episode}_{trap.value}",
                                function_name=self._trajectory_action_name(trap),
                                arguments={},
                            )
                        )
                        if not commands:
                            observation_results.append(ObservationResult(content=observation))
                    elif not commands and direct_observation is None:
                        observation_results.append(ObservationResult(content=observation))
                    tool_calls = tool_calls_list or None
                else:
                    observation_results.append(ObservationResult(content=observation))

                self._trajectory_steps.append(
                    Step(
                        step_id=len(self._trajectory_steps) + 1,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        source="agent",
                        model_name=self._model_name,
                        message=message_content,
                        reasoning_content=llm_response.reasoning_content,
                        tool_calls=tool_calls,
                        observation=Observation(results=observation_results),
                        metrics=Metrics(
                            prompt_tokens=chat.total_input_tokens - tokens_before_input,
                            completion_tokens=chat.total_output_tokens - tokens_before_output,
                            cached_tokens=cache_tokens_used if cache_tokens_used > 0 else None,
                            cost_usd=step_cost if step_cost > 0 else None,
                            prompt_token_ids=llm_response.prompt_token_ids,
                            completion_token_ids=llm_response.completion_token_ids,
                            logprobs=llm_response.logprobs,
                        ),
                    )
                )
                self._dump_trajectory()

                if completion_confirmed:
                    return episode + 1

                prompt = observation

        return self._n_episodes
