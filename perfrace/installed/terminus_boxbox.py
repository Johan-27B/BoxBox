"""Run Terminus-BOXBOX on the host through Harbor's native agent interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from boxbox.terminus_boxbox import TerminusBoxBox, Kernel, harness
from boxbox.terminus_boxbox.kernel.interfaces import TaskPhase
from boxbox.terminus_boxbox.seed import materialize


class TerminusBoxBoxAgent(BaseAgent):
    """Keep the kernel and runtime alive across PerfRace evaluations."""

    SUPPORTS_RESUME = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        source = kwargs.pop("harness_source", None)
        self._harness_source = Path(source) if source is not None else None
        self._harness_revision = kwargs.pop("harness_revision", None)
        if self._harness_revision is not None and self._harness_source is None:
            raise ValueError("A harness revision requires an explicit source repository")
        runtime_kwargs = dict(kwargs)
        super().__init__(*args, **kwargs)
        if not self.model_name:
            raise ValueError("PerfRace agents require model_name")
        model_name = self.model_name if "/" in self.model_name else f"openai/{self.model_name}"
        api_base = self.extra_env.get("LLM_BASE_URL")
        if api_base:
            api_base = api_base.replace("://host.docker.internal:", "://127.0.0.1:")
        llm_kwargs = dict(runtime_kwargs.pop("llm_kwargs", {}) or {})
        if self.extra_env.get("LLM_API_KEY"):
            llm_kwargs.setdefault("api_key", self.extra_env["LLM_API_KEY"])
        runtime_kwargs.update(
            logs_dir=self.logs_dir,
            model_name=model_name,
            api_base=api_base,
            llm_kwargs=llm_kwargs,
            extra_env={
                **self.extra_env,
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "PAGER": "cat",
                "SYSTEMD_PAGER": "cat",
            },
            record_terminal_session=False,
            use_responses_api=True,
            completion_name="submit",
            completion_description="Call this to request official verification of the current candidate.",
        )
        self._kernel = Kernel(
            runtime_class=TerminusBoxBox,
            logs=self.logs_dir,
            constructor=runtime_kwargs,
        )

    @staticmethod
    def name() -> str:
        return "terminus-boxbox"

    def version(self) -> str:
        return "1.0.0"

    def task_phase(self) -> TaskPhase:
        return TaskPhase.TASK

    async def setup(self, environment: BaseEnvironment) -> None:
        workdir = environment.task_env_config.workdir
        if not workdir:
            raise ValueError("TerminusBoxBoxAgent requires a workdir")
        source = materialize(
            self._harness_source or Path(harness.__file__).parent,
            self.logs_dir / "initial-harness",
            revision=self._harness_revision,
        )
        await self._kernel.setup(environment, workdir=workdir, source=source)
        await self._kernel.active_runtime.setup(environment)

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._kernel.active_runtime.set_task_instruction(instruction)
        await self._kernel.run_active_runtime(
            instruction, environment, context, phase=self.task_phase()
        )

    async def resume(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        await self._kernel.resume(instruction, environment, context, phase=self.task_phase())

    async def finalize(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        """Deliver the best candidate without starting another harness review."""
        instruction = (
            f"{instruction}\n\n"
            "After leaving the best candidate clean and coherent, call `submit` "
            "exactly once to complete final delivery. This final-delivery submission "
            "is required even when the best candidate is unchanged and does not "
            "require another local measurement."
        )
        await self._kernel.run_active_runtime(
            instruction, environment, context, phase=TaskPhase.NO_REVIEW
        )
