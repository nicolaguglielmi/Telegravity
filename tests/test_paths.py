import importlib
import os
from pathlib import Path


def test_data_dir_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAVITY_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    import telegravity.paths as paths

    importlib.reload(paths)
    assert paths.DATA_DIR == tmp_path / "data"


def test_data_dir_env_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-data"
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(override))
    import telegravity.paths as paths

    importlib.reload(paths)
    assert paths.DATA_DIR == override.resolve()


def test_ensure_data_dir_creates_missing(monkeypatch, tmp_path):
    override = tmp_path / "freshly-created"
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(override))
    import telegravity.paths as paths

    importlib.reload(paths)
    assert not override.exists()
    paths.ensure_data_dir()
    assert override.exists()


def test_ensure_data_dir_idempotent(monkeypatch, tmp_path):
    override = tmp_path / "exists-already"
    override.mkdir()
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(override))
    import telegravity.paths as paths

    importlib.reload(paths)
    # Should not raise even if dir already there
    paths.ensure_data_dir()
    paths.ensure_data_dir()
