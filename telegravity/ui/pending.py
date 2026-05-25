"""In-memory registry of pending confirmations.

Used to gate destructive or potentially sensitive actions (shell exec, file
view) behind a tap-to-confirm button. Each entry has a short TTL so abandoned
prompts don't accumulate.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class PendingAction:
    kind: str          # "shell" | "file"
    payload: str       # the command or path
    created_at: float
    chat_id: int


class PendingRegistry:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._items: Dict[str, PendingAction] = {}

    def add(self, kind: str, payload: str, chat_id: int) -> str:
        self._gc()
        token = secrets.token_urlsafe(8)
        self._items[token] = PendingAction(kind, payload, time.time(), chat_id)
        return token

    def take(self, token: str) -> Optional[PendingAction]:
        self._gc()
        return self._items.pop(token, None)

    def cancel(self, token: str) -> bool:
        return self._items.pop(token, None) is not None

    def _gc(self) -> None:
        cutoff = time.time() - self.ttl
        expired = [t for t, v in self._items.items() if v.created_at < cutoff]
        for t in expired:
            self._items.pop(t, None)
