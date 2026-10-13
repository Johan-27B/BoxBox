"""Publish a complete PerfRace instance release."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
import tomllib
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from perfrace.curate.lint import lint_instance_format, lint_task_toml
from perfrace.curate.report import (
    INSTANCE_ID_PATTERN,
    ReportState,
    read_report,
    read_text,
    update_report,
    update_report_metadata,
    write_text,
)
from perfrace.release.archive import (
    TaskArchive,
    create_task_archive,
    extract_task_archive,
    verify_task_archive,
)
from perfrace.release.oci import ARTIFACT_TYPE, OrasClient

_IMMUTABLE_IMAGE = re.compile(
    r"^(?P<repository>ghcr\.io/[a-z0-9_.-]+/[a-z0-9_./-]+)"
    r"@(?P<digest>sha256:[0-9a-f]{64})$"
)
_DOCKER_IMAGE_LINE = re.compile(r'(?m)^(docker_image\s*=\s*")[^"]+(")\s*$')
_PUSH_DIGEST = re.compile(r"\bdigest:\s*(sha256:[0-9a-f]{64})\b")
_AGENT_SETUP_PROBE = r"""
set -eu
bash --version >/dev/null
git --version >/dev/null
python3 --version >/dev/null
python3 -c 'import ssl; assert ssl.create_default_context().get_ca_certs()'
tmux -V >/dev/null
session="perfrace-release-probe-$$"
tmux new-session -d -e PERFRACE_RELEASE_PROBE=ok -s "$session" sleep 30
test "$(tmux show-environment -t "$session" PERFRACE_RELEASE_PROBE)" \
    = "PERFRACE_RELEASE_PROBE=ok"
tmux kill-session -t "$session"
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ImageRelease:
    reference: str
    repository: str
    manifest_digest: str
    local_image_id: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class ReleaseRecord:
    schema_version: int
    instance: str
    image: str
    task_artifact: str
    task_content_hash: str
    archive_digest: str
    packaged_files: int
    published_at: str
    local_image_id: str | None = None
    image_size_bytes: int | None = None


class InstanceValidationError(ValueError):
    """A deterministic instance defect that prevents publication."""


class DockerPublisher:
    """Publish and verify one single-platform image."""

    @staticmethod
    def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(arguments, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Docker command failed: {detail}")
        return result

    def inspect_local(self, local_image: str) -> tuple[str, int]:
        output = self._run(
            [
                "docker",
                "image",
                "inspect",
                local_image,
                "--format",
                "{{.Id}}\t{{.Size}}",
            ]
        ).stdout.strip()
        try:
            image_id, raw_size = output.split("\t", 1)
            return image_id, int(raw_size)
        except ValueError as exc:
            raise RuntimeError("could not parse local Docker image metadata") from exc

    def publish(self, local_image_id: str, repository: str, tag: str) -> ImageRelease:
        inspected_id, size_bytes = self.inspect_local(local_image_id)
        if inspected_id != local_image_id:
            raise RuntimeError("local image identity changed before publication")
        tagged = f"{repository}:{tag}"
        self._run(["docker", "tag", local_image_id, tagged])
        pushed = self._run(["docker", "push", tagged])
        matches = _PUSH_DIGEST.findall(f"{pushed.stdout}\n{pushed.stderr}")
        if not matches:
            raise RuntimeError("docker push did not report a manifest digest")
        manifest_digest = matches[-1]
        reference = f"{repository}@{manifest_digest}"
        manifest = json.loads(
            self._run(["docker", "buildx", "imagetools", "inspect", reference, "--raw"]).stdout
        )
        config = manifest.get("config")
        remote_image_id = config.get("digest") if isinstance(config, dict) else None
        if remote_image_id != local_image_id:
            raise RuntimeError(
                f"published image config {remote_image_id} does not match {local_image_id}"
            )
        return ImageRelease(
            reference=reference,
            repository=repository,
            manifest_digest=manifest_digest,
            local_image_id=local_image_id,
            size_bytes=size_bytes,
        )

    def verify_existing(self, reference: str) -> ImageRelease:
        match = _IMMUTABLE_IMAGE.fullmatch(reference)
        if match is None:
            raise InstanceValidationError("task.toml must pin an immutable ghcr.io image digest")
        self._run(["docker", "buildx", "imagetools", "inspect", reference, "--raw"])
        return ImageRelease(
            reference=reference,
            repository=match.group("repository"),
            manifest_digest=match.group("digest"),
            local_image_id=None,
            size_bytes=None,
        )

    def verify_agent_setup(self, reference: str) -> None:
        """Require the standard candidate-agent tools in the image's default user."""
        self._run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "/bin/sh",
                reference,
                "-c",
                _AGENT_SETUP_PROBE,
            ]
        )


