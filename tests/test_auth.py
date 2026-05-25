from unittest.mock import MagicMock

from telegravity.auth import AuthGate


def _message(user_id):
    m = MagicMock()
    m.from_user.id = user_id
    m.from_user.username = "tester"
    m.text = "hi"
    return m


def _callback(user_id):
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "ui_menu"
    return cb


def test_message_allowed_only_for_authorized():
    gate = AuthGate(authorized_chat_id=42)
    assert gate.message_allowed(_message(42)) is True
    assert gate.message_allowed(_message(7)) is False


def test_callback_allowed_only_for_authorized():
    gate = AuthGate(authorized_chat_id=42)
    assert gate.callback_allowed(_callback(42)) is True
    assert gate.callback_allowed(_callback(7)) is False


def test_missing_user_rejected():
    gate = AuthGate(42)
    msg = MagicMock()
    msg.from_user = None
    assert gate.message_allowed(msg) is False
    assert gate.message_allowed(None) is False


def test_missing_callback_user_rejected():
    gate = AuthGate(42)
    cb = MagicMock()
    cb.from_user = None
    assert gate.callback_allowed(cb) is False
    assert gate.callback_allowed(None) is False
