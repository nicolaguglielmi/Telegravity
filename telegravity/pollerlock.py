"""Single-poller election via an advisory file lock.

Two MCP clients (e.g. the Antigravity hub and the Antigravity IDE, which read
the same ``mcp_config.json``) each spawn their own ``telegravity`` process with
the same ``TELEGRAM_TOKEN``. When both long-poll ``getUpdates``, Telegram
answers 409 Conflict and delivers each update to whichever poll happens to win
— instructions silently vanish into the losing process's buffer.

Whoever holds an exclusive ``flock`` on ``<DATA_DIR>/poller.lock`` runs the
Telegram poller; every other instance stands by, keeps serving MCP tools, and
periodically retries the lock so a survivor takes over when the holder exits
(the kernel drops the lock with the process — no stale-lock cleanup needed).

The lock file is created once and never unlinked: removing it would let a new
process lock the fresh inode while the old holder still locks the old one,
i.e. two "holders". Its content (the holder's PID) is informational only.

``fcntl`` is POSIX-only; on platforms without it (Windows) the guard degrades
to a no-op and every instance behaves as the holder — exactly the pre-guard
behavior.
"""

from __future__ import annotations

import errno
import logging
import os
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover — Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

from . import paths

logger = logging.getLogger(__name__)

LOCK_FILENAME = "poller.lock"
# How often a standby instance retries the lock — i.e. the worst-case lag
# before a survivor takes over polling after the holder exits.
POLLER_LOCK_RETRY_SEC = 10.0

_CONTENTION_ERRNOS = (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES)


class PollerLock:
    """Exclusive advisory lock electing the one process that polls Telegram."""

    def __init__(self) -> None:
        self._fd: Optional[int] = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def try_acquire(self) -> bool:
        """Try to become the poller; True if this instance now holds the lock.

        Idempotent, and never raises: if the locking *mechanism* is unavailable
        (no ``fcntl``, unwritable data dir, filesystem without ``flock``) the
        instance proceeds as holder — a broken guard must not take the bot
        offline. Only a live rival actually holding the lock returns False.
        """
        if self._held:
            return True
        if fcntl is None:
            self._held = True
            return True
        lock_path = paths.DATA_DIR / LOCK_FILENAME
        try:
            paths.ensure_data_dir()
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as exc:
            logger.warning(
                "Poller lock %s unavailable (%s) — polling without the "
                "single-poller guard",
                lock_path,
                exc,
            )
            self._held = True
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in _CONTENTION_ERRNOS:
                return False  # a rival instance holds the lock
            logger.warning(
                "flock on %s failed (%s) — polling without the "
                "single-poller guard",
                lock_path,
                exc,
            )
            self._held = True
            return True
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
        except OSError:
            pass  # the PID is informational; the lock itself is what matters
        self._fd = fd
        self._held = True
        return True

    def release(self) -> None:
        """Drop the lock; no-op if not held. Closing the fd releases the flock."""
        fd, self._fd = self._fd, None
        self._held = False
        if fd is not None:
            try:
                os.close(fd)
            except OSError:  # pragma: no cover — defensive double-close guard
                pass
