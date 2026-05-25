"""Routes inbound Telegram updates to renderers/executors."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ..config import Config
from ..formatting import md2, now_str
from ..state import StateManager
from . import executor, views
from .messenger import Messenger
from .pending import PendingRegistry

logger = logging.getLogger(__name__)

USER_STATE_SHELL = "AWAITING_SHELL"
USER_STATE_FILE = "AWAITING_FILE"
USER_STATE_AGENT = "AWAITING_AGENT_PROMPT"
USER_STATE_NEW_CONV = "AWAITING_NEW_CONV_TITLE"


class Router:
    def __init__(
        self,
        state: StateManager,
        config: Config,
        messenger: Messenger,
        pending: PendingRegistry,
    ):
        self.state = state
        self.config = config
        self.messenger = messenger
        self.pending = pending

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------
    async def handle_message(self, update: Update) -> None:
        message = update.message
        if not message or not message.text:
            return

        text = message.text.strip()
        chat_id = message.chat_id
        first_name = message.from_user.first_name if message.from_user else ""

        if text.lower() in {"/start", "start"}:
            await self._handle_start(chat_id, first_name)
            return

        if text.startswith("/"):
            handled = await self._handle_command(text, chat_id)
            if handled:
                self.state.reset_user_state()
                return

        # In-progress dialog (waiting for a free-text input)
        if self.state.user_state != StateManager.USER_STATE_IDLE:
            await self._handle_pending_input(text, chat_id)
            return

        if self.state.chat_mode:
            await self._forward_to_agent(text, chat_id, first_name)
            return

        # Default: assume it's a prompt for the agent and tell the user how to act on it.
        await self.messenger.send_plain(
            chat_id,
            "_I don't have Chat Mode on, so I didn't queue that\\._\n"
            "Open `/menu` and tap *Ask agent* or toggle *Chat mode*\\.",
        )

    # ------------------------------------------------------------------
    # Callback handler
    # ------------------------------------------------------------------
    async def handle_callback(self, update: Update) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        data = query.data
        chat_id = query.message.chat_id

        # Selection
        if data.startswith("select:"):
            workspace = data.split(":", 1)[1]
            self.state.current_workspace = workspace
            self.state.active_conversation_index = None
            self.state.save_state()
            await query.answer(f"📍 {workspace}")
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return

        if data.startswith("tour:"):
            step = int(data.split(":", 1)[1])
            await query.answer()
            await self._render(views.render_tour(step), chat_id, edit_query=query)
            return

        if data == "ui_menu":
            self.state.reset_user_state()
            await query.answer()
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return

        if data == "ui_workspaces":
            self.state.reset_user_state()
            await query.answer()
            await self._render(views.render_workspace_picker(self.state), chat_id, edit_query=query)
            return

        if data == "ui_sync":
            count = self.state.reload_workspaces()
            await query.answer(f"🔄 {count} workspaces loaded")
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return

        if data == "ui_conversations":
            self.state.reset_user_state()
            if not self.state.current_workspace:
                await query.answer("⚠ Pick a workspace first")
                await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
                return
            await query.answer()
            await self._render(views.render_conversation_hub(self.state), chat_id, edit_query=query)
            return

        if data.startswith("conv_view:"):
            idx = int(data.split(":", 1)[1])
            await query.answer()
            await self._render(views.render_conversation_detail(self.state, idx), chat_id, edit_query=query)
            return

        if data.startswith("int_view:"):
            _, conv_idx, int_idx = data.split(":")
            await query.answer()
            await self._render(
                views.render_interaction_detail(self.state, int(conv_idx), int(int_idx)),
                chat_id,
                edit_query=query,
            )
            return

        if data.startswith("ui_enter_chat:"):
            idx = int(data.split(":", 1)[1])
            self.state.active_conversation_index = idx
            self.state.chat_mode = True
            self.state.save_state()
            conversations = self.state.conversations_for(self.state.current_workspace)
            desc = conversations[idx]["desc"] if idx < len(conversations) else "—"
            await query.answer("💬 Chat active")
            await self.messenger.send_menu(
                chat_id,
                f"💬 *Chatting in* `{md2(desc)}`\n"
                "Type your next instruction — it will be queued for the agent\\.",
                edit_query=query,
            )
            return

        if data == "ui_chat_toggle":
            self.state.chat_mode = not self.state.chat_mode
            self.state.save_state()
            await query.answer(f"Chat mode: {'ON' if self.state.chat_mode else 'OFF'}")
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return

        if data == "ui_chat_log":
            await query.answer()
            await self._render(views.render_activity_feed(self.state), chat_id, edit_query=query)
            return

        if data == "ui_new_conv":
            if not self.state.current_workspace:
                await query.answer("⚠ Pick a workspace first")
                return
            self.state.set_user_state(USER_STATE_NEW_CONV)
            await query.answer()
            await self._render(views.render_prompt("new_conv"), chat_id, edit_query=query)
            return

        if data == "ui_prompt_agent":
            self.state.set_user_state(USER_STATE_AGENT)
            await query.answer()
            await self._render(views.render_prompt("agent"), chat_id, edit_query=query)
            return

        if data == "ui_prompt_command":
            if not executor.is_enabled(self.config, "shell"):
                await query.answer("Disabled in .env")
                await self.messenger.send_plain(chat_id, executor.feature_disabled_message("shell"))
                return
            self.state.set_user_state(USER_STATE_SHELL)
            await query.answer()
            await self._render(views.render_prompt("shell"), chat_id, edit_query=query)
            return

        if data == "ui_prompt_file":
            if not executor.is_enabled(self.config, "file"):
                await query.answer("Disabled in .env")
                await self.messenger.send_plain(chat_id, executor.feature_disabled_message("file"))
                return
            self.state.set_user_state(USER_STATE_FILE)
            await query.answer()
            await self._render(views.render_prompt("file"), chat_id, edit_query=query)
            return

        # Confirm flow ------------------------------------------------------
        if data.startswith("shell_ok:"):
            await self._confirm_shell(query, data.split(":", 1)[1])
            return
        if data.startswith("shell_no:"):
            self.pending.cancel(data.split(":", 1)[1])
            await query.answer("Cancelled")
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return
        if data.startswith("file_ok:"):
            await self._confirm_file(query, data.split(":", 1)[1])
            return
        if data.startswith("file_no:"):
            self.pending.cancel(data.split(":", 1)[1])
            await query.answer("Cancelled")
            await self._render(views.render_dashboard(self.state, self.config), chat_id, edit_query=query)
            return

        # Unknown callback
        await query.answer()
        logger.warning("Unhandled callback: %s", data)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _render(self, payload, chat_id, *, edit_query=None) -> None:
        text, markup = payload
        await self.messenger.send_menu(chat_id, text, markup, edit_query=edit_query)

    async def _handle_start(self, chat_id: int, first_name: str) -> None:
        if not self.state.has_seen_onboarding:
            self.state.has_seen_onboarding = True
            self.state.save_state()
            await self._render(views.render_welcome(self.state, first_name), chat_id)
        else:
            await self._render(views.render_dashboard(self.state, self.config), chat_id)

    async def _handle_command(self, text: str, chat_id: int) -> bool:
        cmd = text.split("@", 1)[0].split()[0].lower()
        if cmd == "/menu":
            await self._render(views.render_dashboard(self.state, self.config), chat_id)
            return True
        if cmd in {"/conversations", "/conv"}:
            await self._render(views.render_conversation_hub(self.state), chat_id)
            return True
        if cmd == "/workspaces":
            await self._render(views.render_workspace_picker(self.state), chat_id)
            return True
        if cmd == "/chat":
            self.state.chat_mode = not self.state.chat_mode
            self.state.save_state()
            await self._render(views.render_dashboard(self.state, self.config), chat_id)
            return True
        if cmd == "/activity" or cmd == "/logs":
            await self._render(views.render_activity_feed(self.state), chat_id)
            return True
        if cmd == "/reload":
            count = self.state.reload_workspaces()
            await self.messenger.send_plain(chat_id, f"🔄 *{count}* workspaces reloaded\\.")
            return True
        if cmd in {"/help", "/start"}:
            await self._render(views.render_welcome(self.state, ""), chat_id)
            return True
        return False

    async def _handle_pending_input(self, text: str, chat_id: int) -> None:
        user_state = self.state.user_state
        self.state.reset_user_state()

        if user_state == USER_STATE_AGENT:
            await self._forward_to_agent(text, chat_id, "Telegram")
            await self._render(views.render_dashboard(self.state, self.config), chat_id)
            return

        if user_state == USER_STATE_NEW_CONV:
            if not self.state.current_workspace:
                await self.messenger.send_plain(chat_id, "⚠ Pick a workspace first\\.")
                return
            self.state.add_conversation(self.state.current_workspace, text)
            await self.messenger.send_plain(chat_id, f"🚀 Started: *{md2(text)}*")
            await self._render(views.render_conversation_hub(self.state), chat_id)
            return

        if user_state == USER_STATE_SHELL:
            token = self.pending.add("shell", text, chat_id)
            await self._render(views.render_shell_confirm(token, text), chat_id)
            return

        if user_state == USER_STATE_FILE:
            token = self.pending.add("file", text, chat_id)
            await self._render(views.render_file_confirm(token, text), chat_id)
            return

    async def _forward_to_agent(self, text: str, chat_id: int, sender: str) -> None:
        msg = f"[{now_str()}] 👤 {sender}: {text}"
        await self.state.add_message(msg)
        await self.messenger.send_plain(
            chat_id,
            f"✅ *Queued for the agent*\n_{md2(text)}_",
        )

    async def _confirm_shell(self, query, token: str) -> None:
        pending = self.pending.take(token)
        if not pending:
            await query.answer("⏰ Expired — try again")
            await self._render(views.render_dashboard(self.state, self.config), query.message.chat_id, edit_query=query)
            return
        if not executor.is_enabled(self.config, "shell"):
            await query.answer("Disabled")
            return
        await query.answer("Running…")
        chat_id = query.message.chat_id
        try:
            code, stdout, stderr = await executor.run_shell(
                pending.payload, timeout=self.config.SHELL_TIMEOUT_SEC
            )
            text = executor.format_shell_result(pending.payload, code, stdout, stderr)
        except asyncio.TimeoutError:
            text = f"❌ Timeout after *{self.config.SHELL_TIMEOUT_SEC}s*\\."
        except Exception as exc:
            logger.exception("Shell exec failed")
            text = f"❌ Error: `{md2(str(exc))}`"
        await self.messenger.send_plain(chat_id, text)
        await self._render(views.render_dashboard(self.state, self.config), chat_id)

    async def _confirm_file(self, query, token: str) -> None:
        pending = self.pending.take(token)
        if not pending:
            await query.answer("⏰ Expired — try again")
            await self._render(views.render_dashboard(self.state, self.config), query.message.chat_id, edit_query=query)
            return
        if not executor.is_enabled(self.config, "file"):
            await query.answer("Disabled")
            return
        await query.answer("Opening…")
        chat_id = query.message.chat_id
        try:
            language, content = executor.safe_read_file(pending.payload)
            text = executor.format_file_view(pending.payload, language, content)
        except executor.FileViewError as exc:
            text = f"❌ {md2(str(exc))}"
        except Exception as exc:
            logger.exception("File view failed")
            text = f"❌ Error: `{md2(str(exc))}`"
        await self.messenger.send_plain(chat_id, text)
        await self._render(views.render_dashboard(self.state, self.config), chat_id)
