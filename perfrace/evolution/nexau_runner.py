"""Run one host-local NexAU meta-agent with durable trajectory capture."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from perfrace.evolution.state import write_text_atomic

Agent: Any = None
OpenAI: Any = None


def validate_nexau_output(output_dir: Path) -> bool:
    """Validate one atomically completed NexAU result and trajectory pair."""
    result_path = output_dir / "result.md"
    trajectory_path = output_dir / "trajectory.json"
    completion_path = output_dir / "complete.json"
    if not (result_path.is_file() and trajectory_path.is_file() and completion_path.is_file()):
        return False
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(trajectory, list):
        return False
    return completion == {
        "schema_version": 1,
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "trajectory_sha256": hashlib.sha256(trajectory_path.read_bytes()).hexdigest(),
    }


def run_nexau_agent(
    *,
    config_path: Path,
    workspace: Path,
    output_dir: Path,
    model: str,
    base_url: str,
    api_key: str,
    reasoning_effort: str,
    session_id: str,
    message: str,
    context: dict[str, Any],
    read_roots: tuple[Path, ...],
    write_roots: tuple[Path, ...],
    shell_root: Path,
) -> str:
    """Run one NexAU agent and persist its complete trace and final result."""
    global Agent, OpenAI
    if Agent is None:
        from nexau import Agent as NexAUAgent

        Agent = NexAUAgent
    if OpenAI is None:
        from openai import OpenAI as OpenAIClient

        OpenAI = OpenAIClient
    resolved_workspace = workspace.expanduser().resolve()
    resolved_output = output_dir.expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    tool_output_dir = resolved_output / "tool-outputs"
    environment = {
        "EVOLVE_WORK_DIR": str(resolved_workspace),
        "NEXAU_TOOL_OUTPUT_DIR": str(tool_output_dir),
        "LLM_MODEL": model,
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": api_key,
        "LLM_REASONING_EFFORT": reasoning_effort,
        "PERFRACE_META_READ_ROOTS": os.pathsep.join(
            str(path.expanduser().resolve()) for path in read_roots
        ),
        "PERFRACE_META_WRITE_ROOTS": os.pathsep.join(
            str(path.expanduser().resolve()) for path in write_roots
        ),
        "PERFRACE_META_SHELL_ROOT": str(shell_root.expanduser().resolve()),
    }
    previous = {key: os.environ.get(key) for key in environment}
    os.environ.update(environment)
    agent = Agent.from_yaml(config_path.expanduser().resolve())
    clients: list[Any] = []

    def client_provider(agent_name: str) -> Any:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"X-PerfRace-Session": f"{session_id}:{agent_name}"},
        )
        clients.append(client)
        return client

    result: object | None = None
    succeeded = False
    try:
        result = agent.run(
            message=message,
            context=context,
            custom_llm_client_provider=client_provider,
        )
        text = result[0] if isinstance(result, tuple) else result
        if not isinstance(text, str):
            raise TypeError("NexAU agent did not return a text result")
        write_text_atomic(resolved_output / "result.md", f"{text.rstrip()}\n")
        succeeded = True
        return text
    finally:
        trace = []
        for item in agent.full_trace or list(agent.history):
            if hasattr(item, "model_dump"):
                trace.append(item.model_dump(mode="json"))
            else:
                trace.append(str(item))
        trajectory_path = resolved_output / "trajectory.json"
        write_text_atomic(
            trajectory_path,
            json.dumps(trace, ensure_ascii=True, indent=2, default=str) + "\n",
        )
        if succeeded:
            result_path = resolved_output / "result.md"
            write_text_atomic(
                resolved_output / "complete.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                        "trajectory_sha256": hashlib.sha256(
                            trajectory_path.read_bytes()
                        ).hexdigest(),
                    },
                    indent=2,
                )
                + "\n",
            )
        for client in clients:
            client.close()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
