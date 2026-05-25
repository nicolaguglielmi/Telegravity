"""Gated executors: shell command + file viewer.

Both are opt-in (``ENABLE_SHELL_EXEC`` / ``ENABLE_FILE_VIEW``) and always run
through a tap-to-confirm flow. File reads are jailed to ``Path.cwd()``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Tuple

from ..config import Config
from ..formatting import code_block, inline_code, md2, truncate_block

logger = logging.getLogger(__name__)


async def run_shell(command: str, timeout: int) -> Tuple[int, str, str]:
    """Run ``command`` in a subprocess, return ``(returncode, stdout, stderr)``."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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


def safe_read_file(path_str: str) -> Tuple[str, str]:
    """Read a file, jailed to CWD. Returns ``(language_hint, content)``."""
    root = Path.cwd().resolve()
    candidate = (root / path_str).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FileViewError("Path escapes the project tree.") from exc
    if not candidate.exists():
        raise FileViewError(f"File not found: {path_str}")
    if not candidate.is_file():
        raise FileViewError(f"Not a regular file: {path_str}")
    if candidate.stat().st_size > 256 * 1024:
        raise FileViewError("File too large (>256KB) to render in chat.")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    lang = candidate.suffix.lstrip(".") or ""
    return lang, text


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