def _read_report(instance_dir: Path) -> ReportState:
    try:
        report = read_report(instance_dir / "report.md")
    except (OSError, TypeError, ValueError) as exc:
        raise InstanceValidationError(str(exc)) from exc
    if report is None:
        raise InstanceValidationError("report.md is required")
    return report


def _task_metadata(instance_dir: Path) -> tuple[str, str]:
    try:
        data = tomllib.loads(read_text(instance_dir / "task.toml"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise InstanceValidationError(f"task.toml is unreadable: {exc}") from exc
    task = data.get("task")
    environment = data.get("environment")
    if not isinstance(task, dict) or not isinstance(task.get("name"), str):
        raise InstanceValidationError("task.toml is missing task.name")
    if not isinstance(environment, dict) or not isinstance(environment.get("docker_image"), str):
        raise InstanceValidationError("task.toml is missing environment.docker_image")
    return task["name"].split("/", 1)[-1], environment["docker_image"]


def _write_docker_image(task_path: Path, reference: str) -> None:
    updated, count = _DOCKER_IMAGE_LINE.subn(
        rf"\g<1>{reference}\g<2>",
        read_text(task_path),
    )
    if count != 1:
        raise InstanceValidationError(
            "task.toml must contain exactly one environment docker_image"
        )
    write_text(task_path, updated)


def _lint(instance_dir: Path) -> None:
    errors = [*lint_task_toml(instance_dir), *lint_instance_format(instance_dir)]
    if errors:
        raise InstanceValidationError("; ".join(errors))


def _create_archive(instance_dir: Path, destination: Path) -> TaskArchive:
    try:
        return create_task_archive(instance_dir, destination)
    except ValueError as exc:
        raise InstanceValidationError(str(exc)) from exc


def _validate_reviews(report: ReportState) -> None:
    if any(
        status != "APPROVED" for status in (report.realism, report.reliability, report.integrity)
    ):
        raise InstanceValidationError("instance publication requires all reviews to be APPROVED")


class InstancePublisher:
    """Publish an image and task archive as one release."""

    def __init__(
        self,
        *,
        instance_root: Path,
        oras: OrasClient,
        docker: DockerPublisher | None = None,
    ) -> None:
        self.instance_root = instance_root.resolve()
        self.oras = oras
        self.docker = docker or DockerPublisher()

    def _release_path(self, instance_id: str) -> Path:
        return self.instance_root / ".releases" / f"{instance_id}.json"

    @contextmanager
    def _temporary_root(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(
            prefix=".release-",
            dir=self.instance_root,
        ) as temporary:
            yield Path(temporary)

    @contextmanager
    def _release_lock(self, instance_id: str) -> Iterator[None]:
        if INSTANCE_ID_PATTERN.fullmatch(instance_id) is None:
            raise InstanceValidationError(f"invalid instance ID: {instance_id}")
        root_fd = os.open(
            self.instance_root,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        releases_fd = -1
        locks_fd = -1
        lock_fd = -1
        try:
            try:
                os.mkdir(".releases", mode=0o775, dir_fd=root_fd)
            except FileExistsError:
                pass
            else:
                os.fsync(root_fd)
            releases_fd = os.open(
                ".releases",
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
            try:
                os.mkdir(".locks", mode=0o775, dir_fd=releases_fd)
            except FileExistsError:
                pass
            else:
                os.fsync(releases_fd)
            locks_fd = os.open(
                ".locks",
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=releases_fd,
            )
            lock_fd = os.open(
                f"{instance_id}.lock",
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o666,
                dir_fd=locks_fd,
            )
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise InstanceValidationError("instance release lock is not a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd >= 0:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            if locks_fd >= 0:
                os.close(locks_fd)
            if releases_fd >= 0:
                os.close(releases_fd)
            os.close(root_fd)

    def _validate_location(
        self,
        instance_dir: Path,
        instance_id: str,
        *,
        accepted: bool,
    ) -> None:
        try:
            relative = instance_dir.relative_to(self.instance_root)
        except ValueError as exc:
            raise InstanceValidationError(
                "instance directory must be inside the configured instance root"
            ) from exc
        if accepted:
            if relative.parts != (instance_id,):
                raise InstanceValidationError(
                    "accepted publication requires a direct formal directory matching the ID"
                )
            return
        is_formal = relative.parts == (instance_id,)
        is_staging = len(relative.parts) >= 2 and relative.parts[0] == ".staging"
        if not is_formal and not is_staging:
            raise InstanceValidationError(
                "publication requires the matching formal directory or a staging workspace"
            )
        if is_staging and (self.instance_root / instance_id).exists():
            raise InstanceValidationError(
                f"formal instance path already exists: {self.instance_root / instance_id}"
            )

    def current_release(self, instance_dir: Path) -> ReleaseRecord | None:
        """Return a matching release, or reject drift from an existing record."""
        instance_dir = instance_dir.resolve()
        report = _read_report(instance_dir)
        instance_id, image_reference = _task_metadata(instance_dir)
        if report.instance != instance_id:
            raise InstanceValidationError("report.md instance does not match task.name")
        release_path = self._release_path(instance_id)
        if not release_path.is_file():
            return None
        _lint(instance_dir)
        record = ReleaseRecord(**json.loads(read_text(release_path)))
        with self._temporary_root() as temporary_root:
            archive = _create_archive(instance_dir, temporary_root / "task.tar.gz")
        if (
            record.instance != instance_id
            or record.image != image_reference
            or record.task_content_hash != f"sha256:{archive.content_hash}"
            or record.archive_digest != f"sha256:{archive.archive_digest}"
            or record.packaged_files != archive.file_count
        ):
            raise InstanceValidationError("accepted package differs from its published release")
        manifest = self.oras.fetch_manifest(record.task_artifact)
        subject = manifest.get("subject")
        subject_digest = subject.get("digest") if isinstance(subject, dict) else None
        if (
            manifest.get("artifactType") != ARTIFACT_TYPE
            or subject_digest != image_reference.rsplit("@", 1)[-1]
        ):
            raise InstanceValidationError("published task artifact identity is invalid")
        return record

    def _verify_artifact(
        self,
        *,
        image: ImageRelease,
        artifact_reference: str,
        archive: TaskArchive,
        temporary_root: Path,
        instance_id: str,
    ) -> None:
        manifest = self.oras.fetch_manifest(artifact_reference)
        if manifest.get("artifactType") != ARTIFACT_TYPE:
            raise InstanceValidationError("published task artifact has the wrong artifactType")
        subject = manifest.get("subject")
        subject_digest = subject.get("digest") if isinstance(subject, dict) else None
        if subject_digest != image.manifest_digest:
            raise InstanceValidationError(
                "published task artifact does not reference the image digest"
            )
        pulled = self.oras.pull(artifact_reference, temporary_root / "pull")
        extracted = temporary_root / "extracted"
        try:
            count = verify_task_archive(
                pulled,
                extracted,
                expected_content_hash=archive.content_hash,
                expected_archive_digest=archive.archive_digest,
            )
        except ValueError as exc:
            raise InstanceValidationError(str(exc)) from exc
        if count != archive.file_count:
            raise InstanceValidationError("pulled task package file count does not match")
        _lint(extracted)
        pulled_id, pulled_image = _task_metadata(extracted)
        pulled_report = _read_report(extracted)
        if pulled_id != instance_id or pulled_report.instance != instance_id:
            raise InstanceValidationError(
                "pulled task package identity does not match the release"
            )
        if pulled_image != image.reference:
            raise InstanceValidationError(
                "pulled task package does not pin the artifact subject image"
            )

    def _write_release_record(self, record: ReleaseRecord) -> None:
        path = self._release_path(record.instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")

    def publish(
        self,
        instance_dir: Path,
        *,
        local_image: str | None = None,
        repository: str | None = None,
        tag: str = "release",
    ) -> ReleaseRecord:
        instance_dir = instance_dir.resolve()
        report = _read_report(instance_dir)
        instance_id, _ = _task_metadata(instance_dir)
        if report.instance != instance_id:
            raise InstanceValidationError("report.md instance does not match task.name")
        self._validate_location(
            instance_dir,
            instance_id,
            accepted=report.status == "ACCEPT",
        )
        with self._release_lock(instance_id):
            return self._publish_locked(
                instance_dir,
                local_image=local_image,
                repository=repository,
                tag=tag,
            )

    def _publish_locked(
        self,
        instance_dir: Path,
        *,
        local_image: str | None,
        repository: str | None,
        tag: str,
    ) -> ReleaseRecord:
        report = _read_report(instance_dir)
        _validate_reviews(report)
        instance_id, image_reference = _task_metadata(instance_dir)
        if report.instance != instance_id:
            raise InstanceValidationError("report.md instance does not match task.name")
        accepted = report.status == "ACCEPT"
        if not accepted and report.status not in {"IN_PROGRESS", "REVISE"}:
            raise InstanceValidationError(
                "publication requires report status IN_PROGRESS, REVISE, or ACCEPT"
            )
        self._validate_location(instance_dir, instance_id, accepted=accepted)
        self.oras.preflight()

        if accepted:
            current = self.current_release(instance_dir)
            if current is not None:
                return current
            if local_image is not None or repository is not None:
                raise InstanceValidationError(
                    "accepted instances use the immutable image already pinned in task.toml"
                )
            _lint(instance_dir)
            image = self.docker.verify_existing(image_reference)
            self.docker.verify_agent_setup(image.reference)
            return self._publish_accepted(instance_dir, instance_id, image)

        if local_image is None or repository is None:
            raise InstanceValidationError(
                "non-accepted publication requires a local image and GHCR repository"
            )
        if not repository.startswith("ghcr.io/"):
            raise InstanceValidationError("repository must be a ghcr.io repository")
        _lint(instance_dir)
        return self._publish_new(
            instance_dir,
            report,
            local_image=local_image,
            repository=repository.rstrip("/"),
            tag=tag,
        )

    def _publish_accepted(
        self,
        instance_dir: Path,
        instance_id: str,
        image: ImageRelease,
    ) -> ReleaseRecord:
        with self._temporary_root() as temporary_root:
            archive = _create_archive(instance_dir, temporary_root / "task.tar.gz")
            artifact = self.oras.attach_task(
                image_reference=image.reference,
                archive_path=archive.path,
                instance_id=instance_id,
                content_hash=archive.content_hash,
                created_at=utc_now(),
            )
            self._verify_artifact(
                image=image,
                artifact_reference=artifact.reference,
                archive=archive,
                temporary_root=temporary_root,
                instance_id=instance_id,
            )
            current = _create_archive(instance_dir, temporary_root / "current.tar.gz")
            if (
                current.content_hash != archive.content_hash
                or current.archive_digest != archive.archive_digest
            ):
                raise RuntimeError("accepted package changed during publication")
        record = ReleaseRecord(
            schema_version=1,
            instance=instance_id,
            image=image.reference,
            task_artifact=artifact.reference,
            task_content_hash=f"sha256:{archive.content_hash}",
            archive_digest=f"sha256:{archive.archive_digest}",
            packaged_files=archive.file_count,
            published_at=utc_now(),
        )
        self._write_release_record(record)
        return record

    def _publish_new(
        self,
        instance_dir: Path,
        report: ReportState,
        *,
        local_image: str,
        repository: str,
        tag: str,
    ) -> ReleaseRecord:
        report_path = instance_dir / "report.md"
        task_path = instance_dir / "task.toml"
        with self._temporary_root() as temporary_root:
            source = _create_archive(instance_dir, temporary_root / "source.tar.gz")
            snapshot = temporary_root / "snapshot"
            extract_task_archive(source.path, snapshot)
            local_image_id, _ = self.docker.inspect_local(local_image)
            image = self.docker.publish(local_image_id, repository, tag)
            if image.local_image_id != local_image_id:
                raise RuntimeError("published image does not match the inspected local image")
            self.docker.verify_agent_setup(image.reference)
            published_at = utc_now()
            _write_docker_image(snapshot / "task.toml", image.reference)
            update_report_metadata(
                snapshot / "report.md",
                {"Image": image.reference, "Completed": published_at},
                updated=published_at,
            )
            update_report(
                snapshot / "report.md",
                replace(report, status="ACCEPT", updated=published_at),
            )
            _lint(snapshot)
            archive = _create_archive(snapshot, temporary_root / "task.tar.gz")
            artifact = self.oras.attach_task(
                image_reference=image.reference,
                archive_path=archive.path,
                instance_id=report.instance,
                content_hash=archive.content_hash,
                created_at=published_at,
            )
            self._verify_artifact(
                image=image,
                artifact_reference=artifact.reference,
                archive=archive,
                temporary_root=temporary_root,
                instance_id=report.instance,
            )
            current = _create_archive(instance_dir, temporary_root / "current.tar.gz")
            if (
                current.content_hash != source.content_hash
                or current.archive_digest != source.archive_digest
            ):
                raise RuntimeError("instance changed during publication")
            self._validate_location(instance_dir, report.instance, accepted=False)
            record = ReleaseRecord(
                schema_version=1,
                instance=report.instance,
                image=image.reference,
                task_artifact=artifact.reference,
                task_content_hash=f"sha256:{archive.content_hash}",
                archive_digest=f"sha256:{archive.archive_digest}",
                packaged_files=archive.file_count,
                published_at=published_at,
                local_image_id=image.local_image_id,
                image_size_bytes=image.size_bytes,
            )
            final_task = read_text(snapshot / "task.toml")
            final_report = read_text(snapshot / "report.md")

        write_text(task_path, final_task)
        self._write_release_record(record)
        write_text(report_path, final_report)
        return record


def accepted_instances(instance_root: Path) -> list[Path]:
    """Return direct accepted instance directories."""
    accepted: list[Path] = []
    for path in sorted(instance_root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        try:
            report = read_report(path / "report.md")
        except (OSError, TypeError, ValueError):
            continue
        if report is not None and report.status == "ACCEPT":
            accepted.append(path)
    return accepted
