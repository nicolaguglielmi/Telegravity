"""Single-poller lock: election, takeover, and degraded modes.

``flock`` locks belong to the open file description, not the process, so two
``PollerLock`` instances in the same test process genuinely contend — these
tests exercise the real mechanism without spawning subprocesses.
"""

import errno
import logging
import os

import pytest

import telegravity.paths as paths
from telegravity import pollerlock
from telegravity.pollerlock import PollerLock


@pytest.fixture
def lock():
    lk = PollerLock()
    yield lk
    lk.release()


def test_first_instance_acquires_and_creates_lock_file(lock, data_dir):
    assert lock.try_acquire() is True
    assert lock.held
    assert (data_dir / pollerlock.LOCK_FILENAME).exists()


def test_second_instance_refused_until_holder_releases(data_dir):
    holder, rival = PollerLock(), PollerLock()
    try:
        assert holder.try_acquire() is True
        assert rival.try_acquire() is False
        assert not rival.held
        holder.release()
        # The survivor takes over once the holder is gone.
        assert rival.try_acquire() is True
        assert rival.held
    finally:
        holder.release()
        rival.release()


def test_try_acquire_is_idempotent(lock, data_dir):
    assert lock.try_acquire()
    assert lock.try_acquire()
    assert lock.held


def test_release_without_acquire_is_noop():
    PollerLock().release()  # must not raise


def test_reacquire_after_release(lock, data_dir):
    assert lock.try_acquire()
    lock.release()
    assert not lock.held
    assert lock.try_acquire()
    assert lock.held


def test_lock_file_records_holder_pid(lock, data_dir):
    lock.try_acquire()
    content = (data_dir / pollerlock.LOCK_FILENAME).read_text()
    assert content.strip() == str(os.getpid())


def test_pid_write_failure_is_ignored(monkeypatch, data_dir):
    def boom(fd, length):
        raise OSError(errno.EIO, "io error")

    monkeypatch.setattr(pollerlock.os, "ftruncate", boom)
    lk = PollerLock()
    try:
        assert lk.try_acquire() is True  # the PID note is best-effort
        assert lk.held
    finally:
        lk.release()


def test_no_fcntl_platform_degrades_to_holder(monkeypatch):
    """Windows fallback: no advisory locks — every instance polls (pre-guard
    behavior)."""
    monkeypatch.setattr(pollerlock, "fcntl", None)
    a, b = PollerLock(), PollerLock()
    assert a.try_acquire() is True
    assert b.try_acquire() is True
    assert a.held and b.held
    a.release()
    b.release()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_data_dir_degrades_to_holder(monkeypatch, tmp_path, caplog):
    """A broken lock file must not take the bot offline: poll anyway."""
    ro_parent = tmp_path / "ro"
    ro_parent.mkdir()
    monkeypatch.setenv("TELEGRAVITY_DATA_DIR", str(ro_parent / "data"))
    paths.refresh()
    ro_parent.chmod(0o500)
    lk = PollerLock()
    try:
        with caplog.at_level(logging.WARNING):
            assert lk.try_acquire() is True
        assert lk.held
        assert "single-poller guard" in caplog.text
    finally:
        lk.release()
        ro_parent.chmod(0o755)


def test_flock_unsupported_degrades_to_holder(monkeypatch, data_dir, caplog):
    """e.g. a network filesystem without flock: warn and poll anyway."""

    class _BrokenFlock:
        LOCK_EX = 2
        LOCK_NB = 4

        @staticmethod
        def flock(fd, op):
            raise OSError(errno.ENOTSUP, "flock not supported")

    monkeypatch.setattr(pollerlock, "fcntl", _BrokenFlock)
    lk = PollerLock()
    try:
        with caplog.at_level(logging.WARNING):
            assert lk.try_acquire() is True
        assert lk.held
        assert "single-poller guard" in caplog.text
    finally:
        lk.release()
