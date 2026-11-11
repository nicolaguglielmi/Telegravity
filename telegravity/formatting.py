"""Helpers for rendering Telegram messages.

We use MarkdownV2 because legacy Markdown is forgiving about unescaped
characters until it isn't — and "isn't" usually means a user message containing
an underscore or asterisk silently fails to send.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

_MD2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"

# Telegram caps a text message at 4096 UTF-16 code units — not characters.
# Anything outside the BMP (most emoji) costs two units, and a variation
# selector another one, so "🛰️" is three units where len() says two. The
# helpers below measure in UTF-16 so an emoji-dense message is split by the
# same rule Telegram applies; the margin under 4096 covers Telegram's own
# accounting of entities.
def md2(text: str) -> str:
    """Escape user-supplied text for MarkdownV2."""
    out = []
    for ch in text:
        if ch in _MD2_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


TELEGRAM_TEXT_LIMIT = 4096
SAFE_TEXT_LIMIT = 4000


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units, which is what Telegram counts."""
    return len(text.encode("utf-16-le")) // 2


def _longest_prefix(text: str, limit: int) -> int:
    """Characters in the longest prefix of ``text`` fitting ``limit`` units.

    Slicing is by code point, so a surrogate pair is never cut in half.
    """
    if utf16_len(text) <= limit:
        return len(text)
    # Every character costs at least one unit, so `limit` characters is an
    # upper bound on the answer.
    lo, hi = 0, min(len(text), limit)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if utf16_len(text[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo


def split_message(text: str, limit: int = SAFE_TEXT_LIMIT) -> List[str]:
    """Split plain text into Telegram-sized chunks, preferring line breaks.

    For *unformatted* text only. Splitting MarkdownV2 at an arbitrary offset
    can cut an escape sequence or a code fence in half and Telegram rejects
    the whole message, so formatted senders truncate instead of chunking.

    Always returns at least one chunk, and never an empty one (Telegram
    refuses to send an empty message).
    """
    if limit < 2:
        raise ValueError("limit must be at least 2 UTF-16 units")
    if utf16_len(text) <= limit:
        return [text]

    chunks: List[str] = []
    rest = text
    while utf16_len(rest) > limit:
        cut = _longest_prefix(rest, limit)
        if cut < 1:  # pragma: no cover - limit >= 2 always fits one character
            break
        # Prefer the last line break inside the window; a single line longer
        # than the whole budget falls back to the hard cut.
        newline = rest.rfind("\n", 0, cut + 1)
        if newline > 0:
            cut = newline
        head, rest = rest[:cut].rstrip(), rest[cut:].lstrip("\n")
        if head:
            chunks.append(head)
    if rest.strip():
        chunks.append(rest)
    return chunks or [text[: _longest_prefix(text, limit)]]


def code_block(text: str, language: str = "") -> str:
    """Render a fenced code block. Body is intentionally unescaped."""
    body = text.replace("\\", "\\\\").replace("`", "\\`")
    return f"```{language}\n{body}\n```"


def inline_code(text: str) -> str:
    body = text.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{body}`"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short(text: str, limit: int = 30) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def truncate_block(text: str, limit: int = 3500, suffix: str = "\n… (truncated)") -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix


_BADGES = {
    "active": "🟢",
    "idle": "🟡",
    "offline": "⚪",
    "thinking": "💭",
    "executing": "⚡",
    "done": "✅",
    "error": "❌",
    "waiting": "🛰️",
}


def badge(name: str) -> str:
    return _BADGES.get(name, "•")
