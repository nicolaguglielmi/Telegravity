import pytest

from telegravity.ui import executor


def test_safe_read_file_blocks_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    with pytest.raises(executor.FileViewError, match="escapes"):
        executor.safe_read_file("../secret.txt")


def test_safe_read_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(executor.FileViewError, match="not found"):
        executor.safe_read_file("does-not-exist.txt")


def test_safe_read_file_rejects_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    with pytest.raises(executor.FileViewError, match="regular file"):
        executor.safe_read_file("sub")


def test_safe_read_file_returns_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "hello.py"
    target.write_text("print('hi')\n")
    lang, content = executor.safe_read_file("hello.py")
    assert lang == "py"
    assert "print" in content


def test_safe_read_rejects_huge_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "big.bin"
    target.write_bytes(b"x" * (300 * 1024))
    with pytest.raises(executor.FileViewError, match="too large"):
        executor.safe_read_file("big.bin")


@pytest.mark.asyncio
async def test_run_shell_captures_output():
    code, stdout, stderr = await executor.run_shell("echo hello", timeout=5)
    assert code == 0
    assert "hello" in stdout
    assert stderr == ""


def test_format_shell_result_marks_failure():
    out = executor.format_shell_result("ls /nope", 2, "", "no such")
    assert "❌" in out
    assert "exit 2" in out
    assert "no such" in out


def test_format_shell_result_no_output():
    out = executor.format_shell_result("true", 0, "", "")
    assert "no output" in out


def test_format_file_view_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    lang, content = executor.safe_read_file("empty.txt")
    out = executor.format_file_view("empty.txt", lang, content)
    assert "empty" in out


def test_format_file_view_with_content():
    out = executor.format_file_view("a.py", "py", "print('x')")
    # Path is MarkdownV2-escaped, so `.` becomes `\.`
    assert "a\\.py" in out
    assert "print" in out


def test_is_enabled_flags(monkeypatch):
    from telegravity.config import Config

    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("ENABLE_SHELL_EXEC", "1")
    monkeypatch.setenv("ENABLE_FILE_VIEW", "0")
    cfg = Config.load()
    assert executor.is_enabled(cfg, "shell") is True
    assert executor.is_enabled(cfg, "file") is False
    assert executor.is_enabled(cfg, "bogus") is False


def test_feature_disabled_message_for_each_kind():
    assert "ENABLE_SHELL_EXEC" in executor.feature_disabled_message("shell")
    assert "ENABLE_FILE_VIEW" in executor.feature_disabled_message("file")


@pytest.mark.asyncio
async def test_run_shell_timeout_kills_process():
    import asyncio

    with pytest.raises(asyncio.TimeoutError):
        await executor.run_shell("sleep 5", timeout=0.2)


@pytest.mark.asyncio
async def test_run_shell_captures_stderr():
    code, _, stderr = await executor.run_shell("ls /definitely-not-a-path-9999", timeout=5)
    assert code != 0
    assert stderr
