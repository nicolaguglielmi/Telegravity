"""Process entrypoint.

Sets up logging, instantiates the bot + state + MCP gateway, kicks off the
Telegram polling worker and the workspaces-file watcher, then hands control to
the MCP stdio loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

from telegram import Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict, TelegramError

from . import paths
from .__version__ import __version__
from .auth import AuthGate
from .config import Config, ConfigError
from .formatting import md2
from .mcp_tools import Gateway, bind, mcp
from .pollerlock import POLLER_LOCK_RETRY_SEC, PollerLock
from .state import StateManager
from .ui.messenger import Messenger
from .ui.pending import PendingRegistry
from .ui.router import Router

logger = logging.getLogger("telegravity")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("TELEGRAVITY_LOGLEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
        stream=sys.stderr,
    )
    for noisy in ("httpx", "httpcore", "telegram.ext"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


BOT_COMMANDS = [
    BotCommand("menu", "Open the dashboard"),
    BotCommand("conversations", "Browse conversations"),
    BotCommand("workspaces", "Switch workspace"),
    BotCommand("chat", "Toggle Chat Mode"),
    BotCommand("activity", "Activity feed"),
    BotCommand("reload", "Reload workspaces"),
    BotCommand("help", "Show welcome"),
]


async def _poll_loop(bot: Bot, auth: AuthGate, router: Router) -> None:
    offset = 0
    logger.info("Polling worker started")
    backoff = 1.0
    conflict_backoff = 1.0
    while True:
        try:
            updates = await bot.get_updates(
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            backoff = 1.0
            conflict_backoff = 1.0
            for upd in updates:
                offset = upd.update_id + 1
                try:
                    if upd.callback_query:
                        if not auth.callback_allowed(upd.callback_query):
                            await upd.callback_query.answer("Not authorized", show_alert=False)
                            continue
                        await router.handle_callback(upd)
                    elif upd.message:
                        if not auth.message_allowed(upd.message):
                            continue
                        await router.handle_message(upd)
                except Exception:
                    logger.exception("Error handling update %s", upd.update_id)
        except Conflict as exc:
            # Another process briefly grabbed the long-poll. Same-DATA_DIR
            # duplicates are prevented by the poller lock (see _poller_guard),
            # so landing here means a rival with a different data dir, another
            # host, or a non-Telegravity consumer of the token. Don't give up
            # permanently: back off and retry so we resume polling once the
            # rival exits.
            logger.warning(
                "Telegram conflict — another instance is polling: %s "
                "(retrying in %.1fs)",
                exc,
                conflict_backoff,
            )
            await asyncio.sleep(conflict_backoff)
            conflict_backoff = min(conflict_backoff * 2, 15)
        except asyncio.CancelledError:
            logger.info("Polling worker cancelled")
            return
        except TelegramError as exc:
            logger.warning("Polling error: %s (retry in %.1fs)", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        except Exception:
            logger.exception("Unexpected polling error")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def _poller_guard(bot: Bot, auth: AuthGate, router: Router, lock: PollerLock) -> None:
    """Run ``_poll_loop`` only while holding the exclusive poller lock.

    Two MCP clients reading the same config spawn two telegravity processes
    with the same token; if both long-polled getUpdates, Telegram would 409
    and split updates randomly between them. Only the lock holder polls. A
    standby instance keeps serving MCP tools (send still works; the receive
    tools explain the situation — see mcp_tools) and retries the lock every
    ``POLLER_LOCK_RETRY_SEC`` so it takes over when the holder exits.
    """
    standby = False
    while True:
        if lock.try_acquire():
            if standby:
                logger.info("Poller lock acquired — taking over Telegram polling")
            await _poll_loop(bot, auth, router)
            return
        if not standby:
            logger.warning(
                "another Telegravity instance owns the Telegram poller — "
                "standing by (MCP tools still served; retrying every %.0fs)",
                POLLER_LOCK_RETRY_SEC,
            )
            standby = True
        try:
            await asyncio.sleep(POLLER_LOCK_RETRY_SEC)
        except asyncio.CancelledError:
            return


async def _watch_workspaces(state: StateManager) -> None:
    last_mtime: Optional[float] = None
    while True:
        try:
            if paths.WORKSPACES_FILE.exists():
                mtime = paths.WORKSPACES_FILE.stat().st_mtime
                if last_mtime is None or mtime > last_mtime:
                    state.reload_workspaces()
                    if last_mtime is not None:
                        logger.info("Workspaces hot-reloaded")
                    last_mtime = mtime
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Workspace watcher error")
            await asyncio.sleep(10)


async def _verify_token(bot: Bot) -> None:
    """Fail loudly on a bad token instead of running mute forever.

    Nothing else here is fatal: ``set_my_commands`` and the startup card both
    swallow TelegramError so a transient Telegram outage can't stop the MCP
    server coming up. That used to mean a wrong token produced a process that
    looked perfectly healthy — MCP tools answering, no crash — while the bot
    simply never existed. ``get_me`` is the one call whose failure is always
    the operator's problem, so it exits like a config error does.
    """
    try:
        me = await bot.get_me()
    except TelegramError as exc:
        logger.error(
            "Telegram rejected TELEGRAM_TOKEN: %s\n"
            "Check the token @BotFather gave you and set TELEGRAM_TOKEN in "
            "your .env (or %s).",
            exc,
            paths.ENV_FILE,
        )
        sys.exit(2)
    logger.info("Authenticated with Telegram as @%s", me.username)


async def _send_startup_card(messenger: Messenger, state: StateManager, config: Config) -> None:
    text = (
        "🟢 *Telegravity online* · "
        f"_v{md2(__version__)}_\n\n"
        "Tap below to open the dashboard\\."
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚀 Open dashboard", callback_data="ui_menu")]]
    )
    # Messenger swallows Telegram errors so a failed redraw can't kill the
    # worker, so ask it whether the card actually landed.
    delivered = await messenger.send_menu(config.authorized_chat_id, text, markup)
    if not delivered:
        # Usually AUTHORIZED_CHAT_ID is wrong, or the user has never opened the
        # chat — Telegram won't deliver to a chat that doesn't exist yet. Not
        # fatal: the moment they send /start, polling picks them up.
        logger.error(
            "Could not send the startup card to chat_id=%s. Open Telegram, "
            "send /start to your bot, and check AUTHORIZED_CHAT_ID "
            "(ask @userinfobot for yours).",
            config.authorized_chat_id,
        )
    # The agent itself is connected either way.
    state.update_agent("idle", "ready")


async def run() -> None:
    _setup_logging()
    logger.info("Starting Telegravity v%s", __version__)

    try:
        config = Config.load()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(2)

    paths.ensure_data_dir()
    state = StateManager(config)
    bot = Bot(token=config.telegram_token)
    await _verify_token(bot)
    auth = AuthGate(config.authorized_chat_id)
    messenger = Messenger(bot, state)
    pending = PendingRegistry(ttl_seconds=config.PENDING_CONFIRM_TTL_SEC)
    router = Router(state, config, messenger, pending)
    poller_lock = PollerLock()

    bind(Gateway(bot=bot, state=state, config=config, poller_lock=poller_lock))

    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except TelegramError as exc:
        logger.warning("Could not register bot commands: %s", exc)

    await _send_startup_card(messenger, state, config)

    poll_task = asyncio.create_task(
        _poller_guard(bot, auth, router, poller_lock), name="poll"
    )
    watch_task = asyncio.create_task(_watch_workspaces(state), name="watch")

    try:
        await mcp.run_stdio_async()
    finally:
        state.update_agent("offline")
        poll_task.cancel()
        watch_task.cancel()
        await asyncio.gather(poll_task, watch_task, return_exceptions=True)
        poller_lock.release()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
