"""Apply fixed submission patches in separate PerfRace trials.

PatchAgent applies each task's patch relative to its editable project workdir.
The agent uses Harbor's task short name to select the patch from
``patches_by_instance``. PerfRace runs a separate nop baseline for comparison.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

CONTAINER_PATCH_PATH = "/tmp/perfrace-submission.patch"


class PatchAgent(BaseAgent):
    """Apply one task's submission patch to its agent-editable workspace."""

    def __init__(
        self,
        *args,
        patches_by_instance: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._patches_by_instance = dict(patches_by_instance or {})

    @staticmethod
    def name() -> str:
        return "patch"

    def version(self) -> str | None:
        return "0.1"

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        instance_id = environment.environment_name
        patch_path = self._patches_by_instance.get(instance_id)
        if patch_path is None:
            raise FileNotFoundError(
                f"No submission patch configured for task {instance_id!r}; "
                "the submission's predictions.jsonl must cover every task in this job."
            )

        await environment.upload_file(Path(patch_path), CONTAINER_PATCH_PATH)
        result = await environment.exec(command=f"git apply {shlex.quote(CONTAINER_PATCH_PATH)}")

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "return-code.txt").write_text(str(result.return_code))
        if result.stdout:
            (self.logs_dir / "stdout.txt").write_text(result.stdout)
        if result.stderr:
            (self.logs_dir / "stderr.txt").write_text(result.stderr)
        if result.return_code != 0:
            raise RuntimeError(
                f"Failed to apply submission patch for {instance_id!r}: "
                f"{result.stdout or ''}{result.stderr or ''}"
            )
