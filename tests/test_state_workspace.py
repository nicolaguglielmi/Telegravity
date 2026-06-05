"""Tests for StateManager workspace path handling + persistence."""

import importlib

from telegravity import paths as _paths


def test_select_workspace_sets_path(state):
    state.workspaces = ["A"]
    state.workspace_paths = {"A": "/tmp/a-root"}
    assert state.select_workspace("A") is True
    assert state.current_workspace == "A"
    assert state.workspace_root() == "/tmp/a-root"


def test_select_workspace_unknown_returns_false(state):
    state.workspaces = ["A"]
    assert state.select_workspace("Nope") is False


def test_workspace_root_falls_back_to_persisted(state):
    state.workspaces = ["A"]
    state.workspace_paths = {}  # no live mapping
    state.current_workspace = "A"
    state.current_workspace_path = "/persisted/path"
    assert state.workspace_root() == "/persisted/path"


def test_workspace_root_none_without_selection(state):
    state.workspaces = []
    state.current_workspace = None
    state.current_workspace_path = None
    assert state.workspace_root() is None


def test_workspace_path_persists_across_reload(state, data_dir):
    state.workspaces = ["A"]
    state.workspace_paths = {"A": str(data_dir)}
    state.select_workspace("A")  # writes state.json with the path

    import telegravity.state as state_mod

    importlib.reload(state_mod)
    sm2 = state_mod.StateManager(state.config)
    assert sm2.current_workspace == "A"
    assert sm2.current_workspace_path == str(data_dir)


def test_save_state_is_atomic_no_tmp_left(state):
    state.save_state()
    assert _paths.STATE_FILE.exists()
    tmp = _paths.STATE_FILE.with_name(_paths.STATE_FILE.name + ".tmp")
    assert not tmp.exists()
