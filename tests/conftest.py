"""Shared test fixtures.

We point ``TELEGRAVITY_DATA_DIR`` at a fresh tmp dir for every test so the state
manager's persistence machinery has somewhere to write without trampling real
user data.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Run every test in a fresh tmp directory so any local ``.env`` file in
    the developer's repo cannot leak into ``Config.load()``."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "data"
    target.mkdir()
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(target))
    # Re-import paths so DATA_DIR re-resolves to our tmp dir.
    import telegravity.paths as paths

    importlib.reload(paths)
    yield target


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "42")
    monkeypatch.delenv("CHAT_ID", raising=False)
    monkeypatch.setenv("ENABLE_SHELL_EXEC", "0")
    monkeypatch.setenv("ENABLE_FILE_VIEW", "0")
    from telegravity.config import Config

    return Config.load()


@pytest.fixture
def state(config, data_dir):
    import importlib
    import telegravity.state as state_mod

    importlib.reload(state_mod)
    return state_mod.StateManager(config)
