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
