"""Fixed-harness frozen harness backed by one persistent Terminus-KIRA chat."""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import override

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Step

from .terminus_kira import TerminusKira

_FINISH_DESCRIPTION = (
    "Finish final delivery after leaving the workspace clean and coherent. "
    "Do not start new research in this phase. "
    "Preserve the fastest causally supported accepted candidate rather than "
    "leaving a later or unexplained timing state."
)

_FINAL_DELIVERY_HANDOFF = (
    "Final-delivery handoff (selection, not research): do not make a new "
    "optimization edit or remeasure an unchanged candidate. First inspect the "
    "current status and HEAD, then use the verifier result, checkpoint evidence, "
    "Git history/notes, and the existing promotion packet to identify the fastest "
    "accepted checkpoint whose timing is attributable to an exact clean candidate. "
    "If the current clean candidate is that winner, leave it unchanged. If a "
    "different supported candidate is recoverable, restore that exact candidate; "
    "if no source change has supported evidence, leave clean main rather than "
    "promoting a noisy baseline timing. Do not replace a supported winner with a "
    "later slower or speculative state. Before calling finish, ensure the shell "
    "is idle, the worktree is clean, and HEAD is the candidate you intend the "
    "final verifier to measure."
)

# Keep provenance recovery in the harness rather than asking the model to parse
# every note. Accept either a JSON note or JSON embedded in a textual note and
# search nested measurement objects conservatively.
_MEASURED_CANDIDATE_SCAN = r"""python3 - <<'PY'
import json
import re
import subprocess

sha_re = re.compile(r"^[0-9a-fA-F]{40}$")


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=False)


def decode(text):
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def accepted_values(node):
    if isinstance(node, dict):
        verdict = node.get("verdict")
        value = node.get("value")
        if verdict == "ACCEPTED" and isinstance(value, (int, float)) and not isinstance(value, bool):
            yield float(value)
        for child in node.values():
            yield from accepted_values(child)
    elif isinstance(node, list):
        for child in node:
            yield from accepted_values(child)


listing = run("git", "notes", "--ref=perfrace-measurements", "list")
candidates = []
if listing.returncode == 0:
    for line in listing.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        note_object, target_object = fields[0], fields[-1]
        shown = run("git", "notes", "--ref=perfrace-measurements", "show", target_object)
        payload = decode(shown.stdout) if shown.returncode == 0 else None
        if payload is None:
            continue
        target = payload.get("target_commit") if isinstance(payload, dict) else None
        if not isinstance(target, str) or not sha_re.fullmatch(target):
            target = target_object if sha_re.fullmatch(target_object) else None
        if target is None:
            continue
        for seconds in accepted_values(payload):
            if seconds > 0:
                candidates.append({"commit": target, "seconds": seconds, "note": note_object})

best = min(candidates, key=lambda item: item["seconds"], default=None)
print(json.dumps(best or {"status": "none"}, separators=(",", ":")))
PY"""


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

    async def _prepare_measured_candidate_handoff(self) -> str:
        """Reconcile a clean worktree with the fastest accepted note, if any.

        Verifier notes are the durable bridge between a checkpoint and a later
        continuation. Only a clean tree is mutated: an in-progress dirty
        candidate is never discarded by recovery, and malformed notes are
        reported to the model instead of being guessed at.
        """
        if self._session is None:
            return "MEASURED-CANDIDATE HANDOFF: terminal session is unavailable."
        environment = self._session.environment
        workdir = environment.task_env_config.workdir
        status = await environment.exec(
            "git status --porcelain=v1 --untracked-files=all",
            cwd=workdir,
            timeout_sec=30,
        )
        if status.return_code != 0:
            return (
                "MEASURED-CANDIDATE HANDOFF: could not inspect worktree status; "
                "do not overwrite the current candidate until status is checked."
            )
        if status.stdout.strip():
            return (
                "MEASURED-CANDIDATE HANDOFF: worktree is dirty, so the harness "
                "did not restore an accepted commit. Inspect and preserve or "
                "discard the in-progress candidate explicitly before continuing."
            )

        scan = await environment.exec(
            _MEASURED_CANDIDATE_SCAN,
            cwd=workdir,
            timeout_sec=30,
        )
        if scan.return_code != 0:
            return (
                "MEASURED-CANDIDATE HANDOFF: measurement-note scan failed; inspect "
                "perfrace-measurements and the current HEAD before changing state."
            )
        try:
            record = json.loads(scan.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return (
                "MEASURED-CANDIDATE HANDOFF: measurement-note scan returned an "
                "unreadable result; no candidate was restored."
            )
        candidate = record.get("commit") if isinstance(record, dict) else None
        seconds = record.get("seconds") if isinstance(record, dict) else None
        status_value = record.get("status") if isinstance(record, dict) else None
        if status_value == "none" or not isinstance(candidate, str):
            return (
                "MEASURED-CANDIDATE HANDOFF: no parseable accepted measurement "
                "was found; no candidate was restored."
            )
        if not re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
            return (
                "MEASURED-CANDIDATE HANDOFF: ignored a note with an invalid commit "
                "identifier; no candidate was restored."
            )
        present = await environment.exec(
            f"git cat-file -e {shlex.quote(candidate)}^{{commit}}",
            cwd=workdir,
            timeout_sec=30,
        )
        if present.return_code != 0:
            return (
                "MEASURED-CANDIDATE HANDOFF: the fastest accepted note references "
                "a commit unavailable in this checkout; no candidate was restored."
            )
        current = await environment.exec(
            "git rev-parse HEAD",
            cwd=workdir,
            timeout_sec=30,
        )
        current_head = current.stdout.strip() if current.return_code == 0 else ""
        timing = f" ({float(seconds):.6g} s)" if isinstance(seconds, (int, float)) else ""
        if current_head.lower() == candidate.lower():
            return (
                f"MEASURED-CANDIDATE HANDOFF: HEAD is already the fastest accepted "
                f"candidate {candidate}{timing}; preserve it."
            )

        restored = await environment.exec(
            f"git checkout --detach --quiet {shlex.quote(candidate)}",
            cwd=workdir,
            timeout_sec=30,
        )
        if restored.return_code != 0:
            return (
                f"MEASURED-CANDIDATE HANDOFF: fastest accepted candidate {candidate}"
                f"{timing} could not be restored automatically; keep the tree clean "
                "and restore it only after inspecting the checkout error."
            )
        return (
            f"MEASURED-CANDIDATE HANDOFF: restored fastest accepted candidate "
            f"{candidate}{timing} from perfrace-measurements. Keep this exact clean "
            "HEAD for delivery, or switch deliberately before a new hypothesis."
        )

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

        measured_candidate_handoff = await self._prepare_measured_candidate_handoff()
        runtime_journal = await self._read_runtime_command_journal(self._session)
        effective_prompt = "\n\n".join(
            part
            for part in (
                measured_candidate_handoff,
                runtime_journal,
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
                f"{_FINAL_DELIVERY_HANDOFF}\n\n{instruction}",
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
