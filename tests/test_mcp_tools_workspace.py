"""Tests for the workspace-aware MCP tools: set_active_workspace + agent exec."""

import asyncio
import dataclasses
from unittest.mock import AsyncMock

from telegravity import mcp_tools


def _call(fn, **kwargs):
    return asyncio.run(getattr(fn, "fn", fn)(**kwargs))


def _bind(state, config):
    mcp_tools.bind(mcp_tools.Gateway(bot=AsyncMock(), state=state, config=config))


def _ws(state, tmp_path, name="WS"):
    p = str(tmp_path)
    state.workspaces = [name]
    state.workspace_paths = {name: p}
    state.current_workspace = name
    state.current_workspace_path = p
    return p


def test_set_active_workspace_ok(state, config, tmp_path):
    p = _ws(state, tmp_path, "WS")
    state.current_workspace = None  # ensure the tool sets it
    _bind(state, config)
    out = _call(mcp_tools.set_active_workspace, name="WS")
    assert "OK" in out and p in out
    assert state.current_workspace == "WS"


def test_set_active_workspace_unknown(state, config):
    state.workspaces = ["WS"]
    _bind(state, config)
    out = _call(mcp_tools.set_active_workspace, name="Nope")
    assert "ERROR" in out


def test_run_command_disabled_by_default(state, config, tmp_path):
    _ws(state, tmp_path)
    _bind(state, config)  # enable_shell_exec is False in the test config
    assert "disabled" in _call(mcp_tools.run_command, command="echo hi").lower()


def test_run_command_requires_workspace_dir(state, config):
    cfg = dataclasses.replace(config, enable_shell_exec=True)
    state.workspaces = []
    state.current_workspace = None
    state.current_workspace_path = None
    state.workspace_paths = {}
    _bind(state, cfg)
    out = _call(mcp_tools.run_command, command="echo hi")
    assert "ERROR" in out and "workspace" in out.lower()


def test_run_command_runs_in_workspace_dir(state, config, tmp_path):
    cfg = dataclasses.replace(config, enable_shell_exec=True)
    p = _ws(state, tmp_path)
    _bind(state, cfg)
    out = _call(mcp_tools.run_command, command="echo hi")
    assert "exit=0" in out
    assert "hi" in out
    assert f"cwd={p}" in out


def test_read_file_jailed_to_workspace(state, config, tmp_path):
    (tmp_path / "f.txt").write_text("hello-content")
    cfg = dataclasses.replace(config, enable_file_view=True)
    _ws(state, tmp_path)
    _bind(state, cfg)
    assert _call(mcp_tools.read_file, rel_path="f.txt") == "hello-content"
    assert "ERROR" in _call(mcp_tools.read_file, rel_path="../escape.txt")


def test_write_file_gated_and_jailed(state, config, tmp_path):
    _ws(state, tmp_path)
    _bind(state, config)  # enable_file_write False
    assert "disabled" in _call(
        mcp_tools.write_file, rel_path="a.txt", content="x"
    ).lower()

    cfg = dataclasses.replace(config, enable_file_write=True)
    _bind(state, cfg)
    out = _call(mcp_tools.write_file, rel_path="sub/a.txt", content="data")
    assert "OK" in out
    assert (tmp_path / "sub" / "a.txt").read_text() == "data"
    assert "ERROR" in _call(mcp_tools.write_file, rel_path="../evil.txt", content="x")


def test_get_state_surfaces_workspace_dir(state, config, tmp_path):
    p = _ws(state, tmp_path, "WS")
    _bind(state, config)
    out = _call(mcp_tools.get_state)
    assert "WORKSPACE: WS" in out
    assert f"WORKSPACE_DIR: {p}" in out
    assert "AVAILABLE WORKSPACES: WS" in out
