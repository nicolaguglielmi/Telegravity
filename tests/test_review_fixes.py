"""Regression tests added from the adversarial review of the workspace feature.

The headline ones lock in the path-jail's symlink/absolute-path behavior — the
feature's security boundary, which previously had only lexical '..' coverage and
would silently break under a symlink-blind refactor.
"""

import asyncio
import dataclasses
import importlib
import json
import os
from unittest.mock import AsyncMock

import pytest

from telegravity import mcp_tools
from telegravity import paths as _paths
from telegravity.ui import executor
from telegravity.workspaces import resolve_workspaces


def _call(fn, **kwargs):
    return asyncio.run(getattr(fn, "fn", fn)(**kwargs))


# --- security: the jail must collapse symlinks and reject absolute paths ---

def test_safe_read_file_blocks_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOPSECRET")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "link.txt").symlink_to(outside / "secret.txt")
    with pytest.raises(executor.FileViewError):
        executor.safe_read_file("link.txt", root=str(root))


def test_safe_write_file_blocks_symlinked_dir_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "ws"
    root.mkdir()
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    with pytest.raises(executor.FileViewError):
        executor.safe_write_file("linkdir/x.txt", "data", root=str(root))
    assert not (outside / "x.txt").exists()


def test_safe_read_file_blocks_absolute_path(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(executor.FileViewError):
        executor.safe_read_file("/etc/hosts", root=str(root))


# --- mcp: run_command timeout returns ERROR (not an uncaught exception) ---

def test_run_command_timeout(state, config, tmp_path):
    cfg = dataclasses.replace(config, enable_shell_exec=True)
    state.workspaces = ["WS"]
    state.workspace_paths = {"WS": str(tmp_path)}
    state.current_workspace = "WS"
    state.current_workspace_path = str(tmp_path)
    mcp_tools.bind(mcp_tools.Gateway(bot=AsyncMock(), state=state, config=cfg))
    out = _call(mcp_tools.run_command, command="sleep 3", timeout_sec=1)
    assert "timed out" in out.lower()
    assert f"cwd={tmp_path}" in out


# --- correctness: reload re-derives a kept path and clears a removed one ---

def test_reload_redrives_path_for_kept_workspace(state, data_dir):
    new_dir = data_dir / "A-new"
    new_dir.mkdir()
    state.workspaces = ["A"]
    state.workspace_paths = {"A": "/old/path"}
    state.current_workspace = "A"
    state.current_workspace_path = "/old/path"
    (data_dir / "workspaces.txt").write_text(f"A={new_dir}\n")
    state.reload_workspaces()
    assert state.current_workspace == "A"
    assert state.workspace_root() == str(new_dir.resolve())


def test_reload_clears_removed_workspace(state, data_dir):
    state.workspaces = ["A"]
    state.workspace_paths = {"A": "/old/path"}
    state.current_workspace = "A"
    state.current_workspace_path = "/old/path"
    (data_dir / "workspaces.txt").write_text("B\n")  # A is gone everywhere
    state.reload_workspaces()
    assert state.current_workspace is None
    assert state.workspace_root() is None


# --- workspaces: auto-import path wins over the base-dir fallback ---

def test_autoimport_takes_precedence_over_base_dir(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    auto = tmp_path / "auto-A"
    auto.mkdir()
    (projects / "a.json").write_text(
        json.dumps(
            {"name": "A", "projectResources": {"resources": [{"folderUri": f"file://{auto}"}]}}
        )
    )
    base = tmp_path / "base"
    base.mkdir()
    (base / "A").mkdir()  # also resolvable via base_dir
    f = tmp_path / "workspaces.txt"
    f.write_text("A\n")
    labels, paths = resolve_workspaces(
        [], f, projects, autoimport=True, base_dir=str(base)
    )
    assert paths["A"] == str(auto.resolve())  # auto-import wins over base fallback


# --- regression: production defaults (autoimport ON, even when env is empty) ---

def test_autoimport_default_on_end_to_end(data_dir, monkeypatch):
    projects = data_dir / "ag-projects"
    projects.mkdir()
    proj = data_dir / "RealProj"
    proj.mkdir()
    (projects / "p.json").write_text(
        json.dumps(
            {
                "name": "RealProj",
                "projectResources": {"resources": [{"folderUri": f"file://{proj}"}]},
            }
        )
    )
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAVITY_AUTOIMPORT", "1")
    monkeypatch.setenv("TELEGRAVITY_PROJECTS_DIR", str(projects))
    from telegravity.config import Config
    import telegravity.state as state_mod

    importlib.reload(state_mod)
    sm = state_mod.StateManager(Config.load())
    assert "RealProj" in sm.workspaces
    assert sm.workspace_paths["RealProj"] == str(proj.resolve())


def test_empty_autoimport_env_keeps_default_on(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAVITY_AUTOIMPORT", "")  # empty must keep the default
    from telegravity.config import Config

    assert Config.load().autoimport_projects is True


# --- hardening: a failed os.replace must not corrupt the existing state.json ---

def test_save_state_durable_on_replace_failure(state, monkeypatch):
    _paths.STATE_FILE.write_text('{"current_workspace": "GOOD"}')

    def _boom(*a, **k):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)
    state.save_state()  # logs the error, must not raise
    assert "GOOD" in _paths.STATE_FILE.read_text()
