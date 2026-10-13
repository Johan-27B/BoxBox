"""Fixed Terminus-KIRA runtime with native tool calling."""

import asyncio
import itertools
import json
import re
import shlex
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import litellm
from litellm.exceptions import (
    AuthenticationError as LiteLLMAuthenticationError,
    BadRequestError,
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

from perfrace.run.agents.verdict_guidance import MEASUREMENT_CONFIRMATION
from perfrace.run.services.gateway import TokenUsage, estimate_cost_usd

from .materiality import (
    ESTIMATOR_PATH,
    created_hypotheses,
    validate_materiality_record,
    validate_promotion_record,
)


class BlockError(Exception):
    """Raised when infrastructure API call blocks for too long."""

    pass


BLOCK_TIMEOUT_SEC = 600  # 10 minutes
# An empty poll is an explicit request to wait without changing the shell.
# Coalesce two requested waits so long builds do not force a model turn every
# 60 seconds, while keeping interruption responsive and bounded.
_PENDING_EMPTY_POLL_MULTIPLIER = 2.0
_PENDING_EMPTY_POLL_MAX_SEC = 120.0
_MARKER_PREFIX = "__CMDEND__"  # Marker prefix for command completion detection
_FAILURE_MARKER_PREFIX = "__CMDFAIL__"  # Marker prefix for nonzero command status
_RUNTIME_HANDOFF_FILENAME = "perfrace-runtime-handoff.json"
_RUNTIME_HANDOFF_MAX_BYTES = 16_000


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


class PhaseAction(str, Enum):
    """Control action selected by a phase-ending tool."""

    CONTINUE = "continue"
    TASK_COMPLETE = "task_complete"


@dataclass(frozen=True)
class PhaseOutcome:
    """Control result produced by one agent phase."""

    action: PhaseAction = PhaseAction.CONTINUE


# Tool description strings
_EXECUTE_COMMANDS_DESC = (
    "Call this to execute commands in the terminal with your analysis and plan. "
    "Commands run sequentially: if a foreground command has not finished, "
    "the harness stops before sending later commands and safely retains the "
    "already-submitted remainder; use an empty command with a duration to poll "
    "it rather than sending more input to the process. Compound shell commands "
    "are run in a fail-fast child shell: a nonzero edit, assertion, or build "
    "step stops that compound script, reports the exit status, and prevents its "
    "queued suffix from running. Use explicit `|| true` only for an expected "
    "failure, and use an absolute path or `cd` inside each compound script "
    "because child-shell directory changes do not persist. If the pending "
    "command has become low-information or must be abandoned, submit exactly "
    "`C-c` as the sole command to interrupt it; then inspect the workspace and "
    "result before retrying. Once its completion marker is observed, the "
    "retained remainder resumes automatically, so do not duplicate those "
    "commands."
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
    "The text will be used completely verbatim as keystrokes. "
    "Write commands exactly as you want them sent to the terminal. "
    "Most bash commands should end with a newline (\\n) to cause them to execute. "
    "For special key sequences, use tmux-style escape sequences: C-c for Ctrl+C, C-d for Ctrl+D. "
    "Each command's keystrokes are sent exactly as written to the terminal. "
    "Do not include extra whitespace before or after the keystrokes unless it's part of the intended command. "
    "Never enable persistent shell exit-on-error state with a bare `set -e`; "
    "if fail-fast behavior is needed, scope it to a subshell such as `(set -e; commands...)`."
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
    "Never request more than 60 seconds for one wait; when polling an already-running command, the harness may coalesce two empty waits (up to 120 seconds total) without sending any new shell input. Use the sole C-c command when you need to interrupt instead of waiting."
)

_TASK_COMPLETE_DESC = "Call this when the task is complete."
_REPEATED_MEASUREMENT_CONFIRMATION = """

Before confirming, verify that the target worktree is clean and inspect whether
the current commit already has an official measurement:

    git status --porcelain=v1 --untracked-files=all
    git notes --ref=perfrace-measurements show HEAD

The status command must produce no output. If the worktree is dirty, commit a
supported hypothesis or discard it and return to clean main before requesting
verification. If HEAD is already measured and this is not an intentional
remeasurement, do not confirm. Continue target research instead. Repeating
official verification charges the shared work budget without measuring a new
candidate.
"""
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
            "name": "task_complete",
            "description": _TASK_COMPLETE_DESC,
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


class TerminusKira(Terminus2):
    """
    TerminusKira extends harbor's Terminus2 with native tool calling.

    Instead of prompting the model to output JSON/XML and parsing it,
    TerminusKira uses the `tools` parameter in LLM API calls for structured outputs.
    """

    def __init__(self, *args, **kwargs):
        max_turns = kwargs.get("max_turns")
        super().__init__(*args, **kwargs)
        self._max_episodes = max_turns
        self._marker_seq = 0
        self._marker_nonce = uuid.uuid4().hex[:12]
        # A command may outlive the duration requested by the model. Keep its
        # marker across tool calls so a later call can poll it without sending
        # another payload to the still-running foreground process.
        self._pending_command_marker: str | None = None
        self._pending_command_text: str | None = None
        # Preserve commands that were explicitly submitted after a foreground
        # command which outlived its polling window. They are safe to resume
        # only after the marker for the foreground command is observed.
        self._pending_command_queue: list[Command] = []
        self._total_time_saved = 0.0
        self._completion_tool_name = "task_complete"
        self._completion_tool_description = _TASK_COMPLETE_DESC
        self._completion_trajectory_name = "mark_task_complete"
        self._completion_requires_confirmation = True
        self._measurement_confirmation = MEASUREMENT_CONFIRMATION
        self._completion_confirmation_prompt: str | None = self._measurement_confirmation
        self._complete_on_no_tool_response = False
        self._phase_outcome = PhaseOutcome()
        self._task_instruction: str | None = None
        self._base_system_prompt = self._prompt_template
        contract_path = Path(__file__).parent / "skills" / "autoresearch" / "SKILL.md"
        self._system_prompt = (
            f"{self._base_system_prompt}\n\n{contract_path.read_text(encoding='utf-8')}"
        )
        self._prompt_template = (
            "Task Description:\n{instruction}\n\nCurrent terminal state:\n{terminal_state}"
        )

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

    @staticmethod
    def _runtime_journal_script(action: str, payload: str = "") -> str:
        """Return a shell snippet for the hidden interrupted-command journal."""
        if action == "write":
            encoded = shlex.quote(payload)
            return (
                "git_path=$(git rev-parse --git-path perfrace-runtime-command.json "
                "2>/dev/null) || exit 0; "
                "mkdir -p \"$(dirname \"$git_path\")\"; "
                f"printf %s {encoded} > \"$git_path.tmp\"; "
                "mv -f \"$git_path.tmp\" \"$git_path\""
            )
        if action == "read":
            return (
                "git_path=$(git rev-parse --git-path perfrace-runtime-command.json "
                "2>/dev/null) || exit 0; "
                "test -f \"$git_path\" && cat -- \"$git_path\" || true"
            )
        if action == "clear":
            return (
                "git_path=$(git rev-parse --git-path perfrace-runtime-command.json "
                "2>/dev/null) || exit 0; "
                "rm -f -- \"$git_path\" \"$git_path.tmp\""
            )
        raise ValueError(f"unknown runtime journal action: {action}")

    async def _write_runtime_command_journal(
        self,
        session: TmuxSession,
        command: Command,
        queued: list[Command],
    ) -> None:
        """Persist an in-flight command outside the target worktree.

        The journal is deliberately stored below Git's metadata rather than in
        the checkout: an interrupted command must not make the promotion gate
        reject an otherwise clean candidate. Failure to write it is advisory and
        never prevents the requested command from running.
        """
        payload = json.dumps(
            {
                "schema_version": 1,
                "state": "running",
                "command": command.keystrokes,
                "duration_seconds": command.duration_sec,
                "queued_commands": [item.keystrokes for item in queued],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        try:
            result = await session.environment.exec(
                self._runtime_journal_script("write", payload),
                cwd=session.environment.task_env_config.workdir,
                timeout_sec=30,
            )
        except Exception:
            self.logger.debug("Could not persist interrupted-command journal")
            return
        if result.return_code != 0:
            self.logger.debug("Could not persist interrupted-command journal")

    async def _clear_runtime_command_journal(self, session: TmuxSession) -> None:
        """Remove the journal only after the completion marker is observed."""
        try:
            result = await session.environment.exec(
                self._runtime_journal_script("clear"),
                cwd=session.environment.task_env_config.workdir,
                timeout_sec=30,
            )
        except Exception:
            self.logger.debug("Could not clear interrupted-command journal")
            return
        if result.return_code != 0:
            self.logger.debug("Could not clear interrupted-command journal")

    async def _read_runtime_command_journal(
        self,
        session: TmuxSession,
    ) -> str | None:
        """Return a bounded recovery hint for a journal left by a timeout."""
        try:
            result = await session.environment.exec(
                self._runtime_journal_script("read"),
                cwd=session.environment.task_env_config.workdir,
                timeout_sec=30,
            )
        except Exception:
            self.logger.debug("Could not read interrupted-command journal")
            return None
        # Harbor may represent a successful command with no stdout as None
        # (not an empty string). Journal recovery is advisory; it must never
        # abort an otherwise resumable checkpoint on that representation.
        journal_text = result.stdout if isinstance(result.stdout, str) else ""
        if result.return_code != 0 or not journal_text.strip():
            return None
        try:
            payload = json.loads(journal_text)
        except json.JSONDecodeError:
            return (
                "INTERRUPTED-COMMAND JOURNAL: an unreadable journal exists in Git "
                "metadata; inspect the shell and workspace before replaying work."
            )
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return (
                "INTERRUPTED-COMMAND JOURNAL: an unrecognized journal exists in Git "
                "metadata; inspect the shell and workspace before replaying work."
            )
        command = payload.get("command")
        queued = payload.get("queued_commands")
        if not isinstance(command, str) or not isinstance(queued, list):
            return (
                "INTERRUPTED-COMMAND JOURNAL: its contents are incomplete; inspect "
                "the shell and workspace before replaying work."
            )
        if len(command) > 4000:
            command = command[:4000] + "\n[command truncated]"
        queued_text = "\n".join(
            item for item in queued if isinstance(item, str)
        )
        if len(queued_text) > 4000:
            queued_text = queued_text[:4000] + "\n[queued suffix truncated]"
        return (
            "INTERRUPTED-COMMAND JOURNAL: a prior harness turn recorded a command "
            "that may have been running when the phase stopped. This is context, "
            "not evidence that it failed or completed; do not replay it blindly. "
            "Inspect HEAD, status, processes, outputs, and the command result."
            f"\nRecorded command:\n{command}"
            + (f"\nCommands queued after it:\n{queued_text}" if queued_text else "")
        )

    def _runtime_handoff_script(self, action: str, payload: str = "") -> str:
        """Return a Git-metadata script for the compact research handoff."""
        path = shlex.quote(_RUNTIME_HANDOFF_FILENAME)
        if action == "write":
            encoded = shlex.quote(payload)
            return (
                "git_path=$(git rev-parse --git-path "
                f"{path} 2>/dev/null) || exit 0; "
                "mkdir -p \"$(dirname \"$git_path\")\"; "
                f"printf %s {encoded} > \"$git_path.tmp\"; "
                "mv -f \"$git_path.tmp\" \"$git_path\""
            )
        if action == "read":
            return (
                "git_path=$(git rev-parse --git-path "
                f"{path} 2>/dev/null) || exit 0; "
                "test -f \"$git_path\" && cat -- \"$git_path\" || true"
            )
        if action == "clear":
            return (
                "git_path=$(git rev-parse --git-path "
                f"{path} 2>/dev/null) || exit 0; "
                "rm -f -- \"$git_path\" \"$git_path.tmp\""
            )
        raise ValueError(f"unknown runtime handoff action: {action}")

    async def _write_runtime_handoff(
        self,
        session: TmuxSession,
        *,
        episode: int,
        phase: str,
        analysis: str,
        plan: str,
        commands: list[Command],
        terminal_output: str = "",
    ) -> None:
        """Persist the latest bounded research decision outside the worktree.

        This is deliberately advisory: it records what the model intended and
        observed, but never claims that a command completed or that a candidate
        improved. The existing command journal remains authoritative for an
        in-flight shell command.
        """
        def bounded(value: str, limit: int) -> str:
            value = value if isinstance(value, str) else str(value)
            return value[-limit:] if len(value) > limit else value

        payload = json.dumps(
            {
                "schema_version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "episode": episode,
                "phase": phase,
                "analysis": bounded(analysis, 3000),
                "plan": bounded(plan, 4000),
                "commands": [
                    {
                        "keystrokes": bounded(command.keystrokes, 3000),
                        "duration_seconds": command.duration_sec,
                    }
                    for command in commands[:8]
                ],
                "terminal_output": bounded(terminal_output, 5000),
            },
            ensure_ascii=False,
        )
        if len(payload.encode("utf-8")) > _RUNTIME_HANDOFF_MAX_BYTES:
            payload = json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "episode": episode,
                    "phase": phase,
                    "analysis": bounded(analysis, 1500),
                    "plan": bounded(plan, 2000),
                    "commands": [
                        {
                            "keystrokes": bounded(command.keystrokes, 1200),
                            "duration_seconds": command.duration_sec,
                        }
                        for command in commands[:4]
                    ],
                    "terminal_output": bounded(terminal_output, 2500),
                },
                ensure_ascii=False,
            )
        try:
            result = await session.environment.exec(
                self._runtime_handoff_script("write", payload),
                cwd=session.environment.task_env_config.workdir,
                timeout_sec=30,
            )
        except Exception:
            self.logger.debug("Could not persist research checkpoint handoff")
            return
        if result.return_code != 0:
            self.logger.debug("Could not persist research checkpoint handoff")

    async def _read_runtime_handoff(self, session: TmuxSession) -> str | None:
        """Read a bounded handoff as advisory context for a new phase."""
        try:
            result = await session.environment.exec(
                self._runtime_handoff_script("read"),
                cwd=session.environment.task_env_config.workdir,
                timeout_sec=30,
            )
        except Exception:
            self.logger.debug("Could not read research checkpoint handoff")
            return None
        text = self._result_text(result, "stdout")
        if result.return_code != 0 or not text.strip() or len(text) > _RUNTIME_HANDOFF_MAX_BYTES:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "RESEARCH HANDOFF: an unreadable advisory handoff exists; inspect the workspace and ignore it."
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return "RESEARCH HANDOFF: an unrecognized advisory handoff exists; inspect the workspace and ignore it."

        def field(name: str, limit: int) -> str:
            value = payload.get(name, "")
            return value[:limit] if isinstance(value, str) else ""

        commands = payload.get("commands")
        command_lines: list[str] = []
        if isinstance(commands, list):
            for item in commands[:8]:
                if not isinstance(item, dict) or not isinstance(item.get("keystrokes"), str):
                    continue
                command_lines.append(item["keystrokes"][:1200])
        return (
            "RESEARCH HANDOFF (advisory, may be stale): the prior harness phase "
            "saved the latest research decision outside the worktree. Verify HEAD, "
            "status, processes, artifacts, and command results before acting; this "
            "record is not evidence that a command completed or that a candidate won."
            f"\nUpdated: {field('updated_at', 80)}"
            f"\nPhase: {field('phase', 40)}; episode: {payload.get('episode', '?')}"
            f"\nPrior analysis:\n{field('analysis', 3000)}"
            f"\nPrior plan:\n{field('plan', 4000)}"
            + ("\nPrior submitted commands:\n" + "\n---\n".join(command_lines) if command_lines else "")
            + f"\nPrior terminal output (context only):\n{field('terminal_output', 5000)}"
        )

    def _completion_marker(self, sequence: int) -> str:
        """Return one runtime-scoped shell completion marker."""
        return f"{_MARKER_PREFIX}{self._marker_nonce}_{sequence}__"

    def _completion_marker_command(self, sequence: int) -> str:
        """Report command status, then print the marker for completion detection."""
        return (
            "__perfrace_status=$?; "
            "if [ \"$__perfrace_status\" -ne 0 ]; then "
            "printf '\\n%s%s%s exit=%s\\n' "
            f"'{_FAILURE_MARKER_PREFIX}' '{self._marker_nonce}' '_{sequence}' "
            "\"$__perfrace_status\"; fi; "
            "printf '\\n%s%s%s%s\\n' "
            f"'{_MARKER_PREFIX}' '{self._marker_nonce}' '_{sequence}' '__'\n"
        )

    @staticmethod
    def _shell_prompt_visible(pane_content: str) -> bool:
        """Return whether the last visible terminal line is an idle shell prompt.

        This is deliberately only a recovery signal. The unique completion marker
        remains authoritative when it is present; the prompt check prevents an
        absent marker from pinning the session forever after the shell has already
        returned to its prompt.
        """
        # Tmux captures may include cursor/colour escapes around the prompt. Strip
        # them before the bounded recovery check, but keep the marker authoritative.
        ansi_stripped = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", pane_content)
        lines = [line.rstrip() for line in ansi_stripped.splitlines() if line.strip()]
        if not lines:
            return False
        last = lines[-1].strip()
        if _MARKER_PREFIX in last:
            return False
        # Harbor's shells use prompts such as user@container:/workspace$ or
        # root@container:/#; also accept bare bash-style prompts.
        return last.rstrip().endswith(("$", "#", ">"))

    @staticmethod
    def _pager_visible(pane_content: str) -> bool:
        """Return whether a common line pager is holding the foreground shell."""
        ansi_stripped = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", pane_content)
        lines = [line.strip() for line in ansi_stripped.splitlines() if line.strip()]
        if not lines:
            return False
        last = lines[-1]
        # These are pager UI status lines, not arbitrary output containing a word
        # such as ``END``. Dismissing only these exact forms is intentionally narrow.
        return last in {"(END)", "-- More --", "--More--"}

    async def _dismiss_pager(self, session: TmuxSession, pane_content: str) -> bool:
        """Exit a detected pager so the already-queued completion marker can run."""
        if not self._pager_visible(pane_content):
            return False
        try:
            # ``q`` is the standard quit key for less/more and is sent only after
            # their unmistakable status line is visible. It is not appended to the
            # model command and therefore cannot alter ordinary command arguments.
            await session.send_keys(keys="q", block=False, min_timeout_sec=0.0)
        except RuntimeError:
            return False
        return True

    @staticmethod
    def _command_input(keystrokes: str) -> str:
        """Preserve control-key sequences while making shell commands executable."""
        if keystrokes.endswith((chr(10), chr(13))):
            return keystrokes
        # Terminus accepts tmux-style control sequences (for example C-cC-d).
        # Do not turn those into a literal shell line; ordinary model-issued
        # commands, however, need a terminating newline before the marker.
        if re.fullmatch(r"(?:C-[A-Za-z](?:C-[A-Za-z])*)+", keystrokes):
            return keystrokes
        return keystrokes + chr(10)

    @staticmethod
    def _is_compound_shell_command(keystrokes: str) -> bool:
        """Return whether a submitted command contains multiple shell steps.

        A simple command remains in the persistent shell so a deliberate ``cd``
        continues to work across tool calls. Multi-step scripts are isolated so
        an edit/assertion failure cannot fall through to a later build or timing
        command. This conservative test may isolate a command with quoted shell
        punctuation, which is harmless and safer than missing a compound batch.
        """
        text = keystrokes.rstrip("\r\n")
        return "\n" in text or bool(re.search(r"&&|\|\||[;|]", text))

    @staticmethod
    def _fail_fast_input(keystrokes: str) -> str:
        """Quote a compound script for a child bash with errexit enabled."""
        script = keystrokes.rstrip("\r\n")
        return f"bash -e -c {shlex.quote(script)}\n"

    @staticmethod
    def _result_text(result: Any, stream: str) -> str:
        """Normalize Harbor's optional command-result streams for control flow."""
        value = getattr(result, stream, None)
        return value if isinstance(value, str) else ""

    @staticmethod
    def _materiality_workdir_candidates(
        commands: list[Command],
        default_workdir: str,
    ) -> list[str]:
        """Find explicit project-directory prefixes in a prospective command batch.

        The agent shell can already be inside the editable project while Harbor's
        fixed environment workdir remains its parent workspace. Materiality
        validation must inspect the same repository that the literal branch
        command will use, without guessing among unrelated repositories.
        """
        candidates = [default_workdir]
        for command in commands:
            for fragment in re.split(r"(?:&&|\|\||[;\n])", command.keystrokes):
                try:
                    tokens = shlex.split(fragment)
                except ValueError:
                    continue
                if not tokens:
                    continue
                first = tokens[0].lstrip("(")
                paths: list[str] = []
                if first == "cd":
                    args = tokens[1:]
                    if args and args[0] == "--":
                        args = args[1:]
                    if args and args[0] not in {"-", "~"}:
                        paths.append(args[0])
                for index, token in enumerate(tokens[:-2]):
                    if token == "git" and tokens[index + 1] == "-C":
                        paths.append(tokens[index + 2])
                for path in paths:
                    if path.startswith("/"):
                        candidate = path
                    elif path.startswith("~"):
                        # Do not expand a host-side home directory into the
                        # target container; the explicit absolute form is safe.
                        continue
                    else:
                        candidate = str(Path(default_workdir) / path)
                    if candidate not in candidates:
                        candidates.append(candidate)
        return candidates

    async def _materiality_gate_errors(
        self,
        hypothesis: str,
        session: TmuxSession,
        commands: list[Command] | None = None,
    ) -> list[str]:
        """Validate the agent-authored estimate for one prospective try branch."""
        environment = session.environment
        default_workdir = environment.task_env_config.workdir
        candidates = self._materiality_workdir_candidates(commands or [], default_workdir)
        workdir = default_workdir
        base = None
        for candidate_workdir in candidates:
            try:
                probe = await environment.exec(
                    "git rev-parse main",
                    cwd=candidate_workdir,
                    timeout_sec=30,
                )
            except Exception:
                continue
            if probe.return_code == 0:
                workdir = candidate_workdir
                base = probe
                break
        if base is None:
            return ["cannot resolve main: no candidate project directory contains refs/heads/main"]

        estimate_path = f".autoresearch/estimates/{hypothesis}.json"

        estimator = await environment.exec(
            f"sha256sum -- {shlex.quote(ESTIMATOR_PATH)}",
            cwd=workdir,
            timeout_sec=30,
        )
        if estimator.return_code != 0:
            return [f"{ESTIMATOR_PATH} is missing or unreadable"]
        estimator_fields = self._result_text(estimator, "stdout").split(maxsplit=1)
        if not estimator_fields:
            return [f"{ESTIMATOR_PATH} hash output is missing or unreadable"]
        estimator_sha256 = estimator_fields[0]

        record = await environment.exec(
            f"cat -- {shlex.quote(estimate_path)}",
            cwd=workdir,
            timeout_sec=30,
        )
        if record.return_code != 0:
            return [f"{estimate_path} is missing or unreadable"]
        record_text = self._result_text(record, "stdout")
        if len(record_text) > 256_000:
            return [f"{estimate_path} exceeds 256000 bytes"]
        try:
            payload = json.loads(record_text)
        except json.JSONDecodeError as exc:
            return [f"{estimate_path} is not valid JSON: {exc}"]

        return validate_materiality_record(
            payload,
            expected_hypothesis=hypothesis,
            expected_base_commit=self._result_text(base, "stdout").strip(),
            estimator_sha256=estimator_sha256,
        )

    async def _promotion_gate_errors(self, session: TmuxSession) -> list[str]:
        """Require attributable local evidence before requesting verification.

        This gate does not claim that the candidate is correct or that local
        timing predicts the verifier. It prevents an unchanged, dirty, or
        undocumented tree from being presented as a researched optimization.
        """
        environment = session.environment
        workdir = environment.task_env_config.workdir
        status = await environment.exec(
            "git status --porcelain=v1 --untracked-files=all",
            cwd=workdir,
            timeout_sec=30,
        )
        errors: list[str] = []
        if status.return_code != 0:
            errors.append(f"cannot inspect worktree: {self._result_text(status, 'stderr').strip()}")
        elif self._result_text(status, "stdout").strip():
            errors.append(
                "worktree is dirty; commit or discard target edits and add "
                ".autoresearch/ to .git/info/exclude"
            )

        head = await environment.exec("git rev-parse HEAD", cwd=workdir, timeout_sec=30)
        if head.return_code != 0:
            errors.append(f"cannot resolve candidate HEAD: {self._result_text(head, 'stderr').strip()}")
            return errors
        candidate_commit = self._result_text(head, "stdout").strip()
        record = await environment.exec(
            "cat -- .autoresearch/promotion.json",
            cwd=workdir,
            timeout_sec=30,
        )
        if record.return_code != 0:
            errors.append(
                "missing .autoresearch/promotion.json; record the exact candidate "
                "commit, distinct baseline, comparable samples, and correctness evidence"
            )
            return errors
        record_text = self._result_text(record, "stdout")
        if len(record_text) > 128_000:
            errors.append(".autoresearch/promotion.json exceeds 128000 bytes")
            return errors
        try:
            payload = json.loads(record_text)
        except json.JSONDecodeError as exc:
            errors.append(f".autoresearch/promotion.json is not valid JSON: {exc}")
            return errors
        errors.extend(
            validate_promotion_record(
                payload,
                expected_candidate_commit=candidate_commit,
            )
        )

        if isinstance(payload, dict):
            baseline_commit = payload.get("baseline_commit")
            if isinstance(baseline_commit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", baseline_commit):
                baseline = await environment.exec(
                    f"git rev-parse --verify {shlex.quote(baseline_commit)}^{{commit}}",
                    cwd=workdir,
                    timeout_sec=30,
                )
                if baseline.return_code != 0:
                    errors.append("baseline_commit is not present in the repository")
                else:
                    delta = await environment.exec(
                        f"git diff --quiet {shlex.quote(baseline_commit)} {shlex.quote(candidate_commit)} --",
                        cwd=workdir,
                        timeout_sec=30,
                    )
                    if delta.return_code == 0:
                        errors.append(
                            "candidate tree is identical to baseline; do not request "
                            "measurement for a no-op candidate"
                        )
                    elif delta.return_code not in (1,):
                        errors.append("could not compare candidate and baseline trees")
        return errors

    async def _execute_commands(
        self,
        commands: list[Command],
        session: TmuxSession,
        *,
        skip_materiality_gate: bool = False,
    ) -> tuple[bool, str]:
        """Execute sequential commands without injecting into a running process.

        Each command gets a unique completion marker. If the marker is absent
        when the requested duration expires, remember it and return immediately;
        a later tool call polls the marker instead of sending more keystrokes.
        Any later commands from the same submitted batch are retained and
        resumed after the marker appears. This keeps long builds/tests from
        consuming the next command as stdin without losing planned work.
        """
        def clean_output(output: str) -> str:
            lines = output.split("\n")
            return "\n".join(line for line in lines if _MARKER_PREFIX not in line)

        # A previous command still owns the foreground shell. Never queue the
        # next model payload behind it: doing so is the source of concatenated
        # build/test commands seen in long research runs. An explicit, sole
        # C-c is the one exception: it is an intentional abort request, not
        # another payload to queue behind the foreground process.
        if self._pending_command_marker is not None:
            if len(commands) == 1 and re.fullmatch(r"C-c", commands[0].keystrokes):
                pending_text = self._pending_command_text or "<pending command>"
                try:
                    await session.send_keys(
                        keys=["C-c"],
                        block=False,
                        min_timeout_sec=0.0,
                    )
                except RuntimeError as exc:
                    if not await session.is_session_alive():
                        recovered = await self._recover_dead_session(
                            session,
                            command=pending_text,
                            error=exc,
                        )
                        self._pending_command_marker = None
                        self._pending_command_text = None
                        self._pending_command_queue = []
                        return False, recovered
                    raise
                marker = self._pending_command_marker
                released = False
                marker_lost = False
                deadline = time.monotonic() + 2.0
                while True:
                    pane_content = await session.capture_pane()
                    if marker in pane_content:
                        released = True
                        break
                    if self._shell_prompt_visible(pane_content):
                        released = True
                        marker_lost = True
                        break
                    if not pane_content and not await session.is_session_alive():
                        recovered = await self._recover_dead_session(
                            session,
                            command=pending_text,
                        )
                        self._pending_command_marker = None
                        self._pending_command_text = None
                        self._pending_command_queue = []
                        return False, recovered
                    if time.monotonic() >= deadline:
                        break
                    await asyncio.sleep(0.2)

                output = clean_output(await session.get_incremental_output())
                if not released:
                    return False, self._limit_output_length(
                        "INTERRUPT SIGNAL SENT, BUT THE PENDING COMMAND STILL OWNS "
                        "THE SHELL. No queued commands were sent and the pending "
                        "guard remains active; poll again or inspect only after the "
                        "shell is idle.\n"
                        f"Pending command:\n{pending_text}\n\n{output}"
                    )

                self._pending_command_marker = None
                self._pending_command_text = None
                self._pending_command_queue = []
                await self._clear_runtime_command_journal(session)
                marker_note = (
                    " The completion marker was not visible, so inspect the command "
                    "result before retrying."
                    if marker_lost
                    else ""
                )
                return False, self._limit_output_length(
                    "PENDING COMMAND INTERRUPTED BY EXPLICIT C-c. No queued "
                    "commands were sent. The command may have partially completed; "
                    "inspect the workspace, processes, and outputs before retrying "
                    "or proceeding."
                    f"{marker_note}\nInterrupted command:\n{pending_text}\n\n{output}"
                )

            duration = max(
                (command.duration_sec for command in commands),
                default=1.0,
            )
            # Empty commands carry no new shell input, so waiting through a
            # second interval is safe: the foreground process still owns the
            # shell and the marker remains the only completion signal. This
            # removes low-information model turns from long builds while the
            # explicit C-c path above remains available on the next turn.
            if not commands or all(not command.keystrokes for command in commands):
                duration = min(
                    duration * _PENDING_EMPTY_POLL_MULTIPLIER,
                    _PENDING_EMPTY_POLL_MAX_SEC,
                )
            marker = self._pending_command_marker
            start = time.monotonic()
            await asyncio.sleep(min(0.3, duration))
            completed = False
            while True:
                pane_content = await session.capture_pane()
                if marker in pane_content:
                    completed = True
                    break
                if await self._dismiss_pager(session, pane_content):
                    await asyncio.sleep(0.1)
                    continue
                if self._shell_prompt_visible(pane_content):
                    # The shell is visibly idle even though the marker was lost
                    # (for example, due to a terminal write race). Clear the
                    # stale guard so the model can inspect before retrying.
                    completed = True
                    marker = None
                    break
                if not pane_content and not await session.is_session_alive():
                    recovered = await self._recover_dead_session(
                        session,
                        command=self._pending_command_text or "<pending command>",
                    )
                    self._pending_command_marker = None
                    self._pending_command_text = None
                    self._pending_command_queue = []
                    return False, recovered
                if time.monotonic() - start >= duration:
                    break
                await asyncio.sleep(0.5)

            output = clean_output(await session.get_incremental_output())
            if completed:
                pending_text = self._pending_command_text or "<pending command>"
                self._pending_command_marker = None
                self._pending_command_text = None
                if marker is None:
                    self._pending_command_queue = []
                    return False, self._limit_output_length(
                        "SHELL PROMPT RETURNED BUT THE COMPLETION MARKER WAS LOST. "
                        "The stale pending guard was cleared; inspect the workspace "
                        "and command result before retrying or continuing.\n"
                        f"Possibly completed command:\n{pending_text}\n\n{output}"
                    )
                if _FAILURE_MARKER_PREFIX in output:
                    self._pending_command_queue = []
                    await self._clear_runtime_command_journal(session)
                    return False, self._limit_output_length(
                        "COMMAND FAILED. The completion marker was observed, but "
                        "the command exited nonzero; no queued commands were sent. "
                        "Inspect the edit, workspace, and outputs before retrying.\n"
                        f"{output}"
                    )
                queued = self._pending_command_queue
                self._pending_command_queue = []
                if queued:
                    await self._write_runtime_command_journal(
                        session,
                        queued[0],
                        queued[1:],
                    )
                    _continued, continuation_output = await self._execute_commands(
                        queued,
                        session,
                        skip_materiality_gate=True,
                    )
                    return False, self._limit_output_length(
                        "PREVIOUS COMMAND COMPLETED. Resumed the remaining commands "
                        "from the same submitted batch.\n"
                        f"Previous command:\n{pending_text}\n\n"
                        f"{output}\n\n{continuation_output}"
                    )
                await self._clear_runtime_command_journal(session)
                return False, self._limit_output_length(
                    "PREVIOUS COMMAND COMPLETED. No queued command was sent. "
                    "Inspect the result before issuing the next command.\n"
                    f"Previous command:\n{pending_text}\n\n{output}"
                )
            return False, self._limit_output_length(
                "COMMAND STILL RUNNING. No new command was sent. Use an empty "
                "command with a duration to poll again; do not inject input or "
                "duplicate the retained batch suffix before completion.\n"
                f"Pending command:\n{self._pending_command_text or '<pending command>'}\n\n"
                f"{output}"
            )

        if not skip_materiality_gate:
            hypotheses = created_hypotheses(command.keystrokes for command in commands)
            for hypothesis in hypotheses:
                errors = await self._materiality_gate_errors(hypothesis, session, commands)
                if errors:
                    details = "\n".join(f"- {error}" for error in errors)
                    return (
                        False,
                        "MATERIALITY GATE BLOCKED: no command in this batch was executed.\n"
                        f"Hypothesis: {hypothesis}\n"
                        f"{details}\n"
                        "Create or repair the estimator and estimate on main, run the "
                        "estimator, then retry the literal try/* branch creation command.",
                    )

        for command_index, command in enumerate(commands):
            self._marker_seq += 1
            marker = self._completion_marker(self._marker_seq)
            start = time.monotonic()

            await self._write_runtime_command_journal(
                session,
                command,
                list(commands[command_index + 1 :]),
            )

            try:
                # Submit one ordered payload. Separate nonblocking writes can
                # race with tmux capture and leave only the shell setup visible
                # while the harness waits forever for a marker that was never
                # queued. Compound scripts run in a fail-fast child so an edit
                # failure cannot fall through to a build or timing command.
                command_input = (
                    self._fail_fast_input(command.keystrokes)
                    if self._is_compound_shell_command(command.keystrokes)
                    else self._command_input(command.keystrokes)
                )
                payload = (
                    # Research commands frequently invoke git or other tools that
                    # open a pager in a non-interactive tmux shell. Disable common
                    # pagers at the shell boundary; the targeted recovery below is
                    # still needed for commands that explicitly launch one.
                    "set +e\n"
                    "export GIT_PAGER=cat PAGER=cat SYSTEMD_PAGER=cat "
                    "GH_PAGER=cat LESS=-FRX\n"
                    + command_input
                    + self._completion_marker_command(self._marker_seq)
                )
                await session.send_keys(
                    payload,
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

            await asyncio.sleep(min(0.3, command.duration_sec))
            completed = False
            while True:
                pane_content = await session.capture_pane()
                if marker in pane_content:
                    completed = True
                    break
                if await self._dismiss_pager(session, pane_content):
                    await asyncio.sleep(0.1)
                    continue
                if self._shell_prompt_visible(pane_content):
                    # The shell is visibly idle even though the marker was lost
                    # (for example, due to a terminal write race). Clear the
                    # stale guard so the model can inspect before retrying.
                    completed = True
                    marker = None
                    break
                if not pane_content and not await session.is_session_alive():
                    recovered = await self._recover_dead_session(
                        session,
                        command=command.keystrokes,
                    )
                    self._pending_command_queue = []
                    return False, recovered
                if time.monotonic() - start >= command.duration_sec:
                    break
                await asyncio.sleep(0.5)

            saved = command.duration_sec - (time.monotonic() - start)
            if saved > 0.1:
                self._total_time_saved += saved
                self.logger.debug(
                    f"[polling] saved {saved:.1f}s "
                    f"(duration={command.duration_sec:.1f}s) "
                    f"cmd={command.keystrokes!r}"
                )

            output = clean_output(await session.get_incremental_output())
            if completed and _FAILURE_MARKER_PREFIX in output:
                self._pending_command_queue = []
                await self._clear_runtime_command_journal(session)
                return False, self._limit_output_length(
                    "COMMAND FAILED. The completion marker was observed, but the "
                    "command exited nonzero; no queued commands were sent. Inspect "
                    "the edit, workspace, and outputs before retrying.\n"
                    f"{output}"
                )

            if not completed:
                self._pending_command_marker = marker
                self._pending_command_text = command.keystrokes
                self._pending_command_queue = list(commands[command_index + 1 :])
                output = clean_output(await session.get_incremental_output())
                return False, self._limit_output_length(
                    "COMMAND STILL RUNNING. Later commands in this batch were not "
                    "sent but are retained by the harness. Use an empty command "
                    "with a duration to poll; do not duplicate the retained suffix "
                    "after completion.\n"
                    f"Pending command:\n{command.keystrokes}\n\n{output}"
                )
            if marker is None:
                output = clean_output(await session.get_incremental_output())
                return False, self._limit_output_length(
                    "SHELL PROMPT RETURNED BUT THE COMPLETION MARKER WAS LOST. "
                    "No later commands in this batch were sent. Inspect the "
                    "workspace and command result before retrying or continuing.\n"
                    f"Completed command candidate:\n{command.keystrokes}\n\n{output}"
                )

        await self._clear_runtime_command_journal(session)
        output = clean_output(await session.get_incremental_output())
        return False, self._limit_output_length(output)

    @staticmethod
    def name() -> str:
        return "terminus-kira"

    def version(self) -> str | None:
        return "1.0.0"

    def system_prompt(self) -> str:
        """Return the system prompt installed during agent-session restoration."""
        return self._system_prompt

    async def ensure_agent_session(self) -> None:
        """Restart the active terminal if its persistent shell exited."""
        if self._session is None:
            raise RuntimeError("Active runtime has no terminal session")
        if not await self._session.is_session_alive():
            await self._session.start()

    def set_task_instruction(self, instruction: str) -> None:
        """Set the benchmark task retained across continuation prompts."""
        if not instruction.strip():
            raise ValueError("Task instruction must be non-empty")
        self._task_instruction = instruction

    @staticmethod
    def _merge_context(context: AgentContext, addition: AgentContext) -> None:
        """Accumulate one internal target or review segment."""
        context.n_input_tokens = (context.n_input_tokens or 0) + (addition.n_input_tokens or 0)
        context.n_output_tokens = (context.n_output_tokens or 0) + (addition.n_output_tokens or 0)
        context.n_cache_tokens = (context.n_cache_tokens or 0) + (addition.n_cache_tokens or 0)
        if addition.cost_usd is not None:
            context.cost_usd = (context.cost_usd or 0.0) + addition.cost_usd
        context.rollout_details = [
            *(context.rollout_details or []),
            *(addition.rollout_details or []),
        ]
        if addition.metadata:
            metadata = dict(context.metadata or {})
            segments = list(metadata.get("internal_segments", []))
            segments.append(addition.metadata)
            metadata.update(addition.metadata)
            metadata["internal_segments"] = segments
            context.metadata = metadata

    def _build_summarization_chat(self, chat: Chat) -> Chat:
        """Serialize native tool calls as transcript text for Terminus summarization."""
        messages: list[dict[str, Any]] = []
        for message in chat.messages:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            if role == "tool":
                tool_call_id = message.get("tool_call_id", "unknown")
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool result ({tool_call_id}):\n{content}",
                    }
                )
                continue
            if role == "assistant" and message.get("tool_calls"):
                tool_calls = json.dumps(message["tool_calls"], ensure_ascii=False)
                content = f"{content}\n\nTool calls:\n{tool_calls}".strip()
            messages.append({"role": role, "content": content})
        summary_chat = Chat(self._llm)
        summary_chat.load_state({"schema_version": 1, "messages": messages})
        return summary_chat

    async def _summarize(
        self,
        chat: Chat,
        original_instruction: str,
        session: TmuxSession,
    ):
        """Run native summarization with KIRA tool messages represented as text."""
        has_native_tools = any(
            message.get("role") == "tool" or message.get("tool_calls") for message in chat.messages
        )
        if not has_native_tools:
            return await super()._summarize(chat, original_instruction, session)
        summary_chat = self._build_summarization_chat(chat)
        result = await super()._summarize(
            summary_chat,
            original_instruction,
            session,
        )
        chat._messages = summary_chat.dump_state()["messages"]
        chat.reset_response_chain()
        return result

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        """Run one fixed Terminus-KIRA agent phase."""
        self._original_instruction = instruction
        self._phase_outcome = PhaseOutcome()
        self._pending_completion = False
        self._include_initial_handoff = True
        if self._pending_chat_state is None:
            self._pending_chat_state = {
                "schema_version": 1,
                "messages": [{"role": "system", "content": self._system_prompt}],
            }
        try:
            await super().run(instruction, environment, context)
        finally:
            if self._chat is not None:
                self._pending_chat_state = self._chat.dump_state()

    def take_phase_outcome(self) -> PhaseOutcome:
        """Return and clear the controller-visible outcome of the last run."""
        outcome = self._phase_outcome
        self._phase_outcome = PhaseOutcome()
        return outcome

    def _get_parser(self):
        """Return None since we use native tool calling instead of parsing."""
        return None

    def _get_prompt_template_path(self) -> Path:
        """Return the path to the prompt template for native tool use."""
        return Path(__file__).parent / "prompt-templates" / "terminus-kira.txt"

    def _get_error_response_type(self) -> str:
        """Return error response type for native tool use."""
        return "response with valid tool calls"

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions with this runtime's phase-ending action."""
        tools = []
        for tool in TOOLS:
            name = tool["function"]["name"]
            if name != "task_complete":
                tools.append(tool)
            elif self._completion_tool_name is not None:
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
        return tools

    def _setup_episode_logging(
        self, logging_dir: Path | None, episode: int
    ) -> tuple[Path | None, Path | None, Path | None]:
        """Compatibility shim for Harbor versions without this Terminus2 helper."""
        if logging_dir is None:
            return None, None, None
        episode_logging_dir = logging_dir / f"episode-{episode}"
        episode_logging_dir.mkdir(parents=True, exist_ok=True)
        return (
            episode_logging_dir / "debug.json",
            episode_logging_dir / "prompt.txt",
            episode_logging_dir / "response.txt",
        )

    def _record_asciinema_marker(self, marker_text: str) -> None:
        """Compatibility shim for Harbor versions without asciinema markers."""
        return

    def _get_completion_confirmation_message(self, terminal_output: str) -> str:
        """Return task completion confirmation message for native tool use."""
        instruction = self._task_instruction or getattr(
            self,
            "_original_instruction",
            "N/A",
        )
        if self._completion_confirmation_prompt is not None:
            return self._completion_confirmation_prompt.format(
                original_task=instruction,
                terminal_output=terminal_output,
                completion_tool=self._completion_tool_name,
            )
        return (
            f"Original task:\n{instruction}\n\n"
            f"Current terminal state:\n{terminal_output}\n\n"
            "Are you sure you want to mark the task as complete?\n\n"
            "[!] Checklist\n"
            "- Does your solution meet the requirements in the original task above? [TODO/DONE]\n"
            "- Does your solution account for potential changes in numeric values, array sizes, file contents, or configuration parameters? [TODO/DONE]\n"
            "- Have you verified your solution from the all perspectives of a test engineer, a QA engineer, and the user who requested this task?\n"
            "  - test engineer [TODO/DONE]\n"
            "  - QA engineer [TODO/DONE]\n"
            "  - user who requested this task [TODO/DONE]\n\n"
            "After this point, solution grading will begin and no further edits will be possible. "
            f"If everything looks good, call {self._completion_tool_name} tool again."
        )

    def _resolve_completion_request(
        self,
        outcome: PhaseOutcome,
        output: str,
    ) -> tuple[str, bool]:
        """Resolve a phase-ending request and report whether the phase should end."""
        if outcome.action is PhaseAction.CONTINUE:
            self._pending_completion = False
            return output, False
        if not self._completion_requires_confirmation:
            self._pending_completion = False
            self._phase_outcome = outcome
            return output, True
        if self._pending_completion:
            self._pending_completion = False
            self._phase_outcome = outcome
            return output, True
        self._pending_completion = True
        return self._get_completion_confirmation_message(output), False

    def _trajectory_action_name(self, outcome: PhaseOutcome) -> str:
        """Return the stable trajectory name for a completed phase action."""
        if outcome.action is PhaseAction.TASK_COMPLETE:
            return self._completion_trajectory_name or "task_complete"
        return outcome.action.value

    @staticmethod
    def _append_native_tool_acknowledgements(
        chat: Chat,
        tool_calls: list[dict[str, Any]],
    ) -> None:
        """Close native tool calls before potentially blocking tool execution."""
        for tool_call in tool_calls:
            chat._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": "executed",
                }
            )
        if tool_calls:
            chat.reset_response_chain()

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
                model = self._model_name.removeprefix("openai/")
                token_usage = TokenUsage()
                token_usage.add(model, usage_data)
                return UsageInfo(
                    prompt_tokens=token_usage.input_tokens,
                    completion_tokens=token_usage.output_tokens,
                    cache_tokens=token_usage.cached_input_tokens,
                    cost_usd=estimate_cost_usd(model, token_usage) or 0.0,
                )
        except (AttributeError, TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _responses_input(messages: list[dict]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert chat history into OpenAI Responses input items."""
        instructions: list[str] = []
        items: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                if content:
                    instructions.append(str(content))
                continue
            if role == "user":
                items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": str(content)}],
                    }
                )
                continue
            if role == "assistant":
                if content:
                    items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": str(content)}],
                        }
                    )
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function") or {}
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments", "{}"),
                        }
                    )
                continue
            if role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.get("tool_call_id"),
                        "output": str(content),
                    }
                )
        return "\n\n".join(instructions) or None, items

    def _parse_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> tuple[list[Command], PhaseOutcome, str, str, str, ImageReadRequest | None]:
        """Parse tool calls into commands.

        Returns:
            Commands, phase outcome, feedback, analysis, plan, and image request.
        """
        commands = []
        outcome = PhaseOutcome()
        feedback = ""
        analysis = ""
        plan = ""
        image_read = None

        if not tool_calls:
            if self._complete_on_no_tool_response:
                outcome = PhaseOutcome(PhaseAction.TASK_COMPLETE)
                return commands, outcome, feedback, analysis, plan, image_read
            feedback = (
                "WARNINGS: Your response contained no tool calls. "
                "Please use execute_commands to run commands."
            )
            return commands, outcome, feedback, analysis, plan, image_read

        if len(tool_calls) > 1:
            feedback = (
                "WARNINGS: Call exactly one native tool per response. "
                "Batch shell commands inside one execute_commands call."
            )
            return commands, outcome, feedback, analysis, plan, image_read

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
                if outcome.action is not PhaseAction.CONTINUE:
                    feedback = "WARNINGS: Call only one phase-ending tool per response."
                    outcome = PhaseOutcome()
                else:
                    outcome = PhaseOutcome(PhaseAction.TASK_COMPLETE)
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
                available = ["execute_commands", "image_read"]
                if self._completion_tool_name is not None:
                    available.append(self._completion_tool_name)
                feedback = (
                    f"WARNINGS: Unknown function '{function_name}'. "
                    f"Please use one of: {', '.join(available)}."
                )
                self.logger.warning(f"Unknown function called: {function_name}")

        return commands, outcome, feedback, analysis, plan, image_read

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
        # Image analysis doesn't need high reasoning effort
        # Skip reasoning_effort to use default (faster response)
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
        if getattr(self._llm, "_use_responses_api", False):
            return await self._call_responses_with_tools(messages)

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

    async def _call_responses_with_tools(
        self,
        messages: list[dict],
    ) -> ToolCallResponse:
        """Call litellm.aresponses while preserving native tool calls."""
        instructions, input_items = self._responses_input(messages)
        tools = [
            {
                "type": "function",
                **tool["function"],
            }
            for tool in self._get_tool_definitions()
        ]
        request: dict[str, Any] = {
            "model": self._model_name,
            "input": input_items,
            "tools": tools,
            "timeout": 900,
            "drop_params": True,
        }
        if instructions:
            request["instructions"] = instructions
        api_base = getattr(self._llm, "_api_base", None)
        if api_base:
            request["api_base"] = api_base
        request.update(getattr(self._llm, "_llm_kwargs", {}))
        max_output_tokens = self._llm.get_model_output_limit()
        if max_output_tokens is not None:
            request["max_output_tokens"] = max_output_tokens
        if self._reasoning_effort:
            request["reasoning"] = {"effort": self._reasoning_effort}

        try:
            response = await litellm.aresponses(**request)
        except LiteLLMContextWindowExceededError:
            raise ContextLengthExceededError()

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in getattr(response, "output", ()) or ():
            item_type = getattr(item, "type", None)
            if item_type == "message":
                for part in getattr(item, "content", ()) or ():
                    if getattr(part, "type", None) == "output_text":
                        text = getattr(part, "text", "")
                        if text:
                            content_parts.append(text)
            elif item_type == "function_call":
                call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": getattr(item, "name", ""),
                            "arguments": getattr(item, "arguments", "{}"),
                        },
                    }
                )
            elif item_type == "reasoning":
                for summary in getattr(item, "summary", ()) or ():
                    text = getattr(summary, "text", "")
                    if text:
                        reasoning_parts.append(text)

        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        if status == "incomplete" and getattr(incomplete, "reason", None) == "max_output_tokens":
            raise OutputLengthExceededError(
                "Response was truncated due to max output tokens",
                truncated_response="\n".join(content_parts),
            )
        return ToolCallResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            reasoning_content="\n".join(reasoning_parts) or None,
            usage=self._extract_usage_info(response),
        )

    async def _handle_llm_interaction(
        self,
        chat: Chat,
        prompt: str | None,
        logging_paths: tuple[Path | None, Path | None, Path | None],
        original_instruction: str = "",
        session: TmuxSession | None = None,
    ) -> tuple[
        list[Command],
        PhaseOutcome,
        str,
        str,
        str,
        LLMResponse,
        ImageReadRequest | None,
        list[dict[str, Any]],
    ]:
        """Handle LLM interaction using native tool calling.

        This overrides the parent's _handle_llm_interaction to use native tools
        instead of JSON/XML parsing.
        """
        _, prompt_path, response_path = logging_paths

        if prompt_path is not None:
            prompt_path.write_text(prompt or "")

        # Build messages from chat history + new prompt
        messages = chat.messages.copy()
        if prompt is not None:
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

            if prompt is not None:
                chat._messages.append({"role": "user", "content": prompt})
            chat._messages.append(assistant_message)
            self._append_native_tool_acknowledgements(chat, tool_response.tool_calls)

            # Update cumulative metrics
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
            self._append_native_tool_acknowledgements(chat, tool_response.tool_calls)

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

            if prompt is not None:
                chat._messages.append({"role": "user", "content": prompt})
            chat._messages.extend(
                [
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
            self._append_native_tool_acknowledgements(chat, tool_response.tool_calls)

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
        commands, phase_outcome, feedback, analysis, plan, image_read = self._parse_tool_calls(
            tool_response.tool_calls
        )

        # Create LLMResponse for compatibility with parent class
        llm_response = LLMResponse(
            content=tool_response.content or "",
            reasoning_content=tool_response.reasoning_content,
            usage=tool_response.usage,
        )

        return (
            commands,
            phase_outcome,
            feedback,
            analysis,
            plan,
            llm_response,
            image_read,
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
        if getattr(self, "_include_initial_handoff", False):
            prior_handoff = await self._read_runtime_handoff(self._session)
            if prior_handoff:
                prompt = "\n\n".join((prior_handoff, prompt))
            self._include_initial_handoff = False

        self._context.n_input_tokens = 0
        self._context.n_output_tokens = 0
        self._context.n_cache_tokens = 0
        self._context.cost_usd = None

        episodes = itertools.count() if self._max_episodes is None else range(self._max_episodes)
        for episode in episodes:
            self._n_episodes = episode + 1
            if not await self._with_block_timeout(self._session.is_session_alive()):
                self.logger.debug("Session has ended, breaking out of agent loop")
                return episode + 1

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
                phase_outcome,
                feedback,
                analysis,
                plan,
                llm_response,
                image_read,
                _native_tool_calls,
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

            promotion_gate_feedback = ""
            if phase_outcome.action is not PhaseAction.CONTINUE:
                gate_errors = await self._promotion_gate_errors(self._session)
                if gate_errors:
                    phase_outcome = PhaseOutcome()
                    promotion_gate_feedback = (
                        "WARNINGS: PROMOTION GATE BLOCKED; no verification was requested.\n"
                        + "\n".join(f"- {error}" for error in gate_errors)
                        + "\nCreate or repair .autoresearch/promotion.json, then retry completion."
                    )
                    feedback = "\n".join(filter(None, (feedback, promotion_gate_feedback)))

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

            self._record_asciinema_marker(
                f"Episode {episode}: {len(commands)} commands"
                + (" (image_read)" if image_read else ""),
            )

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

            await self._write_runtime_handoff(
                self._session,
                episode=episode,
                phase="planned",
                analysis=analysis,
                plan=plan,
                commands=commands,
            )

            if image_read is not None:
                # File read path
                image_read_result = await self._execute_image_read(
                    image_read, chat, original_instruction
                )
                await self._write_runtime_handoff(
                    self._session,
                    episode=episode,
                    phase="observed-image",
                    analysis=analysis,
                    plan=plan,
                    commands=commands,
                    terminal_output=image_read_result,
                )

                observation, completion_confirmed = self._resolve_completion_request(
                    phase_outcome,
                    image_read_result,
                )
                if (
                    phase_outcome.action is PhaseAction.CONTINUE
                    and feedback
                    and "WARNINGS:" in feedback
                ):
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
                    if (
                        phase_outcome.action is not PhaseAction.CONTINUE
                        and self._completion_tool_name is not None
                    ):
                        tool_calls_list.append(
                            ToolCall(
                                tool_call_id=f"call_{episode}_{phase_outcome.action.value}",
                                function_name=self._trajectory_action_name(phase_outcome),
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
                # Commands path (existing behavior)
                timeout_occurred, terminal_output = await self._with_block_timeout(
                    self._execute_commands(
                        commands,
                        self._session,
                    )
                )

                limited_output = self._limit_output_length(terminal_output)
                await self._write_runtime_handoff(
                    self._session,
                    episode=episode,
                    phase="observed-command",
                    analysis=analysis,
                    plan=plan,
                    commands=commands,
                    terminal_output=limited_output,
                )
                observation, completion_confirmed = self._resolve_completion_request(
                    phase_outcome,
                    limited_output,
                )
                if (
                    phase_outcome.action is PhaseAction.CONTINUE
                    and feedback
                    and "WARNINGS:" in feedback
                ):
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
                    if (
                        phase_outcome.action is not PhaseAction.CONTINUE
                        and self._completion_tool_name is not None
                    ):
                        tool_calls_list.append(
                            ToolCall(
                                tool_call_id=f"call_{episode}_{phase_outcome.action.value}",
                                function_name=self._trajectory_action_name(phase_outcome),
                                arguments={},
                            )
                        )
                        if not commands:
                            observation_results.append(ObservationResult(content=observation))
                    elif not commands:
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
