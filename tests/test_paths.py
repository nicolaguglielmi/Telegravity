import importlib


def test_data_dir_defaults_to_home(monkeypatch, tmp_path):
    # No override + an arbitrary cwd (as an MCP client would launch us) must
    # still land on a fixed, writable per-user location — never ``cwd/data``.
    monkeypatch.delenv("TELEGRAVITY_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    import telegravity.paths as paths

    importlib.reload(paths)
    assert paths.DATA_DIR == tmp_path / ".telegravity"


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


def test_refresh_reresolves_every_constant(monkeypatch, tmp_path):
    import telegravity.paths as paths

    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(tmp_path / "a"))
    paths.refresh()
    assert paths.DATA_DIR == (tmp_path / "a").resolve()
    assert paths.ENV_FILE == paths.DATA_DIR / ".env"

    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(tmp_path / "b"))
    paths.refresh()
    assert paths.DATA_DIR == (tmp_path / "b").resolve()
    assert paths.STATE_FILE == paths.DATA_DIR / "state.json"
    assert paths.WORKSPACES_FILE == paths.DATA_DIR / "workspaces.txt"
