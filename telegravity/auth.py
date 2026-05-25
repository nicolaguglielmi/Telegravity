"""Authorization: only the configured chat_id can drive the bot."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import CallbackQuery, Message

logger = logging.getLogger(__name__)


class AuthGate:
    """Single-user lockdown.

    The bot is configured with one ``authorized_chat_id``; every inbound
    message and callback is matched against it. Anything else gets a short
    polite refusal (logged at INFO with the unauthorized id, so the operator
    can spot scanning attempts).
    """

    def __init__(self, authorized_chat_id: int):
        self.authorized_chat_id = authorized_chat_id

    def message_allowed(self, message: Optional[Message]) -> bool:
        if not message or not message.from_user:
            return False
        ok = message.from_user.id == self.authorized_chat_id
        if not ok:
            logger.info(
                "Rejected message from unauthorized chat_id=%s username=%s text=%r",
                message.from_user.id,
                message.from_user.username,
                (message.text or "")[:120],
            )
        return ok

    def callback_allowed(self, query: Optional[CallbackQuery]) -> bool:
        if not query or not query.from_user:
            return False
        ok = query.from_user.id == self.authorized_chat_id
        if not ok:
            logger.info(
                "Rejected callback from unauthorized chat_id=%s data=%r",
                query.from_user.id,
                query.data,
            )
        return ok
