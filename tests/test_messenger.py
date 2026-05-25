from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest, TelegramError

from telegravity.ui.messenger import Messenger


@pytest.fixture
def bot():
    b = AsyncMock()
    sent = MagicMock()
    sent.message_id = 999
    b.send_message.return_value = sent
    return b


@pytest.fixture
def messenger(bot, state):
    return Messenger(bot, state)


@pytest.mark.asyncio
async def test_send_menu_creates_new_message(messenger, bot, state):
    await messenger.send_menu(42, "hello", markup=None)
    bot.send_message.assert_awaited_once()
    assert state.last_menu_message_id == 999


@pytest.mark.asyncio
async def test_send_menu_deletes_previous_then_sends(messenger, bot, state):
    state.last_menu_message_id = 7
    await messenger.send_menu(42, "hello")
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=7)
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_menu_swallows_delete_errors(messenger, bot, state):
    state.last_menu_message_id = 7
    bot.delete_message.side_effect = TelegramError("gone")
    # Should not raise — delete failure is harmless.
    await messenger.send_menu(42, "hello")
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_menu_uses_edit_when_query_provided(messenger, bot):
    query = AsyncMock()
    await messenger.send_menu(42, "edit me", edit_query=query)
    query.edit_message_text.assert_awaited_once()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_menu_silent_on_not_modified(messenger, bot):
    query = AsyncMock()
    query.edit_message_text.side_effect = BadRequest("message is not modified")
    await messenger.send_menu(42, "same content", edit_query=query)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_menu_falls_back_when_edit_fails(messenger, bot, state):
    query = AsyncMock()
    query.edit_message_text.side_effect = TelegramError("boom")
    await messenger.send_menu(42, "new content", edit_query=query)
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_menu_logs_when_send_fails(messenger, bot):
    bot.send_message.side_effect = TelegramError("no route to telegram")
    # Should not raise.
    await messenger.send_menu(42, "hello")


@pytest.mark.asyncio
async def test_send_plain_uses_markdown_v2(messenger, bot):
    await messenger.send_plain(42, "_italic_")
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 42
    assert kwargs["parse_mode"].value == "MarkdownV2"


@pytest.mark.asyncio
async def test_send_plain_swallows_errors(messenger, bot):
    bot.send_message.side_effect = TelegramError("nope")
    await messenger.send_plain(42, "hello")
