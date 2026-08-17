import pytest

from telegravity.config import Config, ConfigError


def test_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN"):
        Config.load()


def test_requires_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    with pytest.raises(ConfigError, match="AUTHORIZED_CHAT_ID"):
        Config.load()


def test_legacy_chat_id_accepted(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.setenv("CHAT_ID", "99")
    cfg = Config.load()
    assert cfg.authorized_chat_id == 99


def test_chat_id_must_be_int(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "not-a-number")
    with pytest.raises(ConfigError, match="integer"):
        Config.load()


def test_workspaces_parsed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("INITIAL_WORKSPACES", "  alpha , beta,, gamma ")
    cfg = Config.load()
    assert cfg.initial_workspaces == ["alpha", "beta", "gamma"]


def test_truthy_flags(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("ENABLE_SHELL_EXEC", "yes")
    monkeypatch.setenv("ENABLE_FILE_VIEW", "0")
    cfg = Config.load()
    assert cfg.enable_shell_exec is True
    assert cfg.enable_file_view is False


def test_data_dir_env_fallback(monkeypatch, data_dir):
    """With no .env anywhere up from cwd, <data_dir>/.env is loaded."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    (data_dir / ".env").write_text("TELEGRAM_TOKEN=global-token\nAUTHORIZED_CHAT_ID=7\n")
    cfg = Config.load()
    assert cfg.telegram_token == "global-token"
    assert cfg.authorized_chat_id == 7


def test_cwd_env_wins_over_data_dir_env(monkeypatch, data_dir, tmp_path):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    (data_dir / ".env").write_text("TELEGRAM_TOKEN=global-token\nAUTHORIZED_CHAT_ID=7\n")
    (tmp_path / ".env").write_text("TELEGRAM_TOKEN=local-token\nAUTHORIZED_CHAT_ID=8\n")
    cfg = Config.load()
    assert cfg.telegram_token == "local-token"
    assert cfg.authorized_chat_id == 8


def test_global_env_fills_gaps_left_by_unrelated_cwd_env(monkeypatch, data_dir, tmp_path):
    """An unrelated project's .env up the cwd chain must not mask the global
    config — the fallback layers underneath whatever was found."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    (tmp_path / ".env").write_text("DATABASE_URL=postgres://elsewhere\n")
    (data_dir / ".env").write_text("TELEGRAM_TOKEN=global-token\nAUTHORIZED_CHAT_ID=7\n")
    cfg = Config.load()
    assert cfg.telegram_token == "global-token"
    assert cfg.authorized_chat_id == 7


def test_data_dir_setting_in_dotenv_relocates_paths(monkeypatch, tmp_path):
    """TELEGRAVITY_DATA_DIR set in a .env (not the real environment) must
    actually move the data dir — paths re-resolve after load_dotenv."""
    import telegravity.paths as paths

    monkeypatch.delenv("TELEGRAVITY_DATA_DIR", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("AUTHORIZED_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    paths.refresh()
    custom = tmp_path / "custom-data"
    (tmp_path / ".env").write_text(
        f"TELEGRAM_TOKEN=t\nAUTHORIZED_CHAT_ID=1\nTELEGRAVITY_DATA_DIR={custom}\n"
    )
    cfg = Config.load()
    assert cfg.telegram_token == "t"
    assert paths.DATA_DIR == custom.resolve()
    assert paths.STATE_FILE == custom.resolve() / "state.json"
