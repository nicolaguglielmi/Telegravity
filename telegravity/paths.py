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

``TELEGRAVITY_DATA_DIR`` may also be set in a ``.env`` file: the module
resolves at import from the process environment, and ``Config.load()`` calls
``refresh()`` after each ``load_dotenv`` so a value arriving from a ``.env``
still takes effect. Access the constants via the module (``paths.DATA_DIR``),
not ``from``-imports, or a refresh won't reach your copy.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR: Path
STATE_FILE: Path
CONVERSATIONS_FILE: Path
WORKSPACES_FILE: Path
ACTIVITY_LOG: Path
CONVERSATION_LOG: Path
ENV_FILE: Path


def _resolve_data_dir() -> Path:
    override = os.environ.get("TELEGRAVITY_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".telegravity"


def refresh() -> None:
    """Re-resolve every path from the current environment."""
    global DATA_DIR, STATE_FILE, CONVERSATIONS_FILE, WORKSPACES_FILE
    global ACTIVITY_LOG, CONVERSATION_LOG, ENV_FILE
    DATA_DIR = _resolve_data_dir()
    STATE_FILE = DATA_DIR / "state.json"
    CONVERSATIONS_FILE = DATA_DIR / "conversations.json"
    WORKSPACES_FILE = DATA_DIR / "workspaces.txt"
    ACTIVITY_LOG = DATA_DIR / "activity.log"
    CONVERSATION_LOG = DATA_DIR / "conversations.log"
    ENV_FILE = DATA_DIR / ".env"


refresh()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
