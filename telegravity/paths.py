"""Filesystem paths for runtime data.

Everything that the server writes at runtime (state, conversations, logs,
workspaces list) lives under a single ``DATA_DIR`` so the package itself stays
read-only. The directory is created lazily on first write.

``DATA_DIR`` defaults to ``~/.telegravity`` and can be overridden via the
``TELEGRAVITY_DATA_DIR`` environment variable. The default is a fixed per-user
location rather than ``cwd``-relative on purpose: MCP clients (Antigravity,
Claude Code, Cursor, …) launch the server with an arbitrary working directory —
often ``/`` — so a ``cwd``-relative default would crash on a read-only
filesystem or scatter state across unrelated directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_data_dir() -> Path:
    override = os.environ.get("TELEGRAVITY_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".telegravity"


DATA_DIR: Path = _resolve_data_dir()

STATE_FILE: Path = DATA_DIR / "state.json"
CONVERSATIONS_FILE: Path = DATA_DIR / "conversations.json"
WORKSPACES_FILE: Path = DATA_DIR / "workspaces.txt"
ACTIVITY_LOG: Path = DATA_DIR / "activity.log"
CONVERSATION_LOG: Path = DATA_DIR / "conversations.log"

# Legacy file in the project root — read once during migration if present.
LEGACY_TASKS_FILE: Path = Path.cwd() / "tasks.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
