import subprocess
from pathlib import Path

import pytest

from perfrace.evolution.runtime_repository import RuntimeRepository


def test_runtime_repository_materializes_and_preserves_selected_commits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "helpers").mkdir(parents=True)
    (source / "__init__.py").write_text(
        "from .runtime import TerminusBoxBox\n",
        encoding="utf-8",
    )
    (source / "runtime.py").write_text(
        "class TerminusBoxBox: pass\n",
        encoding="utf-8",
    )
    (source / "helpers" / "contract.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "repository")
    initial = repository.validate_head()
    snapshot_dir = tmp_path / "snapshot"

    materialized = repository.materialize(initial.commit, snapshot_dir)

    assert materialized == initial
    assert (snapshot_dir / "runtime.py").read_text() == "class TerminusBoxBox: pass\n"
    repository.verify_materialized(initial.commit, snapshot_dir)
    (snapshot_dir / "runtime.py").write_text(
        "class TerminusBoxBox: changed\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differs from commit"):
        repository.verify_materialized(initial.commit, snapshot_dir)
    recovered_dir = tmp_path / "recovered"
    recovered_dir.mkdir()
    recovered_dir.joinpath("partial.txt").write_text("partial\n", encoding="utf-8")
    repository.materialize_atomic(initial.commit, recovered_dir)
    repository.verify_materialized(initial.commit, recovered_dir)
    assert tmp_path.joinpath("recovered-incomplete-01/partial.txt").is_file()

    runtime = repository.path / "runtime.py"
    runtime.write_text("class TerminusBoxBox:\n    VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository.path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository.path), "commit", "-q", "-m", "evolve runtime"],
        check=True,
    )
    evolved = repository.validate_head()
    assert evolved.commit != initial.commit

    contract = repository.path / "helpers" / "contract.py"
    contract.write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository.path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository.path), "commit", "-q", "-m", "update helper"],
        check=True,
    )
    assert repository.validate_head().commit != initial.commit
    repository.verify_materialized(initial.commit, recovered_dir)


def test_runtime_repository_rejects_symlink_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "helpers").mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "helpers" / "contract.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "repository")
    link = repository.path / "link.py"
    link.symlink_to("runtime.py")

    with pytest.raises(ValueError, match="non-regular entry"):
        repository.validate_worktree_entries()

    subprocess.run(["git", "-C", str(repository.path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository.path), "commit", "-q", "-m", "add symlink"],
        check=True,
    )
    with pytest.raises(ValueError, match="non-regular entry"):
        repository.validate_commit_entries(repository.head_commit())


def test_runtime_repository_allows_new_harness_modules(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source).mkdir(parents=True)
    (source / "__init__.py").write_text(
        "from .runtime import TerminusBoxBox\n",
        encoding="utf-8",
    )
    (source / "runtime.py").write_text(
        "class TerminusBoxBox: pass\n",
        encoding="utf-8",
    )

    repository = RuntimeRepository.initialize(source, tmp_path / "repository")
    initial = repository.validate_head()
    materialized = repository.materialize(initial.commit, tmp_path / "snapshot")

    assert materialized == initial
    assert not (tmp_path / "snapshot" / "helpers").exists()

    kernel = repository.path / "helpers"
    kernel.mkdir()
    kernel.joinpath("contract.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository.path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository.path), "commit", "-q", "-m", "add helper"],
        check=True,
    )
    assert repository.validate_head().commit != initial.commit
    repository.verify_materialized(initial.commit, tmp_path / "snapshot")


def test_formal_runtime_repository_can_commit_skill_changes(tmp_path: Path) -> None:
    from boxbox.terminus_boxbox import harness

    source = Path(harness.__file__).parent
    repository = RuntimeRepository.initialize(source, tmp_path / "repository")
    parent = repository.validate_head()
    skill = repository.path / "skills" / "self_review" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nSmoke revision.\n", encoding="utf-8")

    successor = repository.commit_worktree("test: evolve skill")

    assert successor.commit != parent.commit
    assert repository.changed_files(parent.commit, successor.commit) == (
        "skills/self_review/SKILL.md",
    )
