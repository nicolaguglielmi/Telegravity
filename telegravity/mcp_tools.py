"""MCP tools exposed to the AI agent.

Built around a tiny ``Gateway`` object so the tools have access to the bot,
state, and config without relying on module globals — easier to test, and
makes the lifecycle obvious.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .config import Config
from .formatting import md2, now_str
from .state import StateManager
from .ui import executor

logger = logging.getLogger(__name__)


@dataclass
class Gateway:
    bot: Bot
    state: StateManager
    config: Config


_gateway: Optional[Gateway] = None


def bind(gateway: Gateway) -> None:
    """Bind the runtime gateway. Must be called once at startup."""
    global _gateway
    _gateway = gateway


def _gw() -> Gateway:
    if _gateway is None:
        raise RuntimeError("MCP tools used before gateway was bound")
    return _gateway


mcp = FastMCP("Telegravity")


def _quick_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu"),
                InlineKeyboardButton("💬 Conversations", callback_data="ui_conversations"),
            ]
        ]
    )


@mcp.tool()
async def send_message(text: str) -> str:
    """Send a free-form message from the agent to the user on Telegram."""
    gw = _gw()
    try:
        await gw.bot.send_message(
            chat_id=gw.config.authorized_chat_id,
            text=text,
            reply_markup=_quick_keyboard(),
        )
        await gw.state.add_message(f"[{now_str()}] 🧠 Agent: {text}")
        return "SUCCESS"
    except TelegramError as exc:
        logger.error("send_message failed: %s", exc)
        return f"ERROR: {exc}"


@mcp.tool()
async def check_telegram_updates() -> List[str]:
    """Return messages received from the user since the last poll. May be empty."""
    return await _gw().state.drain_messages()


@mcp.tool()
async def wait_for_remote_instruction(timeout_sec: int = 300) -> List[str]:
    """Long-poll. Blocks until a Telegram message arrives or ``timeout_sec`` elapses.

    Returns the queued messages (possibly empty on timeout). Use this to enter
    "Active Mode" — the agent stays awake and reacts the moment the user types.
    """
    return await _gw().state.wait_for_messages(timeout=max(5, min(timeout_sec, 600)))


@mcp.tool()
async def get_state() -> str:
    """Return a compact snapshot of workspace, active conversation, and recent buffer."""
    state = _gw().state
    conversations = state.conversations_for(state.current_workspace)
    conv_lines = (
        "\n".join(f"- [{c['status']}] {c['desc']}" for c in conversations)
        or "(none)"
    )
    active = "None"
    if (
        state.active_conversation_index is not None
        and 0 <= state.active_conversation_index < len(conversations)
    ):
        active = conversations[state.active_conversation_index]["desc"]
    history = "\n".join(state.recent_messages(10))
    root = state.workspace_root()
    ws_list = ", ".join(state.workspaces) or "(none)"
    return (
        f"WORKSPACE: {state.current_workspace or '(none)'}\n"
        f"WORKSPACE_DIR: {root or '(no directory — selection is label-only)'}\n"
        f"ACTIVE CONVERSATION: {active}\n"
        f"CHAT_MODE: {state.chat_mode}\n"
        f"AVAILABLE WORKSPACES: {ws_list}\n\n"
        f"CONVERSATIONS:\n{conv_lines}\n\n"
        f"RECENT BUFFER:\n{history}"
    )


@mcp.tool()
async def set_active_workspace(name: str) -> str:
    """Set the active workspace (the project the user wants you to work on).

    ``name`` must be one of the known workspaces (see AVAILABLE WORKSPACES in
    get_state). Returns the resolved directory so you know exactly where to
    operate — this is how a Telegram workspace selection 'takes effect'.
    """
    state = _gw().state
    if not state.select_workspace(name):
        known = ", ".join(state.workspaces) or "(none)"
        return f"ERROR: unknown workspace '{name}'. Known: {known}"
    root = state.workspace_root()
    if root:
        return f"OK: active workspace '{name}' -> {root}"
    return f"OK: active workspace '{name}' (no directory mapped; exec/file tools unavailable)"


@mcp.tool()
async def run_command(command: str, timeout_sec: int = 30) -> str:
    """Run a shell command IN THE SELECTED WORKSPACE's directory; return output.

    Gated by ENABLE_SHELL_EXEC. Runs with cwd = the active workspace's path, so
    it acts on the project chosen from Telegram even when the IDE has a
    different folder open. Requires a workspace with a mapped directory.
    """
    gw = _gw()
    if not gw.config.enable_shell_exec:
        return "ERROR: shell execution disabled (set ENABLE_SHELL_EXEC=1)"
    root = gw.state.workspace_root()
    if not root:
        return "ERROR: no workspace directory selected — call set_active_workspace first"
    timeout = max(1, min(int(timeout_sec), 300))
    try:
        code, out, err = await executor.run_shell(command, timeout=timeout, cwd=root)
    except asyncio.TimeoutError:
        return f"ERROR: command timed out after {timeout}s (cwd={root})"
    parts = [f"exit={code} cwd={root}"]
    if out:
        parts.append(f"stdout:\n{out}")
    if err:
        parts.append(f"stderr:\n{err}")
    return "\n\n".join(parts)


@mcp.tool()
async def read_file(rel_path: str) -> str:
    """Read a file from the SELECTED workspace (path jailed to its directory).

    Gated by ENABLE_FILE_VIEW. ``rel_path`` is relative to the active
    workspace's path.
    """
    gw = _gw()
    if not gw.config.enable_file_view:
        return "ERROR: file view disabled (set ENABLE_FILE_VIEW=1)"
    root = gw.state.workspace_root()
    if not root:
        return "ERROR: no workspace directory selected — call set_active_workspace first"
    try:
        _lang, content = executor.safe_read_file(rel_path, root=root)
    except executor.FileViewError as exc:
        return f"ERROR: {exc}"
    return content


@mcp.tool()
async def write_file(rel_path: str, content: str) -> str:
    """Write a file into the SELECTED workspace (path jailed to its directory).

    Gated by ENABLE_FILE_WRITE. ``rel_path`` is relative to the active
    workspace's path; parent directories are created as needed.
    """
    gw = _gw()
    if not gw.config.enable_file_write:
        return "ERROR: file write disabled (set ENABLE_FILE_WRITE=1)"
    root = gw.state.workspace_root()
    if not root:
        return "ERROR: no workspace directory selected — call set_active_workspace first"
    try:
        abs_path = executor.safe_write_file(rel_path, content, root=root)
    except executor.FileViewError as exc:
        return f"ERROR: {exc}"
    return f"OK: wrote {abs_path}"


@mcp.tool()
async def register_agent_activity(status: str, detail: str = "") -> str:
    """Heartbeat for the dashboard.

    Call this when entering a new phase so the user sees a live state badge.
    ``status`` should be one of: ``thinking``, ``executing``, ``waiting``,
    ``done``, ``idle``, ``error``.
    """
    valid = {"thinking", "executing", "waiting", "done", "idle", "error"}
    if status not in valid:
        return f"ERROR: status must be one of {sorted(valid)}"
    _gw().state.update_agent(status, detail)
    return "OK"


@mcp.tool()
async def update_conversation(
    conv_desc: str,
    status: str,
    conv_index: Optional[int] = None,
    log_title: Optional[str] = None,
    summary: Optional[str] = None,
    files_edited: Optional[List[str]] = None,
    progress_steps: Optional[List[str]] = None,
    log_content: Optional[str] = None,
    notify: bool = True,
) -> str:
    """Update a conversation with a rich interaction log.

    Matches by ``conv_index`` first, then by case-insensitive description.
    Creates a new conversation if neither matches. If ``notify`` is true the
    user gets a Telegram ping with status + summary.
    """
    gw = _gw()
    state = gw.state
    if not state.current_workspace:
        return "ERROR: no workspace selected"

    conversations = state.conversations.setdefault(state.current_workspace, [])
    conv = None
    if conv_index is not None and 0 <= conv_index < len(conversations):
        conv = conversations[conv_index]
    else:
        for c in conversations:
            if c["desc"].lower() == conv_desc.lower():
                conv = c
                break
    if conv is None:
        conv = {
            "desc": conv_desc,
            "status": "active",
            "interactions": [],
            "created_at": now_str(),
        }
        conversations.append(conv)

    conv["status"] = status

    if log_title:
        conv.setdefault("interactions", []).append(
            {
                "title": log_title,
                "summary": summary,
                "files": files_edited,
                "steps": progress_steps,
                "content": log_content,
                "time": now_str(),
            }
        )
        conv["output"] = f"Latest: {log_title}"

    state.save_conversations()
    state.append_conversation_log(
        f"[{now_str()}] 🛰️ {conv_desc} → {status} | {log_title or '-'}"
    )

    if notify:
        try:
            msg = (
                f"🛰️ *{md2(conv_desc)}*\n"
                f"_status_ `{md2(status)}`"
            )
            if log_title:
                msg += f"\n_action_ {md2(log_title)}"
            if summary:
                msg += f"\n\n{md2(summary)}"
            await gw.bot.send_message(
                chat_id=gw.config.authorized_chat_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_quick_keyboard(),
            )
        except TelegramError as exc:
            logger.error("update_conversation notify failed: %s", exc)

    return f"OK: {conv_desc} → {status}"


@mcp.tool()
async def import_conversations(workspace_name: str, conversations: List[str]) -> str:
    """Bulk-insert conversation titles for ``workspace_name``. Skips duplicates."""
    state = _gw().state
    if workspace_name not in state.workspaces and workspace_name != state.current_workspace:
        return f"ERROR: unknown workspace '{workspace_name}'"
    bucket = state.conversations.setdefault(workspace_name, [])
    existing = {c["desc"].lower() for c in bucket}
    added = 0
    for desc in conversations:
        if desc.lower() in existing:
            continue
        bucket.append(
            {
                "desc": desc,
                "status": "active",
                "interactions": [],
                "created_at": now_str(),
            }
        )
        added += 1
    state.save_conversations()
    return f"OK: added {added} conversations to {workspace_name}"


@mcp.resource("telegram://inbox")
async def telegram_inbox() -> str:
    """Read-only view of the last 10 buffered Telegram messages."""
    return "\n".join(_gw().state.recent_messages(10))
