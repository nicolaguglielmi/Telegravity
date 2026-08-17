"""Configuration loaded from environment variables.

Loaded once at process start. ``Config.load()`` raises ``ConfigError`` with a
human-readable message when required values are missing or malformed — the
caller (server entrypoint) prints it and exits, instead of starting in a
half-broken state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import find_dotenv, load_dotenv

from . import paths as _paths


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


@dataclass(frozen=True)
class Config:
    telegram_token: str
    authorized_chat_id: int
    initial_workspaces: List[str] = field(default_factory=list)
    enable_shell_exec: bool = False
    enable_file_view: bool = False
    enable_file_write: bool = False
    # Auto-import workspaces from Antigravity's project registry, give bare
    # labels a path under ``workspace_base``, and where that registry lives.
    autoimport_projects: bool = True
    projects_dir: str = ""
    workspace_base: str = ""

    BUFFER_LIMIT: int = 200
    SHELL_TIMEOUT_SEC: int = 30
    PENDING_CONFIRM_TTL_SEC: int = 60

    @classmethod
    def load(cls) -> "Config":
        # ``usecwd=True`` walks up from the working directory instead of from
        # the package's source location — important so the user's project-local
        # ``.env`` is found, and so the test suite can isolate via ``chdir``.
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path)
            _paths.refresh()
        # Layer the global config (~/.telegravity/.env) underneath: with
        # override left False it only fills keys that neither the real
        # environment nor the project .env provided. An unrelated project's
        # .env up the cwd chain therefore can't mask the global credentials —
        # MCP clients launch the server from arbitrary directories.
        if _paths.ENV_FILE.is_file():
            load_dotenv(_paths.ENV_FILE)
            _paths.refresh()

        token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
        if not token:
            raise ConfigError(
                "TELEGRAM_TOKEN is missing. Create a bot with @BotFather and set "
                "TELEGRAM_TOKEN in your .env file."
            )

        raw_chat_id = (
            os.environ.get("AUTHORIZED_CHAT_ID")
            or os.environ.get("CHAT_ID")  # legacy name
            or ""
        ).strip()
        if not raw_chat_id:
            raise ConfigError(
                "AUTHORIZED_CHAT_ID is missing. Message @userinfobot on Telegram "
                "to get yours and set AUTHORIZED_CHAT_ID in your .env file."
            )
        try:
            chat_id = int(raw_chat_id)
        except ValueError as exc:
            raise ConfigError(
                f"AUTHORIZED_CHAT_ID must be an integer, got: {raw_chat_id!r}"
            ) from exc

        workspaces_raw = os.environ.get("INITIAL_WORKSPACES", "")
        workspaces = [w.strip() for w in workspaces_raw.split(",") if w.strip()]

        default_projects_dir = str(Path.home() / ".gemini" / "config" / "projects")
        projects_dir = (os.environ.get("TELEGRAVITY_PROJECTS_DIR") or default_projects_dir).strip()
        workspace_base = (os.environ.get("TELEGRAVITY_WORKSPACE_BASE") or "").strip()

        return cls(
            telegram_token=token,
            authorized_chat_id=chat_id,
            initial_workspaces=workspaces,
            enable_shell_exec=_truthy(os.environ.get("ENABLE_SHELL_EXEC")),
            enable_file_view=_truthy(os.environ.get("ENABLE_FILE_VIEW")),
            enable_file_write=_truthy(os.environ.get("ENABLE_FILE_WRITE")),
            autoimport_projects=_truthy(os.environ.get("TELEGRAVITY_AUTOIMPORT"), default=True),
            projects_dir=projects_dir,
            workspace_base=workspace_base,
        )
