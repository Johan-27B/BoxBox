from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from perfrace.curate.dashboard.session import write_run_config
from perfrace.run.config import load_run


def test_copilot_run_config_has_paired_gateway_and_host_wiring(tmp_path: Path) -> None:
    instance = (tmp_path / "instances" / "project--workload").resolve()
    path = tmp_path / "session" / "run.yaml"
    path.parent.mkdir()

    write_run_config(
        path,
        instance_path=instance,
        session_id="00000000-0000-4000-8000-000000000001",
        candidate_agent="copilot-cli",
        candidate_model="gpt-5.5",
        candidate_timeout_seconds=1800,
        gateway_port=43210,
    )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["enable_cache"] is False
    assert raw["api_gateway"]["port"] == 43210
    assert "command" not in raw["api_gateway"]
    assert raw["job"]["job_name"] == ("pair-verification-00000000-0000-4000-8000-000000000001")
    assert raw["job"]["n_attempts"] == 1
    assert raw["job"]["n_concurrent_trials"] == 1
    assert raw["job"]["tasks"] == [{"path": str(instance)}]
    agent = raw["job"]["agents"][0]
    assert agent["name"] == "copilot-cli"
    assert agent["model_name"] == "gpt-5.5"
    assert agent["override_timeout_sec"] == 1800
    assert agent["kwargs"]["reasoning_effort"] == "high"
    assert agent["env"]["COPILOT_PROVIDER_WIRE_API"] == "responses"
    overlay = Path(raw["job"]["environment"]["extra_docker_compose"][0])
    assert overlay == path.parent / "host-gateway.yaml"
    assert "host.docker.internal:host-gateway" in overlay.read_text(encoding="utf-8")

    loaded = load_run(path)
    assert loaded.enable_cache is False
    assert loaded.job.tasks[0].path == instance
    assert loaded.job.agents[0].env["COPILOT_PROVIDER_BASE_URL"] == (
        "http://host.docker.internal:9/v1"
    )


def test_non_copilot_run_config_uses_native_harbor_agent(tmp_path: Path) -> None:
    instance = (tmp_path / "instances" / "project--workload").resolve()
    path = tmp_path / "session" / "run.yaml"
    path.parent.mkdir()

    write_run_config(
        path,
        instance_path=instance,
        session_id="00000000-0000-4000-8000-000000000002",
        candidate_agent="claude-code",
        candidate_model="claude-sonnet-4-5",
        candidate_timeout_seconds=1800,
        gateway_port=43211,
    )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "api_gateway" not in raw
    assert raw["job"]["environment"] == {"type": "docker"}
    assert raw["job"]["agents"] == [
        {
            "name": "claude-code",
            "model_name": "claude-sonnet-4-5",
            "n_concurrent": 1,
            "override_timeout_sec": 1800,
        }
    ]
    assert not (path.parent / "host-gateway.yaml").exists()


def test_run_config_write_does_not_follow_final_symlink(tmp_path: Path) -> None:
    instance = (tmp_path / "instances" / "project--workload").resolve()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    victim = tmp_path / "victim.yaml"
    victim.write_text("keep: me\n", encoding="utf-8")
    path = session_dir / "run.yaml"
    path.symlink_to(victim)

    with pytest.raises(OSError):
        write_run_config(
            path,
            instance_path=instance,
            session_id="00000000-0000-4000-8000-000000000003",
            candidate_agent="claude-code",
            candidate_model="claude-sonnet-4-5",
            candidate_timeout_seconds=1800,
            gateway_port=43212,
        )

    assert victim.read_text(encoding="utf-8") == "keep: me\n"
