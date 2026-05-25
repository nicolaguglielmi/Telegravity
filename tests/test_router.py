import asyncio
import dataclasses
from unittest.mock import AsyncMock

import pytest

from telegravity.ui.pending import PendingRegistry
from telegravity.ui.router import (
    USER_STATE_AGENT,
    USER_STATE_SHELL,
    Router,
)


def _enable_features(router, *, shell=False, file=False):
    """Config is frozen — build a fresh router with the toggles flipped."""
    new_cfg = dataclasses.replace(
        router.config, enable_shell_exec=shell, enable_file_view=file
    )
    return Router(router.state, new_cfg, router.messenger, router.pending)


class FakeMessenger:
    def __init__(self):
        self.menus = []
        self.plain = []

    async def send_menu(self, chat_id, text, markup=None, *, edit_query=None, replace_previous=True):
        self.menus.append((chat_id, text, markup, edit_query))

    async def send_plain(self, chat_id, text, markup=None):
        self.plain.append((chat_id, text))


def make_update(text=None, *, callback_data=None, user_id=42):
    upd = AsyncMock()
    upd.message = None
    upd.callback_query = None
    if text is not None:
        upd.message = AsyncMock()
        upd.message.text = text
        upd.message.chat_id = user_id
        upd.message.from_user.first_name = "Tester"
        upd.message.from_user.id = user_id
    if callback_data is not None:
        upd.callback_query = AsyncMock()
        upd.callback_query.data = callback_data
        upd.callback_query.message.chat_id = user_id
        upd.callback_query.from_user.id = user_id
    return upd


@pytest.fixture
def router(state, config):
    messenger = FakeMessenger()
    pending = PendingRegistry(ttl_seconds=60)
    return Router(state, config, messenger, pending), messenger, pending


def test_start_shows_welcome_first_time(router):
    r, messenger, _ = router
    asyncio.run(r.handle_message(make_update("/start")))
    assert messenger.menus, "Welcome should be sent"
    text = messenger.menus[0][1]
    assert "Telegravity" in text
    assert r.state.has_seen_onboarding is True


def test_start_second_time_shows_dashboard(router):
    r, messenger, _ = router
    r.state.has_seen_onboarding = True
    asyncio.run(r.handle_message(make_update("/start")))
    text = messenger.menus[-1][1]
    assert "Dashboard" in text


def test_menu_command_renders_dashboard(router):
    r, messenger, _ = router
    asyncio.run(r.handle_message(make_update("/menu")))
    assert any("Dashboard" in m[1] for m in messenger.menus)


def test_chat_toggle_persists(router):
    r, messenger, _ = router
    assert r.state.chat_mode is False
    asyncio.run(r.handle_message(make_update("/chat")))
    assert r.state.chat_mode is True


def test_agent_prompt_flow_buffers_message(router):
    r, messenger, _ = router
    r.state.set_user_state(USER_STATE_AGENT)
    asyncio.run(r.handle_message(make_update("refactor this")))
    assert r.state.user_state == r.state.USER_STATE_IDLE
    assert any("refactor this" in m for m in r.state.message_buffer)


def test_shell_flow_requires_confirmation(router):
    r, messenger, pending = router
    r.state.set_user_state(USER_STATE_SHELL)
    asyncio.run(r.handle_message(make_update("ls -la")))
    # The dialog should have produced a confirmation prompt with one pending token.
    assert len(pending._items) == 1
    token = next(iter(pending._items))
    assert pending._items[token].payload == "ls -la"


def test_shell_disabled_returns_help(router):
    r, messenger, pending = router
    # Config has ENABLE_SHELL_EXEC=0 in fixture
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_command")))
    assert any("disabled" in t.lower() for _, t in messenger.plain)


def test_chat_mode_forwards_free_text(router):
    r, messenger, _ = router
    r.state.chat_mode = True
    asyncio.run(r.handle_message(make_update("do the thing")))
    assert any("do the thing" in m for m in r.state.message_buffer)


def test_idle_free_text_explains_chat_mode(router):
    r, messenger, _ = router
    r.state.chat_mode = False
    asyncio.run(r.handle_message(make_update("random text")))
    assert any("Chat Mode" in t or "Ask agent" in t for _, t in messenger.plain)


def test_unknown_slash_command_falls_through(router):
    r, messenger, _ = router
    asyncio.run(r.handle_message(make_update("/nothinghere")))
    # Should still reset user state and not crash
    assert r.state.user_state == r.state.USER_STATE_IDLE


