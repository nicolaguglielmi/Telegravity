import asyncio
import json


import telegravity.paths as paths


def _state_file():
    return paths.STATE_FILE


def _conversations_file():
    return paths.CONVERSATIONS_FILE


def test_workspaces_load_from_initial(monkeypatch, data_dir):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("INITIAL_WORKSPACES", "Alpha,Beta")
    from telegravity.config import Config
    from telegravity.state import StateManager

    cfg = Config.load()
    sm = StateManager(cfg)
    assert "Alpha" in sm.workspaces
    assert "Beta" in sm.workspaces


def test_state_round_trip(state):
    state.current_workspace = "Alpha"
    state.chat_mode = True
    state.last_ai_index = 3
    state.has_seen_onboarding = True
    state.save_state()
    assert _state_file().exists()
    data = json.loads(_state_file().read_text())
    assert data["current_workspace"] == "Alpha"
    assert data["chat_mode"] is True
    assert data["last_index"] == 3
    assert data["has_seen_onboarding"] is True


def test_buffer_respects_limit(state):
    limit = state.config.BUFFER_LIMIT
    asyncio.run(_flood_buffer(state, limit + 10))
    assert len(state.message_buffer) == limit
    assert state.message_buffer[0].endswith("msg-10")


async def _flood_buffer(state, n):
    for i in range(n):
        await state.add_message(f"msg-{i}", persist_logs=False)


def test_drain_messages_advances_cursor(state):
    asyncio.run(state.add_message("a", persist_logs=False))
    asyncio.run(state.add_message("b", persist_logs=False))
    msgs = asyncio.run(state.drain_messages())
    assert msgs == ["a", "b"]
    assert asyncio.run(state.drain_messages()) == []


def test_wait_for_messages_resolves_on_new_message(state):
    async def scenario():
        async def producer():
            await asyncio.sleep(0.05)
            await state.add_message("late")

        producer_task = asyncio.create_task(producer())
        result = await state.wait_for_messages(timeout=2)
        await producer_task
        return result

    result = asyncio.run(scenario())
    assert result == ["late"]


def test_add_conversation_persists(state):
    state.current_workspace = "Alpha"
    state.workspaces.append("Alpha")
    state.add_conversation("Alpha", "First conv")
    assert _conversations_file().exists()
    payload = json.loads(_conversations_file().read_text())
    assert payload["Alpha"][0]["desc"] == "First conv"


def test_workspaces_loaded_from_file(monkeypatch, data_dir):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("INITIAL_WORKSPACES", "")
    (data_dir / "workspaces.txt").write_text("X\nY\n\nZ\n")
    from telegravity.config import Config
    from telegravity.state import StateManager

    sm = StateManager(Config.load())
    assert sm.workspaces == ["X", "Y", "Z"]


def test_reload_workspaces_picks_up_changes(state, data_dir):
    (data_dir / "workspaces.txt").write_text("New1\nNew2\n")
    count = state.reload_workspaces()
    assert count >= 2
    assert "New1" in state.workspaces


def test_state_load_corrupt_file_is_recovered(state, data_dir):
    paths.STATE_FILE.write_text("not-json")
    state._load_state()  # should not raise
    assert state.current_workspace is None


def test_conversations_load_corrupt_file(state, data_dir):
    paths.CONVERSATIONS_FILE.write_text("garbage")
    state._load_conversations()


def test_cwd_tasks_json_is_not_ingested(monkeypatch, data_dir, tmp_path):
    """A ``tasks.json`` in CWD belongs to whatever project we were launched
    from — it must never seed the conversations store."""
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.delenv("CHAT_ID", raising=False)
    (tmp_path / "tasks.json").write_text(
        '{"Alpha": [{"desc": "unrelated", "status": "active"}]}'
    )
    # State is created with cwd already set by autouse fixture
    from telegravity.config import Config
    from telegravity.state import StateManager

    sm = StateManager(Config.load())
    assert sm.conversations == {}


def test_recent_messages_returns_tail(state):
    asyncio.run(_flood(state, 30))
    assert state.recent_messages(5)[-1].endswith("29")
    assert len(state.recent_messages(5)) == 5


async def _flood(state, n):
    for i in range(n):
        await state.add_message(f"m-{i}", persist_logs=False)


def test_user_state_helpers_persist(state):
    state.set_user_state("AWAITING_X")
    assert state.user_state == "AWAITING_X"
    state.reset_user_state()
    assert state.user_state == state.USER_STATE_IDLE


def test_update_agent_records_status(state):
    state.update_agent("executing", "doing things")
    assert state.agent.status == "executing"
    assert state.agent.detail == "doing things"
    assert state.agent.freshness() == "just now"


def test_agent_freshness_buckets(state):
    import time

    state.update_agent("idle", "")
    state.agent.updated_at = time.time() - 90  # 90s ago
    assert state.agent.freshness().endswith("m ago")
    state.agent.updated_at = time.time() - 4000
    assert state.agent.freshness().endswith("h ago")
    state.agent.updated_at = time.time() - 100000
    assert state.agent.freshness().endswith("d ago")


def test_conversations_for_unknown_workspace(state):
    assert state.conversations_for(None) == []
    assert state.conversations_for("does-not-exist") == []


def test_append_logs(state):
    state.append_activity_log("activity entry")
    state.append_conversation_log("conv entry")
    assert "activity entry" in paths.ACTIVITY_LOG.read_text()
    assert "conv entry" in paths.CONVERSATION_LOG.read_text()


def test_save_state_swallows_io_error(state, monkeypatch):
    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(type(paths.STATE_FILE), "write_text", explode)
    # Should not raise — error is logged.
    state.save_state()


def test_save_conversations_swallows_io_error(state, monkeypatch):
    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(type(paths.CONVERSATIONS_FILE), "write_text", explode)
    state.save_conversations()


def test_append_activity_log_swallows_io_error(state, monkeypatch):
    def explode(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(type(paths.ACTIVITY_LOG), "open", explode)
    state.append_activity_log("won't write")
    state.append_conversation_log("won't write either")


def test_load_logs_swallows_io_error(state, monkeypatch):
    paths.ACTIVITY_LOG.write_text("line\n")
    def explode(*_args, **_kwargs):
        raise OSError("read fail")

    monkeypatch.setattr(type(paths.ACTIVITY_LOG), "read_text", explode)
    # Should not raise
    state._load_logs()


def test_workspaces_load_handles_unreadable_file(state, data_dir, monkeypatch):
    (data_dir / "workspaces.txt").write_text("Hi\n")
    def explode(*_args, **_kwargs):
        raise OSError("perm denied")

    monkeypatch.setattr(type(paths.WORKSPACES_FILE), "read_text", explode)
    state._load_workspaces()
    # Falls back to initial workspaces (empty here)
    assert isinstance(state.workspaces, list)
