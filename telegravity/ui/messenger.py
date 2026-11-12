"""Thin wrapper around the Telegram Bot API for sending/editing menus.

Centralises the "send a new message, but if there's a stale menu kill it"
dance so views don't have to know about ``last_menu_message_id``. Always uses
MarkdownV2.
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Bot, CallbackQuery, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from ..state import StateManager

logger = logging.getLogger(__name__)


class Messenger:
    def __init__(self, bot: Bot, state: StateManager):
        self.bot = bot
        self.state = state

    async def send_menu(
        self,
        chat_id: int,
        text: str,
        markup: Optional[InlineKeyboardMarkup] = None,
        *,
        edit_query: Optional[CallbackQuery] = None,
        replace_previous: bool = True,
    ) -> bool:
        """Render a screen. Returns whether it actually reached the chat.

        Telegram errors are swallowed and logged here — a failed redraw must
        not kill the polling worker — so the boolean is the only way a caller
        can tell. The startup card uses it to explain a misconfigured
        AUTHORIZED_CHAT_ID instead of failing silently.
        """
        if edit_query:
            try:
                await edit_query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return True
            except BadRequest as exc:
                # "message is not modified" → harmless, the screen is already
                # what we wanted it to be.
                if "not modified" in str(exc).lower():
                    return True
                logger.debug("Inline edit failed (%s), falling back to send", exc)
            except TelegramError as exc:
                logger.warning("Inline edit failed: %s", exc)

        if replace_previous and self.state.last_menu_message_id:
            try:
                await self.bot.delete_message(
                    chat_id=chat_id, message_id=self.state.last_menu_message_id
                )
            except TelegramError:
                pass

        try:
            msg = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            self.state.last_menu_message_id = msg.message_id
            self.state.save_state()
            return True
        except TelegramError as exc:
            logger.error("Failed to send menu: %s", exc)
            return False

    async def send_plain(
        self,
        chat_id: int,
        text: str,
        markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except TelegramError as exc:
            logger.error("Failed to send plain message: %s", exc)
