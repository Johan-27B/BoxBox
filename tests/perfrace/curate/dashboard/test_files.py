from __future__ import annotations

from pathlib import Path

import pytest

from perfrace.curate.dashboard import files
from perfrace.curate.dashboard.files import list_directory, read_file_range, render_markdown


def test_lazy_tree_and_bounded_text_preview(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "instruction.md").write_text("optimize me\n", encoding="utf-8")
    (tmp_path / "tests" / "test.sh").write_text("echo ok\n", encoding="utf-8")

    tree = list_directory(tmp_path)
    preview = read_file_range(tmp_path, "instruction.md", limit=5)

    assert [entry["name"] for entry in tree["entries"]] == ["tests", "instruction.md"]
    assert preview["content"] == "optim"
    assert preview["truncated"] is True
    assert preview["nextOffset"] == 5


def test_file_browser_blocks_traversal_and_external_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "outside-link").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes"):
        read_file_range(tmp_path, "../outside.txt")

    assert list_directory(tmp_path)["entries"] == []


def test_binary_preview_does_not_decode_bytes(tmp_path: Path) -> None:
    (tmp_path / "fixture.bin").write_bytes(b"a\0b")

    preview = read_file_range(tmp_path, "fixture.bin")

    assert preview["binary"] is True
    assert preview["content"] == ""


def test_markdown_preview_renders_tables_and_escapes_raw_html() -> None:
    rendered = render_markdown(
        "# Report\n\n| Field | Value |\n| --- | --- |\n| Status | Ready |\n\n"
        "<script>alert('unsafe')</script>\n"
    )

    assert "<table>" in rendered
    assert "<h1>Report</h1>" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_file_preview_rejects_symlink_replacement_during_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path.parent / "outside-race.txt"
    outside.write_text("secret", encoding="utf-8")
    target = tmp_path / "preview.txt"
    target.write_text("safe", encoding="utf-8")
    original_open_component = files._open_component
    replaced = False

    def replace_before_open(parent_fd: int, name: str, *, directory: bool) -> int:
        nonlocal replaced
        if name == "preview.txt" and not replaced:
            target.unlink()
            target.symlink_to(outside)
            replaced = True
        return original_open_component(parent_fd, name, directory=directory)

    monkeypatch.setattr(files, "_open_component", replace_before_open)

    with pytest.raises(ValueError, match="symlinks"):
        read_file_range(tmp_path, "preview.txt")