def test_help_alias_renders_welcome(router):
    r, messenger, _ = router
    asyncio.run(r.handle_message(make_update("/help")))
    assert any("Telegravity" in m[1] for m in messenger.menus)


def test_reload_command_returns_count(router):
    r, messenger, _ = router
    r.state.workspaces = ["A", "B"]
    asyncio.run(r.handle_message(make_update("/reload")))
    assert any("workspaces reloaded" in t for _, t in messenger.plain)


def test_new_conv_dialog_creates_thread(router):
    r, messenger, _ = router
    r.state.current_workspace = "Alpha"
    r.state.workspaces = ["Alpha"]
    asyncio.run(r.handle_callback(make_update(callback_data="ui_new_conv")))
    assert r.state.user_state == "AWAITING_NEW_CONV_TITLE"
    asyncio.run(r.handle_message(make_update("Refactor login")))
    convs = r.state.conversations_for("Alpha")
    assert any(c["desc"] == "Refactor login" for c in convs)


def test_new_conv_requires_workspace(router):
    r, messenger, _ = router
    r.state.current_workspace = None
    asyncio.run(r.handle_callback(make_update(callback_data="ui_new_conv")))
    # No state change because there's no workspace selected
    assert r.state.user_state == r.state.USER_STATE_IDLE


def test_select_workspace_callback(router):
    r, messenger, _ = router
    r.state.workspaces = ["Alpha"]
    asyncio.run(r.handle_callback(make_update(callback_data="select:Alpha")))
    assert r.state.current_workspace == "Alpha"


def test_tour_callback_renders_step(router):
    r, messenger, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="tour:2")))
    assert any("2 /" in m[1] for m in messenger.menus)


def test_ui_workspaces_resets_user_state(router):
    r, messenger, _ = router
    r.state.set_user_state("AWAITING_AGENT_PROMPT")
    asyncio.run(r.handle_callback(make_update(callback_data="ui_workspaces")))
    assert r.state.user_state == r.state.USER_STATE_IDLE


def test_ui_sync_callback_reloads(router):
    r, messenger, _ = router
    r.state.workspaces = []
    asyncio.run(r.handle_callback(make_update(callback_data="ui_sync")))
    # No crash, no workspaces still
    assert r.state.workspaces == []


def test_ui_conversations_without_workspace(router):
    r, messenger, _ = router
    r.state.current_workspace = None
    asyncio.run(r.handle_callback(make_update(callback_data="ui_conversations")))
    # Falls back to dashboard
    assert messenger.menus


def test_ui_conversations_with_workspace(router):
    r, messenger, _ = router
    r.state.current_workspace = "Alpha"
    r.state.workspaces = ["Alpha"]
    asyncio.run(r.handle_callback(make_update(callback_data="ui_conversations")))
    assert any("Conversation Hub" in m[1] for m in messenger.menus)


def test_conv_view_callback(router):
    r, messenger, _ = router
    r.state.current_workspace = "Alpha"
    r.state.workspaces = ["Alpha"]
    r.state.add_conversation("Alpha", "X")
    asyncio.run(r.handle_callback(make_update(callback_data="conv_view:0")))
    assert any("Conversation" in m[1] for m in messenger.menus)


def test_int_view_callback(router):
    r, messenger, _ = router
    r.state.current_workspace = "Alpha"
    r.state.workspaces = ["Alpha"]
    r.state.add_conversation("Alpha", "X")
    r.state.conversations["Alpha"][0]["interactions"] = [
        {"title": "S1", "time": "12:00", "content": "out"}
    ]
    asyncio.run(r.handle_callback(make_update(callback_data="int_view:0:0")))
    assert any("Step 1" in m[1] for m in messenger.menus)


def test_enter_chat_callback_enables_chat_mode(router):
    r, messenger, _ = router
    r.state.current_workspace = "Alpha"
    r.state.workspaces = ["Alpha"]
    r.state.add_conversation("Alpha", "X")
    r.state.chat_mode = False
    asyncio.run(r.handle_callback(make_update(callback_data="ui_enter_chat:0")))
    assert r.state.chat_mode is True
    assert r.state.active_conversation_index == 0


