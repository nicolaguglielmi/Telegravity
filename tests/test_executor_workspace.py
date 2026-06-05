"""Tests for workspace-rooted executor helpers (cwd, jailed read/write)."""

import asyncio

import pytest

from telegravity.ui import executor


def test_run_shell_respects_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("CWD_OK")
    code, out, err = asyncio.run(
        executor.run_shell("cat marker.txt", timeout=5, cwd=str(tmp_path))
    )
    assert code == 0
    assert out == "CWD_OK"


def test_safe_read_file_with_root(tmp_path):
    (tmp_path / "a.txt").write_text("body")
    lang, content = executor.safe_read_file("a.txt", root=str(tmp_path))
    assert content == "body"


def test_safe_read_file_root_jail(tmp_path):
    with pytest.raises(executor.FileViewError):
        executor.safe_read_file("../x", root=str(tmp_path))


def test_safe_write_file_creates_and_returns_path(tmp_path):
    p = executor.safe_write_file("sub/new.txt", "hello", root=str(tmp_path))
    assert (tmp_path / "sub" / "new.txt").read_text() == "hello"
    assert p == str((tmp_path / "sub" / "new.txt").resolve())


def test_safe_write_file_jail_escape(tmp_path):
    with pytest.raises(executor.FileViewError):
        executor.safe_write_file("../evil.txt", "x", root=str(tmp_path))


def test_safe_write_file_rejects_directory(tmp_path):
    (tmp_path / "adir").mkdir()
    with pytest.raises(executor.FileViewError):
        executor.safe_write_file("adir", "x", root=str(tmp_path))
