"""Tests that queued instructions are tagged with the active workspace + path."""

import asyncio
from unittest.mock import AsyncMock

from telegravity.ui.pending import PendingRegistry
from telegravity.ui.router import Router


def _router(state, config):
    return Router(state, config, AsyncMock(), PendingRegistry(ttl_seconds=60))


def test_forward_to_agent_tags_workspace_and_path(state, config):
    state.workspaces = ["WS"]
    state.workspace_paths = {"WS": "/ws/root"}
    state.current_workspace = "WS"
    state.current_workspace_path = "/ws/root"
    asyncio.run(_router(state, config)._forward_to_agent("do it", 42, "Telegram"))
    tagged = [m for m in state.message_buffer if "do it" in m]
    assert tagged
    assert "workspace=WS" in tagged[0]
    assert "/ws/root" in tagged[0]


def test_forward_to_agent_workspace_without_path(state, config):
    state.workspaces = ["WS"]
    state.workspace_paths = {}
    state.current_workspace = "WS"
    state.current_workspace_path = None
    asyncio.run(_router(state, config)._forward_to_agent("hello", 42, "Telegram"))
    tagged = [m for m in state.message_buffer if "hello" in m]
    assert tagged
    assert "workspace=WS" in tagged[0]
    assert "dir=" not in tagged[0]


def test_forward_to_agent_no_workspace_no_tag(state, config):
    state.workspaces = []
    state.current_workspace = None
    state.current_workspace_path = None
    asyncio.run(_router(state, config)._forward_to_agent("plain", 42, "Telegram"))
    tagged = [m for m in state.message_buffer if "plain" in m]
    assert tagged
    assert "workspace=" not in tagged[0]
