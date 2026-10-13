import json
import os
from pathlib import Path

from perfrace.evolution import nexau_runner


def test_run_nexau_agent_sets_context_headers_and_persists_trace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeAgent:
        full_trace = ["trace-event"]
        history = []

        @classmethod
        def from_yaml(cls, path):
            captured["config"] = path
            return cls()

        def run(self, **kwargs):
            captured["run"] = kwargs
            captured["tool_output_dir"] = os.environ["NEXAU_TOOL_OUTPUT_DIR"]
            kwargs["custom_llm_client_provider"]("evolver")
            return "completed"

    monkeypatch.setattr(nexau_runner, "Agent", FakeAgent)
    monkeypatch.setattr(nexau_runner, "OpenAI", FakeClient)
    monkeypatch.setenv("LLM_MODEL", "previous-model")

    result = nexau_runner.run_nexau_agent(
        config_path=tmp_path / "agent.yaml",
        workspace=tmp_path,
        output_dir=tmp_path / "output",
        model="test-model",
        base_url="http://127.0.0.1:4003/v1",
        api_key="test-key",
        reasoning_effort="high",
        session_id="generation-1",
        message="analyze",
        context={"generation": 1},
        read_roots=(tmp_path,),
        write_roots=(tmp_path / "output",),
        shell_root=tmp_path,
    )

    assert result == "completed"
    assert captured["client"]["default_headers"] == {"X-PerfRace-Session": "generation-1:evolver"}
    assert captured["run"]["context"] == {"generation": 1}
    assert captured["tool_output_dir"] == str(tmp_path / "output" / "tool-outputs")
    assert os.environ["LLM_MODEL"] == "previous-model"
    assert "NEXAU_TOOL_OUTPUT_DIR" not in os.environ
    assert (tmp_path / "output" / "result.md").read_text() == "completed\n"
    assert json.loads((tmp_path / "output" / "trajectory.json").read_text()) == ["trace-event"]
    assert nexau_runner.validate_nexau_output(tmp_path / "output")
