"""ORAS adapter for PerfRace task artifacts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ORAS_VERSION = "1.3.3"
ARTIFACT_TYPE = "application/vnd.perfrace.task.v1"
LAYER_MEDIA_TYPE = "application/vnd.perfrace.task.layer.v1.tar+gzip"
_DIGEST_PATTERN = re.compile(r"^Digest:\s*(sha256:[0-9a-f]{64})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class AttachedArtifact:
    """One task artifact attached to an immutable image."""

    reference: str
    digest: str


class OrasClient:
    """Small checked subprocess wrapper around the pinned ORAS CLI."""

    def __init__(self, executable: str = "oras") -> None:
        self.executable = executable

    def _run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.executable, *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"ORAS command failed: {detail}")
        return result

    def preflight(self) -> None:
        """Require the exact reviewed ORAS CLI version."""
        if shutil.which(self.executable) is None:
            raise FileNotFoundError(
                f"required ORAS CLI {ORAS_VERSION} is not installed: {self.executable}"
            )
        output = self._run(["version"]).stdout
        match = re.search(r"\bVersion:\s*v?([0-9]+\.[0-9]+\.[0-9]+)\b", output)
        if match is None or match.group(1) != ORAS_VERSION:
            actual = match.group(1) if match else "unknown"
            raise RuntimeError(f"ORAS {ORAS_VERSION} is required, found {actual}")

    def attach_task(
        self,
        *,
        image_reference: str,
        archive_path: Path,
        instance_id: str,
        content_hash: str,
        created_at: str,
    ) -> AttachedArtifact:
        """Attach a task archive to its immutable image subject."""
        result = self._run(
            [
                "attach",
                "--artifact-type",
                ARTIFACT_TYPE,
                "--annotation",
                f"io.perfrace.instance={instance_id}",
                "--annotation",
                f"io.perfrace.content-digest=sha256:{content_hash}",
                "--annotation",
                f"org.opencontainers.image.created={created_at}",
                image_reference,
                f"{archive_path.name}:{LAYER_MEDIA_TYPE}",
            ],
            cwd=archive_path.parent,
        )
        matches = _DIGEST_PATTERN.findall(f"{result.stdout}\n{result.stderr}")
        if not matches:
            raise RuntimeError("ORAS attach did not report an artifact digest")
        digest = matches[-1]
        repository = image_reference.split("@", 1)[0]
        return AttachedArtifact(reference=f"{repository}@{digest}", digest=digest)

    def fetch_manifest(self, reference: str) -> dict[str, object]:
        """Fetch and parse one OCI manifest."""
        result = self._run(["manifest", "fetch", reference])
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError("ORAS returned a non-object manifest")
        return value

    def pull(self, reference: str, destination: Path) -> Path:
        """Pull one task artifact and return its archive path."""
        destination.mkdir(parents=True, exist_ok=True)
        self._run(["pull", "--output", str(destination), reference])
        archive = destination / "task.tar.gz"
        if not archive.is_file():
            raise FileNotFoundError("ORAS pull did not produce task.tar.gz")
        return archive
