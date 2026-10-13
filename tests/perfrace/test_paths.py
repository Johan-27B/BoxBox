from __future__ import annotations

from pathlib import Path

from perfrace.paths import INSTANCE_ROOT_ENV, PROJECT_ROOT, resolve_instance_root


def test_instance_root_defaults_to_repository() -> None:
    assert resolve_instance_root() == PROJECT_ROOT.parent / "PerfRace-Bench"


def test_instance_root_prefers_explicit_then_environment(tmp_path: Path, monkeypatch) -> None:
    environment_root = tmp_path / "environment"
    explicit_root = tmp_path / "explicit"
    monkeypatch.setenv(INSTANCE_ROOT_ENV, str(environment_root))

    assert resolve_instance_root() == environment_root.resolve()
    assert resolve_instance_root(explicit_root) == explicit_root.resolve()
