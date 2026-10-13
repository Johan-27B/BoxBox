from pathlib import Path

from perfrace.evolution.state import read_evolution_state, write_model_atomic
from perfrace.evolution.types import EvolutionState


def test_write_model_atomic_round_trips_evolution_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = EvolutionState(
        experiment_name="demo",
        config_sha256="a" * 64,
        split_manifest_path=tmp_path / "splits" / "manifest.json",
    )

    write_model_atomic(path, state)

    assert read_evolution_state(path) == state
    assert list(tmp_path.glob(".state.json.*")) == []
