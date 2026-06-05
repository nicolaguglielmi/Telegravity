"""Process-wide state manager.

Owns the in-memory message buffer, the conversations database, and the
persistent ``state.json``. All mutating operations go through an
``asyncio.Lock`` so the Telegram polling worker and the MCP tool handlers
cannot race each other.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import paths as _paths
from .config import Config
from .paths import ensure_data_dir
from .workspaces import resolve_workspaces

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class AgentHeartbeat:
    """Snapshot of what the agent last reported via ``register_agent_activity``."""

    status: str = "offline"  # offline | idle | thinking | executing | waiting | done | error
    detail: str = ""
    updated_at: float = field(default_factory=time.time)

    def freshness(self) -> str:
        delta = time.time() - self.updated_at
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{int(delta / 60)}m ago"
        if delta < 86400:
            return f"{int(delta / 3600)}h ago"
        return f"{int(delta / 86400)}d ago"


class StateManager:
    """Owns workspace + conversation + buffer state for the single user."""

    USER_STATE_IDLE = "IDLE"

    def __init__(self, config: Config):
        self.config = config
        self.workspaces: List[str] = []
        self.workspace_paths: Dict[str, str] = {}
        self.current_workspace: Optional[str] = None
        self.current_workspace_path: Optional[str] = None
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.message_buffer: List[str] = []
        self.chat_mode: bool = False
        self.last_ai_index: int = 0
        self.active_conversation_index: Optional[int] = None
        self.last_menu_message_id: Optional[int] = None
        self.user_state: str = self.USER_STATE_IDLE
        self.has_seen_onboarding: bool = False

        self.agent = AgentHeartbeat()

        self.new_message_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._sync_lock = __import__("threading").Lock()

        ensure_data_dir()
        self._load_workspaces()
        self._load_conversations()
        self._load_logs()
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @staticmethod
    def _atomic_write(path, text: str) -> None:
        """Write via temp file + os.replace so a crash mid-write can't truncate."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)

    def _load_state(self) -> None:
        if not _paths.STATE_FILE.exists():
            return
        try:
            data = json.loads(_paths.STATE_FILE.read_text())
        except Exception as exc:
            logger.error("Failed to load state.json: %s", exc)
            return
        self.current_workspace = data.get("current_workspace")
        self.current_workspace_path = data.get("current_workspace_path")
        self.chat_mode = data.get("chat_mode", False)
        self.last_ai_index = data.get("last_index", 0)
        self.active_conversation_index = data.get("active_conversation")
        self.user_state = data.get("user_state", self.USER_STATE_IDLE)
        self.has_seen_onboarding = data.get("has_seen_onboarding", False)
        self.last_menu_message_id = data.get("last_menu_message_id")

    def save_state(self) -> None:
        ensure_data_dir()
        payload = {
            "current_workspace": self.current_workspace,
            "current_workspace_path": self.current_workspace_path,
            "chat_mode": self.chat_mode,
            "last_index": self.last_ai_index,
            "active_conversation": self.active_conversation_index,
            "user_state": self.user_state,
            "has_seen_onboarding": self.has_seen_onboarding,
            "last_menu_message_id": self.last_menu_message_id,
        }
        with self._sync_lock:
            try:
                self._atomic_write(_paths.STATE_FILE, json.dumps(payload, indent=2))
            except Exception as exc:
                logger.error("Failed to save state.json: %s", exc)

    def _load_conversations(self) -> None:
        if _paths.CONVERSATIONS_FILE.exists():
            try:
                self.conversations = json.loads(_paths.CONVERSATIONS_FILE.read_text())
                return
            except Exception as exc:
                logger.error("Failed to load conversations.json: %s", exc)
        if _paths.LEGACY_TASKS_FILE.exists():
            try:
                self.conversations = json.loads(_paths.LEGACY_TASKS_FILE.read_text())
                logger.info("Migrated legacy tasks.json into conversations store.")
                self.save_conversations()
            except Exception as exc:
                logger.error("Legacy tasks migration failed: %s", exc)

    def save_conversations(self) -> None:
        ensure_data_dir()
        with self._sync_lock:
            try:
                self._atomic_write(
                    _paths.CONVERSATIONS_FILE, json.dumps(self.conversations, indent=2)
                )
            except Exception as exc:
                logger.error("Failed to save conversations: %s", exc)

    def _load_workspaces(self) -> None:
        self.workspaces, self.workspace_paths = resolve_workspaces(
            self.config.initial_workspaces,
            _paths.WORKSPACES_FILE,
            self.config.projects_dir,
            autoimport=self.config.autoimport_projects,
            base_dir=self.config.workspace_base or None,
        )

    def workspace_root(self) -> Optional[str]:
        """Absolute path of the active workspace, or None if it has no directory."""
        if self.current_workspace and self.current_workspace in self.workspace_paths:
            return self.workspace_paths[self.current_workspace]
        return self.current_workspace_path

    def select_workspace(self, name: str) -> bool:
        """Set the active workspace if known. Returns False for unknown labels."""
        if name not in self.workspaces:
            return False
        self.current_workspace = name
        self.current_workspace_path = self.workspace_paths.get(name)
        self.active_conversation_index = None
        self.save_state()
        return True

    def reload_workspaces(self) -> int:
        self._load_workspaces()
        if self.current_workspace and self.current_workspace in self.workspace_paths:
            self.current_workspace_path = self.workspace_paths[self.current_workspace]
        return len(self.workspaces)

    def _load_logs(self) -> None:
        if not _paths.ACTIVITY_LOG.exists():
            return
        try:
            lines = _paths.ACTIVITY_LOG.read_text().splitlines()
            self.message_buffer = [ln.strip() for ln in lines[-self.config.BUFFER_LIMIT:]]
        except Exception as exc:
            logger.error("Failed to load activity log: %s", exc)

    def append_activity_log(self, entry: str) -> None:
        ensure_data_dir()
        with self._sync_lock:
            try:
                with _paths.ACTIVITY_LOG.open("a") as f:
                    f.write(entry + "\n")
            except Exception as exc:
                logger.error("Activity log write failed: %s", exc)

    def append_conversation_log(self, entry: str) -> None:
        ensure_data_dir()
        with self._sync_lock:
            try:
                with _paths.CONVERSATION_LOG.open("a") as f:
                    f.write(entry + "\n")
            except Exception as exc:
                logger.error("Conversation log write failed: %s", exc)

    # ------------------------------------------------------------------
    # Buffer / async-safe operations
    # ------------------------------------------------------------------
    async def add_message(self, msg: str, *, persist_logs: bool = True) -> None:
        async with self._lock:
            self.message_buffer.append(msg)
            if len(self.message_buffer) > self.config.BUFFER_LIMIT:
                dropped = len(self.message_buffer) - self.config.BUFFER_LIMIT
                self.message_buffer = self.message_buffer[dropped:]
                self.last_ai_index = max(0, self.last_ai_index - dropped)
            self.new_message_event.set()
        if persist_logs:
            self.append_activity_log(msg)
            self.append_conversation_log(msg)

    async def drain_messages(self) -> List[str]:
        async with self._lock:
            if self.last_ai_index >= len(self.message_buffer):
                return []
            messages = self.message_buffer[self.last_ai_index:]
            self.last_ai_index = len(self.message_buffer)
        self.save_state()
        return messages

    async def wait_for_messages(self, timeout: float) -> List[str]:
        async with self._lock:
            if self.last_ai_index < len(self.message_buffer):
                pending = self.message_buffer[self.last_ai_index:]
                self.last_ai_index = len(self.message_buffer)
                save_now = True
            else:
                pending = None
                save_now = False
                self.new_message_event.clear()
        if save_now:
            self.save_state()
            return pending or []
        try:
            await asyncio.wait_for(self.new_message_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return []
        return await self.drain_messages()

    def recent_messages(self, n: int = 10) -> List[str]:
        return list(self.message_buffer[-n:])

    # ------------------------------------------------------------------
    # User-state machine (for multi-step UI dialogs)
    # ------------------------------------------------------------------
    def set_user_state(self, new_state: str) -> None:
        self.user_state = new_state
        self.save_state()

    def reset_user_state(self) -> None:
        self.user_state = self.USER_STATE_IDLE
        self.save_state()

    # ------------------------------------------------------------------
    # Agent heartbeat
    # ------------------------------------------------------------------
    def update_agent(self, status: str, detail: str = "") -> None:
        self.agent = AgentHeartbeat(status=status, detail=detail, updated_at=time.time())

    # ------------------------------------------------------------------
    # Conversation helpers
    # ------------------------------------------------------------------
    def conversations_for(self, workspace: Optional[str]) -> List[Dict[str, Any]]:
        if not workspace:
            return []
        return self.conversations.get(workspace, [])

    def add_conversation(self, workspace: str, desc: str) -> Dict[str, Any]:
        conv = {
            "desc": desc,
            "status": "active",
            "interactions": [],
            "created_at": _now(),
        }
        self.conversations.setdefault(workspace, []).append(conv)
        self.save_conversations()
        return conv
