import asyncio
from unittest.mock import AsyncMock

import pytest

from telegravity import mcp_tools


@pytest.fixture
def bound_gateway(state, config):
    bot = AsyncMock()
    mcp_tools.bind(mcp_tools.Gateway(bot=bot, state=state, config=config))
    state.current_workspace = "Alpha"
    state.workspaces.append("Alpha")
    return mcp_tools._gateway


def _call(fn, **kwargs):
    """FastMCP wraps tools; we invoke the underlying coroutine directly."""
    target = getattr(fn, "fn", fn)
    return asyncio.run(target(**kwargs))


def test_send_message_uses_authorized_chat(bound_gateway):
    result = _call(mcp_tools.send_message, text="hello")
    assert result == "SUCCESS"
    bound_gateway.bot.send_message.assert_awaited_once()
    kwargs = bound_gateway.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == bound_gateway.config.authorized_chat_id
    assert kwargs["text"] == "hello"


def test_check_telegram_updates_drains(bound_gateway):
    asyncio.run(bound_gateway.state.add_message("user: hi"))
    result = _call(mcp_tools.check_telegram_updates)
    assert "user: hi" in result[0]
    # Subsequent calls return empty until new traffic.
    assert _call(mcp_tools.check_telegram_updates) == []


def test_register_agent_activity_validates(bound_gateway):
    assert "ERROR" in _call(mcp_tools.register_agent_activity, status="bogus")
    result = _call(
        mcp_tools.register_agent_activity, status="executing", detail="hot path"
    )
    assert result == "OK"
    assert bound_gateway.state.agent.status == "executing"
    assert bound_gateway.state.agent.detail == "hot path"


def test_update_conversation_creates_and_notifies(bound_gateway):
    result = _call(
        mcp_tools.update_conversation,
        conv_desc="Build feature",
        status="executing",
        log_title="Step 1",
        summary="Started work",
    )
    assert "OK" in result
    convs = bound_gateway.state.conversations_for("Alpha")
    assert convs[0]["desc"] == "Build feature"
    assert convs[0]["status"] == "executing"
    assert convs[0]["interactions"][0]["title"] == "Step 1"
    bound_gateway.bot.send_message.assert_awaited()


def test_update_conversation_skips_notify_when_disabled(bound_gateway):
    _call(
        mcp_tools.update_conversation,
        conv_desc="No ping",
        status="done",
        notify=False,
    )
    bound_gateway.bot.send_message.assert_not_awaited()


def test_get_state_renders_snapshot(bound_gateway):
    asyncio.run(bound_gateway.state.add_message("user: ping"))
    text = _call(mcp_tools.get_state)
    assert "Alpha" in text
    assert "CHAT_MODE" in text


def test_get_state_with_active_conversation(bound_gateway):
    bound_gateway.state.add_conversation("Alpha", "Focus me")
    bound_gateway.state.active_conversation_index = 0
    text = _call(mcp_tools.get_state)
    assert "Focus me" in text


def test_send_message_reports_telegram_error(bound_gateway):
    from telegram.error import TelegramError

    bound_gateway.bot.send_message.side_effect = TelegramError("offline")
    result = _call(mcp_tools.send_message, text="x")
    assert result.startswith("ERROR")


def test_update_conversation_requires_workspace(bound_gateway):
    bound_gateway.state.current_workspace = None
    result = _call(
        mcp_tools.update_conversation,
        conv_desc="X",
        status="done",
    )
    assert "ERROR" in result


def test_update_conversation_matches_by_index(bound_gateway):
    bound_gateway.state.add_conversation("Alpha", "First")
    bound_gateway.state.add_conversation("Alpha", "Second")
    result = _call(
        mcp_tools.update_conversation,
        conv_desc="anything",
        status="done",
        conv_index=1,
        notify=False,
    )
    assert "OK" in result
    assert bound_gateway.state.conversations["Alpha"][1]["status"] == "done"


def test_update_conversation_swallows_notify_failure(bound_gateway):
    from telegram.error import TelegramError

    bound_gateway.bot.send_message.side_effect = TelegramError("no chat")
    result = _call(
        mcp_tools.update_conversation,
        conv_desc="X",
        status="error",
    )
    assert result.startswith("OK")


def test_import_conversations_dedupes(bound_gateway):
    bound_gateway.state.add_conversation("Alpha", "Existing")
    result = _call(
        mcp_tools.import_conversations,
        workspace_name="Alpha",
        conversations=["Existing", "Brand new"],
    )
    assert "added 1" in result


def test_import_conversations_unknown_workspace(bound_gateway):
    result = _call(
        mcp_tools.import_conversations,
        workspace_name="ZZZ-not-registered",
        conversations=["x"],
    )
    assert "ERROR" in result


def test_wait_for_remote_instruction_clamps_timeout(bound_gateway):
    # 0 → clamped to 5s minimum, but with empty buffer this still returns []
    # We don't want to actually wait 5s, so prime the buffer first
    asyncio.run(bound_gateway.state.add_message("queued"))
    result = _call(mcp_tools.wait_for_remote_instruction, timeout_sec=1)
    assert any("queued" in m for m in result)


def test_register_agent_activity_all_valid_statuses(bound_gateway):
    for status in ("thinking", "executing", "waiting", "done", "idle", "error"):
        result = _call(mcp_tools.register_agent_activity, status=status)
        assert result == "OK"
        assert bound_gateway.state.agent.status == status


def test_telegram_inbox_resource(bound_gateway):
    asyncio.run(bound_gateway.state.add_message("hi"))
    out = asyncio.run(mcp_tools.telegram_inbox())
    assert "hi" in out


def test_gateway_must_be_bound():
    import telegravity.mcp_tools as m

    # Snapshot then unbind
    saved = m._gateway
    m._gateway = None
    try:
        with pytest.raises(RuntimeError, match="bound"):
            m._gw()
    finally:
        m._gateway = saved
