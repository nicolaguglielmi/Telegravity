import time

from telegravity.ui.pending import PendingRegistry


def test_add_returns_unique_token():
    r = PendingRegistry(ttl_seconds=10)
    t1 = r.add("shell", "ls", chat_id=42)
    t2 = r.add("shell", "ls", chat_id=42)
    assert t1 != t2


def test_take_returns_payload_then_removes():
    r = PendingRegistry(ttl_seconds=10)
    token = r.add("shell", "pytest", 42)
    item = r.take(token)
    assert item is not None
    assert item.kind == "shell"
    assert item.payload == "pytest"
    assert item.chat_id == 42
    # Already consumed
    assert r.take(token) is None


def test_cancel_returns_true_then_false():
    r = PendingRegistry(ttl_seconds=10)
    token = r.add("file", "README.md", 42)
    assert r.cancel(token) is True
    assert r.cancel(token) is False


def test_ttl_expires_entries(monkeypatch):
    r = PendingRegistry(ttl_seconds=1)
    token = r.add("shell", "ls", 42)
    # Move time forward
    future = time.time() + 5
    monkeypatch.setattr(time, "time", lambda: future)
    assert r.take(token) is None


def test_gc_runs_on_add_and_take():
    r = PendingRegistry(ttl_seconds=0)  # immediate expiry
    t1 = r.add("shell", "a", 42)
    # ttl 0 → gc on next add evicts the previous one
    t2 = r.add("shell", "b", 42)
    assert r.take(t1) is None
    # t2 also expired by the time we call take
    assert r.take(t2) is None
