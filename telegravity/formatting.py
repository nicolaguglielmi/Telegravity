"""Helpers for rendering Telegram messages.

We use MarkdownV2 because legacy Markdown is forgiving about unescaped
characters until it isn't — and "isn't" usually means a user message containing
an underscore or asterisk silently fails to send.
"""

from __future__ import annotations

from datetime import datetime, timezone

_MD2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"


def md2(text: str) -> str:
    """Escape user-supplied text for MarkdownV2."""
    out = []
    for ch in text:
        if ch in _MD2_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


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
