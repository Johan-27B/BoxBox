"""Load standalone copies of the TerminusBoxBox harness for external evolution."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

from boxbox.terminus_boxbox.kernel.interfaces import RuntimeTrap


def validate_harness_source(source: Path, *, identity: str) -> type[Any]:
    """Compile and load a harness exporting the current TerminusBoxBox contract.

    Loading executes Python on the host. Only use this with trusted harness code;
    interface validation is not a security sandbox.
    """
    source = source.resolve()
    init = source / "__init__.py"
    if not init.is_file():
        raise ValueError(f"Harness source must contain __init__.py: {source}")
    for path in sorted(source.rglob("*.py")):
        if ".git" in path.relative_to(source).parts:
            continue
        compile(path.read_bytes(), str(path), "exec")
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:16]
    module_name = f"_perfrace_harness_{suffix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name, init, submodule_search_locations=[str(source)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load harness from {init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        runtime_class = getattr(module, "TerminusBoxBox", None)
        if not isinstance(runtime_class, type):
            raise TypeError("Harness must export the TerminusBoxBox class")
        required = (
            "setup", "set_task_instruction", "ensure_agent_session",
            "configure_target_phase", "run_until_trap",
            "export_state", "import_state", "release_session", "attach_session",
            "restart_session", "prepare_continuation", "reconcile_review_trajectory",
            "mark_harness_context_accepted", "review",
        )
        missing = [name for name in required if not callable(getattr(runtime_class, name, None))]
        if missing:
            raise TypeError(f"Harness is missing runtime methods: {', '.join(missing)}")
        return runtime_class
    except BaseException:
        for name in list(sys.modules):
            if name == module_name or name.startswith(module_name + "."):
                sys.modules.pop(name, None)
        raise


class StaticRuntime:
    """Execute an HS attempt without enabling runtime-controlled harness reviews."""

    def __init__(self, runtime):
        self._runtime = runtime

    async def setup(self, environment):
        await self._runtime.setup(environment)

    async def run(self, instruction, environment, context):
        self._runtime.set_task_instruction(instruction)
        await self._runtime.ensure_agent_session()
        self._runtime.configure_target_phase(boxbox_enabled=False)
        trap = await self._runtime.run_until_trap(instruction, environment, context)
        if trap not in (None, RuntimeTrap.COMPLETE):
            raise RuntimeError(f"Static harness returned an unsupported trap: {trap}")

    async def finalize(self, instruction, environment, context):
        await self.run(
            f"{instruction}\n\nCall `submit` to complete final delivery after leaving "
            "the best validated candidate in the project workspace.",
            environment,
            context,
        )

    def __getattr__(self, name):
        return getattr(self._runtime, name)
