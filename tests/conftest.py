"""Shared test fixtures.

Every test runs in a fresh tmp directory with ``TELEGRAVITY_DATA_DIR`` pinned
under it, so neither a local ``.env`` in the developer's repo nor a real
``~/.telegravity`` can leak into the suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import telegravity.paths as paths


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Fresh cwd + per-test data dir; ``paths`` re-resolved to match."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(tmp_path / "data"))
    paths.refresh()
    yield tmp_path


@pytest.fixture(autouse=True)
def _no_autoimport(monkeypatch):
    """Hermetic by default: never auto-import the developer's real Antigravity
    projects, and ignore any host-set workspace env. Tests that exercise
    auto-import opt back in with a tmp dir."""
    monkeypatch.setenv("TELEGRAVITY_AUTOIMPORT", "0")
    monkeypatch.delenv("TELEGRAVITY_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("TELEGRAVITY_WORKSPACE_BASE", raising=False)


@pytest.fixture
def data_dir(_isolated_cwd) -> Path:
    """The per-test data dir (already pinned by the autouse fixture)."""
    target = paths.DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "42")
    monkeypatch.delenv("CHAT_ID", raising=False)
    monkeypatch.setenv("ENABLE_SHELL_EXEC", "0")
    monkeypatch.setenv("ENABLE_FILE_VIEW", "0")
    monkeypatch.setenv("ENABLE_FILE_WRITE", "0")
    # Keep tests hermetic: never auto-import the developer's real Antigravity
    # projects, and ignore any host-set workspace env.
    monkeypatch.setenv("TELEGRAVITY_AUTOIMPORT", "0")
    monkeypatch.delenv("TELEGRAVITY_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("TELEGRAVITY_WORKSPACE_BASE", raising=False)
    from telegravity.config import Config

    return Config.load()


@pytest.fixture
def state(config, data_dir):
    import importlib
    import telegravity.state as state_mod

    importlib.reload(state_mod)
    return state_mod.StateManager(config)