def test_chat_toggle_via_callback(router):
    r, _, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="ui_chat_toggle")))
    assert r.state.chat_mode is True
    asyncio.run(r.handle_callback(make_update(callback_data="ui_chat_toggle")))
    assert r.state.chat_mode is False


def test_chat_log_callback_renders_feed(router):
    r, messenger, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="ui_chat_log")))
    assert any("Activity" in m[1] for m in messenger.menus)


def test_ask_agent_prompt_sets_state(router):
    r, _, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_agent")))
    assert r.state.user_state == "AWAITING_AGENT_PROMPT"


def test_shell_confirm_runs_and_clears(router):
    r, messenger, pending = router
    r = _enable_features(r, shell=True)
    r.state.set_user_state("AWAITING_SHELL")
    asyncio.run(r.handle_message(make_update("echo hi")))
    token = next(iter(pending._items))
    asyncio.run(r.handle_callback(make_update(callback_data=f"shell_ok:{token}")))
    assert pending.take(token) is None
    assert any("exit 0" in t or "hi" in t for _, t in messenger.plain)


def test_shell_confirm_expired_token(router):
    r, messenger, pending = router
    r = _enable_features(r, shell=True)
    asyncio.run(r.handle_callback(make_update(callback_data="shell_ok:bogus")))
    assert messenger.menus


def test_shell_cancel_releases_token(router):
    r, messenger, pending = router
    r = _enable_features(r, shell=True)
    r.state.set_user_state("AWAITING_SHELL")
    asyncio.run(r.handle_message(make_update("rm -rf /")))
    token = next(iter(pending._items))
    asyncio.run(r.handle_callback(make_update(callback_data=f"shell_no:{token}")))
    assert pending.take(token) is None


def test_file_view_flow(router, tmp_path):
    r, messenger, pending = router
    r = _enable_features(r, file=True)
    target = tmp_path / "hello.md"
    target.write_text("# hi")
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_file")))
    assert r.state.user_state == "AWAITING_FILE"
    asyncio.run(r.handle_message(make_update("hello.md")))
    token = next(iter(pending._items))
    asyncio.run(r.handle_callback(make_update(callback_data=f"file_ok:{token}")))
    assert any("hi" in t for _, t in messenger.plain)


def test_file_view_cancel_clears_token(router, tmp_path):
    r, messenger, pending = router
    r = _enable_features(r, file=True)
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_file")))
    asyncio.run(r.handle_message(make_update("anywhere.txt")))
    token = next(iter(pending._items))
    asyncio.run(r.handle_callback(make_update(callback_data=f"file_no:{token}")))
    assert pending.take(token) is None


def test_file_view_invalid_path_renders_error(router, tmp_path):
    r, messenger, pending = router
    r = _enable_features(r, file=True)
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_file")))
    asyncio.run(r.handle_message(make_update("does/not/exist")))
    token = next(iter(pending._items))
    asyncio.run(r.handle_callback(make_update(callback_data=f"file_ok:{token}")))
    assert any("not found" in t for _, t in messenger.plain)


def test_shell_disabled_during_confirm_short_circuits(router):
    """If feature is toggled off between prompt and confirm, executor refuses."""
    r, messenger, pending = router
    r_enabled = _enable_features(r, shell=True)
    r_enabled.state.set_user_state("AWAITING_SHELL")
    asyncio.run(r_enabled.handle_message(make_update("echo hi")))
    token = next(iter(pending._items))
    # Now use the original router (shell disabled) to confirm
    asyncio.run(r.handle_callback(make_update(callback_data=f"shell_ok:{token}")))
    # Pending was taken but executor short-circuits on disabled feature
    assert pending.take(token) is None


def test_file_disabled_explains(router):
    r, messenger, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="ui_prompt_file")))
    assert any("disabled" in t.lower() for _, t in messenger.plain)


def test_unknown_callback_is_swallowed(router):
    r, _, _ = router
    asyncio.run(r.handle_callback(make_update(callback_data="totally_unknown_thing")))


def test_missing_message_is_noop(router):
    r, messenger, _ = router
    upd = make_update()
    upd.message = None
    upd.callback_query = None
    asyncio.run(r.handle_message(upd))
    assert messenger.menus == []


def test_callback_without_data_is_noop(router):
    r, messenger, _ = router
    from unittest.mock import AsyncMock
    upd = AsyncMock()
    upd.callback_query = None
    asyncio.run(r.handle_callback(upd))
    assert messenger.menus == []
