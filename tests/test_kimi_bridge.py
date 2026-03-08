from __future__ import annotations

from pathlib import Path

import pytest

from agentflow.remote.kimi_bridge import _execute_tool, _safe_path


def test_safe_path_rejects_absolute_prefix_sibling_escape(tmp_path: Path):
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    escaped_dir = tmp_path / "work-evil"
    escaped_dir.mkdir()
    escaped_path = escaped_dir / "secret.txt"
    escaped_path.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="path escapes working dir"):
        _safe_path(working_dir, str(escaped_path))


def test_execute_tool_rejects_symlink_escape_on_read(tmp_path: Path):
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    escaped_dir = tmp_path / "escaped"
    escaped_dir.mkdir()
    (escaped_dir / "secret.txt").write_text("secret", encoding="utf-8")
    (working_dir / "link").symlink_to(escaped_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="path escapes working dir"):
        _execute_tool("read_file", {"path": "link/secret.txt"}, working_dir)


def test_execute_tool_rejects_glob_escape_pattern(tmp_path: Path):
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    escaped_dir = tmp_path / "work-evil"
    escaped_dir.mkdir()
    (escaped_dir / "secret.txt").write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="path escapes working dir"):
        _execute_tool("glob", {"pattern": "../work-evil/*"}, working_dir)


def test_execute_tool_glob_lists_files_inside_working_dir(tmp_path: Path):
    working_dir = tmp_path / "work"
    nested_dir = working_dir / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "file.txt").write_text("ok", encoding="utf-8")

    result = _execute_tool("glob", {"pattern": "nested/*.txt"}, working_dir)

    assert result == "nested/file.txt"
