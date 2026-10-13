"""Fixed-harness frozen harness backed by one persistent Terminus-KIRA chat."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import override

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Step

from .terminus_kira import TerminusKira

_FINISH_DESCRIPTION = (
    "Finish final delivery after leaving the workspace clean and coherent. "
    "Do not start new research in this phase."
)


class TerminusBoxBox(TerminusKira):
    """Resume one fixed Terminus-KIRA chat across verifier checkpoints."""

    SUPPORTS_RESUME = True
    RESUME_PREFIX = (
        "This is a new checkpoint in the same optimization run. Continue from "
        "the current workspace and session state. First inspect the verifier result "
        "and the exact measured commit, then compare it with the fastest prior "
        "accepted candidate and its correctness evidence. Preserve the best "
        "causally supported candidate before exploring further: an unexplained "
        "timing, an unchanged tree, or a shell-interrupted run is not evidence of "
        "a speedup. Any new experiment must start from that preserved candidate, "
        "and final delivery must leave it (or a better measured candidate) clean "
        "and reproducible."
    )

    def __init__(self, *args, **kwargs) -> None:
        if kwargs.get("max_turns") is not None:
            raise ValueError("TerminusBoxBox uses only the shared active-agent time budget")
        trajectory_config = kwargs.get("trajectory_config") or {}
        if trajectory_config.get("linear_history"):
            raise ValueError(
                "TerminusBoxBox does not support linear_history across checkpoints"
            )
        extra_env = dict(kwargs.get("extra_env") or {})
        model_name = kwargs.get("model_name")
        if isinstance(model_name, str) and "/" not in model_name:
            kwargs["model_name"] = f"openai/{model_name}"
        api_base = extra_env.get("LLM_BASE_URL")
        if api_base:
            api_base = api_base.replace(
                "://host.docker.internal:",
                "://127.0.0.1:",
            )
        kwargs.setdefault("api_base", api_base)
        llm_kwargs = dict(kwargs.get("llm_kwargs") or {})
        if extra_env.get("LLM_API_KEY"):
            llm_kwargs.setdefault("api_key", extra_env["LLM_API_KEY"])
        kwargs["llm_kwargs"] = llm_kwargs
        kwargs.setdefault("record_terminal_session", False)
        kwargs.setdefault("use_responses_api", True)
        super().__init__(*args, **kwargs)
        prompt_prefix = (
            self._get_prompt_template_path()
            .read_text(encoding="utf-8")
            .partition("\nTask Description:")[0]
            .strip()
        )
        # The parent installs the generic research contract, but the checkpoint
        # wrapper historically replaced it with only the short prompt prefix.
        # Keep task/checkpoint text out of the system message while retaining
        # the contract that teaches the agent how to select and validate work.
        contract_path = Path(__file__).parent / "skills" / "autoresearch" / "SKILL.md"
        self._system_prompt = (
            f"{prompt_prefix}\n\n"
            f"{contract_path.read_text(encoding='utf-8').strip()}"
        )
        self._llm_kwargs = {
            key: value for key, value in (self._llm_kwargs or {}).items() if key != "api_key"
        }

    @staticmethod
    @override
    def name() -> str:
        return "offline-terminus-boxbox"

    @override
    def _get_prompt_template_path(self) -> Path:
        """Use the checkpoint-aware long-horizon research prompt."""
        return Path(__file__).parent / "prompt-templates" / "terminus-boxbox.txt"

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run the first checkpoint and interrupt terminal work on cancellation."""
        try:
            await super().run(instruction, environment, context)
        except asyncio.CancelledError:
            await asyncio.shield(self._interrupt_active_command())
            raise

    def _reset_checkpoint_state(self) -> tuple[int, str]:
        """Reset turn-local state without replacing the persistent Chat."""
        summarization_count = self._summarization_count
        session_id = self._session_id
        pending_handoff_prompt = self._pending_handoff_prompt
        pending_subagent_refs = self._pending_subagent_refs
        self._reset_per_run_state()
        self._summarization_count = summarization_count
        self._session_id = session_id
        self._pending_handoff_prompt = pending_handoff_prompt
        self._pending_subagent_refs = pending_subagent_refs
        return summarization_count, session_id

    async def _interrupt_active_command(self) -> None:
        """Interrupt tmux foreground work before verifier access to the workspace."""
        if self._session is None or not await self._session.is_session_alive():
            return
        await self._session.send_keys(
            keys=["C-c"],
            min_timeout_sec=0.5,
        )

    def _populate_checkpoint_context(
        self,
        context: AgentContext,
        *,
        prompt_details_before: int,
        completion_details_before: int,
        logprobs_before: int,
        extra_before: int,
        summarizations_before: int,
    ) -> None:
        """Store rollout details and metadata produced by this checkpoint."""
        if self._chat is None:
            raise RuntimeError("Persistent Terminus-KIRA Chat is unavailable")

        detail = {}
        prompt_ids = self._chat._prompt_token_ids_list[prompt_details_before:]
        completion_ids = self._chat._completion_token_ids_list[completion_details_before:]
        logprobs = self._chat._logprobs_list[logprobs_before:]
        extras = self._chat._extra_list[extra_before:]
        if prompt_ids:
            detail["prompt_token_ids"] = prompt_ids
        if completion_ids:
            detail["completion_token_ids"] = completion_ids
        if logprobs:
            detail["logprobs"] = logprobs
        if extras:
            all_keys = {key for item in extras for key in item}
            detail["extra"] = {key: [item.get(key) for item in extras] for key in sorted(all_keys)}
        context.rollout_details = [
            *([detail] if detail else []),
            *self._subagent_rollout_details,
        ]
        context.metadata = {
            "n_episodes": self._n_episodes,
            "api_request_times_msec": self._api_request_times,
            "summarization_count": self._summarization_count - summarizations_before,
        }
        if self._store_all_messages:
            context.metadata["all_messages"] = self._chat.messages

    async def _continue_chat(
        self,
        prompt: str,
        *,
        original_instruction: str,
        context: AgentContext,
    ) -> None:
        """Continue the persistent Chat for a resumed or delivery turn."""
        if self._chat is None:
            raise RuntimeError("Cannot resume Terminus-KIRA before its first checkpoint")
        if self._session is None:
            raise RuntimeError("Terminus-KIRA terminal session is unavailable")
        terminal_recovery_prompt: str | None = None
        if not await self._session.is_session_alive():
            self._session._previous_buffer = None
            await self._session.start()
            terminal_recovery_prompt = (
                "The persistent terminal shell exited after the previous turn. "
                "A fresh shell was started in the task workspace. Files are "
                "preserved, but shell-local state such as the working directory, "
                "exported variables, shell options, and background processes was "
                "lost. Inspect the workspace before continuing."
            )

        summarizations_before, _ = self._reset_checkpoint_state()
        self._context = context
        prompt_details_before = len(self._chat._prompt_token_ids_list)
        completion_details_before = len(self._chat._completion_token_ids_list)
        logprobs_before = len(self._chat._logprobs_list)
        extra_before = len(self._chat._extra_list)

        effective_prompt = "\n\n".join(
            part
            for part in (
                self._pending_handoff_prompt,
                terminal_recovery_prompt,
                prompt,
            )
            if part
        )
        self._trajectory_steps.append(
            Step(
                step_id=1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="user",
                message=effective_prompt,
            )
        )
        try:
            await self._run_agent_loop(
                initial_prompt=effective_prompt,
                chat=self._chat,
                original_instruction=original_instruction,
            )
        except asyncio.CancelledError:
            await asyncio.shield(self._interrupt_active_command())
            raise
        finally:
            self._populate_checkpoint_context(
                context,
                prompt_details_before=prompt_details_before,
                completion_details_before=completion_details_before,
                logprobs_before=logprobs_before,
                extra_before=extra_before,
                summarizations_before=summarizations_before,
            )
            self._dump_trajectory()

    @override
    async def resume(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Continue the existing Chat with neutral verifier feedback."""
        continuation = f"{self.RESUME_PREFIX} {instruction}"
        await self._continue_chat(
            continuation,
            original_instruction=getattr(
                self,
                "_original_instruction",
                instruction,
            ),
            context=context,
        )

    async def finalize(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run the reserved final delivery turn in the persistent Chat."""
        previous_name = self._completion_tool_name
        previous_description = self._completion_tool_description
        previous_trajectory_name = self._completion_trajectory_name
        self._completion_tool_name = "finish"
        self._completion_tool_description = _FINISH_DESCRIPTION
        self._completion_trajectory_name = "finish"
        try:
            await self._continue_chat(
                instruction,
                original_instruction=getattr(
                    self,
                    "_original_instruction",
                    instruction,
                ),
                context=context,
            )
        finally:
            self._completion_tool_name = previous_name
            self._completion_tool_description = previous_description
            self._completion_trajectory_name = previous_trajectory_name
