from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfrace.curate.report import read_report
from perfrace.release.oci import ARTIFACT_TYPE, AttachedArtifact
from perfrace.release.publisher import (
    ImageRelease,
    InstancePublisher,
    InstanceValidationError,
)

IMAGE_DIGEST = "sha256:" + "a" * 64
ARTIFACT_DIGEST = "sha256:" + "b" * 64
IMAGE_REFERENCE = f"ghcr.io/example/perfrace-project-workload@{IMAGE_DIGEST}"


def _instance(root: Path, *, status: str = "IN_PROGRESS") -> Path:
    instance = root / "project--workload"
    workload = instance / "environment" / "workspace" / "workload"
    project = instance / "environment" / "workspace" / "project"
    tests = instance / "tests"
    workload.mkdir(parents=True)
    project.mkdir()
    (tests / "workload").mkdir(parents=True)
    (tests / "heldout").mkdir()
    (tests / "expected").mkdir()
    (project / "source.txt").write_text("source\n")
    (workload / "input.txt").write_text("input\n")
    (instance / "environment" / "Dockerfile").write_text(
        "FROM debian:bookworm-slim\nCOPY workspace/ /home/user/workspace/\n"
        "WORKDIR /home/user/workspace\n"
    )
    run_script = workload / "run.sh"
    run_script.write_text("#!/bin/sh\ncat input.txt\n")
    run_script.chmod(0o755)
    (tests / "workload" / "input.txt").write_text("input\n")
    for name in ("test.sh", "test_correctness.sh", "test_performance.sh"):
        script = tests / name
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
    (instance / "instruction.md").write_text("Optimize `project/`, then run `workload/run.sh`.\n")
    (instance / "task.toml").write_text(
        f'''schema_version = "1.3"

[task]
name = "perfrace/project--workload"
description = "Optimize a project workload"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"
workload = "project-workload"
n_warmup = 1
n_repetitions = 2
aggregator = "mean"
repetition_scope = "internal"

[agent]
timeout_sec = 1800

[verifier]
timeout_sec = 1200

[environment]
docker_image = "{IMAGE_REFERENCE if status == "ACCEPT" else "local/project:release"}"
workdir = "/home/user/workspace"
network_mode = "public"
cpus = 2
memory_mb = 8192
storage_mb = 10240
'''
    )
    (instance / "report.md").write_text(
        f"""---
schema: 1
instance: project--workload
status: {status}
realism: APPROVED
reliability: APPROVED
integrity: APPROVED
updated: 2026-09-02T00:00:00Z
---

# Project workload

| Field | Value |
|---|---|
| Source | https://github.com/example/project |
| Revision | `abc` |
| Image | Pending |
| Started | 2026-09-02T00:00:00Z |
| Completed | Pending |
| Agent cost | Pending |
| Human interactions | Pending |

## Overview

Project workload.
"""
    )
    return instance


class FakeDocker:
    def __init__(self) -> None:
        self.publish_count = 0
        self.verified_agent_setup: list[str] = []

    def inspect_local(self, local_image: str) -> tuple[str, int]:
        suffix = "d" if local_image.endswith(":different") else "c"
        return "sha256:" + suffix * 64, 123

    def publish(self, _local_image: str, repository: str, _tag: str) -> ImageRelease:
        self.publish_count += 1
        local_image_id, size_bytes = self.inspect_local(_local_image)
        return ImageRelease(
            reference=f"{repository}@{IMAGE_DIGEST}",
            repository=repository,
            manifest_digest=IMAGE_DIGEST,
            local_image_id=local_image_id,
            size_bytes=size_bytes,
        )

    def verify_existing(self, reference: str) -> ImageRelease:
        assert reference == IMAGE_REFERENCE
        return ImageRelease(
            reference=reference,
            repository=reference.split("@", 1)[0],
            manifest_digest=IMAGE_DIGEST,
            local_image_id=None,
            size_bytes=None,
        )

    def verify_agent_setup(self, reference: str) -> None:
        self.verified_agent_setup.append(reference)


class FakeOras:
    def __init__(self, *, fail_attach: bool = False) -> None:
        self.archive: bytes | None = None
        self.fail_attach = fail_attach
        self.attach_count = 0

    def preflight(self) -> None:
        pass

    def attach_task(self, **kwargs) -> AttachedArtifact:
        self.attach_count += 1
        if self.fail_attach:
            raise RuntimeError("attach failed")
        self.archive = kwargs["archive_path"].read_bytes()
        return AttachedArtifact(
            reference=f"ghcr.io/example/perfrace-project-workload@{ARTIFACT_DIGEST}",
            digest=ARTIFACT_DIGEST,
        )

    def fetch_manifest(self, _reference: str):
        return {
            "artifactType": ARTIFACT_TYPE,
            "subject": {"digest": IMAGE_DIGEST},
        }

    def pull(self, _reference: str, destination: Path) -> Path:
        assert self.archive is not None
        destination.mkdir(parents=True)
        target = destination / "task.tar.gz"
        target.write_bytes(self.archive)
        return target


def test_publish_writes_release_record_after_pullback(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root)
    docker = FakeDocker()
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=docker,
    )

    record = publisher.publish(
        instance,
        local_image="local/project:release",
        repository="ghcr.io/example/perfrace-project-workload",
        tag="release",
    )

    assert read_report(instance / "report.md").status == "ACCEPT"
    assert IMAGE_REFERENCE in (instance / "task.toml").read_text()
    release = json.loads((root / ".releases" / "project--workload.json").read_text())
    assert release["task_artifact"].endswith(ARTIFACT_DIGEST)
    assert release["task_content_hash"] == record.task_content_hash
    assert docker.verified_agent_setup == [IMAGE_REFERENCE]


