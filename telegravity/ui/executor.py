"""Gated executors: shell command + jailed file read/write.

These helpers back BOTH the Telegram tap-to-confirm flow and the direct MCP
tools (``run_command`` / ``read_file`` / ``write_file``) — the MCP tools run
without a tap, gated only by ``ENABLE_SHELL_EXEC`` / ``ENABLE_FILE_VIEW`` /
``ENABLE_FILE_WRITE``. ``run_shell`` runs with ``cwd`` set to the active
workspace directory; ``safe_read_file`` / ``safe_write_file`` are path-jailed to
a ``root`` (the workspace directory), falling back to ``Path.cwd()`` when no
workspace is selected.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from ..config import Config
from ..formatting import code_block, inline_code, md2, truncate_block

logger = logging.getLogger(__name__)


async def run_shell(
    command: str, timeout: int, cwd: Optional[str] = None
) -> Tuple[int, str, str]:
    """Run ``command`` in a subprocess, return ``(returncode, stdout, stderr)``.

    ``cwd`` sets the working directory (the selected workspace's path). When
    None the subprocess inherits the server's CWD.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return (
        proc.returncode or 0,
        (stdout_b or b"").decode(errors="replace").strip(),
        (stderr_b or b"").decode(errors="replace").strip(),
    )


def format_shell_result(command: str, code: int, stdout: str, stderr: str) -> str:
    icon = "✅" if code == 0 else "❌"
    parts = [f"{icon} `{md2(command)}` *\\(exit {code}\\)*"]
    if stdout:
        parts.append("*stdout*")
        parts.append(code_block(truncate_block(stdout, 1500)))
    if stderr:
        parts.append("*stderr*")
        parts.append(code_block(truncate_block(stderr, 1500)))
    if not stdout and not stderr:
        parts.append("_no output_")
    return "\n".join(parts)


class FileViewError(Exception):
    pass


def _jail(path_str: str, root: Optional[str]) -> Path:
    """Resolve ``path_str`` under ``root`` (defaults to CWD), refusing escapes."""
    base = Path(root).resolve() if root else Path.cwd().resolve()
    candidate = (base / path_str).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise FileViewError("Path escapes the workspace tree.") from exc
    return candidate


def safe_read_file(path_str: str, root: Optional[str] = None) -> Tuple[str, str]:
    """Read a file, jailed to ``root`` (defaults to CWD). Returns ``(lang, content)``."""
    candidate = _jail(path_str, root)
    if not candidate.exists():
        raise FileViewError(f"File not found: {path_str}")
    if not candidate.is_file():
        raise FileViewError(f"Not a regular file: {path_str}")
    if candidate.stat().st_size > 256 * 1024:
        raise FileViewError("File too large (>256KB) to render in chat.")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    lang = candidate.suffix.lstrip(".") or ""
    return lang, text


def safe_write_file(path_str: str, content: str, root: Optional[str] = None) -> str:
    """Write ``content`` to a file jailed to ``root`` (defaults to CWD).

    Creates parent directories as needed. Returns the absolute path written.
    """
    candidate = _jail(path_str, root)
    if candidate.is_dir():
        raise FileViewError(f"Is a directory: {path_str}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(content, encoding="utf-8")
    return str(candidate)


def format_file_view(rel_path: str, language: str, content: str) -> str:
    if not content.strip():
        return f"📄 `{md2(rel_path)}` is empty\\."
    truncated = truncate_block(content, 3500)
    return f"📄 *{md2(rel_path)}*\n{code_block(truncated, language)}"


def is_enabled(config: Config, kind: str) -> bool:
    if kind == "shell":
        return config.enable_shell_exec
    if kind == "file":
        return config.enable_file_view
    return False


def feature_disabled_message(kind: str) -> str:
    env_var = {"shell": "ENABLE_SHELL_EXEC", "file": "ENABLE_FILE_VIEW"}[kind]
    return (
        f"🚫 This feature is disabled\\.\n\n"
        f"Set {inline_code(env_var + '=1')} in your `.env` to enable it\\. "
        "You will still need to confirm every action with a tap\\."
    )
