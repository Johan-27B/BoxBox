"""Atomic persistence for resumable harness-evolution state."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from perfrace.evolution.types import EvolutionState


ModelT = TypeVar("ModelT", bound=BaseModel)


def write_model_atomic(path: Path, model: BaseModel) -> None:
    """Atomically persist one Pydantic model as formatted JSON."""
    write_text_atomic(path, f"{model.model_dump_json(indent=2)}\n")


def write_text_atomic(path: Path, text: str) -> None:
    """Atomically persist one UTF-8 text artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def read_model(path: Path, model_type: type[ModelT]) -> ModelT:
    """Read and validate one persisted Pydantic model."""
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Failed to read persisted model {path}: {exc}") from exc
    return model_type.model_validate_json(payload)


def read_evolution_state(path: Path) -> EvolutionState:
    """Read one durable experiment state file."""
    return read_model(path, EvolutionState)