def test_publish_keeps_live_files_unmodified_on_remote_failure(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root)
    original_task = (instance / "task.toml").read_text()
    original_report = (instance / "report.md").read_text()
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(fail_attach=True),
        docker=FakeDocker(),
    )

    with pytest.raises(RuntimeError, match="attach failed"):
        publisher.publish(
            instance,
            local_image="local/project:release",
            repository="ghcr.io/example/perfrace-project-workload",
            tag="release",
        )

    assert (instance / "task.toml").read_text() == original_task
    assert (instance / "report.md").read_text() == original_report
    assert not (root / ".releases" / "project--workload.json").exists()


def test_publish_rejects_image_without_agent_setup(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root)

    class FailingDocker(FakeDocker):
        def verify_agent_setup(self, reference: str) -> None:
            super().verify_agent_setup(reference)
            raise RuntimeError("agent setup probe failed")

    docker = FailingDocker()
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=docker,
    )

    with pytest.raises(RuntimeError, match="agent setup probe failed"):
        publisher.publish(
            instance,
            local_image="local/project:release",
            repository="ghcr.io/example/perfrace-project-workload",
            tag="release",
        )

    assert docker.verified_agent_setup == [IMAGE_REFERENCE]
    assert read_report(instance / "report.md").status == "IN_PROGRESS"
    assert not (root / ".releases" / "project--workload.json").exists()


def test_accepted_publication_failure_preserves_accept(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(fail_attach=True),
        docker=FakeDocker(),
    )

    with pytest.raises(RuntimeError, match="attach failed"):
        publisher.publish(instance)

    assert read_report(instance / "report.md").status == "ACCEPT"


def test_accepted_publication_reuses_existing_image_without_mutating_report(
    tmp_path: Path,
) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    original_report = (instance / "report.md").read_text()
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=FakeDocker(),
    )

    record = publisher.publish(instance)

    assert record.image == IMAGE_REFERENCE
    assert (instance / "report.md").read_text() == original_report


def test_accepted_publication_skips_matching_release(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    oras = FakeOras()
    publisher = InstancePublisher(
        instance_root=root,
        oras=oras,
        docker=FakeDocker(),
    )

    first = publisher.publish(instance)
    second = publisher.publish(instance)

    assert second == first
    assert oras.attach_count == 1


def test_accepted_publication_rejects_executable_mode_changes(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    oras = FakeOras()
    publisher = InstancePublisher(
        instance_root=root,
        oras=oras,
        docker=FakeDocker(),
    )
    publisher.publish(instance)
    script = instance / "tests" / "test.sh"
    script.chmod(0o644)

    with pytest.raises(InstanceValidationError, match="must be executable"):
        publisher.publish(instance)

    assert read_report(instance / "report.md").status == "ACCEPT"


def test_accepted_publication_rejects_content_drift(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    oras = FakeOras()
    publisher = InstancePublisher(
        instance_root=root,
        oras=oras,
        docker=FakeDocker(),
    )
    publisher.publish(instance)
    (instance / "environment" / "workspace" / "project" / "source.txt").write_text("changed\n")

    with pytest.raises(InstanceValidationError, match="differs from its published release"):
        publisher.publish(instance)

    assert read_report(instance / "report.md").status == "ACCEPT"
    assert oras.attach_count == 1


def test_release_record_rejects_symlinked_release_directory(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".releases").symlink_to(outside, target_is_directory=True)
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=FakeDocker(),
    )

    with pytest.raises(OSError):
        publisher.publish(instance)

    assert not (outside / "project--workload.json").exists()


def test_publish_rejects_directory_claiming_another_instance_id(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root, status="ACCEPT")
    mismatched = root / "other--workload"
    instance.rename(mismatched)
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=FakeDocker(),
    )

    with pytest.raises(InstanceValidationError, match="direct formal directory"):
        publisher.publish(mismatched)

    assert read_report(mismatched / "report.md").status == "ACCEPT"


def test_publish_preserves_external_changes_on_remote_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    instance = _instance(root)

    class MutatingOras(FakeOras):
        def attach_task(self, **_kwargs) -> AttachedArtifact:
            report = instance / "report.md"
            report.write_text(report.read_text().replace("# Project workload", "# External edit"))
            raise RuntimeError("attach failed")

    publisher = InstancePublisher(
        instance_root=root,
        oras=MutatingOras(),
        docker=FakeDocker(),
    )

    with pytest.raises(RuntimeError, match="attach failed"):
        publisher.publish(
            instance,
            local_image="local/project:release",
            repository="ghcr.io/example/perfrace-project-workload",
            tag="release",
        )

    assert "# External edit" in (instance / "report.md").read_text()
    assert read_report(instance / "report.md").status == "IN_PROGRESS"


def test_publish_rejects_outside_path_without_mutating_report(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    instance = _instance(outside_root, status="ACCEPT")
    original_report = (instance / "report.md").read_text()
    publisher = InstancePublisher(
        instance_root=root,
        oras=FakeOras(),
        docker=FakeDocker(),
    )

    with pytest.raises(InstanceValidationError, match="inside the configured instance root"):
        publisher.publish(instance)

    assert (instance / "report.md").read_text() == original_report
