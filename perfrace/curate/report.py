"""Read and update lightweight Pair Verification Markdown reports."""

from __future__ import annotations

import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

REPORT_FIELDS = (
    "schema",
    "instance",
    "status",
    "realism",
    "reliability",
    "integrity",
    "updated",
)
REPORT_STATUSES = frozenset({"IN_PROGRESS", "ACCEPT", "REVISE", "REJECT"})
REVIEW_STATUSES = frozenset({"PENDING", "APPROVED", "REVISE", "REJECTED"})
INSTANCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*--[a-z0-9][a-z0-9-]*$")
METADATA_FIELDS = frozenset(
    {
        "Source",
        "Revision",
        "Image",
        "Started",
        "Completed",
        "Agent cost",
        "Human interactions",
    }
)


@dataclass(frozen=True)
class ReportState:
    """Machine-readable state stored in ``report.md`` front matter."""

    schema: int
    instance: str
    status: str
    realism: str
    reliability: str
    integrity: str
    updated: str


def read_text(path: Path) -> str:
    """Read one regular UTF-8 file without following its final symlink."""
    directory_fd = os.open(
        path.parent,
        os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        file_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError(f"{path} is not a regular file")
            with os.fdopen(file_fd, encoding="utf-8") as handle:
                file_fd = -1
                return handle.read()
        finally:
            if file_fd >= 0:
                os.close(file_fd)
    finally:
        os.close(directory_fd)


def write_text(path: Path, content: str) -> None:
    """Atomically replace a regular file without following predictable symlinks."""
    directory_fd = os.open(
        path.parent,
        os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    temporary_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        mode = 0o644
        try:
            current_fd = os.open(
                path.name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            pass
        else:
            try:
                current_stat = os.fstat(current_fd)
                if not stat.S_ISREG(current_stat.st_mode):
                    raise ValueError(f"{path} is not a regular file")
                mode = stat.S_IMODE(current_stat.st_mode)
            finally:
                os.close(current_fd)
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=directory_fd,
        )
        try:
            with os.fdopen(temporary_fd, "w", encoding="utf-8") as handle:
                temporary_fd = -1
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if temporary_fd >= 0:
                os.close(temporary_fd)
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("report.md must start with front matter")
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise ValueError("report.md front matter is not closed")
    values: dict[str, str] = {}
    for line in lines[1:closing_index]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"invalid report.md front matter line: {line.rstrip()}")
        normalized_key = key.strip()
        if normalized_key in values:
            raise ValueError(f"duplicate report.md field: {normalized_key}")
        values[normalized_key] = value.strip()
    return values, "".join(lines[closing_index + 1 :])


def _state_from_values(values: dict[str, str]) -> ReportState:
    """Validate front matter values and return their typed representation."""
    missing = [field for field in REPORT_FIELDS if field not in values]
    extra = sorted(set(values) - set(REPORT_FIELDS))
    if missing:
        raise ValueError(f"report.md is missing fields: {missing}")
    if extra:
        raise ValueError(f"report.md has unsupported fields: {extra}")
    try:
        schema = int(values["schema"])
    except ValueError as exc:
        raise ValueError("report.md schema must be an integer") from exc
    if schema != 1:
        raise ValueError(f"unsupported report.md schema: {schema}")
    if values["status"] not in REPORT_STATUSES:
        raise ValueError(f"invalid report.md status: {values['status']}")
    for field in ("realism", "reliability", "integrity"):
        if values[field] not in REVIEW_STATUSES:
            raise ValueError(f"invalid report.md {field}: {values[field]}")
    if values["reliability"] != "PENDING" and values["realism"] != "APPROVED":
        raise ValueError("report.md Reliability review requires approved Realism")
    if values["integrity"] != "PENDING" and (
        values["realism"] != "APPROVED" or values["reliability"] != "APPROVED"
    ):
        raise ValueError("report.md Integrity review requires approved Realism and Reliability")
    if values["status"] == "ACCEPT" and any(
        values[field] != "APPROVED" for field in ("realism", "reliability", "integrity")
    ):
        raise ValueError("report.md ACCEPT requires all reviews to be approved")
    if values["status"] == "ACCEPT" and (
        not INSTANCE_ID_PATTERN.fullmatch(values["instance"])
        or values["instance"].endswith("--pending")
    ):
        raise ValueError("report.md ACCEPT requires a final instance id")
    return ReportState(
        schema=schema,
        instance=values["instance"],
        status=values["status"],
        realism=values["realism"],
        reliability=values["reliability"],
        integrity=values["integrity"],
        updated=values["updated"],
    )


def read_report(path: Path) -> ReportState | None:
    """Read report front matter, or return ``None`` when no report exists."""
    try:
        text = read_text(path)
    except FileNotFoundError:
        return None
    values, _ = _split_front_matter(text)
    return _state_from_values(values)


def update_report(path: Path, state: ReportState) -> None:
    """Atomically replace only the front matter of an existing report."""
    values = {
        "schema": str(state.schema),
        "instance": state.instance,
        "status": state.status,
        "realism": state.realism,
        "integrity": state.integrity,
        "reliability": state.reliability,
        "updated": state.updated,
    }
    _state_from_values(values)
    for field, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"report.md {field} must fit on one line")
    _, body = _split_front_matter(read_text(path))
    front_matter = "---\n" + "".join(f"{field}: {values[field]}\n" for field in REPORT_FIELDS)
    write_text(path, f"{front_matter}---\n{body}")


def update_report_metadata(
    path: Path,
    updates: Mapping[str, object],
    *,
    updated: str,
) -> None:
    """Atomically update telemetry table rows and the front matter timestamp."""
    unsupported = sorted(set(updates) - METADATA_FIELDS)
    if unsupported:
        raise ValueError(f"unsupported report.md metadata fields: {unsupported}")
    normalized: dict[str, str] = {}
    for field, raw_value in updates.items():
        value = str(raw_value)
        if "\n" in value or "\r" in value:
            raise ValueError(f"report.md metadata {field} must fit on one line")
        normalized[field] = value.replace("|", r"\|")

    values, body = _split_front_matter(read_text(path))
    values["updated"] = updated
    _state_from_values(values)
    lines = body.splitlines(keepends=True)
    remaining = set(normalized)
    for index, line in enumerate(lines):
        for field in tuple(remaining):
            row_names = (field, "Human comments") if field == "Human interactions" else (field,)
            if any(line.startswith(f"| {name} |") for name in row_names):
                newline = "\n" if line.endswith("\n") else ""
                lines[index] = f"| {field} | {normalized[field]} |{newline}"
                remaining.remove(field)
                break
    if remaining:
        raise ValueError(f"report.md is missing metadata rows: {sorted(remaining)}")

    front_matter = "---\n" + "".join(f"{field}: {values[field]}\n" for field in REPORT_FIELDS)
    write_text(path, f"{front_matter}---\n{''.join(lines)}")
