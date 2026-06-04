"""Server entrypoint: workers, startup card, lifecycle plumbing."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import Conflict, TelegramError

from telegravity import server
from telegravity.auth import AuthGate
from telegravity.ui.messenger import Messenger
from telegravity.ui.pending import PendingRegistry
from telegravity.ui.router import Router


@pytest.fixture
def fake_bot():
    bot = AsyncMock()
    sent = MagicMock()
    sent.message_id = 1
    bot.send_message.return_value = sent
    return bot


@pytest.fixture
def router(state, config, fake_bot):
    messenger = Messenger(fake_bot, state)
    pending = PendingRegistry(ttl_seconds=60)
    return Router(state, config, messenger, pending)


def test_setup_logging_respects_env(monkeypatch):
    monkeypatch.setenv("TELEGRAVITY_LOGLEVEL", "WARNING")
    server._setup_logging()
    assert logging.getLogger().level == logging.WARNING


def _mk_update(update_id, *, message_text=None, user_id=42, callback_data=None):
    upd = MagicMock()
    upd.update_id = update_id
    upd.message = None
    upd.callback_query = None
    if message_text:
        upd.message = MagicMock()
        upd.message.text = message_text
        upd.message.chat_id = user_id
        upd.message.from_user.id = user_id
        upd.message.from_user.first_name = "Tester"
        upd.message.from_user.username = "tester"
    if callback_data:
        upd.callback_query = AsyncMock()
        upd.callback_query.data = callback_data
        upd.callback_query.message.chat_id = user_id
        upd.callback_query.from_user.id = user_id
    return upd


@pytest.mark.asyncio
async def test_poll_loop_dispatches_authorized_message(fake_bot, router, config):
    auth = AuthGate(config.authorized_chat_id)
    update = _mk_update(1, message_text="/menu", user_id=config.authorized_chat_id)
    fake_bot.get_updates.side_effect = [
        [update],
        asyncio.CancelledError(),
    ]

    task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_poll_loop_drops_unauthorized_message(fake_bot, router, config):
    auth = AuthGate(config.authorized_chat_id)
    update = _mk_update(1, message_text="/menu", user_id=999)
    fake_bot.get_updates.side_effect = [[update], asyncio.CancelledError()]

    task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # No message ever sent because router never invoked
    fake_bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_loop_rejects_unauthorized_callback(fake_bot, router, config):
    auth = AuthGate(config.authorized_chat_id)
    update = _mk_update(1, callback_data="ui_menu", user_id=7)
    fake_bot.get_updates.side_effect = [[update], asyncio.CancelledError()]

    task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    update.callback_query.answer.assert_awaited_with("Not authorized", show_alert=False)


@pytest.mark.asyncio
async def test_poll_loop_retries_on_conflict(fake_bot, router, config, monkeypatch):
    """A transient Conflict must NOT kill the worker — it backs off and retries."""
    auth = AuthGate(config.authorized_chat_id)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)
    fake_bot.get_updates.side_effect = Conflict("already polling")

    task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Backed off to retry instead of returning permanently.
    assert sleeps and sleeps[0] >= 1.0


@pytest.mark.asyncio
async def test_poll_loop_recovers_after_conflict(fake_bot, router, config, monkeypatch):
    """After the rival poller exits, the worker resumes and dispatches updates."""
    auth = AuthGate(config.authorized_chat_id)
    update = _mk_update(1, message_text="/menu", user_id=config.authorized_chat_id)
    fake_bot.get_updates.side_effect = [
        Conflict("already polling"),  # rival is briefly polling
        [update],                      # rival gone — our poll succeeds
        asyncio.CancelledError(),      # stop the loop
    ]

    async def fast_sleep(seconds):
        pass

    monkeypatch.setattr(server.asyncio, "sleep", fast_sleep)

    with patch.object(router, "handle_message") as handle:
        task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
        try:
            await task
        except asyncio.CancelledError:
            pass

    handle.assert_awaited_once()  # the update after the conflict was processed


@pytest.mark.asyncio
async def test_poll_loop_backs_off_on_telegram_error(fake_bot, router, config, monkeypatch):
    auth = AuthGate(config.authorized_chat_id)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)
    fake_bot.get_updates.side_effect = TelegramError("transient")

    task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert sleeps and sleeps[0] >= 1.0


@pytest.mark.asyncio
async def test_poll_loop_handles_handler_exception(fake_bot, router, config):
    """If a single update raises, the worker logs and keeps going."""
    auth = AuthGate(config.authorized_chat_id)
    update = _mk_update(1, message_text="/menu", user_id=config.authorized_chat_id)
    fake_bot.get_updates.side_effect = [[update], asyncio.CancelledError()]

    with patch.object(router, "handle_message", side_effect=RuntimeError("boom")):
        task = asyncio.create_task(server._poll_loop(fake_bot, auth, router))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_watch_workspaces_reloads_on_change(state, data_dir, monkeypatch):
    import os
    import time

    ws_file = data_dir / "workspaces.txt"
    ws_file.write_text("Initial\n")
    # Make sure paths module sees this file
    import telegravity.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACES_FILE", ws_file)
    monkeypatch.setattr(server, "WORKSPACES_FILE", ws_file)

    call_count = {"n": 0}
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Between iterations: rewrite + future mtime so watcher detects change
            ws_file.write_text("Initial\nSecond\n")
            future = time.time() + 100
            os.utime(ws_file, (future, future))
            await real_sleep(0)
            return
        raise asyncio.CancelledError()

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)
    try:
        await server._watch_workspaces(state)
    except asyncio.CancelledError:
        pass

    assert "Second" in state.workspaces


@pytest.mark.asyncio
async def test_watch_workspaces_handles_missing_file(state, monkeypatch):
    """Watcher should not crash when the file doesn't exist."""
    import telegravity.paths as paths_mod

    missing = paths_mod.WORKSPACES_FILE.parent / "no-such-file.txt"
    monkeypatch.setattr(server, "WORKSPACES_FILE", missing)

    iterations = {"n": 0}

    async def fake_sleep(_):
        iterations["n"] += 1
        if iterations["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)
    try:
        await server._watch_workspaces(state)
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_send_startup_card_marks_agent_ready(fake_bot, state, config):
    messenger = Messenger(fake_bot, state)
    await server._send_startup_card(fake_bot, messenger, state, config)
    assert state.agent.status == "idle"
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_send_startup_card_survives_telegram_error(fake_bot, state, config):
    fake_bot.send_message.side_effect = TelegramError("offline")
    messenger = Messenger(fake_bot, state)
    # Should not raise.
    await server._send_startup_card(fake_bot, messenger, state, config)


def test_main_handles_keyboard_interrupt(monkeypatch):
    async def boom():
        raise KeyboardInterrupt

    monkeypatch.setattr(server, "run", boom)
    # Should swallow the KeyboardInterrupt
    server.main()


@pytest.mark.asyncio
async def test_run_exits_on_bad_config(monkeypatch):
    """``run()`` should call sys.exit(2) when Config.load fails."""
    from telegravity.config import ConfigError

    def bad_load():
        raise ConfigError("missing")

    monkeypatch.setattr(server.Config, "load", bad_load)
    with pytest.raises(SystemExit) as exc:
        await server.run()
    assert exc.value.code == 2


def _make_fake_bot(get_updates_side_effect=None):
    """Build a Bot stub whose ``get_updates`` actually yields control so the
    polling worker is cancellable instead of spinning a tight CPU loop."""

    fake_bot = AsyncMock()
    sent = MagicMock()
    sent.message_id = 1
    fake_bot.send_message.return_value = sent

    if get_updates_side_effect is None:
        async def yielding_updates(*_args, **_kwargs):
            # Sleep briefly so a cancel() between iterations is honored.
            await asyncio.sleep(0.05)
            return []
        fake_bot.get_updates.side_effect = yielding_updates
    else:
        fake_bot.get_updates.side_effect = get_updates_side_effect

    return fake_bot


@pytest.mark.asyncio
async def test_run_full_lifecycle(monkeypatch, config, data_dir):
    """End-to-end happy path: Config OK → bot stub → MCP stdio returns immediately."""

    fake_bot = _make_fake_bot()
    monkeypatch.setattr(server, "Bot", MagicMock(return_value=fake_bot))

    async def quick_stdio():
        await asyncio.sleep(0.05)

    monkeypatch.setattr(server.mcp, "run_stdio_async", quick_stdio)
    monkeypatch.setattr(server.Config, "load", staticmethod(lambda: config))

    await asyncio.wait_for(server.run(), timeout=3)

    fake_bot.set_my_commands.assert_awaited()
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_run_continues_when_set_my_commands_fails(monkeypatch, config):
    fake_bot = _make_fake_bot()
    fake_bot.set_my_commands.side_effect = TelegramError("offline")
    monkeypatch.setattr(server, "Bot", MagicMock(return_value=fake_bot))

    async def quick_stdio():
        await asyncio.sleep(0.05)

    monkeypatch.setattr(server.mcp, "run_stdio_async", quick_stdio)
    monkeypatch.setattr(server.Config, "load", staticmethod(lambda: config))

    # Best-effort: should not raise even if registering commands fails.
    await asyncio.wait_for(server.run(), timeout=3)
